"""Composite Signal 2: Leverage Positioning.

See docs/sub-specs/SS-10.md §4.2
"""

import logging

import numpy as np

from custom.utils.db import get_latest

logger = logging.getLogger(__name__)


def _score_funding(funding_rate: float, cfg: dict) -> float:
    """Map funding rate to directional score (contrarian at extremes).

    See docs/sub-specs/SS-10.md §4.2
    """
    extreme_high = cfg["funding_extreme_high"]
    high = cfg["funding_high"]
    low = cfg["funding_low"]
    extreme_low = cfg["funding_extreme_low"]

    if funding_rate > extreme_high:
        return -1.0
    if funding_rate > high:
        t = (funding_rate - high) / (extreme_high - high)
        return -0.3 - t * 0.5
    if funding_rate > -low:  # above ~0.01 (mildly positive)
        return 0.0
    if funding_rate > low:  # neutral band around zero
        return 0.0
    if funding_rate > extreme_low:
        t = (funding_rate - extreme_low) / (low - extreme_low)
        return 0.6 - t * 0.3
    return 1.0


def _score_oi_regime(regime: str) -> float:
    """Map OI-price regime to score.

    See docs/sub-specs/SS-10.md §4.2
    """
    mapping = {
        "NEW_LONGS": 0.8,
        "NEW_SHORTS": -0.8,
        "LONG_CLOSING": -0.3,
        "SHORT_CLOSING": 0.3,
    }
    return mapping.get(regime, 0.0)


def _score_smart_retail(top_ls: float, global_ls: float, cfg: dict) -> float:
    """Score smart vs. retail divergence.

    See docs/sub-specs/SS-10.md §4.2
    """
    long_thresh = cfg["ls_net_long_threshold"]
    short_thresh = cfg["ls_net_short_threshold"]

    top_long = top_ls > long_thresh
    top_short = top_ls < short_thresh
    retail_long = global_ls > long_thresh
    retail_short = global_ls < short_thresh

    if top_long and retail_short:
        return 0.8
    if top_short and retail_long:
        return -0.8
    if top_long and retail_long:
        return 0.2
    if top_short and retail_short:
        return -0.2
    return 0.0


def _score_taker(taker_ratio: float, cfg: dict) -> float:
    """Score taker buy/sell aggression.

    See docs/sub-specs/SS-10.md §4.2
    """
    mult = cfg["taker_multiplier"]
    return float(np.clip((taker_ratio - 1.0) * mult, -1.0, 1.0))


def _consistency_multiplier(scores: list[float], cfg: dict) -> float:
    """Compute internal consistency multiplier.

    See docs/sub-specs/SS-10.md §4.2
    """
    positive = sum(1 for s in scores if s > 0)
    negative = sum(1 for s in scores if s < 0)

    if positive >= 3 or negative >= 3:
        return cfg["strong_agreement_multiplier"]
    if (positive >= 2 and negative == 0) or (negative >= 2 and positive == 0):
        return cfg["moderate_agreement_multiplier"]
    if positive >= 2 and negative >= 2:
        return cfg["conflict_multiplier"]
    return cfg["default_multiplier"]


def compute_leverage(db_path: str, config: dict) -> float:
    """Compute Composite Signal 2: Leverage Positioning.

    See docs/sub-specs/SS-10.md §4.2

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.

    Returns:
        Signal score in [-1.0, +1.0]. Returns 0.0 on failure.
    """
    try:
        cfg = config["leverage_positioning"]
        snap_rows = get_latest(db_path, "futures_snapshot", n=1, order_col="timestamp")
        if not snap_rows:
            logger.warning("Leverage signal: no futures data")
            return 0.0

        row = snap_rows[0]
        funding = row.get("funding_weighted_avg", 0.0) or 0.0
        top_ls = row.get("top_trader_ls_ratio", 1.0) or 1.0
        global_ls = row.get("global_ls_ratio", 1.0) or 1.0
        taker = row.get("taker_buy_sell_ratio", 1.0) or 1.0

        regime_rows = get_latest(db_path, "futures_oi_price", n=1, order_col="timestamp")
        regime = regime_rows[0].get("regime", "") if regime_rows else ""

        c1 = _score_funding(funding, cfg)
        c2 = _score_oi_regime(regime)
        c3 = _score_smart_retail(top_ls, global_ls, cfg)
        c4 = _score_taker(taker, cfg)

        scores = [c1, c2, c3, c4]
        consistency = _consistency_multiplier(scores, cfg)

        raw = (
            c1 * cfg["funding_weight"]
            + c2 * cfg["oi_price_weight"]
            + c3 * cfg["smart_retail_weight"]
            + c4 * cfg["taker_weight"]
        )
        final = float(np.clip(raw * consistency, -1.0, 1.0))
        logger.info(
            "Leverage: %.3f (fund=%.2f regime=%.2f sr=%.2f taker=%.2f cons=%.1f)",
            final, c1, c2, c3, c4, consistency,
        )
        return final
    except Exception as e:
        logger.error("Leverage signal failed: %s", e)
        return 0.0
