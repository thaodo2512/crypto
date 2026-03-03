"""Futures market data collector (Binance + Bybit + OKX + Coinglass).

See docs/sub-specs/SS-03.md §3.3
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from custom.collectors.spot import CollectorError
from custom.utils.db import get_latest, insert_row, query

logger = logging.getLogger(__name__)

BINANCE_URL = "https://fapi.binance.com"
BYBIT_URL = "https://api.bybit.com"
OKX_URL = "https://www.okx.com"
COINGLASS_URL = "https://open-api.coinglass.com"
REQUEST_TIMEOUT_SECONDS = 10


class FuturesCollector:
    """Collects futures data from Binance, Bybit, OKX, and Coinglass.

    See docs/sub-specs/SS-03.md §3.3
    """

    def __init__(self, config: dict, db_path: str) -> None:
        """Initialize the futures collector.

        See docs/sub-specs/SS-03.md

        Args:
            config: Full settings dict.
            db_path: Path to SQLite database.
        """
        self._config = config
        self._db_path = db_path

    async def _get(self, url: str, params: dict | None = None) -> Any:
        """Make GET request to any exchange API.

        See docs/sub-specs/SS-03.md

        Raises:
            CollectorError: On non-200 status or network failure.
        """
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error("API error: GET %s → %d: %s", url, resp.status, text)
                        raise CollectorError(f"API returned {resp.status}")
                    return await resp.json()
        except aiohttp.ClientError as e:
            logger.error("Network error fetching %s: %s", url, e)
            raise CollectorError(str(e)) from e
        except TimeoutError as e:
            logger.error("Timeout fetching %s", url)
            raise CollectorError("Request timed out") from e

    # ─── Private fetch methods (per exchange) ────────────

    async def _fetch_binance_funding(self) -> float | None:
        """Fetch latest funding rate from Binance.

        See docs/sub-specs/SS-03.md §3.3
        """
        try:
            data = await self._get(
                f"{BINANCE_URL}/fapi/v1/fundingRate",
                params={"symbol": "BTCUSDT", "limit": "1"},
            )
            return float(data[0]["fundingRate"])
        except (CollectorError, KeyError, IndexError) as e:
            logger.warning("Binance funding unavailable: %s", e)
            return None

    async def _fetch_bybit_funding(self) -> float | None:
        """Fetch latest funding rate from Bybit.

        See docs/sub-specs/SS-03.md §3.3
        """
        try:
            data = await self._get(
                f"{BYBIT_URL}/v5/market/funding/history",
                params={"category": "linear", "symbol": "BTCUSDT", "limit": "1"},
            )
            return float(data["result"]["list"][0]["fundingRate"])
        except (CollectorError, KeyError, IndexError) as e:
            logger.warning("Bybit funding unavailable: %s", e)
            return None

    async def _fetch_okx_funding(self) -> float | None:
        """Fetch latest funding rate from OKX.

        See docs/sub-specs/SS-03.md §3.3
        """
        try:
            data = await self._get(
                f"{OKX_URL}/api/v5/public/funding-rate",
                params={"instId": "BTC-USDT-SWAP"},
            )
            return float(data["data"][0]["fundingRate"])
        except (CollectorError, KeyError, IndexError) as e:
            logger.warning("OKX funding unavailable: %s", e)
            return None

    async def _fetch_binance_oi(self) -> float | None:
        """Fetch open interest (BTC) from Binance.

        See docs/sub-specs/SS-03.md §3.3

        Returns:
            OI in BTC, or None on failure.
        """
        try:
            data = await self._get(
                f"{BINANCE_URL}/fapi/v1/openInterest",
                params={"symbol": "BTCUSDT"},
            )
            return float(data["openInterest"])
        except (CollectorError, KeyError) as e:
            logger.warning("Binance OI unavailable: %s", e)
            return None

    async def _fetch_bybit_oi(self) -> float | None:
        """Fetch open interest (BTC) from Bybit.

        See docs/sub-specs/SS-03.md §3.3

        Returns:
            OI in BTC, or None on failure.
        """
        try:
            data = await self._get(
                f"{BYBIT_URL}/v5/market/open-interest",
                params={"category": "linear", "symbol": "BTCUSDT", "intervalTime": "5min", "limit": "1"},
            )
            return float(data["result"]["list"][0]["openInterest"])
        except (CollectorError, KeyError, IndexError) as e:
            logger.warning("Bybit OI unavailable: %s", e)
            return None

    async def _fetch_okx_oi(self) -> float | None:
        """Fetch open interest (BTC) from OKX.

        See docs/sub-specs/SS-03.md §3.3

        Uses oiCcy field which returns OI in BTC (not raw contract count).

        Returns:
            OI in BTC, or None on failure.
        """
        try:
            data = await self._get(
                f"{OKX_URL}/api/v5/public/open-interest",
                params={"instType": "SWAP", "instId": "BTC-USDT-SWAP"},
            )
            return float(data["data"][0]["oiCcy"])
        except (CollectorError, KeyError, IndexError) as e:
            logger.warning("OKX OI unavailable: %s", e)
            return None

    # ─── Public methods ──────────────────────────────────

    async def fetch_snapshot(self) -> dict[str, Any]:
        """Collect full futures snapshot from all sources.

        See docs/sub-specs/SS-03.md §3.3

        Returns:
            Dict matching futures_snapshot table columns.

        Raises:
            CollectorError: If ALL primary sources (Binance, Bybit, OKX) fail.
        """
        # Fetch funding + OI from all exchanges concurrently
        (
            funding_binance, funding_bybit, funding_okx,
            oi_binance, oi_bybit, oi_okx,
        ) = await asyncio.gather(
            self._fetch_binance_funding(),
            self._fetch_bybit_funding(),
            self._fetch_okx_funding(),
            self._fetch_binance_oi(),
            self._fetch_bybit_oi(),
            self._fetch_okx_oi(),
        )

        # Check if all sources failed
        all_funding_none = all(f is None for f in [funding_binance, funding_bybit, funding_okx])
        all_oi_none = all(o is None for o in [oi_binance, oi_bybit, oi_okx])
        if all_funding_none and all_oi_none:
            raise CollectorError("All futures sources failed")

        # OI-weighted funding rate (uses BTC OI for weighting — ratio is unitless)
        funding_weighted_avg = _compute_weighted_funding(
            fundings=[funding_binance, funding_bybit, funding_okx],
            ois=[oi_binance, oi_bybit, oi_okx],
        )

        # Fetch Binance-specific data (L/S, taker, premium)
        top_trader_ls = await self._safe_fetch_ratio(
            f"{BINANCE_URL}/futures/data/topLongShortPositionRatio",
            {"symbol": "BTCUSDT", "period": "1h", "limit": "1"},
        )
        global_ls = await self._safe_fetch_ratio(
            f"{BINANCE_URL}/futures/data/globalLongShortAccountRatio",
            {"symbol": "BTCUSDT", "period": "1h", "limit": "1"},
        )
        taker = await self._safe_fetch_taker()
        premium = await self._safe_fetch_premium()

        # Convert OI from BTC to USD using mark price
        btc_price = float(premium["futures_price"]) if premium else None
        if btc_price and btc_price > 0:
            oi_binance = oi_binance * btc_price if oi_binance is not None else None
            oi_bybit = oi_bybit * btc_price if oi_bybit is not None else None
            oi_okx = oi_okx * btc_price if oi_okx is not None else None
        else:
            logger.warning("No BTC price available — OI stored in BTC, not USD")

        # OI total (sum of available, now in USD)
        oi_values = [v for v in [oi_binance, oi_bybit, oi_okx] if v is not None]
        oi_total = sum(oi_values) if oi_values else None

        # OI change percentages from historical data
        oi_change_1h = _compute_oi_change(self._db_path, oi_total, hours=1)
        oi_change_4h = _compute_oi_change(self._db_path, oi_total, hours=4)
        oi_change_24h = _compute_oi_change(self._db_path, oi_total, hours=24)

        # Basis calculation
        basis_pct = None
        annualized_premium_pct = None
        futures_price = premium.get("futures_price") if premium else None
        spot_price = premium.get("spot_price") if premium else None
        if futures_price and spot_price and spot_price > 0:
            basis_pct = (futures_price - spot_price) / spot_price * 100
            # Perp approximation: funding × 3 × 365 for annualized
            if funding_weighted_avg is not None:
                annualized_premium_pct = funding_weighted_avg * 3 * 365 * 100

        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "funding_binance": funding_binance,
            "funding_bybit": funding_bybit,
            "funding_okx": funding_okx,
            "funding_weighted_avg": funding_weighted_avg,
            "oi_binance_usd": oi_binance,
            "oi_bybit_usd": oi_bybit,
            "oi_okx_usd": oi_okx,
            "oi_total_usd": oi_total,
            "oi_change_1h_pct": oi_change_1h,
            "oi_change_4h_pct": oi_change_4h,
            "oi_change_24h_pct": oi_change_24h,
            "futures_price": futures_price,
            "spot_price": spot_price,
            "basis_pct": basis_pct,
            "annualized_premium_pct": annualized_premium_pct,
            "top_trader_ls_ratio": top_trader_ls,
            "account_ls_ratio": global_ls.get("account") if global_ls else None,
            "global_ls_ratio": global_ls.get("ratio") if global_ls else None,
            "taker_buy_sell_ratio": taker.get("ratio") if taker else None,
            "taker_buy_volume": taker.get("buy_vol") if taker else None,
            "taker_sell_volume": taker.get("sell_vol") if taker else None,
        }
        insert_row(self._db_path, "futures_snapshot", row)
        logger.info(
            "Stored futures snapshot: funding_avg=%s oi_total=%s basis=%s",
            funding_weighted_avg, oi_total, basis_pct,
        )
        return row

    async def fetch_oi_price_regime(self) -> dict[str, Any]:
        """Classify OI-price relationship and store in futures_oi_price.

        See docs/sub-specs/SS-03.md §3.3

        Returns:
            Dict with price, total_oi, oi_change_pct, price_change_pct, regime.
        """
        snapshots = get_latest(self._db_path, "futures_snapshot", n=2)
        if len(snapshots) < 2:
            logger.warning("Not enough snapshots for OI-price regime")
            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "price": snapshots[0]["futures_price"] if snapshots else None,
                "total_oi": snapshots[0]["oi_total_usd"] if snapshots else None,
                "oi_change_pct": None,
                "price_change_pct": None,
                "regime": None,
            }
            insert_row(self._db_path, "futures_oi_price", row)
            return row

        current, previous = snapshots[0], snapshots[1]
        curr_oi = current["oi_total_usd"]
        prev_oi = previous["oi_total_usd"]
        curr_price = current["futures_price"]
        prev_price = previous["futures_price"]

        if prev_oi and prev_oi > 0:
            oi_change_pct = (curr_oi - prev_oi) / prev_oi * 100
        else:
            oi_change_pct = None

        if prev_price and prev_price > 0:
            price_change_pct = (curr_price - prev_price) / prev_price * 100
        else:
            price_change_pct = None

        regime = _classify_regime(oi_change_pct, price_change_pct)

        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "price": curr_price,
            "total_oi": curr_oi,
            "oi_change_pct": oi_change_pct,
            "price_change_pct": price_change_pct,
            "regime": regime,
        }
        insert_row(self._db_path, "futures_oi_price", row)
        logger.info("Stored OI-price regime: %s (OI=%.2f%% Price=%.2f%%)",
                     regime, oi_change_pct or 0, price_change_pct or 0)
        return row

    async def fetch_liquidations(self) -> dict[str, Any]:
        """Fetch liquidation data from Coinglass.

        See docs/sub-specs/SS-03.md §3.3

        Returns:
            Dict with long_liq_usd, short_liq_usd, total_liq_usd, liq_ratio.
        """
        try:
            data = await self._get(
                f"{COINGLASS_URL}/public/v2/liquidation_history",
                params={"symbol": "BTC", "time_type": "all"},
            )
            long_liq = float(data["data"][0].get("longLiquidationUsd", 0))
            short_liq = float(data["data"][0].get("shortLiquidationUsd", 0))
        except (CollectorError, KeyError, IndexError, TypeError) as e:
            logger.warning("Coinglass liquidations unavailable: %s", e)
            long_liq = None
            short_liq = None

        if long_liq is not None and short_liq is not None:
            total_liq = long_liq + short_liq
            liq_ratio = long_liq / total_liq if total_liq > 0 else 0.5
        else:
            total_liq = None
            liq_ratio = None

        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "long_liq_usd": long_liq,
            "short_liq_usd": short_liq,
            "total_liq_usd": total_liq,
            "liq_ratio": liq_ratio,
        }
        insert_row(self._db_path, "futures_liquidations", row)
        logger.info("Stored liquidations: long=%s short=%s ratio=%s",
                     long_liq, short_liq, liq_ratio)
        return row

    # ─── Helper fetch methods ────────────────────────────

    async def _safe_fetch_ratio(
        self, url: str, params: dict
    ) -> float | dict | None:
        """Fetch L/S ratio from Binance, return None on failure.

        See docs/sub-specs/SS-03.md §3.3
        """
        try:
            data = await self._get(url, params)
            if "globalLongShortAccountRatio" in url:
                return {
                    "ratio": float(data[0]["longShortRatio"]),
                    "account": float(data[0]["longAccount"]),
                }
            return float(data[0]["longShortRatio"])
        except (CollectorError, KeyError, IndexError) as e:
            logger.warning("L/S ratio unavailable from %s: %s", url, e)
            return None

    async def _safe_fetch_taker(self) -> dict | None:
        """Fetch taker buy/sell ratio from Binance.

        See docs/sub-specs/SS-03.md §3.3
        """
        try:
            data = await self._get(
                f"{BINANCE_URL}/futures/data/takerlongshortRatio",
                params={"symbol": "BTCUSDT", "period": "1h", "limit": "1"},
            )
            return {
                "ratio": float(data[0]["buySellRatio"]),
                "buy_vol": float(data[0]["buyVol"]),
                "sell_vol": float(data[0]["sellVol"]),
            }
        except (CollectorError, KeyError, IndexError) as e:
            logger.warning("Taker ratio unavailable: %s", e)
            return None

    async def _safe_fetch_premium(self) -> dict | None:
        """Fetch premium index (mark/index price) from Binance.

        See docs/sub-specs/SS-03.md §3.3
        """
        try:
            data = await self._get(
                f"{BINANCE_URL}/fapi/v1/premiumIndex",
                params={"symbol": "BTCUSDT"},
            )
            return {
                "futures_price": float(data["markPrice"]),
                "spot_price": float(data["indexPrice"]),
            }
        except (CollectorError, KeyError) as e:
            logger.warning("Premium index unavailable: %s", e)
            return None


# ─── Module-level helpers ────────────────────────────────


def _compute_weighted_funding(
    fundings: list[float | None],
    ois: list[float | None],
) -> float | None:
    """Compute OI-weighted average funding rate.

    See docs/sub-specs/SS-03.md §3.3

    Falls back to simple average if no OI data available.
    Returns None if no funding data available.
    """
    available = [
        (f, o) for f, o in zip(fundings, ois)
        if f is not None
    ]
    if not available:
        return None

    # Check if we have OI data for weighting
    with_oi = [(f, o) for f, o in available if o is not None and o > 0]
    if with_oi:
        total_oi = sum(o for _, o in with_oi)
        return sum(f * o for f, o in with_oi) / total_oi

    # Fallback: simple average of available funding rates
    return sum(f for f, _ in available) / len(available)


def _compute_oi_change(
    db_path: str, current_oi: float | None, hours: int
) -> float | None:
    """Compute OI change percentage vs X hours ago.

    See docs/sub-specs/SS-03.md §3.3
    """
    if current_oi is None:
        return None
    rows = query(
        db_path,
        "SELECT oi_total_usd FROM futures_snapshot "
        "WHERE timestamp <= datetime('now', ?) "
        "ORDER BY timestamp DESC LIMIT 1",
        (f"-{hours} hours",),
    )
    if not rows or rows[0]["oi_total_usd"] is None:
        return None
    prev_oi = rows[0]["oi_total_usd"]
    if prev_oi == 0:
        return None
    return (current_oi - prev_oi) / prev_oi * 100


def _classify_regime(
    oi_change_pct: float | None, price_change_pct: float | None
) -> str | None:
    """Classify OI-price regime.

    See docs/sub-specs/SS-03.md §3.3

    Returns:
        One of NEW_LONGS, NEW_SHORTS, LONG_CLOSING, SHORT_CLOSING, or None.
    """
    if oi_change_pct is None or price_change_pct is None:
        return None
    oi_up = oi_change_pct >= 0
    price_up = price_change_pct >= 0
    if oi_up and price_up:
        return "NEW_LONGS"
    if oi_up and not price_up:
        return "NEW_SHORTS"
    if not oi_up and not price_up:
        return "LONG_CLOSING"
    return "SHORT_CLOSING"
