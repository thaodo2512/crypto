"""Telegram bot command handlers and message formatters.

See docs/sub-specs/SS-18.md §12
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from custom.calculators.confluence import compute_confluence_zones
from custom.output.alerts import check_alerts, format_alert
from custom.regime.regime import compute_regime
from custom.signals.engine import assemble_signal, compute_final_signal
from custom.signals.event_risk import compute_event_risk
from custom.trade_plan.plan import generate_trade_plan
from custom.utils.db import get_latest, query

logger = logging.getLogger(__name__)


# ── Message Formatters ───────────────────────────────────────


def format_signal_report(signal: dict[str, Any]) -> str:
    """Format signal dict into a Telegram message.

    See docs/sub-specs/SS-18.md §12.2

    Args:
        signal: Signal dict from engine.

    Returns:
        Formatted message string.
    """
    if not signal:
        return "⚠️ No signal data available."

    score = signal.get("final_score", 0.0)
    bias = signal.get("bias", "NEUTRAL")
    strength = signal.get("strength", "NEUTRAL")
    confidence = signal.get("confidence", "LOW")
    regime = signal.get("regime", "UNKNOWN")
    event_risk = signal.get("event_risk", 0.0)
    consensus = signal.get("consensus", "MIXED")
    breakdown = signal.get("breakdown", {})

    bias_emoji = {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "⚪"}.get(bias, "⚪")
    strength_bar = _strength_bar(abs(score))

    lines = [
        f"📊 SIGNAL REPORT",
        f"",
        f"{bias_emoji} {bias} | {strength} | {confidence} confidence",
        f"Score: {score:+.3f} {strength_bar}",
        f"Regime: {regime} | Consensus: {consensus}",
        f"Event Risk: {event_risk:.2f}",
        f"",
        f"📈 Breakdown:",
        f"  Spot Flow:    {breakdown.get('spot_flow', 0):+.3f}",
        f"  Leverage:     {breakdown.get('leverage_pos', 0):+.3f}",
        f"  Options:      {breakdown.get('options_struct', 0):+.3f}",
        f"  Mean Rev:     {breakdown.get('mean_reversion', 0):+.3f}",
    ]

    price = signal.get("btc_price", 0)
    if price:
        lines.insert(1, f"BTC: ${price:,.0f}")

    return "\n".join(lines)


def format_trade_plan(plan: dict[str, Any]) -> str:
    """Format trade plan for Telegram.

    See docs/sub-specs/SS-18.md §12.2

    Args:
        plan: Trade plan dict.

    Returns:
        Formatted message string.
    """
    if not plan:
        return "⚠️ No trade plan — entry gates not met."

    direction = plan.get("direction", "LONG")
    emoji = "🟢" if direction == "LONG" else "🔴"

    lines = [
        f"{emoji} TRADE PLAN — {direction}",
        f"",
        f"Entry:  ${plan.get('entry_price', 0):,.0f}",
        f"Stop:   ${plan.get('stop_loss', 0):,.0f}",
        f"TP1:    ${plan.get('tp1', 0):,.0f} ({plan.get('tp1_pct', 50)}%)",
        f"TP2:    ${plan.get('tp2', 0):,.0f} ({plan.get('tp2_pct', 30)}%)",
        f"TP3:    trailing {plan.get('tp3_pct', 20)}%",
        f"",
        f"Size:   ${plan.get('position_size_usd', 0):,.0f}",
        f"Risk:   {plan.get('risk_pct', 0):.1f}%",
        f"Lever:  {plan.get('leverage', 0):.1f}x",
    ]

    return "\n".join(lines)


def format_levels(zones: list[dict[str, Any]]) -> str:
    """Format confluence zones for Telegram.

    See docs/sub-specs/SS-18.md §12.2

    Args:
        zones: List of confluence zone dicts.

    Returns:
        Formatted message string.
    """
    if not zones:
        return "⚠️ No confluence zones detected."

    lines = ["📍 CONFLUENCE ZONES", ""]

    for zone in zones:
        zone_type = zone.get("type", "unknown")
        emoji = "🟢" if zone_type == "support" else "🔴"
        center = zone.get("center", 0)
        strength = zone.get("strength", 0)
        components = zone.get("components", [])
        stars = "⭐" * min(strength, 5)

        lines.append(f"{emoji} ${center:,.0f} | {zone_type.upper()} | {stars} ({strength})")
        if components:
            lines.append(f"   Sources: {', '.join(components[:5])}")

    return "\n".join(lines)


def format_alerts(alerts: list[dict[str, Any]]) -> str:
    """Format alert list for Telegram.

    See docs/sub-specs/SS-18.md §12.2

    Args:
        alerts: List of alert dicts.

    Returns:
        Formatted message string.
    """
    if not alerts:
        return "✅ No active alerts."

    lines = ["🚨 ALERTS", ""]
    for alert in alerts:
        lines.append(format_alert(alert))

    return "\n".join(lines)


def format_regime(regime_result: dict[str, Any]) -> str:
    """Format regime detection result for Telegram.

    See docs/sub-specs/SS-18.md §12.2

    Args:
        regime_result: Dict with regime, weights, raw_weights.

    Returns:
        Formatted message string.
    """
    if not regime_result:
        return "⚠️ No regime data available."

    regime = regime_result.get("regime", "UNKNOWN")
    weights = regime_result.get("weights", {})

    lines = [
        f"🔄 MARKET REGIME: {regime}",
        f"",
        f"📊 Weight Allocation:",
        f"  Spot Flow:    {weights.get('spot_flow', 0):.0%}",
        f"  Leverage:     {weights.get('leverage_pos', 0):.0%}",
        f"  Options:      {weights.get('options_struct', 0):.0%}",
        f"  Mean Rev:     {weights.get('mean_reversion', 0):.0%}",
    ]

    return "\n".join(lines)


def format_risk(event_risk: float, components: dict[str, float] | None = None) -> str:
    """Format event risk breakdown for Telegram.

    See docs/sub-specs/SS-18.md §12.2

    Args:
        event_risk: Overall event risk score.
        components: Optional dict of individual risk components.

    Returns:
        Formatted message string.
    """
    level = "🟢 LOW" if event_risk < 0.4 else "🟡 MEDIUM" if event_risk < 0.7 else "🔴 HIGH"
    if event_risk >= 0.8:
        level = "⛔ STAY OUT"

    lines = [
        f"⚠️ EVENT RISK: {event_risk:.2f} — {level}",
    ]

    if components:
        lines.append("")
        for name, value in components.items():
            lines.append(f"  {name}: {value:.2f}")

    return "\n".join(lines)


def format_health(health_report: dict[str, Any]) -> str:
    """Format health report for Telegram.

    See docs/sub-specs/SS-18.md §12.2

    Args:
        health_report: Health report dict from HealthMonitor.

    Returns:
        Formatted message string.
    """
    if not health_report:
        return "⚠️ No health data available."

    lines = ["🏥 SYSTEM HEALTH", ""]

    sources = health_report.get("sources", {})
    for name, status in sources.items():
        state = status.get("status", "unknown")
        emoji = "✅" if state == "healthy" else "⚠️" if state == "degraded" else "❌"
        latency = status.get("latency_ms", 0)
        lines.append(f"{emoji} {name}: {state} ({latency:.0f}ms)")

    overall = health_report.get("overall_status", "unknown")
    lines.append(f"\nOverall: {overall}")

    return "\n".join(lines)


def format_macro(events: list[dict[str, Any]]) -> str:
    """Format upcoming macro events for Telegram.

    See docs/sub-specs/SS-18.md §12.2

    Args:
        events: List of macro event dicts.

    Returns:
        Formatted message string.
    """
    if not events:
        return "📅 No upcoming macro events in next 7 days."

    lines = ["📅 UPCOMING MACRO EVENTS", ""]

    tier_emoji = {1: "🔴", 2: "🟡", 3: "🟢"}
    for event in events:
        tier = event.get("tier", 3)
        emoji = tier_emoji.get(tier, "🟢")
        date = event.get("date", "")
        time_utc = event.get("time_utc", "")
        name = event.get("event", "Unknown")
        lines.append(f"{emoji} T{tier} | {date} {time_utc} UTC | {name}")

    return "\n".join(lines)


def format_help() -> str:
    """Format help message listing all commands.

    See docs/sub-specs/SS-18.md §12.2

    Returns:
        Help text string.
    """
    return (
        "📖 COMMANDS\n"
        "\n"
        "/signal — Quick signal summary\n"
        "/breakdown — Detailed signal breakdown\n"
        "/levels — Confluence zones\n"
        "/entry long|short — Trade plan\n"
        "/risk — Event risk check\n"
        "/regime — Market regime + weights\n"
        "/health — System health\n"
        "/macro — Upcoming macro events\n"
        "/performance — Trading performance\n"
        "/ai — AI market analysis\n"
    )


# ── Command Dispatch ─────────────────────────────────────────


def handle_command(
    command: str, args: str, db_path: str, config: dict,
    portfolio_usd: float = 10000,
) -> str:
    """Dispatch a Telegram command and return the response message.

    See docs/sub-specs/SS-18.md §12.2

    Args:
        command: Command name (e.g. "signal", "levels").
        args: Command arguments string.
        db_path: Path to SQLite database.
        config: Full settings dict.
        portfolio_usd: Portfolio value for position sizing.

    Returns:
        Response message string.
    """
    try:
        if command == "signal" or command == "breakdown":
            return _handle_signal(db_path, config)
        elif command == "levels":
            return _handle_levels(db_path, config)
        elif command == "entry":
            return _handle_entry(args, db_path, config, portfolio_usd)
        elif command == "risk":
            return _handle_risk(db_path, config)
        elif command == "regime":
            return _handle_regime(db_path, config)
        elif command == "health":
            return _handle_health(db_path)
        elif command == "macro":
            return _handle_macro(db_path)
        elif command == "performance":
            return "📊 Performance tracking available in a future update."
        elif command == "ai":
            return "🤖 AI analysis available in a future update."
        else:
            return format_help()
    except Exception as e:
        logger.error("Command '%s' failed: %s", command, e)
        return f"⚠️ Command failed: {e}"


# ── Private command handlers ─────────────────────────────────


def _handle_signal(db_path: str, config: dict) -> str:
    """Handle /signal command."""
    rows = get_latest(db_path, "signals", n=1, order_col="timestamp")
    if not rows:
        return "⚠️ No signal data. Run signal computation first."

    row = rows[0]
    signal = {
        "final_score": row.get("final_score", 0),
        "bias": row.get("bias", "NEUTRAL"),
        "strength": row.get("strength", "NEUTRAL"),
        "confidence": row.get("confidence", "LOW"),
        "regime": row.get("regime", "UNKNOWN"),
        "event_risk": row.get("event_risk", 0),
        "consensus": row.get("consensus", "MIXED"),
        "btc_price": row.get("btc_price_at_signal", 0),
        "breakdown": {
            "spot_flow": row.get("spot_flow", 0),
            "leverage_pos": row.get("leverage_pos", 0),
            "options_struct": row.get("options_struct", 0),
            "mean_reversion": row.get("mean_reversion", 0),
        },
    }
    return format_signal_report(signal)


def _handle_levels(db_path: str, config: dict) -> str:
    """Handle /levels command."""
    price_rows = get_latest(db_path, "spot_price", n=1, order_col="timestamp")
    spot = price_rows[0]["close"] if price_rows else 0
    if spot <= 0:
        return "⚠️ No price data available."

    zones = compute_confluence_zones(db_path, config, spot)
    return format_levels(zones)


def _handle_entry(args: str, db_path: str, config: dict, portfolio_usd: float) -> str:
    """Handle /entry long|short command."""
    direction = args.strip().upper() if args else "LONG"
    if direction not in ("LONG", "SHORT"):
        return "Usage: /entry long or /entry short"

    rows = get_latest(db_path, "signals", n=1, order_col="timestamp")
    if not rows:
        return "⚠️ No signal data available."

    row = rows[0]
    signal = {
        "final_score": row.get("final_score", 0),
        "bias": direction,
        "strength": row.get("strength", "NEUTRAL"),
        "confidence": row.get("confidence", "LOW"),
    }

    price_rows = get_latest(db_path, "spot_price", n=1, order_col="timestamp")
    spot = price_rows[0]["close"] if price_rows else 0
    if spot <= 0:
        return "⚠️ No price data available."

    zones = compute_confluence_zones(db_path, config, spot)
    plan = generate_trade_plan(signal, zones, spot, portfolio_usd, config)
    return format_trade_plan(plan)


def _handle_risk(db_path: str, config: dict) -> str:
    """Handle /risk command."""
    price_rows = get_latest(db_path, "spot_price", n=1, order_col="timestamp")
    spot = price_rows[0]["close"] if price_rows else 0

    risk = compute_event_risk(db_path, config, spot=spot)
    return format_risk(risk)


def _handle_regime(db_path: str, config: dict) -> str:
    """Handle /regime command."""
    result = compute_regime(db_path, config)
    return format_regime(result)


def _handle_health(db_path: str) -> str:
    """Handle /health command."""
    # Check DB tables for staleness
    table_cols = {
        "spot_price": "timestamp",
        "futures_snapshot": "timestamp",
        "options_oi": "date",
        "daily_snapshot": "date",
    }
    sources: dict[str, Any] = {}

    for table, col in table_cols.items():
        rows = get_latest(db_path, table, n=1, order_col=col)
        if rows:
            sources[table] = {"status": "healthy", "latency_ms": 0}
        else:
            sources[table] = {"status": "no_data", "latency_ms": 0}

    overall = "healthy" if all(s["status"] == "healthy" for s in sources.values()) else "degraded"
    return format_health({"sources": sources, "overall_status": overall})


def _handle_macro(db_path: str) -> str:
    """Handle /macro command."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=7)

    rows = query(
        db_path,
        "SELECT * FROM macro_events WHERE date >= ? AND date <= ? ORDER BY date, time_utc",
        (now.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
    )
    events = [dict(r) for r in rows] if rows else []
    return format_macro(events)


# ── Helpers ──────────────────────────────────────────────────


def _strength_bar(abs_score: float) -> str:
    """Generate a visual strength bar."""
    filled = int(abs_score * 10)
    return "█" * filled + "░" * (10 - filled)
