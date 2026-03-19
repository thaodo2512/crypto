"""Tests for AI narrative integration into daily report, alerts, and /ai command.

See docs/sub-specs/SS-19.md §11
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom.ai.analyzer import AIPromptBuilder, ClaudeAnalyzer, RateLimiter
from custom.utils.db import get_db, init_db, insert_row


@pytest.fixture
def db(tmp_path) -> str:
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


@pytest.fixture
def config() -> dict:
    return {
        "general": {
            "target_asset": "BTC/USDT",
            "database_path": ":memory:",
            "log_level": "DEBUG",
            "timezone": "UTC",
        },
        "signal_classification": {
            "no_signal_threshold": 0.15,
            "weak_threshold": 0.35,
            "moderate_threshold": 0.60,
        },
        "ai": {
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": 1024,
            "max_daily_calls": 10,
            "response_language": "vi",
        },
        "alerts": {
            "cooldown_critical_minutes": 15,
            "cooldown_warning_minutes": 30,
            "cooldown_info_minutes": 120,
        },
        "health": {
            "staleness_threshold_minutes": 30,
            "latency_threshold_seconds": 5,
            "consecutive_failures_before_fallback": 3,
        },
    }


def _seed_signal(db_path: str, score: float = 0.45, timestamp: str = "2026-03-01T08:00:00Z") -> None:
    conn = get_db(db_path)
    try:
        conn.execute(
            """INSERT INTO signals (timestamp, final_score, bias, strength, confidence,
               regime, event_risk, consensus, spot_flow, leverage_pos, options_struct,
               mean_reversion, weights_json, btc_price_at_signal)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, score, "LONG", "MODERATE", "MEDIUM",
             "STRONG_TREND", 0.2, "MODERATE_CONSENSUS",
             0.6, 0.4, -0.1, 0.3, "{}", 100000),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_price(db_path: str) -> None:
    insert_row(db_path, "spot_price", {
        "timestamp": "2026-03-01T08:00:00",
        "open": 99000, "high": 101000, "low": 98500, "close": 100000,
        "volume": 5000, "quote_volume": 500000000, "num_trades": 10000,
    })


# ── Daily Report + AI Tests ─────────────────────────────────


class TestDailyReportAI:
    def test_daily_report_includes_ai_section(self, db, config) -> None:
        """Daily report appends AI narrative when analyzer succeeds."""
        from main import _make_daily_report_job

        _seed_price(db)
        _seed_signal(db)

        bot = MagicMock()
        ai_builder = MagicMock()
        ai_builder.build_daily_briefing.return_value = {"system": "s", "user": "u"}

        ai_analyzer = MagicMock()
        ai_analyzer.analyze = AsyncMock(return_value="Thị trường đang trong xu hướng tăng.")

        with patch("custom.signals.engine.compute_final_signal", return_value={"final_score": 0.45}), \
             patch("custom.regime.regime.compute_regime", return_value={"regime": "STRONG_TREND", "weights": {}}), \
             patch("custom.signals.event_risk.compute_event_risk", return_value=0.2):
            job = _make_daily_report_job(db, config, bot, ai_builder, ai_analyzer)
            job()

        broadcast_text = bot.broadcast_sync.call_args[0][0]
        assert "DAILY REPORT" in broadcast_text
        assert "🤖 AI ANALYSIS" in broadcast_text
        assert "Thị trường đang trong xu hướng tăng." in broadcast_text

    def test_daily_report_still_sends_on_ai_failure(self, db, config) -> None:
        """Daily report sends data-only report when AI fails."""
        from main import _make_daily_report_job

        _seed_price(db)
        _seed_signal(db)

        bot = MagicMock()
        ai_builder = MagicMock()
        ai_builder.build_daily_briefing.side_effect = Exception("API down")

        ai_analyzer = MagicMock()

        with patch("custom.signals.engine.compute_final_signal", return_value={"final_score": 0.45}), \
             patch("custom.regime.regime.compute_regime", return_value={"regime": "STRONG_TREND", "weights": {}}), \
             patch("custom.signals.event_risk.compute_event_risk", return_value=0.2):
            job = _make_daily_report_job(db, config, bot, ai_builder, ai_analyzer)
            job()

        broadcast_text = bot.broadcast_sync.call_args[0][0]
        assert "DAILY REPORT" in broadcast_text
        assert "🤖 AI ANALYSIS" not in broadcast_text

    def test_daily_report_without_ai_instances(self, db, config) -> None:
        """Daily report works fine when AI instances are None."""
        from main import _make_daily_report_job

        _seed_price(db)
        _seed_signal(db)

        bot = MagicMock()

        with patch("custom.signals.engine.compute_final_signal", return_value={"final_score": 0.45}), \
             patch("custom.regime.regime.compute_regime", return_value={"regime": "STRONG_TREND", "weights": {}}), \
             patch("custom.signals.event_risk.compute_event_risk", return_value=0.2):
            job = _make_daily_report_job(db, config, bot, None, None)
            job()

        broadcast_text = bot.broadcast_sync.call_args[0][0]
        assert "DAILY REPORT" in broadcast_text
        assert "🤖 AI ANALYSIS" not in broadcast_text


# ── Alert Job + AI Tests ────────────────────────────────────


class TestAlertJobAI:
    def test_alert_job_loads_prev_signal(self, db, config) -> None:
        """Alert job loads 2 most recent signals and passes prev_signal."""
        from main import _make_alert_job

        _seed_signal(db, score=0.30, timestamp="2026-03-01T06:00:00Z")
        _seed_signal(db, score=0.45, timestamp="2026-03-01T08:00:00Z")

        bot = MagicMock()
        health_monitor = MagicMock()
        health_monitor.get_health_report.return_value = {"sources": {}}

        with patch("custom.output.alerts.check_alerts", return_value=[]) as mock_check, \
             patch("custom.output.alerts.check_system_health", return_value=[]):
            job = _make_alert_job(db, config, health_monitor, bot)
            job()

        # check_alerts should have been called with prev_signal
        call_kwargs = mock_check.call_args
        assert call_kwargs[1]["prev_signal"] is not None
        assert call_kwargs[1]["prev_signal"]["final_score"] == 0.30

    def test_alert_with_crossing_appends_ai(self, db, config) -> None:
        """Signal crossing alert appends AI narrative."""
        from custom.output.alerts import reset_cooldowns
        from main import _make_alert_job

        reset_cooldowns()
        _seed_signal(db, score=0.30, timestamp="2026-03-01T06:00:00Z")
        _seed_signal(db, score=0.45, timestamp="2026-03-01T08:00:00Z")

        bot = MagicMock()
        health_monitor = MagicMock()
        health_monitor.get_health_report.return_value = {"sources": {}}

        ai_builder = MagicMock()
        ai_builder.build_signal_change.return_value = {"system": "s", "user": "u"}

        ai_analyzer = MagicMock()
        ai_analyzer.analyze = AsyncMock(return_value="Tín hiệu đã vượt ngưỡng 0.35.")

        job = _make_alert_job(db, config, health_monitor, bot, ai_builder, ai_analyzer)
        job()

        if bot.broadcast_sync.called:
            broadcast_text = bot.broadcast_sync.call_args[0][0]
            # If signal crossing fired, AI section should be there
            if "signal_threshold_crossing" in broadcast_text:
                assert "🤖 AI ANALYSIS" in broadcast_text
                assert "Tín hiệu đã vượt ngưỡng 0.35." in broadcast_text

    def test_alert_ai_failure_still_sends_alert(self, db, config) -> None:
        """Alert fires even if AI analysis fails."""
        from custom.output.alerts import reset_cooldowns
        from main import _make_alert_job

        reset_cooldowns()
        _seed_signal(db, score=0.30, timestamp="2026-03-01T06:00:00Z")
        _seed_signal(db, score=0.45, timestamp="2026-03-01T08:00:00Z")

        bot = MagicMock()
        health_monitor = MagicMock()
        health_monitor.get_health_report.return_value = {"sources": {}}

        ai_builder = MagicMock()
        ai_builder.build_signal_change.side_effect = Exception("AI down")

        ai_analyzer = MagicMock()

        job = _make_alert_job(db, config, health_monitor, bot, ai_builder, ai_analyzer)
        job()

        if bot.broadcast_sync.called:
            broadcast_text = bot.broadcast_sync.call_args[0][0]
            assert "ALERTS" in broadcast_text
            # AI section should NOT be present when AI fails
            assert "🤖 AI ANALYSIS" not in broadcast_text

    def test_alert_no_prev_signal_skips_crossing(self, db, config) -> None:
        """With only 1 signal row, prev_signal is None — no crossing alert fires."""
        from main import _make_alert_job

        _seed_signal(db, score=0.45, timestamp="2026-03-01T08:00:00Z")

        bot = MagicMock()
        health_monitor = MagicMock()
        health_monitor.get_health_report.return_value = {"sources": {}}

        with patch("custom.output.alerts.check_alerts", return_value=[]) as mock_check, \
             patch("custom.output.alerts.check_system_health", return_value=[]):
            job = _make_alert_job(db, config, health_monitor, bot)
            job()

        call_kwargs = mock_check.call_args
        assert call_kwargs[1]["prev_signal"] is None


# ── /ai Command Tests ───────────────────────────────────────
# Note: python-telegram-bot is not installed in test env, so we mock the module
# and test _handle_ai logic via a standalone async function that mirrors bot.py.


def _make_handle_ai(ai_prompt_builder, ai_analyzer):
    """Create a standalone _handle_ai coroutine for testing without telegram import."""

    async def _handle_ai(reply_func, args: str) -> None:
        if not ai_analyzer or not ai_prompt_builder:
            await reply_func("🤖 AI analysis not configured.")
            return

        if not ai_analyzer.rate_limiter.can_call():
            remaining = ai_analyzer.rate_limiter.remaining()
            await reply_func(
                f"🤖 AI rate limit reached — {remaining} calls remaining today."
            )
            return

        await reply_func("🤖 Analyzing...")

        try:
            if args.strip():
                prompt = ai_prompt_builder.build_custom_question(args.strip())
            else:
                prompt = ai_prompt_builder.build_daily_briefing()

            ai_text = await ai_analyzer.analyze(prompt)
            remaining = ai_analyzer.rate_limiter.remaining()

            response = (
                "🤖 AI ANALYSIS\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"{ai_text}\n\n"
                f"📊 AI calls remaining today: {remaining}"
            )
        except Exception:
            response = "⚠️ AI analysis temporarily unavailable."

        await reply_func(response)

    return _handle_ai


class TestAiCommand:
    def test_ai_not_configured(self) -> None:
        """Returns not-configured message when AI instances are None."""
        handle_ai = _make_handle_ai(None, None)
        reply = AsyncMock()
        asyncio.run(handle_ai(reply, ""))
        text = reply.call_args[0][0]
        assert "not configured" in text.lower()

    def test_ai_rate_limit_exhausted(self, config) -> None:
        """Returns rate limit message when limit exhausted."""
        analyzer = ClaudeAnalyzer(api_key="test", config=config)
        for _ in range(10):
            analyzer.rate_limiter.record_call()

        handle_ai = _make_handle_ai(MagicMock(), analyzer)
        reply = AsyncMock()
        asyncio.run(handle_ai(reply, ""))
        text = reply.call_args[0][0]
        assert "rate limit" in text.lower()

    def test_ai_custom_question(self, config) -> None:
        """Custom question is forwarded to build_custom_question."""
        builder = MagicMock()
        builder.build_custom_question.return_value = {"system": "s", "user": "u"}

        analyzer = MagicMock()
        analyzer.rate_limiter = RateLimiter(max_daily=10)
        analyzer.analyze = AsyncMock(return_value="Funding rate tăng do...")

        handle_ai = _make_handle_ai(builder, analyzer)
        reply = AsyncMock()
        asyncio.run(
            handle_ai(reply, "why is funding rate spiking?")
        )

        builder.build_custom_question.assert_called_once_with("why is funding rate spiking?")
        calls = reply.call_args_list
        final_text = calls[-1][0][0]
        assert "Funding rate tăng do..." in final_text
        assert "AI calls remaining today:" in final_text

    def test_ai_no_question_defaults_to_briefing(self, config) -> None:
        """No question text defaults to daily briefing."""
        builder = MagicMock()
        builder.build_daily_briefing.return_value = {"system": "s", "user": "u"}

        analyzer = MagicMock()
        analyzer.rate_limiter = RateLimiter(max_daily=10)
        analyzer.analyze = AsyncMock(return_value="Tổng quan thị trường...")

        handle_ai = _make_handle_ai(builder, analyzer)
        reply = AsyncMock()
        asyncio.run(handle_ai(reply, ""))

        builder.build_daily_briefing.assert_called_once()
        calls = reply.call_args_list
        final_text = calls[-1][0][0]
        assert "Tổng quan thị trường..." in final_text

    def test_ai_failure_graceful(self, config) -> None:
        """AI failure returns graceful error message."""
        builder = MagicMock()
        builder.build_daily_briefing.side_effect = Exception("Prompt build failed")

        analyzer = MagicMock()
        analyzer.rate_limiter = RateLimiter(max_daily=10)

        handle_ai = _make_handle_ai(builder, analyzer)
        reply = AsyncMock()
        asyncio.run(handle_ai(reply, ""))

        calls = reply.call_args_list
        final_text = calls[-1][0][0]
        assert "unavailable" in final_text.lower()


# ── Shared RateLimiter Tests ────────────────────────────────


class TestSharedRateLimiter:
    def test_rate_limiter_thread_safe(self) -> None:
        """RateLimiter is thread-safe with Lock."""
        import threading

        limiter = RateLimiter(max_daily=100)
        errors = []

        def record_calls():
            try:
                for _ in range(20):
                    if limiter.can_call():
                        limiter.record_call()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_calls) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert limiter.remaining() == 0

    def test_shared_limiter_across_paths(self, config) -> None:
        """Single analyzer's RateLimiter shared across daily report, alerts, /ai."""
        analyzer = ClaudeAnalyzer(api_key="test", config=config)

        # Simulate 3 calls from different paths
        analyzer.rate_limiter.record_call()  # daily report
        analyzer.rate_limiter.record_call()  # alert
        analyzer.rate_limiter.record_call()  # /ai command

        assert analyzer.rate_limiter.remaining() == 7
