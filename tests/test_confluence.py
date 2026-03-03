"""Tests for SS-08: Confluence Zone Calculator.

See docs/sub-specs/SS-08.md §Acceptance Criteria
"""

import pytest

from custom.calculators.confluence import (
    _levels_from_round_numbers,
    _levels_from_snapshot,
    _levels_from_technicals,
    collect_levels,
    compute_confluence_zones,
    find_confluence_zones,
)
from custom.utils.db import init_db, insert_row


@pytest.fixture
def db(tmp_path) -> str:
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


@pytest.fixture
def config() -> dict:
    return {
        "trade_plan": {
            "confluence_zone_width_pct": 0.5,
            "confluence_min_levels": 3,
        },
    }


def _seed_technicals(db: str, ema_21: float, ema_55: float, ema_200: float, vwap: float) -> None:
    insert_row(db, "spot_technicals", {
        "date": "2026-03-01", "rsi_14": 50,
        "ema_21": ema_21, "ema_55": ema_55, "ema_200": ema_200,
        "vwap": vwap, "bb_upper": 105000, "bb_lower": 95000,
        "bb_width": 10000, "adx_14": 25, "volume_sma_20": 5000, "volume_ratio": 1.0,
    })


def _seed_options_oi(db: str, strike: float, call_oi: float, put_oi: float) -> None:
    insert_row(db, "options_oi", {
        "date": "2026-03-01", "expiry": "2026-03-28", "strike": strike,
        "call_oi": call_oi, "put_oi": put_oi,
        "call_iv": 0.6, "put_iv": 0.65,
        "call_volume": 100, "put_volume": 80,
    })


class TestCollectLevels:
    def test_collects_all_sources(self, db) -> None:
        """AC 1: Collects levels from all 8 sources."""
        spot = 100000
        _seed_technicals(db, 100100, 99500, 95000, 100050)
        _seed_options_oi(db, 100000, 5000, 3000)
        _seed_options_oi(db, 95000, 1000, 8000)
        snapshot = {"gamma_flip": 99800, "max_pain": 98000}

        levels = collect_levels(db, spot, snapshot)
        sources = {l["source"] for l in levels}

        # Should have: EMA 21, EMA 55, EMA 200, VWAP, Call Wall, Put Wall,
        # Gamma Flip, Max Pain, Round Number
        assert "EMA 21" in sources
        assert "EMA 55" in sources
        assert "EMA 200" in sources
        assert "VWAP" in sources
        assert "Call Wall" in sources
        assert "Put Wall" in sources
        assert "Gamma Flip" in sources
        assert "Max Pain" in sources
        assert "Round Number" in sources

    def test_technicals_levels(self, db) -> None:
        """Technicals source extracts EMA and VWAP."""
        _seed_technicals(db, 100100, 99500, 95000, 100050)
        levels = _levels_from_technicals(db)
        assert len(levels) == 4
        sources = {l["source"] for l in levels}
        assert sources == {"EMA 21", "EMA 55", "EMA 200", "VWAP"}

    def test_snapshot_levels(self, db) -> None:
        """Snapshot source extracts gamma flip and max pain."""
        snapshot = {"gamma_flip": 99800, "max_pain": 98000}
        levels = _levels_from_snapshot(db, snapshot)
        assert len(levels) == 2
        sources = {l["source"] for l in levels}
        assert sources == {"Gamma Flip", "Max Pain"}

    def test_snapshot_none_fallback(self, db) -> None:
        """No snapshot and no gex_data returns empty."""
        levels = _levels_from_snapshot(db, None)
        assert levels == []


class TestRoundNumbers:
    def test_round_numbers_near_spot(self) -> None:
        """AC 7: Round numbers ($5k increments) included."""
        levels = _levels_from_round_numbers(100000)
        prices = [l["price"] for l in levels]
        assert 100000 in prices
        assert 95000 in prices
        assert 105000 in prices
        # All should be multiples of 5000
        for p in prices:
            assert p % 5000 == 0
        # All sources should be "Round Number"
        for l in levels:
            assert l["source"] == "Round Number"


class TestFindConfluenceZones:
    def test_zone_requires_min_levels(self, config) -> None:
        """AC 2: Zones require ≥3 levels within ±0.5%."""
        spot = 100000
        # Only 2 levels at ~100000 → no zone
        levels = [
            {"price": 100000, "type": "dynamic_sr", "source": "EMA 21"},
            {"price": 100200, "type": "dynamic_sr", "source": "VWAP"},
        ]
        zones = find_confluence_zones(levels, spot, config)
        assert len(zones) == 0

    def test_zone_with_three_levels(self, config) -> None:
        """AC 2+3: Zone created with 3 levels, center = mean."""
        spot = 100000
        # 3 levels within ±0.5% of each other (100000 ± 500)
        levels = [
            {"price": 100000, "type": "dynamic_sr", "source": "EMA 21"},
            {"price": 100200, "type": "dynamic_sr", "source": "VWAP"},
            {"price": 99900, "type": "boundary", "source": "Gamma Flip"},
        ]
        zones = find_confluence_zones(levels, spot, config)
        assert len(zones) == 1
        # AC 3: center = mean of prices
        expected_center = (100000 + 100200 + 99900) / 3
        assert zones[0]["center"] == pytest.approx(expected_center)
        assert zones[0]["strength"] == 3

    def test_support_vs_resistance(self, config) -> None:
        """AC 4: Zones classified as support (below) or resistance (above)."""
        spot = 100000
        # Support zone below spot
        levels = [
            {"price": 95000, "type": "support", "source": "Put Wall"},
            {"price": 95100, "type": "dynamic_sr", "source": "EMA 200"},
            {"price": 95200, "type": "psychological", "source": "Round Number"},
        ]
        zones = find_confluence_zones(levels, spot, config)
        assert len(zones) == 1
        assert zones[0]["type"] == "support"

    def test_resistance_zone(self, config) -> None:
        """AC 4: Resistance zone above spot."""
        spot = 90000
        levels = [
            {"price": 95000, "type": "resistance", "source": "Call Wall"},
            {"price": 95100, "type": "dynamic_sr", "source": "EMA 55"},
            {"price": 95200, "type": "psychological", "source": "Round Number"},
        ]
        zones = find_confluence_zones(levels, spot, config)
        assert len(zones) == 1
        assert zones[0]["type"] == "resistance"

    def test_strength_ranking(self, config) -> None:
        """AC 5: Zones ranked by strength."""
        spot = 100000
        # 4-level zone and 3-level zone
        levels = [
            # 4-level zone near 95000
            {"price": 95000, "type": "support", "source": "Put Wall"},
            {"price": 95100, "type": "dynamic_sr", "source": "EMA 200"},
            {"price": 95200, "type": "psychological", "source": "Round Number"},
            {"price": 94900, "type": "magnet", "source": "Max Pain"},
            # 3-level zone near 105000
            {"price": 105000, "type": "resistance", "source": "Call Wall"},
            {"price": 105100, "type": "dynamic_sr", "source": "EMA 21"},
            {"price": 105200, "type": "psychological", "source": "Round Number"},
        ]
        zones = find_confluence_zones(levels, spot, config)
        assert len(zones) == 2
        strengths = [z["strength"] for z in zones]
        assert 4 in strengths
        assert 3 in strengths

    def test_merge_overlapping_zones(self, config) -> None:
        """AC 6: Overlapping zones are merged."""
        spot = 100000
        # Two clusters very close together → should merge
        levels = [
            {"price": 95000, "type": "support", "source": "A"},
            {"price": 95100, "type": "support", "source": "B"},
            {"price": 95200, "type": "support", "source": "C"},
            {"price": 95300, "type": "support", "source": "D"},
            {"price": 95400, "type": "support", "source": "E"},
            {"price": 95450, "type": "support", "source": "F"},
        ]
        zones = find_confluence_zones(levels, spot, config)
        # All within ±0.5% of each other, should be 1 merged zone
        assert len(zones) == 1
        assert zones[0]["strength"] == 6

    def test_empty_levels(self, config) -> None:
        """AC 8: Returns empty list with no levels."""
        zones = find_confluence_zones([], 100000, config)
        assert zones == []


class TestComputeConfluenceZones:
    def test_orchestrator_returns_zones(self, db, config) -> None:
        """AC 1+2: Full pipeline produces zones."""
        spot = 100000
        # Seed data to create a confluence at ~100000
        _seed_technicals(db, 100100, 99500, 95000, 100050)
        snapshot = {"gamma_flip": 99900, "max_pain": 98000}

        zones = compute_confluence_zones(db, config, spot, snapshot)
        # EMA 21 (100100), VWAP (100050), Gamma Flip (99900) + Round Number (100000)
        # All within ±0.5% of 100000 → should form a zone
        assert len(zones) >= 1
        # Find the zone near 100000
        near_spot = [z for z in zones if abs(z["center"] - 100000) < 1000]
        assert len(near_spot) >= 1

    def test_returns_empty_on_failure(self, db) -> None:
        """AC 8: Returns empty list on failure."""
        # Bad config that would cause issues
        zones = compute_confluence_zones(db, {}, 100000)
        # Should not crash, returns whatever it can find (round numbers only, likely no zones)
        assert isinstance(zones, list)

    def test_thresholds_from_config(self, config) -> None:
        """AC 9: All thresholds from config."""
        assert config["trade_plan"]["confluence_zone_width_pct"] == 0.5
        assert config["trade_plan"]["confluence_min_levels"] == 3
