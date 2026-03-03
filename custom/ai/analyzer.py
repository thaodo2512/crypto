"""AI Analysis Layer — Claude API prompt builder and analyzer.

See docs/sub-specs/SS-19.md §11
"""

import logging
from datetime import datetime, timezone
from typing import Any

from custom.utils.db import get_latest, query

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a crypto market analyst assistant embedded in an automated signal \
system. Your role is to interpret quantitative data and provide clear, \
actionable analysis for a swing trader.

RULES:
1. You receive structured market data from the signal system. This data \
is REAL and CURRENT — trust it.
2. Be direct and concise. Lead with the conclusion, then explain.
3. Always state your confidence level and what could invalidate your view.
4. When signals conflict, explain WHY they conflict and which one \
matters most in the current context.
5. Never fabricate data. Only reference numbers provided in the data payload.
6. Flag risks the quantitative system might miss: narrative shifts, \
correlation breakdowns, unusual patterns in the data.
7. Keep response under 400 words for daily briefing, under 200 words \
for alerts.
8. Use Vietnamese language for all responses.
9. Format for Telegram (plain text, use emoji sparingly, no markdown headers).

TRADING CONTEXT:
- Asset: BTC/USDT
- Style: Swing trade (1-5 day holds)
- Risk: 1-2% per trade, max 3x leverage
"""

_DAILY_QUESTION = (
    "Based on all the data above, provide:\n"
    "1. Your overall market read for the next 24-48h (2-3 sentences)\n"
    "2. The single most important thing the trader should pay attention to today\n"
    "3. If there is a trade setup, describe it. If not, explain why sitting out is correct.\n"
    "4. One risk or scenario the quantitative signals might be missing"
)


class RateLimiter:
    """Track daily API call count. Max 10 calls/day (IMMUTABLE).

    See docs/sub-specs/SS-19.md §11
    """

    def __init__(self, max_daily: int = 10):
        self._max_daily = max_daily
        self._calls: list[datetime] = []

    def can_call(self) -> bool:
        """Check if a call is allowed."""
        self._prune()
        return len(self._calls) < self._max_daily

    def record_call(self) -> None:
        """Record a call."""
        self._calls.append(datetime.now(timezone.utc))

    def remaining(self) -> int:
        """Return remaining calls today."""
        self._prune()
        return max(0, self._max_daily - len(self._calls))

    def _prune(self) -> None:
        """Remove calls older than 24h."""
        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        self._calls = [c for c in self._calls if c >= cutoff]


class AIPromptBuilder:
    """Builds structured prompts from system data for Claude API.

    See docs/sub-specs/SS-19.md §11.3
    """

    def __init__(self, db_path: str, config: dict):
        self.db_path = db_path
        self.config = config

    def build_daily_briefing(self) -> dict[str, str]:
        """Build the full daily analysis prompt.

        See docs/sub-specs/SS-19.md §11.4

        Returns:
            Dict with 'system' and 'user' prompt strings.
        """
        payload = self._build_data_payload()
        return {
            "system": _SYSTEM_PROMPT,
            "user": payload + f"\n=== QUESTION ===\n{_DAILY_QUESTION}",
        }

    def build_signal_change(self, old_score: float, new_score: float) -> dict[str, str]:
        """Build prompt for signal threshold crossing.

        See docs/sub-specs/SS-19.md §11.4

        Args:
            old_score: Previous signal score.
            new_score: New signal score.

        Returns:
            Dict with 'system' and 'user' prompt strings.
        """
        payload = self._build_data_payload()
        question = (
            f"Signal just changed from {old_score:.2f} to {new_score:.2f}. "
            "What caused this shift? Is it meaningful or noise? "
            "Should the trader act on it?"
        )
        return {
            "system": _SYSTEM_PROMPT,
            "user": payload + f"\n=== QUESTION ===\n{question}",
        }

    def build_macro_reaction(
        self, event: str, actual: float, forecast: float
    ) -> dict[str, str]:
        """Build prompt for post-macro event analysis.

        See docs/sub-specs/SS-19.md §11.4

        Args:
            event: Macro event name.
            actual: Actual value.
            forecast: Forecast value.

        Returns:
            Dict with 'system' and 'user' prompt strings.
        """
        payload = self._build_data_payload()
        question = (
            f"{event} just released: Actual={actual} vs Forecast={forecast}. "
            "How is the market reacting? Does this change the medium-term outlook? "
            "When is it safe to trade again?"
        )
        return {
            "system": _SYSTEM_PROMPT,
            "user": payload + f"\n=== QUESTION ===\n{question}",
        }

    def build_custom_question(self, question: str) -> dict[str, str]:
        """Build prompt for user's custom question.

        See docs/sub-specs/SS-19.md §11.4

        Args:
            question: User's question text.

        Returns:
            Dict with 'system' and 'user' prompt strings.
        """
        payload = self._build_data_payload()
        return {
            "system": _SYSTEM_PROMPT,
            "user": payload + f"\n=== QUESTION ===\n{question}",
        }

    def _build_data_payload(self) -> str:
        """Collect and format all system data into a structured payload.

        See docs/sub-specs/SS-19.md §11.3
        """
        sections: list[str] = []

        # Price
        price_rows = get_latest(self.db_path, "spot_price", n=1, order_col="timestamp")
        if price_rows:
            p = price_rows[0]
            sections.append(
                f"=== MARKET SNAPSHOT ===\n"
                f"BTC Price: ${p.get('close', 0):,.0f}\n"
                f"Volume: {p.get('volume', 0):,.0f}"
            )

        # Signals
        sig_rows = get_latest(self.db_path, "signals", n=1, order_col="timestamp")
        if sig_rows:
            s = sig_rows[0]
            sections.append(
                f"=== COMPOSITE SIGNALS ===\n"
                f"Final Score: {s.get('final_score', 0):+.3f} | Bias: {s.get('bias', 'N/A')} | "
                f"Strength: {s.get('strength', 'N/A')} | Confidence: {s.get('confidence', 'N/A')}\n"
                f"Spot Flow: {s.get('spot_flow', 0):+.3f}\n"
                f"Leverage: {s.get('leverage_pos', 0):+.3f}\n"
                f"Options: {s.get('options_struct', 0):+.3f}\n"
                f"Mean Reversion: {s.get('mean_reversion', 0):+.3f}\n"
                f"Regime: {s.get('regime', 'N/A')} | Consensus: {s.get('consensus', 'N/A')}\n"
                f"Event Risk: {s.get('event_risk', 0):.2f}"
            )

        # Technicals
        tech_rows = get_latest(self.db_path, "spot_technicals", n=1, order_col="date")
        if tech_rows:
            t = tech_rows[0]
            sections.append(
                f"=== TECHNICALS ===\n"
                f"RSI(14): {t.get('rsi_14', 0):.1f} | ADX(14): {t.get('adx_14', 0):.1f}\n"
                f"EMA 21: ${t.get('ema_21', 0):,.0f} | EMA 55: ${t.get('ema_55', 0):,.0f} | "
                f"EMA 200: ${t.get('ema_200', 0):,.0f}\n"
                f"VWAP: ${t.get('vwap', 0):,.0f}"
            )

        # Futures
        fut_rows = get_latest(self.db_path, "futures_snapshot", n=1, order_col="timestamp")
        if fut_rows:
            f = fut_rows[0]
            sections.append(
                f"=== FUTURES ===\n"
                f"Funding: {f.get('funding_weighted_avg', 0):.4f}%\n"
                f"OI Total: ${f.get('oi_total_usd', 0):,.0f}\n"
                f"Top Trader L/S: {f.get('top_trader_ls_ratio', 0):.2f}"
            )

        # Macro events
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        macro_rows = query(
            self.db_path,
            "SELECT * FROM macro_events WHERE date >= ? ORDER BY date, time_utc LIMIT 5",
            (now,),
        )
        if macro_rows:
            events_str = "\n".join(
                f"  T{r['tier']} | {r['date']} {r['time_utc']} | {r['event']}"
                for r in macro_rows
            )
            sections.append(f"=== MACRO EVENTS ===\n{events_str}")

        return "\n\n".join(sections) if sections else "=== NO DATA AVAILABLE ==="


class ClaudeAnalyzer:
    """Send prompts to Claude API and return analysis text.

    See docs/sub-specs/SS-19.md §11.5
    """

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str | None, config: dict):
        self.api_key = api_key
        self.config = config
        ai_cfg = config.get("ai", {})
        self.model = ai_cfg.get("model", "claude-sonnet-4-5-20250929")
        self.max_tokens = ai_cfg.get("max_tokens", 1024)
        self.rate_limiter = RateLimiter(ai_cfg.get("max_daily_calls", 10))

    async def analyze(self, prompt: dict[str, str]) -> str:
        """Send prompt to Claude API.

        See docs/sub-specs/SS-19.md §11.5

        Args:
            prompt: Dict with 'system' and 'user' keys.

        Returns:
            Analysis text, or fallback message on failure.
        """
        if not self.api_key:
            logger.warning("AI Analysis disabled — no API key")
            return "⚠️ AI analysis unavailable — API key not configured."

        if not self.rate_limiter.can_call():
            logger.warning("AI rate limit reached (%d remaining)", self.rate_limiter.remaining())
            return "⚠️ AI analysis unavailable — daily rate limit reached."

        try:
            import aiohttp

            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": prompt["system"],
                "messages": [{"role": "user", "content": prompt["user"]}],
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.API_URL, headers=headers, json=payload) as resp:
                    self.rate_limiter.record_call()
                    if resp.status == 200:
                        data = await resp.json()
                        return data["content"][0]["text"]
                    else:
                        error = await resp.text()
                        logger.error("Claude API error %d: %s", resp.status, error[:200])
                        return f"⚠️ AI analysis unavailable (HTTP {resp.status})"

        except Exception as e:
            logger.error("AI analysis failed: %s", e)
            return "⚠️ AI analysis temporarily unavailable."
