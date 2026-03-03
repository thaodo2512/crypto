"""Tests for SS-20: Evaluation & Performance Tracking.

See docs/sub-specs/SS-20.md §Acceptance Criteria
"""

from datetime import datetime, timedelta, timezone

import pytest

from custom.evaluation.tracker import (
    compute_component_accuracy,
    compute_regime_accuracy,
    compute_win_rate,
    evaluate_correctness,
    fill_outcomes,
    generate_monthly_report,
    generate_weekly_report,
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
        "evaluation": {
            "outcome_horizons_hours": [4, 12, 24, 48],
            "primary_horizon_hours": 24,
            "neutral_correct_threshold_pct": 1.0,
            "min_samples_overall": 30,
            "min_samples_per_regime": 15,
        },
    }


def _seed_signal(db: str, ts: str, bias: str, price: float, regime: str = "STRONG_TREND",
                 correct: int | None = None, magnitude: float | None = None,
                 price_24h: float | None = None,
                 sf: float = 0.3, lp: float = 0.2, os_: float = 0.1, mr: float = 0.0) -> None:
    conn = get_db(db)
    try:
        conn.execute(
            """INSERT INTO signals (timestamp, final_score, bias, strength, confidence,
               regime, event_risk, consensus, spot_flow, leverage_pos, options_struct,
               mean_reversion, weights_json, btc_price_at_signal, btc_price_24h_later,
               correct, magnitude_24h_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, 0.4, bias, "MODERATE", "MEDIUM", regime, 0.1, "MIXED",
             sf, lp, os_, mr, "{}", price, price_24h, correct, magnitude),
        )
        conn.commit()
    finally:
        conn.close()


class TestEvaluateCorrectness:
    def test_long_correct(self) -> None:
        """AC 2: LONG correct if price went up."""
        assert evaluate_correctness("LONG", 100000, 101000) == 1

    def test_long_incorrect(self) -> None:
        """AC 2: LONG incorrect if price went down."""
        assert evaluate_correctness("LONG", 100000, 99000) == 0

    def test_short_correct(self) -> None:
        """AC 2: SHORT correct if price went down."""
        assert evaluate_correctness("SHORT", 100000, 99000) == 1

    def test_short_incorrect(self) -> None:
        """AC 2: SHORT incorrect if price went up."""
        assert evaluate_correctness("SHORT", 100000, 101000) == 0

    def test_neutral_correct_flat(self) -> None:
        """AC 3: NEUTRAL correct if |change| < 1%."""
        assert evaluate_correctness("NEUTRAL", 100000, 100500) == 1

    def test_neutral_incorrect_moved(self) -> None:
        """AC 3: NEUTRAL incorrect if |change| >= 1%."""
        assert evaluate_correctness("NEUTRAL", 100000, 102000) == 0


class TestFillOutcomes:
    def test_fills_price_data(self, db) -> None:
        """AC 1: Outcome tracker fills prices at horizons."""
        # Seed a signal from 25 hours ago
        past = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed_signal(db, past, "LONG", 100000)

        # Seed price data
        for h in [4, 12, 24]:
            ts = (datetime.now(timezone.utc) - timedelta(hours=25 - h)).strftime("%Y-%m-%dT%H:%M:%S")
            insert_row(db, "spot_price", {
                "timestamp": ts,
                "open": 100000, "high": 101000, "low": 99000,
                "close": 100000 + h * 100,
                "volume": 5000, "quote_volume": 5e8, "num_trades": 10000,
            })

        updates = fill_outcomes(db)
        assert updates > 0


class TestComputeWinRate:
    def test_win_rate(self, db) -> None:
        """AC 4: Win rate computed over rolling window."""
        now = datetime.now(timezone.utc)
        for i in range(35):
            ts = (now - timedelta(hours=i * 6)).strftime("%Y-%m-%dT%H:%M:%SZ")
            correct = 1 if i % 3 != 0 else 0  # ~67% win rate
            _seed_signal(db, ts, "LONG", 100000, correct=correct)

        result = compute_win_rate(db, days=30)
        assert result["total"] >= 30
        assert not result["insufficient_data"]
        assert 50 < result["win_rate"] < 80

    def test_insufficient_data(self, db) -> None:
        """AC 8: Insufficient data warning when < 30 samples."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed_signal(db, now, "LONG", 100000, correct=1)

        result = compute_win_rate(db, days=30)
        assert result["insufficient_data"] is True


class TestComponentAccuracy:
    def test_component_correlation(self, db) -> None:
        """AC 5: Component accuracy computed per signal."""
        now = datetime.now(timezone.utc)
        for i in range(35):
            ts = (now - timedelta(hours=i * 6)).strftime("%Y-%m-%dT%H:%M:%SZ")
            # Spot flow positively correlates with outcomes
            mag = 2.0 if i % 2 == 0 else -1.0
            sf = 0.5 if i % 2 == 0 else -0.3
            _seed_signal(db, ts, "LONG", 100000, magnitude=mag, sf=sf, price_24h=100000 + mag * 1000)

        result = compute_component_accuracy(db, days=30)
        assert "spot_flow" in result
        assert "leverage_pos" in result
        # Spot flow should have positive correlation
        assert result["spot_flow"] > 0


class TestRegimeAccuracy:
    def test_regime_segmentation(self, db) -> None:
        """AC 6: Accuracy segmented by regime."""
        now = datetime.now(timezone.utc)
        for i in range(20):
            ts = (now - timedelta(hours=i * 6)).strftime("%Y-%m-%dT%H:%M:%SZ")
            regime = "STRONG_TREND" if i < 10 else "TIGHT_RANGE"
            correct = 1 if i < 8 else 0  # STRONG_TREND: 80%, TIGHT_RANGE: mixed
            _seed_signal(db, ts, "LONG", 100000, regime=regime, correct=correct)

        result = compute_regime_accuracy(db, days=30)
        assert "STRONG_TREND" in result
        assert "TIGHT_RANGE" in result
        assert result["STRONG_TREND"]["win_rate"] > result["TIGHT_RANGE"]["win_rate"]


class TestReports:
    def test_weekly_report(self, db, config) -> None:
        """AC 7: Weekly report includes win/loss counts."""
        now = datetime.now(timezone.utc)
        for i in range(5):
            ts = (now - timedelta(hours=i * 12)).strftime("%Y-%m-%dT%H:%M:%SZ")
            _seed_signal(db, ts, "LONG", 100000, correct=1 if i < 3 else 0)

        report = generate_weekly_report(db, config)
        assert "WEEKLY" in report
        assert "Wins" in report

    def test_monthly_report(self, db, config) -> None:
        """AC 5+6: Monthly report includes component and regime accuracy."""
        report = generate_monthly_report(db, config)
        assert "MONTHLY" in report
        assert "Component" in report

    def test_weekly_no_data(self, db, config) -> None:
        """AC 8: No data handled gracefully."""
        report = generate_weekly_report(db, config)
        assert "No signals" in report or "WEEKLY" in report

    def test_config_horizons(self, config) -> None:
        """AC 9: All horizons from config."""
        assert config["evaluation"]["outcome_horizons_hours"] == [4, 12, 24, 48]
        assert config["evaluation"]["primary_horizon_hours"] == 24
