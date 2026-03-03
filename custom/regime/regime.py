"""Market regime detection and adaptive weight engine.

See docs/sub-specs/SS-14.md §5
"""

import logging
from typing import Any

import numpy as np

from custom.utils.db import get_latest

logger = logging.getLogger(__name__)


def detect_regime(adx: float, bb_width_percentile: float, config: dict) -> str:
    """Classify the current market regime.

    See docs/sub-specs/SS-14.md §5.1

    Args:
        adx: ADX(14) value.
        bb_width_percentile: BB width percentile (0-100).
        config: Full settings dict.

    Returns:
        Regime string: STRONG_TREND, MODERATE_TREND, WIDE_RANGE,
        TIGHT_RANGE, or TRANSITIONAL.
    """
    cfg = config["regime"]
    adx_strong = cfg["adx_strong_trend"]
    adx_moderate = cfg["adx_moderate_trend"]
    adx_tight = cfg["adx_tight_range"]
    bb_strong = cfg["bb_strong_trend_pctile"]
    bb_moderate = cfg["bb_moderate_trend_pctile"]
    bb_tight = cfg["bb_tight_range_pctile"]
    bb_wide = cfg["bb_wide_range_pctile"]

    if adx > adx_strong and bb_width_percentile > bb_strong:
        return "STRONG_TREND"
    if adx > adx_moderate and bb_width_percentile > bb_moderate:
        return "MODERATE_TREND"
    if adx < adx_tight and bb_width_percentile < bb_tight:
        return "TIGHT_RANGE"
    if adx < adx_moderate and bb_width_percentile < bb_wide:
        return "WIDE_RANGE"
    return "TRANSITIONAL"


def get_regime_weights(regime: str, config: dict) -> dict[str, float]:
    """Get signal weights for the current regime.

    See docs/sub-specs/SS-14.md §5.1

    Args:
        regime: Regime classification string.
        config: Full settings dict.

    Returns:
        Dict of signal weights keyed by signal name.
    """
    regime_key = regime.lower()
    weights_cfg = config["adaptive_weights"]
    if regime_key in weights_cfg:
        return dict(weights_cfg[regime_key])
    logger.warning("Unknown regime '%s', using transitional weights", regime)
    return dict(weights_cfg["transitional"])


def smooth_weights(
    new_weights: dict[str, float],
    prev_weights: dict[str, float] | None,
    smoothing_factor: float,
) -> dict[str, float]:
    """Apply EMA smoothing to prevent weight whipsawing.

    See docs/sub-specs/SS-14.md §5.2

    Args:
        new_weights: New regime weights.
        prev_weights: Previous weights (None on first call).
        smoothing_factor: EMA factor from config (0-1).

    Returns:
        Smoothed weights dict.
    """
    if prev_weights is None:
        return dict(new_weights)

    smoothed = {}
    for key, new_val in new_weights.items():
        prev_val = prev_weights.get(key, new_val)
        smoothed[key] = smoothing_factor * new_val + (1 - smoothing_factor) * prev_val
    return smoothed


def compute_bb_width_percentile(db_path: str, lookback_days: int = 90) -> float:
    """Compute BB width percentile from historical data.

    See docs/sub-specs/SS-14.md §5.1

    Args:
        db_path: Path to SQLite database.
        lookback_days: Number of days of history.

    Returns:
        Percentile (0-100) of latest BB width, or 50.0 if insufficient data.
    """
    rows = get_latest(db_path, "spot_technicals", n=lookback_days, order_col="date")
    if len(rows) < 5:
        logger.warning("BB width percentile: insufficient data (%d rows)", len(rows))
        return 50.0

    widths = [r["bb_width"] for r in rows if r.get("bb_width") is not None]
    if len(widths) < 5:
        return 50.0

    latest = widths[0]  # get_latest returns newest first
    arr = np.array(widths, dtype=float)
    percentile = float(np.sum(arr <= latest) / len(arr) * 100)
    logger.debug("BB width percentile: %.1f (latest=%.4f, n=%d)", percentile, latest, len(arr))
    return percentile


def compute_regime(db_path: str, config: dict, prev_weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Detect regime and compute smoothed adaptive weights.

    See docs/sub-specs/SS-14.md §5

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        prev_weights: Previous smoothed weights (None on first call).

    Returns:
        Dict with regime, weights, and raw_weights.
    """
    try:
        tech_rows = get_latest(db_path, "spot_technicals", n=1, order_col="date")
        if not tech_rows:
            logger.warning("Regime detection: no technicals data")
            return {
                "regime": "TRANSITIONAL",
                "weights": get_regime_weights("TRANSITIONAL", config),
                "raw_weights": get_regime_weights("TRANSITIONAL", config),
            }

        adx = tech_rows[0].get("adx_14", 25.0) or 25.0
        lookback = config["regime"].get("bb_width_lookback_days", 90)
        bb_pctile = compute_bb_width_percentile(db_path, lookback)

        regime = detect_regime(adx, bb_pctile, config)
        raw_weights = get_regime_weights(regime, config)
        smoothing = config["adaptive_weights"]["smoothing_factor"]
        weights = smooth_weights(raw_weights, prev_weights, smoothing)

        logger.info("Regime: %s (ADX=%.1f BB%%ile=%.1f)", regime, adx, bb_pctile)
        return {
            "regime": regime,
            "weights": weights,
            "raw_weights": raw_weights,
        }
    except Exception as e:
        logger.error("Regime detection failed: %s", e)
        return {
            "regime": "TRANSITIONAL",
            "weights": {"spot_flow": 0.25, "leverage_pos": 0.25, "options_struct": 0.25, "mean_reversion": 0.25},
            "raw_weights": {"spot_flow": 0.25, "leverage_pos": 0.25, "options_struct": 0.25, "mean_reversion": 0.25},
        }
