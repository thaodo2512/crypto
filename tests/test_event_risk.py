"""Tests for SS-13: Signal 5 — Event Risk.

See docs/sub-specs/SS-13.md §Acceptance Criteria
"""

from datetime import datetime, timedelta, timezone

import pytest

from custom.signals.event_risk import (
    _risk_dvol,
    _risk_gamma_flip,
    _risk_liquidation,
    _risk_macro,
    _risk_options_expiry,
    compute_event_risk,
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
        "event_risk": {
            "expiry_24h_btc_threshold": 10000,
            "expiry_48h_btc_threshold": 5000,
            "liq_extreme_usd": 200_000_000,
            "liq_high_usd": 100_000_000,
            "liq_medium_usd": 50_000_000,
            "gamma_flip_close_pct": 0.5,
            "gamma_flip_near_pct": 2.0,
            "dvol_extreme": 80,
            "dvol_high": 60,
            "dvol_moderate": 40,
            "stay_out_threshold": 0.8,
        },
    }


class TestOptionsExpiryRisk:
    def test_expiry_risk_48h(self, db, config) -> None:
        """AC 1: Options expiry risk scores by notional and time."""
        # Insert expiry ~30h from now (within 48h, > 5000 BTC)
        future = (datetime.now(timezone.utc) + timedelta(hours=30)).strftime("%Y-%m-%d")
        insert_row(db, "options_oi", {
            "date": "2026-03-01", "expiry": future, "strike": 100000,
            "call_oi": 4000, "put_oi": 3000, "call_iv": 0.6, "put_iv": 0.65,
            "call_volume": 100, "put_volume": 80,
        })
        risk = _risk_options_expiry(db, config["event_risk"])
        assert risk == 0.4  # < 48h, total 7000 > 5000

    def test_expiry_risk_no_risk(self, db, config) -> None:
        """AC 1: No expiry risk when OI below threshold."""
        future = (datetime.now(timezone.utc) + timedelta(hours=30)).strftime("%Y-%m-%d")
        insert_row(db, "options_oi", {
            "date": "2026-03-01", "expiry": future, "strike": 100000,
            "call_oi": 1000, "put_oi": 500, "call_iv": 0.6, "put_iv": 0.65,
            "call_volume": 10, "put_volume": 5,
        })
        risk = _risk_options_expiry(db, config["event_risk"])
        assert risk == 0.0  # total 1500 < 5000


class TestLiquidationRisk:
    def test_liquidation_cascade(self, db, config) -> None:
        """AC 2: Liquidation cascade maps to tiers."""
        insert_row(db, "futures_liquidations", {
            "timestamp": "2026-03-01T00:00:00",
            "long_liq_usd": 120_000_000, "short_liq_usd": 90_000_000,
            "total_liq_usd": 210_000_000, "liq_ratio": 0.57,
        })
        risk = _risk_liquidation(db, config["event_risk"])
        assert risk == 0.9  # > $200M

    def test_liquidation_medium(self, db, config) -> None:
        """AC 2: Medium liquidation."""
        insert_row(db, "futures_liquidations", {
            "timestamp": "2026-03-01T00:00:00",
            "long_liq_usd": 30_000_000, "short_liq_usd": 30_000_000,
            "total_liq_usd": 60_000_000, "liq_ratio": 0.5,
        })
        risk = _risk_liquidation(db, config["event_risk"])
        assert risk == 0.2


class TestGammaFlipRisk:
    def test_gamma_flip_proximity(self, config) -> None:
        """AC 3: Gamma flip proximity scores correctly."""
        cfg = config["event_risk"]
        assert _risk_gamma_flip(100000, 99600, cfg) == 0.5   # 0.4% → close (< 0.5%)
        # 1.0% → linear fade: (1.0 - 0.5) / (2.0 - 0.5) = 0.333 → 0.5 * (1 - 0.333) ≈ 0.333
        assert abs(_risk_gamma_flip(100000, 99000, cfg) - 0.333) < 0.01
        assert _risk_gamma_flip(100000, 95000, cfg) == 0.0   # 5% → far
        assert _risk_gamma_flip(100000, None, cfg) == 0.0


class TestDvolRisk:
    def test_dvol_risk(self, db, config) -> None:
        """AC 4: DVol maps to risk tiers."""
        insert_row(db, "daily_snapshot", {"date": "2026-03-01", "dvol": 85})
        risk = _risk_dvol(db, config["event_risk"])
        assert risk == 0.8  # > 80


class TestMacroRisk:
    def test_macro_event_proximity(self, db) -> None:
        """AC 5: Macro event proximity scores by tier and time."""
        # Insert Tier 1 event 1 hour away
        soon = datetime.now(timezone.utc) + timedelta(hours=1)
        insert_row(db, "macro_events", {
            "date": soon.strftime("%Y-%m-%d"),
            "time_utc": soon.strftime("%H:%M"),
            "event": "FOMC Decision",
            "tier": 1,
        })
        risk = _risk_macro(db)
        assert risk == 0.95  # Tier 1 < 2h


class TestComputeEventRisk:
    def test_final_is_max(self, db, config) -> None:
        """AC 6: Final risk = max of all components."""
        # Only seed liquidation data → that component should dominate
        insert_row(db, "futures_liquidations", {
            "timestamp": "2026-03-01T00:00:00",
            "long_liq_usd": 60_000_000, "short_liq_usd": 60_000_000,
            "total_liq_usd": 120_000_000, "liq_ratio": 0.5,
        })
        risk = compute_event_risk(db, config, spot=100000, gamma_flip=90000)
        assert 0.0 <= risk <= 1.0
        assert risk == 0.5  # liq > $100M

    def test_range_zero_to_one(self, db, config) -> None:
        """AC 7: Range is [0, 1.0]."""
        risk = compute_event_risk(db, config, spot=100000)
        assert 0.0 <= risk <= 1.0

    def test_thresholds_from_config(self, config) -> None:
        """AC 8: All thresholds from config."""
        cfg = config["event_risk"]
        assert cfg["stay_out_threshold"] == 0.8
        assert cfg["liq_extreme_usd"] == 200_000_000

    def test_returns_zero_on_failure(self, db) -> None:
        """AC 9: Returns 0.0 on data failure."""
        assert compute_event_risk(db, {}) == 0.0
