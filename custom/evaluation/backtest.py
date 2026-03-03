"""Walk-forward backtesting framework for composite signals.

See docs/sub-specs/SS-22.md §15
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from custom.signals.engine import assemble_signal
from custom.utils.db import get_latest, query

logger = logging.getLogger(__name__)


def generate_walk_forward_periods(
    start_date: str,
    end_date: str,
    train_days: int = 60,
    test_days: int = 30,
    slide_days: int = 30,
) -> list[dict[str, str]]:
    """Generate walk-forward train/test period tuples.

    See docs/sub-specs/SS-22.md §15.2

    Args:
        start_date: Start date string (YYYY-MM-DD).
        end_date: End date string (YYYY-MM-DD).
        train_days: Training window length.
        test_days: Testing window length.
        slide_days: Slide step between periods.

    Returns:
        List of dicts with train_start, train_end, test_start, test_end.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    periods: list[dict[str, str]] = []
    cursor = start

    while cursor + timedelta(days=train_days + test_days) <= end:
        train_start = cursor
        train_end = cursor + timedelta(days=train_days)
        test_start = train_end
        test_end = train_end + timedelta(days=test_days)

        periods.append({
            "train_start": train_start.strftime("%Y-%m-%d"),
            "train_end": train_end.strftime("%Y-%m-%d"),
            "test_start": test_start.strftime("%Y-%m-%d"),
            "test_end": test_end.strftime("%Y-%m-%d"),
        })
        cursor += timedelta(days=slide_days)

    logger.info("Generated %d walk-forward periods from %s to %s", len(periods), start_date, end_date)
    return periods


def replay_signals(
    db_path: str, config: dict, start_date: str, end_date: str
) -> list[dict[str, Any]]:
    """Replay signal computation on historical data for a date range.

    See docs/sub-specs/SS-22.md §15

    Reads stored signals from the signals table for the given date range.
    For backtesting, signals should already have been computed and stored.

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        List of signal dicts from the signals table.
    """
    try:
        rows = query(
            db_path,
            "SELECT * FROM signals WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp",
            (start_date, end_date),
        )
        signals = []
        for row in rows:
            signals.append({
                "timestamp": row["timestamp"],
                "final_score": row["final_score"],
                "bias": row["bias"],
                "strength": row["strength"],
                "confidence": row["confidence"],
                "regime": row["regime"],
                "event_risk": row["event_risk"],
                "consensus": row["consensus"],
                "btc_price": row.get("btc_price_at_signal", 0.0),
                "breakdown": {
                    "spot_flow": row.get("spot_flow", 0.0),
                    "leverage_pos": row.get("leverage_pos", 0.0),
                    "options_struct": row.get("options_struct", 0.0),
                    "mean_reversion": row.get("mean_reversion", 0.0),
                },
            })
        logger.debug("Replayed %d signals from %s to %s", len(signals), start_date, end_date)
        return signals
    except Exception as e:
        logger.error("Signal replay failed: %s", e)
        return []


def evaluate_period(
    signals: list[dict[str, Any]], db_path: str, horizon_hours: int = 24
) -> dict[str, Any]:
    """Compute metrics for a test period.

    See docs/sub-specs/SS-22.md §15.3

    Metrics: win_rate, avg_rr, max_drawdown, signal_count, accuracy_by_regime.

    Args:
        signals: List of signal dicts from replay_signals().
        db_path: Path to SQLite database (for price lookup).
        horizon_hours: Hours to check for direction validation.

    Returns:
        Metrics dict.
    """
    if not signals:
        return _empty_metrics()

    wins = 0
    total = 0
    rr_values: list[float] = []
    equity_curve: list[float] = [0.0]
    regime_stats: dict[str, dict[str, int]] = {}

    for sig in signals:
        bias = sig.get("bias", "NEUTRAL")
        if bias == "NEUTRAL":
            continue

        price_at_signal = sig.get("btc_price", 0.0)
        if price_at_signal <= 0:
            continue

        # Look up future price at horizon
        timestamp = sig.get("timestamp", "")
        horizon_col = f"btc_price_{horizon_hours}h_later"

        # Try to get the outcome price from signals table
        outcome_rows = query(
            db_path,
            f"SELECT {horizon_col} FROM signals WHERE timestamp = ? AND {horizon_col} IS NOT NULL",
            (timestamp,),
        )

        if not outcome_rows or outcome_rows[0][horizon_col] is None:
            continue

        future_price = outcome_rows[0][horizon_col]
        price_change_pct = (future_price - price_at_signal) / price_at_signal * 100

        # Check direction match
        correct = (bias == "LONG" and price_change_pct > 0) or (bias == "SHORT" and price_change_pct < 0)

        total += 1
        if correct:
            wins += 1
            rr_values.append(abs(price_change_pct))
        else:
            rr_values.append(-abs(price_change_pct))

        # Track equity
        equity_curve.append(equity_curve[-1] + (abs(price_change_pct) if correct else -abs(price_change_pct)))

        # Regime stats
        regime = sig.get("regime", "UNKNOWN")
        if regime not in regime_stats:
            regime_stats[regime] = {"wins": 0, "total": 0}
        regime_stats[regime]["total"] += 1
        if correct:
            regime_stats[regime]["wins"] += 1

    win_rate = (wins / total * 100) if total > 0 else 0.0
    avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0.0
    max_dd = _compute_max_drawdown(equity_curve)

    # Accuracy by regime
    accuracy_by_regime = {}
    for regime, stats in regime_stats.items():
        accuracy_by_regime[regime] = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0.0

    return {
        "win_rate": win_rate,
        "avg_rr": avg_rr,
        "max_drawdown": max_dd,
        "signal_count": total,
        "accuracy_by_regime": accuracy_by_regime,
    }


def compute_backtest_metrics(
    period_results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Aggregate metrics across all walk-forward periods.

    See docs/sub-specs/SS-22.md §15.3

    Args:
        period_results: List of metrics dicts from evaluate_period().

    Returns:
        Aggregated metrics dict.
    """
    if not period_results:
        return _empty_metrics()

    total_signals = sum(r.get("signal_count", 0) for r in period_results)
    if total_signals == 0:
        return _empty_metrics()

    # Weighted win rate
    total_wins = sum(
        r.get("win_rate", 0) * r.get("signal_count", 0) / 100 for r in period_results
    )
    overall_win_rate = (total_wins / total_signals * 100) if total_signals > 0 else 0.0

    # Avg RR weighted
    total_rr = sum(r.get("avg_rr", 0) * r.get("signal_count", 0) for r in period_results)
    overall_avg_rr = total_rr / total_signals if total_signals > 0 else 0.0

    # Max drawdown = worst across all periods
    overall_max_dd = max((r.get("max_drawdown", 0) for r in period_results), default=0.0)

    # Merge regime accuracies
    regime_totals: dict[str, dict[str, float]] = {}
    for r in period_results:
        for regime, acc in r.get("accuracy_by_regime", {}).items():
            if regime not in regime_totals:
                regime_totals[regime] = {"wins_weighted": 0, "count": 0}
            count = r.get("signal_count", 0)
            regime_totals[regime]["wins_weighted"] += acc * count / 100
            regime_totals[regime]["count"] += count

    accuracy_by_regime = {}
    for regime, data in regime_totals.items():
        accuracy_by_regime[regime] = (data["wins_weighted"] / data["count"] * 100) if data["count"] > 0 else 0.0

    return {
        "win_rate": overall_win_rate,
        "avg_rr": overall_avg_rr,
        "max_drawdown": overall_max_dd,
        "signal_count": total_signals,
        "num_periods": len(period_results),
        "accuracy_by_regime": accuracy_by_regime,
    }


def run_backtest(
    db_path: str, config: dict, start_date: str, end_date: str
) -> dict[str, Any]:
    """Orchestrator: run full walk-forward backtest.

    See docs/sub-specs/SS-22.md §15

    Args:
        db_path: Path to SQLite database.
        config: Full settings dict.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        Aggregated backtest metrics.
    """
    try:
        bt_cfg = config.get("backtesting", {})
        train_days = bt_cfg.get("train_window_days", 60)
        test_days = bt_cfg.get("test_window_days", 30)
        slide_days = bt_cfg.get("slide_days", 30)
        horizon = config.get("evaluation", {}).get("primary_horizon_hours", 24)

        periods = generate_walk_forward_periods(start_date, end_date, train_days, test_days, slide_days)
        if not periods:
            logger.warning("No walk-forward periods generated for %s to %s", start_date, end_date)
            return _empty_metrics()

        period_results: list[dict[str, Any]] = []
        for period in periods:
            signals = replay_signals(db_path, config, period["test_start"], period["test_end"])
            metrics = evaluate_period(signals, db_path, horizon)
            period_results.append(metrics)

        result = compute_backtest_metrics(period_results)
        logger.info(
            "Backtest complete: %d periods, %d signals, %.1f%% win rate",
            result.get("num_periods", 0), result.get("signal_count", 0), result.get("win_rate", 0),
        )
        return result

    except Exception as e:
        logger.error("Backtest failed: %s", e)
        return _empty_metrics()


def _compute_max_drawdown(equity_curve: list[float]) -> float:
    """Compute max drawdown from an equity curve."""
    if len(equity_curve) < 2:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve[1:]:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _empty_metrics() -> dict[str, Any]:
    """Return empty metrics on insufficient data."""
    return {
        "win_rate": 0.0,
        "avg_rr": 0.0,
        "max_drawdown": 0.0,
        "signal_count": 0,
        "num_periods": 0,
        "accuracy_by_regime": {},
    }
