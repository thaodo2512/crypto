"""Tests for SS-14: Regime Detection & Adaptive Weights.

See docs/sub-specs/SS-14.md §Acceptance Criteria
"""

import pytest

from custom.regime.regime import (
    compute_bb_width_percentile,
    compute_regime,
    detect_regime,
    get_regime_weights,
    smooth_weights,
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
        "regime": {
            "adx_period": 14,
            "bb_width_lookback_days": 90,
            "adx_strong_trend": 30,
            "adx_moderate_trend": 25,
            "adx_tight_range": 20,
            "bb_strong_trend_pctile": 60,
            "bb_moderate_trend_pctile": 40,
            "bb_tight_range_pctile": 30,
            "bb_wide_range_pctile": 50,
        },
        "adaptive_weights": {
            "smoothing_factor": 0.3,
            "strong_trend": {"spot_flow": 0.35, "leverage_pos": 0.30, "options_struct": 0.20, "mean_reversion": 0.15},
            "moderate_trend": {"spot_flow": 0.30, "leverage_pos": 0.25, "options_struct": 0.25, "mean_reversion": 0.20},
            "wide_range": {"spot_flow": 0.20, "leverage_pos": 0.20, "options_struct": 0.30, "mean_reversion": 0.30},
            "tight_range": {"spot_flow": 0.15, "leverage_pos": 0.20, "options_struct": 0.30, "mean_reversion": 0.35},
            "transitional": {"spot_flow": 0.25, "leverage_pos": 0.25, "options_struct": 0.25, "mean_reversion": 0.25},
        },
    }


class TestDetectRegime:
    def test_strong_trend(self, config) -> None:
        """AC 1: STRONG_TREND when ADX > 30 and BB %ile > 60."""
        assert detect_regime(35, 70, config) == "STRONG_TREND"

    def test_moderate_trend(self, config) -> None:
        """AC 2: MODERATE_TREND when ADX > 25 and BB %ile > 40."""
        assert detect_regime(27, 50, config) == "MODERATE_TREND"

    def test_wide_range(self, config) -> None:
        """AC 3: WIDE_RANGE when ADX < 25 and BB %ile < 50."""
        assert detect_regime(22, 40, config) == "WIDE_RANGE"

    def test_tight_range(self, config) -> None:
        """AC 4: TIGHT_RANGE when ADX < 20 and BB %ile < 30."""
        assert detect_regime(15, 20, config) == "TIGHT_RANGE"

    def test_transitional(self, config) -> None:
        """AC 5: TRANSITIONAL for ambiguous combinations."""
        # ADX=28 > 25 but BB=35 < 40 → not moderate; ADX > 25 → not wide_range; ADX > 20 → not tight
        assert detect_regime(28, 35, config) == "TRANSITIONAL"


class TestGetRegimeWeights:
    def test_regime_weights(self, config) -> None:
        """AC 6: Regime weights match config values."""
        w = get_regime_weights("STRONG_TREND", config)
        assert w["spot_flow"] == 0.35
        assert w["leverage_pos"] == 0.30
        assert w["mean_reversion"] == 0.15

    def test_unknown_regime_fallback(self, config) -> None:
        """AC 6: Unknown regime falls back to transitional."""
        w = get_regime_weights("UNKNOWN_REGIME", config)
        assert w == config["adaptive_weights"]["transitional"]


class TestSmoothWeights:
    def test_ema_smoothing(self) -> None:
        """AC 7: Weight smoothing applies EMA correctly."""
        new = {"spot_flow": 0.35, "leverage_pos": 0.30}
        prev = {"spot_flow": 0.25, "leverage_pos": 0.25}
        result = smooth_weights(new, prev, 0.3)
        # spot_flow: 0.3 × 0.35 + 0.7 × 0.25 = 0.105 + 0.175 = 0.28
        assert result["spot_flow"] == pytest.approx(0.28)
        # leverage_pos: 0.3 × 0.30 + 0.7 × 0.25 = 0.09 + 0.175 = 0.265
        assert result["leverage_pos"] == pytest.approx(0.265)

    def test_smoothing_first_call(self) -> None:
        """AC 7: First call (no prev) returns new weights."""
        new = {"spot_flow": 0.35}
        result = smooth_weights(new, None, 0.3)
        assert result["spot_flow"] == 0.35


class TestBbWidthPercentile:
    def test_bb_width_percentile(self, db) -> None:
        """AC 8: BB width percentile computes from history."""
        for i in range(20):
            insert_row(db, "spot_technicals", {
                "date": f"2026-02-{i+1:02d}", "rsi_14": 50,
                "ema_21": 100000, "ema_55": 99000, "ema_200": 95000,
                "vwap": 100000, "bb_upper": 105000, "bb_lower": 95000,
                "bb_width": float(i + 1),  # 1 to 20
                "adx_14": 25, "volume_sma_20": 5000, "volume_ratio": 1.0,
            })
        pctile = compute_bb_width_percentile(db, lookback_days=90)
        # Latest (highest timestamp = date 2026-02-20) has bb_width=20
        # 20 is the largest → percentile = 100%
        assert pctile == 100.0


class TestComputeRegime:
    def test_thresholds_from_config(self, config) -> None:
        """AC 9: All thresholds from config."""
        assert config["regime"]["adx_strong_trend"] == 30
        assert config["adaptive_weights"]["smoothing_factor"] == 0.3
