"""Tests for SS-18: Telegram Bot Interface.

See docs/sub-specs/SS-18.md §Acceptance Criteria
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from custom.output.telegram_commands import (
    format_alerts,
    format_health,
    format_help,
    format_levels,
    format_macro,
    format_regime,
    format_risk,
    format_signal_report,
    format_trade_plan,
    handle_command,
)
from custom.utils.db import get_db, init_db, insert_row


@pytest.fixture
def db(tmp_path) -> str:
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


@pytest.fixture
def config() -> dict:
    return {
        "trade_plan": {
            "max_risk_per_trade_pct": 2.0,
            "max_leverage": 3,
            "min_reward_risk_ratio": 1.5,
            "high_confidence_strong_risk": 2.0,
            "high_or_strong_risk": 1.5,
            "medium_confidence_risk": 1.0,
            "low_confidence_risk": 0.5,
            "confluence_zone_width_pct": 0.5,
            "confluence_min_levels": 3,
            "tp1_position_pct": 50,
            "tp2_position_pct": 30,
            "tp3_position_pct": 20,
            "stop_loss_buffer_pct": 0.3,
            "trailing_stop_pct": 2.0,
            "entry_min_signal_strength": "MODERATE",
            "entry_min_confidence": "MEDIUM",
        },
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
            "transitional": {"spot_flow": 0.25, "leverage_pos": 0.25, "options_struct": 0.25, "mean_reversion": 0.25},
        },
        "event_risk": {
            "expiry_24h_btc_threshold": 10000,
            "expiry_48h_btc_threshold": 5000,
            "liq_extreme_usd": 200_000_000,
            "liq_high_usd": 100_000_000,
            "liq_medium_usd": 50_000_000,
            "gamma_flip_close_pct": 1.0,
            "gamma_flip_near_pct": 3.0,
            "dvol_extreme": 80,
            "dvol_high": 60,
            "dvol_moderate": 40,
            "stay_out_threshold": 0.8,
        },
    }


def _seed_signal(db: str) -> None:
    """Seed a signal row."""
    conn = get_db(db)
    try:
        conn.execute(
            """INSERT INTO signals (timestamp, final_score, bias, strength, confidence,
               regime, event_risk, consensus, spot_flow, leverage_pos, options_struct,
               mean_reversion, weights_json, btc_price_at_signal)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-03-01T08:00:00Z", 0.45, "LONG", "MODERATE", "MEDIUM",
             "STRONG_TREND", 0.2, "MODERATE_CONSENSUS",
             0.6, 0.4, -0.1, 0.3, "{}", 100000),
        )
        conn.commit()
    finally:
        conn.close()


class TestFormatSignalReport:
    def test_full_report(self) -> None:
        """AC 1+8: format_signal_report produces readable message."""
        signal = {
            "final_score": 0.45,
            "bias": "LONG",
            "strength": "MODERATE",
            "confidence": "MEDIUM",
            "regime": "STRONG_TREND",
            "event_risk": 0.2,
            "consensus": "MODERATE_CONSENSUS",
            "btc_price": 100000,
            "breakdown": {
                "spot_flow": 0.6,
                "leverage_pos": 0.4,
                "options_struct": -0.1,
                "mean_reversion": 0.3,
            },
        }
        msg = format_signal_report(signal)
        assert "SIGNAL REPORT" in msg
        assert "LONG" in msg
        assert "MODERATE" in msg
        assert "MEDIUM" in msg
        assert "+0.450" in msg
        assert "100,000" in msg
        assert "Spot Flow" in msg

    def test_empty_signal(self) -> None:
        """AC 12: Missing data handled gracefully."""
        msg = format_signal_report({})
        assert "No signal" in msg


class TestFormatTradePlan:
    def test_full_plan(self) -> None:
        """AC 3+9: format_trade_plan produces message with levels."""
        plan = {
            "direction": "LONG",
            "entry_price": 100000,
            "stop_loss": 95000,
            "tp1": 107500,
            "tp2": 112500,
            "tp3": 98000,
            "tp1_pct": 50,
            "tp2_pct": 30,
            "tp3_pct": 20,
            "position_size_usd": 50000,
            "risk_pct": 1.0,
            "leverage": 0.5,
        }
        msg = format_trade_plan(plan)
        assert "LONG" in msg
        assert "100,000" in msg
        assert "95,000" in msg
        assert "107,500" in msg
        assert "50%" in msg

    def test_none_plan(self) -> None:
        """AC 12: None plan returns graceful message."""
        msg = format_trade_plan(None)
        assert "entry gates" in msg.lower() or "no trade" in msg.lower()


class TestFormatLevels:
    def test_zones_formatted(self) -> None:
        """AC 2: format_levels returns confluence zones."""
        zones = [
            {"center": 95000, "strength": 4, "type": "support", "components": ["EMA 200", "Put Wall"]},
            {"center": 105000, "strength": 3, "type": "resistance", "components": ["Call Wall", "EMA 21"]},
        ]
        msg = format_levels(zones)
        assert "CONFLUENCE ZONES" in msg
        assert "95,000" in msg
        assert "105,000" in msg
        assert "SUPPORT" in msg
        assert "RESISTANCE" in msg

    def test_empty_zones(self) -> None:
        """AC 12: Empty zones handled."""
        msg = format_levels([])
        assert "No confluence" in msg


class TestFormatAlerts:
    def test_alerts_with_emoji(self) -> None:
        """AC 10: format_alerts includes priority emoji."""
        alerts = [
            {"priority": "CRITICAL", "trigger": "gamma_flip", "message": "Test"},
            {"priority": "WARNING", "trigger": "funding", "message": "High"},
        ]
        msg = format_alerts(alerts)
        assert "🔴" in msg
        assert "🟡" in msg
        assert "ALERTS" in msg

    def test_no_alerts(self) -> None:
        """AC 12: No alerts returns clean message."""
        msg = format_alerts([])
        assert "No active alerts" in msg


class TestFormatRegime:
    def test_regime_formatted(self) -> None:
        """AC 5: format_regime shows regime and weights."""
        result = {
            "regime": "STRONG_TREND",
            "weights": {"spot_flow": 0.35, "leverage_pos": 0.30, "options_struct": 0.20, "mean_reversion": 0.15},
        }
        msg = format_regime(result)
        assert "STRONG_TREND" in msg
        assert "Spot Flow" in msg
        assert "35%" in msg

    def test_empty_regime(self) -> None:
        """AC 12: Empty regime handled."""
        msg = format_regime({})
        assert "No regime" in msg


class TestFormatRisk:
    def test_risk_levels(self) -> None:
        """AC 4: format_risk shows risk level."""
        msg = format_risk(0.85)
        assert "STAY OUT" in msg

        msg = format_risk(0.5)
        assert "MEDIUM" in msg

        msg = format_risk(0.1)
        assert "LOW" in msg


class TestFormatHealth:
    def test_health_formatted(self) -> None:
        """AC 6: format_health shows source status."""
        report = {
            "sources": {
                "spot_price": {"status": "healthy", "latency_ms": 50},
                "futures_snapshot": {"status": "degraded", "latency_ms": 500},
            },
            "overall_status": "degraded",
        }
        msg = format_health(report)
        assert "HEALTH" in msg
        assert "✅" in msg
        assert "⚠️" in msg
        assert "degraded" in msg


class TestFormatMacro:
    def test_macro_formatted(self) -> None:
        """AC 7: format_macro shows upcoming events."""
        events = [
            {"date": "2026-03-05", "time_utc": "13:30", "event": "CPI Release", "tier": 1},
            {"date": "2026-03-07", "time_utc": "15:00", "event": "Fed Speech", "tier": 2},
        ]
        msg = format_macro(events)
        assert "MACRO EVENTS" in msg
        assert "CPI Release" in msg
        assert "🔴" in msg  # Tier 1
        assert "🟡" in msg  # Tier 2

    def test_no_events(self) -> None:
        """AC 12: No events handled."""
        msg = format_macro([])
        assert "No upcoming" in msg


class TestHandleCommand:
    def test_signal_command(self, db, config) -> None:
        """AC 1: /signal returns formatted signal."""
        _seed_signal(db)
        msg = handle_command("signal", "", db, config)
        assert "SIGNAL REPORT" in msg
        assert "LONG" in msg

    def test_signal_no_data(self, db, config) -> None:
        """AC 12: /signal with no data."""
        msg = handle_command("signal", "", db, config)
        assert "No signal" in msg or "⚠️" in msg

    def test_regime_command(self, db, config) -> None:
        """AC 5: /regime returns regime info."""
        msg = handle_command("regime", "", db, config)
        # Should return something (even TRANSITIONAL fallback)
        assert "REGIME" in msg or "⚠️" in msg

    def test_risk_command(self, db, config) -> None:
        """AC 4: /risk returns event risk."""
        msg = handle_command("risk", "", db, config)
        assert "RISK" in msg or "EVENT" in msg

    def test_health_command(self, db, config) -> None:
        """AC 6: /health returns health status."""
        msg = handle_command("health", "", db, config)
        assert "HEALTH" in msg

    def test_macro_command(self, db, config) -> None:
        """AC 7: /macro returns macro events."""
        msg = handle_command("macro", "", db, config)
        assert "macro" in msg.lower() or "MACRO" in msg

    def test_unknown_command(self, db, config) -> None:
        """AC 11: Unknown commands return help text."""
        msg = handle_command("foobar", "", db, config)
        assert "COMMANDS" in msg

    def test_performance_stub(self, db, config) -> None:
        """Performance command returns stub."""
        msg = handle_command("performance", "", db, config)
        assert "Performance" in msg or "future" in msg

    def test_ai_stub(self, db, config) -> None:
        """AI command returns stub."""
        msg = handle_command("ai", "", db, config)
        assert "AI" in msg or "future" in msg
