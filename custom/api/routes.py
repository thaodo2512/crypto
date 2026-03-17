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


@router.get("/signal/outcomes")
def signal_outcomes(days: int = Query(default=30, ge=1, le=365)) -> list[dict[str, Any]]:
    """Get signal history with outcome data and trade levels."""
    db = get_db_path()
    return query(
        db,
        f"""SELECT s.timestamp, s.final_score, s.bias, s.strength, s.confidence,
                   s.regime, s.event_risk, s.btc_price_at_signal,
                   s.btc_price_4h_later, s.btc_price_12h_later,
                   s.btc_price_24h_later, s.btc_price_48h_later,
                   s.correct, s.magnitude_24h_pct,
                   s.spot_flow, s.leverage_pos, s.options_struct, s.mean_reversion,
                   t.stop_loss, t.tp1, t.tp2, t.tp3,
                   t.entry_price as trade_entry, t.exit_price as trade_exit,
                   t.exit_reason, t.pnl_pct, t.r_multiple, t.tp1_hit
            FROM signals s
            LEFT JOIN trades t ON t.signal_id = s.id
            WHERE s.timestamp >= datetime('now', '-{days} days')
              AND s.btc_price_at_signal IS NOT NULL
            ORDER BY s.timestamp DESC""",
    )


@router.get("/signal/{signal_ts}/plan")
def signal_trade_plan(signal_ts: str) -> dict[str, Any]:
    """Compute trade plan for a specific signal timestamp (on-the-fly)."""
    db = get_db_path()
    config = get_config()

    rows = query(
        db,
        "SELECT * FROM signals WHERE timestamp = ? LIMIT 1",
        (signal_ts,),
    )
    if not rows:
        return {"error": "Signal not found"}

    signal = rows[0]
    spot = signal.get("btc_price_at_signal", 0)
    if spot <= 0:
        return {"error": "No price data"}

    from custom.calculators.confluence import compute_confluence_zones
    from custom.trade_plan.plan import generate_trade_plan

    zones = compute_confluence_zones(db, config, spot)
    plan = generate_trade_plan(signal, zones, spot, config.get("trade_plan", {}).get("portfolio_usd", 10000), config)
    return plan or {"error": "Entry gates not met"}


# ── Price endpoints ───────────────────────────────────────


@router.get("/price/latest")
def price_latest() -> dict[str, Any]:
    """Get latest price tick."""
    db = get_db_path()
    rows = get_latest(db, "spot_price", n=1, order_col="timestamp")
    return rows[0] if rows else {}


@router.get("/price/klines")
def price_klines(
    interval: str = Query(default="1h", regex="^(1m|5m|15m|30m|1h|4h|1d)$"),
    limit: int = Query(default=200, ge=10, le=1000),
) -> list[dict[str, Any]]:
    """Fetch OHLCV klines from Binance at any timeframe.

    Args:
        interval: Candle interval (1m, 5m, 15m, 30m, 1h, 4h, 1d).
        limit: Number of candles (max 1000).
    """
    import aiohttp
    import asyncio
    from datetime import datetime, timezone

    async def _fetch() -> list[dict[str, Any]]:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "BTCUSDT", "interval": interval, "limit": str(limit)}
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [
                    {
                        "timestamp": datetime.fromtimestamp(
                            c[0] / 1000, tz=timezone.utc
                        ).isoformat(),
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                    }
                    for c in data
                ]

    try:
        return asyncio.run(_fetch())
    except Exception as e:
        logger.error("Klines fetch failed: %s", e)
        return []


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
def options_gex() -> dict[str, Any]:
    """Get latest GEX data by strike (aggregated) with computed gamma flip."""
    db = get_db_path()
    rows = query(
        db,
        """SELECT strike, SUM(call_gex) as call_gex, SUM(put_gex) as put_gex,
                  SUM(net_gex) as net_gex
           FROM gex_data
           WHERE date = (SELECT MAX(date) FROM gex_data)
           GROUP BY strike
           ORDER BY strike ASC""",
    )

    # Compute gamma flip from cumulative net GEX
    gamma_flip = None
    cumulative = 0.0
    prev_sign = None
    for row in rows:
        cumulative += row["net_gex"]
        current_sign = cumulative >= 0
        if prev_sign is not None and current_sign != prev_sign:
            gamma_flip = row["strike"]
        prev_sign = current_sign

    # If no flip today, get the most recent known flip
    if gamma_flip is None:
        flip_rows = query(
            db,
            """SELECT gamma_flip_price FROM gex_data
               WHERE gamma_flip_price IS NOT NULL
               ORDER BY date DESC, id DESC LIMIT 1""",
        )
        if flip_rows:
            gamma_flip = flip_rows[0]["gamma_flip_price"]

    return {
        "strikes": rows,
        "gamma_flip": gamma_flip,
    }


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


@router.get("/events/upcoming")
def events_upcoming(days: int = Query(default=7, ge=1, le=30)) -> list[dict[str, Any]]:
    """Get upcoming macro events."""
    from datetime import datetime, timezone

    db = get_db_path()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = query(
        db,
        """SELECT date, time_utc, event, tier, forecast, actual, previous, source
           FROM macro_events
           WHERE date >= ? AND date <= date(?, '+' || ? || ' days')
           ORDER BY date ASC, time_utc ASC""",
        (today, today, days),
    )
    # Compute hours_until for each event
    now = datetime.now(timezone.utc)
    result = []
    for row in rows:
        try:
            event_dt = datetime.strptime(
                f"{row['date']}T{row['time_utc']}", "%Y-%m-%dT%H:%M"
            ).replace(tzinfo=timezone.utc)
            hours_until = (event_dt - now).total_seconds() / 3600
        except (ValueError, TypeError):
            hours_until = None
        result.append({**row, "hours_until": hours_until})
    return result


@router.get("/risk/breakdown")
def risk_breakdown() -> dict[str, Any]:
    """Get event risk component breakdown from latest signal."""
    from datetime import datetime, timedelta, timezone

    db = get_db_path()
    config = get_config()

    # Get latest price for gamma flip distance
    price_rows = get_latest(db, "spot_price", n=1, order_col="timestamp")
    spot = price_rows[0]["close"] if price_rows else 0.0

    # Get gamma flip from GEX
    gex_rows = query(
        db,
        "SELECT gamma_flip_price FROM gex_data WHERE date = (SELECT MAX(date) FROM gex_data) LIMIT 1",
    )
    gamma_flip = gex_rows[0]["gamma_flip_price"] if gex_rows else None

    # Compute individual risk components
    from custom.signals.event_risk import (
        _risk_options_expiry,
        _risk_liquidation,
        _risk_gamma_flip,
        _risk_dvol,
        _risk_macro,
    )

    cfg = config.get("event_risk", {})
    components = {
        "options_expiry": _risk_options_expiry(db, cfg),
        "liquidation": _risk_liquidation(db, cfg),
        "gamma_flip": _risk_gamma_flip(spot, gamma_flip, cfg),
        "dvol": _risk_dvol(db, cfg),
        "macro": _risk_macro(db),
    }

    risks = list(components.values())
    peak = max(risks) if risks else 0.0
    active = [r for r in risks if r > 0]
    avg = sum(active) / len(active) if active else 0.0
    final = 0.6 * avg + 0.4 * peak

    return {
        "final": round(final, 3),
        "components": {k: round(v, 3) for k, v in components.items()},
    }


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
