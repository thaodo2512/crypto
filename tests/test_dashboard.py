"""Tests for SS-23: Streamlit Dashboard.

See docs/sub-specs/SS-23.md §Acceptance Criteria
"""

import pytest

from custom.utils.db import get_db, init_db, insert_row
from dashboard.app import (
    build_basis_chart,
    build_candlestick,
    build_component_accuracy_chart,
    build_funding_chart,
    build_gex_chart,
    build_ls_ratio_chart,
    build_oi_chart,
    build_oi_heatmap,
    build_regime_accuracy_chart,
    build_score_gauge,
    build_signal_bars,
    build_signal_history,
    build_win_rate_chart,
    load_confluence_zones,
    load_config,
    load_futures_data,
    load_gex_data,
    load_latest_signal,
    load_options_oi,
    load_performance,
    load_signals,
    load_spot_prices,
)


@pytest.fixture
def db(tmp_path) -> str:
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


def _seed_signal(db: str, ts: str, score: float = 0.45, bias: str = "LONG",
                 correct: int | None = None) -> None:
    conn = get_db(db)
    try:
        conn.execute(
            """INSERT INTO signals (timestamp, final_score, bias, strength, confidence,
               regime, event_risk, consensus, spot_flow, leverage_pos, options_struct,
               mean_reversion, weights_json, btc_price_at_signal, correct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, score, bias, "MODERATE", "MEDIUM", "STRONG_TREND", 0.2, "MIXED",
             0.6, 0.4, -0.1, 0.3, "{}", 100000, correct),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_price(db: str, ts: str, close: float = 100000) -> None:
    insert_row(db, "spot_price", {
        "timestamp": ts, "open": close - 500, "high": close + 500,
        "low": close - 800, "close": close, "volume": 5000,
        "quote_volume": 5e8, "num_trades": 10000,
    })


def _seed_gex(db: str, date: str = "2026-03-01") -> None:
    for strike in [90000, 95000, 100000, 105000, 110000]:
        insert_row(db, "gex_data", {
            "date": date, "strike": strike,
            "call_gex": 100 if strike > 100000 else -50,
            "put_gex": -80 if strike < 100000 else 30,
            "net_gex": 20 if strike > 100000 else -130,
            "gamma_flip_price": 100000 if strike == 100000 else None,
        })


def _seed_options_oi(db: str, date: str = "2026-03-01") -> None:
    for strike in [90000, 95000, 100000, 105000]:
        insert_row(db, "options_oi", {
            "date": date, "expiry": "2026-03-28", "strike": strike,
            "call_oi": 500 + strike / 1000, "put_oi": 300 + strike / 1000,
            "call_iv": 0.5, "put_iv": 0.55,
        })


def _seed_futures(db: str, ts: str) -> None:
    insert_row(db, "futures_snapshot", {
        "timestamp": ts,
        "funding_binance": 0.01, "funding_bybit": 0.02, "funding_okx": 0.015,
        "funding_weighted_avg": 0.015,
        "oi_total_usd": 15_000_000_000, "basis_pct": 0.5,
        "top_trader_ls_ratio": 1.2, "global_ls_ratio": 0.95,
    })


def _seed_level(db: str, date: str = "2026-03-01") -> None:
    insert_row(db, "level_outcomes", {
        "date": date, "level_price": 99000, "level_type": "support",
        "strength": 4, "components": "EMA,VWAP,Round,Options",
        "price_reached_zone": 1, "zone_held": 1,
    })
    insert_row(db, "level_outcomes", {
        "date": date, "level_price": 105000, "level_type": "resistance",
        "strength": 3, "components": "BB_upper,MaxPain,Round",
        "price_reached_zone": 0, "zone_held": None,
    })


class TestDataLoaders:
    """AC 9: Data helper functions return correct structures from DB."""

    def test_load_signals_empty(self, db) -> None:
        result = load_signals(db, days=30)
        assert result == []

    def test_load_signals_with_data(self, db) -> None:
        _seed_signal(db, "2026-03-01T08:00:00Z")
        _seed_signal(db, "2026-03-01T12:00:00Z", score=0.6)
        result = load_signals(db, days=30)
        assert len(result) == 2
        assert result[0]["final_score"] == 0.45
        assert result[1]["final_score"] == 0.6

    def test_load_latest_signal_empty(self, db) -> None:
        result = load_latest_signal(db)
        assert result is None

    def test_load_latest_signal(self, db) -> None:
        _seed_signal(db, "2026-03-01T08:00:00Z", score=0.3)
        _seed_signal(db, "2026-03-01T12:00:00Z", score=0.7)
        result = load_latest_signal(db)
        assert result is not None
        assert result["final_score"] == 0.7

    def test_load_gex_data_empty(self, db) -> None:
        assert load_gex_data(db) == []

    def test_load_gex_data(self, db) -> None:
        _seed_gex(db)
        result = load_gex_data(db)
        assert len(result) == 5
        assert result[0]["strike"] == 90000

    def test_load_options_oi_empty(self, db) -> None:
        assert load_options_oi(db) == []

    def test_load_options_oi(self, db) -> None:
        _seed_options_oi(db)
        result = load_options_oi(db)
        assert len(result) == 4
        assert "call_oi" in result[0]

    def test_load_spot_prices_empty(self, db) -> None:
        assert load_spot_prices(db) == []

    def test_load_spot_prices(self, db) -> None:
        _seed_price(db, "2026-03-01T08:00:00")
        _seed_price(db, "2026-03-01T12:00:00", close=101000)
        result = load_spot_prices(db, days=30)
        assert len(result) == 2

    def test_load_confluence_zones_empty(self, db) -> None:
        assert load_confluence_zones(db) == []

    def test_load_confluence_zones(self, db) -> None:
        _seed_level(db)
        result = load_confluence_zones(db)
        assert len(result) == 2
        assert result[0]["level_type"] == "support"
        assert result[1]["level_type"] == "resistance"

    def test_load_futures_data_empty(self, db) -> None:
        assert load_futures_data(db) == []

    def test_load_futures_data(self, db) -> None:
        _seed_futures(db, "2026-03-01T08:00:00")
        result = load_futures_data(db, days=30)
        assert len(result) == 1
        assert result[0]["funding_binance"] == 0.01

    def test_load_performance_empty(self, db) -> None:
        result = load_performance(db, days=30)
        assert result["win_rate"]["insufficient_data"] is True
        assert "spot_flow" in result["component_accuracy"]
        assert isinstance(result["regime_accuracy"], dict)


class TestChartBuilders:
    """AC 2-6, AC 10: Charts use Plotly and render correctly."""

    def test_build_score_gauge(self) -> None:
        """AC 2: Score gauge renders."""
        fig = build_score_gauge(0.45, "LONG")
        assert fig is not None
        assert len(fig.data) == 1
        assert fig.data[0].value == 0.45

    def test_build_score_gauge_short(self) -> None:
        fig = build_score_gauge(-0.6, "SHORT")
        assert fig.data[0].value == -0.6

    def test_build_signal_bars(self) -> None:
        """AC 2: Signal bars render."""
        signal = {"spot_flow": 0.6, "leverage_pos": 0.4,
                  "options_struct": -0.1, "mean_reversion": 0.3}
        fig = build_signal_bars(signal)
        assert len(fig.data) == 1
        assert len(fig.data[0].x) == 4

    def test_build_signal_history(self) -> None:
        """AC 2: Signal history chart renders."""
        signals = [
            {"timestamp": "2026-03-01T08:00:00Z", "final_score": 0.3},
            {"timestamp": "2026-03-01T12:00:00Z", "final_score": 0.5},
        ]
        fig = build_signal_history(signals)
        assert len(fig.data) >= 1
        assert len(fig.data[0].x) == 2

    def test_build_gex_chart(self) -> None:
        """AC 3: GEX chart renders."""
        gex = [{"strike": 100000, "net_gex": 50, "gamma_flip_price": 100000},
               {"strike": 105000, "net_gex": -30, "gamma_flip_price": None}]
        fig = build_gex_chart(gex)
        assert len(fig.data) == 1

    def test_build_oi_heatmap(self) -> None:
        """AC 3: OI heatmap renders."""
        oi = [{"strike": 100000, "call_oi": 500, "put_oi": 300},
              {"strike": 105000, "call_oi": 600, "put_oi": 200}]
        fig = build_oi_heatmap(oi)
        assert len(fig.data) == 2  # call + put traces

    def test_build_candlestick(self) -> None:
        """AC 4: Candlestick chart renders."""
        prices = [{"timestamp": "2026-03-01", "open": 99000, "high": 101000,
                    "low": 98500, "close": 100000}]
        zones = [{"level_price": 99000, "level_type": "support", "strength": 4}]
        fig = build_candlestick(prices, zones)
        assert len(fig.data) >= 1

    def test_build_candlestick_no_zones(self) -> None:
        """AC 4: Candlestick works without zones."""
        prices = [{"timestamp": "2026-03-01", "open": 99000, "high": 101000,
                    "low": 98500, "close": 100000}]
        fig = build_candlestick(prices, [])
        assert len(fig.data) == 1

    def test_build_funding_chart(self) -> None:
        """AC 5: Funding chart renders."""
        futures = [{"timestamp": "2026-03-01", "funding_binance": 0.01,
                     "funding_bybit": 0.02, "funding_okx": 0.015}]
        fig = build_funding_chart(futures)
        assert len(fig.data) == 3  # 3 exchanges

    def test_build_oi_chart(self) -> None:
        """AC 5: OI chart renders."""
        futures = [{"timestamp": "2026-03-01", "oi_total_usd": 15e9}]
        fig = build_oi_chart(futures)
        assert len(fig.data) == 1

    def test_build_basis_chart(self) -> None:
        """AC 5: Basis chart renders."""
        futures = [{"timestamp": "2026-03-01", "basis_pct": 0.5}]
        fig = build_basis_chart(futures)
        assert len(fig.data) == 1

    def test_build_ls_ratio_chart(self) -> None:
        """AC 5: L/S ratio chart renders."""
        futures = [{"timestamp": "2026-03-01", "top_trader_ls_ratio": 1.2,
                     "global_ls_ratio": 0.95}]
        fig = build_ls_ratio_chart(futures)
        assert len(fig.data) == 2

    def test_build_win_rate_chart_empty(self) -> None:
        """AC 6+7: Win rate chart handles no data."""
        fig = build_win_rate_chart([])
        assert fig is not None

    def test_build_win_rate_chart(self) -> None:
        """AC 6: Win rate chart renders."""
        signals = [
            {"timestamp": "2026-03-01", "correct": 1},
            {"timestamp": "2026-03-02", "correct": 0},
            {"timestamp": "2026-03-03", "correct": 1},
        ]
        fig = build_win_rate_chart(signals)
        assert len(fig.data) >= 1

    def test_build_regime_accuracy_chart_empty(self) -> None:
        """AC 6+7: Regime chart handles no data."""
        fig = build_regime_accuracy_chart({})
        assert fig is not None

    def test_build_regime_accuracy_chart(self) -> None:
        """AC 6: Regime accuracy chart renders."""
        data = {
            "STRONG_TREND": {"win_rate": 70.0, "total": 20, "insufficient_data": False},
            "TIGHT_RANGE": {"win_rate": 45.0, "total": 10, "insufficient_data": True},
        }
        fig = build_regime_accuracy_chart(data)
        assert len(fig.data) == 1
        assert len(fig.data[0].x) == 2

    def test_build_component_accuracy_chart(self) -> None:
        """AC 6: Component accuracy chart renders."""
        data = {"spot_flow": 0.3, "leverage_pos": 0.1,
                "options_struct": -0.05, "mean_reversion": 0.2}
        fig = build_component_accuracy_chart(data)
        assert len(fig.data) == 1
        assert len(fig.data[0].x) == 4


class TestEmptyDB:
    """AC 7: Empty database renders placeholder messages, no crashes."""

    def test_all_loaders_return_empty(self, db) -> None:
        assert load_signals(db) == []
        assert load_latest_signal(db) is None
        assert load_gex_data(db) == []
        assert load_options_oi(db) == []
        assert load_spot_prices(db) == []
        assert load_confluence_zones(db) == []
        assert load_futures_data(db) == []

    def test_performance_graceful_on_empty(self, db) -> None:
        perf = load_performance(db)
        assert perf["win_rate"]["total"] == 0
        assert perf["win_rate"]["insufficient_data"] is True


class TestConfig:
    """AC 8: All lookback/refresh settings from config/settings.yaml."""

    def test_load_config_has_dashboard(self) -> None:
        config = load_config()
        assert "dashboard" in config
        assert config["dashboard"]["refresh_interval_seconds"] == 300
        assert config["dashboard"]["lookback_days"] == 30

    def test_config_has_db_path(self) -> None:
        config = load_config()
        assert config["general"]["database_path"] == "data/signals.db"
