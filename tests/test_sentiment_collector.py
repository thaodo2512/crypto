"""Tests for SS-05: Sentiment & Macro Collector.

See docs/sub-specs/SS-05.md §Acceptance Criteria
"""

import inspect
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from custom.collectors.sentiment import SentimentCollector
from custom.collectors.spot import CollectorError
from custom.utils.db import insert_row, query


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def sentiment_config() -> dict:
    """Config dict for sentiment collector."""
    return {
        "macro_events": {
            "tier1_imminent_hours": 2,
            "tier1_warning_hours": 6,
            "tier1_alert_hours": 24,
            "tier2_imminent_hours": 2,
            "tier2_warning_hours": 6,
            "tier3_imminent_hours": 2,
            "inflation_very_bearish": 0.2,
            "inflation_bearish": 0.1,
            "inflation_bullish": -0.1,
            "inflation_very_bullish": -0.2,
            "nfp_bearish_threshold": 100,
            "nfp_bullish_range": [50, -50],
            "nfp_very_bearish_threshold": -50,
        },
    }


@pytest.fixture
def collector(sentiment_config, db_path) -> SentimentCollector:
    """SentimentCollector with test config and temp DB."""
    return SentimentCollector(sentiment_config, db_path)


@pytest.fixture
def calendar_file(tmp_path) -> str:
    """Create a temp macro events JSON file."""
    data = {
        "events": [
            {"date": "2026-03-11", "time_utc": "13:30", "event": "CPI", "tier": 1},
            {"date": "2026-03-18", "time_utc": "19:00", "event": "FOMC Rate Decision", "tier": 1},
            {"date": "2026-03-27", "time_utc": "13:30", "event": "PCE Price Index", "tier": 2},
        ]
    }
    path = tmp_path / "test_calendar.json"
    path.write_text(json.dumps(data))
    return str(path)


# ─── TestFetchFearGreed ──────────────────────────────────


class TestFetchFearGreed:
    """Tests for fetch_fear_greed()."""

    @pytest.mark.asyncio
    async def test_fetch_fear_greed(self, collector, db_path) -> None:
        """AC 1: Returns value (0-100) and classification string."""
        collector._get = AsyncMock(return_value={
            "data": [{"value": "72", "value_classification": "Greed"}],
        })

        result = await collector.fetch_fear_greed()

        assert result is not None
        assert result["value"] == 72
        assert result["classification"] == "Greed"
        assert 0 <= result["value"] <= 100

        rows = query(db_path, "SELECT * FROM daily_snapshot")
        assert len(rows) == 1
        assert rows[0]["fear_greed"] == 72

    @pytest.mark.asyncio
    async def test_fetch_fear_greed_api_failure(self, collector) -> None:
        """AC 2: Returns None when API fails."""
        collector._get = AsyncMock(side_effect=CollectorError("API down"))

        result = await collector.fetch_fear_greed()

        assert result is None


# ─── TestLoadMacroCalendar ───────────────────────────────


class TestLoadMacroCalendar:
    """Tests for load_macro_calendar()."""

    def test_load_macro_calendar(self, collector, db_path, calendar_file) -> None:
        """AC 3: Inserts events from JSON into macro_events table."""
        count = collector.load_macro_calendar(calendar_path=calendar_file)

        assert count == 3

        rows = query(db_path, "SELECT * FROM macro_events")
        assert len(rows) == 3

        cpi = [r for r in rows if r["event"] == "CPI"]
        assert len(cpi) == 1
        assert cpi[0]["date"] == "2026-03-11"
        assert cpi[0]["tier"] == 1
        assert cpi[0]["time_utc"] == "13:30"

    def test_load_macro_calendar_idempotent(
        self, collector, db_path, calendar_file
    ) -> None:
        """AC 4: Skips duplicate events (idempotent)."""
        count1 = collector.load_macro_calendar(calendar_path=calendar_file)
        count2 = collector.load_macro_calendar(calendar_path=calendar_file)

        assert count1 == 3
        assert count2 == 0

        rows = query(db_path, "SELECT * FROM macro_events")
        assert len(rows) == 3


# ─── TestGetUpcomingEvents ───────────────────────────────


class TestGetUpcomingEvents:
    """Tests for get_upcoming_events()."""

    def test_get_upcoming_events_sorted(self, collector, db_path) -> None:
        """AC 5: Returns events within N hours, sorted by hours_until."""
        now = datetime.now(timezone.utc)

        # Insert events at known future times
        for hours, event, tier in [
            (12, "CPI", 1),
            (3, "FOMC Rate Decision", 1),
            (36, "PCE Price Index", 2),
        ]:
            future = now + timedelta(hours=hours)
            insert_row(db_path, "macro_events", {
                "date": future.strftime("%Y-%m-%d"),
                "time_utc": future.strftime("%H:%M"),
                "event": event,
                "tier": tier,
            })

        result = collector.get_upcoming_events(hours_ahead=48)

        assert len(result) == 3
        # Sorted by hours_until ascending
        assert result[0]["event"] == "FOMC Rate Decision"
        assert result[1]["event"] == "CPI"
        assert result[2]["event"] == "PCE Price Index"
        assert result[0]["hours_until"] < result[1]["hours_until"]
        assert result[1]["hours_until"] < result[2]["hours_until"]

    def test_get_upcoming_events_empty(self, collector) -> None:
        """AC 6: Returns empty list when no events upcoming."""
        result = collector.get_upcoming_events(hours_ahead=48)

        assert result == []


# ─── TestGetNextEvent ────────────────────────────────────


class TestGetNextEvent:
    """Tests for get_next_event()."""

    def test_get_next_event(self, collector, db_path) -> None:
        """AC 7: Returns closest event or None."""
        now = datetime.now(timezone.utc)

        for hours, event, tier in [
            (24, "CPI", 1),
            (6, "FOMC Rate Decision", 1),
        ]:
            future = now + timedelta(hours=hours)
            insert_row(db_path, "macro_events", {
                "date": future.strftime("%Y-%m-%d"),
                "time_utc": future.strftime("%H:%M"),
                "event": event,
                "tier": tier,
            })

        result = collector.get_next_event()

        assert result is not None
        assert result["event"] == "FOMC Rate Decision"
        assert result["tier"] == 1
        assert result["hours_until"] < 7


# ─── TestFetchCpiActual ──────────────────────────────────


class TestFetchCpiActual:
    """Tests for fetch_cpi_actual()."""

    @pytest.mark.asyncio
    async def test_fetch_cpi_actual(self, collector) -> None:
        """AC 8: Returns float from FRED API."""
        collector._get = AsyncMock(return_value={
            "observations": [{"date": "2026-02-01", "value": "312.345"}],
        })

        with patch.dict(os.environ, {"FRED_API_KEY": "test_key_123"}):
            result = await collector.fetch_cpi_actual()

        assert result == 312.345
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_fetch_cpi_actual_failure(self, collector) -> None:
        """AC 9: Returns None when FRED API fails or key missing."""
        # Case 1: Missing API key
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("FRED_API_KEY", None)
            result = await collector.fetch_cpi_actual()
            assert result is None

        # Case 2: API error
        collector._get = AsyncMock(side_effect=CollectorError("FRED down"))
        with patch.dict(os.environ, {"FRED_API_KEY": "test_key"}):
            result = await collector.fetch_cpi_actual()
            assert result is None


# ─── TestClassifySurprise ────────────────────────────────


class TestClassifySurprise:
    """Tests for classify_surprise()."""

    def test_classify_inflation_surprise(self, collector) -> None:
        """AC 10: Correctly classifies inflation surprises (5 tiers)."""
        # Thresholds: very_bearish=0.2, bearish=0.1, bullish=-0.1, very_bullish=-0.2

        # VERY_BEARISH: surprise > 0.2
        assert collector.classify_surprise("CPI", 3.5, 3.2) == "VERY_BEARISH"

        # BEARISH: 0.1 < surprise <= 0.2
        assert collector.classify_surprise("CPI", 3.25, 3.1) == "BEARISH"

        # NEUTRAL: -0.1 <= surprise <= 0.1
        assert collector.classify_surprise("CPI", 3.15, 3.1) == "NEUTRAL"
        assert collector.classify_surprise("PCE Price Index", 3.0, 3.0) == "NEUTRAL"

        # BULLISH: -0.2 <= surprise < -0.1
        assert collector.classify_surprise("PPI", 2.85, 3.0) == "BULLISH"

        # VERY_BULLISH: surprise < -0.2
        assert collector.classify_surprise("CPI", 2.7, 3.0) == "VERY_BULLISH"

    def test_classify_nfp_surprise(self, collector) -> None:
        """AC 11: Correctly classifies NFP surprises (4 tiers)."""
        # Thresholds: bearish=100, bullish_range=[50,-50], very_bearish=-50

        # BEARISH: surprise > 100
        assert collector.classify_surprise("Non-Farm Payrolls", 350, 200) == "BEARISH"

        # NEUTRAL: 50 < surprise <= 100
        assert collector.classify_surprise("Non-Farm Payrolls", 275, 200) == "NEUTRAL"

        # BULLISH: -50 <= surprise <= 50
        assert collector.classify_surprise("Non-Farm Payrolls", 220, 200) == "BULLISH"
        assert collector.classify_surprise("Non-Farm Payrolls", 200, 200) == "BULLISH"

        # VERY_BEARISH: surprise < -50
        assert collector.classify_surprise("Non-Farm Payrolls", 100, 200) == "VERY_BEARISH"


# ─── TestUpdateEventActual ───────────────────────────────


class TestUpdateEventActual:
    """Tests for update_event_actual()."""

    def test_update_event_actual(self, collector, db_path) -> None:
        """AC 12: Updates macro_events row with actual, surprise, impact."""
        insert_row(db_path, "macro_events", {
            "date": "2026-03-11",
            "time_utc": "13:30",
            "event": "CPI",
            "tier": 1,
        })

        impact = collector.update_event_actual(
            date="2026-03-11",
            event="CPI",
            actual=3.5,
            forecast=3.2,
        )

        assert impact == "VERY_BEARISH"

        rows = query(
            db_path,
            "SELECT * FROM macro_events WHERE date = '2026-03-11' AND event = 'CPI'",
        )
        assert len(rows) == 1
        assert rows[0]["actual"] == 3.5
        assert rows[0]["forecast"] == 3.2
        assert abs(rows[0]["surprise"] - 0.3) < 0.001
        assert rows[0]["impact"] == "VERY_BEARISH"


# ─── TestConfig ──────────────────────────────────────────


class TestConfig:
    """Tests for config usage."""

    def test_thresholds_from_config(self, db_path) -> None:
        """AC 13: All thresholds read from config, not hardcoded."""
        config = {
            "macro_events": {
                "inflation_very_bearish": 0.3,
                "inflation_bearish": 0.15,
                "inflation_bullish": -0.15,
                "inflation_very_bullish": -0.3,
                "nfp_bearish_threshold": 150,
                "nfp_bullish_range": [75, -75],
                "nfp_very_bearish_threshold": -75,
            },
        }
        c = SentimentCollector(config, db_path)

        # With custom thresholds, 0.2 surprise should be BEARISH (not VERY_BEARISH)
        assert c.classify_surprise("CPI", 3.2, 3.0) == "BEARISH"

        # With custom NFP threshold, 120 surprise should be NEUTRAL (not BEARISH)
        assert c.classify_surprise("Non-Farm Payrolls", 320, 200) == "NEUTRAL"


# ─── TestAsync ───────────────────────────────────────────


class TestAsync:
    """Tests for async compliance."""

    def test_methods_are_async(self) -> None:
        """AC 14: All HTTP API calls use aiohttp (async)."""
        assert inspect.iscoroutinefunction(SentimentCollector.fetch_fear_greed)
        assert inspect.iscoroutinefunction(SentimentCollector.fetch_cpi_actual)
        assert inspect.iscoroutinefunction(SentimentCollector._get)


# ─── TestEdgeCases ───────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_unknown_event_type_neutral(self, collector) -> None:
        """Edge: Unknown event type returns NEUTRAL."""
        result = collector.classify_surprise("Unknown Event", 100, 90)
        assert result == "NEUTRAL"

    def test_calendar_file_not_found(self, collector) -> None:
        """Edge: Missing JSON file returns 0."""
        count = collector.load_macro_calendar(calendar_path="/nonexistent/file.json")
        assert count == 0

    def test_get_next_event_none(self, collector) -> None:
        """Edge: No events upcoming returns None."""
        result = collector.get_next_event()
        assert result is None
