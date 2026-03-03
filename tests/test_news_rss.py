"""Tests for SS-24: News RSS Collector.

See docs/sub-specs/SS-24.md §Acceptance Criteria
"""

import inspect
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom.ai.classifier import HeadlineClassifier
from custom.collectors.news_rss import NewsRSSCollector
from custom.collectors.spot import CollectorError
from custom.utils.db import query


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def rss_config() -> dict:
    """Config dict for RSS collector."""
    return {
        "news_rss": {
            "feed_url": "https://www.financialjuice.com/feed.ashx",
            "poll_interval_minutes": 15,
            "active_window_hours": 4,
            "max_age_hours": 24,
        },
        "haiku_classifier": {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 100,
            "max_daily_calls": 48,
        },
    }


@pytest.fixture
def mock_classifier() -> HeadlineClassifier:
    """Mock HeadlineClassifier that classifies all headlines as Tier 2."""
    classifier = MagicMock(spec=HeadlineClassifier)
    classifier.classify = AsyncMock(return_value={
        "tier": 2,
        "event_name": "Test Event",
        "active_hours": 4,
    })
    return classifier


@pytest.fixture
def collector(rss_config, db_path, mock_classifier) -> NewsRSSCollector:
    """NewsRSSCollector with test config and mocked classifier."""
    return NewsRSSCollector(rss_config, db_path, mock_classifier)


@pytest.fixture
def sample_rss_xml() -> str:
    """Sample RSS feed XML."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>FinancialJuice</title>
    <item>
      <title>Trump announces 25% tariffs on EU imports</title>
      <link>https://example.com/1</link>
      <guid>https://example.com/1</guid>
      <pubDate>Mon, 04 Mar 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>ECB holds rates steady as expected</title>
      <link>https://example.com/2</link>
      <guid>https://example.com/2</guid>
      <pubDate>Mon, 04 Mar 2026 11:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Local sports team wins championship</title>
      <link>https://example.com/3</link>
      <guid>https://example.com/3</guid>
      <pubDate>Mon, 04 Mar 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


# ─── TestFetchBreakingNews ───────────────────────────────


class TestFetchBreakingNews:
    """Tests for fetch_breaking_news()."""

    @pytest.mark.asyncio
    async def test_fetch_inserts_classified_events(
        self, collector, db_path, sample_rss_xml,
    ) -> None:
        """AC 4: Returns count of inserted events."""
        collector._fetch_feed = AsyncMock(return_value=sample_rss_xml)

        count = await collector.fetch_breaking_news()

        assert count == 3  # All 3 classified as Tier 2 by mock
        rows = query(db_path, "SELECT * FROM macro_events")
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_fetch_skips_irrelevant_headlines(
        self, collector, db_path, sample_rss_xml, mock_classifier,
    ) -> None:
        """AC 7: Headlines classified as None are not inserted."""
        # First headline relevant, rest irrelevant
        mock_classifier.classify = AsyncMock(side_effect=[
            {"tier": 1, "event_name": "Tariff Shock", "active_hours": 6},
            None,  # irrelevant
            None,  # irrelevant
        ])

        collector._fetch_feed = AsyncMock(return_value=sample_rss_xml)

        count = await collector.fetch_breaking_news()

        assert count == 1
        rows = query(db_path, "SELECT * FROM macro_events")
        assert len(rows) == 1
        assert rows[0]["event"] == "Tariff Shock"
        assert rows[0]["tier"] == 1

    @pytest.mark.asyncio
    async def test_fetch_source_is_rss(
        self, collector, db_path, sample_rss_xml,
    ) -> None:
        """AC 8: Events tagged with source='rss'."""
        collector._fetch_feed = AsyncMock(return_value=sample_rss_xml)

        await collector.fetch_breaking_news()

        rows = query(db_path, "SELECT source FROM macro_events")
        for row in rows:
            assert row["source"] == "rss"


# ─── TestDeduplication ───────────────────────────────────


class TestDeduplication:
    """Tests for RSS deduplication."""

    @pytest.mark.asyncio
    async def test_dedup_via_news_rss_seen(
        self, collector, db_path, sample_rss_xml,
    ) -> None:
        """AC 5: Duplicate RSS entries are not reprocessed."""
        collector._fetch_feed = AsyncMock(return_value=sample_rss_xml)

        count1 = await collector.fetch_breaking_news()
        count2 = await collector.fetch_breaking_news()

        assert count1 == 3
        assert count2 == 0

        # news_rss_seen should have 3 entries
        seen = query(db_path, "SELECT * FROM news_rss_seen")
        assert len(seen) == 3

    @pytest.mark.asyncio
    async def test_is_seen_and_mark_seen(self, collector, db_path) -> None:
        """Seen tracking works correctly."""
        assert collector._is_seen("test-guid-1") is False

        collector._mark_seen("test-guid-1", "Test Headline")

        assert collector._is_seen("test-guid-1") is True
        assert collector._is_seen("test-guid-2") is False


# ─── TestGuidExtraction ──────────────────────────────────


class TestGuidExtraction:
    """Tests for _get_guid()."""

    def test_guid_from_id(self, collector) -> None:
        """Uses entry.id when available."""
        entry = MagicMock()
        entry.id = "guid-123"
        assert collector._get_guid(entry) == "guid-123"

    def test_guid_from_link(self, collector) -> None:
        """Falls back to link when no id."""
        entry = MagicMock(spec=[])
        entry.link = "https://example.com/article"
        entry.id = None
        # _get_guid checks for id first via getattr
        delattr(entry, "id")
        entry = MagicMock()
        entry.id = None
        entry.link = "https://example.com/article"
        # When id is None (falsy), should use link
        result = collector._get_guid(entry)
        assert result == "https://example.com/article"

    def test_guid_from_title_hash(self, collector) -> None:
        """Falls back to title hash when no id or link."""
        entry = MagicMock()
        entry.id = None
        entry.link = None
        entry.title = "Some headline"
        result = collector._get_guid(entry)
        assert len(result) == 64  # SHA-256 hex digest


# ─── TestGracefulDegradation ─────────────────────────────


class TestGracefulDegradation:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_feed_fetch_failure(self, collector) -> None:
        """AC 9: Returns 0 on feed fetch failure."""
        collector._fetch_feed = AsyncMock(side_effect=CollectorError("Feed down"))

        count = await collector.fetch_breaking_news()

        assert count == 0

    @pytest.mark.asyncio
    async def test_empty_feed(self, collector) -> None:
        """AC 9: Returns 0 on empty feed."""
        collector._fetch_feed = AsyncMock(
            return_value='<?xml version="1.0"?><rss><channel></channel></rss>'
        )

        count = await collector.fetch_breaking_news()

        assert count == 0


# ─── TestAsync ───────────────────────────────────────────


class TestAsync:
    """Tests for async compliance."""

    def test_methods_are_async(self) -> None:
        """All HTTP calls use async."""
        assert inspect.iscoroutinefunction(NewsRSSCollector.fetch_breaking_news)
        assert inspect.iscoroutinefunction(NewsRSSCollector._fetch_feed)
