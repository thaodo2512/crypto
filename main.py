"""Crypto Signal Bot — Entry point.

See docs/sub-specs/SS-01.md
"""

import asyncio
import logging
import os
import threading

import yaml
from dotenv import load_dotenv

from custom.utils.db import init_db

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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


def start_scheduler(config: dict, db_path: str) -> object:
    """Create, register jobs, and start the scheduler.

    See docs/sub-specs/SS-21.md §9

    Args:
        config: Full settings dict.
        db_path: Path to SQLite database.

    Returns:
        Running SignalBotScheduler instance.
    """
    from custom.collectors.futures import FuturesCollector
    from custom.collectors.options import OptionsCollector
    from custom.collectors.sentiment import SentimentCollector
    from custom.collectors.spot import SpotCollector
    from custom.scheduler import SignalBotScheduler

    scheduler = SignalBotScheduler(config)

    spot = SpotCollector(config, db_path)
    futures = FuturesCollector(config, db_path)
    options = OptionsCollector(config, db_path)
    sentiment = SentimentCollector(config, db_path)

    # Every 2 minutes
    scheduler.register_job("price", _run_async(spot.fetch_price))

    # Every 15 minutes
    scheduler.register_job("orderbook", _run_async(spot.fetch_orderbook))
    scheduler.register_job("futures", _run_async(futures.fetch_snapshot))

    # Every hour
    scheduler.register_job("hourly", _run_async(spot.fetch_trades))

    # Every 4 hours
    scheduler.register_job("options", _run_async(options.fetch_snapshot))

    # Daily at 08:00 UTC
    async def daily_job() -> None:
        await spot.fetch_technicals()
        await sentiment.fetch_fear_greed()
    scheduler.register_job("daily_report", _run_async(daily_job))

    scheduler.start()
    return scheduler


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
    scheduler = start_scheduler(config, db_path)
    logger.info("Scheduler started")

    # Start Telegram bot (blocks on polling)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if token:
        from custom.output.bot import TelegramBot
        bot = TelegramBot(config, db_path)
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
