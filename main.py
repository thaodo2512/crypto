"""Crypto Signal Bot — Entry point.

See docs/sub-specs/SS-01.md
"""

import argparse
import asyncio
import logging
import os
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml
from dotenv import load_dotenv

from custom.utils.db import init_db

load_dotenv()

# ── Logging setup ────────────────────────────────────────────
_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(exist_ok=True)

# Console handler — INFO level
_console = logging.StreamHandler()
_console.setLevel(logging.INFO)
_console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

# File handler — DEBUG level, 5 MB rotation, 3 backups
_file = RotatingFileHandler(
    _LOG_DIR / "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3,
)
_file.setLevel(logging.DEBUG)
_file.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
))

logging.basicConfig(level=logging.DEBUG, handlers=[_console, _file])
logger = logging.getLogger(__name__)

# Bot start time for uptime tracking
BOT_START_TIME: float = time.time()


def load_config(path: str = "config/settings.yaml") -> dict:
    """Load configuration from YAML file.

    See docs/sub-specs/SS-01.md §Config

    Raises:
        FileNotFoundError: If config file does not exist.
    """
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _run_async(coro_func: object) -> object:
    """Wrap an async function so APScheduler can call it synchronously.

    See docs/sub-specs/SS-21.md §9

    Args:
        coro_func: Async callable to wrap.

    Returns:
        Synchronous wrapper function.
    """
    def wrapper() -> None:
        asyncio.run(coro_func())
    wrapper.__name__ = getattr(coro_func, "__name__", "async_job")
    return wrapper


def _tracked_async(
    coro_func: object,
    source_name: str,
    health_monitor: object,
) -> object:
    """Wrap an async collector call to track success/failure/latency in HealthMonitor.

    Args:
        coro_func: Async callable to wrap.
        source_name: Data source name for health tracking.
        health_monitor: HealthMonitor instance.

    Returns:
        Synchronous wrapper suitable for APScheduler.
    """
    def wrapper() -> None:
        from custom.collectors.spot import CollectorError

        t0 = time.time()
        try:
            asyncio.run(coro_func())
            health_monitor.record_success(source_name, time.time() - t0)
        except CollectorError as e:
            health_monitor.record_failure(source_name, str(e))
            logger.warning("Job %s failed (expected): %s", source_name, e)
        except Exception as e:
            health_monitor.record_failure(source_name, str(e))
            raise
    wrapper.__name__ = getattr(coro_func, "__name__", source_name)
    return wrapper


def _make_signal_job(
    db_path: str, config: dict, bot: object,
    has_options: bool = True, asset_name: str = "BTC",
) -> object:
    """Create a signal computation + broadcast job for the scheduler.

    See docs/sub-specs/SS-18.md §12

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        bot: TelegramBot instance with broadcast_sync().
        has_options: Whether this asset has options data.
        asset_name: Asset name for message prefix.

    Returns:
        Callable job function.
    """
    def job() -> None:
        from datetime import datetime, timedelta, timezone

        from custom.calculators.confluence import compute_confluence_zones
        from custom.output.telegram_commands import format_signal_report, format_trade_event, format_trade_plan
        from custom.signals.engine import compute_final_signal
        from custom.trade_plan.plan import generate_trade_plan
        from custom.utils.db import get_latest, query

        # Skip if a signal was computed recently (within 75% of interval)
        tg_cfg = config.get("telegram", {})
        interval_h = tg_cfg.get("signal_report_interval_hours", 4)
        min_gap_minutes = int(interval_h * 60 * 0.75)
        recent = query(
            db_path,
            "SELECT timestamp FROM signals ORDER BY timestamp DESC LIMIT 1",
        )
        if recent:
            last_ts = recent[0]["timestamp"]
            try:
                last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - last_dt
                if age < timedelta(minutes=min_gap_minutes):
                    logger.info(
                        "%s signal skipped: last signal %d min ago (min gap %d min)",
                        asset_name, int(age.total_seconds() / 60), min_gap_minutes,
                    )
                    return
            except (ValueError, TypeError):
                pass  # Can't parse timestamp, proceed with computation

        result = compute_final_signal(db_path, config, has_options=has_options)
        report = format_signal_report(result, asset_name=asset_name)

        # Append trade plan if signal passes entry gates
        price_rows = get_latest(db_path, "spot_price", n=1, order_col="timestamp")
        spot = price_rows[0]["close"] if price_rows else 0
        if spot > 0:
            from custom.trade_plan.lifecycle import close_trade, get_open_trade, open_trade
            from custom.utils.asset_config import get_asset_config

            ac = get_asset_config(config, asset_name)
            zones = compute_confluence_zones(db_path, config, spot, round_number_step=ac.round_number_step)
            portfolio = config.get("trade_plan", {}).get("portfolio_usd", 10000)
            plan = generate_trade_plan(result, zones, spot, portfolio, config)
            trade_msg = format_trade_plan(plan)
            report = report + "\n\n" + trade_msg

            # Trade lifecycle: open new trade or close opposing
            if plan:
                trade_event = open_trade(db_path, plan, result)
                if trade_event:
                    report += "\n\n" + format_trade_event(trade_event)
            else:
                # No plan but check if current signal opposes open trade
                open_t = get_open_trade(db_path)
                if open_t:
                    existing_dir = open_t["direction"]
                    new_bias = result.get("bias", "NEUTRAL")
                    if (existing_dir == "LONG" and new_bias == "SHORT") or \
                       (existing_dir == "SHORT" and new_bias == "LONG"):
                        event = close_trade(db_path, open_t["id"], spot, "signal_reversal")
                        report += "\n\n" + format_trade_event(event)

        bot.broadcast_sync(report)
    job.__name__ = f"signal_compute_broadcast_{asset_name.lower()}"
    return job


def _make_alert_job(
    db_path: str, config: dict, health_monitor: object, bot: object,
    ai_builder: object = None, ai_analyzer: object = None,
    asset_name: str = "BTC",
) -> object:
    """Create an alert check + broadcast job for the scheduler.

    See docs/sub-specs/SS-18.md §12

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        health_monitor: HealthMonitor instance.
        bot: TelegramBot instance with broadcast_sync().
        ai_builder: Optional AIPromptBuilder for AI narrative.
        ai_analyzer: Optional ClaudeAnalyzer for AI narrative.
        asset_name: Asset name for message prefix.

    Returns:
        Callable job function.
    """
    def job() -> None:
        from custom.output.alerts import check_alerts, check_system_health, format_alert
        from custom.output.telegram_commands import format_trade_event
        from custom.trade_plan.lifecycle import check_trade_levels
        from custom.utils.db import get_latest

        # Load 2 most recent signals for prev_signal tracking
        rows = get_latest(db_path, "signals", n=2, order_col="timestamp")
        signal = dict(rows[0]) if rows else {}
        prev_signal = dict(rows[1]) if len(rows) >= 2 else None

        # Get current price and gamma flip for alerts
        price_rows = get_latest(db_path, "spot_price", n=1, order_col="timestamp")
        current_price = price_rows[0]["close"] if price_rows else 0

        from custom.utils.db import query as db_query
        gf_rows = db_query(
            db_path,
            "SELECT gamma_flip_price FROM gex_data WHERE gamma_flip_price IS NOT NULL "
            "ORDER BY date DESC, id DESC LIMIT 1",
        )
        gamma_flip = gf_rows[0]["gamma_flip_price"] if gf_rows else None

        alerts = check_alerts(
            db_path, signal, config, prev_signal=prev_signal,
            spot=current_price, gamma_flip=gamma_flip,
        )
        alerts.extend(check_system_health(health_monitor, config))

        # Check open trade against SL/TP levels
        if current_price > 0:
            trade_events = check_trade_levels(db_path, current_price)
            for event in trade_events:
                priority = "CRITICAL" if event["type"] == "sl_hit" else "WARNING"
                alerts.append({
                    "priority": priority,
                    "trigger": f"trade_{event['type']}",
                    "message": format_trade_event(event),
                })

        if alerts:
            lines = [f"🚨 {asset_name} ALERTS", ""]
            for alert in alerts:
                lines.append(format_alert(alert))

            # Check if any signal crossing alert fired — append AI narrative
            has_crossing = any(a.get("trigger") == "signal_threshold_crossing" for a in alerts)
            if has_crossing and ai_builder and ai_analyzer and prev_signal:
                try:
                    old_score = prev_signal.get("final_score", 0.0)
                    new_score = signal.get("final_score", 0.0)
                    prompt = ai_builder.build_signal_change(old_score, new_score)
                    ai_text = asyncio.run(ai_analyzer.analyze(prompt))
                    lines.append("")
                    lines.append("━━━━━━━━━━━━━━━")
                    lines.append("🤖 AI ANALYSIS")
                    lines.append("")
                    lines.append(ai_text)
                except Exception as e:
                    logger.error("AI analysis for alert failed: %s", e)

            bot.broadcast_sync("\n".join(lines))
    job.__name__ = f"alert_check_broadcast_{asset_name.lower()}"
    return job


def _make_daily_report_job(
    db_path: str, config: dict, bot: object,
    ai_builder: object = None, ai_analyzer: object = None,
    asset_name: str = "BTC",
) -> object:
    """Create a daily report broadcast job for the scheduler.

    See docs/sub-specs/SS-18.md §12

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        bot: TelegramBot instance with broadcast_sync().
        ai_builder: Optional AIPromptBuilder for AI narrative.
        ai_analyzer: Optional ClaudeAnalyzer for AI narrative.
        asset_name: Asset name for message prefix.

    Returns:
        Callable job function.
    """
    def job() -> None:
        from custom.output.telegram_commands import (
            format_regime,
            format_risk,
            format_signal_report,
        )
        from custom.regime.regime import compute_regime
        from custom.signals.engine import compute_final_signal
        from custom.signals.event_risk import compute_event_risk
        from custom.utils.db import get_latest

        # Compute fresh signal
        result = compute_final_signal(db_path, config)

        # Get price for risk computation
        price_rows = get_latest(db_path, "spot_price", n=1, order_col="timestamp")
        spot = price_rows[0]["close"] if price_rows else 0.0

        # Build report sections
        signal_section = format_signal_report(result)
        regime_result = compute_regime(db_path, config)
        regime_section = format_regime(regime_result)
        event_risk = compute_event_risk(db_path, config, spot=spot)
        risk_section = format_risk(event_risk)

        report = (
            f"📋 {asset_name} DAILY REPORT\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{signal_section}\n\n"
            f"{regime_section}\n\n"
            f"{risk_section}"
        )

        # Append AI narrative if available
        if ai_builder and ai_analyzer:
            try:
                prompt = ai_builder.build_daily_briefing()
                ai_text = asyncio.run(ai_analyzer.analyze(prompt))
                report += (
                    "\n\n━━━━━━━━━━━━━━━\n"
                    "🤖 AI ANALYSIS\n\n"
                    f"{ai_text}"
                )
            except Exception as e:
                logger.error("AI analysis for daily report failed: %s", e)

        bot.broadcast_sync(report)
    job.__name__ = f"daily_report_broadcast_{asset_name.lower()}"
    return job


async def _fill_daily_snapshot(db_path: str, options: object) -> None:
    """Fill remaining daily_snapshot columns (btc_price, dvol, P/C ratio, regime, adx, bb_width).

    Called after fetch_technicals + fetch_fear_greed in the daily job.
    """
    from custom.utils.db import get_db, get_latest, query
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Get latest price
    price_rows = get_latest(db_path, "spot_price", n=1, order_col="timestamp")
    btc_price = price_rows[0]["close"] if price_rows else None

    # Get DVol from Deribit
    dvol = await options.fetch_dvol()

    # Get P/C ratios from latest options snapshot
    options_rows = get_latest(db_path, "options_oi", n=500, order_col="date")
    total_call_oi = sum(r.get("call_oi") or 0 for r in options_rows)
    total_put_oi = sum(r.get("put_oi") or 0 for r in options_rows)
    total_call_vol = sum(r.get("call_volume") or 0 for r in options_rows)
    total_put_vol = sum(r.get("put_volume") or 0 for r in options_rows)
    pc_ratio_oi = total_put_oi / total_call_oi if total_call_oi > 0 else None
    pc_ratio_vol = total_put_vol / total_call_vol if total_call_vol > 0 else None

    # Get regime, adx, bb_width from latest technicals
    tech_rows = get_latest(db_path, "spot_technicals", n=1, order_col="date")
    adx = tech_rows[0].get("adx_14") if tech_rows else None
    bb_width = tech_rows[0].get("bb_width") if tech_rows else None

    # Compute regime label from ADX
    if adx is not None:
        if adx > 40:
            regime = "STRONG_TREND"
        elif adx > 25:
            regime = "MODERATE_TREND"
        else:
            regime = "RANGE_BOUND"
    else:
        regime = None

    conn = get_db(db_path)
    try:
        # Ensure row exists before updating (fear_greed collector may not have run yet)
        conn.execute(
            "INSERT OR IGNORE INTO daily_snapshot (date) VALUES (?)",
            (today,),
        )
        conn.execute(
            """UPDATE daily_snapshot
               SET btc_price = ?, dvol = ?, put_call_ratio_oi = ?,
                   put_call_ratio_volume = ?, regime = ?, adx = ?,
                   bb_width_percentile = ?
               WHERE date = ?""",
            (btc_price, dvol, pc_ratio_oi, pc_ratio_vol, regime, adx, bb_width, today),
        )
        conn.commit()
        logger.info("Daily snapshot enriched: price=%s dvol=%s regime=%s", btc_price, dvol, regime)
    finally:
        conn.close()


def _register_asset_jobs(
    scheduler: object, config: dict, asset_db: str, asset_name: str,
    health_monitor: object, bot: object = None,
    ai_builder: object = None, ai_analyzer: object = None,
) -> None:
    """Register per-asset collector, signal, and broadcast jobs.

    Args:
        scheduler: SignalBotScheduler instance.
        config: Full settings dict.
        asset_db: Path to this asset's database.
        asset_name: Asset name (e.g. "BTC", "ETH").
        health_monitor: HealthMonitor instance.
        bot: Optional TelegramBot for proactive messaging.
        ai_builder: Optional AIPromptBuilder.
        ai_analyzer: Optional ClaudeAnalyzer.
    """
    from custom.collectors.futures import FuturesCollector
    from custom.collectors.options import OptionsCollector
    from custom.collectors.sentiment import SentimentCollector
    from custom.collectors.spot import SpotCollector
    from custom.utils.asset_config import get_asset_config

    ac = get_asset_config(config, asset_name)
    suffix = f"_{asset_name.lower()}"
    source_prefix = f"{asset_name.lower()}_"

    spot = SpotCollector(config, asset_db, symbol=ac.spot_symbol)
    futures = FuturesCollector(
        config, asset_db,
        symbol_binance=ac.futures_binance,
        symbol_bybit=ac.futures_bybit,
        symbol_okx=ac.futures_okx,
    )

    # Every 2 minutes — price
    scheduler.register_job(
        f"price{suffix}",
        _tracked_async(spot.fetch_price, f"{source_prefix}spot_price", health_monitor),
    )

    # Every 15 minutes — orderbook + futures
    scheduler.register_job(
        f"orderbook{suffix}",
        _tracked_async(spot.fetch_orderbook, f"{source_prefix}spot_orderbook", health_monitor),
    )
    scheduler.register_job(
        f"futures{suffix}",
        _tracked_async(futures.fetch_snapshot, f"{source_prefix}futures", health_monitor),
    )

    # Every hour — CVD + trades
    scheduler.register_job(
        f"hourly{suffix}",
        _tracked_async(spot.fetch_trades, f"{source_prefix}spot_trades", health_monitor),
    )

    # Every hour — OI-price regime
    scheduler.register_job(
        f"oi_price_regime{suffix}",
        _tracked_async(futures.fetch_oi_price_regime, f"{source_prefix}oi_price_regime", health_monitor),
    )

    # Every 4 hours — liquidations
    scheduler.register_job(
        f"liquidations{suffix}",
        _tracked_async(futures.fetch_liquidations, f"{source_prefix}liquidations", health_monitor),
    )

    # Options — only if asset has options on Deribit
    options = None
    if ac.has_options and ac.deribit_currency:
        options = OptionsCollector(config, asset_db, currency=ac.deribit_currency)
        scheduler.register_job(
            f"options{suffix}",
            _tracked_async(options.fetch_snapshot, f"{source_prefix}options", health_monitor),
        )

    # Every hour — fill outcome prices
    def outcome_job(_db=asset_db) -> None:
        from custom.evaluation.tracker import fill_outcomes
        fill_outcomes(_db)
    outcome_job.__name__ = f"outcome_tracker{suffix}"
    scheduler.register_job(f"outcome_tracker{suffix}", outcome_job)

    # Daily at 08:00 UTC — technicals + daily snapshot
    async def daily_job(
        _spot=spot, _db=asset_db, _options=options, _config=config,
    ) -> None:
        await _spot.fetch_technicals()
        sentiment = SentimentCollector(_config, _db)
        await sentiment.fetch_fear_greed()
        if _options:
            await _fill_daily_snapshot(_db, _options)
    scheduler.register_job(
        f"daily_report{suffix}",
        _tracked_async(daily_job, f"{source_prefix}daily_report", health_monitor),
    )

    # Proactive messaging (per-asset signal + alert + daily broadcast)
    if bot is not None:
        scheduler.register_job(
            f"signal_compute{suffix}",
            _make_signal_job(asset_db, config, bot, has_options=ac.has_options, asset_name=asset_name),
        )
        scheduler.register_job(
            f"alert_check{suffix}",
            _make_alert_job(asset_db, config, health_monitor, bot, ai_builder, ai_analyzer, asset_name=asset_name),
        )
        scheduler.register_job(
            f"daily_broadcast{suffix}",
            _make_daily_report_job(asset_db, config, bot, ai_builder, ai_analyzer, asset_name=asset_name),
        )


def start_scheduler(
    config: dict, db_path: str, bot: object = None,
    ai_builder: object = None, ai_analyzer: object = None,
) -> tuple:
    """Create, register jobs, and start the scheduler.

    See docs/sub-specs/SS-21.md §9

    Args:
        config: Full settings dict.
        db_path: Path to SQLite database (primary / BTC fallback).
        bot: Optional TelegramBot for proactive messaging jobs.
        ai_builder: Optional AIPromptBuilder for AI narrative in reports.
        ai_analyzer: Optional ClaudeAnalyzer for AI narrative in reports.

    Returns:
        Tuple of (SignalBotScheduler, HealthMonitor).
    """
    from custom.ai.classifier import HeadlineClassifier
    from custom.collectors.macro_calendar import ForexFactoryCalendarCollector
    from custom.collectors.news_rss import NewsRSSCollector
    from custom.scheduler import SignalBotScheduler
    from custom.utils.asset_config import get_enabled_assets
    from custom.utils.health import HealthMonitor

    scheduler = SignalBotScheduler(config)
    health_monitor = HealthMonitor(config)

    # Register per-asset jobs for all enabled assets
    enabled = get_enabled_assets(config)
    for ac in enabled:
        _register_asset_jobs(
            scheduler, config, ac.db_path, ac.name,
            health_monitor, bot, ai_builder, ai_analyzer,
        )
        logger.info("Registered jobs for %s (db=%s)", ac.name, ac.db_path)

    # Shared jobs (run once, use primary DB for storage)
    primary_db = enabled[0].db_path if enabled else db_path
    classifier = HeadlineClassifier(os.getenv("ANTHROPIC_API_KEY"), config)
    calendar = ForexFactoryCalendarCollector(config, primary_db)
    news_rss = NewsRSSCollector(config, primary_db, classifier)

    scheduler.register_job(
        "economic_calendar",
        _tracked_async(calendar.fetch_calendar, "economic_calendar", health_monitor),
    )
    scheduler.register_job(
        "news_rss",
        _tracked_async(news_rss.fetch_breaking_news, "news_rss", health_monitor),
    )

    scheduler.start()
    return scheduler, health_monitor


def _run_preflight(config: dict, db_path: str) -> tuple:
    """Run preflight checks and print console report.

    Args:
        config: Full settings dict.
        db_path: Path to SQLite database.

    Returns:
        Tuple of (PreflightResult, HealthMonitor).
    """
    from custom.utils.health import HealthMonitor
    from custom.utils.preflight import format_preflight_console, run_preflight

    health_monitor = HealthMonitor(config)
    result = asyncio.run(run_preflight(config, db_path, health_monitor))
    print(format_preflight_console(result))
    return result, health_monitor


def main() -> None:
    """Initialize database, load config, start scheduler and Telegram bot.

    See docs/sub-specs/SS-01.md
    """
    parser = argparse.ArgumentParser(description="Crypto Signal Bot")
    parser.add_argument(
        "--preflight", action="store_true",
        help="Force preflight health check regardless of DB state",
    )
    args = parser.parse_args()

    config = load_config()
    db_path = config["general"]["database_path"]
    logging.getLogger().setLevel(config["general"].get("log_level", "INFO"))

    # Multi-asset DB initialization
    from custom.utils.asset_config import get_enabled_assets

    enabled_assets = get_enabled_assets(config)

    # Migration: copy existing signals.db → btc.db if needed
    import shutil
    old_db = Path(db_path)
    if old_db.exists():
        for ac in enabled_assets:
            asset_db = Path(ac.db_path)
            if not asset_db.exists():
                if ac.name == "BTC":
                    asset_db.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(old_db), str(asset_db))
                    logger.info("Migrated %s → %s", db_path, ac.db_path)

    # Initialize all per-asset databases
    for ac in enabled_assets:
        Path(ac.db_path).parent.mkdir(parents=True, exist_ok=True)
        init_db(ac.db_path)
        logger.info("Initialized DB for %s: %s", ac.name, ac.db_path)

    # Also init legacy DB if it doesn't exist (for backward compat)
    init_db(db_path)

    # Use primary asset DB as main reference
    primary_db = enabled_assets[0].db_path if enabled_assets else db_path

    # Load static macro calendar on startup (idempotent)
    from custom.collectors.sentiment import SentimentCollector
    sentiment = SentimentCollector(config, primary_db)
    static_count = sentiment.load_macro_calendar()
    if static_count:
        logger.info("Loaded %d static macro events", static_count)

    # Preflight check: run on first start (empty DB) or --preflight flag
    preflight_result = None
    preflight_health = None
    if args.preflight:
        from custom.utils.preflight import is_first_run

        logger.info("Preflight check requested via --preflight flag")
        preflight_result, preflight_health = _run_preflight(config, primary_db)
    else:
        from custom.utils.preflight import is_first_run

        if is_first_run(primary_db):
            logger.info("First run detected — running preflight check")
            preflight_result, preflight_health = _run_preflight(config, primary_db)

    # Start Telegram bot (blocks on polling)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # If --preflight with no Telegram token, just exit after checks
    if args.preflight and not token:
        logger.info("Preflight complete (no Telegram token). Exiting.")
        return

    if token:
        from custom.ai.analyzer import AIPromptBuilder, ClaudeAnalyzer
        from custom.ai.classifier import HeadlineClassifier
        from custom.output.bot import TelegramBot
        from custom.utils.preflight import format_preflight_telegram

        # Create shared AI instances (shared RateLimiter across all paths)
        ai_builder = AIPromptBuilder(primary_db, config)
        ai_analyzer = ClaudeAnalyzer(os.getenv("ANTHROPIC_API_KEY"), config, db_path=primary_db)
        headline_classifier = HeadlineClassifier(os.getenv("ANTHROPIC_API_KEY"), config)
        logger.info(
            "AI layer initialized (API key %s)",
            "configured" if os.getenv("ANTHROPIC_API_KEY") else "not set",
        )

        # 1. Create bot (no health_monitor/scheduler yet)
        bot = TelegramBot(config, primary_db)

        # 2. Start scheduler with bot reference for proactive jobs
        scheduler, health_monitor = start_scheduler(
            config, primary_db, bot=bot,
            ai_builder=ai_builder, ai_analyzer=ai_analyzer,
        )
        logger.info("Scheduler started with proactive messaging jobs")

        # Merge preflight health data into scheduler's health_monitor
        if preflight_health is not None:
            for src, state in preflight_health._sources.items():
                health_monitor._sources[src] = state

        # 3. Inject health_monitor + scheduler + AI back into bot
        bot._health_monitor = health_monitor
        bot._scheduler = scheduler
        bot._ai_prompt_builder = ai_builder
        bot._ai_analyzer = ai_analyzer
        bot._headline_classifier = headline_classifier

        # 4. Auto-add admin as subscriber
        bot._ensure_admin_subscriber()

        # 5. Queue preflight report for Telegram broadcast after event loop starts
        if preflight_result is not None:
            bot._pending_preflight_message = format_preflight_telegram(preflight_result)

        # 6. Start FastAPI dashboard
        _start_api(primary_db, config, health_monitor, scheduler)

        # 7. Start bot (blocks on polling, captures event loop via post_init)
        logger.info("Crypto Signal Bot started — Telegram bot active")
        try:
            bot.start()
        finally:
            scheduler.stop()
    else:
        import signal as sig

        # No bot — start scheduler without proactive messaging
        scheduler, health_monitor = start_scheduler(config, primary_db)

        # Merge preflight health data
        if preflight_health is not None:
            for src, state in preflight_health._sources.items():
                health_monitor._sources[src] = state

        # Start FastAPI dashboard
        _start_api(primary_db, config, health_monitor, scheduler)

        logger.info("Crypto Signal Bot started — no Telegram token, scheduler only")
        shutdown = threading.Event()
        sig.signal(sig.SIGINT, lambda *_: shutdown.set())
        sig.signal(sig.SIGTERM, lambda *_: shutdown.set())
        shutdown.wait()
        scheduler.stop()


def _start_api(
    db_path: str, config: dict, health_monitor: object, scheduler: object,
) -> None:
    """Start FastAPI dashboard on a background thread."""
    api_cfg = config.get("api", {})
    port = api_cfg.get("port", 8080)
    host = api_cfg.get("host", "0.0.0.0")

    try:
        from custom.api.app import create_app
        from custom.api.deps import init_state

        init_state(db_path=db_path, config=config,
                   health_monitor=health_monitor, scheduler=scheduler)
        app = create_app()

        def run() -> None:
            import uvicorn
            uvicorn.run(app, host=host, port=port, log_level="warning")

        api_thread = threading.Thread(target=run, daemon=True, name="fastapi")
        api_thread.start()
        logger.info("FastAPI dashboard started on %s:%d", host, port)
    except ImportError as e:
        logger.warning("FastAPI not available, dashboard disabled: %s", e)
    except Exception as e:
        logger.error("Failed to start FastAPI dashboard: %s", e)


if __name__ == "__main__":
    main()
