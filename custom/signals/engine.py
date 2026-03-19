"""Signal Engine — Final score computation pipeline.

See docs/sub-specs/SS-15.md §6
"""

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np

from custom.utils.db import insert_row

logger = logging.getLogger(__name__)


def compute_raw_score(
    signals: dict[str, float], weights: dict[str, float]
) -> float:
    """Compute weighted sum of 4 directional signals.

    See docs/sub-specs/SS-15.md §6.1 Step 3

    Args:
        signals: Dict with spot_flow, leverage_pos, options_struct, mean_reversion.
        weights: Dict with same keys, values summing to ~1.0.

    Returns:
        Raw score in [-1, +1].
    """
    score = 0.0
    for key in ("spot_flow", "leverage_pos", "options_struct", "mean_reversion"):
        score += signals.get(key, 0.0) * weights.get(key, 0.25)
    return float(np.clip(score, -1.0, 1.0))


def check_consensus(
    signals: dict[str, float], config: dict
) -> tuple[str, float]:
    """Check directional consensus among the 4 signals.

    See docs/sub-specs/SS-15.md §6.1 Step 4

    Args:
        signals: Dict with 4 directional signal scores.
        config: Full settings dict.

    Returns:
        Tuple of (consensus_type, multiplier).
    """
    cfg = config.get("consensus", {})
    bull_thresh = cfg.get("bullish_threshold", 0.15)
    bear_thresh = cfg.get("bearish_threshold", -0.15)

    signal_keys = ("spot_flow", "leverage_pos", "options_struct", "mean_reversion")
    bullish = sum(1 for k in signal_keys if signals.get(k, 0.0) > bull_thresh)
    bearish = sum(1 for k in signal_keys if signals.get(k, 0.0) < bear_thresh)

    if bullish >= 3 or bearish >= 3:
        return "STRONG_CONSENSUS", cfg.get("strong_consensus_multiplier", 1.3)

    if bullish >= 2 and bearish >= 2:
        return "CONFLICT", cfg.get("conflict_multiplier", 0.5)

    if (bullish >= 2 and bearish == 0) or (bearish >= 2 and bullish == 0):
        return "MODERATE_CONSENSUS", cfg.get("moderate_consensus_multiplier", 1.1)

    return "MIXED", cfg.get("mixed_multiplier", 0.8)


def apply_event_risk_penalty(
    score: float, event_risk: float, config: dict
) -> float:
    """Apply smooth event risk confidence penalty to the adjusted score.

    See docs/sub-specs/SS-15.md §6.1 Step 5

    Uses smooth linear decay: penalty = max(min_penalty, 1.0 - event_risk × decay_rate).
    This avoids hard cliffs where a small risk change causes a large score jump.

    Args:
        score: Consensus-adjusted score.
        event_risk: Event risk value in [0, 1].
        config: Full settings dict.

    Returns:
        Penalized final score.
    """
    cfg = config.get("event_risk_penalty", {})
    min_penalty = cfg.get("min_penalty", 0.30)
    decay_rate = cfg.get("decay_rate", 0.70)

    penalty = max(min_penalty, 1.0 - event_risk * decay_rate)

    return float(np.clip(score * penalty, -1.0, 1.0))


def classify_signal(score: float, config: dict) -> tuple[str, str]:
    """Classify the final score into bias and strength.

    See docs/sub-specs/SS-15.md §6.1 Step 6

    Args:
        score: Final score in [-1, +1].
        config: Full settings dict.

    Returns:
        Tuple of (bias, strength). Bias is LONG/SHORT/NEUTRAL.
    """
    cfg = config.get("signal_classification", {})
    no_signal = cfg.get("no_signal_threshold", 0.15)
    weak = cfg.get("weak_threshold", 0.35)
    moderate = cfg.get("moderate_threshold", 0.60)

    abs_score = abs(score)

    if abs_score < no_signal:
        return "NEUTRAL", "NEUTRAL"

    bias = "LONG" if score > 0 else "SHORT"

    if abs_score > moderate:
        return bias, "STRONG"
    if abs_score > weak:
        return bias, "MODERATE"
    return bias, "WEAK"


def compute_confidence(
    consensus_multiplier: float,
    event_risk: float,
    regime: str,
    final_score: float,
    config: dict,
) -> str:
    """Compute confidence level from 4 boolean factors.

    See docs/sub-specs/SS-15.md §6.1 Step 7

    Factors:
        1. consensus_multiplier > 1.0
        2. event_risk < 0.4
        3. regime != TRANSITIONAL
        4. |final_score| > 0.35

    Args:
        consensus_multiplier: From check_consensus().
        event_risk: Event risk value.
        regime: Current regime string.
        final_score: The final penalized score.
        config: Full settings dict.

    Returns:
        Confidence level: HIGH, MEDIUM, or LOW.
    """
    cfg = config.get("confidence", {})
    high_thresh = cfg.get("high_threshold", 0.75)
    medium_thresh = cfg.get("medium_threshold", 0.50)

    factors = [
        consensus_multiplier > 1.0,
        event_risk < 0.4,
        regime != "TRANSITIONAL",
        abs(final_score) > 0.35,
    ]
    ratio = sum(factors) / len(factors)

    if ratio >= high_thresh:
        return "HIGH"
    if ratio >= medium_thresh:
        return "MEDIUM"
    return "LOW"


def store_signal(db_path: str, result: dict[str, Any]) -> None:
    """Write the final signal to the signals table.

    See docs/sub-specs/SS-15.md §6.2

    Args:
        db_path: Path to SQLite database.
        result: Final signal dict from compute_final_signal().
    """
    breakdown = result.get("breakdown", {})
    weights = result.get("weights_used", {})
    import json

    insert_row(db_path, "signals", {
        "timestamp": result.get("timestamp", ""),
        "final_score": result.get("final_score", 0.0),
        "bias": result.get("bias", "NEUTRAL"),
        "strength": result.get("strength", "NEUTRAL"),
        "confidence": result.get("confidence", "LOW"),
        "regime": result.get("regime", "TRANSITIONAL"),
        "event_risk": result.get("event_risk", 0.0),
        "consensus": result.get("consensus", "MIXED"),
        "spot_flow": breakdown.get("spot_flow", 0.0),
        "leverage_pos": breakdown.get("leverage_pos", 0.0),
        "options_struct": breakdown.get("options_struct", 0.0),
        "mean_reversion": breakdown.get("mean_reversion", 0.0),
        "weights_json": json.dumps(weights),
        "btc_price_at_signal": result.get("btc_price", 0.0),
    })
    logger.info("Stored signal: %s %s (%.3f)", result.get("bias"), result.get("strength"), result.get("final_score", 0))


def assemble_signal(
    signals: dict[str, float],
    weights: dict[str, float],
    event_risk: float,
    regime: str,
    btc_price: float,
    config: dict,
) -> dict[str, Any]:
    """Assemble the final signal from pre-computed components.

    See docs/sub-specs/SS-15.md §6.1

    This is the core pipeline: raw score → consensus → event penalty →
    classify → confidence. Separated from data fetching for testability.

    Args:
        signals: Dict with 4 directional signal scores.
        weights: Adaptive weights from regime detection.
        event_risk: Event risk modifier [0, 1].
        regime: Current regime string.
        btc_price: Current BTC price.
        config: Full settings dict.

    Returns:
        Complete signal dict matching §6.2 schema.
    """
    # Step 3: Raw score
    raw_score = compute_raw_score(signals, weights)

    # Step 4: Consensus check
    consensus_type, consensus_mult = check_consensus(signals, config)
    adjusted_score = float(np.clip(raw_score * consensus_mult, -1.0, 1.0))

    # Step 5: Event risk penalty
    final_score = apply_event_risk_penalty(adjusted_score, event_risk, config)

    # Step 6: Classify
    bias, strength = classify_signal(final_score, config)

    # Step 7: Confidence
    confidence = compute_confidence(consensus_mult, event_risk, regime, final_score, config)

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "btc_price": btc_price,
        "final_score": final_score,
        "bias": bias,
        "strength": strength,
        "confidence": confidence,
        "regime": regime,
        "event_risk": event_risk,
        "consensus": consensus_type,
        "breakdown": {
            "spot_flow": signals.get("spot_flow", 0.0),
            "leverage_pos": signals.get("leverage_pos", 0.0),
            "options_struct": signals.get("options_struct", 0.0),
            "mean_reversion": signals.get("mean_reversion", 0.0),
        },
        "weights_used": dict(weights),
    }


def compute_final_signal(
    db_path: str, config: dict, prev_weights: dict[str, float] | None = None,
    has_options: bool = True,
) -> dict[str, Any]:
    """Orchestrator: compute all signals, regime, and final score.

    See docs/sub-specs/SS-15.md §6

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        prev_weights: Previous smoothed weights for regime EMA.
        has_options: Whether this asset has options data. When False,
            options signal is set to 0.0 and its weight redistributed.

    Returns:
        Complete signal dict. Returns neutral on any failure.
    """
    try:
        from custom.regime.regime import compute_regime
        from custom.signals.event_risk import compute_event_risk
        from custom.signals.leverage import compute_leverage
        from custom.signals.mean_reversion import compute_mean_reversion
        from custom.signals.spot_flow import compute_spot_flow
        from custom.utils.db import get_latest

        # Get current price
        price_rows = get_latest(db_path, "spot_price", n=1, order_col="timestamp")
        btc_price = price_rows[0]["close"] if price_rows else 0.0

        # Step 1: Compute signals
        spot_flow = compute_spot_flow(db_path, config)
        leverage_pos = compute_leverage(db_path, config)

        snapshot: dict[str, Any] = {}
        options_struct = 0.0
        if has_options:
            from custom.calculators.greeks import compute_options_snapshot
            from custom.signals.options_signal import compute_options_signal

            options_rows = get_latest(db_path, "options_oi", n=200, order_col="date")
            snapshot = compute_options_snapshot(db_path, list(options_rows), btc_price) if options_rows else {}
            options_struct = compute_options_signal(db_path, config, snapshot, btc_price)

        mean_reversion = compute_mean_reversion(db_path, config)
        event_risk = compute_event_risk(db_path, config, spot=btc_price, gamma_flip=snapshot.get("gamma_flip"))

        signals = {
            "spot_flow": spot_flow,
            "leverage_pos": leverage_pos,
            "options_struct": options_struct,
            "mean_reversion": mean_reversion,
        }

        # Step 2: Regime and adaptive weights
        regime_result = compute_regime(db_path, config, prev_weights)
        regime = regime_result["regime"]
        weights = dict(regime_result["weights"])

        # Redistribute options weight when no options data
        if not has_options:
            opt_w = weights.pop("options_struct", 0.0)
            remaining = ["spot_flow", "leverage_pos", "mean_reversion"]
            total_remaining = sum(weights.get(k, 0.0) for k in remaining)
            if total_remaining > 0:
                for k in remaining:
                    weights[k] = weights.get(k, 0.0) + opt_w * (weights.get(k, 0.0) / total_remaining)
            weights["options_struct"] = 0.0

        # Steps 3-7: Assemble
        result = assemble_signal(signals, weights, event_risk, regime, btc_price, config)
        result["raw_weights"] = regime_result.get("raw_weights", weights)

        # Store
        store_signal(db_path, result)

        return result

    except Exception as e:
        logger.error("Signal engine failed: %s", e)
        return _neutral_signal()


def _neutral_signal() -> dict[str, Any]:
    """Return a neutral fallback signal on failure.

    See docs/sub-specs/SS-15.md §6
    """
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "btc_price": 0.0,
        "final_score": 0.0,
        "bias": "NEUTRAL",
        "strength": "NEUTRAL",
        "confidence": "LOW",
        "regime": "TRANSITIONAL",
        "event_risk": 0.0,
        "consensus": "MIXED",
        "breakdown": {
            "spot_flow": 0.0,
            "leverage_pos": 0.0,
            "options_struct": 0.0,
            "mean_reversion": 0.0,
        },
        "weights_used": {
            "spot_flow": 0.25,
            "leverage_pos": 0.25,
            "options_struct": 0.25,
            "mean_reversion": 0.25,
        },
    }
