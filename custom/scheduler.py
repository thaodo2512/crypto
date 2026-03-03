"""Scheduler — APScheduler-based main loop for all periodic jobs.

See docs/sub-specs/SS-21.md §9
"""

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SignalBotScheduler:
    """Orchestrates all periodic data collection, signal computation, and reporting.

    See docs/sub-specs/SS-21.md §9.1

    Standard intervals:
        - 2 min: price + alert checks
        - 15 min: orderbook, futures OI, basis
        - 1 hour: funding, L/S ratio, CVD, whale trades, liquidations
        - 4 hours: options scan, signal recompute
        - daily 08:00 UTC: full report, technicals, regime, macro, maintenance

    Elevated risk (event_risk > 0.7):
        - 30s: price
        - 5 min: futures
        - 30 min: options + signals
    """

    def __init__(self, config: dict):
        self.config = config
        self.scheduler = None
        self._elevated = False
        self._jobs: dict[str, Any] = {}
        self._job_funcs: dict[str, Callable] = {}

    def register_job(self, name: str, func: Callable, **kwargs: Any) -> None:
        """Register a job function for scheduling.

        Args:
            name: Job name identifier.
            func: Callable to execute.
            **kwargs: Additional metadata.
        """
        self._job_funcs[name] = func
        logger.debug("Registered job: %s", name)

    def get_standard_intervals(self) -> dict[str, int]:
        """Get standard scheduling intervals from config.

        See docs/sub-specs/SS-21.md §9.1

        Returns:
            Dict mapping job category to interval in seconds.
        """
        sched_cfg = self.config.get("scheduling", {})
        return {
            "price": sched_cfg.get("price_interval_seconds", 120),
            "orderbook": sched_cfg.get("orderbook_interval_minutes", 15) * 60,
            "futures": sched_cfg.get("futures_interval_minutes", 15) * 60,
            "hourly": sched_cfg.get("hourly_interval_minutes", 60) * 60,
            "options": sched_cfg.get("options_interval_hours", 4) * 3600,
            "daily_report_hour": sched_cfg.get("daily_report_utc_hour", 8),
        }

    def get_elevated_intervals(self) -> dict[str, int]:
        """Get elevated-risk scheduling intervals from config.

        See docs/sub-specs/SS-21.md §9.2

        Returns:
            Dict mapping job category to interval in seconds.
        """
        sched_cfg = self.config.get("scheduling", {})
        return {
            "price": sched_cfg.get("elevated_price_seconds", 30),
            "futures": sched_cfg.get("elevated_futures_minutes", 5) * 60,
            "options": sched_cfg.get("elevated_options_minutes", 30) * 60,
            "signals": sched_cfg.get("elevated_signals_minutes", 30) * 60,
        }

    def check_elevated_risk(self, event_risk: float) -> bool:
        """Determine if elevated schedule is needed.

        See docs/sub-specs/SS-21.md §9.2

        Args:
            event_risk: Current event risk value.

        Returns:
            True if event_risk > 0.7, meaning intervals should tighten.
        """
        return event_risk > 0.7

    def set_elevated(self, elevated: bool) -> None:
        """Switch between standard and elevated schedules.

        See docs/sub-specs/SS-21.md §9.2

        Args:
            elevated: True for elevated risk intervals.
        """
        if elevated == self._elevated:
            return

        self._elevated = elevated
        if elevated:
            logger.warning("Switching to ELEVATED risk schedule")
        else:
            logger.info("Reverting to standard schedule")

    @property
    def is_elevated(self) -> bool:
        """Whether the scheduler is in elevated risk mode."""
        return self._elevated

    def start(self) -> None:
        """Start the scheduler.

        See docs/sub-specs/SS-21.md §9

        Creates and starts an APScheduler instance with all registered jobs.
        """
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger

            self.scheduler = BackgroundScheduler()

            intervals = self.get_standard_intervals()

            # Register interval jobs
            for name, func in self._job_funcs.items():
                if name == "daily_report":
                    hour = intervals.get("daily_report_hour", 8)
                    self.scheduler.add_job(
                        self._safe_run(func), CronTrigger(hour=hour, minute=0),
                        id=name, name=name,
                    )
                elif name in intervals:
                    self.scheduler.add_job(
                        self._safe_run(func), IntervalTrigger(seconds=intervals[name]),
                        id=name, name=name,
                    )

            self.scheduler.start()
            logger.info("Scheduler started with %d jobs", len(self._job_funcs))
        except ImportError:
            logger.error("APScheduler not installed — scheduler disabled")
        except Exception as e:
            logger.error("Scheduler start failed: %s", e)

    def stop(self) -> None:
        """Stop the scheduler gracefully.

        See docs/sub-specs/SS-21.md §9
        """
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")
            self.scheduler = None

    def _safe_run(self, func: Callable) -> Callable:
        """Wrap a job function to catch and log errors.

        See docs/sub-specs/SS-21.md §9

        Args:
            func: Job function to wrap.

        Returns:
            Wrapped function that never raises.
        """
        def wrapper() -> None:
            try:
                func()
            except Exception as e:
                logger.error("Job failed: %s — %s", func.__name__, e)
        wrapper.__name__ = getattr(func, "__name__", "unknown_job")
        return wrapper
