"""Tests for trade lifecycle management."""

import pytest

from custom.trade_plan.lifecycle import (
    check_trade_levels,
    close_trade,
    get_open_trade,
    open_trade,
)
from custom.utils.db import insert_row, query


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def plan() -> dict:
    """Sample trade plan."""
    return {
        "timestamp": "2026-03-15T12:00:00Z",
        "direction": "LONG",
        "entry_price": 70000,
        "stop_loss": 68500,
        "tp1": 71500,
        "tp2": 73000,
        "tp3": 75000,
        "position_size_usd": 2000,
        "risk_pct": 1.5,
    }


@pytest.fixture
def signal_result() -> dict:
    """Sample signal result."""
    return {
        "final_score": 0.3,
        "bias": "LONG",
        "strength": "MODERATE",
        "confidence": "MEDIUM",
    }


# ─── TestOpenTrade ───────────────────────────────────────


class TestOpenTrade:
    def test_open_trade(self, db_path, plan, signal_result) -> None:
        """Opens trade and inserts into DB."""
        event = open_trade(db_path, plan, signal_result)

        assert event is not None
        assert event["type"] == "trade_opened"
        assert event["direction"] == "LONG"
        assert event["entry_price"] == 70000

        trade = get_open_trade(db_path)
        assert trade is not None
        assert trade["direction"] == "LONG"
        assert trade["stop_loss"] == 68500
        assert trade["exit_timestamp"] is None

    def test_skip_same_direction(self, db_path, plan, signal_result) -> None:
        """Skips if trade already open in same direction."""
        open_trade(db_path, plan, signal_result)
        event = open_trade(db_path, plan, signal_result)
        assert event is None

        trades = query(db_path, "SELECT * FROM trades")
        assert len(trades) == 1

    def test_reversal_closes_existing(self, db_path, plan, signal_result) -> None:
        """Closes existing trade on opposing direction."""
        open_trade(db_path, plan, signal_result)

        short_plan = {**plan, "direction": "SHORT", "entry_price": 71000,
                      "stop_loss": 72500, "tp1": 69500, "tp2": 68000, "tp3": 66000}
        event = open_trade(db_path, short_plan, signal_result)

        assert event["type"] == "reversal_and_open"
        assert event["closed"]["type"] == "signal_reversal"
        assert event["opened"]["direction"] == "SHORT"

        # Old trade closed, new one open
        trades = query(db_path, "SELECT * FROM trades WHERE exit_timestamp IS NULL")
        assert len(trades) == 1
        assert trades[0]["direction"] == "SHORT"


# ─── TestCloseTrade ──────────────────────────────────────


class TestCloseTrade:
    def test_close_with_profit(self, db_path, plan, signal_result) -> None:
        """Closing a winning LONG trade calculates positive PnL."""
        event = open_trade(db_path, plan, signal_result)
        trade_id = event["trade_id"]

        result = close_trade(db_path, trade_id, 72000, "tp2_hit")

        assert result["type"] == "tp2_hit"
        assert result["pnl_pct"] > 0
        assert result["r_multiple"] > 0

        # Trade should be closed in DB
        trade = query(db_path, "SELECT * FROM trades WHERE id = ?", (trade_id,))
        assert trade[0]["exit_timestamp"] is not None
        assert trade[0]["exit_reason"] == "tp2_hit"

    def test_close_with_loss(self, db_path, plan, signal_result) -> None:
        """Closing at SL calculates negative PnL and ~-1R."""
        event = open_trade(db_path, plan, signal_result)
        trade_id = event["trade_id"]

        result = close_trade(db_path, trade_id, 68500, "sl_hit")

        assert result["pnl_pct"] < 0
        assert abs(result["r_multiple"] - (-1.0)) < 0.01


# ─── TestCheckTradeLevels ────────────────────────────────


class TestCheckTradeLevels:
    def test_sl_hit(self, db_path, plan, signal_result) -> None:
        """SL triggers close."""
        open_trade(db_path, plan, signal_result)
        events = check_trade_levels(db_path, 68000)
        assert len(events) == 1
        assert events[0]["type"] == "sl_hit"
        assert get_open_trade(db_path) is None

    def test_tp1_hit(self, db_path, plan, signal_result) -> None:
        """TP1 sends alert but keeps trade open."""
        open_trade(db_path, plan, signal_result)
        events = check_trade_levels(db_path, 72000)
        assert len(events) == 1
        assert events[0]["type"] == "tp1_hit"
        assert get_open_trade(db_path) is not None

    def test_tp1_not_repeated(self, db_path, plan, signal_result) -> None:
        """TP1 alert only fires once."""
        open_trade(db_path, plan, signal_result)
        check_trade_levels(db_path, 72000)  # First hit
        events = check_trade_levels(db_path, 72000)  # Second check
        assert len(events) == 0

    def test_tp2_closes_trade(self, db_path, plan, signal_result) -> None:
        """TP2 closes the trade."""
        open_trade(db_path, plan, signal_result)
        events = check_trade_levels(db_path, 73500)
        assert len(events) == 1
        assert events[0]["type"] == "tp2_hit"
        assert get_open_trade(db_path) is None

    def test_no_open_trade(self, db_path) -> None:
        """No events when no trade is open."""
        events = check_trade_levels(db_path, 70000)
        assert events == []

    def test_price_in_range(self, db_path, plan, signal_result) -> None:
        """No events when price is between SL and TP1."""
        open_trade(db_path, plan, signal_result)
        events = check_trade_levels(db_path, 70500)
        assert events == []

    def test_short_sl_hit(self, db_path, signal_result) -> None:
        """SHORT trade SL triggers on price going up."""
        short_plan = {
            "timestamp": "2026-03-15T12:00:00Z",
            "direction": "SHORT",
            "entry_price": 70000,
            "stop_loss": 71500,
            "tp1": 68500,
            "tp2": 67000,
            "tp3": 65000,
            "position_size_usd": 2000,
            "risk_pct": 1.5,
        }
        open_trade(db_path, short_plan, signal_result)
        events = check_trade_levels(db_path, 72000)
        assert len(events) == 1
        assert events[0]["type"] == "sl_hit"
