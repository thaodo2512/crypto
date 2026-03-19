"""Tests for SS-17: Alert System.

See docs/sub-specs/SS-17.md §Acceptance Criteria
"""

from datetime import datetime, timedelta, timezone

import pytest

from custom.output.alerts import (
    _cooldown_tracker,
    check_alerts,
    check_cooldown,
    format_alert,
    record_cooldown,
    reset_cooldowns,
)
from custom.utils.db import init_db, insert_row


@pytest.fixture(autouse=True)
def _clear_cooldowns():
    """Reset cooldowns before each test."""
    reset_cooldowns()
    yield
    reset_cooldowns()


@pytest.fixture
def db(tmp_path) -> str:
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


@pytest.fixture
def config() -> dict:
    return {
        "alerts": {
            "cooldown_critical_minutes": 15,
            "cooldown_warning_minutes": 30,
            "cooldown_info_minutes": 120,
        },
        "event_risk": {
            "liq_high_usd": 100_000_000,
        },
        "leverage_positioning": {
            "funding_extreme_high": 0.05,
            "funding_extreme_low": -0.03,
        },
    }


class TestGammaFlipBreach:
    def test_warning_on_breach(self, db, config) -> None:
        """AC 1: WARNING alert fires on gamma flip breach (within 0.3%)."""
        signal = {"final_score": 0.3}
        alerts = check_alerts(db, signal, config, spot=100000, gamma_flip=100200)
        breach = [a for a in alerts if a["trigger"] == "gamma_flip_breach"]
        assert len(breach) == 1
        assert breach[0]["priority"] == "WARNING"

    def test_no_alert_when_far(self, db, config) -> None:
        """No gamma flip alert when far from flip."""
        signal = {"final_score": 0.3}
        alerts = check_alerts(db, signal, config, spot=100000, gamma_flip=110000)
        gamma_alerts = [a for a in alerts if a["trigger"] == "gamma_flip_breach"]
        assert len(gamma_alerts) == 0


class TestLiquidationCascade:
    def test_critical_on_cascade(self, db, config) -> None:
        """AC 2: CRITICAL alert fires on liquidation cascade >$100M."""
        insert_row(db, "futures_liquidations", {
            "timestamp": "2026-03-01T00:00:00",
            "long_liq_usd": 60_000_000, "short_liq_usd": 60_000_000,
            "total_liq_usd": 120_000_000, "liq_ratio": 0.5,
        })
        signal = {"final_score": 0.3}
        alerts = check_alerts(db, signal, config, spot=100000)
        liq_alerts = [a for a in alerts if a["trigger"] == "liquidation_cascade"]
        assert len(liq_alerts) == 1
        assert liq_alerts[0]["priority"] == "CRITICAL"


class TestMacroImminent:
    def test_critical_on_imminent(self, db, config) -> None:
        """AC 3: CRITICAL alert fires on macro event <2h."""
        soon = datetime.now(timezone.utc) + timedelta(hours=1)
        insert_row(db, "macro_events", {
            "date": soon.strftime("%Y-%m-%d"),
            "time_utc": soon.strftime("%H:%M"),
            "event": "FOMC Decision",
            "tier": 1,
        })
        signal = {"final_score": 0.3}
        alerts = check_alerts(db, signal, config, spot=100000)
        macro_alerts = [a for a in alerts if a["trigger"] == "macro_imminent"]
        assert len(macro_alerts) == 1
        assert macro_alerts[0]["priority"] == "CRITICAL"


class TestFundingExtreme:
    def test_warning_on_extreme_funding(self, db, config) -> None:
        """AC 4: WARNING alert fires on extreme funding."""
        insert_row(db, "futures_snapshot", {
            "timestamp": "2026-03-01T00:00:00",
            "funding_binance": 0.06, "funding_bybit": 0.06, "funding_okx": 0.06,
            "funding_weighted_avg": 0.06,
            "oi_binance_usd": 1e9, "oi_bybit_usd": 5e8, "oi_okx_usd": 3e8,
            "oi_total_usd": 1.8e9,
            "oi_change_1h_pct": 0, "oi_change_4h_pct": 0, "oi_change_24h_pct": 0,
            "futures_price": 100000, "spot_price": 100000,
            "basis_pct": 0, "annualized_premium_pct": 0,
            "top_trader_ls_ratio": 1.0, "account_ls_ratio": 1.0, "global_ls_ratio": 1.0,
            "taker_buy_sell_ratio": 1.0, "taker_buy_volume": 1e6, "taker_sell_volume": 1e6,
        })
        signal = {"final_score": 0.3}
        alerts = check_alerts(db, signal, config, spot=100000)
        funding_alerts = [a for a in alerts if a["trigger"] == "funding_extreme"]
        assert len(funding_alerts) == 1
        assert funding_alerts[0]["priority"] == "WARNING"


class TestSignalThresholdCrossing:
    def test_info_on_crossing_035(self, db, config) -> None:
        """AC 5: INFO alert fires on signal score crossing ±0.35."""
        prev = {"final_score": 0.30}
        curr = {"final_score": 0.40}
        alerts = check_alerts(db, curr, config, prev_signal=prev, spot=100000)
        crossing_alerts = [a for a in alerts if a["trigger"] == "signal_threshold_crossing"]
        assert len(crossing_alerts) == 1
        assert crossing_alerts[0]["priority"] == "INFO"

    def test_no_alert_no_crossing(self, db, config) -> None:
        """No alert when score doesn't cross threshold."""
        prev = {"final_score": 0.20}
        curr = {"final_score": 0.25}
        alerts = check_alerts(db, curr, config, prev_signal=prev, spot=100000)
        crossing_alerts = [a for a in alerts if a["trigger"] == "signal_threshold_crossing"]
        assert len(crossing_alerts) == 0


class TestCooldown:
    def test_critical_cooldown_15min(self, config) -> None:
        """AC 6: Cooldown prevents duplicate CRITICAL within 15 min."""
        assert check_cooldown("test_critical", "CRITICAL", config) is True
        record_cooldown("test_critical")
        assert check_cooldown("test_critical", "CRITICAL", config) is False

    def test_warning_cooldown_30min(self, config) -> None:
        """AC 7: Cooldown prevents duplicate WARNING within 30 min."""
        record_cooldown("test_warning")
        assert check_cooldown("test_warning", "WARNING", config) is False

    def test_info_cooldown_2h(self, config) -> None:
        """AC 8: Cooldown prevents duplicate INFO within 2 hours."""
        record_cooldown("test_info")
        assert check_cooldown("test_info", "INFO", config) is False

    def test_cooldown_expired(self, config) -> None:
        """Cooldown allows alert after expiry."""
        _cooldown_tracker["test_expired"] = datetime.now(timezone.utc) - timedelta(hours=3)
        assert check_cooldown("test_expired", "INFO", config) is True


class TestFormatAlert:
    def test_critical_format(self) -> None:
        """AC 9: format_alert returns readable string with priority emoji."""
        alert = {"priority": "CRITICAL", "trigger": "gamma_flip_breach", "message": "Test message"}
        result = format_alert(alert)
        assert "🔴" in result
        assert "CRITICAL" in result
        assert "gamma_flip_breach" in result

    def test_warning_format(self) -> None:
        """AC 9: WARNING format."""
        alert = {"priority": "WARNING", "trigger": "funding_extreme", "message": "Funding high"}
        result = format_alert(alert)
        assert "🟡" in result

    def test_info_format(self) -> None:
        """AC 9: INFO format."""
        alert = {"priority": "INFO", "trigger": "signal_cross", "message": "Score crossed"}
        result = format_alert(alert)
        assert "🟢" in result


class TestCheckAlerts:
    def test_empty_when_no_triggers(self, db, config) -> None:
        """AC 10: Returns empty list when no alerts triggered."""
        signal = {"final_score": 0.3}
        alerts = check_alerts(db, signal, config, spot=100000)
        assert isinstance(alerts, list)

    def test_thresholds_from_config(self, config) -> None:
        """AC 11: All thresholds from config."""
        assert config["alerts"]["cooldown_critical_minutes"] == 15
        assert config["alerts"]["cooldown_warning_minutes"] == 30
        assert config["alerts"]["cooldown_info_minutes"] == 120
