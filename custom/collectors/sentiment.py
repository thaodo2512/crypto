"""Sentiment & macro economic data collector.

See docs/sub-specs/SS-05.md §3.5, §8
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

from custom.collectors.spot import CollectorError
from custom.utils.db import get_db, insert_row, query

logger = logging.getLogger(__name__)

FNG_URL = "https://api.alternative.me/fng/"
FRED_URL = "https://api.stlouisfed.org"
REQUEST_TIMEOUT_SECONDS = 10

_INFLATION_EVENTS = {"CPI", "PCE Price Index", "PPI"}
_JOBS_EVENTS = {"Non-Farm Payrolls"}


class SentimentCollector:
    """Collects sentiment and macro economic data.

    See docs/sub-specs/SS-05.md §3.5, §8
    """

    def __init__(self, config: dict, db_path: str) -> None:
        """Initialize the sentiment collector.

        See docs/sub-specs/SS-05.md

        Args:
            config: Full settings dict.
            db_path: Path to SQLite database.
        """
        self._config = config
        self._db_path = db_path
        self._macro_cfg = config["macro_events"]

    async def _get(self, url: str, params: dict | None = None) -> Any:
        """Make GET request to external API.

        See docs/sub-specs/SS-05.md

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
                        logger.error("API error: GET %s → %d: %s", url, resp.status, text)
                        raise CollectorError(f"API returned {resp.status}")
                    return await resp.json()
        except aiohttp.ClientError as e:
            logger.error("Network error fetching %s: %s", url, e)
            raise CollectorError(str(e)) from e
        except TimeoutError as e:
            logger.error("Timeout fetching %s", url)
            raise CollectorError("Request timed out") from e

    async def fetch_fear_greed(self) -> dict[str, Any] | None:
        """Fetch Fear & Greed Index from Alternative.me.

        See docs/sub-specs/SS-05.md §3.5

        Returns:
            Dict with value (int 0-100) and classification, or None on failure.
        """
        try:
            data = await self._get(FNG_URL)
            item = data["data"][0]
            value = int(item["value"])
            classification = item["value_classification"]

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            existing = query(
                self._db_path,
                "SELECT id FROM daily_snapshot WHERE date = ?",
                (today,),
            )
            if existing:
                conn = get_db(self._db_path)
                try:
                    conn.execute(
                        "UPDATE daily_snapshot SET fear_greed = ? WHERE date = ?",
                        (value, today),
                    )
                    conn.commit()
                finally:
                    conn.close()
            else:
                insert_row(self._db_path, "daily_snapshot", {
                    "date": today,
                    "fear_greed": value,
                })

            logger.info("Fear & Greed: %d (%s)", value, classification)
            return {"value": value, "classification": classification}
        except (CollectorError, KeyError, IndexError, TypeError, ValueError) as e:
            logger.warning("Fear & Greed unavailable: %s", e)
            return None

    def load_macro_calendar(
        self, calendar_path: str = "config/macro_events_2026.json"
    ) -> int:
        """Load macro events from JSON file into macro_events table.

        See docs/sub-specs/SS-05.md §8

        Args:
            calendar_path: Path to the macro events JSON file.

        Returns:
            Count of newly inserted events.
        """
        try:
            with open(calendar_path, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error("Failed to load macro calendar from %s: %s", calendar_path, e)
            return 0

        events = data.get("events", [])
        inserted = 0
        for evt in events:
            date = evt.get("date")
            event_name = evt.get("event")
            if not date or not event_name:
                continue

            existing = query(
                self._db_path,
                "SELECT id FROM macro_events WHERE date = ? AND event = ?",
                (date, event_name),
            )
            if existing:
                continue

            insert_row(self._db_path, "macro_events", {
                "date": date,
                "time_utc": evt.get("time_utc", "00:00"),
                "event": event_name,
                "tier": evt.get("tier", 3),
                "source": "static",
            })
            inserted += 1

        logger.info("Loaded macro calendar: %d new events (from %d total)", inserted, len(events))
        return inserted

    def get_upcoming_events(self, hours_ahead: int = 48) -> list[dict[str, Any]]:
        """Get macro events within the next N hours.

        See docs/sub-specs/SS-05.md §8

        Args:
            hours_ahead: Number of hours to look ahead.

        Returns:
            List of event dicts sorted by hours_until ascending.
        """
        now = datetime.now(timezone.utc)
        rows = query(
            self._db_path,
            "SELECT date, time_utc, event, tier, source FROM macro_events",
        )

        results = []
        for row in rows:
            try:
                event_dt = datetime.strptime(
                    f"{row['date']}T{row['time_utc']}", "%Y-%m-%dT%H:%M"
                ).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            hours_until = (event_dt - now).total_seconds() / 3600
            if hours_until <= 0 or hours_until > hours_ahead:
                continue
            results.append({
                "event": row["event"],
                "tier": row["tier"],
                "date": row["date"],
                "time_utc": row["time_utc"],
                "hours_until": round(hours_until, 2),
                "source": row.get("source", "static"),
            })

        results.sort(key=lambda x: x["hours_until"])
        return results

    def get_next_event(self) -> dict[str, Any] | None:
        """Get the single closest upcoming macro event.

        See docs/sub-specs/SS-05.md §8

        Returns:
            Event dict or None if no events within 48 hours.
        """
        upcoming = self.get_upcoming_events(hours_ahead=48)
        if not upcoming:
            return None
        return upcoming[0]

    async def fetch_cpi_actual(self) -> float | None:
        """Fetch latest CPI actual value from FRED API.

        See docs/sub-specs/SS-05.md §8

        Returns:
            CPI value as float, or None on failure.
        """
        api_key = os.environ.get("FRED_API_KEY")
        if not api_key:
            logger.warning("FRED_API_KEY not set — cannot fetch CPI actual")
            return None

        try:
            data = await self._get(
                f"{FRED_URL}/fred/series/observations",
                params={
                    "series_id": "CPIAUCSL",
                    "sort_order": "desc",
                    "limit": "1",
                    "api_key": api_key,
                    "file_type": "json",
                },
            )
            value = float(data["observations"][0]["value"])
            logger.info("FRED CPI actual: %.1f", value)
            return value
        except (CollectorError, KeyError, IndexError, TypeError, ValueError) as e:
            logger.warning("FRED CPI unavailable: %s", e)
            return None

    def classify_surprise(
        self, event_type: str, actual: float, forecast: float
    ) -> str:
        """Classify the surprise impact of a macro data release.

        See docs/sub-specs/SS-05.md §8.4

        Args:
            event_type: Event name (e.g. "CPI", "Non-Farm Payrolls").
            actual: Actual released value.
            forecast: Consensus forecast value.

        Returns:
            Impact classification string.
        """
        surprise = actual - forecast

        if event_type in _INFLATION_EVENTS:
            very_bearish = self._macro_cfg["inflation_very_bearish"]
            bearish = self._macro_cfg["inflation_bearish"]
            bullish = self._macro_cfg["inflation_bullish"]
            very_bullish = self._macro_cfg["inflation_very_bullish"]

            if surprise > very_bearish:
                return "VERY_BEARISH"
            if surprise > bearish:
                return "BEARISH"
            if surprise >= bullish:
                return "NEUTRAL"
            if surprise >= very_bullish:
                return "BULLISH"
            return "VERY_BULLISH"

        if event_type in _JOBS_EVENTS:
            bearish_threshold = self._macro_cfg["nfp_bearish_threshold"]
            bullish_range = self._macro_cfg["nfp_bullish_range"]
            very_bearish_threshold = self._macro_cfg["nfp_very_bearish_threshold"]

            if surprise > bearish_threshold:
                return "BEARISH"
            if surprise > bullish_range[0]:
                return "NEUTRAL"
            if surprise >= very_bearish_threshold:
                return "BULLISH"
            return "VERY_BEARISH"

        logger.warning("Unknown event type for classify_surprise: %s", event_type)
        return "NEUTRAL"

    def update_event_actual(
        self, date: str, event: str, actual: float, forecast: float
    ) -> str:
        """Update a macro event with actual data and classify impact.

        See docs/sub-specs/SS-05.md §8

        Args:
            date: Event date (YYYY-MM-DD).
            event: Event name.
            actual: Actual released value.
            forecast: Consensus forecast value.

        Returns:
            Impact classification string.
        """
        surprise = actual - forecast
        impact = self.classify_surprise(event, actual, forecast)

        conn = get_db(self._db_path)
        try:
            conn.execute(
                "UPDATE macro_events SET actual = ?, forecast = ?, surprise = ?, impact = ? "
                "WHERE date = ? AND event = ?",
                (actual, forecast, surprise, impact, date, event),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info(
            "Updated %s on %s: actual=%.2f forecast=%.2f surprise=%.2f impact=%s",
            event, date, actual, forecast, surprise, impact,
        )
        return impact
