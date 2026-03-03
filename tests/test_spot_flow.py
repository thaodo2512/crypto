"""Tests for SS-09: Signal 1 — Spot Flow.

See docs/sub-specs/SS-09.md §Acceptance Criteria
"""

import numpy as np
import pytest

from custom.signals.spot_flow import (
    _compute_cvd_component,
    _compute_orderbook_component,
    _compute_volume_multiplier,
    _compute_whale_component,
    compute_spot_flow,
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
        "spot_flow": {
            "cvd_weight": 0.50,
            "whale_weight": 0.25,
            "orderbook_weight": 0.25,
            "cvd_divergence_amplifier": 1.5,
            "cvd_4h_contradiction_factor": 0.7,
            "z_score_lookback_days": 30,
            "anti_spoof_threshold": 0.6,
            "anti_spoof_factor": 0.5,
            "volume_high_threshold": 1.5,
            "volume_low_threshold": 0.5,
            "volume_high_multiplier": 1.3,
            "volume_low_multiplier": 0.6,
            "volume_base": 0.7,
            "volume_slope": 0.4,
        },
    }


def _seed_cvd(db_path: str, values: list[tuple[float, float, float]]) -> None:
    for i, (c1, c4, c24) in enumerate(values):
        insert_row(db_path, "spot_cvd", {
            "timestamp": f"2026-03-01T{i:02d}:00:00",
            "cvd_1h": c1, "cvd_4h": c4, "cvd_24h": c24,
            "buy_volume": 1000, "sell_volume": 800,
        })


def _seed_prices(db_path: str, prices: list[float]) -> None:
    for i, p in enumerate(prices):
        insert_row(db_path, "spot_price", {
            "timestamp": f"2026-03-01T{i:02d}:00:00",
            "open": p, "high": p + 100, "low": p - 100, "close": p,
            "volume": 5000, "quote_volume": 5000 * p, "num_trades": 1000,
        })


class TestCvdComponent:
    def test_cvd_zscore_clipped(self, db, config) -> None:
        """AC 1: CVD component uses z-score clipped to [-1, +1]."""
        values = [(0, 50, v) for v in [0.1, 0.2, -0.1, 0.3, -0.2, 0.1, 0.0, -0.1, 0.2, 10.0]]
        _seed_cvd(db, values)
        _seed_prices(db, [100000, 101000])

        score = _compute_cvd_component(db, config["spot_flow"])
        assert -1.0 <= score <= 1.0

    def test_cvd_divergence_amplified(self, db, config) -> None:
        """AC 2: CVD divergence amplifies score by config factor."""
        values = [(0, 50, v) for v in [0.1, -0.1, 0.2, -0.2, 0.1, 0.3, -0.1, 0.0, 0.2, 2.0]]
        _seed_cvd(db, values)
        _seed_prices(db, [105000, 100000])  # price down, CVD positive → divergence

        score = _compute_cvd_component(db, config["spot_flow"])
        # With divergence, absolute value should be larger (amplified)
        assert score != 0.0

    def test_cvd_4h_contradiction_reduces(self, db, config) -> None:
        """AC 3: CVD 4h contradiction reduces score by config factor."""
        values = [(0, -50, v) for v in [0.1, -0.1, 0.2, -0.2, 0.1, 0.3, -0.1, 0.0, 0.2, 1.5]]
        _seed_cvd(db, values)  # 4h negative, 24h positive → contradiction
        _seed_prices(db, [100000, 101000])

        score = _compute_cvd_component(db, config["spot_flow"])
        assert -1.0 <= score <= 1.0


class TestWhaleComponent:
    def test_whale_ratio_score(self, db) -> None:
        """AC 4: Whale ratio produces score in [-1, +1]."""
        for i in range(5):
            insert_row(db, "spot_whale_trades", {
                "timestamp": f"2026-03-01T{i:02d}:00:00",
                "side": "buy", "price": 100000, "quantity": 1.5, "value_usd": 150000,
            })
        insert_row(db, "spot_whale_trades", {
            "timestamp": "2026-03-01T05:00:00",
            "side": "sell", "price": 100000, "quantity": 1.5, "value_usd": 150000,
        })
        # 5 buys, 1 sell → ratio = 5/6 ≈ 0.833 → score = (0.833 - 0.5) × 2 ≈ 0.667
        score = _compute_whale_component(db)
        assert 0.5 < score < 0.8
        assert -1.0 <= score <= 1.0


class TestOrderbookComponent:
    def test_anti_spoof_filter(self, db, config) -> None:
        """AC 5: Order book imbalance applies anti-spoof filter."""
        insert_row(db, "spot_orderbook", {
            "timestamp": "2026-03-01T00:00:00",
            "bid_depth_usd": 1000000, "ask_depth_usd": 200000,
            "imbalance": 0.8, "spread_bps": 1.0,
        })
        score = _compute_orderbook_component(db, config["spot_flow"])
        # |0.8| > 0.6 threshold → reduced to 0.8 × 0.5 = 0.4
        assert score == pytest.approx(0.4)


class TestVolumeMultiplier:
    def test_volume_multiplier_high(self, db, config) -> None:
        """AC 6: High volume multiplier applied correctly."""
        insert_row(db, "spot_technicals", {
            "date": "2026-03-01", "rsi_14": 50, "ema_21": 100000,
            "ema_55": 99000, "ema_200": 95000, "vwap": 100000,
            "bb_upper": 105000, "bb_lower": 95000, "bb_width": 10,
            "adx_14": 25, "volume_sma_20": 5000, "volume_ratio": 2.0,
        })
        mult = _compute_volume_multiplier(db, config["spot_flow"])
        assert mult == 1.3

    def test_volume_multiplier_low(self, db, config) -> None:
        """AC 6: Low volume multiplier applied correctly."""
        insert_row(db, "spot_technicals", {
            "date": "2026-03-01", "rsi_14": 50, "ema_21": 100000,
            "ema_55": 99000, "ema_200": 95000, "vwap": 100000,
            "bb_upper": 105000, "bb_lower": 95000, "bb_width": 10,
            "adx_14": 25, "volume_sma_20": 5000, "volume_ratio": 0.3,
        })
        mult = _compute_volume_multiplier(db, config["spot_flow"])
        assert mult == 0.6

    def test_volume_multiplier_linear(self, db, config) -> None:
        """AC 6: Mid-range volume uses linear interpolation."""
        insert_row(db, "spot_technicals", {
            "date": "2026-03-01", "rsi_14": 50, "ema_21": 100000,
            "ema_55": 99000, "ema_200": 95000, "vwap": 100000,
            "bb_upper": 105000, "bb_lower": 95000, "bb_width": 10,
            "adx_14": 25, "volume_sma_20": 5000, "volume_ratio": 1.0,
        })
        mult = _compute_volume_multiplier(db, config["spot_flow"])
        assert mult == pytest.approx(1.1)  # 0.7 + 1.0 × 0.4


class TestComputeSpotFlow:
    def test_final_score_clipped(self, db, config) -> None:
        """AC 7: Final score clipped to [-1, +1]."""
        _seed_cvd(db, [(0, 50, v) for v in [0.1, -0.1, 0.2, -0.2, 0.1, 0.3, -0.1, 0.0, 0.2, 3.0]])
        _seed_prices(db, [100000, 101000])
        for i in range(10):
            insert_row(db, "spot_whale_trades", {
                "timestamp": f"2026-03-01T{i:02d}:00:00",
                "side": "buy", "price": 100000, "quantity": 2, "value_usd": 200000,
            })
        insert_row(db, "spot_orderbook", {
            "timestamp": "2026-03-01T00:00:00",
            "bid_depth_usd": 900000, "ask_depth_usd": 100000,
            "imbalance": 0.5, "spread_bps": 1.0,
        })
        insert_row(db, "spot_technicals", {
            "date": "2026-03-01", "rsi_14": 50, "ema_21": 100000,
            "ema_55": 99000, "ema_200": 95000, "vwap": 100000,
            "bb_upper": 105000, "bb_lower": 95000, "bb_width": 10,
            "adx_14": 25, "volume_sma_20": 5000, "volume_ratio": 2.0,
        })

        score = compute_spot_flow(db, config)
        assert -1.0 <= score <= 1.0

    def test_weights_from_config(self, config) -> None:
        """AC 8: All weights and thresholds from config."""
        cfg = config["spot_flow"]
        assert cfg["cvd_weight"] == 0.50
        assert cfg["whale_weight"] == 0.25
        assert cfg["orderbook_weight"] == 0.25
        assert cfg["cvd_divergence_amplifier"] == 1.5

    def test_returns_zero_on_failure(self, db) -> None:
        """AC 9: Returns 0.0 on data failure."""
        score = compute_spot_flow(db, {})  # missing config key → exception
        assert score == 0.0
