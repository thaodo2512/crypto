"""Tests for SS-12: Signal 4 — Mean Reversion.

See docs/sub-specs/SS-12.md §Acceptance Criteria
"""

import pytest

from custom.signals.mean_reversion import (
    _score_basis,
    _score_bollinger,
    _score_fear_greed,
    _score_rsi,
    _score_vwap,
    compute_mean_reversion,
)
from custom.utils.db import init_db, insert_row


@pytest.fixture
def db(tmp_path) -> str:
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


@pytest.fixture
def config() -> dict:
    return {
        "mean_reversion": {
            "rsi_weight": 0.30,
            "vwap_weight": 0.20,
            "basis_weight": 0.20,
            "fear_greed_weight": 0.15,
            "bollinger_weight": 0.15,
            "rsi_extreme_overbought": 80,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "rsi_extreme_oversold": 20,
        },
    }


class TestRsiScore:
    def test_rsi_scores(self, config) -> None:
        """AC 1: RSI maps to correct mean-reversion score."""
        cfg = config["mean_reversion"]
        assert _score_rsi(85, cfg) == -1.0   # extreme overbought
        assert _score_rsi(50, cfg) == 0.0    # neutral
        assert _score_rsi(15, cfg) == 1.0    # extreme oversold


class TestVwapScore:
    def test_vwap_distance(self) -> None:
        """AC 2: VWAP distance maps to correct score."""
        assert _score_vwap(106000, 100000) == -0.8  # +6%
        assert _score_vwap(103000, 100000) == -0.3   # +3%
        assert _score_vwap(100000, 100000) == 0.0    # at VWAP
        assert _score_vwap(97000, 100000) == 0.3     # -3%
        assert _score_vwap(94000, 100000) == 0.8     # -6%


class TestBasisScore:
    def test_basis_scores(self) -> None:
        """AC 3: Futures basis maps to correct score."""
        assert _score_basis(0.1) == -0.8    # 36.5% annualized
        assert _score_basis(0.05) == -0.4   # 18.25% annualized
        assert _score_basis(0.03) == 0.0    # 10.95% annualized
        assert _score_basis(0.0) == 0.3     # 0% annualized
        assert _score_basis(-0.02) == 0.8   # backwardation


class TestFearGreedScore:
    def test_fear_greed_contrarian(self) -> None:
        """AC 4: Fear & Greed maps to contrarian score."""
        assert _score_fear_greed(90) == -0.8  # extreme greed
        assert _score_fear_greed(70) == -0.3
        assert _score_fear_greed(50) == 0.0
        assert _score_fear_greed(30) == 0.3
        assert _score_fear_greed(10) == 0.8   # extreme fear


class TestBollingerScore:
    def test_bollinger_position(self) -> None:
        """AC 5: Bollinger Band position maps to correct score."""
        assert _score_bollinger(104900, 105000, 95000) == -0.8  # 0.99 → upper
        assert _score_bollinger(103500, 105000, 95000) == -0.4  # 0.85
        assert _score_bollinger(100000, 105000, 95000) == 0.0   # mid
        assert _score_bollinger(96000, 105000, 95000) == 0.4    # 0.10
        assert _score_bollinger(95100, 105000, 95000) == 0.8    # 0.01 → lower

    def test_bollinger_zero_range(self) -> None:
        """Edge: Zero BB range returns 0."""
        assert _score_bollinger(100000, 100000, 100000) == 0.0


class TestComputeMeanReversion:
    def test_final_clipped(self, db, config) -> None:
        """AC 6: Final score clipped to [-1, +1]."""
        insert_row(db, "spot_technicals", {
            "date": "2026-03-01", "rsi_14": 85, "ema_21": 100000,
            "ema_55": 99000, "ema_200": 95000, "vwap": 95000,
            "bb_upper": 105000, "bb_lower": 95000, "bb_width": 10,
            "adx_14": 25, "volume_sma_20": 5000, "volume_ratio": 1.0,
        })
        insert_row(db, "spot_price", {
            "timestamp": "2026-03-01T00:00:00",
            "open": 104000, "high": 105000, "low": 103000, "close": 104000,
            "volume": 5000, "quote_volume": 500000000, "num_trades": 1000,
        })
        insert_row(db, "daily_snapshot", {"date": "2026-03-01", "fear_greed": 90})

        score = compute_mean_reversion(db, config)
        assert -1.0 <= score <= 1.0
        assert score < 0  # all components bearish/overbought

    def test_weights_from_config(self, config) -> None:
        """AC 7: All weights from config."""
        cfg = config["mean_reversion"]
        total = cfg["rsi_weight"] + cfg["vwap_weight"] + cfg["basis_weight"] + cfg["fear_greed_weight"] + cfg["bollinger_weight"]
        assert total == pytest.approx(1.0)

    def test_returns_zero_on_failure(self, db) -> None:
        """AC 8: Returns 0.0 on data failure."""
        assert compute_mean_reversion(db, {}) == 0.0
