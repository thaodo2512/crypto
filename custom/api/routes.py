"""REST API routes for the web dashboard.

See docs/sub-specs/SS-25.md
"""

import logging
from typing import Any

from fastapi import APIRouter, Query

from custom.api.deps import get_config, get_db_path, get_health_monitor, get_scheduler
from custom.evaluation.tracker import (
    compute_component_accuracy,
    compute_regime_accuracy,
    compute_win_rate,
)
from custom.utils.db import get_latest, query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ── Signal endpoints ──────────────────────────────────────


@router.get("/signal/latest")
def signal_latest() -> dict[str, Any]:
    """Get the most recent composite signal."""
    db = get_db_path()
    rows = query(
        db,
        """SELECT timestamp, final_score, bias, strength, confidence,
                  regime, event_risk, consensus,
                  spot_flow, leverage_pos, options_struct, mean_reversion,
                  btc_price_at_signal, weights_json
           FROM signals ORDER BY timestamp DESC LIMIT 1""",
    )
    return rows[0] if rows else {}


@router.get("/signal/history")
def signal_history(days: int = Query(default=30, ge=1, le=365)) -> list[dict[str, Any]]:
    """Get signal history for charts."""
    db = get_db_path()
    return query(
        db,
        f"""SELECT timestamp, final_score, bias, strength, confidence,
                   regime, event_risk, consensus,
                   spot_flow, leverage_pos, options_struct, mean_reversion,
                   btc_price_at_signal, correct
            FROM signals
            WHERE timestamp >= datetime('now', '-{days} days')
            ORDER BY timestamp ASC""",
    )


# ── Price endpoints ───────────────────────────────────────


@router.get("/price/latest")
def price_latest() -> dict[str, Any]:
    """Get latest price tick."""
    db = get_db_path()
    rows = get_latest(db, "spot_price", n=1, order_col="timestamp")
    return rows[0] if rows else {}


@router.get("/price/ohlcv")
def price_ohlcv(days: int = Query(default=7, ge=1, le=365)) -> list[dict[str, Any]]:
    """Get OHLCV candlestick data (one per hour)."""
    db = get_db_path()
    return query(
        db,
        f"""SELECT timestamp, open, high, low, close, volume
            FROM spot_price
            WHERE timestamp >= datetime('now', '-{days} days')
              AND id IN (
                  SELECT MAX(id) FROM spot_price
                  WHERE timestamp >= datetime('now', '-{days} days')
                  GROUP BY timestamp
              )
            ORDER BY timestamp ASC""",
    )


# ── Options endpoints ─────────────────────────────────────


@router.get("/options/gex")
def options_gex() -> list[dict[str, Any]]:
    """Get latest GEX data by strike."""
    db = get_db_path()
    return query(
        db,
        """SELECT date, strike, call_gex, put_gex, net_gex, gamma_flip_price
           FROM gex_data
           WHERE date = (SELECT MAX(date) FROM gex_data)
           ORDER BY strike ASC""",
    )


@router.get("/options/oi")
def options_oi() -> list[dict[str, Any]]:
    """Get latest options open interest data."""
    db = get_db_path()
    return query(
        db,
        """SELECT date, expiry, strike, call_oi, put_oi, call_iv, put_iv
           FROM options_oi
           WHERE date = (SELECT MAX(date) FROM options_oi)
           ORDER BY strike ASC""",
    )


# ── Futures endpoints ─────────────────────────────────────


@router.get("/futures/history")
def futures_history(days: int = Query(default=7, ge=1, le=365)) -> list[dict[str, Any]]:
    """Get futures snapshot history."""
    db = get_db_path()
    return query(
        db,
        f"""SELECT timestamp, funding_binance, funding_bybit, funding_okx,
                   funding_weighted_avg,
                   oi_total_usd, basis_pct,
                   top_trader_ls_ratio, global_ls_ratio,
                   taker_buy_sell_ratio
            FROM futures_snapshot
            WHERE timestamp >= datetime('now', '-{days} days')
            ORDER BY timestamp ASC""",
    )


@router.get("/futures/latest")
def futures_latest() -> dict[str, Any]:
    """Get latest futures snapshot."""
    db = get_db_path()
    rows = get_latest(db, "futures_snapshot", n=1, order_col="timestamp")
    return rows[0] if rows else {}


# ── Levels endpoints ──────────────────────────────────────


@router.get("/levels/confluence")
def confluence_zones() -> list[dict[str, Any]]:
    """Get latest confluence support/resistance zones."""
    db = get_db_path()
    return query(
        db,
        """SELECT date, level_price, level_type, strength, components
           FROM level_outcomes
           WHERE date = (SELECT MAX(date) FROM level_outcomes)
           ORDER BY level_price ASC""",
    )


# ── Performance endpoints ─────────────────────────────────


@router.get("/performance")
def performance(days: int = Query(default=30, ge=1, le=365)) -> dict[str, Any]:
    """Get performance metrics (win rate, component accuracy, regime accuracy)."""
    db = get_db_path()
    return {
        "win_rate": compute_win_rate(db, days=days),
        "component_accuracy": compute_component_accuracy(db, days=days),
        "regime_accuracy": compute_regime_accuracy(db, days=days),
    }


# ── System endpoints ──────────────────────────────────────


@router.get("/health")
def health() -> dict[str, Any]:
    """Get system health status."""
    hm = get_health_monitor()
    if hm is None:
        return {"status": "unknown", "message": "health monitor not initialized"}
    return hm.get_health_report()


@router.get("/scheduler/jobs")
def scheduler_jobs() -> dict[str, Any]:
    """Get scheduler job stats."""
    sched = get_scheduler()
    if sched is None:
        return {}
    return sched.get_job_stats()


@router.get("/daily-snapshot")
def daily_snapshot() -> dict[str, Any]:
    """Get latest daily snapshot (F&G, DVol, regime, etc.)."""
    db = get_db_path()
    rows = get_latest(db, "daily_snapshot", n=1, order_col="date")
    return rows[0] if rows else {}


@router.get("/technicals")
def technicals() -> dict[str, Any]:
    """Get latest technical indicators."""
    db = get_db_path()
    rows = get_latest(db, "spot_technicals", n=1, order_col="date")
    return rows[0] if rows else {}
