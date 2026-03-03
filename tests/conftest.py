"""Shared test fixtures.

See docs/sub-specs/SS-01.md §Tests
"""

import sqlite3
import tempfile
from typing import Generator

import pytest

from custom.utils.db import init_db, get_db


@pytest.fixture
def db_path(tmp_path) -> str:
    """Return a temporary database path."""
    path = str(tmp_path / "test_signals.db")
    init_db(path)
    return path


@pytest.fixture
def db(db_path) -> Generator[sqlite3.Connection, None, None]:
    """In-memory-style SQLite with all tables created."""
    conn = get_db(db_path)
    yield conn
    conn.close()


@pytest.fixture
def config() -> dict:
    """Test configuration dict mirroring settings.yaml structure."""
    return {
        "general": {
            "target_asset": "BTC/USDT",
            "database_path": ":memory:",
            "log_level": "DEBUG",
            "timezone": "UTC",
        },
        "signal_classification": {
            "no_signal_threshold": 0.15,
            "weak_threshold": 0.35,
            "moderate_threshold": 0.60,
        },
        "spot_flow": {
            "cvd_weight": 0.50,
            "whale_weight": 0.25,
            "orderbook_weight": 0.25,
            "z_score_lookback_days": 30,
        },
        "health": {
            "staleness_threshold_minutes": 30,
            "latency_threshold_seconds": 5,
            "consecutive_failures_before_fallback": 3,
        },
    }
