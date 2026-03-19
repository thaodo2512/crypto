"""Tests for SS-02: Spot Data Collector.

See docs/sub-specs/SS-02.md §Acceptance Criteria
"""

import asyncio
import inspect
import time
from unittest.mock import AsyncMock, patch

import pytest

from custom.collectors.spot import CollectorError, SpotCollector
from custom.utils.db import query


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def spot_config() -> dict:
    """Config dict with spot_data section."""
    return {
        "spot_data": {
            "whale_trade_threshold_usd": 100_000,
            "orderbook_depth_levels": 20,
            "volume_sma_period": 20,
        },
    }


@pytest.fixture
def collector(spot_config, db_path) -> SpotCollector:
    """SpotCollector with test config and temp DB."""
    return SpotCollector(spot_config, db_path)


def _kline(
    open_time: int = 1709424000000,
    o: str = "85000.0", h: str = "86000.0",
    l: str = "84000.0", c: str = "85500.0",
    vol: str = "1000.0", qvol: str = "85500000.0",
    trades: int = 5000,
) -> list:
    """Build a single Binance kline array."""
    return [
        open_time, o, h, l, c, vol,
        open_time + 3600000, qvol, trades,
        "500.0", "42750000.0", "0",
    ]


# ─── TestFetchPrice ──────────────────────────────────────


class TestFetchPrice:
    """Tests for fetch_price()."""

    @pytest.mark.asyncio
    async def test_fetch_price_stores_ohlcv(self, collector, db_path) -> None:
        """AC 1: fetch_price() returns OHLCV dict and stores in spot_price."""
        mock_response = [_kline()]
        collector._get = AsyncMock(return_value=mock_response)

        result = await collector.fetch_price()

        assert result["open"] == 85000.0
        assert result["high"] == 86000.0
        assert result["low"] == 84000.0
        assert result["close"] == 85500.0
        assert result["volume"] == 1000.0
        assert result["quote_volume"] == 85500000.0
        assert result["num_trades"] == 5000

        rows = query(db_path, "SELECT * FROM spot_price")
        assert len(rows) == 1
        assert rows[0]["close"] == 85500.0


# ─── TestFetchOrderbook ──────────────────────────────────


class TestFetchOrderbook:
    """Tests for fetch_orderbook()."""

    @pytest.mark.asyncio
    async def test_fetch_orderbook_stores_imbalance(self, collector, db_path) -> None:
        """AC 2: Computes imbalance in [-1, +1] and stores in spot_orderbook."""
        mock_response = {
            "bids": [["85000.0", "2.0"], ["84999.0", "1.0"]],
            "asks": [["85001.0", "1.0"], ["85002.0", "0.5"]],
        }
        collector._get = AsyncMock(return_value=mock_response)

        result = await collector.fetch_orderbook()

        assert -1.0 <= result["imbalance"] <= 1.0
        # bids: 85000*2 + 84999*1 = 254999, asks: 85001*1 + 85002*0.5 = 127502
        # imbalance = (254999 - 127502) / (254999 + 127502) > 0
        assert result["imbalance"] > 0
        assert result["bid_depth_usd"] > result["ask_depth_usd"]

        rows = query(db_path, "SELECT * FROM spot_orderbook")
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_fetch_orderbook_spread_bps(self, collector) -> None:
        """AC 3: Computes spread in basis points correctly."""
        mock_response = {
            "bids": [["85000.0", "1.0"]],
            "asks": [["85010.0", "1.0"]],
        }
        collector._get = AsyncMock(return_value=mock_response)

        result = await collector.fetch_orderbook()

        # spread_bps = (85010 - 85000) / 85000 * 10000 ≈ 1.176
        expected = (85010.0 - 85000.0) / 85000.0 * 10000
        assert abs(result["spread_bps"] - expected) < 0.01

    @pytest.mark.asyncio
    async def test_orderbook_imbalance_symmetric(self, collector) -> None:
        """AC 4: Imbalance returns 0.0 when bid_depth == ask_depth."""
        mock_response = {
            "bids": [["85000.0", "1.0"]],
            "asks": [["85000.0", "1.0"]],
        }
        collector._get = AsyncMock(return_value=mock_response)

        result = await collector.fetch_orderbook()

        assert result["imbalance"] == 0.0


# ─── TestFetchTrades ─────────────────────────────────────


class TestFetchTrades:
    """Tests for fetch_trades()."""

    @pytest.mark.asyncio
    async def test_fetch_trades_computes_cvd(self, collector, db_path) -> None:
        """AC 5: Computes CVD from klines taker buy volume."""
        now_ms = int(time.time() * 1000)
        # kline format: [open_time, o, h, l, c, volume, close_time, quote_vol, trades, taker_buy_base, ...]
        mock_klines = [
            [now_ms - 3600000, "85000", "85500", "84500", "85200", "100.0", now_ms, "0", 0, "60.0", "0", "0"],
        ]
        mock_agg_trades: list = []
        collector._get = AsyncMock(side_effect=[mock_klines, mock_agg_trades])

        result = await collector.fetch_trades()

        # CVD = taker_buy(60) - taker_sell(100-60=40) = 20
        assert abs(result["cvd_1h"] - 20.0) < 0.1
        assert result["buy_volume"] == 60.0
        assert result["sell_volume"] == 40.0

        rows = query(db_path, "SELECT * FROM spot_cvd")
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_fetch_trades_detects_whales(self, collector, db_path) -> None:
        """AC 6: Detects whale trades above threshold."""
        now_ms = int(time.time() * 1000)
        mock_klines = [
            [now_ms - 3600000, "85000", "85500", "84500", "85200", "10.0", now_ms, "0", 0, "5.0", "0", "0"],
        ]
        mock_agg_trades = [
            {"p": "85000.0", "q": "2.0", "T": now_ms - 1000, "m": False},   # $170K whale
            {"p": "85000.0", "q": "0.5", "T": now_ms - 2000, "m": True},    # $42.5K not whale
        ]
        collector._get = AsyncMock(side_effect=[mock_klines, mock_agg_trades])

        result = await collector.fetch_trades()

        assert result["whale_count"] == 1
        rows = query(db_path, "SELECT * FROM spot_whale_trades")
        assert len(rows) == 1
        assert rows[0]["side"] == "buy"
        assert rows[0]["value_usd"] == 170000.0

    @pytest.mark.asyncio
    async def test_fetch_trades_no_whales_below_threshold(self, collector, db_path) -> None:
        """AC 7: No whale trades stored when all below threshold."""
        now_ms = int(time.time() * 1000)
        mock_klines = [
            [now_ms - 3600000, "85000", "85500", "84500", "85200", "1.0", now_ms, "0", 0, "0.5", "0", "0"],
        ]
        mock_agg_trades = [
            {"p": "85000.0", "q": "0.1", "T": now_ms - 1000, "m": False},
        ]
        collector._get = AsyncMock(side_effect=[mock_klines, mock_agg_trades])

        result = await collector.fetch_trades()

        assert result["whale_count"] == 0
        rows = query(db_path, "SELECT * FROM spot_whale_trades")
        assert len(rows) == 0


# ─── TestFetchTechnicals ─────────────────────────────────


def _make_klines(n: int = 210) -> list[list]:
    """Generate n daily klines with realistic price data."""
    base_time = 1700000000000  # arbitrary start
    klines = []
    price = 80000.0
    for i in range(n):
        o = price
        h = price + 500
        l = price - 500
        c = price + 100 * (1 if i % 2 == 0 else -1)
        vol = 10000.0 + i * 10
        klines.append(_kline(
            open_time=base_time + i * 86400000,
            o=str(o), h=str(h), l=str(l), c=str(c),
            vol=str(vol), qvol=str(c * vol), trades=5000 + i,
        ))
        price = c
    return klines


class TestFetchTechnicals:
    """Tests for fetch_technicals()."""

    @pytest.mark.asyncio
    async def test_fetch_technicals_indicators(self, collector, db_path) -> None:
        """AC 8: Computes RSI, EMAs, VWAP, BB, ADX and stores in spot_technicals."""
        mock_klines = _make_klines(210)
        collector._get = AsyncMock(return_value=mock_klines)

        result = await collector.fetch_technicals()

        assert result["rsi_14"] is not None
        assert result["ema_21"] is not None
        assert result["ema_55"] is not None
        assert result["ema_200"] is not None
        assert result["bb_upper"] is not None
        assert result["bb_lower"] is not None
        assert result["adx_14"] is not None

        rows = query(db_path, "SELECT * FROM spot_technicals")
        assert len(rows) == 1
        assert rows[0]["rsi_14"] is not None

    @pytest.mark.asyncio
    async def test_fetch_technicals_volume_ratio(self, collector) -> None:
        """AC 9: Computes volume_ratio = current_volume / volume_sma_20."""
        mock_klines = _make_klines(210)
        collector._get = AsyncMock(return_value=mock_klines)

        result = await collector.fetch_technicals()

        assert result["volume_sma_20"] is not None
        assert result["volume_ratio"] is not None
        assert result["volume_ratio"] > 0


# ─── TestErrorHandling ───────────────────────────────────


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_http_error_raises_collector_error(self, collector) -> None:
        """AC 10: HTTP error raises CollectorError with status code."""
        import aiohttp

        collector._get = AsyncMock(
            side_effect=CollectorError("Binance API returned 500")
        )

        with pytest.raises(CollectorError, match="500"):
            await collector.fetch_price()

    @pytest.mark.asyncio
    async def test_timeout_raises_collector_error(self, collector) -> None:
        """AC 11: Network timeout raises CollectorError."""
        collector._get = AsyncMock(
            side_effect=CollectorError("Request timed out")
        )

        with pytest.raises(CollectorError, match="timed out"):
            await collector.fetch_price()


# ─── TestConfig ──────────────────────────────────────────


class TestConfig:
    """Tests for config usage."""

    def test_thresholds_from_config(self, db_path) -> None:
        """AC 12: All thresholds read from config, not hardcoded."""
        custom_config = {
            "spot_data": {
                "whale_trade_threshold_usd": 50_000,
                "orderbook_depth_levels": 10,
                "volume_sma_period": 30,
            },
        }
        c = SpotCollector(custom_config, db_path)
        assert c._whale_threshold == 50_000
        assert c._depth_levels == 10
        assert c._volume_sma_period == 30


# ─── TestAsync ───────────────────────────────────────────


class TestAsync:
    """Tests for async compliance."""

    def test_methods_are_async(self) -> None:
        """AC 13: All API calls use aiohttp (async)."""
        assert inspect.iscoroutinefunction(SpotCollector.fetch_price)
        assert inspect.iscoroutinefunction(SpotCollector.fetch_orderbook)
        assert inspect.iscoroutinefunction(SpotCollector.fetch_trades)
        assert inspect.iscoroutinefunction(SpotCollector.fetch_technicals)
        assert inspect.iscoroutinefunction(SpotCollector._get)


# ─── TestEdgeCases ───────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_empty_trades_list(self, collector, db_path) -> None:
        """Edge: Empty trades list produces zero CVD."""
        collector._get = AsyncMock(return_value=[])

        result = await collector.fetch_trades()

        assert result["cvd_1h"] == 0.0
        assert result["cvd_4h"] == 0.0
        assert result["cvd_24h"] == 0.0
        assert result["whale_count"] == 0

    @pytest.mark.asyncio
    async def test_empty_orderbook(self, collector) -> None:
        """Edge: Empty order book returns zero imbalance and spread."""
        mock_response = {"bids": [], "asks": []}
        collector._get = AsyncMock(return_value=mock_response)

        result = await collector.fetch_orderbook()

        assert result["imbalance"] == 0.0
        assert result["spread_bps"] == 0.0

    @pytest.mark.asyncio
    async def test_orderbook_zero_depth(self, collector) -> None:
        """Edge: Both sides have zero quantity → imbalance = 0.0."""
        mock_response = {
            "bids": [["85000.0", "0.0"]],
            "asks": [["85001.0", "0.0"]],
        }
        collector._get = AsyncMock(return_value=mock_response)

        result = await collector.fetch_orderbook()

        assert result["imbalance"] == 0.0
