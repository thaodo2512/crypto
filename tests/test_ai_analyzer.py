"""Tests for SS-19: AI Analysis Layer.

See docs/sub-specs/SS-19.md §Acceptance Criteria
"""

import pytest

from custom.ai.analyzer import AIPromptBuilder, ClaudeAnalyzer, RateLimiter, _SYSTEM_PROMPT
from custom.utils.db import get_db, init_db, insert_row


@pytest.fixture
def db(tmp_path) -> str:
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


@pytest.fixture
def config() -> dict:
    return {
        "ai": {
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": 1024,
            "max_daily_calls": 10,
            "response_language": "vi",
        },
    }


def _seed_signal(db: str) -> None:
    conn = get_db(db)
    try:
        conn.execute(
            """INSERT INTO signals (timestamp, final_score, bias, strength, confidence,
               regime, event_risk, consensus, spot_flow, leverage_pos, options_struct,
               mean_reversion, weights_json, btc_price_at_signal)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2026-03-01T08:00:00Z", 0.45, "LONG", "MODERATE", "MEDIUM",
             "STRONG_TREND", 0.2, "MODERATE_CONSENSUS",
             0.6, 0.4, -0.1, 0.3, "{}", 100000),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_price(db: str) -> None:
    insert_row(db, "spot_price", {
        "timestamp": "2026-03-01T08:00:00",
        "open": 99000, "high": 101000, "low": 98500, "close": 100000,
        "volume": 5000, "quote_volume": 500000000, "num_trades": 10000,
    })


class TestAIPromptBuilder:
    def test_daily_briefing_has_all_sections(self, db, config) -> None:
        """AC 1: Daily briefing includes all data sections."""
        _seed_price(db)
        _seed_signal(db)
        insert_row(db, "spot_technicals", {
            "date": "2026-03-01", "rsi_14": 55, "ema_21": 100100,
            "ema_55": 99500, "ema_200": 95000, "vwap": 100050,
            "bb_upper": 105000, "bb_lower": 95000, "bb_width": 10000,
            "adx_14": 28, "volume_sma_20": 5000, "volume_ratio": 1.1,
        })

        builder = AIPromptBuilder(db, config)
        prompt = builder.build_daily_briefing()

        assert "system" in prompt
        assert "user" in prompt
        assert "MARKET SNAPSHOT" in prompt["user"]
        assert "COMPOSITE SIGNALS" in prompt["user"]
        assert "TECHNICALS" in prompt["user"]
        assert "QUESTION" in prompt["user"]

    def test_signal_change_prompt(self, db, config) -> None:
        """AC 2: Signal change prompt includes old/new scores."""
        _seed_price(db)
        builder = AIPromptBuilder(db, config)
        prompt = builder.build_signal_change(0.30, 0.50)
        assert "0.30" in prompt["user"]
        assert "0.50" in prompt["user"]
        assert "changed" in prompt["user"].lower() or "shift" in prompt["user"].lower()

    def test_custom_question_prompt(self, db, config) -> None:
        """AC 3: Custom question includes user's question."""
        builder = AIPromptBuilder(db, config)
        prompt = builder.build_custom_question("Why is options signal bearish?")
        assert "Why is options signal bearish?" in prompt["user"]

    def test_macro_reaction_prompt(self, db, config) -> None:
        """AC 2: Macro reaction prompt includes event details."""
        builder = AIPromptBuilder(db, config)
        prompt = builder.build_macro_reaction("CPI", 3.2, 3.0)
        assert "CPI" in prompt["user"]
        assert "3.2" in prompt["user"]
        assert "3.0" in prompt["user"]

    def test_system_prompt_vietnamese(self) -> None:
        """AC 4: System prompt enforces Vietnamese language."""
        assert "Vietnamese" in _SYSTEM_PROMPT
        assert "Telegram" in _SYSTEM_PROMPT


class TestRateLimiter:
    def test_allows_within_limit(self) -> None:
        """AC 5: Rate limiter allows calls within limit."""
        limiter = RateLimiter(max_daily=3)
        assert limiter.can_call() is True
        limiter.record_call()
        assert limiter.can_call() is True
        limiter.record_call()
        assert limiter.can_call() is True
        limiter.record_call()
        assert limiter.can_call() is False

    def test_remaining_count(self) -> None:
        """AC 5: Remaining count decreases."""
        limiter = RateLimiter(max_daily=5)
        assert limiter.remaining() == 5
        limiter.record_call()
        assert limiter.remaining() == 4


class TestClaudeAnalyzer:
    def test_no_api_key_returns_fallback(self, config) -> None:
        """AC 6: No API key returns fallback message."""
        analyzer = ClaudeAnalyzer(api_key=None, config=config)
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            analyzer.analyze({"system": "test", "user": "test"})
        )
        assert "unavailable" in result.lower() or "API key" in result

    def test_rate_limit_returns_fallback(self, config) -> None:
        """AC 5+6: Rate limit exceeded returns fallback."""
        analyzer = ClaudeAnalyzer(api_key="test-key", config=config)
        # Exhaust rate limit
        for _ in range(10):
            analyzer.rate_limiter.record_call()

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            analyzer.analyze({"system": "test", "user": "test"})
        )
        assert "rate limit" in result.lower()

    def test_config_values(self, config) -> None:
        """AC 8: Config values loaded from settings."""
        analyzer = ClaudeAnalyzer(api_key="test", config=config)
        assert analyzer.model == "claude-sonnet-4-5-20250929"
        assert analyzer.max_tokens == 1024
        assert analyzer.rate_limiter._max_daily == 10

    def test_ai_advisory_only(self) -> None:
        """AC 7: AI output is advisory only — analyzer has no write methods."""
        # ClaudeAnalyzer has no method to modify signals, scores, or trades
        assert not hasattr(ClaudeAnalyzer, "modify_signal")
        assert not hasattr(ClaudeAnalyzer, "execute_trade")
        assert not hasattr(ClaudeAnalyzer, "update_score")
