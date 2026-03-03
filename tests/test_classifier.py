"""Tests for SS-24: Haiku Headline Classifier.

See docs/sub-specs/SS-24.md §Acceptance Criteria
"""

import inspect
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom.ai.classifier import HeadlineClassifier


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def classifier_config() -> dict:
    """Config dict for headline classifier."""
    return {
        "haiku_classifier": {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 100,
            "max_daily_calls": 48,
        },
    }


@pytest.fixture
def classifier(classifier_config) -> HeadlineClassifier:
    """HeadlineClassifier with test config and API key."""
    return HeadlineClassifier("test-api-key", classifier_config)


def _mock_response(text: str) -> MagicMock:
    """Create a mock Anthropic API response."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


# ─── TestClassify ────────────────────────────────────────


class TestClassify:
    """Tests for classify()."""

    @pytest.mark.asyncio
    async def test_classify_tier1(self, classifier) -> None:
        """AC 6: Returns tier/event_name/active_hours for relevant headlines."""
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_response(
            json.dumps({"tier": 1, "event_name": "Tariff Shock", "active_hours": 8})
        ))
        classifier._client = mock_client

        result = await classifier.classify("Trump announces 50% tariffs on China")

        assert result is not None
        assert result["tier"] == 1
        assert result["event_name"] == "Tariff Shock"
        assert result["active_hours"] == 8

    @pytest.mark.asyncio
    async def test_classify_tier2(self, classifier) -> None:
        """Tier 2 classification."""
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_response(
            json.dumps({"tier": 2, "event_name": "ECB Rate Hold", "active_hours": 4})
        ))
        classifier._client = mock_client

        result = await classifier.classify("ECB holds rates as expected")

        assert result["tier"] == 2

    @pytest.mark.asyncio
    async def test_classify_irrelevant_returns_none(self, classifier) -> None:
        """AC 7: Irrelevant headlines (tier=null) return None."""
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_response(
            json.dumps({"tier": None, "event_name": "Sports", "active_hours": 0})
        ))
        classifier._client = mock_client

        result = await classifier.classify("Local team wins championship")

        assert result is None


# ─── TestRateLimiter ─────────────────────────────────────


class TestRateLimiter:
    """Tests for separate rate limiter."""

    @pytest.mark.asyncio
    async def test_separate_rate_limiter(self, classifier_config) -> None:
        """AC 10: Haiku has separate rate limiter from Sonnet."""
        from custom.ai.analyzer import RateLimiter

        c = HeadlineClassifier("test-key", classifier_config)
        assert isinstance(c.rate_limiter, RateLimiter)
        assert c.rate_limiter._max_daily == 48

    @pytest.mark.asyncio
    async def test_rate_limit_returns_none(self, classifier) -> None:
        """Returns None when rate limit reached."""
        # Exhaust rate limit
        for _ in range(48):
            classifier.rate_limiter.record_call()

        assert classifier.rate_limiter.can_call() is False

        result = await classifier.classify("Any headline")

        assert result is None


# ─── TestNoApiKey ────────────────────────────────────────


class TestNoApiKey:
    """Tests for missing API key."""

    @pytest.mark.asyncio
    async def test_no_api_key_returns_none(self, classifier_config) -> None:
        """Returns None when no API key configured."""
        c = HeadlineClassifier(None, classifier_config)

        result = await c.classify("Any headline")

        assert result is None


# ─── TestSummarizeRisk ───────────────────────────────────


class TestSummarizeRisk:
    """Tests for summarize_risk()."""

    @pytest.mark.asyncio
    async def test_summarize_risk_returns_narrative(self, classifier) -> None:
        """Returns narrative string for events."""
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_response(
            "FOMC is the key risk. Stay out until 1h after the decision."
        ))
        classifier._client = mock_client

        events = [
            {"event": "FOMC Rate Decision", "tier": 1, "hours_until": 1.5},
            {"event": "CPI", "tier": 1, "hours_until": 18.0},
        ]
        result = await classifier.summarize_risk(0.95, events)

        assert result is not None
        assert "FOMC" in result

    @pytest.mark.asyncio
    async def test_summarize_risk_no_events(self, classifier) -> None:
        """Returns None when no events."""
        result = await classifier.summarize_risk(0.10, [])
        assert result is None

    @pytest.mark.asyncio
    async def test_summarize_risk_no_api_key(self, classifier_config) -> None:
        """Returns None when no API key."""
        c = HeadlineClassifier(None, classifier_config)
        events = [{"event": "CPI", "tier": 1, "hours_until": 2.0}]
        result = await c.summarize_risk(0.80, events)
        assert result is None

    @pytest.mark.asyncio
    async def test_summarize_risk_api_failure(self, classifier) -> None:
        """Returns None on API failure."""
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))
        classifier._client = mock_client

        events = [{"event": "CPI", "tier": 1, "hours_until": 2.0}]
        result = await classifier.summarize_risk(0.80, events)
        assert result is None


# ─── TestErrorHandling ───────────────────────────────────


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_none(self, classifier) -> None:
        """AC 9: Returns None on unparseable response."""
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response("not valid json")
        )
        classifier._client = mock_client

        result = await classifier.classify("Some headline")

        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_tier_returns_none(self, classifier) -> None:
        """Returns None on invalid tier value."""
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_response(
            json.dumps({"tier": 5, "event_name": "Bad", "active_hours": 1})
        ))
        classifier._client = mock_client

        result = await classifier.classify("Some headline")

        assert result is None

    @pytest.mark.asyncio
    async def test_api_exception_returns_none(self, classifier) -> None:
        """AC 9: Returns None on API exception."""
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=Exception("API error")
        )
        classifier._client = mock_client

        result = await classifier.classify("Some headline")

        assert result is None


# ─── TestAsync ───────────────────────────────────────────


class TestAsync:
    """Tests for async compliance."""

    def test_classify_is_async(self) -> None:
        """classify() is async."""
        assert inspect.iscoroutinefunction(HeadlineClassifier.classify)
