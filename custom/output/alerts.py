"""Alert system — evaluate triggers and manage cooldowns.

See docs/sub-specs/SS-17.md §10
"""

import logging
from datetime import datetime, timezone
from typing import Any

from custom.utils.db import get_latest
from custom.utils.health import HealthMonitor

logger = logging.getLogger(__name__)

# In-memory cooldown tracker: {trigger_key: last_fired_datetime}
_cooldown_tracker: dict[str, datetime] = {}


def check_alerts(
    db_path: str, signal: dict[str, Any], config: dict,
    prev_signal: dict[str, Any] | None = None,
    spot: float = 0.0, gamma_flip: float | None = None,
) -> list[dict[str, Any]]:
    """Evaluate all alert triggers against current data.

    See docs/sub-specs/SS-17.md §10.1

    Args:
        db_path: Path to SQLite database.
        signal: Current signal dict from engine.
        config: Full settings dict.
        prev_signal: Previous signal dict (for threshold crossing).
        spot: Current spot price.
        gamma_flip: Current gamma flip price.

    Returns:
        List of fired alert dicts.
    """
    alerts_cfg = config.get("alerts", {})
    alerts: list[dict[str, Any]] = []

    # CRITICAL alerts
    alerts.extend(_check_gamma_flip_breach(spot, gamma_flip, alerts_cfg))
    alerts.extend(_check_liquidation_cascade(db_path, config, alerts_cfg))
    alerts.extend(_check_macro_imminent(db_path, alerts_cfg))

    # WARNING alerts
    alerts.extend(_check_funding_extreme(db_path, config, alerts_cfg))

    # INFO alerts
    alerts.extend(_check_signal_threshold_crossing(signal, prev_signal, alerts_cfg))

    return alerts


def check_cooldown(
    trigger: str, priority: str, config: dict
) -> bool:
    """Check if an alert is within its cooldown period.

    See docs/sub-specs/SS-17.md §10.2

    Args:
        trigger: Alert trigger key.
        priority: CRITICAL, WARNING, or INFO.
        config: Full settings dict.

    Returns:
        True if alert can fire (cooldown expired), False if still cooling down.
    """
    alerts_cfg = config.get("alerts", {})

    if priority == "CRITICAL":
        cooldown_minutes = alerts_cfg.get("cooldown_critical_minutes", 15)
    elif priority == "WARNING":
        cooldown_minutes = alerts_cfg.get("cooldown_warning_minutes", 30)
    else:
        cooldown_minutes = alerts_cfg.get("cooldown_info_minutes", 120)

    now = datetime.now(timezone.utc)
    last_fired = _cooldown_tracker.get(trigger)

    if last_fired is None:
        return True

    elapsed = (now - last_fired).total_seconds() / 60.0
    return elapsed >= cooldown_minutes


def record_cooldown(trigger: str) -> None:
    """Record that an alert was fired for cooldown tracking.

    Args:
        trigger: Alert trigger key.
    """
    _cooldown_tracker[trigger] = datetime.now(timezone.utc)


def reset_cooldowns() -> None:
    """Reset all cooldown trackers (for testing)."""
    _cooldown_tracker.clear()


def check_system_health(
    health_monitor: HealthMonitor, config: dict,
) -> list[dict[str, Any]]:
    """Check HealthMonitor for degraded or stale data sources and return alerts.

    Args:
        health_monitor: HealthMonitor instance with recorded source data.
        config: Full settings dict (for cooldown settings).

    Returns:
        List of system health alert dicts.
    """
    report = health_monitor.get_health_report()
    alerts: list[dict[str, Any]] = []

    for source, status in report.get("sources", {}).items():
        if status.get("is_degraded"):
            trigger = f"system_degraded_{source}"
            if check_cooldown(trigger, "CRITICAL", config):
                failures = status.get("consecutive_failures", 0)
                error = status.get("last_error", "unknown")
                alert = _make_alert(
                    "CRITICAL", trigger,
                    f"Data source '{source}' degraded — {failures} consecutive failures. Last error: {error}",
                )
                record_cooldown(trigger)
                alerts.append(alert)
        elif status.get("is_stale"):
            trigger = f"system_stale_{source}"
            if check_cooldown(trigger, "WARNING", config):
                alert = _make_alert(
                    "WARNING", trigger,
                    f"Data source '{source}' is stale — no successful update in >30 min.",
                )
                record_cooldown(trigger)
                alerts.append(alert)

    return alerts


def format_alert(alert: dict[str, Any]) -> str:
    """Format an alert dict into a readable message string.

    See docs/sub-specs/SS-17.md §10

    Args:
        alert: Alert dict with priority, trigger, message.

    Returns:
        Formatted string with priority emoji.
    """
    priority = alert.get("priority", "INFO")
    emoji_map = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🟢"}
    emoji = emoji_map.get(priority, "🟢")
    trigger = alert.get("trigger", "unknown")
    message = alert.get("message", "")

    return f"{emoji} [{priority}] {trigger}: {message}"


# ── Private alert checkers ───────────────────────────────────


def _make_alert(priority: str, trigger: str, message: str) -> dict[str, Any]:
    """Create an alert dict."""
    return {
        "priority": priority,
        "trigger": trigger,
        "message": message,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _check_gamma_flip_breach(
    spot: float, gamma_flip: float | None, alerts_cfg: dict
) -> list[dict[str, Any]]:
    """CRITICAL: Price crosses gamma flip point."""
    if gamma_flip is None or spot <= 0:
        return []

    distance_pct = abs(spot - gamma_flip) / spot * 100
    if distance_pct < 0.5:  # Within 0.5% = breach
        alert = _make_alert(
            "CRITICAL", "gamma_flip_breach",
            f"Price ${spot:,.0f} at gamma flip ${gamma_flip:,.0f} ({distance_pct:.1f}%)",
        )
        if check_cooldown("gamma_flip_breach", "CRITICAL", {"alerts": alerts_cfg}):
            record_cooldown("gamma_flip_breach")
            return [alert]
    return []


def _check_liquidation_cascade(
    db_path: str, config: dict, alerts_cfg: dict
) -> list[dict[str, Any]]:
    """CRITICAL: Total liquidation > $100M."""
    rows = get_latest(db_path, "futures_liquidations", n=1, order_col="timestamp")
    if not rows:
        return []

    total_liq = rows[0].get("total_liq_usd") or 0
    threshold = config.get("event_risk", {}).get("liq_high_usd", 100_000_000)

    if total_liq > threshold:
        alert = _make_alert(
            "CRITICAL", "liquidation_cascade",
            f"Liquidation cascade: ${total_liq / 1_000_000:.0f}M (threshold: ${threshold / 1_000_000:.0f}M)",
        )
        if check_cooldown("liquidation_cascade", "CRITICAL", {"alerts": alerts_cfg}):
            record_cooldown("liquidation_cascade")
            return [alert]
    return []


def _check_macro_imminent(
    db_path: str, alerts_cfg: dict
) -> list[dict[str, Any]]:
    """CRITICAL: Tier 1 macro event < 2 hours away."""
    rows = get_latest(db_path, "macro_events", n=10, order_col="date")
    if not rows:
        return []

    now = datetime.now(timezone.utc)
    for row in rows:
        tier = row.get("tier", 3)
        if tier != 1:
            continue
        try:
            date_str = row.get("date", "")
            time_str = row.get("time_utc", "00:00")
            event_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            hours_until = (event_dt - now).total_seconds() / 3600
            if 0 < hours_until < 2:
                alert = _make_alert(
                    "CRITICAL", "macro_imminent",
                    f"{row.get('event', 'Macro event')} in {hours_until:.1f}h",
                )
                if check_cooldown("macro_imminent", "CRITICAL", {"alerts": alerts_cfg}):
                    record_cooldown("macro_imminent")
                    return [alert]
        except (ValueError, TypeError):
            continue
    return []


def _check_funding_extreme(
    db_path: str, config: dict, alerts_cfg: dict
) -> list[dict[str, Any]]:
    """WARNING: Weighted funding > 0.05% or < -0.03%."""
    rows = get_latest(db_path, "futures_snapshot", n=1, order_col="timestamp")
    if not rows:
        return []

    funding = rows[0].get("funding_weighted_avg") or 0
    lev_cfg = config.get("leverage_positioning", {})
    high = lev_cfg.get("funding_extreme_high", 0.05)
    low = lev_cfg.get("funding_extreme_low", -0.03)

    if funding > high or funding < low:
        alert = _make_alert(
            "WARNING", "funding_extreme",
            f"Funding rate extreme: {funding:.4f}% (thresholds: {low}% / {high}%)",
        )
        if check_cooldown("funding_extreme", "WARNING", {"alerts": alerts_cfg}):
            record_cooldown("funding_extreme")
            return [alert]
    return []


def _check_signal_threshold_crossing(
    signal: dict[str, Any], prev_signal: dict[str, Any] | None, alerts_cfg: dict
) -> list[dict[str, Any]]:
    """INFO: Signal score crosses ±0.35 or ±0.60."""
    if prev_signal is None:
        return []

    curr = abs(signal.get("final_score", 0.0))
    prev = abs(prev_signal.get("final_score", 0.0))

    thresholds = [0.35, 0.60]
    for thresh in thresholds:
        if (prev < thresh <= curr) or (curr < thresh <= prev):
            direction = "above" if curr >= thresh else "below"
            alert = _make_alert(
                "INFO", "signal_threshold_crossing",
                f"Signal crossed {direction} ±{thresh} (now {signal.get('final_score', 0):.3f})",
            )
            trigger_key = f"signal_cross_{thresh}"
            if check_cooldown(trigger_key, "INFO", {"alerts": alerts_cfg}):
                record_cooldown(trigger_key)
                return [alert]
    return []
