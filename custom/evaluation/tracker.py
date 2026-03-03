"""Evaluation & performance tracking — outcome tracker and reports.

See docs/sub-specs/SS-20.md §16
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from custom.utils.db import get_db, get_latest, query

logger = logging.getLogger(__name__)

HORIZONS = {
    "btc_price_4h_later": timedelta(hours=4),
    "btc_price_12h_later": timedelta(hours=12),
    "btc_price_24h_later": timedelta(hours=24),
    "btc_price_48h_later": timedelta(hours=48),
}


def fill_outcomes(db_path: str) -> int:
    """Fill in actual prices for signals that have matured.

    See docs/sub-specs/SS-20.md §16.1

    Finds signals missing outcome data and fills from price history.

    Args:
        db_path: Path to SQLite database.

    Returns:
        Number of fields updated.
    """
    updates = 0
    try:
        pending = query(
            db_path,
            """SELECT id, timestamp, bias, btc_price_at_signal,
                      btc_price_4h_later, btc_price_12h_later,
                      btc_price_24h_later, btc_price_48h_later
               FROM signals
               WHERE btc_price_48h_later IS NULL
               AND timestamp > datetime('now', '-3 days')""",
        )

        if not pending:
            return 0

        now = datetime.now(timezone.utc)

        for sig in pending:
            sig_time = _parse_timestamp(sig["timestamp"])
            if sig_time is None:
                continue
            elapsed = now - sig_time

            conn = get_db(db_path)
            try:
                for field, horizon in HORIZONS.items():
                    if sig[field] is None and elapsed >= horizon:
                        target_time = sig_time + horizon
                        price = _get_price_at_time(db_path, target_time)
                        if price is not None:
                            conn.execute(
                                f"UPDATE signals SET {field} = ? WHERE id = ?",
                                (price, sig["id"]),
                            )
                            updates += 1

                # Compute correctness once 24h data available
                if sig["btc_price_24h_later"] is None and elapsed >= timedelta(hours=24):
                    price_24h = _get_price_at_time(db_path, sig_time + timedelta(hours=24))
                    if price_24h is not None:
                        correct = evaluate_correctness(
                            sig["bias"], sig["btc_price_at_signal"], price_24h
                        )
                        magnitude = (price_24h - sig["btc_price_at_signal"]) / sig["btc_price_at_signal"] * 100
                        conn.execute(
                            "UPDATE signals SET btc_price_24h_later = ?, correct = ?, magnitude_24h_pct = ? WHERE id = ?",
                            (price_24h, correct, magnitude, sig["id"]),
                        )
                        updates += 1

                conn.commit()
            finally:
                conn.close()

        logger.info("Outcome tracker: %d fields updated", updates)
    except Exception as e:
        logger.error("Outcome tracking failed: %s", e)

    return updates


def evaluate_correctness(bias: str, price_at: float, price_after: float) -> int:
    """Determine if a prediction was correct.

    See docs/sub-specs/SS-20.md §16.1

    Args:
        bias: Signal bias (LONG, SHORT, NEUTRAL).
        price_at: BTC price at signal time.
        price_after: BTC price at horizon.

    Returns:
        1 if correct, 0 if incorrect.
    """
    if price_at <= 0:
        return 0
    if bias == "LONG":
        return 1 if price_after > price_at else 0
    elif bias == "SHORT":
        return 1 if price_after < price_at else 0
    else:  # NEUTRAL
        change_pct = abs(price_after - price_at) / price_at * 100
        return 1 if change_pct < 1.0 else 0


def compute_win_rate(db_path: str, days: int = 30) -> dict[str, Any]:
    """Compute rolling win rate over N days.

    See docs/sub-specs/SS-20.md §16.1

    Args:
        db_path: Path to SQLite database.
        days: Rolling window in days.

    Returns:
        Dict with win_rate, wins, losses, total, insufficient_data flag.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = query(
        db_path,
        "SELECT correct FROM signals WHERE timestamp >= ? AND correct IS NOT NULL",
        (cutoff,),
    )

    total = len(rows)
    if total < 30:
        return {"win_rate": 0.0, "wins": 0, "losses": 0, "total": total, "insufficient_data": True}

    wins = sum(1 for r in rows if r["correct"] == 1)
    losses = total - wins
    return {
        "win_rate": wins / total * 100,
        "wins": wins,
        "losses": losses,
        "total": total,
        "insufficient_data": False,
    }


def compute_component_accuracy(db_path: str, days: int = 30) -> dict[str, float]:
    """Compute per-signal correlation with 24h outcomes.

    See docs/sub-specs/SS-20.md §16.2

    Args:
        db_path: Path to SQLite database.
        days: Rolling window in days.

    Returns:
        Dict mapping signal name to correlation coefficient.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = query(
        db_path,
        """SELECT spot_flow, leverage_pos, options_struct, mean_reversion,
                  magnitude_24h_pct
           FROM signals
           WHERE timestamp >= ? AND magnitude_24h_pct IS NOT NULL""",
        (cutoff,),
    )

    if len(rows) < 30:
        return {"spot_flow": 0.0, "leverage_pos": 0.0, "options_struct": 0.0, "mean_reversion": 0.0}

    outcomes = np.array([r["magnitude_24h_pct"] for r in rows])
    result = {}

    for sig_name in ("spot_flow", "leverage_pos", "options_struct", "mean_reversion"):
        values = np.array([r[sig_name] or 0 for r in rows])
        if np.std(values) == 0 or np.std(outcomes) == 0:
            result[sig_name] = 0.0
        else:
            corr = float(np.corrcoef(values, outcomes)[0, 1])
            result[sig_name] = corr if not np.isnan(corr) else 0.0

    return result


def compute_regime_accuracy(db_path: str, days: int = 30) -> dict[str, dict[str, Any]]:
    """Compute win rate segmented by regime.

    See docs/sub-specs/SS-20.md §16.3

    Args:
        db_path: Path to SQLite database.
        days: Rolling window.

    Returns:
        Dict mapping regime to {win_rate, total} dict.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = query(
        db_path,
        "SELECT regime, correct FROM signals WHERE timestamp >= ? AND correct IS NOT NULL",
        (cutoff,),
    )

    regimes: dict[str, dict[str, int]] = {}
    for r in rows:
        regime = r["regime"] or "UNKNOWN"
        if regime not in regimes:
            regimes[regime] = {"wins": 0, "total": 0}
        regimes[regime]["total"] += 1
        if r["correct"] == 1:
            regimes[regime]["wins"] += 1

    result = {}
    for regime, stats in regimes.items():
        total = stats["total"]
        result[regime] = {
            "win_rate": (stats["wins"] / total * 100) if total > 0 else 0.0,
            "total": total,
            "insufficient_data": total < 15,
        }

    return result


def generate_weekly_report(db_path: str, config: dict) -> str:
    """Generate weekly performance summary.

    See docs/sub-specs/SS-20.md §16.6

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.

    Returns:
        Formatted weekly report string.
    """
    wr = compute_win_rate(db_path, days=7)

    if wr["insufficient_data"] and wr["total"] == 0:
        return "📊 WEEKLY REVIEW\n\nNo signals generated this week."

    lines = [
        "📊 WEEKLY REVIEW",
        "",
        f"Signals evaluated: {wr['total']}",
        f"  ✅ Wins:  {wr['wins']}",
        f"  ❌ Losses: {wr['losses']}",
        f"  Win Rate: {wr['win_rate']:.1f}%",
    ]

    if wr["insufficient_data"]:
        lines.append("\n⚠️ Insufficient data for reliable statistics (<30 signals)")

    return "\n".join(lines)


def generate_monthly_report(db_path: str, config: dict) -> str:
    """Generate monthly performance summary.

    See docs/sub-specs/SS-20.md §16.6

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.

    Returns:
        Formatted monthly report string.
    """
    wr = compute_win_rate(db_path, days=30)
    comp = compute_component_accuracy(db_path, days=30)
    regime = compute_regime_accuracy(db_path, days=30)

    lines = [
        "📊 MONTHLY PERFORMANCE REPORT",
        "",
        f"Overall Win Rate: {wr['win_rate']:.1f}% ({wr['wins']}/{wr['total']})",
    ]

    if wr["insufficient_data"]:
        lines.append("⚠️ Insufficient data (<30 signals)")

    lines.extend([
        "",
        "📈 Component Accuracy (correlation):",
        f"  Spot Flow:    {comp.get('spot_flow', 0):.3f}",
        f"  Leverage:     {comp.get('leverage_pos', 0):.3f}",
        f"  Options:      {comp.get('options_struct', 0):.3f}",
        f"  Mean Rev:     {comp.get('mean_reversion', 0):.3f}",
    ])

    if regime:
        lines.extend(["", "🔄 Accuracy by Regime:"])
        for r_name, r_stats in regime.items():
            flag = " ⚠️" if r_stats["insufficient_data"] else ""
            lines.append(f"  {r_name}: {r_stats['win_rate']:.1f}% (n={r_stats['total']}){flag}")

    return "\n".join(lines)


# ── Private helpers ──────────────────────────────────────────


def _parse_timestamp(ts: str) -> datetime | None:
    """Parse a timestamp string to datetime."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def _get_price_at_time(db_path: str, target_time: datetime) -> float | None:
    """Get BTC price closest to a target time."""
    ts = target_time.strftime("%Y-%m-%dT%H:%M:%S")
    rows = query(
        db_path,
        "SELECT close FROM spot_price WHERE timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
        (ts,),
    )
    if rows:
        return rows[0]["close"]
    return None
