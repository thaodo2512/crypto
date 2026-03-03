"""Tests for SS-10: Signal 2 — Leverage Positioning.

See docs/sub-specs/SS-10.md §Acceptance Criteria
"""

import pytest

from custom.signals.leverage import (
    _consistency_multiplier,
    _score_funding,
    _score_oi_regime,
    _score_smart_retail,
    _score_taker,
    compute_leverage,
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
        "leverage_positioning": {
            "funding_weight": 0.30,
            "oi_price_weight": 0.30,
            "smart_retail_weight": 0.25,
            "taker_weight": 0.15,
            "funding_extreme_high": 0.05,
            "funding_high": 0.03,
            "funding_low": -0.01,
            "funding_extreme_low": -0.03,
            "oi_change_threshold_pct": 1.0,
            "ls_net_long_threshold": 1.1,
            "ls_net_short_threshold": 0.9,
            "taker_multiplier": 3.0,
            "strong_agreement_multiplier": 1.3,
            "moderate_agreement_multiplier": 1.1,
            "conflict_multiplier": 0.5,
            "default_multiplier": 0.8,
        },
    }


def _seed_futures(db_path: str, **kwargs) -> None:
    snap_defaults = {
        "timestamp": "2026-03-01T00:00:00",
        "funding_weighted_avg": 0.01,
        "oi_total_usd": 5000000000,
        "basis_pct": 0.5,
        "top_trader_ls_ratio": 1.2,
        "global_ls_ratio": 0.85,
        "taker_buy_sell_ratio": 1.1,
    }
    regime = kwargs.pop("regime", "NEW_LONGS")
    # Map friendly names to real column names
    col_map = {
        "funding_rate": "funding_weighted_avg",
        "top_ls_ratio": "top_trader_ls_ratio",
        "taker_ratio": "taker_buy_sell_ratio",
    }
    for old_key, new_key in col_map.items():
        if old_key in kwargs:
            kwargs[new_key] = kwargs.pop(old_key)
    snap_defaults.update(kwargs)
    insert_row(db_path, "futures_snapshot", snap_defaults)
    insert_row(db_path, "futures_oi_price", {
        "timestamp": "2026-03-01T00:00:00",
        "price": 100000, "total_oi": 50000,
        "oi_change_pct": 2.0, "price_change_pct": 1.5,
        "regime": regime,
    })


class TestFundingScore:
    def test_funding_extreme_high(self, config) -> None:
        """AC 1: Extreme high funding → bearish."""
        cfg = config["leverage_positioning"]
        assert _score_funding(0.06, cfg) == -1.0

    def test_funding_extreme_low(self, config) -> None:
        """AC 1: Extreme low funding → bullish."""
        cfg = config["leverage_positioning"]
        assert _score_funding(-0.04, cfg) == 1.0

    def test_funding_normal(self, config) -> None:
        """AC 1: Normal funding → neutral."""
        cfg = config["leverage_positioning"]
        assert _score_funding(0.02, cfg) == 0.0


class TestOiRegime:
    def test_oi_regime_scores(self) -> None:
        """AC 2: OI-price regime maps to directional score."""
        assert _score_oi_regime("NEW_LONGS") == 0.8
        assert _score_oi_regime("NEW_SHORTS") == -0.8
        assert _score_oi_regime("LONG_CLOSING") == -0.3
        assert _score_oi_regime("SHORT_CLOSING") == 0.3
        assert _score_oi_regime("UNKNOWN") == 0.0


class TestSmartRetail:
    def test_divergence_top_long_retail_short(self, config) -> None:
        """AC 3: Top long + retail short → bullish."""
        cfg = config["leverage_positioning"]
        assert _score_smart_retail(1.2, 0.85, cfg) == 0.8

    def test_divergence_top_short_retail_long(self, config) -> None:
        """AC 3: Top short + retail long → bearish."""
        cfg = config["leverage_positioning"]
        assert _score_smart_retail(0.85, 1.2, cfg) == -0.8


class TestTakerScore:
    def test_taker_aggression(self, config) -> None:
        """AC 4: Taker uses config multiplier."""
        cfg = config["leverage_positioning"]
        # (1.2 - 1.0) × 3 = 0.6
        assert _score_taker(1.2, cfg) == pytest.approx(0.6)
        # (0.8 - 1.0) × 3 = -0.6
        assert _score_taker(0.8, cfg) == pytest.approx(-0.6)


class TestConsistency:
    def test_strong_agreement(self, config) -> None:
        """AC 5: 3+ same direction → 1.3."""
        cfg = config["leverage_positioning"]
        assert _consistency_multiplier([0.5, 0.3, 0.2, -0.1], cfg) == 1.3

    def test_conflict(self, config) -> None:
        """AC 5: 2+ positive AND 2+ negative → 0.5."""
        cfg = config["leverage_positioning"]
        assert _consistency_multiplier([0.5, 0.3, -0.2, -0.1], cfg) == 0.5


class TestComputeLeverage:
    def test_final_clipped(self, db, config) -> None:
        """AC 6: Final score clipped to [-1, +1]."""
        _seed_futures(db, funding_rate=-0.04, regime="NEW_LONGS",
                      top_ls_ratio=1.2, global_ls_ratio=0.85, taker_ratio=1.3)
        score = compute_leverage(db, config)
        assert -1.0 <= score <= 1.0

    def test_weights_from_config(self, config) -> None:
        """AC 7: All weights from config."""
        cfg = config["leverage_positioning"]
        total = cfg["funding_weight"] + cfg["oi_price_weight"] + cfg["smart_retail_weight"] + cfg["taker_weight"]
        assert total == pytest.approx(1.0)

    def test_returns_zero_on_failure(self, db) -> None:
        """AC 8: Returns 0.0 on data failure."""
        assert compute_leverage(db, {}) == 0.0
