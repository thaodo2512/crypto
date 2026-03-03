"""Tests for SS-07: CVD Calculators.

See docs/sub-specs/SS-07.md §Acceptance Criteria
"""

import pytest

from custom.calculators.cvd import (
    compute_cvd_4h_confirmation,
    compute_cvd_divergence,
    compute_cvd_zscore,
)
from custom.utils.db import init_db, insert_row


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def db(tmp_path) -> str:
    """Initialized test database with sample CVD and price data."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


def _insert_cvd_rows(db_path: str, values: list[tuple[float, float, float]]) -> None:
    """Insert CVD rows with ascending timestamps.

    Args:
        db_path: Database path.
        values: List of (cvd_1h, cvd_4h, cvd_24h) tuples, oldest first.
    """
    for i, (cvd_1h, cvd_4h, cvd_24h) in enumerate(values):
        insert_row(db_path, "spot_cvd", {
            "timestamp": f"2026-03-01T{i:02d}:00:00",
            "cvd_1h": cvd_1h,
            "cvd_4h": cvd_4h,
            "cvd_24h": cvd_24h,
            "buy_volume": 1000.0,
            "sell_volume": 800.0,
        })


def _insert_price_rows(db_path: str, prices: list[float]) -> None:
    """Insert price rows with ascending timestamps, oldest first."""
    for i, close in enumerate(prices):
        insert_row(db_path, "spot_price", {
            "timestamp": f"2026-03-01T{i:02d}:00:00",
            "open": close,
            "high": close + 100,
            "low": close - 100,
            "close": close,
            "volume": 5000.0,
            "quote_volume": 5000.0 * close,
            "num_trades": 1000,
        })


# ─── TestComputeCvdZscore ────────────────────────────────


class TestComputeCvdZscore:
    """Tests for compute_cvd_zscore()."""

    def test_cvd_zscore_normal(self, db) -> None:
        """AC 12: Returns z-score of latest CVD against lookback window."""
        # 10 data points with known distribution: mean ~0, latest = 5.0 (high z-score)
        values = [
            (0, 0, -1.0), (0, 0, 0.5), (0, 0, -0.5), (0, 0, 1.0),
            (0, 0, -0.3), (0, 0, 0.2), (0, 0, -0.7), (0, 0, 0.8),
            (0, 0, 0.1), (0, 0, 5.0),  # latest (highest timestamp)
        ]
        _insert_cvd_rows(db, values)

        z = compute_cvd_zscore(db, lookback_days=30)

        # latest=5.0 is well above mean, so z should be > 1
        assert z > 1.0
        assert z <= 3.0  # clipped

    def test_cvd_zscore_insufficient_data(self, db) -> None:
        """AC 13: Returns 0.0 when insufficient data (< 5 points)."""
        values = [(0, 0, 1.0), (0, 0, 2.0), (0, 0, 3.0)]
        _insert_cvd_rows(db, values)

        z = compute_cvd_zscore(db, lookback_days=30)
        assert z == 0.0


# ─── TestComputeCvdDivergence ────────────────────────────


class TestComputeCvdDivergence:
    """Tests for compute_cvd_divergence()."""

    def test_cvd_divergence_detected(self, db) -> None:
        """AC 14: Detects when CVD and price move in opposite directions."""
        # CVD positive (buying pressure) but price falling
        _insert_cvd_rows(db, [(0, 0, 500.0)])
        _insert_price_rows(db, [105000.0, 100000.0])  # price down

        result = compute_cvd_divergence(db)

        assert result["cvd_direction"] == "up"
        assert result["price_direction"] == "down"
        assert result["is_divergent"] is True

    def test_cvd_divergence_aligned(self, db) -> None:
        """AC 14: No divergence when CVD and price agree."""
        _insert_cvd_rows(db, [(0, 0, 500.0)])
        _insert_price_rows(db, [100000.0, 105000.0])  # price up

        result = compute_cvd_divergence(db)

        assert result["cvd_direction"] == "up"
        assert result["price_direction"] == "up"
        assert result["is_divergent"] is False


# ─── TestComputeCvd4hConfirmation ────────────────────────


class TestComputeCvd4hConfirmation:
    """Tests for compute_cvd_4h_confirmation()."""

    def test_cvd_4h_confirmation_agree(self, db) -> None:
        """AC 15: Returns True when 4h and 24h CVD agree in sign."""
        _insert_cvd_rows(db, [(0, 100.0, 500.0)])  # both positive

        assert compute_cvd_4h_confirmation(db) is True

    def test_cvd_4h_confirmation_disagree(self, db) -> None:
        """AC 15: Returns False when 4h and 24h CVD disagree."""
        _insert_cvd_rows(db, [(0, -100.0, 500.0)])  # 4h neg, 24h pos

        assert compute_cvd_4h_confirmation(db) is False
