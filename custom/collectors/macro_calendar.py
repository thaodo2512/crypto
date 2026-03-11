"""Forex Factory Economic Calendar collector — scheduled macro events.

See docs/sub-specs/SS-24.md §2
"""

import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from custom.collectors.spot import CollectorError
from custom.utils.db import insert_row, query

logger = logging.getLogger(__name__)

FOREX_FACTORY_URLS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]
REQUEST_TIMEOUT_SECONDS = 15

# Mapping from Forex Factory impact field to tier
_IMPACT_TO_TIER: dict[str, int] = {
    "High": 1,
    "Medium": 2,
    "Low": 3,
}


def _parse_ff_value(raw: Any) -> float | None:
    """Parse a Forex Factory forecast/actual/previous value to float.

    Handles strings like "3.2%", "250K", "-0.1%", or empty strings.
    """
    if raw is None:
        return None
    s = str(raw).strip().rstrip("%KMB")
    if not s or s == "":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


class ForexFactoryCalendarCollector:
    """Fetches scheduled economic events from Forex Factory calendar endpoint.

    See docs/sub-specs/SS-24.md §2

    Replaces static JSON calendar with live API data. Events flow into
    the same macro_events table and are picked up by event_risk automatically.
    """

    def __init__(self, config: dict, db_path: str) -> None:
        """Initialize the Forex Factory calendar collector.

        See docs/sub-specs/SS-24.md §2

        Args:
            config: Full settings dict.
            db_path: Path to SQLite database.
        """
        self._config = config
        self._db_path = db_path
        cal_cfg = config.get("economic_calendar", {})
        self._relevant_events: list[str] = cal_cfg.get("relevant_events", [])

    async def _get(self, url: str) -> Any:
        """Make GET request to Forex Factory endpoint.

        See docs/sub-specs/SS-24.md §2

        Args:
            url: Full URL to fetch.

        Returns:
            Parsed JSON response (list of event dicts).

        Raises:
            CollectorError: On non-200 status or network failure.
        """
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(
                            "Forex Factory API error: GET %s → %d: %s", url, resp.status, text
                        )
                        raise CollectorError(f"Forex Factory API returned {resp.status}")
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
            event_name: Event title from Forex Factory.

        Returns:
            True if the event matches any relevant event keyword.
        """
        if not self._relevant_events:
            return True
        name_lower = event_name.lower()
        return any(kw.lower() in name_lower for kw in self._relevant_events)

    def _upsert_event(self, evt: dict, date: str, time_utc: str, event_name: str, tier: int) -> bool:
        """Insert new event or update actual value for existing event.

        Args:
            evt: Raw Forex Factory event dict.
            date: Parsed date string (YYYY-MM-DD).
            time_utc: Parsed time string (HH:MM).
            event_name: Event title.
            tier: Event tier (1-3).

        Returns:
            True if a new event was inserted, False if updated or skipped.
        """
        actual = _parse_ff_value(evt.get("actual"))
        forecast = _parse_ff_value(evt.get("forecast"))
        previous = _parse_ff_value(evt.get("previous"))

        existing = query(
            self._db_path,
            "SELECT id, actual FROM macro_events WHERE date = ? AND event = ?",
            (date, event_name),
        )
        if existing:
            row = existing[0]
            # Update actual value if it's now available but wasn't before
            if actual is not None and row.get("actual") is None:
                query(
                    self._db_path,
                    "UPDATE macro_events SET actual = ?, surprise = ? WHERE id = ?",
                    (actual, (actual - forecast) if forecast is not None else None, row["id"]),
                )
                logger.debug("Updated actual for %s %s: %s", date, event_name, actual)
            return False

        insert_row(self._db_path, "macro_events", {
            "date": date,
            "time_utc": time_utc,
            "event": event_name,
            "tier": tier,
            "forecast": forecast,
            "previous": previous,
            "actual": actual,
            "source": "calendar",
        })
        return True

    async def fetch_calendar(self) -> int:
        """Fetch economic calendar from Forex Factory (this week + next week).

        See docs/sub-specs/SS-24.md §2

        Returns:
            Count of newly inserted events. Returns 0 on failure.
        """
        all_events: list[dict] = []
        for url in FOREX_FACTORY_URLS:
            try:
                data = await self._get(url)
                if data and isinstance(data, list):
                    all_events.extend(data)
            except CollectorError as e:
                logger.warning("Calendar fetch failed for %s: %s", url, e)

        if not all_events:
            logger.info("Forex Factory: no events from any endpoint")
            return 0

        inserted = 0
        for evt in all_events:
            # Filter to USD events only
            country = evt.get("country", "")
            if country != "USD":
                continue

            event_name = evt.get("title", "")
            if not event_name or not self._is_relevant(event_name):
                continue

            impact = evt.get("impact", "Low")
            tier = _IMPACT_TO_TIER.get(impact, 3)

            # Parse ISO 8601 date (e.g. "2026-03-11T08:30:00-04:00") → UTC
            date_str = evt.get("date", "")
            if not date_str:
                continue

            try:
                dt = datetime.fromisoformat(date_str)
                dt_utc = dt.astimezone(timezone.utc)
                date = dt_utc.strftime("%Y-%m-%d")
                time_utc = dt_utc.strftime("%H:%M")
            except (ValueError, TypeError):
                logger.warning("Skipping event with unparseable date: %s", date_str)
                continue

            if self._upsert_event(evt, date, time_utc, event_name, tier):
                inserted += 1

        logger.info(
            "Forex Factory calendar: %d new events inserted (from %d total)",
            inserted, len(all_events),
        )
        return inserted
