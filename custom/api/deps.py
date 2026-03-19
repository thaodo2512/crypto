"""Dependency injection for FastAPI routes.

See docs/sub-specs/SS-25.md
"""

from typing import Any

_state: dict[str, Any] = {}


def init_state(
    db_path: str,
    config: dict,
    health_monitor: Any = None,
    scheduler: Any = None,
) -> None:
    """Initialize shared state for API routes.

    Called once from main.py at startup.
    """
    _state["db_path"] = db_path
    _state["config"] = config
    _state["health_monitor"] = health_monitor
    _state["scheduler"] = scheduler


def get_db_path(symbol: str = "BTC") -> str:
    """Get the database path for a given asset symbol.

    Args:
        symbol: Asset symbol (e.g. "BTC", "ETH"). Defaults to "BTC".

    Returns:
        Path to the asset's database file.
    """
    config = _state.get("config", {})
    assets = config.get("assets", {})
    key = symbol.upper()
    if key in assets:
        return assets[key]["db_path"]
    return _state["db_path"]


def get_config() -> dict:
    """Get the settings config."""
    return _state["config"]


def get_health_monitor() -> Any:
    """Get the health monitor instance."""
    return _state.get("health_monitor")


def get_scheduler() -> Any:
    """Get the scheduler instance."""
    return _state.get("scheduler")
