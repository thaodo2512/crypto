"""CVD (Cumulative Volume Delta) calculators.

See docs/sub-specs/SS-07.md §3.2
"""

import logging
from typing import Any

import numpy as np

from custom.utils.db import get_latest, query

logger = logging.getLogger(__name__)

_MIN_DATA_POINTS = 5


def compute_cvd_zscore(db_path: str, lookback_days: int = 30) -> float:
    """Compute z-score of latest CVD against lookback window.

    See docs/sub-specs/SS-07.md §3.2

    Args:
        db_path: Path to SQLite database.
        lookback_days: Number of days of history to use.

    Returns:
        Z-score clipped to [-3.0, +3.0], or 0.0 if insufficient data.
    """
    rows = get_latest(db_path, "spot_cvd", n=lookback_days, order_col="timestamp")
    if len(rows) < _MIN_DATA_POINTS:
        logger.warning("CVD z-score: insufficient data (%d rows, need %d)", len(rows), _MIN_DATA_POINTS)
        return 0.0

    values = [r["cvd_24h"] for r in rows if r.get("cvd_24h") is not None]
    if len(values) < _MIN_DATA_POINTS:
        logger.warning("CVD z-score: insufficient non-null values (%d)", len(values))
        return 0.0

    arr = np.array(values, dtype=float)
    latest = arr[0]  # get_latest returns newest first
    mean = float(np.mean(arr))
    std = float(np.std(arr))

    if std == 0:
        return 0.0

    z = (latest - mean) / std
    result = float(np.clip(z, -3.0, 3.0))
    logger.debug("CVD z-score: %.3f (latest=%.2f, mean=%.2f, std=%.2f)", result, latest, mean, std)
    return result


def compute_cvd_divergence(db_path: str) -> dict[str, Any]:
    """Detect divergence between CVD direction and price direction.

    See docs/sub-specs/SS-07.md §3.2

    Args:
        db_path: Path to SQLite database.

    Returns:
        Dict with cvd_direction, price_direction, is_divergent.
    """
    default = {"cvd_direction": "neutral", "price_direction": "neutral", "is_divergent": False}

    cvd_rows = get_latest(db_path, "spot_cvd", n=1, order_col="timestamp")
    if not cvd_rows:
        logger.warning("CVD divergence: no CVD data")
        return default

    price_rows = get_latest(db_path, "spot_price", n=2, order_col="timestamp")
    if len(price_rows) < 2:
        logger.warning("CVD divergence: insufficient price data")
        return default

    cvd_24h = cvd_rows[0].get("cvd_24h", 0.0) or 0.0
    current_price = price_rows[0].get("close", 0.0) or 0.0
    prev_price = price_rows[1].get("close", 0.0) or 0.0

    if prev_price == 0:
        return default

    price_change = current_price - prev_price

    cvd_dir = "up" if cvd_24h > 0 else ("down" if cvd_24h < 0 else "neutral")
    price_dir = "up" if price_change > 0 else ("down" if price_change < 0 else "neutral")

    is_divergent = (
        (cvd_dir == "up" and price_dir == "down")
        or (cvd_dir == "down" and price_dir == "up")
    )

    logger.debug(
        "CVD divergence: cvd=%s price=%s divergent=%s",
        cvd_dir, price_dir, is_divergent,
    )
    return {
        "cvd_direction": cvd_dir,
        "price_direction": price_dir,
        "is_divergent": is_divergent,
    }


def compute_cvd_4h_confirmation(db_path: str) -> bool:
    """Check if 4h CVD confirms 24h CVD direction.

    See docs/sub-specs/SS-07.md §3.2

    Args:
        db_path: Path to SQLite database.

    Returns:
        True if cvd_4h and cvd_24h have the same sign.
    """
    rows = get_latest(db_path, "spot_cvd", n=1, order_col="timestamp")
    if not rows:
        logger.warning("CVD 4h confirmation: no data")
        return True  # default to confirmed when no data

    cvd_4h = rows[0].get("cvd_4h", 0.0) or 0.0
    cvd_24h = rows[0].get("cvd_24h", 0.0) or 0.0

    confirmed = (cvd_4h >= 0 and cvd_24h >= 0) or (cvd_4h < 0 and cvd_24h < 0)
    logger.debug("CVD 4h confirmation: %s (4h=%.2f, 24h=%.2f)", confirmed, cvd_4h, cvd_24h)
    return confirmed
