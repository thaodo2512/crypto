"""Telegram bot command handlers and message formatters.

See docs/sub-specs/SS-18.md §12
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

# Display timezone for all user-facing messages
_DISPLAY_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _fmt_ts(ts_str: str) -> str:
    """Format a UTC timestamp string to display timezone (UTC+7)."""
    try:
        if "T" in ts_str:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(ts_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        local = dt.astimezone(_DISPLAY_TZ)
        return local.strftime("%b %d %H:%M")
    except (ValueError, TypeError):
        return ts_str[:16]


def _now_local() -> datetime:
    """Get current time in display timezone."""
    return datetime.now(_DISPLAY_TZ)

from custom.calculators.confluence import compute_confluence_zones
from custom.output.alerts import check_alerts, format_alert
from custom.regime.regime import compute_regime
from custom.signals.engine import assemble_signal, compute_final_signal
from custom.signals.event_risk import compute_event_risk
from custom.trade_plan.plan import generate_trade_plan
from custom.utils.db import get_latest, get_subscribers, query, remove_subscriber, upsert_subscriber
from custom.utils.health import HealthMonitor

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

    ts = signal.get("timestamp", "")
    time_str = _fmt_ts(ts) if ts else _now_local().strftime("%b %d %H:%M")

    lines = [
        f"📊 SIGNAL REPORT — {time_str}",
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


def format_trade_event(event: dict[str, Any]) -> str:
    """Format a trade lifecycle event for Telegram.

    Args:
        event: Event dict from lifecycle module.

    Returns:
        Formatted message string.
    """
    etype = event.get("type", "")

    if etype == "trade_opened":
        d = event.get("direction", "LONG")
        emoji = "🟢" if d == "LONG" else "🔴"
        return (
            f"{emoji} TRADE OPENED — {d}\n"
            f"Entry: ${event.get('entry_price', 0):,.0f}\n"
            f"SL:    ${event.get('stop_loss', 0):,.0f}\n"
            f"TP1:   ${event.get('tp1', 0):,.0f}\n"
            f"TP2:   ${event.get('tp2', 0):,.0f}\n"
            f"Risk:  {event.get('risk_pct', 0):.1f}%"
        )

    if etype == "reversal_and_open":
        closed = format_trade_event(event["closed"])
        opened = format_trade_event(event["opened"])
        return f"🔄 SIGNAL REVERSAL\n\n{closed}\n\n{opened}"

    if etype == "tp1_hit":
        return (
            f"🎯 TP1 HIT — partial exit\n"
            f"Direction: {event.get('direction')}\n"
            f"Entry:  ${event.get('entry_price', 0):,.0f}\n"
            f"TP1:    ${event.get('tp1_price', 0):,.0f}\n"
            f"Trade still open for TP2/TP3"
        )

    # Close events: sl_hit, tp2_hit, tp3_hit, time_stop, signal_reversal
    labels = {
        "sl_hit": "🛑 STOP LOSS HIT",
        "tp2_hit": "🎯 TP2 HIT",
        "tp3_hit": "🏆 TP3 HIT",
        "time_stop": "⏰ TIME STOP (48h)",
        "signal_reversal": "🔄 SIGNAL REVERSAL — closed",
    }
    label = labels.get(etype, f"TRADE CLOSED ({etype})")
    pnl = event.get("pnl_pct", 0)
    r = event.get("r_multiple", 0)
    pnl_emoji = "✅" if pnl >= 0 else "❌"

    return (
        f"{label}\n"
        f"Direction: {event.get('direction')}\n"
        f"Entry:  ${event.get('entry_price', 0):,.0f}\n"
        f"Exit:   ${event.get('exit_price', 0):,.0f}\n"
        f"{pnl_emoji} PnL: {'+' if pnl >= 0 else ''}{pnl:.2f}% "
        f"(${event.get('pnl_usd', 0):+,.0f})\n"
        f"R-multiple: {'+' if r >= 0 else ''}{r:.1f}R"
    )


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


def format_risk(
    event_risk: float,
    components: dict[str, float] | None = None,
    upcoming_events: list[dict[str, Any]] | None = None,
) -> str:
    """Format event risk breakdown for Telegram.

    See docs/sub-specs/SS-18.md §12.2

    Args:
        event_risk: Overall event risk score.
        components: Optional dict of individual risk components.
        upcoming_events: Optional list of upcoming macro events.

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

    if upcoming_events:
        tier_emoji = {1: "🔴", 2: "🟡", 3: "🟢"}
        lines.append("")
        lines.append("📅 Upcoming events:")
        for evt in upcoming_events[:5]:
            tier = evt.get("tier", 3)
            emoji = tier_emoji.get(tier, "🟢")
            hours = evt.get("hours_until", 0)
            name = evt.get("event", "Unknown")
            source = evt.get("source", "")
            source_tag = f" [{source}]" if source and source != "static" else ""
            if hours < 1:
                time_str = f"{hours * 60:.0f}min"
            elif hours < 24:
                time_str = f"{hours:.1f}h"
            else:
                days = hours / 24
                time_str = f"{days:.1f}d"
            lines.append(f"  {emoji} T{tier} {name} — in {time_str}{source_tag}")

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
        "/trade — Current open trade + PnL\n"
        "/risk — Event risk check\n"
        "/regime — Market regime + weights\n"
        "/macro — Upcoming macro events\n"
        "/ai [question] — AI market analysis (10/day)\n"
        "\n"
        "🔧 SYSTEM\n"
        "/status — Full system status + data freshness\n"
        "/health — Data source health\n"
        "/debug — Debug info (uptime, jobs, DB)\n"
        "\n"
        "👤 ADMIN\n"
        "/adduser <chat_id> — Add subscriber\n"
        "/removeuser <chat_id> — Remove subscriber\n"
        "/subscribers — List active subscribers\n"
    )


# ── Command Dispatch ─────────────────────────────────────────


def handle_command(
    command: str, args: str, db_path: str, config: dict,
    portfolio_usd: float = 10000,
    health_monitor: HealthMonitor | None = None,
    scheduler: Any = None,
) -> str:
    """Dispatch a Telegram command and return the response message.

    See docs/sub-specs/SS-18.md §12.2

    Args:
        command: Command name (e.g. "signal", "levels").
        args: Command arguments string.
        db_path: Path to SQLite database.
        config: Full settings dict.
        portfolio_usd: Portfolio value for position sizing.
        health_monitor: Optional HealthMonitor for /health and /debug.
        scheduler: Optional SignalBotScheduler for /debug job stats.

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
            return _handle_health(db_path, health_monitor)
        elif command == "macro":
            return _handle_macro(db_path)
        elif command == "debug":
            return _handle_debug(db_path, scheduler)
        elif command == "status":
            return _handle_status(db_path, health_monitor, scheduler)
        elif command == "trade":
            return _handle_trade(db_path)
        elif command == "performance":
            return "📊 Performance tracking available in a future update."
        elif command == "ai":
            return "🤖 AI analysis available in a future update."
        elif command == "adduser":
            return _handle_adduser(args, db_path)
        elif command == "removeuser":
            return _handle_removeuser(args, db_path, config)
        elif command == "subscribers":
            return _handle_subscribers(db_path)
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

    upcoming = []
    try:
        from custom.collectors.sentiment import SentimentCollector
        sentiment = SentimentCollector(config, db_path)
        upcoming = sentiment.get_upcoming_events(hours_ahead=168)  # 7 days
    except Exception:
        pass

    return format_risk(risk, upcoming_events=upcoming)


def _handle_regime(db_path: str, config: dict) -> str:
    """Handle /regime command."""
    result = compute_regime(db_path, config)
    return format_regime(result)


def _handle_health(db_path: str, health_monitor: HealthMonitor | None = None) -> str:
    """Handle /health command — show per-source status from HealthMonitor."""
    if health_monitor is None:
        return "⚠️ HealthMonitor not available."

    report = health_monitor.get_health_report()
    sources = report.get("sources", {})

    if not sources:
        return "⚠️ No data sources tracked yet. Waiting for first collection cycle."

    lines = ["🏥 SYSTEM HEALTH", ""]

    for name, status in sources.items():
        is_degraded = status.get("is_degraded", False)
        is_stale = status.get("is_stale", False)
        failures = status.get("consecutive_failures", 0)
        latency = status.get("latency_seconds")
        last_success = status.get("last_success")
        last_error = status.get("last_error")

        if is_degraded:
            emoji = "❌"
            state = "DEGRADED"
        elif is_stale:
            emoji = "⚠️"
            state = "STALE"
        elif last_success:
            emoji = "✅"
            state = "OK"
        else:
            emoji = "⏳"
            state = "PENDING"

        latency_str = f"{latency * 1000:.0f}ms" if latency else "—"
        lines.append(f"{emoji} {name}: {state} | {latency_str}")

        if last_success:
            lines.append(f"   Last OK: {_fmt_ts(str(last_success))}")
        if failures > 0:
            lines.append(f"   Failures: {failures}")
        if last_error:
            lines.append(f"   Error: {last_error[:80]}")

    overall = "HEALTHY" if report.get("overall_healthy") else "DEGRADED"
    lines.append(f"\nOverall: {overall}")
    return "\n".join(lines)


def _handle_debug(db_path: str, scheduler: Any = None) -> str:
    """Handle /debug command — show uptime, job stats, DB size, memory."""
    import resource

    from main import BOT_START_TIME

    lines = ["🔧 DEBUG INFO", ""]

    # Uptime
    uptime_sec = time.time() - BOT_START_TIME
    hours, remainder = divmod(int(uptime_sec), 3600)
    minutes, secs = divmod(remainder, 60)
    lines.append(f"⏱ Uptime: {hours}h {minutes}m {secs}s")

    # DB size
    try:
        db_size = os.path.getsize(db_path)
        if db_size < 1024 * 1024:
            size_str = f"{db_size / 1024:.1f} KB"
        else:
            size_str = f"{db_size / (1024 * 1024):.1f} MB"
        lines.append(f"💾 DB size: {size_str}")
    except OSError:
        lines.append("💾 DB size: unknown")

    # Memory usage
    mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    lines.append(f"🧠 Memory (peak RSS): {mem_mb:.1f} MB")

    # Job stats
    if scheduler is not None:
        stats = scheduler.get_job_stats()
        if stats:
            lines.append("")
            lines.append("📋 JOB STATS:")
            for name, s in stats.items():
                execs = s.get("executions", 0)
                fails = s.get("failures", 0)
                last_run = s.get("last_run", "never")
                last_err = s.get("last_error")
                status = "✅" if fails == 0 else "⚠️"
                lines.append(f"  {status} {name}: {execs} runs, {fails} fails")
                lines.append(f"     Last: {last_run}")
                if last_err:
                    lines.append(f"     Error: {last_err[:60]}")
        else:
            lines.append("\n📋 No jobs tracked yet.")
    else:
        lines.append("\n📋 Scheduler not available.")

    return "\n".join(lines)


def _handle_status(
    db_path: str, health_monitor: HealthMonitor | None = None, scheduler: Any = None,
) -> str:
    """Handle /status — comprehensive system status with data freshness."""
    import resource

    from main import BOT_START_TIME

    lines = ["📡 SYSTEM STATUS", ""]

    # Uptime
    uptime_sec = time.time() - BOT_START_TIME
    hours, remainder = divmod(int(uptime_sec), 3600)
    minutes, _ = divmod(remainder, 60)
    lines.append(f"⏱ Uptime: {hours}h {minutes}m")

    # Memory + DB
    mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    try:
        db_size = os.path.getsize(db_path) / (1024 * 1024)
        lines.append(f"💾 DB: {db_size:.1f}MB | RAM: {mem_mb:.0f}MB")
    except OSError:
        lines.append(f"🧠 RAM: {mem_mb:.0f}MB")

    # Data provider freshness
    lines.append("")
    lines.append("━━━ DATA PROVIDERS ━━━")

    # For date-only tables, use health monitor last_success for accurate freshness
    # hm_key maps table to its health monitor source name
    tables = [
        ("spot_price", "timestamp", "Binance Spot", None),
        ("spot_cvd", "timestamp", "CVD (Binance)", None),
        ("spot_orderbook", "timestamp", "Orderbook", None),
        ("futures_snapshot", "timestamp", "Futures (3 CEX)", None),
        ("futures_oi_price", "timestamp", "OI Price Regime", None),
        ("futures_liquidations", "timestamp", "Liquidations", None),
        ("options_oi", "date", "Deribit Options", "options"),
        ("gex_data", "date", "GEX / Gamma", "options"),
        ("daily_snapshot", "date", "Daily Snapshot", "daily_report"),
        ("spot_technicals", "date", "Technicals", "daily_report"),
        ("macro_events", "date", "Macro Calendar", None),
    ]

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    hm_sources = {}
    if health_monitor:
        hm_report = health_monitor.get_health_report()
        hm_sources = hm_report.get("sources", {})

    for table, ts_col, label, hm_key in tables:
        try:
            cnt_row = query(db_path, f"SELECT COUNT(*) as cnt FROM {table}")
            cnt = cnt_row[0]["cnt"] if cnt_row else 0
            age_min = 99999

            # For date-based tables, use health monitor last_success (actual collection time)
            if ts_col == "date" and hm_key and hm_key in hm_sources:
                ls = hm_sources[hm_key].get("last_success")
                if ls:
                    try:
                        dt = datetime.fromisoformat(str(ls))
                        age_min = int((now - dt).total_seconds() / 60)
                    except (ValueError, TypeError):
                        pass
            elif table == "macro_events":
                ts_row = query(db_path, f"SELECT MAX({ts_col}) as v FROM {table} WHERE {ts_col} <= date('now')")
                v = ts_row[0]["v"] if ts_row else None
                if v:
                    try:
                        dt = datetime.strptime(str(v), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        age_min = int((now - dt).total_seconds() / 60)
                    except (ValueError, TypeError):
                        pass
            else:
                ts_row = query(db_path, f"SELECT MAX({ts_col}) as v FROM {table}")
                v = ts_row[0]["v"] if ts_row else None
                if v:
                    try:
                        if "T" in str(v):
                            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                        else:
                            dt = datetime.strptime(str(v), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        age_min = int((now - dt).total_seconds() / 60)
                    except (ValueError, TypeError):
                        pass

            if age_min == 99999:
                age_str = "no data"
                emoji = "❌"
            elif age_min < 60:
                age_str = f"{age_min}m ago"
                emoji = "✅"
            elif age_min < 1440:
                age_str = f"{age_min // 60}h ago"
                emoji = "✅" if age_min < 300 else "⚠️"
            else:
                age_str = f"{age_min // 1440}d ago"
                emoji = "❌"

            lines.append(f"{emoji} {label}: {age_str} ({cnt} rows)")
        except Exception:
            lines.append(f"❌ {label}: error")

    # Health monitor status
    if health_monitor:
        report = health_monitor.get_health_report()
        degraded = [s for s, st in report.get("sources", {}).items() if st.get("is_degraded")]
        stale = [s for s, st in report.get("sources", {}).items() if st.get("is_stale")]
        if degraded:
            lines.append(f"\n🔴 Degraded: {', '.join(degraded)}")
        if stale:
            lines.append(f"🟡 Stale: {', '.join(stale)}")
        if not degraded and not stale:
            lines.append("\n✅ All sources healthy")

    # Current signal + event risk
    lines.append("")
    lines.append("━━━ SIGNAL STATUS ━━━")
    sig_rows = get_latest(db_path, "signals", n=1, order_col="timestamp")
    if sig_rows:
        s = sig_rows[0]
        lines.append(f"Signal: {s.get('bias')} {s.get('strength')} ({s.get('final_score', 0):+.3f})")
        lines.append(f"Risk: {s.get('event_risk', 0):.2f} | Regime: {s.get('regime')}")
        lines.append(f"Time: {_fmt_ts(s.get('timestamp', ''))}")
    else:
        lines.append("No signals yet")

    # Open trade
    from custom.trade_plan.lifecycle import get_open_trade
    trade = get_open_trade(db_path)
    if trade:
        lines.append(f"\n📈 Open: {trade['direction']} @ ${trade['entry_price']:,.0f}")
        lines.append(f"   SL: ${trade['stop_loss']:,.0f} | TP1: ${trade['tp1']:,.0f}")
    else:
        lines.append("\n📈 No open trade")

    # Scheduler jobs summary
    if scheduler:
        stats = scheduler.get_job_stats()
        total_runs = sum(s.get("executions", 0) for s in stats.values())
        total_fails = sum(s.get("failures", 0) for s in stats.values())
        lines.append(f"\n⚙️ Jobs: {total_runs} runs, {total_fails} failures")

    return "\n".join(lines)


def _handle_trade(db_path: str) -> str:
    """Handle /trade — show current open trade status."""
    from custom.trade_plan.lifecycle import get_open_trade

    trade = get_open_trade(db_path)
    if not trade:
        # Show last closed trade
        rows = query(
            db_path,
            "SELECT * FROM trades WHERE exit_timestamp IS NOT NULL ORDER BY exit_timestamp DESC LIMIT 1",
        )
        if rows:
            t = rows[0]
            pnl = t.get("pnl_pct", 0) or 0
            emoji = "✅" if pnl >= 0 else "❌"
            return (
                f"📈 No open trade\n\n"
                f"Last closed:\n"
                f"{emoji} {t['direction']} @ ${t['entry_price']:,.0f} → ${t['exit_price']:,.0f}\n"
                f"PnL: {'+' if pnl >= 0 else ''}{pnl:.2f}% | R: {'+' if (t.get('r_multiple') or 0) >= 0 else ''}{(t.get('r_multiple') or 0):.1f}\n"
                f"Reason: {t.get('exit_reason', 'unknown')}\n"
                f"Closed: {_fmt_ts(t['exit_timestamp'])}"
            )
        return "📈 No open trade and no trade history."

    # Get current price for unrealized PnL
    price_rows = get_latest(db_path, "spot_price", n=1, order_col="timestamp")
    current = price_rows[0]["close"] if price_rows else 0

    entry = trade["entry_price"]
    direction = trade["direction"]

    if current > 0 and entry > 0:
        if direction == "LONG":
            unreal_pct = (current - entry) / entry * 100
        else:
            unreal_pct = (entry - current) / entry * 100
        unreal_emoji = "🟢" if unreal_pct >= 0 else "🔴"
        unreal_str = f"{unreal_emoji} Unrealized: {'+' if unreal_pct >= 0 else ''}{unreal_pct:.2f}%"
    else:
        unreal_str = ""

    # Time elapsed
    from datetime import datetime, timezone
    try:
        entry_dt = datetime.fromisoformat(trade["entry_timestamp"].replace("Z", "+00:00"))
        elapsed = datetime.now(timezone.utc) - entry_dt
        hours = int(elapsed.total_seconds() / 3600)
        mins = int((elapsed.total_seconds() % 3600) / 60)
        elapsed_str = f"{hours}h {mins}m"
    except (ValueError, TypeError):
        elapsed_str = "unknown"

    lines = [
        f"📈 OPEN TRADE — {direction}",
        "",
        f"Entry:   ${entry:,.0f}",
        f"Current: ${current:,.0f}" if current > 0 else "",
        f"SL:      ${trade['stop_loss']:,.0f}",
        f"TP1:     ${trade['tp1']:,.0f}" + (" ✅" if trade.get("tp1_hit") else ""),
        f"TP2:     ${trade['tp2']:,.0f}",
        f"TP3:     trailing",
        "",
        unreal_str,
        f"⏱ Elapsed: {elapsed_str} / 48h",
        f"Risk:    {trade.get('risk_pct', 0):.1f}%",
        f"Size:    ${trade.get('position_size_usd', 0):,.0f}",
    ]
    return "\n".join(line for line in lines if line is not None)


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


def _handle_adduser(args: str, db_path: str) -> str:
    """Handle /adduser <chat_id> command (admin only).

    See docs/sub-specs/SS-18.md §12
    """
    chat_id = args.strip()
    if not chat_id or not chat_id.lstrip("-").isdigit():
        return "Usage: /adduser <chat_id> (numeric Telegram chat ID)"

    added = upsert_subscriber(db_path, chat_id, added_by="admin")
    if added:
        return f"Subscriber {chat_id} added."
    return f"Subscriber {chat_id} is already active."


def _handle_removeuser(args: str, db_path: str, config: dict) -> str:
    """Handle /removeuser <chat_id> command (admin only).

    See docs/sub-specs/SS-18.md §12
    """
    chat_id = args.strip()
    if not chat_id or not chat_id.lstrip("-").isdigit():
        return "Usage: /removeuser <chat_id> (numeric Telegram chat ID)"

    admin_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if chat_id == admin_id:
        return "Cannot remove the admin subscriber."

    removed = remove_subscriber(db_path, chat_id)
    if removed:
        return f"Subscriber {chat_id} removed."
    return f"Subscriber {chat_id} not found or already inactive."


def _handle_subscribers(db_path: str) -> str:
    """Handle /subscribers command (admin only).

    See docs/sub-specs/SS-18.md §12
    """
    subs = get_subscribers(db_path)
    if not subs:
        return "No active subscribers."

    lines = ["👥 ACTIVE SUBSCRIBERS", ""]
    for cid in subs:
        lines.append(f"  • {cid}")
    lines.append(f"\nTotal: {len(subs)}")
    return "\n".join(lines)


# ── Helpers ──────────────────────────────────────────────────


def _strength_bar(abs_score: float) -> str:
    """Generate a visual strength bar."""
    filled = int(abs_score * 10)
    return "█" * filled + "░" * (10 - filled)
