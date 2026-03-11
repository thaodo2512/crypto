"""Tests for SS-24: Forex Factory Economic Calendar Collector.

See docs/sub-specs/SS-24.md §Acceptance Criteria
"""

import inspect
from unittest.mock import AsyncMock

import pytest

from custom.collectors.macro_calendar import ForexFactoryCalendarCollector
from custom.collectors.spot import CollectorError
from custom.utils.db import query


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def calendar_config() -> dict:
    """Config dict for Forex Factory collector."""
    return {
        "economic_calendar": {
            "calendar_interval_hours": 12,
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
def collector(calendar_config, db_path) -> ForexFactoryCalendarCollector:
    """ForexFactoryCalendarCollector with test config and temp DB."""
    return ForexFactoryCalendarCollector(calendar_config, db_path)


@pytest.fixture
def mock_ff_response() -> list:
    """Sample Forex Factory API response."""
    return [
        {
            "title": "CPI m/m",
            "country": "USD",
            "date": "2026-03-11T08:30:00-04:00",
            "impact": "High",
            "forecast": "0.3%",
            "previous": "0.4%",
        },
        {
            "title": "Interest Rate Decision",
            "country": "USD",
            "date": "2026-03-18T14:00:00-04:00",
            "impact": "High",
            "forecast": "4.25%",
            "previous": "4.50%",
        },
        {
            "title": "Initial Jobless Claims",
            "country": "USD",
            "date": "2026-03-20T08:30:00-04:00",
            "impact": "Medium",
            "forecast": "220K",
            "previous": "215K",
        },
        {
            "title": "Consumer Sentiment",
            "country": "USD",
            "date": "2026-03-15T10:00:00-04:00",
            "impact": "Low",
            "forecast": "67.5",
            "previous": "68.0",
        },
        {
            "title": "EUR CPI m/m",
            "country": "EUR",
            "date": "2026-03-12T05:00:00-04:00",
            "impact": "High",
            "forecast": "0.2%",
            "previous": "0.3%",
        },
    ]


# ─── TestFetchCalendar ──────────────────────────────────


class TestFetchCalendar:
    """Tests for fetch_calendar()."""

    @pytest.mark.asyncio
    async def test_fetch_calendar_inserts_relevant_events(
        self, collector, db_path, mock_ff_response,
    ) -> None:
        """AC 1: Returns count of inserted events."""
        collector._get = AsyncMock(return_value=mock_ff_response)

        count = await collector.fetch_calendar()

        # 3 relevant USD events (CPI, Interest Rate Decision, Jobless Claims)
        # Consumer Sentiment not in relevant_events, EUR CPI filtered by country
        assert count == 3

        rows = query(db_path, "SELECT * FROM macro_events")
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_fetch_calendar_filters_non_usd(
        self, collector, db_path, mock_ff_response,
    ) -> None:
        """Filters out non-USD events."""
        collector._get = AsyncMock(return_value=mock_ff_response)

        await collector.fetch_calendar()

        rows = query(db_path, "SELECT event FROM macro_events")
        events = [r["event"] for r in rows]
        assert "EUR CPI m/m" not in events

    @pytest.mark.asyncio
    async def test_fetch_calendar_filters_irrelevant(
        self, collector, db_path, mock_ff_response,
    ) -> None:
        """AC 2: Filters to crypto-relevant events only."""
        collector._get = AsyncMock(return_value=mock_ff_response)

        await collector.fetch_calendar()

        rows = query(db_path, "SELECT event FROM macro_events")
        events = [r["event"] for r in rows]
        assert "Consumer Sentiment" not in events
        assert "CPI m/m" in events
        assert "Interest Rate Decision" in events

    @pytest.mark.asyncio
    async def test_fetch_calendar_idempotent(
        self, collector, db_path, mock_ff_response,
    ) -> None:
        """AC 3: Duplicate events are not re-inserted."""
        collector._get = AsyncMock(return_value=mock_ff_response)

        count1 = await collector.fetch_calendar()
        count2 = await collector.fetch_calendar()

        assert count1 == 3
        assert count2 == 0

        rows = query(db_path, "SELECT * FROM macro_events")
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_fetch_calendar_impact_to_tier_mapping(
        self, collector, db_path, mock_ff_response,
    ) -> None:
        """AC 8: Correct source and tier values."""
        collector._get = AsyncMock(return_value=mock_ff_response)

        await collector.fetch_calendar()

        rows = query(db_path, "SELECT * FROM macro_events ORDER BY date")
        cpi = [r for r in rows if "CPI" in r["event"]][0]
        assert cpi["tier"] == 1  # High impact
        assert cpi["source"] == "calendar"

        claims = [r for r in rows if "Jobless" in r["event"]][0]
        assert claims["tier"] == 2  # Medium impact

    @pytest.mark.asyncio
    async def test_fetch_calendar_date_converted_to_utc(
        self, collector, db_path, mock_ff_response,
    ) -> None:
        """ISO 8601 dates with timezone offset are converted to UTC."""
        collector._get = AsyncMock(return_value=mock_ff_response)

        await collector.fetch_calendar()

        rows = query(
            db_path,
            "SELECT * FROM macro_events WHERE event = 'CPI m/m'",
        )
        assert len(rows) == 1
        # 2026-03-11T08:30:00-04:00 → UTC = 12:30
        assert rows[0]["date"] == "2026-03-11"
        assert rows[0]["time_utc"] == "12:30"

    @pytest.mark.asyncio
    async def test_fetch_calendar_includes_forecast_previous(
        self, collector, db_path, mock_ff_response,
    ) -> None:
        """Data includes forecast and previous values from Forex Factory."""
        collector._get = AsyncMock(return_value=mock_ff_response)

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
        collector._get = AsyncMock(return_value=[])

        count = await collector.fetch_calendar()

        assert count == 0

    @pytest.mark.asyncio
    async def test_fetch_calendar_non_list_response(self, collector) -> None:
        """AC 9: Returns 0 on non-list response."""
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
        config = {"economic_calendar": {"relevant_events": []}}
        c = ForexFactoryCalendarCollector(config, db_path)
        assert c._is_relevant("Anything") is True


# ─── TestAsync ───────────────────────────────────────────


class TestAsync:
    """Tests for async compliance."""

    def test_methods_are_async(self) -> None:
        """All HTTP API calls use async."""
        assert inspect.iscoroutinefunction(ForexFactoryCalendarCollector.fetch_calendar)
        assert inspect.iscoroutinefunction(ForexFactoryCalendarCollector._get)
