"""Composite Signal 1: Spot Flow.

See docs/sub-specs/SS-09.md §4.1
"""

import logging

import numpy as np

from custom.calculators.cvd import (
    compute_cvd_4h_confirmation,
    compute_cvd_divergence,
    compute_cvd_zscore,
)
from custom.utils.db import get_latest

logger = logging.getLogger(__name__)


def _compute_cvd_component(db_path: str, config: dict) -> float:
    """Compute CVD analysis component.

    See docs/sub-specs/SS-09.md §4.1

    Args:
        db_path: Path to SQLite database.
        config: spot_flow config section.

    Returns:
        CVD component score in [-1, +1].
    """
    lookback = config.get("z_score_lookback_days", 30)
    z = compute_cvd_zscore(db_path, lookback_days=lookback)
    score = float(np.clip(z, -1.0, 1.0))

    divergence = compute_cvd_divergence(db_path)
    if divergence["is_divergent"]:
        amp = config["cvd_divergence_amplifier"]
        score *= amp
        logger.debug("CVD divergence detected, amplified by %.1f", amp)

    if not compute_cvd_4h_confirmation(db_path):
        factor = config["cvd_4h_contradiction_factor"]
        score *= factor
        logger.debug("CVD 4h contradiction, reduced by %.1f", factor)

    return float(np.clip(score, -1.0, 1.0))


def _compute_whale_component(db_path: str) -> float:
    """Compute whale trade ratio component.

    See docs/sub-specs/SS-09.md §4.1

    Args:
        db_path: Path to SQLite database.

    Returns:
        Whale component score in [-1, +1].
    """
    rows = get_latest(db_path, "spot_whale_trades", n=100, order_col="timestamp")
    if not rows:
        return 0.0

    buy_vol = sum(r["value_usd"] for r in rows if r.get("side") == "buy")
    sell_vol = sum(r["value_usd"] for r in rows if r.get("side") == "sell")
    total = buy_vol + sell_vol
    if total == 0:
        return 0.0

    whale_ratio = buy_vol / total
    score = (whale_ratio - 0.5) * 2
    return float(np.clip(score, -1.0, 1.0))


def _compute_orderbook_component(db_path: str, config: dict) -> float:
    """Compute order book imbalance component with anti-spoof filter.

    See docs/sub-specs/SS-09.md §4.1

    Args:
        db_path: Path to SQLite database.
        config: spot_flow config section.

    Returns:
        Orderbook component score in [-1, +1].
    """
    rows = get_latest(db_path, "spot_orderbook", n=1, order_col="timestamp")
    if not rows:
        return 0.0

    imbalance = rows[0].get("imbalance", 0.0) or 0.0
    threshold = config["anti_spoof_threshold"]
    factor = config["anti_spoof_factor"]

    if abs(imbalance) > threshold:
        imbalance *= factor

    return float(np.clip(imbalance, -1.0, 1.0))


def _compute_volume_multiplier(db_path: str, config: dict) -> float:
    """Compute volume multiplier.

    See docs/sub-specs/SS-09.md §4.1

    Args:
        db_path: Path to SQLite database.
        config: spot_flow config section.

    Returns:
        Volume multiplier (positive float).
    """
    rows = get_latest(db_path, "spot_technicals", n=1, order_col="date")
    if not rows:
        return 1.0

    volume_ratio = rows[0].get("volume_ratio", 1.0) or 1.0
    high_thresh = config["volume_high_threshold"]
    low_thresh = config["volume_low_threshold"]
    high_mult = config["volume_high_multiplier"]
    low_mult = config["volume_low_multiplier"]
    base = config["volume_base"]
    slope = config["volume_slope"]

    if volume_ratio > high_thresh:
        return high_mult
    if volume_ratio < low_thresh:
        return low_mult
    return base + volume_ratio * slope


def compute_spot_flow(db_path: str, config: dict) -> float:
    """Compute Composite Signal 1: Spot Flow.

    See docs/sub-specs/SS-09.md §4.1

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.

    Returns:
        Signal score in [-1.0, +1.0]. Returns 0.0 on failure.
    """
    try:
        cfg = config["spot_flow"]
        cvd = _compute_cvd_component(db_path, cfg)
        whale = _compute_whale_component(db_path)
        orderbook = _compute_orderbook_component(db_path, cfg)
        vol_mult = _compute_volume_multiplier(db_path, cfg)

        raw = (
            cvd * cfg["cvd_weight"]
            + whale * cfg["whale_weight"]
            + orderbook * cfg["orderbook_weight"]
        )
        final = float(np.clip(raw * vol_mult, -1.0, 1.0))
        logger.info(
            "Spot Flow: %.3f (cvd=%.3f whale=%.3f ob=%.3f vol_mult=%.2f)",
            final, cvd, whale, orderbook, vol_mult,
        )
        return final
    except Exception as e:
        logger.error("Spot Flow signal failed: %s", e)
        return 0.0
