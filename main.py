"""Crypto Signal Bot — Entry point.

See docs/sub-specs/SS-01.md
"""

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


def start_scheduler(config: dict, db_path: str) -> tuple:
    """Create, register jobs, and start the scheduler.

    See docs/sub-specs/SS-21.md §9

    Args:
        config: Full settings dict.
        db_path: Path to SQLite database.

    Returns:
        Tuple of (SignalBotScheduler, HealthMonitor).
    """
    from custom.collectors.futures import FuturesCollector
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

    # Every 2 minutes
    scheduler.register_job("price", _tracked_async(spot.fetch_price, "spot_price", health_monitor))

    # Every 15 minutes
    scheduler.register_job("orderbook", _tracked_async(spot.fetch_orderbook, "spot_orderbook", health_monitor))
    scheduler.register_job("futures", _tracked_async(futures.fetch_snapshot, "futures", health_monitor))

    # Every hour
    scheduler.register_job("hourly", _tracked_async(spot.fetch_trades, "spot_trades", health_monitor))

    # Every 4 hours
    scheduler.register_job("options", _tracked_async(options.fetch_snapshot, "options", health_monitor))

    # Daily at 08:00 UTC
    async def daily_job() -> None:
        await spot.fetch_technicals()
        await sentiment.fetch_fear_greed()
    scheduler.register_job("daily_report", _tracked_async(daily_job, "daily_report", health_monitor))

    scheduler.start()
    return scheduler, health_monitor


def main() -> None:
    """Initialize database, load config, start scheduler and Telegram bot.

    See docs/sub-specs/SS-01.md
    """
    config = load_config()
    db_path = config["general"]["database_path"]
    logging.getLogger().setLevel(config["general"].get("log_level", "INFO"))

    logger.info("Initializing database...")
    init_db(db_path)

    # Start scheduler in background thread
    scheduler, health_monitor = start_scheduler(config, db_path)
    logger.info("Scheduler started")

    # Start Telegram bot (blocks on polling)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if token:
        from custom.output.bot import TelegramBot
        bot = TelegramBot(config, db_path, health_monitor=health_monitor, scheduler=scheduler)
        logger.info("Crypto Signal Bot started — Telegram bot active")
        try:
            bot.start()  # Blocks until stopped
        finally:
            scheduler.stop()
    else:
        import signal as sig
        logger.info("Crypto Signal Bot started — no Telegram token, scheduler only")
        shutdown = threading.Event()
        sig.signal(sig.SIGINT, lambda *_: shutdown.set())
        sig.signal(sig.SIGTERM, lambda *_: shutdown.set())
        shutdown.wait()
        scheduler.stop()


if __name__ == "__main__":
    main()
