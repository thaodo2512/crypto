"""Haiku headline classifier — AI-based tier classification for RSS headlines.

See docs/sub-specs/SS-24.md §3
"""

import json
import logging
from typing import Any

from custom.ai.analyzer import RateLimiter

logger = logging.getLogger(__name__)

_CLASSIFY_PROMPT = """\
You are a crypto market impact classifier. Given a news headline, classify its \
potential impact on BTC price.

Respond with ONLY a JSON object (no markdown, no explanation):
{{"tier": 1, "event_name": "short name", "active_hours": 4}}

Rules:
- tier 1: Major impact, >2% BTC move expected (FOMC surprise, major hack, \
war escalation, tariff shock, major regulatory action)
- tier 2: Moderate impact, 1-2% move (secondary economic data, exchange issues, \
notable regulatory news)
- tier 3: Minor impact, <1% move (minor economic data, routine announcements)
- tier null: Not crypto-relevant (sports, entertainment, local news)

- event_name: 2-5 word summary of the event
- active_hours: how long this event will impact markets (1-24)

Headline: {headline}
"""


class HeadlineClassifier:
    """Classify news headlines using Claude Haiku for BTC impact tier.

    See docs/sub-specs/SS-24.md §3

    Uses a separate RateLimiter from the Sonnet analyzer (48/day vs 10/day)
    to prevent news classification from starving AI analysis.
    """

    def __init__(self, api_key: str | None, config: dict):
        """Initialize the headline classifier.

        See docs/sub-specs/SS-24.md §3

        Args:
            api_key: Anthropic API key.
            config: Full settings dict.
        """
        self.api_key = api_key
        haiku_cfg = config.get("haiku_classifier", {})
        self.model = haiku_cfg.get("model", "claude-haiku-4-5-20251001")
        self.max_tokens = haiku_cfg.get("max_tokens", 100)
        self.rate_limiter = RateLimiter(haiku_cfg.get("max_daily_calls", 48))
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-init the Anthropic async client.

        See docs/sub-specs/SS-24.md §3
        """
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                timeout=15.0,
                max_retries=2,
            )
        return self._client

    async def classify(self, headline: str) -> dict | None:
        """Classify a news headline for BTC impact.

        See docs/sub-specs/SS-24.md §3

        Args:
            headline: News headline text.

        Returns:
            Dict with tier (1|2|3), event_name, active_hours,
            or None if irrelevant or on failure.
        """
        if not self.api_key:
            logger.warning("Headline classifier disabled — no API key")
            return None

        if not self.rate_limiter.can_call():
            logger.warning(
                "Headline classifier rate limit reached (%d remaining)",
                self.rate_limiter.remaining(),
            )
            return None

        try:
            client = self._get_client()
            response = await client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{
                    "role": "user",
                    "content": _CLASSIFY_PROMPT.format(headline=headline),
                }],
            )
            self.rate_limiter.record_call()

            text = response.content[0].text.strip()
            result = json.loads(text)

            tier = result.get("tier")
            if tier is None:
                logger.debug("Headline classified as irrelevant: %s", headline[:80])
                return None

            if tier not in (1, 2, 3):
                logger.warning("Invalid tier %s for headline: %s", tier, headline[:80])
                return None

            return {
                "tier": int(tier),
                "event_name": str(result.get("event_name", headline[:50])),
                "active_hours": int(result.get("active_hours", 4)),
            }

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("Failed to parse classifier response for '%s': %s", headline[:80], e)
            return None
        except Exception as e:
            logger.error("Headline classification failed: %s", e)
            return None

    async def summarize_risk(
        self, risk_score: float, events: list[dict],
    ) -> str | None:
        """Generate a brief AI narrative about the current risk situation.

        See docs/sub-specs/SS-24.md §3

        Args:
            risk_score: Overall event risk score (0-1).
            events: List of upcoming macro event dicts.

        Returns:
            Short English narrative string, or None on failure.
        """
        if not self.api_key:
            return None

        if not self.rate_limiter.can_call():
            return None

        if not events:
            return None

        events_text = "\n".join(
            f"- T{e.get('tier', 3)} {e.get('event', '?')} in {e.get('hours_until', 0):.1f}h"
            for e in events[:5]
        )

        prompt = (
            f"Event risk score: {risk_score:.2f}/1.00\n"
            f"Upcoming events:\n{events_text}\n\n"
            "In 2-3 sentences, explain the risk situation for a BTC swing trader. "
            "Which event matters most and why? Should they stay out or is it safe "
            "to trade? Be direct and specific. Respond in English."
        )

        try:
            client = self._get_client()
            response = await client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            self.rate_limiter.record_call()
            return response.content[0].text.strip()
        except Exception as e:
            logger.error("Risk narrative generation failed: %s", e)
            return None
