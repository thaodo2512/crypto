"""Tests for SS-01: Foundation & Infrastructure.

See docs/sub-specs/SS-01.md §Acceptance Criteria
"""

import os
import sqlite3

import pytest

from custom.utils.db import (
    _VALID_TABLES,
    get_db,
    get_latest,
    init_db,
    insert_row,
    query,
)
from custom.utils.normalizers import clip_score, normalize_range, z_score
from main import load_config


# ─── Database Tests ──────────────────────────────────────


class TestDatabase:
    """Tests for custom/utils/db.py."""

    def test_init_db_creates_all_tables(self, db: sqlite3.Connection) -> None:
        """AC 1: init_db() creates all 17 tables without errors."""
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {
            row["name"]
            for row in cursor.fetchall()
            if not row["name"].startswith("sqlite_")
        }
        assert tables == _VALID_TABLES

    def test_init_db_idempotent(self, db_path: str) -> None:
        """AC 2: Calling init_db() twice doesn't error or duplicate tables."""
        init_db(db_path)  # second call (first is in fixture)
        conn = get_db(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {
            row["name"]
            for row in cursor.fetchall()
            if not row["name"].startswith("sqlite_")
        }
        conn.close()
        assert tables == _VALID_TABLES

    def test_insert_row_returns_id(self, db_path: str) -> None:
        """AC 3: insert_row() inserts a row and returns the row ID."""
        row_id = insert_row(
            db_path,
            "spot_price",
            {
                "timestamp": "2026-03-03T00:00:00Z",
                "open": 85000.0,
                "high": 86000.0,
                "low": 84000.0,
                "close": 85500.0,
                "volume": 1000.0,
                "quote_volume": 85500000.0,
                "num_trades": 5000,
            },
        )
        assert isinstance(row_id, int)
        assert row_id >= 1

    def test_query_returns_list_of_dicts(self, db_path: str) -> None:
        """AC 4: query() returns list of dicts for SELECT statements."""
        insert_row(
            db_path,
            "spot_price",
            {"timestamp": "2026-03-03T00:00:00Z", "close": 85000.0},
        )
        results = query(db_path, "SELECT * FROM spot_price")
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], dict)
        assert results[0]["close"] == 85000.0
        assert results[0]["timestamp"] == "2026-03-03T00:00:00Z"

    def test_get_latest_returns_n_rows(self, db_path: str) -> None:
        """AC 5: get_latest() returns N most recent rows ordered by timestamp."""
        for i in range(5):
            insert_row(
                db_path,
                "spot_price",
                {"timestamp": f"2026-03-0{i + 1}T00:00:00Z", "close": 85000.0 + i},
            )
        results = get_latest(db_path, "spot_price", n=3)
        assert len(results) == 3
        # Most recent first
        assert results[0]["timestamp"] == "2026-03-05T00:00:00Z"
        assert results[2]["timestamp"] == "2026-03-03T00:00:00Z"

    def test_insert_row_invalid_table(self, db_path: str) -> None:
        """Edge: insert_row() rejects invalid table names."""
        with pytest.raises(ValueError, match="Invalid table name"):
            insert_row(db_path, "nonexistent_table", {"foo": "bar"})

    def test_get_latest_custom_order_col(self, db_path: str) -> None:
        """Edge: get_latest() works with 'date' order column."""
        for i in range(3):
            insert_row(
                db_path,
                "spot_technicals",
                {"date": f"2026-03-0{i + 1}", "rsi_14": 50.0 + i},
            )
        results = get_latest(db_path, "spot_technicals", n=2, order_col="date")
        assert len(results) == 2
        assert results[0]["date"] == "2026-03-03"


# ─── Normalizer Tests ────────────────────────────────────


class TestNormalizers:
    """Tests for custom/utils/normalizers.py."""

    def test_z_score_normal(self) -> None:
        """AC 6: z_score(10, 5, 2) returns 2.5."""
        assert z_score(10, 5, 2) == 2.5

    def test_z_score_zero_std(self) -> None:
        """AC 7: z_score(10, 5, 0) returns 0.0 (safe division)."""
        assert z_score(10, 5, 0) == 0.0

    def test_clip_score_above_max(self) -> None:
        """AC 8: clip_score(1.5) returns 1.0."""
        assert clip_score(1.5) == 1.0

    def test_clip_score_below_min(self) -> None:
        """AC 9: clip_score(-2.0) returns -1.0."""
        assert clip_score(-2.0) == -1.0

    def test_clip_score_no_clip(self) -> None:
        """AC 10: clip_score(0.5) returns 0.5 (no clipping needed)."""
        assert clip_score(0.5) == 0.5

    def test_normalize_range_midpoint(self) -> None:
        """AC 11: normalize_range(75, 50, 100) returns 0.0 (midpoint)."""
        assert normalize_range(75, 50, 100) == 0.0

    def test_normalize_range_equal_bounds(self) -> None:
        """Edge: normalize_range returns 0.0 when min == max."""
        assert normalize_range(50, 50, 50) == 0.0


# ─── Config Tests ────────────────────────────────────────


class TestConfig:
    """Tests for config loading."""

    def test_config_loads_yaml(self) -> None:
        """AC 12: Config loads from YAML file and provides dict-like access."""
        config = load_config("config/settings.yaml")
        assert isinstance(config, dict)
        assert config["general"]["target_asset"] == "BTC/USDT"
        assert config["general"]["database_path"] == "data/signals.db"
        assert isinstance(config["spot_flow"]["cvd_weight"], float)

    def test_config_missing_key_raises(self) -> None:
        """AC 13: Missing config key raises KeyError."""
        config = load_config("config/settings.yaml")
        with pytest.raises(KeyError):
            _ = config["nonexistent_section"]


# ─── Structural Tests ────────────────────────────────────


class TestStructure:
    """Tests for project structure."""

    def test_init_files_exist(self) -> None:
        """AC 14: All __init__.py files exist and are empty."""
        init_dirs = [
            "custom",
            "custom/collectors",
            "custom/calculators",
            "custom/signals",
            "custom/regime",
            "custom/trade_plan",
            "custom/output",
            "custom/ai",
            "custom/evaluation",
            "custom/utils",
        ]
        for d in init_dirs:
            init_path = os.path.join(d, "__init__.py")
            assert os.path.exists(init_path), f"Missing {init_path}"
            with open(init_path) as f:
                content = f.read()
            assert content == "", f"{init_path} is not empty"
