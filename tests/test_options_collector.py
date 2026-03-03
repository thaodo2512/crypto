"""Tests for SS-04: Options Data Collector (Deribit).

See docs/sub-specs/SS-04.md §Acceptance Criteria
"""

import inspect
from unittest.mock import AsyncMock

import pytest

from custom.collectors.options import (
    OptionsCollector,
    _parse_instrument_name,
)
from custom.collectors.spot import CollectorError
from custom.utils.db import query


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def options_config() -> dict:
    """Config dict for options collector."""
    return {
        "spot_data": {
            "whale_trade_threshold_usd": 100_000,
            "orderbook_depth_levels": 20,
            "volume_sma_period": 20,
        },
    }


@pytest.fixture
def collector(options_config, db_path) -> OptionsCollector:
    """OptionsCollector with test config and temp DB."""
    return OptionsCollector(options_config, db_path)


# ─── Mock data ───────────────────────────────────────────

MOCK_INSTRUMENTS_RESPONSE = {
    "result": [
        {"instrument_name": "BTC-28MAR26-85000-C", "strike": 85000, "is_active": True},
        {"instrument_name": "BTC-28MAR26-85000-P", "strike": 85000, "is_active": True},
        {"instrument_name": "BTC-28MAR26-90000-C", "strike": 90000, "is_active": True},
        {"instrument_name": "BTC-28MAR26-90000-P", "strike": 90000, "is_active": True},
        {"instrument_name": "BTC-25APR26-80000-C", "strike": 80000, "is_active": True},
        {"instrument_name": "BTC-OLD-EXPIRED-C", "strike": 70000, "is_active": False},
    ]
}

MOCK_BOOK_SUMMARY_RESPONSE = {
    "result": [
        {
            "instrument_name": "BTC-28MAR26-85000-C",
            "open_interest": 100.0,
            "mark_iv": 0.65,
            "volume": 50.0,
            "mark_price": 0.05,
        },
        {
            "instrument_name": "BTC-28MAR26-85000-P",
            "open_interest": 80.0,
            "mark_iv": 0.70,
            "volume": 30.0,
            "mark_price": 0.03,
        },
        {
            "instrument_name": "BTC-28MAR26-90000-C",
            "open_interest": 60.0,
            "mark_iv": 0.60,
            "volume": 40.0,
            "mark_price": 0.02,
        },
        {
            "instrument_name": "BTC-28MAR26-90000-P",
            "open_interest": 120.0,
            "mark_iv": 0.75,
            "volume": 70.0,
            "mark_price": 0.06,
        },
        {
            "instrument_name": "BTC-25APR26-80000-C",
            "open_interest": 40.0,
            "mark_iv": 0.55,
            "volume": 20.0,
            "mark_price": 0.08,
        },
    ]
}

MOCK_INDEX_PRICE_RESPONSE = {
    "result": {"index_price": 85000.0}
}

MOCK_DVOL_RESPONSE = {
    "result": {
        "data": [
            [1772520000000, 61.0, 63.0, 60.5, 62.5],
        ],
        "continuation": None,
    }
}

MOCK_TRADES_RESPONSE = {
    "result": {
        "trades": [
            {
                "instrument_name": "BTC-28MAR26-85000-C",
                "direction": "buy",
                "amount": 10.0,
                "price": 0.15,
                "iv": 0.65,
            },
            {
                "instrument_name": "BTC-28MAR26-90000-P",
                "direction": "sell",
                "amount": 0.5,
                "price": 0.02,
                "iv": 0.70,
            },
            {
                "instrument_name": "BTC-28MAR26-85000-P",
                "direction": "buy",
                "amount": 5.0,
                "price": 0.10,
                "iv": 0.68,
            },
        ]
    }
}


def _mock_all_endpoints(collector: OptionsCollector) -> None:
    """Mock _get to return canned responses based on endpoint."""
    async def mock_get(endpoint: str, params: dict | None = None) -> dict:
        if "get_instruments" in endpoint:
            return MOCK_INSTRUMENTS_RESPONSE
        if "get_book_summary_by_currency" in endpoint:
            return MOCK_BOOK_SUMMARY_RESPONSE
        if "get_index_price" in endpoint:
            return MOCK_INDEX_PRICE_RESPONSE
        if "get_last_trades_by_currency" in endpoint:
            return MOCK_TRADES_RESPONSE
        if "get_volatility_index_data" in endpoint:
            return MOCK_DVOL_RESPONSE
        raise CollectorError(f"Unexpected endpoint: {endpoint}")

    collector._get = AsyncMock(side_effect=mock_get)


# ─── TestFetchInstruments ────────────────────────────────


class TestFetchInstruments:
    """Tests for fetch_instruments()."""

    @pytest.mark.asyncio
    async def test_fetch_instruments_parses_fields(self, collector) -> None:
        """AC 1: Returns list of active BTC options with strike, expiry, option_type parsed."""
        _mock_all_endpoints(collector)

        result = await collector.fetch_instruments()

        assert len(result) == 5  # 6 total minus 1 inactive
        first = result[0]
        assert first["instrument_name"] == "BTC-28MAR26-85000-C"
        assert first["strike"] == 85000.0
        assert first["expiry"] == "28MAR26"
        assert first["option_type"] == "call"

    @pytest.mark.asyncio
    async def test_fetch_instruments_filters_inactive(self, collector) -> None:
        """AC 2: Filters out inactive instruments."""
        _mock_all_endpoints(collector)

        result = await collector.fetch_instruments()

        names = [r["instrument_name"] for r in result]
        assert "BTC-OLD-EXPIRED-C" not in names
        assert len(result) == 5


# ─── TestFetchOptionsChain ───────────────────────────────


class TestFetchOptionsChain:
    """Tests for fetch_options_chain()."""

    @pytest.mark.asyncio
    async def test_options_chain_stores_per_strike_expiry(
        self, collector, db_path
    ) -> None:
        """AC 3: Stores one row per strike/expiry in options_oi."""
        _mock_all_endpoints(collector)

        result = await collector.fetch_options_chain()

        # 5 instruments → 3 unique (strike, expiry) pairs:
        # (85000, 28MAR26), (90000, 28MAR26), (80000, 25APR26)
        assert len(result) == 3

        rows = query(db_path, "SELECT * FROM options_oi")
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_options_chain_aggregates_call_put(
        self, collector, db_path
    ) -> None:
        """AC 4: Aggregates call and put data at same strike/expiry into single row."""
        _mock_all_endpoints(collector)

        await collector.fetch_options_chain()

        rows = query(db_path, "SELECT * FROM options_oi WHERE strike = 85000.0")
        assert len(rows) == 1
        row = rows[0]
        assert row["call_oi"] == 100.0
        assert row["put_oi"] == 80.0
        assert row["call_iv"] == 0.65
        assert row["put_iv"] == 0.70
        assert row["call_volume"] == 50.0
        assert row["put_volume"] == 30.0


# ─── TestFetchIndexPrice ─────────────────────────────────


class TestFetchIndexPrice:
    """Tests for fetch_index_price()."""

    @pytest.mark.asyncio
    async def test_fetch_index_price(self, collector) -> None:
        """AC 5: Returns BTC index price as float."""
        _mock_all_endpoints(collector)

        result = await collector.fetch_index_price()

        assert result == 85000.0
        assert isinstance(result, float)


# ─── TestFetchDvol ────────────────────────────────────────


class TestFetchDvol:
    """Tests for fetch_dvol()."""

    @pytest.mark.asyncio
    async def test_fetch_dvol(self, collector) -> None:
        """AC 6: Returns DVol index as float."""
        _mock_all_endpoints(collector)

        result = await collector.fetch_dvol()

        assert result == 62.5
        assert isinstance(result, float)


# ─── TestFetchLargeTrades ─────────────────────────────────


class TestFetchLargeTrades:
    """Tests for fetch_large_trades()."""

    @pytest.mark.asyncio
    async def test_large_trades_filters_by_threshold(
        self, collector, db_path
    ) -> None:
        """AC 7: Filters trades above whale threshold (100,000 USD)."""
        _mock_all_endpoints(collector)

        # Trade values at index_price=85000:
        # Trade 1: 10.0 × 0.15 × 85000 = 127,500 → ABOVE threshold
        # Trade 2: 0.5 × 0.02 × 85000 = 850 → below
        # Trade 3: 5.0 × 0.10 × 85000 = 42,500 → below
        result = await collector.fetch_large_trades(index_price=85000.0)

        assert len(result) == 1
        assert result[0]["instrument"] == "BTC-28MAR26-85000-C"

        rows = query(db_path, "SELECT * FROM options_large_trades")
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_large_trades_stores_fields(self, collector, db_path) -> None:
        """AC 8: Stores instrument, direction, amount, price, iv, value_usd."""
        _mock_all_endpoints(collector)

        result = await collector.fetch_large_trades(index_price=85000.0)

        trade = result[0]
        assert trade["instrument"] == "BTC-28MAR26-85000-C"
        assert trade["direction"] == "buy"
        assert trade["amount"] == 10.0
        assert trade["price"] == 0.15
        assert trade["iv"] == 0.65
        assert trade["value_usd"] == 10.0 * 0.15 * 85000.0

        row = query(db_path, "SELECT * FROM options_large_trades")[0]
        assert row["instrument"] == "BTC-28MAR26-85000-C"
        assert row["value_usd"] == 10.0 * 0.15 * 85000.0


# ─── TestFetchSnapshot ────────────────────────────────────


class TestFetchSnapshot:
    """Tests for fetch_snapshot()."""

    @pytest.mark.asyncio
    async def test_fetch_snapshot_returns_summary(self, collector) -> None:
        """AC 9: Orchestrates full scan and returns summary dict."""
        _mock_all_endpoints(collector)

        result = await collector.fetch_snapshot()

        assert result["total_instruments"] == 5
        assert result["dvol"] == 62.5
        assert result["index_price"] == 85000.0
        assert result["large_trades_count"] == 1
        assert "total_call_oi" in result
        assert "total_put_oi" in result
        assert "put_call_ratio_oi" in result
        assert "put_call_ratio_volume" in result

    @pytest.mark.asyncio
    async def test_fetch_snapshot_put_call_ratios(self, collector) -> None:
        """AC 10: Computes put/call ratio by OI and by volume."""
        _mock_all_endpoints(collector)

        result = await collector.fetch_snapshot()

        # Call OI: 100 + 60 + 40 = 200
        # Put OI: 80 + 120 = 200
        # P/C ratio OI = 200 / 200 = 1.0
        assert result["total_call_oi"] == 200.0
        assert result["total_put_oi"] == 200.0
        assert result["put_call_ratio_oi"] == 1.0

        # Call volume: 50 + 40 + 20 = 110
        # Put volume: 30 + 70 = 100
        # P/C ratio volume = 100 / 110 ≈ 0.909
        assert abs(result["put_call_ratio_volume"] - 100 / 110) < 0.001


# ─── TestErrorHandling ────────────────────────────────────


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_individual_endpoint_failure(self, collector) -> None:
        """AC 11: Individual endpoint failures return None (graceful degradation)."""
        collector._get = AsyncMock(side_effect=CollectorError("API down"))

        # index_price returns None
        result = await collector.fetch_index_price()
        assert result is None

        # dvol returns None
        result = await collector.fetch_dvol()
        assert result is None

        # large trades returns empty list
        result = await collector.fetch_large_trades(index_price=85000.0)
        assert result == []

        # options chain returns empty list
        result = await collector.fetch_options_chain()
        assert result == []

    @pytest.mark.asyncio
    async def test_instruments_failure_raises_error(self, collector) -> None:
        """AC 12: Total failure of instruments endpoint raises CollectorError."""
        collector._get = AsyncMock(side_effect=CollectorError("Deribit down"))

        with pytest.raises(CollectorError):
            await collector.fetch_snapshot()


# ─── TestConfig ───────────────────────────────────────────


class TestConfig:
    """Tests for config usage."""

    def test_thresholds_from_config(self, db_path) -> None:
        """AC 13: All thresholds read from config, not hardcoded."""
        config = {
            "spot_data": {
                "whale_trade_threshold_usd": 50_000,
                "orderbook_depth_levels": 20,
                "volume_sma_period": 20,
            },
        }
        c = OptionsCollector(config, db_path)
        assert c._whale_threshold == 50_000
        assert c._db_path == db_path


# ─── TestAsync ────────────────────────────────────────────


class TestAsync:
    """Tests for async compliance."""

    def test_methods_are_async(self) -> None:
        """AC 14: All API calls use aiohttp (async)."""
        assert inspect.iscoroutinefunction(OptionsCollector.fetch_instruments)
        assert inspect.iscoroutinefunction(OptionsCollector.fetch_options_chain)
        assert inspect.iscoroutinefunction(OptionsCollector.fetch_index_price)
        assert inspect.iscoroutinefunction(OptionsCollector.fetch_dvol)
        assert inspect.iscoroutinefunction(OptionsCollector.fetch_large_trades)
        assert inspect.iscoroutinefunction(OptionsCollector.fetch_snapshot)
        assert inspect.iscoroutinefunction(OptionsCollector._get)


# ─── TestEdgeCases ────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_empty_instruments_list(self, collector) -> None:
        """Edge: No active options returns empty list."""
        collector._get = AsyncMock(return_value={"result": []})

        result = await collector.fetch_instruments()
        assert result == []

    @pytest.mark.asyncio
    async def test_zero_call_oi_ratio(self, collector) -> None:
        """Edge: Zero total call OI → put_call_ratio_oi = None."""
        async def mock_get(endpoint: str, params: dict | None = None) -> dict:
            if "get_instruments" in endpoint:
                return MOCK_INSTRUMENTS_RESPONSE
            if "get_book_summary_by_currency" in endpoint:
                # Only puts, no calls
                return {"result": [
                    {
                        "instrument_name": "BTC-28MAR26-85000-P",
                        "open_interest": 100.0,
                        "mark_iv": 0.70,
                        "volume": 30.0,
                    },
                ]}
            if "get_index_price" in endpoint:
                return MOCK_INDEX_PRICE_RESPONSE
            if "ticker" in endpoint:
                return MOCK_DVOL_RESPONSE
            if "get_last_trades_by_currency" in endpoint:
                return {"result": {"trades": []}}
            raise CollectorError(f"Unexpected: {endpoint}")

        collector._get = AsyncMock(side_effect=mock_get)
        result = await collector.fetch_snapshot()

        assert result["total_call_oi"] == 0
        assert result["put_call_ratio_oi"] is None

    @pytest.mark.asyncio
    async def test_no_large_trades_found(self, collector, db_path) -> None:
        """Edge: All trades below threshold → empty list, no rows stored."""
        collector._get = AsyncMock(return_value={
            "result": {
                "trades": [
                    {
                        "instrument_name": "BTC-28MAR26-85000-C",
                        "direction": "buy",
                        "amount": 0.01,
                        "price": 0.01,
                        "iv": 0.60,
                    },
                ]
            }
        })

        result = await collector.fetch_large_trades(index_price=85000.0)

        # 0.01 × 0.01 × 85000 = 8.5 → below 100,000 threshold
        assert result == []
        rows = query(db_path, "SELECT * FROM options_large_trades")
        assert len(rows) == 0
