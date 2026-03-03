"""Tests for SS-06: Data Health Monitor.

See docs/sub-specs/SS-06.md §Acceptance Criteria
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from custom.utils.health import HealthMonitor


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def health_config() -> dict:
    """Config dict for health monitor."""
    return {
        "health": {
            "staleness_threshold_minutes": 30,
            "latency_threshold_seconds": 5,
            "consecutive_failures_before_fallback": 3,
        },
    }


@pytest.fixture
def monitor(health_config) -> HealthMonitor:
    """HealthMonitor with test config."""
    return HealthMonitor(health_config)


# ─── TestRecordSuccess ───────────────────────────────────


class TestRecordSuccess:
    """Tests for record_success()."""

    def test_record_success_updates_timestamp(self, monitor) -> None:
        """AC 1: Updates last_success timestamp and resets failure count."""
        monitor.record_failure("binance_spot", "timeout")
        monitor.record_failure("binance_spot", "timeout")

        monitor.record_success("binance_spot", 0.5)

        status = monitor.get_source_status("binance_spot")
        assert status["last_success"] is not None
        assert status["consecutive_failures"] == 0

    def test_record_success_stores_latency(self, monitor) -> None:
        """AC 2: Stores latency_seconds."""
        monitor.record_success("binance_spot", 1.23)

        status = monitor.get_source_status("binance_spot")
        assert status["latency_seconds"] == 1.23


# ─── TestRecordFailure ───────────────────────────────────


class TestRecordFailure:
    """Tests for record_failure()."""

    def test_record_failure_increments(self, monitor) -> None:
        """AC 3: Increments consecutive_failures and stores error."""
        monitor.record_failure("deribit", "API returned 503")
        monitor.record_failure("deribit", "timeout")

        status = monitor.get_source_status("deribit")
        assert status["consecutive_failures"] == 2
        assert status["last_error"] == "timeout"
        assert status["last_failure"] is not None


# ─── TestGetSourceStatus ─────────────────────────────────


class TestGetSourceStatus:
    """Tests for get_source_status()."""

    def test_get_source_status_known(self, monitor) -> None:
        """AC 4: Returns correct status dict for known source."""
        monitor.record_success("binance_spot", 0.3)

        status = monitor.get_source_status("binance_spot")

        assert "last_success" in status
        assert "last_failure" in status
        assert "consecutive_failures" in status
        assert "latency_seconds" in status
        assert "is_stale" in status
        assert "is_degraded" in status
        assert "last_error" in status
        assert status["consecutive_failures"] == 0
        assert status["latency_seconds"] == 0.3
        assert status["is_stale"] is False
        assert status["is_degraded"] is False

    def test_get_source_status_unknown(self, monitor) -> None:
        """AC 5: Returns default status for unknown source."""
        status = monitor.get_source_status("unknown_source")

        assert status["last_success"] is None
        assert status["last_failure"] is None
        assert status["consecutive_failures"] == 0
        assert status["latency_seconds"] is None
        assert status["is_stale"] is True  # never succeeded = stale
        assert status["is_degraded"] is False
        assert status["last_error"] is None


# ─── TestStaleness ───────────────────────────────────────


class TestStaleness:
    """Tests for is_stale computation."""

    def test_is_stale_old_timestamp(self, monitor) -> None:
        """AC 6: is_stale True when last_success older than threshold."""
        monitor.record_success("binance_spot", 0.5)
        # Manually set last_success to 31 minutes ago
        old_time = datetime.now(timezone.utc) - timedelta(minutes=31)
        monitor._sources["binance_spot"]["last_success"] = old_time

        status = monitor.get_source_status("binance_spot")
        assert status["is_stale"] is True

    def test_is_stale_never_succeeded(self, monitor) -> None:
        """AC 7: is_stale True when source has never succeeded."""
        monitor.record_failure("new_source", "first attempt failed")

        status = monitor.get_source_status("new_source")
        assert status["is_stale"] is True


# ─── TestDegradation ─────────────────────────────────────


class TestDegradation:
    """Tests for is_degraded computation."""

    def test_is_degraded(self, monitor) -> None:
        """AC 8: is_degraded True when consecutive_failures >= threshold (3)."""
        monitor.record_failure("fred", "error1")
        assert monitor.get_source_status("fred")["is_degraded"] is False

        monitor.record_failure("fred", "error2")
        assert monitor.get_source_status("fred")["is_degraded"] is False

        monitor.record_failure("fred", "error3")
        assert monitor.get_source_status("fred")["is_degraded"] is True


# ─── TestHealthReport ────────────────────────────────────


class TestHealthReport:
    """Tests for get_health_report()."""

    def test_health_report_all_sources(self, monitor) -> None:
        """AC 9: Returns all tracked sources with statuses."""
        monitor.record_success("binance_spot", 0.3)
        monitor.record_success("deribit", 1.2)
        monitor.record_success("fred", 0.8)

        report = monitor.get_health_report()

        assert "sources" in report
        assert "overall_healthy" in report
        assert "binance_spot" in report["sources"]
        assert "deribit" in report["sources"]
        assert "fred" in report["sources"]
        assert len(report["sources"]) == 3

    def test_health_report_unhealthy(self, monitor) -> None:
        """AC 10: overall_healthy=False when any source is stale or degraded."""
        monitor.record_success("binance_spot", 0.3)
        monitor.record_failure("deribit", "err1")
        monitor.record_failure("deribit", "err2")
        monitor.record_failure("deribit", "err3")  # now degraded

        report = monitor.get_health_report()

        assert report["overall_healthy"] is False
        assert report["sources"]["binance_spot"]["is_degraded"] is False
        assert report["sources"]["deribit"]["is_degraded"] is True


# ─── TestLatencyWarning ──────────────────────────────────


class TestLatencyWarning:
    """Tests for check_latency_warning()."""

    def test_check_latency_warning(self, monitor) -> None:
        """AC 11: Returns True when latency exceeds threshold (5s)."""
        monitor.record_success("slow_source", 6.0)
        assert monitor.check_latency_warning("slow_source") is True

        monitor.record_success("fast_source", 0.5)
        assert monitor.check_latency_warning("fast_source") is False


# ─── TestConfig ──────────────────────────────────────────


class TestConfig:
    """Tests for config usage."""

    def test_thresholds_from_config(self) -> None:
        """AC 12: All thresholds read from config, not hardcoded."""
        custom_config = {
            "health": {
                "staleness_threshold_minutes": 5,
                "latency_threshold_seconds": 1,
                "consecutive_failures_before_fallback": 2,
            },
        }
        m = HealthMonitor(custom_config)

        # Staleness: 5 min threshold (not 30)
        m.record_success("src", 0.1)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=6)
        m._sources["src"]["last_success"] = old_time
        assert m.get_source_status("src")["is_stale"] is True

        # Latency: 1s threshold (not 5)
        m.record_success("src2", 1.5)
        assert m.check_latency_warning("src2") is True

        # Degradation: 2 failures (not 3)
        m.record_failure("src3", "e1")
        m.record_failure("src3", "e2")
        assert m.get_source_status("src3")["is_degraded"] is True


# ─── TestEdgeCases ───────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_success_resets_failures(self, monitor) -> None:
        """Edge: Success after multiple failures resets count to 0."""
        monitor.record_failure("src", "e1")
        monitor.record_failure("src", "e2")
        monitor.record_failure("src", "e3")
        assert monitor.get_source_status("src")["is_degraded"] is True

        monitor.record_success("src", 0.5)
        status = monitor.get_source_status("src")
        assert status["consecutive_failures"] == 0
        assert status["is_degraded"] is False

    def test_multiple_sources_independent(self, monitor) -> None:
        """Edge: One source failing doesn't affect others."""
        monitor.record_success("healthy", 0.3)
        monitor.record_failure("broken", "down")
        monitor.record_failure("broken", "down")
        monitor.record_failure("broken", "down")

        assert monitor.get_source_status("healthy")["is_degraded"] is False
        assert monitor.get_source_status("healthy")["consecutive_failures"] == 0
        assert monitor.get_source_status("broken")["is_degraded"] is True

    def test_zero_latency(self, monitor) -> None:
        """Edge: Zero latency is valid and does not trigger warning."""
        monitor.record_success("fast", 0.0)

        assert monitor.get_source_status("fast")["latency_seconds"] == 0.0
        assert monitor.check_latency_warning("fast") is False
