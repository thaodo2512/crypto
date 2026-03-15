"""Trade lifecycle manager — open, monitor, close trades.

Manages the state machine: signal → open trade → monitor SL/TP → close trade.
Only one trade open at a time. Checks run every 2 minutes via the alert job.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from custom.utils.db import insert_row, query, update_row

logger = logging.getLogger(__name__)


def get_open_trade(db_path: str) -> dict[str, Any] | None:
    """Get the currently open trade (exit_timestamp IS NULL).

    Returns:
        Trade dict, or None if no open trade.
    """
    rows = query(
        db_path,
        "SELECT * FROM trades WHERE exit_timestamp IS NULL "
        "ORDER BY entry_timestamp DESC LIMIT 1",
    )
    return rows[0] if rows else None


def open_trade(
    db_path: str,
    plan: dict[str, Any],
    signal_result: dict[str, Any],
) -> dict[str, Any] | None:
    """Open a new trade from a trade plan. Closes any opposing open trade first.

    Args:
        db_path: Path to SQLite database.
        plan: Trade plan dict from generate_trade_plan().
        signal_result: Signal dict from compute_final_signal().

    Returns:
        Event dict describing what happened, or None if skipped.
    """
    existing = get_open_trade(db_path)
    new_direction = plan["direction"]
    events: list[dict[str, Any]] = []

    if existing:
        # Same direction — don't stack trades
        if existing["direction"] == new_direction:
            logger.info("Trade already open in same direction (%s), skipping", new_direction)
            return None

        # Opposing direction — close existing as signal reversal
        current_price = plan["entry_price"]
        close_event = close_trade(db_path, existing["id"], current_price, "signal_reversal")
        events.append(close_event)

    # Get signal_id from the most recent signal
    sig_rows = query(
        db_path,
        "SELECT id FROM signals ORDER BY id DESC LIMIT 1",
    )
    signal_id = sig_rows[0]["id"] if sig_rows else None

    trade_id = insert_row(db_path, "trades", {
        "signal_id": signal_id,
        "entry_timestamp": plan["timestamp"],
        "direction": new_direction,
        "entry_price": plan["entry_price"],
        "stop_loss": plan["stop_loss"],
        "tp1": plan["tp1"],
        "tp2": plan["tp2"],
        "tp3": plan["tp3"],
        "position_size_usd": plan["position_size_usd"],
        "risk_pct": plan["risk_pct"],
        "tp1_hit": 0,
    })

    open_event = {
        "type": "trade_opened",
        "trade_id": trade_id,
        "direction": new_direction,
        "entry_price": plan["entry_price"],
        "stop_loss": plan["stop_loss"],
        "tp1": plan["tp1"],
        "tp2": plan["tp2"],
        "tp3": plan["tp3"],
        "risk_pct": plan["risk_pct"],
    }

    logger.info(
        "Trade opened: %s @ $%.0f, SL=$%.0f, TP1=$%.0f",
        new_direction, plan["entry_price"], plan["stop_loss"], plan["tp1"],
    )

    if events:
        return {"type": "reversal_and_open", "closed": events[0], "opened": open_event}
    return open_event


def close_trade(
    db_path: str,
    trade_id: int,
    exit_price: float,
    exit_reason: str,
) -> dict[str, Any]:
    """Close an open trade and calculate PnL.

    Args:
        db_path: Path to SQLite database.
        trade_id: ID of the trade to close.
        exit_price: Price at which the trade exits.
        exit_reason: One of "sl_hit", "tp1_hit", "tp2_hit", "tp3_hit",
                     "time_stop", "signal_reversal".

    Returns:
        Event dict with trade summary.
    """
    rows = query(db_path, "SELECT * FROM trades WHERE id = ?", (trade_id,))
    if not rows:
        logger.error("Cannot close trade %d: not found", trade_id)
        return {"type": "error", "message": f"Trade {trade_id} not found"}

    trade = rows[0]
    entry = trade["entry_price"]
    direction = trade["direction"]
    position_usd = trade["position_size_usd"] or 0

    # PnL calculation
    if direction == "LONG":
        pnl_pct = (exit_price - entry) / entry * 100
    else:
        pnl_pct = (entry - exit_price) / entry * 100

    pnl_usd = pnl_pct / 100 * position_usd

    # R-multiple: (profit or loss) / risk
    sl = trade["stop_loss"]
    risk_per_unit = abs(entry - sl) if sl else 0
    if risk_per_unit > 0:
        if direction == "LONG":
            r_multiple = (exit_price - entry) / risk_per_unit
        else:
            r_multiple = (entry - exit_price) / risk_per_unit
    else:
        r_multiple = 0.0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    update_row(db_path, "trades", {
        "exit_timestamp": now,
        "exit_price": exit_price,
        "pnl_usd": round(pnl_usd, 2),
        "pnl_pct": round(pnl_pct, 4),
        "r_multiple": round(r_multiple, 2),
        "exit_reason": exit_reason,
    }, "id = ?", (trade_id,))

    logger.info(
        "Trade closed: %s @ $%.0f → $%.0f, PnL=%.2f%%, R=%.2f, reason=%s",
        direction, entry, exit_price, pnl_pct, r_multiple, exit_reason,
    )

    return {
        "type": exit_reason,
        "trade_id": trade_id,
        "direction": direction,
        "entry_price": entry,
        "exit_price": exit_price,
        "pnl_pct": round(pnl_pct, 2),
        "pnl_usd": round(pnl_usd, 2),
        "r_multiple": round(r_multiple, 2),
    }


def check_trade_levels(db_path: str, current_price: float) -> list[dict[str, Any]]:
    """Check open trade against SL/TP levels and time stop.

    Called every 2 minutes by the alert job.

    Args:
        db_path: Path to SQLite database.
        current_price: Current BTC spot price.

    Returns:
        List of events (may be empty). Each event has a "type" key.
    """
    trade = get_open_trade(db_path)
    if not trade:
        return []

    events: list[dict[str, Any]] = []
    direction = trade["direction"]
    sl = trade["stop_loss"]
    tp1 = trade["tp1"]
    tp2 = trade["tp2"]
    tp3 = trade["tp3"]
    tp1_already_hit = trade.get("tp1_hit", 0) == 1

    # Time stop: 48 hours
    try:
        entry_dt = datetime.fromisoformat(
            trade["entry_timestamp"].replace("Z", "+00:00")
        )
        age_hours = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 3600
    except (ValueError, TypeError, AttributeError):
        age_hours = 0

    if age_hours >= 48:
        event = close_trade(db_path, trade["id"], current_price, "time_stop")
        events.append(event)
        return events

    if direction == "LONG":
        # SL check (highest priority)
        if sl and current_price <= sl:
            event = close_trade(db_path, trade["id"], current_price, "sl_hit")
            events.append(event)
            return events

        # TP3 check (full exit, best outcome)
        if tp3 and current_price >= tp3:
            event = close_trade(db_path, trade["id"], current_price, "tp3_hit")
            events.append(event)
            return events

        # TP2 check (close trade)
        if tp2 and current_price >= tp2:
            event = close_trade(db_path, trade["id"], current_price, "tp2_hit")
            events.append(event)
            return events

        # TP1 check (partial exit alert, trade stays open)
        if tp1 and current_price >= tp1 and not tp1_already_hit:
            update_row(db_path, "trades", {"tp1_hit": 1}, "id = ?", (trade["id"],))
            events.append({
                "type": "tp1_hit",
                "trade_id": trade["id"],
                "direction": direction,
                "entry_price": trade["entry_price"],
                "tp1_price": tp1,
                "current_price": current_price,
            })
    else:
        # SHORT direction — inverted comparisons
        if sl and current_price >= sl:
            event = close_trade(db_path, trade["id"], current_price, "sl_hit")
            events.append(event)
            return events

        if tp3 and current_price <= tp3:
            event = close_trade(db_path, trade["id"], current_price, "tp3_hit")
            events.append(event)
            return events

        if tp2 and current_price <= tp2:
            event = close_trade(db_path, trade["id"], current_price, "tp2_hit")
            events.append(event)
            return events

        if tp1 and current_price <= tp1 and not tp1_already_hit:
            update_row(db_path, "trades", {"tp1_hit": 1}, "id = ?", (trade["id"],))
            events.append({
                "type": "tp1_hit",
                "trade_id": trade["id"],
                "direction": direction,
                "entry_price": trade["entry_price"],
                "tp1_price": tp1,
                "current_price": current_price,
            })

    return events
