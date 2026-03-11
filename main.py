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
        t0 = time.time()
        try:
            asyncio.run(coro_func())
            health_monitor.record_success(source_name, time.time() - t0)
        except Exception as e:
            health_monitor.record_failure(source_name, str(e))
            raise
    wrapper.__name__ = getattr(coro_func, "__name__", source_name)
    return wrapper


def _make_signal_job(db_path: str, config: dict, bot: object) -> object:
    """Create a signal computation + broadcast job for the scheduler.

    See docs/sub-specs/SS-18.md §12

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        bot: TelegramBot instance with broadcast_sync().

    Returns:
        Callable job function.
    """
    def job() -> None:
        from custom.output.telegram_commands import format_signal_report
        from custom.signals.engine import compute_final_signal

        result = compute_final_signal(db_path, config)
        report = format_signal_report(result)
        bot.broadcast_sync(report)
    job.__name__ = "signal_compute_broadcast"
    return job


def _make_alert_job(
    db_path: str, config: dict, health_monitor: object, bot: object,
    ai_builder: object = None, ai_analyzer: object = None,
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

    Returns:
        Callable job function.
    """
    def job() -> None:
        from custom.output.alerts import check_alerts, check_system_health, format_alert
        from custom.utils.db import get_latest

        # Load 2 most recent signals for prev_signal tracking
        rows = get_latest(db_path, "signals", n=2, order_col="timestamp")
        signal = dict(rows[0]) if rows else {}
        prev_signal = dict(rows[1]) if len(rows) >= 2 else None

        alerts = check_alerts(db_path, signal, config, prev_signal=prev_signal)
        alerts.extend(check_system_health(health_monitor, config))

        if alerts:
            lines = ["🚨 ALERTS", ""]
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
    job.__name__ = "alert_check_broadcast"
    return job


def _make_daily_report_job(
    db_path: str, config: dict, bot: object,
    ai_builder: object = None, ai_analyzer: object = None,
) -> object:
    """Create a daily report broadcast job for the scheduler.

    See docs/sub-specs/SS-18.md §12

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        bot: TelegramBot instance with broadcast_sync().
        ai_builder: Optional AIPromptBuilder for AI narrative.
        ai_analyzer: Optional ClaudeAnalyzer for AI narrative.

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
            "📋 DAILY REPORT\n"
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
    job.__name__ = "daily_report_broadcast"
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


def start_scheduler(
    config: dict, db_path: str, bot: object = None,
    ai_builder: object = None, ai_analyzer: object = None,
) -> tuple:
    """Create, register jobs, and start the scheduler.

    See docs/sub-specs/SS-21.md §9

    Args:
        config: Full settings dict.
        db_path: Path to SQLite database.
        bot: Optional TelegramBot for proactive messaging jobs.
        ai_builder: Optional AIPromptBuilder for AI narrative in reports.
        ai_analyzer: Optional ClaudeAnalyzer for AI narrative in reports.

    Returns:
        Tuple of (SignalBotScheduler, HealthMonitor).
    """
    from custom.ai.classifier import HeadlineClassifier
    from custom.collectors.futures import FuturesCollector
    from custom.collectors.macro_calendar import ForexFactoryCalendarCollector
    from custom.collectors.news_rss import NewsRSSCollector
    from custom.collectors.options import OptionsCollector
    from custom.collectors.sentiment import SentimentCollector
    from custom.collectors.spot import SpotCollector
    from custom.scheduler import SignalBotScheduler
    from custom.utils.health import HealthMonitor

    scheduler = SignalBotScheduler(config)
    health_monitor = HealthMonitor(config)

    spot = SpotCollector(config, db_path)
    futures = FuturesCollector(config, db_path)
    options = OptionsCollector(config, db_path)
    sentiment = SentimentCollector(config, db_path)
    calendar = ForexFactoryCalendarCollector(config, db_path)
    classifier = HeadlineClassifier(os.getenv("ANTHROPIC_API_KEY"), config)
    news_rss = NewsRSSCollector(config, db_path, classifier)

    # Every 2 minutes
    scheduler.register_job("price", _tracked_async(spot.fetch_price, "spot_price", health_monitor))

    # Every 15 minutes
    scheduler.register_job("orderbook", _tracked_async(spot.fetch_orderbook, "spot_orderbook", health_monitor))
    scheduler.register_job("futures", _tracked_async(futures.fetch_snapshot, "futures", health_monitor))

    # Every hour
    scheduler.register_job("hourly", _tracked_async(spot.fetch_trades, "spot_trades", health_monitor))

    # Every hour — OI-price regime (needs ≥2 futures snapshots)
    scheduler.register_job("oi_price_regime", _tracked_async(
        futures.fetch_oi_price_regime, "oi_price_regime", health_monitor,
    ))

    # Every 4 hours — liquidations (Coinglass rate limit: ~100 req/day)
    scheduler.register_job("liquidations", _tracked_async(
        futures.fetch_liquidations, "liquidations", health_monitor,
    ))

    # Every 4 hours
    scheduler.register_job("options", _tracked_async(options.fetch_snapshot, "options", health_monitor))

    # Every 12 hours — Forex Factory economic calendar
    scheduler.register_job(
        "economic_calendar",
        _tracked_async(calendar.fetch_calendar, "economic_calendar", health_monitor),
    )

    # Every 15 minutes — RSS breaking news
    scheduler.register_job(
        "news_rss",
        _tracked_async(news_rss.fetch_breaking_news, "news_rss", health_monitor),
    )

    # Every hour — fill outcome prices for past signals
    def outcome_job() -> None:
        from custom.evaluation.tracker import fill_outcomes
        fill_outcomes(db_path)
    outcome_job.__name__ = "outcome_tracker"
    scheduler.register_job("outcome_tracker", outcome_job)

    # Daily at 08:00 UTC
    async def daily_job() -> None:
        await spot.fetch_technicals()
        await sentiment.fetch_fear_greed()
        # Fill remaining daily_snapshot columns from collectors
        await _fill_daily_snapshot(db_path, options)
    scheduler.register_job("daily_report", _tracked_async(daily_job, "daily_report", health_monitor))

    # Proactive messaging jobs (only when bot is available)
    if bot is not None:
        scheduler.register_job("signal_compute", _make_signal_job(db_path, config, bot))
        scheduler.register_job("alert_check", _make_alert_job(
            db_path, config, health_monitor, bot, ai_builder, ai_analyzer,
        ))
        scheduler.register_job("daily_broadcast", _make_daily_report_job(
            db_path, config, bot, ai_builder, ai_analyzer,
        ))

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

    logger.info("Initializing database...")
    init_db(db_path)

    # Load static macro calendar on startup (idempotent)
    from custom.collectors.sentiment import SentimentCollector
    sentiment = SentimentCollector(config, db_path)
    static_count = sentiment.load_macro_calendar()
    if static_count:
        logger.info("Loaded %d static macro events", static_count)

    # Preflight check: run on first start (empty DB) or --preflight flag
    preflight_result = None
    preflight_health = None
    if args.preflight:
        from custom.utils.preflight import is_first_run

        logger.info("Preflight check requested via --preflight flag")
        preflight_result, preflight_health = _run_preflight(config, db_path)
    else:
        from custom.utils.preflight import is_first_run

        if is_first_run(db_path):
            logger.info("First run detected — running preflight check")
            preflight_result, preflight_health = _run_preflight(config, db_path)

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
        ai_builder = AIPromptBuilder(db_path, config)
        ai_analyzer = ClaudeAnalyzer(os.getenv("ANTHROPIC_API_KEY"), config, db_path=db_path)
        headline_classifier = HeadlineClassifier(os.getenv("ANTHROPIC_API_KEY"), config)
        logger.info(
            "AI layer initialized (API key %s)",
            "configured" if os.getenv("ANTHROPIC_API_KEY") else "not set",
        )

        # 1. Create bot (no health_monitor/scheduler yet)
        bot = TelegramBot(config, db_path)

        # 2. Start scheduler with bot reference for proactive jobs
        scheduler, health_monitor = start_scheduler(
            config, db_path, bot=bot,
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
        _start_api(db_path, config, health_monitor, scheduler)

        # 7. Start bot (blocks on polling, captures event loop via post_init)
        logger.info("Crypto Signal Bot started — Telegram bot active")
        try:
            bot.start()
        finally:
            scheduler.stop()
    else:
        import signal as sig

        # No bot — start scheduler without proactive messaging
        scheduler, health_monitor = start_scheduler(config, db_path)

        # Merge preflight health data
        if preflight_health is not None:
            for src, state in preflight_health._sources.items():
                health_monitor._sources[src] = state

        # Start FastAPI dashboard
        _start_api(db_path, config, health_monitor, scheduler)

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
