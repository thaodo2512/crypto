"""Composite Signal 4: Mean Reversion.

See docs/sub-specs/SS-12.md §4.4
"""

import logging

import numpy as np

from custom.utils.db import get_latest, query

logger = logging.getLogger(__name__)


def _score_rsi(rsi: float, cfg: dict) -> float:
    """Score RSI for mean reversion (inverse logic).

    See docs/sub-specs/SS-12.md §4.4
    """
    extreme_ob = cfg["rsi_extreme_overbought"]
    ob = cfg["rsi_overbought"]
    os_ = cfg["rsi_oversold"]
    extreme_os = cfg["rsi_extreme_oversold"]

    if rsi > extreme_ob:
        return -1.0
    if rsi > ob:
        t = (rsi - ob) / (extreme_ob - ob)
        return -0.5 - t * 0.5
    if rsi > 55:
        return 0.0
    if rsi > 45:
        return 0.0
    if rsi > os_:
        return 0.5
    if rsi > extreme_os:
        t = (rsi - extreme_os) / (os_ - extreme_os)
        return 1.0 - t * 0.5
    return 1.0


def _score_vwap(price: float, vwap: float) -> float:
    """Score price vs. VWAP distance.

    See docs/sub-specs/SS-12.md §4.4
    """
    if vwap == 0:
        return 0.0
    distance_pct = (price - vwap) / vwap * 100
    if distance_pct > 5:
        return -0.8
    if distance_pct > 2:
        return -0.3
    if distance_pct > -2:
        return 0.0
    if distance_pct > -5:
        return 0.3
    return 0.8


def _score_basis(basis_pct: float) -> float:
    """Score futures basis (annualized).

    See docs/sub-specs/SS-12.md §4.4
    """
    annualized = basis_pct * 365
    if annualized > 30:
        return -0.8
    if annualized > 15:
        return -0.4
    if annualized > 5:
        return 0.0
    if annualized > -5:
        return 0.3
    return 0.8


def _score_fear_greed(fg: float) -> float:
    """Score Fear & Greed index (contrarian).

    See docs/sub-specs/SS-12.md §4.4
    """
    if fg > 80:
        return -0.8
    if fg > 60:
        return -0.3
    if fg > 40:
        return 0.0
    if fg > 20:
        return 0.3
    return 0.8


def _score_bollinger(price: float, bb_upper: float, bb_lower: float) -> float:
    """Score Bollinger Band position.

    See docs/sub-specs/SS-12.md §4.4
    """
    bb_range = bb_upper - bb_lower
    if bb_range == 0:
        return 0.0
    position = (price - bb_lower) / bb_range
    if position > 0.95:
        return -0.8
    if position > 0.80:
        return -0.4
    if position > 0.20:
        return 0.0
    if position > 0.05:
        return 0.4
    return 0.8


def compute_mean_reversion(db_path: str, config: dict) -> float:
    """Compute Composite Signal 4: Mean Reversion.

    See docs/sub-specs/SS-12.md §4.4

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.

    Returns:
        Signal score in [-1.0, +1.0]. Returns 0.0 on failure.
    """
    try:
        cfg = config["mean_reversion"]

        tech_rows = get_latest(db_path, "spot_technicals", n=1, order_col="date")
        if not tech_rows:
            logger.warning("Mean Reversion: no technicals data")
            return 0.0
        tech = tech_rows[0]

        rsi = tech.get("rsi_14", 50.0) or 50.0
        price = tech.get("vwap", 0.0) or 0.0  # use VWAP as proxy for current price
        vwap = tech.get("vwap", 0.0) or 0.0
        bb_upper = tech.get("bb_upper", 0.0) or 0.0
        bb_lower = tech.get("bb_lower", 0.0) or 0.0

        # Get actual close price
        price_rows = get_latest(db_path, "spot_price", n=1, order_col="timestamp")
        if price_rows:
            price = price_rows[0].get("close", price) or price

        c1 = _score_rsi(rsi, cfg)

        c2 = _score_vwap(price, vwap)

        # Futures basis
        fut_rows = get_latest(db_path, "futures_snapshot", n=1, order_col="timestamp")
        basis = fut_rows[0].get("basis_pct", 0.0) or 0.0 if fut_rows else 0.0
        c3 = _score_basis(basis)

        # Fear & Greed
        fg_rows = get_latest(db_path, "daily_snapshot", n=1, order_col="date")
        fg = fg_rows[0].get("fear_greed", 50) or 50 if fg_rows else 50
        c4 = _score_fear_greed(fg)

        c5 = _score_bollinger(price, bb_upper, bb_lower)

        raw = (
            c1 * cfg["rsi_weight"]
            + c2 * cfg["vwap_weight"]
            + c3 * cfg["basis_weight"]
            + c4 * cfg["fear_greed_weight"]
            + c5 * cfg["bollinger_weight"]
        )
        final = float(np.clip(raw, -1.0, 1.0))
        logger.info(
            "Mean Reversion: %.3f (rsi=%.2f vwap=%.2f basis=%.2f fg=%.2f bb=%.2f)",
            final, c1, c2, c3, c4, c5,
        )
        return final
    except Exception as e:
        logger.error("Mean Reversion signal failed: %s", e)
        return 0.0
