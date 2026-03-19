"""Confluence zone detection — clustering independent S/R levels.

See docs/sub-specs/SS-08.md §7.2
"""

import logging
from typing import Any

from custom.utils.db import get_latest

logger = logging.getLogger(__name__)


def collect_levels(
    db_path: str, spot: float, snapshot: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Gather price levels from all sources into a unified list.

    See docs/sub-specs/SS-08.md §7.2

    Sources: call/put walls, gamma flip, max pain, EMA 21/55/200,
    VWAP, liquidation clusters, round numbers.

    Args:
        db_path: Path to SQLite database.
        spot: Current spot price.
        snapshot: Options snapshot dict from compute_options_snapshot().

    Returns:
        List of {"price": float, "type": str, "source": str} dicts.
    """
    levels: list[dict[str, Any]] = []

    # 1. EMAs and VWAP from spot_technicals
    levels.extend(_levels_from_technicals(db_path))

    # 2. Call/Put walls from options_oi
    levels.extend(_levels_from_options_walls(db_path, spot))

    # 3. Gamma flip and max pain from snapshot or gex_data
    levels.extend(_levels_from_snapshot(db_path, snapshot))

    # 4. Round numbers
    levels.extend(_levels_from_round_numbers(spot))

    logger.debug("Collected %d raw levels from all sources", len(levels))
    return levels


def find_confluence_zones(
    levels: list[dict[str, Any]], spot: float, config: dict
) -> list[dict[str, Any]]:
    """Detect confluence zones where 3+ levels cluster within ±width_pct%.

    See docs/sub-specs/SS-08.md §7.2

    Algorithm:
      1. Sort levels by price ascending.
      2. For each level, find all others within ±width_pct%.
      3. If count ≥ min_levels → create zone (center = mean, strength = count).
      4. Merge overlapping zones.
      5. Classify as support (below spot) or resistance (above spot).

    Args:
        levels: List of level dicts from collect_levels().
        spot: Current spot price.
        config: Full settings dict.

    Returns:
        List of zone dicts sorted by distance from spot.
    """
    if not levels:
        return []

    tp_cfg = config.get("trade_plan", {})
    width_pct = tp_cfg.get("confluence_zone_width_pct", 0.5)
    min_levels = tp_cfg.get("confluence_min_levels", 3)

    sorted_levels = sorted(levels, key=lambda x: x["price"])
    zones: list[dict[str, Any]] = []
    used: set[int] = set()

    for i, level in enumerate(sorted_levels):
        if i in used:
            continue
        price = level["price"]
        threshold = price * width_pct / 100.0

        # Find all levels within ±width_pct%
        cluster_indices = []
        for j, other in enumerate(sorted_levels):
            if abs(other["price"] - price) <= threshold:
                cluster_indices.append(j)

        if len(cluster_indices) >= min_levels:
            cluster_prices = [sorted_levels[j]["price"] for j in cluster_indices]
            components = [sorted_levels[j]["source"] for j in cluster_indices]
            center = sum(cluster_prices) / len(cluster_prices)

            zones.append({
                "center": center,
                "strength": len(cluster_indices),
                "type": "support" if center < spot else "resistance",
                "components": components,
            })
            used.update(cluster_indices)

    # Merge overlapping zones
    merged = _merge_zones(zones, width_pct, spot)

    # Sort by distance from spot
    merged.sort(key=lambda z: abs(z["center"] - spot))
    return merged


def compute_confluence_zones(
    db_path: str, config: dict, spot: float, snapshot: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Orchestrator: collect levels and detect confluence zones.

    See docs/sub-specs/SS-08.md §7.2

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        spot: Current spot price.
        snapshot: Options snapshot dict from compute_options_snapshot().

    Returns:
        List of confluence zone dicts, or empty list on failure.
    """
    try:
        levels = collect_levels(db_path, spot, snapshot)
        zones = find_confluence_zones(levels, spot, config)
        logger.info("Found %d confluence zones", len(zones))
        return zones
    except Exception as e:
        logger.error("Confluence zone detection failed: %s", e)
        return []


# ── Private helpers ──────────────────────────────────────────


def _levels_from_technicals(db_path: str) -> list[dict[str, Any]]:
    """Extract EMA and VWAP levels from spot_technicals."""
    levels: list[dict[str, Any]] = []
    rows = get_latest(db_path, "spot_technicals", n=1, order_col="date")
    if not rows:
        return levels

    row = rows[0]
    mapping = {
        "ema_21": "EMA 21",
        "ema_55": "EMA 55",
        "ema_200": "EMA 200",
        "vwap": "VWAP",
        "bb_upper": "BB Upper",
        "bb_lower": "BB Lower",
    }
    for col, source in mapping.items():
        val = row.get(col)
        if val and val > 0:
            levels.append({"price": float(val), "type": "dynamic_sr", "source": source})

    return levels


def _levels_from_options_walls(
    db_path: str, spot: float, top_n: int = 5
) -> list[dict[str, Any]]:
    """Extract call/put wall levels from options_oi (highest OI strikes)."""
    levels: list[dict[str, Any]] = []
    rows = get_latest(db_path, "options_oi", n=200, order_col="date")
    if not rows:
        return levels

    # Aggregate OI by strike
    call_oi_by_strike: dict[float, float] = {}
    put_oi_by_strike: dict[float, float] = {}
    for row in rows:
        strike = row.get("strike")
        if strike is None:
            continue
        call_oi_by_strike[strike] = call_oi_by_strike.get(strike, 0) + (row.get("call_oi") or 0)
        put_oi_by_strike[strike] = put_oi_by_strike.get(strike, 0) + (row.get("put_oi") or 0)

    # Top call walls (resistance)
    top_calls = sorted(call_oi_by_strike.items(), key=lambda x: x[1], reverse=True)[:top_n]
    for strike, _ in top_calls:
        levels.append({"price": float(strike), "type": "resistance", "source": "Call Wall"})

    # Top put walls (support)
    top_puts = sorted(put_oi_by_strike.items(), key=lambda x: x[1], reverse=True)[:top_n]
    for strike, _ in top_puts:
        levels.append({"price": float(strike), "type": "support", "source": "Put Wall"})

    return levels


def _levels_from_snapshot(
    db_path: str, snapshot: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Extract gamma flip and max pain from options snapshot or gex_data."""
    levels: list[dict[str, Any]] = []

    gamma_flip = None
    max_pain = None

    if snapshot:
        gamma_flip = snapshot.get("gamma_flip")
        max_pain = snapshot.get("max_pain")
    else:
        # Fallback: read from gex_data
        rows = get_latest(db_path, "gex_data", n=1, order_col="date")
        if rows:
            gamma_flip = rows[0].get("gamma_flip_price")

    if gamma_flip and gamma_flip > 0:
        levels.append({"price": float(gamma_flip), "type": "boundary", "source": "Gamma Flip"})

    if max_pain and max_pain > 0:
        levels.append({"price": float(max_pain), "type": "magnet", "source": "Max Pain"})

    return levels


def _levels_from_round_numbers(spot: float, step: int = 5000) -> list[dict[str, Any]]:
    """Generate round number levels near the current spot price.

    Args:
        spot: Current spot price.
        step: Round number increment (default $5k).

    Returns:
        List of round number level dicts within ±15% of spot.
    """
    levels: list[dict[str, Any]] = []
    lower = int((spot * 0.85) // step) * step
    upper = int((spot * 1.15) // step + 1) * step

    price = lower
    while price <= upper:
        levels.append({"price": float(price), "type": "psychological", "source": "Round Number"})
        price += step

    return levels


def _merge_zones(
    zones: list[dict[str, Any]], width_pct: float, spot: float
) -> list[dict[str, Any]]:
    """Merge overlapping confluence zones."""
    if len(zones) <= 1:
        return zones

    sorted_zones = sorted(zones, key=lambda z: z["center"])
    merged: list[dict[str, Any]] = [sorted_zones[0]]

    for zone in sorted_zones[1:]:
        prev = merged[-1]
        threshold = prev["center"] * width_pct / 100.0
        if abs(zone["center"] - prev["center"]) <= threshold:
            # Merge: weighted average center, combine components
            total_strength = prev["strength"] + zone["strength"]
            new_center = (
                prev["center"] * prev["strength"] + zone["center"] * zone["strength"]
            ) / total_strength
            merged[-1] = {
                "center": new_center,
                "strength": total_strength,
                "type": "support" if new_center < spot else "resistance",
                "components": prev["components"] + zone["components"],
            }
        else:
            merged.append(zone)

    return merged
