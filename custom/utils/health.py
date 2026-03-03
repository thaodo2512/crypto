"""Data health monitor for all data sources.

See docs/sub-specs/SS-06.md §3.6
"""

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Tracks health status of all data sources in-memory.

    See docs/sub-specs/SS-06.md §3.6
    """

    def __init__(self, config: dict) -> None:
        """Initialize the health monitor.

        See docs/sub-specs/SS-06.md

        Args:
            config: Full settings dict (reads health section).
        """
        health_cfg = config["health"]
        self._staleness_minutes: int = health_cfg["staleness_threshold_minutes"]
        self._latency_threshold: float = health_cfg["latency_threshold_seconds"]
        self._failure_threshold: int = health_cfg["consecutive_failures_before_fallback"]
        self._sources: dict[str, dict[str, Any]] = {}

    def _ensure_source(self, source: str) -> dict[str, Any]:
        """Get or create the internal state dict for a source.

        See docs/sub-specs/SS-06.md §3.6
        """
        if source not in self._sources:
            self._sources[source] = {
                "last_success": None,
                "last_failure": None,
                "consecutive_failures": 0,
                "latency_seconds": None,
                "last_error": None,
            }
        return self._sources[source]

    def record_success(self, source: str, latency_seconds: float) -> None:
        """Record a successful fetch for a data source.

        See docs/sub-specs/SS-06.md §3.6

        Args:
            source: Data source name (e.g. "binance_spot").
            latency_seconds: Response time in seconds.
        """
        state = self._ensure_source(source)
        state["last_success"] = datetime.now(timezone.utc)
        state["consecutive_failures"] = 0
        state["latency_seconds"] = latency_seconds
        logger.debug("Health: %s success (%.2fs)", source, latency_seconds)

    def record_failure(self, source: str, error: str) -> None:
        """Record a failed fetch for a data source.

        See docs/sub-specs/SS-06.md §3.6

        Args:
            source: Data source name.
            error: Error message describing the failure.
        """
        state = self._ensure_source(source)
        state["last_failure"] = datetime.now(timezone.utc)
        state["consecutive_failures"] += 1
        state["last_error"] = error
        logger.warning(
            "Health: %s failure #%d: %s",
            source, state["consecutive_failures"], error,
        )

    def get_source_status(self, source: str) -> dict[str, Any]:
        """Get health status for a single data source.

        See docs/sub-specs/SS-06.md §3.6

        Args:
            source: Data source name.

        Returns:
            Dict with last_success, last_failure, consecutive_failures,
            latency_seconds, is_stale, is_degraded, last_error.
        """
        state = self._ensure_source(source)
        now = datetime.now(timezone.utc)

        last_success = state["last_success"]
        if last_success is None:
            is_stale = True
        else:
            age_minutes = (now - last_success).total_seconds() / 60
            is_stale = age_minutes > self._staleness_minutes

        is_degraded = state["consecutive_failures"] >= self._failure_threshold

        return {
            "last_success": last_success.isoformat() if last_success else None,
            "last_failure": state["last_failure"].isoformat() if state["last_failure"] else None,
            "consecutive_failures": state["consecutive_failures"],
            "latency_seconds": state["latency_seconds"],
            "is_stale": is_stale,
            "is_degraded": is_degraded,
            "last_error": state["last_error"],
        }

    def check_latency_warning(self, source: str) -> bool:
        """Check if a source's latest latency exceeds the threshold.

        See docs/sub-specs/SS-06.md §3.6

        Args:
            source: Data source name.

        Returns:
            True if latency exceeds threshold, False otherwise.
        """
        state = self._ensure_source(source)
        latency = state["latency_seconds"]
        if latency is None:
            return False
        return latency > self._latency_threshold

    def get_health_report(self) -> dict[str, Any]:
        """Get full health report across all tracked sources.

        See docs/sub-specs/SS-06.md §3.6

        Returns:
            Dict with sources (dict of source statuses) and overall_healthy (bool).
        """
        sources = {}
        overall_healthy = True

        for source_name in self._sources:
            status = self.get_source_status(source_name)
            sources[source_name] = status
            if status["is_stale"] or status["is_degraded"]:
                overall_healthy = False

        return {
            "sources": sources,
            "overall_healthy": overall_healthy,
        }
