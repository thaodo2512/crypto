"""Spot market data collector (Binance Spot API).

See docs/sub-specs/SS-02.md §3.2
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp
import numpy as np
import pandas as pd
import ta as ta_lib

from custom.utils.db import insert_row

logger = logging.getLogger(__name__)

BASE_URL = "https://api.binance.com"
REQUEST_TIMEOUT_SECONDS = 10


class CollectorError(Exception):
    """Raised when a data collection operation fails.

    See docs/sub-specs/SS-02.md
    """


class SpotCollector:
    """Collects spot market data from Binance Spot API.

    See docs/sub-specs/SS-02.md §3.2
    """

    def __init__(self, config: dict, db_path: str) -> None:
        """Initialize the spot collector.

        See docs/sub-specs/SS-02.md

        Args:
            config: Full settings dict (reads spot_data section).
            db_path: Path to SQLite database.
        """
        self._config = config
        self._db_path = db_path
        spot_cfg = config["spot_data"]
        self._whale_threshold: float = spot_cfg["whale_trade_threshold_usd"]
        self._depth_levels: int = spot_cfg["orderbook_depth_levels"]
        self._volume_sma_period: int = spot_cfg["volume_sma_period"]

    async def _get(self, endpoint: str, params: dict | None = None) -> Any:
        """Make GET request to Binance API.

        See docs/sub-specs/SS-02.md

        Raises:
            CollectorError: On non-200 status or network failure.
        """
        url = f"{BASE_URL}{endpoint}"
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(
                            "Binance API error: %s %s → %d: %s",
                            "GET", endpoint, resp.status, text,
                        )
                        raise CollectorError(
                            f"Binance API returned {resp.status}"
                        )
                    return await resp.json()
        except aiohttp.ClientError as e:
            logger.error("Network error fetching %s: %s", endpoint, e)
            raise CollectorError(str(e)) from e
        except TimeoutError as e:
            logger.error("Timeout fetching %s", endpoint)
            raise CollectorError("Request timed out") from e

    async def fetch_price(self) -> dict[str, Any]:
        """Fetch latest 1h OHLCV candle, store in spot_price.

        See docs/sub-specs/SS-02.md §3.2

        Returns:
            Dict with timestamp, open, high, low, close, volume,
            quote_volume, num_trades.

        Raises:
            CollectorError: On HTTP/network failure.
        """
        data = await self._get(
            "/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1h", "limit": "1"},
        )
        candle = data[0]
        row = {
            "timestamp": datetime.fromtimestamp(
                candle[0] / 1000, tz=timezone.utc
            ).isoformat(),
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
            "volume": float(candle[5]),
            "quote_volume": float(candle[7]),
            "num_trades": int(candle[8]),
        }
        insert_row(self._db_path, "spot_price", row)
        logger.info("Stored spot price: close=%.2f", row["close"])
        return row

    async def fetch_orderbook(self) -> dict[str, Any]:
        """Fetch order book snapshot, compute imbalance and spread.

        See docs/sub-specs/SS-02.md §3.2

        Returns:
            Dict with timestamp, bid_depth_usd, ask_depth_usd,
            imbalance, spread_bps.

        Raises:
            CollectorError: On HTTP/network failure.
        """
        data = await self._get(
            "/api/v3/depth",
            params={"symbol": "BTCUSDT", "limit": str(self._depth_levels)},
        )
        bid_depth = sum(float(b[0]) * float(b[1]) for b in data["bids"])
        ask_depth = sum(float(a[0]) * float(a[1]) for a in data["asks"])

        total = bid_depth + ask_depth
        if total == 0:
            imbalance = 0.0
        else:
            imbalance = (bid_depth - ask_depth) / total

        if data["bids"] and data["asks"]:
            best_bid = float(data["bids"][0][0])
            best_ask = float(data["asks"][0][0])
            spread_bps = (
                (best_ask - best_bid) / best_bid * 10000 if best_bid > 0 else 0.0
            )
        else:
            spread_bps = 0.0

        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bid_depth_usd": bid_depth,
            "ask_depth_usd": ask_depth,
            "imbalance": imbalance,
            "spread_bps": spread_bps,
        }
        insert_row(self._db_path, "spot_orderbook", row)
        logger.info("Stored orderbook: imbalance=%.4f spread=%.2fbps", imbalance, spread_bps)
        return row

    async def fetch_trades(self) -> dict[str, Any]:
        """Fetch aggregated trades, compute CVD and detect whales.

        See docs/sub-specs/SS-02.md §3.2

        Returns:
            Dict with cvd_1h, cvd_4h, cvd_24h, buy_volume, sell_volume,
            whale_count.

        Raises:
            CollectorError: On HTTP/network failure.
        """
        data = await self._get(
            "/api/v3/aggTrades",
            params={"symbol": "BTCUSDT", "limit": "1000"},
        )

        now_ms = int(time.time() * 1000)
        ms_1h = 3600 * 1000
        ms_4h = 4 * ms_1h
        ms_24h = 24 * ms_1h

        buy_vol_1h = 0.0
        sell_vol_1h = 0.0
        buy_vol_4h = 0.0
        sell_vol_4h = 0.0
        buy_vol_24h = 0.0
        sell_vol_24h = 0.0
        whale_count = 0

        for trade in data:
            price = float(trade["p"])
            qty = float(trade["q"])
            trade_time = int(trade["T"])
            is_sell = trade["m"]  # isBuyerMaker: true=sell, false=buy
            age_ms = now_ms - trade_time
            value_usd = price * qty

            if age_ms <= ms_24h:
                if is_sell:
                    sell_vol_24h += qty
                else:
                    buy_vol_24h += qty

                if age_ms <= ms_4h:
                    if is_sell:
                        sell_vol_4h += qty
                    else:
                        buy_vol_4h += qty

                    if age_ms <= ms_1h:
                        if is_sell:
                            sell_vol_1h += qty
                        else:
                            buy_vol_1h += qty

            if value_usd >= self._whale_threshold:
                whale_row = {
                    "timestamp": datetime.fromtimestamp(
                        trade_time / 1000, tz=timezone.utc
                    ).isoformat(),
                    "side": "sell" if is_sell else "buy",
                    "price": price,
                    "quantity": qty,
                    "value_usd": value_usd,
                }
                insert_row(self._db_path, "spot_whale_trades", whale_row)
                whale_count += 1

        cvd_row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cvd_1h": buy_vol_1h - sell_vol_1h,
            "cvd_4h": buy_vol_4h - sell_vol_4h,
            "cvd_24h": buy_vol_24h - sell_vol_24h,
            "buy_volume": buy_vol_24h,
            "sell_volume": sell_vol_24h,
        }
        insert_row(self._db_path, "spot_cvd", cvd_row)
        logger.info(
            "Stored CVD: 1h=%.4f 4h=%.4f 24h=%.4f whales=%d",
            cvd_row["cvd_1h"], cvd_row["cvd_4h"], cvd_row["cvd_24h"], whale_count,
        )
        return {**cvd_row, "whale_count": whale_count}

    async def fetch_technicals(self) -> dict[str, Any]:
        """Fetch daily klines, compute technical indicators.

        See docs/sub-specs/SS-02.md §3.2

        Returns:
            Dict with rsi_14, ema_21, ema_55, ema_200, vwap, bb_upper,
            bb_lower, bb_width, adx_14, volume_sma_20, volume_ratio.

        Raises:
            CollectorError: On HTTP/network failure.
        """
        data = await self._get(
            "/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1d", "limit": "210"},
        )

        df = pd.DataFrame(
            data,
            columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "num_trades",
                "taker_buy_base", "taker_buy_quote", "ignore",
            ],
        )
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        # Technical indicators via ta library
        df["rsi_14"] = ta_lib.momentum.RSIIndicator(
            df["close"], window=14
        ).rsi()
        df["ema_21"] = ta_lib.trend.EMAIndicator(
            df["close"], window=21
        ).ema_indicator()
        df["ema_55"] = ta_lib.trend.EMAIndicator(
            df["close"], window=55
        ).ema_indicator()
        df["ema_200"] = ta_lib.trend.EMAIndicator(
            df["close"], window=200
        ).ema_indicator()
        # 20-day rolling VWAP (not cumulative over full 210-day window)
        _vwap_window = 20
        df["vwap"] = (
            (df["close"] * df["volume"]).rolling(_vwap_window).sum()
            / df["volume"].rolling(_vwap_window).sum()
        )

        bb_indicator = ta_lib.volatility.BollingerBands(
            df["close"], window=20, window_dev=2
        )
        df["bb_upper"] = bb_indicator.bollinger_hband()
        df["bb_lower"] = bb_indicator.bollinger_lband()
        df["bb_width"] = bb_indicator.bollinger_wband()

        adx_indicator = ta_lib.trend.ADXIndicator(
            df["high"], df["low"], df["close"], window=14
        )
        df["adx_14"] = adx_indicator.adx()

        sma_period = self._volume_sma_period
        df["volume_sma_20"] = df["volume"].rolling(sma_period).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma_20"]

        latest = df.iloc[-1]
        today = datetime.fromtimestamp(
            int(latest["open_time"]) / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%d")

        row = {
            "date": today,
            "rsi_14": _safe_float(latest.get("rsi_14")),
            "ema_21": _safe_float(latest.get("ema_21")),
            "ema_55": _safe_float(latest.get("ema_55")),
            "ema_200": _safe_float(latest.get("ema_200")),
            "vwap": _safe_float(latest.get("vwap")),
            "bb_upper": _safe_float(latest.get("bb_upper")),
            "bb_lower": _safe_float(latest.get("bb_lower")),
            "bb_width": _safe_float(latest.get("bb_width")),
            "adx_14": _safe_float(latest.get("adx_14")),
            "volume_sma_20": _safe_float(latest.get("volume_sma_20")),
            "volume_ratio": _safe_float(latest.get("volume_ratio")),
        }
        insert_row(self._db_path, "spot_technicals", row)
        logger.info("Stored technicals: RSI=%.1f ADX=%.1f", row["rsi_14"] or 0, row["adx_14"] or 0)
        return row


def _safe_float(value: Any) -> float | None:
    """Convert value to float, returning None for NaN/None.

    See docs/sub-specs/SS-02.md
    """
    if value is None:
        return None
    try:
        f = float(value)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None
