"""Options market data collector (Deribit API).

See docs/sub-specs/SS-04.md §3.4
"""

import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from custom.collectors.spot import CollectorError
from custom.utils.db import insert_row

logger = logging.getLogger(__name__)

DERIBIT_URL = "https://www.deribit.com/api/v2"
REQUEST_TIMEOUT_SECONDS = 10


class OptionsCollector:
    """Collects options market data from Deribit API.

    See docs/sub-specs/SS-04.md §3.4
    """

    def __init__(self, config: dict, db_path: str, currency: str = "BTC") -> None:
        """Initialize the options collector.

        See docs/sub-specs/SS-04.md

        Args:
            config: Full settings dict.
            db_path: Path to SQLite database.
            currency: Deribit currency (e.g. "BTC", "ETH").
        """
        self._config = config
        self._db_path = db_path
        self._currency = currency
        self._whale_threshold: float = config["spot_data"]["whale_trade_threshold_usd"]

    async def _get(self, endpoint: str, params: dict | None = None) -> Any:
        """Make GET request to Deribit API.

        See docs/sub-specs/SS-04.md

        Args:
            endpoint: API endpoint path (e.g. /public/get_instruments).
            params: Optional query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            CollectorError: On non-200 status or network failure.
        """
        url = f"{DERIBIT_URL}{endpoint}"
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

    async def fetch_instruments(self) -> list[dict[str, Any]]:
        """Enumerate all active BTC option contracts on Deribit.

        See docs/sub-specs/SS-04.md §3.4

        Returns:
            List of dicts with instrument_name, strike, expiry, option_type.

        Raises:
            CollectorError: If the instruments API call fails.
        """
        data = await self._get(
            "/public/get_instruments",
            params={"currency": self._currency, "kind": "option"},
        )
        instruments = []
        for item in data.get("result", []):
            if not item.get("is_active", False):
                continue
            parsed = _parse_instrument_name(item["instrument_name"], self._currency)
            if parsed is None:
                logger.warning("Could not parse instrument: %s", item["instrument_name"])
                continue
            instruments.append(parsed)
        logger.info("Fetched %d active %s option instruments", len(instruments), self._currency)
        return instruments

    async def fetch_options_chain(self) -> list[dict[str, Any]]:
        """Fetch full options chain and store in options_oi table.

        See docs/sub-specs/SS-04.md §3.4

        Uses get_book_summary_by_currency for efficient batch fetch.
        Aggregates call and put data at same strike/expiry into single rows.

        Returns:
            List of stored rows (one per strike/expiry).
        """
        try:
            data = await self._get(
                "/public/get_book_summary_by_currency",
                params={"currency": self._currency, "kind": "option"},
            )
        except CollectorError as e:
            logger.warning("Options chain unavailable: %s", e)
            return []

        summaries = data.get("result", [])
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Aggregate by (strike, expiry)
        aggregated: dict[tuple[float, str], dict[str, Any]] = {}
        for item in summaries:
            parsed = _parse_instrument_name(item.get("instrument_name", ""), self._currency)
            if parsed is None:
                continue
            strike = parsed["strike"]
            expiry = parsed["expiry"]
            key = (strike, expiry)

            if key not in aggregated:
                aggregated[key] = {
                    "date": today,
                    "expiry": expiry,
                    "strike": strike,
                    "call_oi": None,
                    "put_oi": None,
                    "call_iv": None,
                    "put_iv": None,
                    "call_volume": None,
                    "put_volume": None,
                }

            oi = _safe_float(item.get("open_interest"))
            iv = _safe_float(item.get("mark_iv"))
            volume = _safe_float(item.get("volume"))

            if parsed["option_type"] == "call":
                aggregated[key]["call_oi"] = oi
                aggregated[key]["call_iv"] = iv
                aggregated[key]["call_volume"] = volume
            else:
                aggregated[key]["put_oi"] = oi
                aggregated[key]["put_iv"] = iv
                aggregated[key]["put_volume"] = volume

        rows = []
        for row in aggregated.values():
            insert_row(self._db_path, "options_oi", row)
            rows.append(row)

        logger.info("Stored %d options_oi rows (%d instruments)", len(rows), len(summaries))
        return rows

    async def fetch_index_price(self) -> float | None:
        """Fetch BTC index price from Deribit.

        See docs/sub-specs/SS-04.md §3.4

        Returns:
            BTC index price as float, or None on failure.
        """
        try:
            data = await self._get(
                "/public/get_index_price",
                params={"index_name": f"{self._currency.lower()}_usd"},
            )
            return float(data["result"]["index_price"])
        except (CollectorError, KeyError, TypeError) as e:
            logger.warning("Index price unavailable: %s", e)
            return None

    async def fetch_dvol(self) -> float | None:
        """Fetch Deribit DVol (implied volatility index).

        See docs/sub-specs/SS-04.md §3.4

        Uses /public/get_volatility_index_data with a short lookback window
        to get the latest DVol value.

        Returns:
            DVol index as float (annualized IV percentage), or None on failure.
        """
        try:
            import time as _time

            now_ms = int(_time.time() * 1000)
            # 2-hour lookback to ensure we get at least one data point
            start_ms = now_ms - 2 * 3600 * 1000

            data = await self._get(
                "/public/get_volatility_index_data",
                params={
                    "currency": self._currency,
                    "start_timestamp": start_ms,
                    "end_timestamp": now_ms,
                    "resolution": 3600,
                },
            )
            # Response: {"result": {"data": [[ts, open, high, low, close], ...], ...}}
            points = data["result"]["data"]
            if not points:
                logger.warning("DVol unavailable: no data points returned")
                return None
            # Latest point is last; close is index 4
            return float(points[-1][4])
        except (CollectorError, KeyError, TypeError, IndexError) as e:
            logger.warning("DVol unavailable: %s", e)
            return None

    async def fetch_large_trades(
        self, index_price: float | None = None
    ) -> list[dict[str, Any]]:
        """Fetch recent options trades and filter for large/whale trades.

        See docs/sub-specs/SS-04.md §3.4

        Args:
            index_price: BTC index price for USD value calculation.
                If None, attempts to fetch it.

        Returns:
            List of qualifying large trade dicts stored in options_large_trades.
        """
        if index_price is None:
            index_price = await self.fetch_index_price()
        if index_price is None:
            logger.warning("Cannot compute trade USD values without index price")
            return []

        try:
            data = await self._get(
                "/public/get_last_trades_by_currency",
                params={"currency": self._currency, "kind": "option", "count": "100"},
            )
        except CollectorError as e:
            logger.warning("Large trades unavailable: %s", e)
            return []

        trades = data.get("result", {}).get("trades", [])
        large_trades = []
        for t in trades:
            amount = _safe_float(t.get("amount"))
            price = _safe_float(t.get("price"))
            if amount is None or price is None:
                continue
            value_usd = amount * price * index_price
            if value_usd < self._whale_threshold:
                continue

            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "instrument": t.get("instrument_name"),
                "direction": t.get("direction"),
                "amount": amount,
                "price": price,
                "iv": _safe_float(t.get("iv")),
                "value_usd": value_usd,
            }
            insert_row(self._db_path, "options_large_trades", row)
            large_trades.append(row)

        logger.info(
            "Found %d large trades out of %d total", len(large_trades), len(trades)
        )
        return large_trades

    async def fetch_snapshot(self) -> dict[str, Any]:
        """Orchestrate a full options scan from Deribit.

        See docs/sub-specs/SS-04.md §3.4

        Calls fetch_instruments, fetch_options_chain, fetch_index_price,
        fetch_dvol, fetch_large_trades. Returns a summary dict.

        Returns:
            Summary dict with totals, ratios, dvol, index_price, trade count.

        Raises:
            CollectorError: If instruments endpoint fails (nothing to scan).
        """
        # Instruments must succeed — it's the critical path
        instruments = await self.fetch_instruments()

        # Remaining endpoints use graceful degradation
        chain = await self.fetch_options_chain()
        index_price = await self.fetch_index_price()
        dvol = await self.fetch_dvol()
        large_trades = await self.fetch_large_trades(index_price=index_price)

        # Compute totals from chain
        total_call_oi = sum(r["call_oi"] or 0 for r in chain)
        total_put_oi = sum(r["put_oi"] or 0 for r in chain)
        total_call_volume = sum(r["call_volume"] or 0 for r in chain)
        total_put_volume = sum(r["put_volume"] or 0 for r in chain)

        put_call_ratio_oi = (
            total_put_oi / total_call_oi if total_call_oi > 0 else None
        )
        put_call_ratio_volume = (
            total_put_volume / total_call_volume if total_call_volume > 0 else None
        )

        summary = {
            "total_instruments": len(instruments),
            "total_call_oi": total_call_oi,
            "total_put_oi": total_put_oi,
            "put_call_ratio_oi": put_call_ratio_oi,
            "put_call_ratio_volume": put_call_ratio_volume,
            "dvol": dvol,
            "index_price": index_price,
            "large_trades_count": len(large_trades),
        }
        logger.info(
            "Options snapshot: %d instruments, P/C OI=%.3f, DVol=%s",
            len(instruments),
            put_call_ratio_oi or 0,
            dvol,
        )
        return summary


def _parse_instrument_name(name: str, currency: str = "BTC") -> dict[str, Any] | None:
    """Parse Deribit instrument name into components.

    See docs/sub-specs/SS-04.md §3.4

    Format: 'BTC-28MAR26-85000-C' → {instrument_name, strike, expiry, option_type}

    Args:
        name: Deribit instrument name string.
        currency: Expected currency prefix (e.g. "BTC", "ETH").

    Returns:
        Parsed dict, or None if format is invalid.
    """
    parts = name.split("-")
    if len(parts) != 4:
        return None
    inst_currency, expiry_str, strike_str, type_char = parts
    if inst_currency != currency:
        return None
    if type_char not in ("C", "P"):
        return None
    try:
        strike = float(strike_str)
    except ValueError:
        return None
    return {
        "instrument_name": name,
        "strike": strike,
        "expiry": expiry_str,
        "option_type": "call" if type_char == "C" else "put",
    }


def _safe_float(value: Any) -> float | None:
    """Convert value to float, returning None on failure.

    See docs/sub-specs/SS-04.md §3.4
    """
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
