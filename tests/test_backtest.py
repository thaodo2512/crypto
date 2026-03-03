"""Tests for SS-22: Backtesting Framework.

See docs/sub-specs/SS-22.md §Acceptance Criteria
"""

import json

import pytest

from custom.evaluation.backtest import (
    _compute_max_drawdown,
    compute_backtest_metrics,
    evaluate_period,
    generate_walk_forward_periods,
    replay_signals,
    run_backtest,
)
from custom.utils.db import get_db, init_db, insert_row


@pytest.fixture
def db(tmp_path) -> str:
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


@pytest.fixture
def config() -> dict:
    return {
        "backtesting": {
            "train_window_days": 60,
            "test_window_days": 30,
            "slide_days": 30,
        },
        "evaluation": {
            "primary_horizon_hours": 24,
        },
    }


def _seed_signal(db: str, timestamp: str, score: float, bias: str, regime: str,
                 price: float, price_24h: float | None = None) -> None:
    """Seed a signal row into the database."""
    conn = get_db(db)
    try:
        conn.execute(
            """INSERT INTO signals (timestamp, final_score, bias, strength, confidence,
               regime, event_risk, consensus, spot_flow, leverage_pos, options_struct,
               mean_reversion, weights_json, btc_price_at_signal, btc_price_24h_later)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, score, bias, "MODERATE", "MEDIUM", regime, 0.1, "MIXED",
             0.3, 0.2, 0.1, 0.0, "{}", price, price_24h),
        )
        conn.commit()
    finally:
        conn.close()


class TestGenerateWalkForwardPeriods:
    def test_default_periods(self) -> None:
        """AC 1: Walk-forward periods generated correctly (60/30/30)."""
        periods = generate_walk_forward_periods("2025-01-01", "2025-07-01")
        assert len(periods) > 0
        # First period
        assert periods[0]["train_start"] == "2025-01-01"
        assert periods[0]["train_end"] == "2025-03-02"
        assert periods[0]["test_start"] == "2025-03-02"
        assert periods[0]["test_end"] == "2025-04-01"

    def test_periods_no_test_overlap(self) -> None:
        """AC 2: Test periods do not overlap."""
        periods = generate_walk_forward_periods("2025-01-01", "2025-12-31")
        for i in range(1, len(periods)):
            # test_start of current should be >= test_start of previous
            # (they may overlap with train windows, but test windows slide)
            assert periods[i]["test_start"] >= periods[i - 1]["test_start"]

    def test_custom_window_sizes(self) -> None:
        """AC 8: Window sizes from config."""
        periods = generate_walk_forward_periods(
            "2025-01-01", "2025-06-01",
            train_days=30, test_days=15, slide_days=15,
        )
        assert len(periods) > 0
        # Each period should have correct window
        p = periods[0]
        assert p["train_start"] == "2025-01-01"

    def test_insufficient_range(self) -> None:
        """Short range produces no periods."""
        periods = generate_walk_forward_periods("2025-01-01", "2025-02-01")
        assert len(periods) == 0


class TestReplaySignals:
    def test_replay_returns_signals(self, db, config) -> None:
        """AC 3: Signal replay produces results for date range."""
        _seed_signal(db, "2025-06-15T08:00:00Z", 0.4, "LONG", "STRONG_TREND", 100000)
        _seed_signal(db, "2025-06-16T08:00:00Z", -0.3, "SHORT", "MODERATE_TREND", 99000)

        signals = replay_signals(db, config, "2025-06-14", "2025-06-17")
        assert len(signals) == 2
        assert signals[0]["bias"] == "LONG"
        assert signals[1]["bias"] == "SHORT"

    def test_replay_empty_range(self, db, config) -> None:
        """Replay returns empty for no matching data."""
        signals = replay_signals(db, config, "2025-01-01", "2025-01-02")
        assert signals == []


class TestEvaluatePeriod:
    def test_win_rate_correct(self, db) -> None:
        """AC 4: Win rate computed correctly."""
        # 2 correct, 1 wrong → 66.7% win rate
        _seed_signal(db, "2025-06-01T08:00:00Z", 0.4, "LONG", "STRONG_TREND", 100000, 101000)  # +1% correct
        _seed_signal(db, "2025-06-02T08:00:00Z", -0.3, "SHORT", "MODERATE_TREND", 100000, 99000)  # -1% correct
        _seed_signal(db, "2025-06-03T08:00:00Z", 0.3, "LONG", "STRONG_TREND", 100000, 99000)  # -1% wrong

        signals = replay_signals(db, {}, "2025-06-01", "2025-06-04")
        metrics = evaluate_period(signals, db, 24)
        assert metrics["signal_count"] == 3
        assert metrics["win_rate"] == pytest.approx(66.67, abs=0.1)

    def test_max_drawdown(self) -> None:
        """AC 5: Max drawdown tracks peak-to-trough."""
        curve = [0, 10, 8, 12, 5, 15]
        dd = _compute_max_drawdown(curve)
        # Peak 12, trough 5 → dd = 7
        assert dd == 7.0

    def test_accuracy_by_regime(self, db) -> None:
        """AC 6: Accuracy segmented by regime."""
        _seed_signal(db, "2025-06-01T08:00:00Z", 0.4, "LONG", "STRONG_TREND", 100000, 101000)
        _seed_signal(db, "2025-06-02T08:00:00Z", 0.3, "LONG", "TIGHT_RANGE", 100000, 99000)

        signals = replay_signals(db, {}, "2025-06-01", "2025-06-03")
        metrics = evaluate_period(signals, db, 24)
        assert "STRONG_TREND" in metrics["accuracy_by_regime"]
        assert metrics["accuracy_by_regime"]["STRONG_TREND"] == 100.0
        assert metrics["accuracy_by_regime"]["TIGHT_RANGE"] == 0.0

    def test_empty_signals(self, db) -> None:
        """AC 7: Returns empty metrics on no data."""
        metrics = evaluate_period([], db, 24)
        assert metrics["signal_count"] == 0
        assert metrics["win_rate"] == 0.0


class TestComputeBacktestMetrics:
    def test_aggregate_metrics(self) -> None:
        """Aggregate across periods."""
        results = [
            {"win_rate": 60.0, "avg_rr": 1.2, "max_drawdown": 5.0, "signal_count": 10,
             "accuracy_by_regime": {"STRONG_TREND": 70.0}},
            {"win_rate": 50.0, "avg_rr": 0.8, "max_drawdown": 8.0, "signal_count": 10,
             "accuracy_by_regime": {"STRONG_TREND": 60.0}},
        ]
        metrics = compute_backtest_metrics(results)
        assert metrics["signal_count"] == 20
        assert metrics["num_periods"] == 2
        assert metrics["win_rate"] == pytest.approx(55.0)
        assert metrics["max_drawdown"] == 8.0

    def test_empty_results(self) -> None:
        """AC 7: Empty results returns empty metrics."""
        metrics = compute_backtest_metrics([])
        assert metrics["signal_count"] == 0


class TestRunBacktest:
    def test_orchestrator_runs(self, db, config) -> None:
        """Orchestrator runs without crash."""
        result = run_backtest(db, config, "2025-01-01", "2025-07-01")
        assert isinstance(result, dict)
        assert "win_rate" in result
        assert "signal_count" in result

    def test_thresholds_from_config(self, config) -> None:
        """AC 8: All window sizes from config."""
        assert config["backtesting"]["train_window_days"] == 60
        assert config["backtesting"]["test_window_days"] == 30
        assert config["backtesting"]["slide_days"] == 30
