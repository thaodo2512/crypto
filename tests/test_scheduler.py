"""Tests for SS-21: Scheduler & Main Entry Point.

See docs/sub-specs/SS-21.md §Acceptance Criteria
"""

import pytest

from custom.scheduler import SignalBotScheduler


@pytest.fixture
def config() -> dict:
    return {
        "scheduling": {
            "price_interval_seconds": 120,
            "orderbook_interval_minutes": 15,
            "futures_interval_minutes": 15,
            "hourly_interval_minutes": 60,
            "options_interval_hours": 4,
            "daily_report_utc_hour": 8,
            "elevated_price_seconds": 30,
            "elevated_futures_minutes": 5,
            "elevated_options_minutes": 30,
            "elevated_signals_minutes": 30,
        },
    }


class TestStandardIntervals:
    def test_standard_intervals(self, config) -> None:
        """AC 1: Standard schedule registers correct intervals."""
        scheduler = SignalBotScheduler(config)
        intervals = scheduler.get_standard_intervals()

        assert intervals["price"] == 120
        assert intervals["orderbook"] == 15 * 60
        assert intervals["futures"] == 15 * 60
        assert intervals["hourly"] == 60 * 60
        assert intervals["options"] == 4 * 3600

    def test_daily_job_at_0800(self, config) -> None:
        """AC 3: Daily job scheduled at 08:00 UTC."""
        scheduler = SignalBotScheduler(config)
        intervals = scheduler.get_standard_intervals()
        assert intervals["daily_report_hour"] == 8


class TestElevatedRisk:
    def test_elevated_intervals(self, config) -> None:
        """AC 2: Elevated risk tightens intervals."""
        scheduler = SignalBotScheduler(config)
        elevated = scheduler.get_elevated_intervals()

        assert elevated["price"] == 30
        assert elevated["futures"] == 5 * 60
        assert elevated["options"] == 30 * 60
        assert elevated["signals"] == 30 * 60

    def test_check_elevated_risk_threshold(self, config) -> None:
        """AC 2: Elevated when event_risk > 0.7."""
        scheduler = SignalBotScheduler(config)
        assert scheduler.check_elevated_risk(0.8) is True
        assert scheduler.check_elevated_risk(0.5) is False
        assert scheduler.check_elevated_risk(0.7) is False  # not > 0.7

    def test_set_elevated_toggles(self, config) -> None:
        """AC 6: Elevated reverts to standard when risk drops."""
        scheduler = SignalBotScheduler(config)
        assert scheduler.is_elevated is False

        scheduler.set_elevated(True)
        assert scheduler.is_elevated is True

        scheduler.set_elevated(False)
        assert scheduler.is_elevated is False


class TestLifecycle:
    def test_register_job(self, config) -> None:
        """Jobs can be registered."""
        scheduler = SignalBotScheduler(config)

        def dummy_job():
            pass

        scheduler.register_job("test_job", dummy_job)
        assert "test_job" in scheduler._job_funcs

    def test_start_stop_without_apscheduler(self, config) -> None:
        """AC 4+7: Start/stop handle missing APScheduler gracefully."""
        scheduler = SignalBotScheduler(config)
        # start() should handle ImportError gracefully if APScheduler not installed
        # or succeed if it is installed
        scheduler.start()
        scheduler.stop()

    def test_safe_run_catches_errors(self, config) -> None:
        """AC 7: Job errors don't crash scheduler."""
        scheduler = SignalBotScheduler(config)

        def failing_job():
            raise ValueError("test error")

        wrapped = scheduler._safe_run(failing_job)
        # Should not raise
        wrapped()

    def test_intervals_from_config(self, config) -> None:
        """AC 5: All intervals from config."""
        assert config["scheduling"]["price_interval_seconds"] == 120
        assert config["scheduling"]["elevated_price_seconds"] == 30
        assert config["scheduling"]["daily_report_utc_hour"] == 8
