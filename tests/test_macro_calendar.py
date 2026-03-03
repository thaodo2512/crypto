"""Tests for SS-24: Finnhub Economic Calendar Collector.

See docs/sub-specs/SS-24.md §Acceptance Criteria
"""

import inspect
from unittest.mock import AsyncMock

import pytest

from custom.collectors.macro_calendar import FinnhubCalendarCollector
from custom.collectors.spot import CollectorError
from custom.utils.db import query


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def finnhub_config() -> dict:
    """Config dict for Finnhub collector."""
    return {
        "finnhub": {
            "calendar_interval_hours": 12,
            "lookahead_days": 14,
            "lookback_days": 7,
            "relevant_events": [
                "Interest Rate Decision",
                "CPI",
                "Non-Farm Payrolls",
                "GDP",
                "PCE Price Index",
                "PPI",
                "Initial Jobless Claims",
                "FOMC Minutes",
                "Retail Sales",
            ],
        },
    }


@pytest.fixture
def collector(finnhub_config, db_path) -> FinnhubCalendarCollector:
    """FinnhubCalendarCollector with test config and temp DB."""
    return FinnhubCalendarCollector(finnhub_config, db_path)


@pytest.fixture
def mock_finnhub_response() -> dict:
    """Sample Finnhub API response."""
    return {
        "economicCalendar": [
            {
                "date": "2026-03-11",
                "time": "13:30",
                "event": "CPI m/m",
                "impact": "high",
                "estimate": 0.3,
                "prev": 0.4,
                "actual": None,
            },
            {
                "date": "2026-03-18",
                "time": "19:00",
                "event": "Interest Rate Decision",
                "impact": "high",
                "estimate": 4.25,
                "prev": 4.50,
                "actual": None,
            },
            {
                "date": "2026-03-20",
                "time": "08:30",
                "event": "Initial Jobless Claims",
                "impact": "medium",
                "estimate": 220,
                "prev": 215,
                "actual": None,
            },
            {
                "date": "2026-03-15",
                "time": "10:00",
                "event": "University of Michigan Consumer Sentiment",
                "impact": "low",
                "estimate": 67.5,
                "prev": 68.0,
                "actual": None,
            },
        ],
    }


# ─── TestFetchCalendar ──────────────────────────────────


class TestFetchCalendar:
    """Tests for fetch_calendar()."""

    @pytest.mark.asyncio
    async def test_fetch_calendar_inserts_relevant_events(
        self, collector, db_path, mock_finnhub_response,
    ) -> None:
        """AC 1: Returns count of inserted events."""
        collector._get = AsyncMock(return_value=mock_finnhub_response)

        count = await collector.fetch_calendar()

        # 3 relevant (CPI, Interest Rate Decision, Jobless Claims)
        # UMich Consumer Sentiment is not in relevant_events list
        assert count == 3

        rows = query(db_path, "SELECT * FROM macro_events")
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_fetch_calendar_filters_irrelevant(
        self, collector, db_path, mock_finnhub_response,
    ) -> None:
        """AC 2: Filters to crypto-relevant events only."""
        collector._get = AsyncMock(return_value=mock_finnhub_response)

        await collector.fetch_calendar()

        rows = query(db_path, "SELECT event FROM macro_events")
        events = [r["event"] for r in rows]
        assert "University of Michigan Consumer Sentiment" not in events
        assert "CPI m/m" in events
        assert "Interest Rate Decision" in events

    @pytest.mark.asyncio
    async def test_fetch_calendar_idempotent(
        self, collector, db_path, mock_finnhub_response,
    ) -> None:
        """AC 3: Duplicate events are not re-inserted."""
        collector._get = AsyncMock(return_value=mock_finnhub_response)

        count1 = await collector.fetch_calendar()
        count2 = await collector.fetch_calendar()

        assert count1 == 3
        assert count2 == 0

        rows = query(db_path, "SELECT * FROM macro_events")
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_fetch_calendar_impact_to_tier_mapping(
        self, collector, db_path, mock_finnhub_response,
    ) -> None:
        """AC 8: Correct source and tier values."""
        collector._get = AsyncMock(return_value=mock_finnhub_response)

        await collector.fetch_calendar()

        rows = query(db_path, "SELECT * FROM macro_events ORDER BY date")
        cpi = [r for r in rows if "CPI" in r["event"]][0]
        assert cpi["tier"] == 1  # high impact
        assert cpi["source"] == "finnhub"

        claims = [r for r in rows if "Jobless" in r["event"]][0]
        assert claims["tier"] == 2  # medium impact

    @pytest.mark.asyncio
    async def test_fetch_calendar_includes_forecast_previous(
        self, collector, db_path, mock_finnhub_response,
    ) -> None:
        """Data includes forecast and previous values from Finnhub."""
        collector._get = AsyncMock(return_value=mock_finnhub_response)

        await collector.fetch_calendar()

        rows = query(
            db_path,
            "SELECT * FROM macro_events WHERE event = 'CPI m/m'",
        )
        assert len(rows) == 1
        assert rows[0]["forecast"] == 0.3
        assert rows[0]["previous"] == 0.4


# ─── TestGracefulDegradation ─────────────────────────────


class TestGracefulDegradation:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_fetch_calendar_api_failure(self, collector) -> None:
        """AC 9: Returns 0 on API failure."""
        collector._get = AsyncMock(side_effect=CollectorError("API down"))

        count = await collector.fetch_calendar()

        assert count == 0

    @pytest.mark.asyncio
    async def test_fetch_calendar_empty_response(self, collector) -> None:
        """AC 9: Returns 0 on empty response."""
        collector._get = AsyncMock(return_value={"economicCalendar": []})

        count = await collector.fetch_calendar()

        assert count == 0

    @pytest.mark.asyncio
    async def test_fetch_calendar_missing_key(self, collector) -> None:
        """AC 9: Returns 0 on missing key in response."""
        collector._get = AsyncMock(return_value={})

        count = await collector.fetch_calendar()

        assert count == 0


# ─── TestRelevanceFilter ─────────────────────────────────


class TestRelevanceFilter:
    """Tests for _is_relevant()."""

    def test_relevant_event_exact(self, collector) -> None:
        """Exact match returns True."""
        assert collector._is_relevant("CPI") is True

    def test_relevant_event_partial(self, collector) -> None:
        """Partial match returns True (keyword contained in name)."""
        assert collector._is_relevant("CPI m/m") is True
        assert collector._is_relevant("US Non-Farm Payrolls") is True

    def test_relevant_event_case_insensitive(self, collector) -> None:
        """Case-insensitive matching."""
        assert collector._is_relevant("cpi") is True
        assert collector._is_relevant("INTEREST RATE DECISION") is True

    def test_irrelevant_event(self, collector) -> None:
        """Non-matching event returns False."""
        assert collector._is_relevant("University of Michigan Sentiment") is False
        assert collector._is_relevant("Building Permits") is False

    def test_no_filter_accepts_all(self, db_path) -> None:
        """Empty relevant_events list accepts all events."""
        config = {"finnhub": {"relevant_events": []}}
        c = FinnhubCalendarCollector(config, db_path)
        assert c._is_relevant("Anything") is True


# ─── TestAsync ───────────────────────────────────────────


class TestAsync:
    """Tests for async compliance."""

    def test_methods_are_async(self) -> None:
        """All HTTP API calls use async."""
        assert inspect.iscoroutinefunction(FinnhubCalendarCollector.fetch_calendar)
        assert inspect.iscoroutinefunction(FinnhubCalendarCollector._get)
