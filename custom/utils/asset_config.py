"""Asset configuration — per-asset settings for multi-asset support.

See docs/sub-specs/SS-02.md, SS-03.md, SS-04.md
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AssetConfig:
    """Per-asset configuration loaded from settings.yaml assets: section.

    Attributes:
        name: Asset name (e.g. "BTC", "ETH", "SOL").
        enabled: Whether this asset is active.
        spot_symbol: Binance spot symbol (e.g. "BTCUSDT").
        futures_binance: Binance futures symbol.
        futures_bybit: Bybit futures symbol.
        futures_okx: OKX swap instrument ID.
        deribit_currency: Deribit currency code (e.g. "BTC"), None if no options.
        db_path: Path to per-asset SQLite database.
        round_number_step: Step for round number confluence levels.
        whale_threshold_usd: Minimum USD value for whale trade detection.
        has_options: Whether this asset has options data (Deribit).
    """

    name: str
    enabled: bool
    spot_symbol: str
    futures_binance: str
    futures_bybit: str
    futures_okx: str
    deribit_currency: str | None
    db_path: str
    round_number_step: int
    whale_threshold_usd: int
    has_options: bool


def get_asset_config(config: dict, asset_name: str) -> AssetConfig:
    """Load config for a single asset.

    Args:
        config: Full settings dict.
        asset_name: Asset key (e.g. "BTC").

    Returns:
        AssetConfig for the named asset.

    Raises:
        KeyError: If asset not found in config.
    """
    assets = config.get("assets", {})
    ac = assets[asset_name]
    return AssetConfig(
        name=asset_name,
        enabled=ac.get("enabled", False),
        spot_symbol=ac["spot_symbol"],
        futures_binance=ac["futures_binance"],
        futures_bybit=ac["futures_bybit"],
        futures_okx=ac["futures_okx"],
        deribit_currency=ac.get("deribit_currency"),
        db_path=ac["db_path"],
        round_number_step=ac.get("round_number_step", 5000),
        whale_threshold_usd=ac.get("whale_threshold_usd", 100000),
        has_options=ac.get("has_options", True),
    )


def get_enabled_assets(config: dict) -> list[AssetConfig]:
    """Return list of enabled AssetConfig objects.

    Args:
        config: Full settings dict.

    Returns:
        List of AssetConfig for all enabled assets.
    """
    assets = config.get("assets", {})
    result = []
    for name, ac in assets.items():
        if ac.get("enabled", False):
            result.append(get_asset_config(config, name))
    return result


def get_db_path_for_symbol(config: dict, symbol: str) -> str:
    """Resolve symbol name to its database path.

    Args:
        config: Full settings dict.
        symbol: Asset symbol (e.g. "BTC", "ETH"). Case-insensitive.

    Returns:
        Database path string.

    Raises:
        KeyError: If symbol not found.
    """
    assets = config.get("assets", {})
    key = symbol.upper()
    if key in assets:
        return assets[key]["db_path"]
    raise KeyError(f"Unknown asset: {symbol}")
