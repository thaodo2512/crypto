"""Crypto Signal Bot — Entry point.

See docs/sub-specs/SS-01.md
"""

import logging

import yaml

from custom.utils.db import init_db

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


def main() -> None:
    """Initialize database, load config, and start the bot.

    See docs/sub-specs/SS-01.md
    """
    config = load_config()
    db_path = config["general"]["database_path"]
    logging.getLogger().setLevel(config["general"].get("log_level", "INFO"))

    logger.info("Initializing database...")
    init_db(db_path)
    logger.info("Crypto Signal Bot started")


if __name__ == "__main__":
    main()
