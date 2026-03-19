"""Trade plan generator — entry gates, sizing, stops, take-profits.

See docs/sub-specs/SS-16.md §7
"""

import logging
from datetime import datetime, timezone
from typing import Any

from custom.utils.db import insert_row

logger = logging.getLogger(__name__)


def check_entry_gate(
    signal: dict[str, Any], zones: list[dict[str, Any]], config: dict
) -> dict[str, Any]:
    """Validate entry decision gates.

    See docs/sub-specs/SS-16.md §7.3

    Gate 1: strength != WEAK and confidence != LOW
    Gate 2: nearest confluence zone exists
    Gate 3: informational — confirmations available

    Args:
        signal: Signal dict from engine.
        zones: Confluence zones list.
        config: Full settings dict.

    Returns:
        Dict with passed (bool), gate (str), reason (str).
    """
    tp_cfg = config.get("trade_plan", {})
    min_strength = tp_cfg.get("entry_min_signal_strength", "MODERATE")
    min_confidence = tp_cfg.get("entry_min_confidence", "MEDIUM")

    strength = signal.get("strength", "NEUTRAL")
    confidence = signal.get("confidence", "LOW")

    reject_strengths = {"NEUTRAL", "WEAK"} if min_strength == "MODERATE" else {"NEUTRAL"}
    reject_confidences = {"LOW"} if min_confidence == "MEDIUM" else set()

    # Gate 1: Signal quality
    if strength in reject_strengths:
        return {"passed": False, "gate": "GATE_1", "reason": f"Strength {strength} below minimum"}
    if confidence in reject_confidences:
        return {"passed": False, "gate": "GATE_1", "reason": f"Confidence {confidence} below minimum"}

    # Gate 2: Confluence zone exists
    if not zones:
        return {"passed": False, "gate": "GATE_2", "reason": "No confluence zones found"}

    return {"passed": True, "gate": "GATE_3", "reason": "Entry gates passed"}


def compute_position_size(
    portfolio_usd: float,
    signal: dict[str, Any],
    stop_distance_pct: float,
    config: dict,
) -> dict[str, float]:
    """Calculate position size using fixed fractional risk model.

    See docs/sub-specs/SS-16.md §7.4

    Args:
        portfolio_usd: Total portfolio value in USD.
        signal: Signal dict with strength and confidence.
        stop_distance_pct: Stop distance as percentage of entry price.
        config: Full settings dict.

    Returns:
        Dict with risk_pct, risk_usd, position_size_usd, leverage.
    """
    tp_cfg = config.get("trade_plan", {})
    max_risk = tp_cfg.get("max_risk_per_trade_pct", 2.0)
    max_leverage = tp_cfg.get("max_leverage", 3)

    strength = signal.get("strength", "NEUTRAL")
    confidence = signal.get("confidence", "LOW")

    # Risk allocation by quality
    if confidence == "HIGH" and strength == "STRONG":
        risk_pct = tp_cfg.get("high_confidence_strong_risk", 2.0)
    elif confidence == "HIGH" or strength == "STRONG":
        risk_pct = tp_cfg.get("high_or_strong_risk", 1.5)
    elif confidence == "MEDIUM":
        risk_pct = tp_cfg.get("medium_confidence_risk", 1.0)
    else:
        risk_pct = tp_cfg.get("low_confidence_risk", 0.5)

    # IMMUTABLE: cap risk
    risk_pct = min(risk_pct, max_risk)
    risk_usd = portfolio_usd * risk_pct / 100.0

    # Position size = risk_amount / stop_distance
    if stop_distance_pct <= 0:
        return {"risk_pct": risk_pct, "risk_usd": risk_usd, "position_size_usd": 0.0, "leverage": 0.0}

    position_size_usd = risk_usd / (stop_distance_pct / 100.0)

    # IMMUTABLE: leverage cap
    leverage = position_size_usd / portfolio_usd if portfolio_usd > 0 else 0.0
    if leverage > max_leverage:
        position_size_usd = portfolio_usd * max_leverage
        leverage = float(max_leverage)

    return {
        "risk_pct": risk_pct,
        "risk_usd": risk_usd,
        "position_size_usd": position_size_usd,
        "leverage": leverage,
    }


def compute_stop_loss(
    direction: str, zones: list[dict[str, Any]], spot: float, config: dict
) -> float:
    """Place stop loss below/above nearest support/resistance zone + buffer.

    See docs/sub-specs/SS-16.md §7.5

    Args:
        direction: "LONG" or "SHORT".
        zones: Confluence zones list.
        spot: Current spot price.
        config: Full settings dict.

    Returns:
        Stop loss price.
    """
    tp_cfg = config.get("trade_plan", {})
    buffer_pct = tp_cfg.get("stop_loss_buffer_pct", 0.3)

    if direction == "LONG":
        # Find nearest support zone below spot
        support_zones = [z for z in zones if z.get("type") == "support" and z["center"] < spot]
        if support_zones:
            nearest = max(support_zones, key=lambda z: z["center"])
            return nearest["center"] * (1 - buffer_pct / 100.0)
        # Fallback: 2% below spot
        return spot * 0.98
    else:
        # Find nearest resistance zone above spot
        resistance_zones = [z for z in zones if z.get("type") == "resistance" and z["center"] > spot]
        if resistance_zones:
            nearest = min(resistance_zones, key=lambda z: z["center"])
            return nearest["center"] * (1 + buffer_pct / 100.0)
        # Fallback: 2% above spot
        return spot * 1.02


def compute_take_profits(
    direction: str,
    entry: float,
    stop: float,
    zones: list[dict[str, Any]],
    config: dict,
) -> dict[str, float | None]:
    """Compute scaled take-profit levels.

    See docs/sub-specs/SS-16.md §7.5

    TP1: 50% at nearest target zone (min 1.5R)
    TP2: 30% at next target zone (target 2–3R)
    TP3: 20% trailing stop

    Args:
        direction: "LONG" or "SHORT".
        entry: Entry price.
        stop: Stop loss price.
        zones: Confluence zones list.
        config: Full settings dict.

    Returns:
        Dict with tp1, tp2, tp3 prices.
    """
    tp_cfg = config.get("trade_plan", {})
    min_rr = tp_cfg.get("min_reward_risk_ratio", 1.5)
    trailing_pct = tp_cfg.get("trailing_stop_pct", 2.0)

    risk = abs(entry - stop)
    if risk <= 0:
        return {"tp1": None, "tp2": None, "tp3": None}

    if direction == "LONG":
        # Target zones above entry
        targets = sorted(
            [z for z in zones if z.get("type") == "resistance" and z["center"] > entry],
            key=lambda z: z["center"],
        )
        min_tp1 = entry + risk * min_rr

        tp1 = targets[0]["center"] if targets and targets[0]["center"] >= min_tp1 else min_tp1
        tp2 = targets[1]["center"] if len(targets) > 1 else entry + risk * 2.5
        # TP3: trailing stop reference — trail starts below the highest price reached
        tp3_trailing = entry + risk * 3.5
    else:
        # Target zones below entry
        targets = sorted(
            [z for z in zones if z.get("type") == "support" and z["center"] < entry],
            key=lambda z: z["center"],
            reverse=True,
        )
        min_tp1 = entry - risk * min_rr

        tp1 = targets[0]["center"] if targets and targets[0]["center"] <= min_tp1 else min_tp1
        tp2 = targets[1]["center"] if len(targets) > 1 else entry - risk * 2.5
        # TP3: trailing stop reference — trail starts above the lowest price reached
        tp3_trailing = entry - risk * 3.5

    return {"tp1": tp1, "tp2": tp2, "tp3": tp3_trailing}


def generate_trade_plan(
    signal: dict[str, Any],
    zones: list[dict[str, Any]],
    spot: float,
    portfolio_usd: float,
    config: dict,
) -> dict[str, Any] | None:
    """Generate a complete trade plan from signal and confluence zones.

    See docs/sub-specs/SS-16.md §7

    Args:
        signal: Signal dict from engine.
        zones: Confluence zones from SS-08.
        spot: Current spot price.
        portfolio_usd: Total portfolio value.
        config: Full settings dict.

    Returns:
        Trade plan dict, or None if entry gate fails.
    """
    try:
        # Entry gates
        gate = check_entry_gate(signal, zones, config)
        if not gate["passed"]:
            logger.info("Entry gate failed: %s — %s", gate["gate"], gate["reason"])
            return None

        direction = signal.get("bias", "LONG")

        # Stop loss
        stop = compute_stop_loss(direction, zones, spot, config)
        stop_distance_pct = abs(spot - stop) / spot * 100.0

        # Position sizing
        sizing = compute_position_size(portfolio_usd, signal, stop_distance_pct, config)

        # Take profits
        tps = compute_take_profits(direction, spot, stop, zones, config)

        tp_cfg = config.get("trade_plan", {})
        plan = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "direction": direction,
            "entry_price": spot,
            "stop_loss": stop,
            "tp1": tps["tp1"],
            "tp2": tps["tp2"],
            "tp3": tps["tp3"],
            "position_size_usd": sizing["position_size_usd"],
            "risk_pct": sizing["risk_pct"],
            "leverage": sizing["leverage"],
            "signal_strength": signal.get("strength"),
            "signal_confidence": signal.get("confidence"),
            "final_score": signal.get("final_score", 0.0),
            "tp1_pct": tp_cfg.get("tp1_position_pct", 50),
            "tp2_pct": tp_cfg.get("tp2_position_pct", 30),
            "tp3_pct": tp_cfg.get("tp3_position_pct", 20),
        }

        logger.info(
            "Trade plan: %s entry=%.0f stop=%.0f tp1=%.0f risk=%.1f%%",
            direction, spot, stop, tps.get("tp1") or 0, sizing["risk_pct"],
        )
        return plan

    except Exception as e:
        logger.error("Trade plan generation failed: %s", e)
        return None


def store_trade_plan(db_path: str, plan: dict[str, Any], signal_id: int | None = None) -> None:
    """Write a trade plan to the trades table.

    See docs/sub-specs/SS-16.md §7

    Args:
        db_path: Path to SQLite database.
        plan: Trade plan dict from generate_trade_plan().
        signal_id: Optional signal ID to link.
    """
    insert_row(db_path, "trades", {
        "signal_id": signal_id,
        "entry_timestamp": plan.get("timestamp"),
        "direction": plan.get("direction"),
        "entry_price": plan.get("entry_price"),
        "stop_loss": plan.get("stop_loss"),
        "tp1": plan.get("tp1"),
        "tp2": plan.get("tp2"),
        "tp3": plan.get("tp3"),
        "position_size_usd": plan.get("position_size_usd"),
        "risk_pct": plan.get("risk_pct"),
    })
    logger.info("Stored trade plan for %s at %.0f", plan.get("direction"), plan.get("entry_price", 0))
