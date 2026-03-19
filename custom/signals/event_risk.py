"""Signal 5: Event Risk (Modifier).

See docs/sub-specs/SS-13.md §4.5
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from custom.utils.db import get_latest, query

logger = logging.getLogger(__name__)


def _risk_options_expiry(db_path: str, cfg: dict) -> float:
    """Compute options expiry risk.

    See docs/sub-specs/SS-13.md §4.5
    """
    rows = query(
        db_path,
        "SELECT expiry, SUM(call_oi + put_oi) as total_oi FROM options_oi GROUP BY expiry",
    )
    if not rows:
        return 0.0

    now = datetime.now(timezone.utc)
    threshold_24h = cfg["expiry_24h_btc_threshold"]
    threshold_48h = cfg["expiry_48h_btc_threshold"]

    max_risk = 0.0
    for row in rows:
        expiry_str = row.get("expiry", "")
        total_oi = row.get("total_oi", 0) or 0
        try:
            if "-" in expiry_str and len(expiry_str) == 10:
                exp_dt = datetime.strptime(expiry_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                exp_dt = datetime.strptime(expiry_str, "%d%b%y").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        hours_until = (exp_dt - now).total_seconds() / 3600
        if hours_until < 0:
            continue

        if hours_until < 24 and total_oi > threshold_24h:
            max_risk = max(max_risk, 0.8)
        elif hours_until < 48 and total_oi > threshold_48h:
            max_risk = max(max_risk, 0.4)

    return max_risk


def _risk_liquidation(db_path: str, cfg: dict) -> float:
    """Compute liquidation cascade risk.

    See docs/sub-specs/SS-13.md §4.5
    """
    rows = get_latest(db_path, "futures_liquidations", n=1, order_col="timestamp")
    if not rows:
        return 0.0

    total_liq = rows[0].get("total_liq_usd", 0) or 0
    if total_liq > cfg["liq_extreme_usd"]:
        return 0.9
    if total_liq > cfg["liq_high_usd"]:
        return 0.5
    if total_liq > cfg["liq_medium_usd"]:
        return 0.2
    return 0.0


def _risk_gamma_flip(spot: float, gamma_flip: float | None, cfg: dict) -> float:
    """Compute gamma flip proximity risk using linear interpolation.

    See docs/sub-specs/SS-13.md §4.5

    Linear: within close_pct (0.5%) → 0.5, fades to 0 at near_pct (2%).
    Less aggressive than the old step function — proximity is a caution,
    not a prohibition.
    """
    if gamma_flip is None or spot == 0:
        return 0.0

    distance_pct = abs((spot - gamma_flip) / spot * 100)
    close = cfg["gamma_flip_close_pct"]
    near = cfg["gamma_flip_near_pct"]

    if distance_pct < close:
        return 0.5
    if distance_pct < near:
        # Linear fade from 0.5 → 0 between close and near
        t = (distance_pct - close) / (near - close)
        return 0.5 * (1 - t)
    return 0.0


def _risk_dvol(db_path: str, cfg: dict) -> float:
    """Compute implied volatility risk from DVol.

    See docs/sub-specs/SS-13.md §4.5
    """
    rows = get_latest(db_path, "daily_snapshot", n=1, order_col="date")
    if not rows:
        return 0.0

    dvol = rows[0].get("dvol", 0) or 0
    if dvol > cfg["dvol_extreme"]:
        return 0.8
    if dvol > cfg["dvol_high"]:
        return 0.4
    if dvol > cfg["dvol_moderate"]:
        return 0.1
    return 0.0


def _risk_macro(db_path: str) -> float:
    """Compute macro event proximity risk.

    See docs/sub-specs/SS-13.md §4.5

    RSS-sourced events are downgraded by 1 tier (RSS T1 → treated as T2)
    because the headline classifier is often too aggressive.
    Only static/calendar T1 events get full risk weight.
    """
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=2)).strftime("%Y-%m-%d")
    rows = query(
        db_path,
        "SELECT date, time_utc, event, tier, source FROM macro_events WHERE date >= ? AND date <= ?",
        (today, tomorrow),
    )
    if not rows:
        return 0.0

    max_risk = 0.0
    for row in rows:
        try:
            event_dt = datetime.strptime(
                f"{row['date']}T{row['time_utc']}", "%Y-%m-%dT%H:%M"
            ).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        hours_until = (event_dt - now).total_seconds() / 3600
        if hours_until < -1 or hours_until > 24:
            continue

        tier = row.get("tier", 3)
        source = row.get("source", "static")

        # Downgrade RSS events by 1 tier — classifier is too aggressive
        if source == "rss":
            tier = min(tier + 1, 4)

        if tier == 1:
            if hours_until < 2:
                max_risk = max(max_risk, 0.95)
            elif hours_until < 6:
                max_risk = max(max_risk, 0.50)
            else:
                max_risk = max(max_risk, 0.20)
        elif tier == 2:
            if hours_until < 2:
                max_risk = max(max_risk, 0.40)
            elif hours_until < 4:
                max_risk = max(max_risk, 0.15)
        # tier 3+ ignored for risk

    return max_risk


def compute_event_risk(
    db_path: str, config: dict, spot: float = 0.0,
    gamma_flip: float | None = None,
) -> float:
    """Compute Signal 5: Event Risk.

    See docs/sub-specs/SS-13.md §4.5

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        spot: Current spot price.
        gamma_flip: Gamma flip price from SS-07 (or None).

    Returns:
        Event risk in [0, 1.0]. Returns 0.0 on failure.
    """
    try:
        cfg = config["event_risk"]

        r1 = _risk_options_expiry(db_path, cfg)
        r2 = _risk_liquidation(db_path, cfg)
        r3 = _risk_gamma_flip(spot, gamma_flip, cfg)
        r4 = _risk_dvol(db_path, cfg)
        r5 = _risk_macro(db_path)

        # Weighted blend: dampens isolated high-risk sources.
        # Only active (>0) risks contribute to the average.
        risks = [r1, r2, r3, r4, r5]
        peak = max(risks)
        active = [r for r in risks if r > 0]
        avg = sum(active) / len(active) if active else 0.0
        final = 0.6 * avg + 0.4 * peak

        logger.info(
            "Event Risk: %.2f (expiry=%.2f liq=%.2f gamma=%.2f dvol=%.2f macro=%.2f peak=%.2f avg=%.2f)",
            final, r1, r2, r3, r4, r5, peak, avg,
        )
        return final
    except Exception as e:
        logger.error("Event Risk signal failed: %s", e)
        return 0.0
