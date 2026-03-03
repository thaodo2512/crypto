"""First-run preflight health check for all data sources.

Runs once on first start (empty DB) or when --preflight flag is passed.
Tests all API connections in parallel and reports results to console and Telegram.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from custom.collectors.spot import CollectorError

logger = logging.getLogger(__name__)

# Env vars to check: (name, required, description_if_missing)
_ENV_VARS: list[tuple[str, bool, str]] = [
    ("TELEGRAM_BOT_TOKEN", True, "Telegram bot disabled"),
    ("TELEGRAM_CHAT_ID", True, "Telegram bot disabled"),
    ("FRED_API_KEY", False, "macro data limited"),
    ("ANTHROPIC_API_KEY", False, "AI analysis disabled"),
]


@dataclass
class CheckResult:
    """Result of a single preflight check."""

    name: str
    ok: bool
    latency_ms: float = 0.0
    error: str = ""
    detail: str = ""


@dataclass
class PreflightResult:
    """Aggregated result of all preflight checks."""

    checks: list[CheckResult] = field(default_factory=list)
    env_vars: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.ok)

    @property
    def total(self) -> int:
        return len(self.checks)


def check_env_vars() -> list[dict[str, Any]]:
    """Check required and optional environment variables.

    Returns:
        List of dicts with keys: name, is_set, required, note.
    """
    results = []
    for name, required, note in _ENV_VARS:
        is_set = bool(os.getenv(name, ""))
        results.append({
            "name": name,
            "is_set": is_set,
            "required": required,
            "note": note,
        })
    return results


def is_first_run(db_path: str) -> bool:
    """Check if this is the first run by looking for any spot_price data.

    Args:
        db_path: Path to SQLite database.

    Returns:
        True if spot_price table is empty (first run).
    """
    from custom.utils.db import get_latest

    rows = get_latest(db_path, "spot_price", n=1, order_col="timestamp")
    return len(rows) == 0


async def _check_spot(config: dict, db_path: str) -> CheckResult:
    """Check Binance Spot API connectivity."""
    from custom.collectors.spot import SpotCollector

    t0 = time.monotonic()
    try:
        collector = SpotCollector(config, db_path)
        await collector.fetch_price()
        latency = (time.monotonic() - t0) * 1000
        return CheckResult(name="Binance Spot", ok=True, latency_ms=latency)
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        return CheckResult(name="Binance Spot", ok=False, latency_ms=latency, error=str(e))


async def _check_futures(config: dict, db_path: str) -> CheckResult:
    """Check Futures API connectivity (Binance + Bybit + OKX)."""
    from custom.collectors.futures import FuturesCollector

    t0 = time.monotonic()
    try:
        collector = FuturesCollector(config, db_path)
        await collector.fetch_snapshot()
        latency = (time.monotonic() - t0) * 1000
        return CheckResult(
            name="Futures", ok=True, latency_ms=latency,
            detail="Binance + Bybit + OKX",
        )
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        return CheckResult(name="Futures", ok=False, latency_ms=latency, error=str(e))


async def _check_options(config: dict, db_path: str) -> CheckResult:
    """Check Deribit Options API connectivity."""
    from custom.collectors.options import OptionsCollector

    t0 = time.monotonic()
    try:
        collector = OptionsCollector(config, db_path)
        await collector.fetch_snapshot()
        latency = (time.monotonic() - t0) * 1000
        return CheckResult(name="Deribit Options", ok=True, latency_ms=latency)
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        return CheckResult(name="Deribit Options", ok=False, latency_ms=latency, error=str(e))


async def _check_sentiment(config: dict, db_path: str) -> CheckResult:
    """Check Fear & Greed API connectivity."""
    from custom.collectors.sentiment import SentimentCollector

    t0 = time.monotonic()
    try:
        collector = SentimentCollector(config, db_path)
        await collector.fetch_fear_greed()
        latency = (time.monotonic() - t0) * 1000
        return CheckResult(name="Fear & Greed", ok=True, latency_ms=latency)
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        return CheckResult(name="Fear & Greed", ok=False, latency_ms=latency, error=str(e))


async def run_preflight(
    config: dict,
    db_path: str,
    health_monitor: Any,
) -> PreflightResult:
    """Run all preflight checks in parallel.

    Args:
        config: Full settings dict.
        db_path: Path to SQLite database.
        health_monitor: HealthMonitor instance for recording results.

    Returns:
        PreflightResult with per-source status and env var info.
    """
    result = PreflightResult()
    result.env_vars = check_env_vars()

    checks = await asyncio.gather(
        _check_spot(config, db_path),
        _check_futures(config, db_path),
        _check_options(config, db_path),
        _check_sentiment(config, db_path),
        return_exceptions=True,
    )

    source_names = ["spot_price", "futures", "options", "sentiment"]

    for i, check in enumerate(checks):
        if isinstance(check, Exception):
            # asyncio.gather returned an exception object
            cr = CheckResult(name=source_names[i], ok=False, error=str(check))
            health_monitor.record_failure(source_names[i], str(check))
        else:
            cr = check
            if cr.ok:
                health_monitor.record_success(source_names[i], cr.latency_ms / 1000)
            else:
                health_monitor.record_failure(source_names[i], cr.error)
        result.checks.append(cr)

    return result


def format_preflight_console(result: PreflightResult) -> str:
    """Format preflight results for console output.

    Args:
        result: PreflightResult from run_preflight().

    Returns:
        Formatted string with pass/fail indicators.
    """
    lines = [
        "",
        "=" * 50,
        "  PREFLIGHT CHECK",
        "=" * 50,
        "",
        "Environment:",
    ]

    for env in result.env_vars:
        if env["is_set"]:
            status = "  SET"
        elif env["required"]:
            status = "  MISSING"
        else:
            status = f"  not set ({env['note']})"
        lines.append(f"  {env['name']:<22} {status}")

    lines.append("")
    lines.append("Data Sources:")

    for check in result.checks:
        if check.ok:
            detail = f" -- {check.detail}" if check.detail else ""
            lines.append(f"  [OK]   {check.name:<20} ({check.latency_ms:.0f}ms){detail}")
        else:
            lines.append(f"  [FAIL] {check.name:<20} {check.error}")

    lines.append("")
    lines.append(f"Result: {result.passed}/{result.total} sources OK")
    lines.append("=" * 50)
    lines.append("")

    return "\n".join(lines)


def format_preflight_telegram(result: PreflightResult) -> str:
    """Format preflight results for Telegram message.

    Args:
        result: PreflightResult from run_preflight().

    Returns:
        Compact Telegram-formatted string.
    """
    lines = ["PREFLIGHT CHECK", ""]

    # Env vars
    for env in result.env_vars:
        if env["is_set"]:
            lines.append(f"  {env['name']}: set")
        elif env["required"]:
            lines.append(f"  {env['name']}: MISSING")
        else:
            lines.append(f"  {env['name']}: not set ({env['note']})")

    lines.append("")

    # Data sources
    for check in result.checks:
        if check.ok:
            detail = f" -- {check.detail}" if check.detail else ""
            lines.append(f"  {check.name}: OK ({check.latency_ms:.0f}ms){detail}")
        else:
            lines.append(f"  {check.name}: FAIL - {check.error}")

    lines.append("")
    lines.append(f"Result: {result.passed}/{result.total} sources OK")

    return "\n".join(lines)
