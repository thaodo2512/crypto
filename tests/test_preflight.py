"""Tests for preflight health check module.

Tests env var checking, format functions, mocked collector checks,
and first-run detection.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom.utils.health import HealthMonitor
from custom.utils.preflight import (
    CheckResult,
    PreflightResult,
    check_env_vars,
    format_preflight_console,
    format_preflight_telegram,
    is_first_run,
    run_preflight,
)


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def health_config() -> dict:
    """Minimal config for HealthMonitor."""
    return {
        "health": {
            "staleness_threshold_minutes": 30,
            "latency_threshold_seconds": 5,
            "consecutive_failures_before_fallback": 3,
        },
    }


@pytest.fixture
def monitor(health_config) -> HealthMonitor:
    """HealthMonitor with test config."""
    return HealthMonitor(health_config)


@pytest.fixture
def full_config(health_config) -> dict:
    """Config dict sufficient for collector instantiation."""
    return {
        **health_config,
        "spot_data": {
            "whale_trade_threshold_usd": 100_000,
            "orderbook_depth_levels": 20,
            "volume_sma_period": 20,
        },
        "macro_events": {
            "tier1_imminent_hours": 2,
            "tier1_warning_hours": 6,
            "tier1_alert_hours": 24,
            "tier2_imminent_hours": 2,
            "tier2_warning_hours": 6,
            "tier3_imminent_hours": 2,
        },
    }


@pytest.fixture
def all_pass_result() -> PreflightResult:
    """PreflightResult where all checks pass."""
    return PreflightResult(
        checks=[
            CheckResult(name="Binance Spot", ok=True, latency_ms=82.0),
            CheckResult(name="Futures", ok=True, latency_ms=156.0, detail="Binance + Bybit + OKX"),
            CheckResult(name="Deribit Options", ok=True, latency_ms=203.0),
            CheckResult(name="Fear & Greed", ok=True, latency_ms=45.0),
        ],
        env_vars=[
            {"name": "TELEGRAM_BOT_TOKEN", "is_set": True, "required": True, "note": "Telegram bot disabled"},
            {"name": "TELEGRAM_CHAT_ID", "is_set": True, "required": True, "note": "Telegram bot disabled"},
            {"name": "FRED_API_KEY", "is_set": False, "required": False, "note": "macro data limited"},
            {"name": "ANTHROPIC_API_KEY", "is_set": True, "required": False, "note": "AI analysis disabled"},
        ],
    )


@pytest.fixture
def partial_fail_result() -> PreflightResult:
    """PreflightResult where some checks fail."""
    return PreflightResult(
        checks=[
            CheckResult(name="Binance Spot", ok=True, latency_ms=82.0),
            CheckResult(name="Futures", ok=False, error="Connection timeout"),
            CheckResult(name="Deribit Options", ok=True, latency_ms=203.0),
            CheckResult(name="Fear & Greed", ok=False, error="API returned 503"),
        ],
        env_vars=[
            {"name": "TELEGRAM_BOT_TOKEN", "is_set": True, "required": True, "note": "Telegram bot disabled"},
            {"name": "TELEGRAM_CHAT_ID", "is_set": False, "required": True, "note": "Telegram bot disabled"},
            {"name": "FRED_API_KEY", "is_set": False, "required": False, "note": "macro data limited"},
            {"name": "ANTHROPIC_API_KEY", "is_set": False, "required": False, "note": "AI analysis disabled"},
        ],
    )


# ─── TestCheckEnvVars ────────────────────────────────────


class TestCheckEnvVars:
    """Tests for check_env_vars()."""

    def test_detects_set_vars(self, monkeypatch) -> None:
        """Env vars that are set should be reported as is_set=True."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setenv("FRED_API_KEY", "fred-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")

        results = check_env_vars()

        assert len(results) == 4
        assert all(r["is_set"] for r in results)

    def test_detects_missing_vars(self, monkeypatch) -> None:
        """Env vars that are not set should be reported as is_set=False."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        results = check_env_vars()

        assert len(results) == 4
        assert all(not r["is_set"] for r in results)

    def test_mixed_set_and_missing(self, monkeypatch) -> None:
        """Mix of set and missing env vars."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")

        results = check_env_vars()

        by_name = {r["name"]: r for r in results}
        assert by_name["TELEGRAM_BOT_TOKEN"]["is_set"] is True
        assert by_name["TELEGRAM_CHAT_ID"]["is_set"] is False
        assert by_name["FRED_API_KEY"]["is_set"] is False
        assert by_name["ANTHROPIC_API_KEY"]["is_set"] is True

    def test_required_flag_preserved(self) -> None:
        """Required flag should match _ENV_VARS definition."""
        results = check_env_vars()
        by_name = {r["name"]: r for r in results}

        assert by_name["TELEGRAM_BOT_TOKEN"]["required"] is True
        assert by_name["TELEGRAM_CHAT_ID"]["required"] is True
        assert by_name["FRED_API_KEY"]["required"] is False
        assert by_name["ANTHROPIC_API_KEY"]["required"] is False

    def test_empty_string_treated_as_missing(self, monkeypatch) -> None:
        """Empty string env var should be treated as not set."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")

        results = check_env_vars()
        by_name = {r["name"]: r for r in results}
        assert by_name["TELEGRAM_BOT_TOKEN"]["is_set"] is False


# ─── TestPreflightResult ────────────────────────────────


class TestPreflightResult:
    """Tests for PreflightResult dataclass."""

    def test_passed_count_all_ok(self, all_pass_result) -> None:
        """All checks passed → passed == total."""
        assert all_pass_result.passed == 4
        assert all_pass_result.total == 4

    def test_passed_count_partial_fail(self, partial_fail_result) -> None:
        """Partial failures → passed < total."""
        assert partial_fail_result.passed == 2
        assert partial_fail_result.total == 4

    def test_passed_count_all_fail(self) -> None:
        """All checks fail → passed == 0."""
        result = PreflightResult(checks=[
            CheckResult(name="A", ok=False, error="err"),
            CheckResult(name="B", ok=False, error="err"),
        ])
        assert result.passed == 0
        assert result.total == 2


# ─── TestFormatConsole ───────────────────────────────────


class TestFormatConsole:
    """Tests for format_preflight_console()."""

    def test_contains_header(self, all_pass_result) -> None:
        """Output includes PREFLIGHT CHECK header."""
        output = format_preflight_console(all_pass_result)
        assert "PREFLIGHT CHECK" in output

    def test_shows_env_var_status(self, all_pass_result) -> None:
        """Output shows each env var with set/missing status."""
        output = format_preflight_console(all_pass_result)
        assert "TELEGRAM_BOT_TOKEN" in output
        assert "SET" in output
        assert "FRED_API_KEY" in output
        assert "not set" in output

    def test_shows_data_source_results(self, all_pass_result) -> None:
        """Output shows each data source with OK/FAIL and latency."""
        output = format_preflight_console(all_pass_result)
        assert "[OK]" in output
        assert "Binance Spot" in output
        assert "82ms" in output

    def test_shows_summary(self, all_pass_result) -> None:
        """Output includes pass/total summary."""
        output = format_preflight_console(all_pass_result)
        assert "4/4 sources OK" in output

    def test_shows_failures(self, partial_fail_result) -> None:
        """Output shows FAIL for failed checks."""
        output = format_preflight_console(partial_fail_result)
        assert "[FAIL]" in output
        assert "Connection timeout" in output
        assert "2/4 sources OK" in output

    def test_shows_missing_required_env(self, partial_fail_result) -> None:
        """Output shows MISSING for required unset env vars."""
        output = format_preflight_console(partial_fail_result)
        assert "MISSING" in output

    def test_shows_detail_for_futures(self, all_pass_result) -> None:
        """Futures check shows exchange detail."""
        output = format_preflight_console(all_pass_result)
        assert "Binance + Bybit + OKX" in output


# ─── TestFormatTelegram ──────────────────────────────────


class TestFormatTelegram:
    """Tests for format_preflight_telegram()."""

    def test_contains_header(self, all_pass_result) -> None:
        """Telegram output includes header."""
        output = format_preflight_telegram(all_pass_result)
        assert "PREFLIGHT CHECK" in output

    def test_shows_data_sources(self, all_pass_result) -> None:
        """Telegram output shows source status."""
        output = format_preflight_telegram(all_pass_result)
        assert "Binance Spot: OK" in output
        assert "82ms" in output

    def test_shows_failures_in_telegram(self, partial_fail_result) -> None:
        """Telegram output shows FAIL for failed checks."""
        output = format_preflight_telegram(partial_fail_result)
        assert "FAIL" in output
        assert "Connection timeout" in output

    def test_shows_summary(self, all_pass_result) -> None:
        """Telegram output includes summary."""
        output = format_preflight_telegram(all_pass_result)
        assert "4/4 sources OK" in output


# ─── TestIsFirstRun ──────────────────────────────────────


class TestIsFirstRun:
    """Tests for is_first_run()."""

    def test_empty_db_is_first_run(self, tmp_path) -> None:
        """Empty spot_price table → first run."""
        from custom.utils.db import init_db

        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        assert is_first_run(db_path) is True

    def test_populated_db_is_not_first_run(self, tmp_path) -> None:
        """Populated spot_price table → not first run."""
        from custom.utils.db import init_db, insert_row

        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        insert_row(db_path, "spot_price", {
            "timestamp": "2026-01-01T00:00:00Z",
            "close": 50000.0,
        })

        assert is_first_run(db_path) is False


# ─── TestRunPreflight ────────────────────────────────────


class TestRunPreflight:
    """Tests for run_preflight() with mocked collectors."""

    def test_all_pass(self, full_config, monitor, tmp_path) -> None:
        """All collectors succeed → all checks OK, health recorded."""
        db_path = str(tmp_path / "test.db")
        from custom.utils.db import init_db
        init_db(db_path)

        with patch("custom.utils.preflight._check_spot") as mock_spot, \
             patch("custom.utils.preflight._check_futures") as mock_futures, \
             patch("custom.utils.preflight._check_options") as mock_options, \
             patch("custom.utils.preflight._check_sentiment") as mock_sentiment:

            mock_spot.return_value = CheckResult(name="Binance Spot", ok=True, latency_ms=80.0)
            mock_futures.return_value = CheckResult(name="Futures", ok=True, latency_ms=150.0)
            mock_options.return_value = CheckResult(name="Deribit Options", ok=True, latency_ms=200.0)
            mock_sentiment.return_value = CheckResult(name="Fear & Greed", ok=True, latency_ms=40.0)

            result = asyncio.run(run_preflight(full_config, db_path, monitor))

        assert result.passed == 4
        assert result.total == 4
        assert len(result.env_vars) == 4

        # Health monitor should have recorded successes
        for src in ["spot_price", "futures", "options", "sentiment"]:
            status = monitor.get_source_status(src)
            assert status["consecutive_failures"] == 0

    def test_partial_failure(self, full_config, monitor, tmp_path) -> None:
        """Some collectors fail → partial results, failures recorded in health."""
        db_path = str(tmp_path / "test.db")
        from custom.utils.db import init_db
        init_db(db_path)

        with patch("custom.utils.preflight._check_spot") as mock_spot, \
             patch("custom.utils.preflight._check_futures") as mock_futures, \
             patch("custom.utils.preflight._check_options") as mock_options, \
             patch("custom.utils.preflight._check_sentiment") as mock_sentiment:

            mock_spot.return_value = CheckResult(name="Binance Spot", ok=True, latency_ms=80.0)
            mock_futures.return_value = CheckResult(name="Futures", ok=False, error="Timeout")
            mock_options.return_value = CheckResult(name="Deribit Options", ok=True, latency_ms=200.0)
            mock_sentiment.return_value = CheckResult(name="Fear & Greed", ok=False, error="503")

            result = asyncio.run(run_preflight(full_config, db_path, monitor))

        assert result.passed == 2
        assert result.total == 4

        # Failed sources should have failures recorded
        futures_status = monitor.get_source_status("futures")
        assert futures_status["consecutive_failures"] == 1
        assert futures_status["last_error"] == "Timeout"

    def test_all_fail(self, full_config, monitor, tmp_path) -> None:
        """All collectors fail → 0 passed, all failures recorded."""
        db_path = str(tmp_path / "test.db")
        from custom.utils.db import init_db
        init_db(db_path)

        with patch("custom.utils.preflight._check_spot") as mock_spot, \
             patch("custom.utils.preflight._check_futures") as mock_futures, \
             patch("custom.utils.preflight._check_options") as mock_options, \
             patch("custom.utils.preflight._check_sentiment") as mock_sentiment:

            mock_spot.return_value = CheckResult(name="Binance Spot", ok=False, error="DNS fail")
            mock_futures.return_value = CheckResult(name="Futures", ok=False, error="Timeout")
            mock_options.return_value = CheckResult(name="Deribit Options", ok=False, error="Refused")
            mock_sentiment.return_value = CheckResult(name="Fear & Greed", ok=False, error="503")

            result = asyncio.run(run_preflight(full_config, db_path, monitor))

        assert result.passed == 0
        assert result.total == 4

    def test_exception_in_gather_handled(self, full_config, monitor, tmp_path) -> None:
        """Unhandled exception from asyncio.gather → treated as failure."""
        db_path = str(tmp_path / "test.db")
        from custom.utils.db import init_db
        init_db(db_path)

        with patch("custom.utils.preflight._check_spot") as mock_spot, \
             patch("custom.utils.preflight._check_futures") as mock_futures, \
             patch("custom.utils.preflight._check_options") as mock_options, \
             patch("custom.utils.preflight._check_sentiment") as mock_sentiment:

            mock_spot.return_value = CheckResult(name="Binance Spot", ok=True, latency_ms=80.0)
            mock_futures.return_value = RuntimeError("Unexpected")
            mock_options.return_value = CheckResult(name="Deribit Options", ok=True, latency_ms=200.0)
            mock_sentiment.return_value = CheckResult(name="Fear & Greed", ok=True, latency_ms=40.0)

            result = asyncio.run(run_preflight(full_config, db_path, monitor))

        assert result.passed == 3
        assert result.total == 4

        # The exception result should be recorded as failure
        futures_status = monitor.get_source_status("futures")
        assert futures_status["consecutive_failures"] == 1

    def test_env_vars_included_in_result(self, full_config, monitor, tmp_path, monkeypatch) -> None:
        """Result includes env var checks."""
        db_path = str(tmp_path / "test.db")
        from custom.utils.db import init_db
        init_db(db_path)

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
        monkeypatch.delenv("FRED_API_KEY", raising=False)

        with patch("custom.utils.preflight._check_spot") as mock_spot, \
             patch("custom.utils.preflight._check_futures") as mock_futures, \
             patch("custom.utils.preflight._check_options") as mock_options, \
             patch("custom.utils.preflight._check_sentiment") as mock_sentiment:

            mock_spot.return_value = CheckResult(name="Binance Spot", ok=True, latency_ms=80.0)
            mock_futures.return_value = CheckResult(name="Futures", ok=True, latency_ms=150.0)
            mock_options.return_value = CheckResult(name="Deribit Options", ok=True, latency_ms=200.0)
            mock_sentiment.return_value = CheckResult(name="Fear & Greed", ok=True, latency_ms=40.0)

            result = asyncio.run(run_preflight(full_config, db_path, monitor))

        assert len(result.env_vars) == 4
        by_name = {v["name"]: v for v in result.env_vars}
        assert by_name["TELEGRAM_BOT_TOKEN"]["is_set"] is True
        assert by_name["FRED_API_KEY"]["is_set"] is False
