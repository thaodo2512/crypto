"""FinancialJuice RSS collector — breaking news headlines.

See docs/sub-specs/SS-24.md §3
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import feedparser

from custom.ai.classifier import HeadlineClassifier
from custom.collectors.spot import CollectorError
from custom.utils.db import get_db, insert_row, query

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 15


class NewsRSSCollector:
    """Fetches breaking news from FinancialJuice RSS and classifies headlines.

    See docs/sub-specs/SS-24.md §3

    New headlines are classified by Haiku for BTC impact tier, then inserted
    into macro_events with source='rss'. Deduplication via news_rss_seen table.
    """

    def __init__(
        self, config: dict, db_path: str, classifier: HeadlineClassifier,
    ) -> None:
        """Initialize the RSS news collector.

        See docs/sub-specs/SS-24.md §3

        Args:
            config: Full settings dict.
            db_path: Path to SQLite database.
            classifier: HeadlineClassifier instance for tier classification.
        """
        self._config = config
        self._db_path = db_path
        self._classifier = classifier
        rss_cfg = config.get("news_rss", {})
        self._feed_url: str = rss_cfg.get(
            "feed_url", "https://www.financialjuice.com/feed.ashx"
        )
        self._active_window_hours: int = rss_cfg.get("active_window_hours", 4)
        self._max_age_hours: int = rss_cfg.get("max_age_hours", 24)

    async def _fetch_feed(self) -> str:
        """Fetch raw RSS feed content.

        See docs/sub-specs/SS-24.md §3

        Returns:
            Raw feed XML as string.

        Raises:
            CollectorError: On network failure or non-200 status.
        """
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self._feed_url) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(
                            "RSS feed error: %d: %s", resp.status, text[:200]
                        )
                        raise CollectorError(f"RSS feed returned {resp.status}")
                    return await resp.text()
        except aiohttp.ClientError as e:
            logger.error("Network error fetching RSS feed: %s", e)
            raise CollectorError(str(e)) from e
        except TimeoutError as e:
            logger.error("Timeout fetching RSS feed")
            raise CollectorError("Request timed out") from e

    def _get_guid(self, entry: Any) -> str:
        """Extract or generate a unique identifier for an RSS entry.

        See docs/sub-specs/SS-24.md §3

        Args:
            entry: feedparser entry object.

        Returns:
            Unique string identifier (guid, link, or title hash).
        """
        guid = getattr(entry, "id", None)
        if guid:
            return guid
        link = getattr(entry, "link", None)
        if link:
            return link
        title = getattr(entry, "title", "")
        return hashlib.sha256(title.encode()).hexdigest()

    def _is_seen(self, guid: str) -> bool:
        """Check if an RSS entry has already been processed.

        See docs/sub-specs/SS-24.md §3

        Args:
            guid: Unique identifier for the entry.

        Returns:
            True if already in news_rss_seen table.
        """
        rows = query(
            self._db_path,
            "SELECT id FROM news_rss_seen WHERE guid = ?",
            (guid,),
        )
        return len(rows) > 0

    def _mark_seen(self, guid: str, title: str) -> None:
        """Mark an RSS entry as seen.

        See docs/sub-specs/SS-24.md §3

        Args:
            guid: Unique identifier for the entry.
            title: Headline title for reference.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        insert_row(self._db_path, "news_rss_seen", {
            "guid": guid,
            "title": title[:500] if title else "",
            "seen_at": now,
        })

    def _cleanup_old_seen(self) -> None:
        """Remove entries older than max_age_hours from news_rss_seen.

        See docs/sub-specs/SS-24.md §3
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=self._max_age_hours * 7)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = get_db(self._db_path)
        try:
            conn.execute("DELETE FROM news_rss_seen WHERE seen_at < ?", (cutoff,))
            conn.commit()
        finally:
            conn.close()

    async def fetch_breaking_news(self) -> int:
        """Fetch RSS feed, classify new headlines, insert into macro_events.

        See docs/sub-specs/SS-24.md §3

        Returns:
            Count of newly inserted events. Returns 0 on failure.
        """
        try:
            raw = await self._fetch_feed()
        except CollectorError as e:
            logger.warning("RSS feed fetch failed: %s", e)
            return 0

        feed = feedparser.parse(raw)
        if not feed.entries:
            logger.info("RSS: no entries in feed")
            return 0

        now = datetime.now(timezone.utc)
        inserted = 0

        for entry in feed.entries:
            title = getattr(entry, "title", "").strip()
            if not title:
                continue

            guid = self._get_guid(entry)
            if self._is_seen(guid):
                continue

            # Mark as seen immediately to avoid reprocessing on next poll
            self._mark_seen(guid, title)

            # Classify via Haiku
            result = await self._classifier.classify(title)
            if result is None:
                continue

            # Insert into macro_events with active window
            event_time = now + timedelta(hours=result["active_hours"])
            insert_row(self._db_path, "macro_events", {
                "date": event_time.strftime("%Y-%m-%d"),
                "time_utc": event_time.strftime("%H:%M"),
                "event": result["event_name"],
                "tier": result["tier"],
                "source": "rss",
            })
            inserted += 1
            logger.info(
                "RSS headline classified: T%d '%s' (active %dh)",
                result["tier"], result["event_name"], result["active_hours"],
            )

        # Periodic cleanup of old seen entries
        self._cleanup_old_seen()

        logger.info(
            "RSS news: %d new events inserted (from %d feed entries)",
            inserted, len(feed.entries),
        )
        return inserted
