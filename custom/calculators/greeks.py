"""Black-Scholes Greeks, GEX, gamma flip, max pain, and IV skew calculators.

See docs/sub-specs/SS-07.md §3.4, §4.3
"""

import logging
from datetime import datetime, timezone
from typing import Any

from py_vollib.black_scholes.greeks.analytical import delta as bs_delta
from py_vollib.black_scholes.greeks.analytical import gamma as bs_gamma

from custom.utils.db import insert_row

logger = logging.getLogger(__name__)


def compute_greeks(
    spot: float, strike: float, T: float, r: float, iv: float, option_type: str
) -> dict[str, float]:
    """Compute delta and gamma using Black-Scholes.

    See docs/sub-specs/SS-07.md §3.4

    Args:
        spot: Current spot price.
        strike: Option strike price.
        T: Time to expiry in years.
        r: Risk-free rate.
        iv: Implied volatility as decimal (e.g. 0.65).
        option_type: "call" or "put".

    Returns:
        Dict with delta and gamma. Zeros on invalid input.
    """
    if T <= 0 or iv <= 0:
        return {"delta": 0.0, "gamma": 0.0}
    flag = "c" if option_type == "call" else "p"
    try:
        d = bs_delta(flag, spot, strike, T, r, iv)
        g = bs_gamma(flag, spot, strike, T, r, iv)
        return {"delta": float(d), "gamma": float(g)}
    except (ValueError, ZeroDivisionError, OverflowError) as e:
        logger.warning("Greeks calc failed (S=%.0f K=%.0f T=%.4f iv=%.4f): %s", spot, strike, T, iv, e)
        return {"delta": 0.0, "gamma": 0.0}


def compute_gex(
    options_chain: list[dict[str, Any]], spot: float
) -> list[dict[str, float]]:
    """Compute Gamma Exposure per strike.

    See docs/sub-specs/SS-07.md §4.3

    Formula per strike:
        call_gex = gamma × call_OI × spot² × 0.01
        put_gex  = gamma × put_OI × spot² × 0.01 × (-1)
        net_gex  = call_gex + put_gex

    Args:
        options_chain: List of options_oi rows from SS-04.
        spot: Current spot price.

    Returns:
        List of dicts with strike, call_gex, put_gex, net_gex.
    """
    results: dict[float, dict[str, float]] = {}
    spot_sq = spot * spot * 0.01

    for row in options_chain:
        strike = row.get("strike")
        if strike is None:
            continue

        expiry = row.get("expiry", "")
        T = _expiry_to_years(expiry)
        if T <= 0:
            continue

        call_iv = row.get("call_iv")
        put_iv = row.get("put_iv")
        call_oi = row.get("call_oi") or 0.0
        put_oi = row.get("put_oi") or 0.0

        call_gex = 0.0
        if call_iv and call_iv > 0 and call_oi > 0:
            greeks = compute_greeks(spot, strike, T, 0.0, call_iv, "call")
            call_gex = greeks["gamma"] * call_oi * spot_sq

        put_gex = 0.0
        if put_iv and put_iv > 0 and put_oi > 0:
            greeks = compute_greeks(spot, strike, T, 0.0, put_iv, "put")
            put_gex = greeks["gamma"] * put_oi * spot_sq * (-1)

        if strike in results:
            results[strike]["call_gex"] += call_gex
            results[strike]["put_gex"] += put_gex
            results[strike]["net_gex"] += call_gex + put_gex
        else:
            results[strike] = {
                "strike": strike,
                "call_gex": call_gex,
                "put_gex": put_gex,
                "net_gex": call_gex + put_gex,
            }

    gex_list = sorted(results.values(), key=lambda x: x["strike"])
    logger.info("Computed GEX for %d strikes", len(gex_list))
    return gex_list


def find_gamma_flip(gex_results: list[dict[str, float]]) -> float | None:
    """Find the gamma flip point where cumulative net GEX changes sign.

    See docs/sub-specs/SS-07.md §4.3

    Args:
        gex_results: Output of compute_gex(), sorted by strike.

    Returns:
        Gamma flip strike price, or None if no sign change.
    """
    if not gex_results:
        return None

    sorted_gex = sorted(gex_results, key=lambda x: x["strike"])
    cumulative = 0.0
    prev_sign = None

    for item in sorted_gex:
        cumulative += item["net_gex"]
        current_sign = cumulative >= 0
        if prev_sign is not None and current_sign != prev_sign:
            return item["strike"]
        prev_sign = current_sign

    return None


def compute_max_pain(options_chain: list[dict[str, Any]]) -> float | None:
    """Compute max pain strike that minimizes total intrinsic value pain.

    See docs/sub-specs/SS-07.md §3.4

    Formula: pain(K) = Σ call_OI × max(0, K - strike_i) + Σ put_OI × max(0, strike_i - K)
    Max pain = K with lowest pain.

    Args:
        options_chain: List of options_oi rows.

    Returns:
        Max pain strike price, or None if chain is empty.
    """
    if not options_chain:
        return None

    strikes_data: list[tuple[float, float, float]] = []
    for row in options_chain:
        strike = row.get("strike")
        if strike is None:
            continue
        call_oi = row.get("call_oi") or 0.0
        put_oi = row.get("put_oi") or 0.0
        strikes_data.append((strike, call_oi, put_oi))

    if not strikes_data:
        return None

    unique_strikes = sorted(set(s for s, _, _ in strikes_data))
    min_pain = float("inf")
    max_pain_strike = unique_strikes[0]

    for K in unique_strikes:
        pain = 0.0
        for strike_i, call_oi, put_oi in strikes_data:
            pain += call_oi * max(0.0, K - strike_i)
            pain += put_oi * max(0.0, strike_i - K)
        if pain < min_pain:
            min_pain = pain
            max_pain_strike = K

    logger.debug("Max pain: %.0f (pain=%.2f)", max_pain_strike, min_pain)
    return max_pain_strike


def compute_iv_skew(
    options_chain: list[dict[str, Any]], spot: float
) -> float | None:
    """Compute IV skew as OTM put IV minus OTM call IV (risk reversal).

    See docs/sub-specs/SS-07.md §3.4

    Compares IV of puts ~5% below spot vs calls ~5% above spot.
    Positive skew = more downside fear (put premium > call premium).

    Args:
        options_chain: List of options_oi rows.
        spot: Current spot price.

    Returns:
        Skew value (positive = more downside fear), or None.
    """
    if not options_chain or spot <= 0:
        return None

    # Target OTM strikes: ~5% below spot (put) and ~5% above spot (call)
    put_target = spot * 0.95
    call_target = spot * 1.05

    # Find closest OTM put strike (below spot) with put_iv
    put_candidates = [
        r for r in options_chain
        if r.get("strike") and r["strike"] < spot and r.get("put_iv")
    ]
    # Find closest OTM call strike (above spot) with call_iv
    call_candidates = [
        r for r in options_chain
        if r.get("strike") and r["strike"] > spot and r.get("call_iv")
    ]

    if not put_candidates or not call_candidates:
        logger.warning("IV skew: insufficient OTM options data")
        return None

    otm_put = min(put_candidates, key=lambda r: abs(r["strike"] - put_target))
    otm_call = min(call_candidates, key=lambda r: abs(r["strike"] - call_target))

    put_iv = otm_put["put_iv"]
    call_iv = otm_call["call_iv"]

    if put_iv is None or call_iv is None:
        return None

    skew = put_iv - call_iv
    logger.debug(
        "IV skew: %.4f (OTM put K=%.0f iv=%.4f, OTM call K=%.0f iv=%.4f)",
        skew, otm_put["strike"], put_iv, otm_call["strike"], call_iv,
    )
    return skew


def store_gex(
    db_path: str, gex_results: list[dict[str, float]], gamma_flip: float | None
) -> int:
    """Write GEX results to gex_data table.

    See docs/sub-specs/SS-07.md §3.4

    Args:
        db_path: Path to SQLite database.
        gex_results: Output of compute_gex().
        gamma_flip: Gamma flip price or None.

    Returns:
        Number of rows written.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    count = 0
    for item in gex_results:
        insert_row(db_path, "gex_data", {
            "date": today,
            "strike": item["strike"],
            "call_gex": item["call_gex"],
            "put_gex": item["put_gex"],
            "net_gex": item["net_gex"],
            "gamma_flip_price": gamma_flip,
        })
        count += 1
    logger.info("Stored %d gex_data rows", count)
    return count


def compute_options_snapshot(
    db_path: str, options_chain: list[dict[str, Any]], spot: float
) -> dict[str, Any]:
    """Orchestrator: compute all options-derived metrics and store GEX.

    See docs/sub-specs/SS-07.md §3.4, §4.3

    Args:
        db_path: Path to SQLite database.
        options_chain: List of options_oi rows from SS-04.
        spot: Current spot price.

    Returns:
        Summary dict with gamma_flip, max_pain, iv_skew, total_net_gex, gex_by_strike.
    """
    gex_results = compute_gex(options_chain, spot)
    gamma_flip = find_gamma_flip(gex_results)
    max_pain = compute_max_pain(options_chain)
    iv_skew = compute_iv_skew(options_chain, spot)

    total_net_gex = sum(item["net_gex"] for item in gex_results)

    store_gex(db_path, gex_results, gamma_flip)

    return {
        "gamma_flip": gamma_flip,
        "max_pain": max_pain,
        "iv_skew": iv_skew,
        "total_net_gex": total_net_gex,
        "gex_by_strike": gex_results,
    }


def _expiry_to_years(expiry: str) -> float:
    """Convert expiry date string to time in years from now.

    Args:
        expiry: Date string in DDMMMYY format (e.g. "28MAR26") or YYYY-MM-DD.

    Returns:
        Time to expiry in years, or 0.0 on parse failure.
    """
    now = datetime.now(timezone.utc)
    try:
        if "-" in expiry:
            exp_dt = datetime.strptime(expiry, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            exp_dt = datetime.strptime(expiry, "%d%b%y").replace(tzinfo=timezone.utc)
        diff = (exp_dt - now).total_seconds()
        return max(diff / (365.25 * 24 * 3600), 0.0)
    except (ValueError, TypeError):
        logger.warning("Could not parse expiry: %s", expiry)
        return 0.0
