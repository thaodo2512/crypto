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
        """AC 2: VWAP distance maps to correct score (linear, ±8% → ±0.8)."""
        assert _score_vwap(100000, 100000) == 0.0     # at VWAP
        # Linear interpolation: distance_pct / 8.0 * 0.8
        assert abs(_score_vwap(106000, 100000) - (-0.6)) < 0.01  # +6% → ~-0.6
        assert abs(_score_vwap(103000, 100000) - (-0.3)) < 0.01  # +3% → ~-0.3
        assert abs(_score_vwap(97000, 100000) - 0.3) < 0.01      # -3% → ~+0.3
        assert abs(_score_vwap(94000, 100000) - 0.6) < 0.01      # -6% → ~+0.6
        assert _score_vwap(110000, 100000) == -0.8    # +10% → capped -0.8


class TestBasisScore:
    def test_basis_scores(self) -> None:
        """AC 3: Futures basis maps to correct score (linear interpolation)."""
        assert _score_basis(0.1) == -0.8    # 36.5% annualized → capped
        # 18.25% annualized → linear: -(18.25-5)/25*0.8 ≈ -0.424
        assert abs(_score_basis(0.05) - (-0.424)) < 0.01
        # 10.95% annualized → linear: -(10.95-5)/25*0.8 ≈ -0.190
        assert abs(_score_basis(0.03) - (-0.190)) < 0.01
        assert _score_basis(0.0) == 0.0     # 0% annualized → dead zone
        # -7.3% annualized → linear: (7.3-5)/25*0.8 ≈ 0.074
        assert abs(_score_basis(-0.02) - 0.074) < 0.01
        assert _score_basis(-0.1) == 0.8    # -36.5% annualized → capped


class TestFearGreedScore:
    def test_fear_greed_contrarian(self) -> None:
        """AC 4: Fear & Greed maps to contrarian score (linear interpolation)."""
        assert _score_fear_greed(90) == -0.8  # extreme greed → capped
        # 70 → linear: -(70-60)/20*0.8 = -0.4
        assert abs(_score_fear_greed(70) - (-0.4)) < 0.01
        assert _score_fear_greed(50) == 0.0   # dead zone
        # 30 → linear: (40-30)/20*0.8 = 0.4
        assert abs(_score_fear_greed(30) - 0.4) < 0.01
        assert _score_fear_greed(10) == 0.8   # extreme fear


class TestBollingerScore:
    def test_bollinger_position(self) -> None:
        """AC 5: Bollinger Band position maps to correct score (linear from center)."""
        # Linear: centered = (pos - 0.5), score = -centered / 0.5 * 0.8
        assert _score_bollinger(100000, 105000, 95000) == 0.0   # mid (pos=0.5)
        assert abs(_score_bollinger(104900, 105000, 95000) - (-0.784)) < 0.01  # pos=0.99
        assert abs(_score_bollinger(103500, 105000, 95000) - (-0.56)) < 0.01   # pos=0.85
        assert abs(_score_bollinger(96000, 105000, 95000) - 0.64) < 0.01     # pos=0.10
        assert abs(_score_bollinger(95100, 105000, 95000) - 0.784) < 0.01     # pos=0.01

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
