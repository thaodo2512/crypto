"""Composite Signal 3: Options Structure.

See docs/sub-specs/SS-11.md §4.3
"""

import logging
from typing import Any

import numpy as np

from custom.utils.db import query

logger = logging.getLogger(__name__)


def _score_gamma_flip(spot: float, gamma_flip: float | None) -> float:
    """Score gamma flip distance.

    See docs/sub-specs/SS-11.md §4.3
    """
    if gamma_flip is None or spot == 0:
        return 0.0
    distance_pct = (spot - gamma_flip) / spot * 100
    if distance_pct > 5:
        return 0.8
    if distance_pct > 2:
        return 0.5
    if distance_pct > 0:
        return 0.2
    if distance_pct > -2:
        return -0.5
    return -0.8


def _score_net_gex(total_net_gex: float, db_path: str, lookback_days: int) -> float:
    """Score net GEX via z-score against history.

    See docs/sub-specs/SS-11.md §4.3
    """
    rows = query(
        db_path,
        "SELECT SUM(net_gex) as total FROM gex_data GROUP BY date ORDER BY date DESC LIMIT ?",
        (lookback_days,),
    )
    if len(rows) < 5:
        return 0.0

    values = [r["total"] for r in rows if r.get("total") is not None]
    if len(values) < 5:
        return 0.0

    arr = np.array(values, dtype=float)
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    if std == 0:
        return 0.0

    z = (total_net_gex - mean) / std

    if z > 1:
        return 0.6
    if z > 0:
        return 0.3
    if z > -1:
        return -0.3
    return -0.6


def _score_iv_skew(iv_skew: float | None) -> float:
    """Score IV skew (contrarian).

    See docs/sub-specs/SS-11.md §4.3
    """
    if iv_skew is None:
        return 0.0
    if iv_skew > 5:
        return 0.6
    if iv_skew > 2:
        return 0.3
    if iv_skew > -2:
        return 0.0
    if iv_skew > -5:
        return -0.3
    return -0.6


def _score_max_pain(spot: float, max_pain: float | None) -> float:
    """Score max pain gravity.

    See docs/sub-specs/SS-11.md §4.3
    """
    if max_pain is None or spot == 0:
        return 0.0
    distance_pct = (spot - max_pain) / spot * 100
    if distance_pct > 5:
        return -0.5
    if distance_pct > 2:
        return -0.3
    if distance_pct > -2:
        return 0.0
    if distance_pct > -5:
        return 0.3
    return 0.5


def compute_options_signal(
    db_path: str, config: dict, snapshot: dict[str, Any], spot: float
) -> float:
    """Compute Composite Signal 3: Options Structure.

    See docs/sub-specs/SS-11.md §4.3

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        snapshot: Output of compute_options_snapshot() from SS-07.
        spot: Current spot price.

    Returns:
        Signal score in [-1.0, +1.0]. Returns 0.0 on failure.
    """
    try:
        cfg = config["options_structure"]
        lookback = cfg.get("z_score_lookback_days", 30)

        c1 = _score_gamma_flip(spot, snapshot.get("gamma_flip"))
        c2 = _score_net_gex(snapshot.get("total_net_gex", 0.0), db_path, lookback)
        c3 = _score_iv_skew(snapshot.get("iv_skew"))
        c4 = _score_max_pain(spot, snapshot.get("max_pain"))

        raw = (
            c1 * cfg["gamma_flip_weight"]
            + c2 * cfg["net_gex_weight"]
            + c3 * cfg["iv_skew_weight"]
            + c4 * cfg["max_pain_weight"]
        )
        final = float(np.clip(raw, -1.0, 1.0))
        logger.info(
            "Options Signal: %.3f (flip=%.2f gex=%.2f skew=%.2f mp=%.2f)",
            final, c1, c2, c3, c4,
        )
        return final
    except Exception as e:
        logger.error("Options signal failed: %s", e)
        return 0.0
