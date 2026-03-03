"""Finnhub Economic Calendar collector — scheduled macro events.

See docs/sub-specs/SS-24.md §2
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from custom.collectors.spot import CollectorError
from custom.utils.db import insert_row, query

logger = logging.getLogger(__name__)

FINNHUB_CALENDAR_URL = "https://finnhub.io/api/v1/calendar/economic"
REQUEST_TIMEOUT_SECONDS = 15

# Mapping from Finnhub impact field to tier
_IMPACT_TO_TIER: dict[str, int] = {
    "high": 1,
    "medium": 2,
    "low": 3,
}


class FinnhubCalendarCollector:
    """Fetches scheduled economic events from Finnhub Economic Calendar API.

    See docs/sub-specs/SS-24.md §2

    Replaces static JSON calendar with live API data. Events flow into
    the same macro_events table and are picked up by event_risk automatically.
    """

    def __init__(self, config: dict, db_path: str) -> None:
        """Initialize the Finnhub calendar collector.

        See docs/sub-specs/SS-24.md §2

        Args:
            config: Full settings dict.
            db_path: Path to SQLite database.
        """
        self._config = config
        self._db_path = db_path
        finnhub_cfg = config.get("finnhub", {})
        self._lookahead_days: int = finnhub_cfg.get("lookahead_days", 14)
        self._lookback_days: int = finnhub_cfg.get("lookback_days", 7)
        self._relevant_events: list[str] = finnhub_cfg.get("relevant_events", [])

    async def _get(self, url: str, params: dict | None = None) -> Any:
        """Make GET request to Finnhub API.

        See docs/sub-specs/SS-24.md §2

        Args:
            url: Full URL to fetch.
            params: Optional query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            CollectorError: On non-200 status or network failure.
        """
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(
                            "Finnhub API error: GET %s → %d: %s", url, resp.status, text
                        )
                        raise CollectorError(f"Finnhub API returned {resp.status}")
                    return await resp.json()
        except aiohttp.ClientError as e:
            logger.error("Network error fetching %s: %s", url, e)
            raise CollectorError(str(e)) from e
        except TimeoutError as e:
            logger.error("Timeout fetching %s", url)
            raise CollectorError("Request timed out") from e

    def _is_relevant(self, event_name: str) -> bool:
        """Check if an event name matches the configured relevant events list.

        See docs/sub-specs/SS-24.md §2

        Args:
            event_name: Event name from Finnhub.

        Returns:
            True if the event matches any relevant event keyword.
        """
        if not self._relevant_events:
            return True
        name_lower = event_name.lower()
        return any(kw.lower() in name_lower for kw in self._relevant_events)

    async def fetch_calendar(self) -> int:
        """Fetch economic calendar from Finnhub and insert new events.

        See docs/sub-specs/SS-24.md §2

        Returns:
            Count of newly inserted events. Returns 0 on failure.
        """
        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=self._lookback_days)).strftime("%Y-%m-%d")
        to_date = (now + timedelta(days=self._lookahead_days)).strftime("%Y-%m-%d")

        try:
            data = await self._get(FINNHUB_CALENDAR_URL, params={
                "from": from_date,
                "to": to_date,
            })
        except CollectorError as e:
            logger.warning("Finnhub calendar fetch failed: %s", e)
            return 0

        events = data.get("economicCalendar", [])
        if not events:
            logger.info("Finnhub: no events in response")
            return 0

        inserted = 0
        for evt in events:
            event_name = evt.get("event", "")
            if not event_name or not self._is_relevant(event_name):
                continue

            impact = evt.get("impact", "low")
            tier = _IMPACT_TO_TIER.get(impact, 3)
            date = evt.get("date", "")
            time_utc = evt.get("time", "00:00")

            if not date:
                continue

            # Idempotent: skip if date+event already exists
            existing = query(
                self._db_path,
                "SELECT id FROM macro_events WHERE date = ? AND event = ?",
                (date, event_name),
            )
            if existing:
                continue

            insert_row(self._db_path, "macro_events", {
                "date": date,
                "time_utc": time_utc,
                "event": event_name,
                "tier": tier,
                "forecast": evt.get("estimate"),
                "previous": evt.get("prev"),
                "actual": evt.get("actual"),
                "source": "finnhub",
            })
            inserted += 1

        logger.info(
            "Finnhub calendar: %d new events inserted (from %d total, %s to %s)",
            inserted, len(events), from_date, to_date,
        )
        return inserted
