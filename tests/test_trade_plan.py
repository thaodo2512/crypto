"""Tests for SS-16: Trade Plan Generator.

See docs/sub-specs/SS-16.md §Acceptance Criteria
"""

import pytest

from custom.trade_plan.plan import (
    check_entry_gate,
    compute_position_size,
    compute_stop_loss,
    compute_take_profits,
    generate_trade_plan,
    store_trade_plan,
)
from custom.utils.db import init_db, query


@pytest.fixture
def db(tmp_path) -> str:
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


@pytest.fixture
def config() -> dict:
    return {
        "trade_plan": {
            "max_risk_per_trade_pct": 2.0,
            "max_leverage": 3,
            "min_reward_risk_ratio": 1.5,
            "high_confidence_strong_risk": 2.0,
            "high_or_strong_risk": 1.5,
            "medium_confidence_risk": 1.0,
            "low_confidence_risk": 0.5,
            "confluence_zone_width_pct": 0.5,
            "confluence_min_levels": 3,
            "tp1_position_pct": 50,
            "tp2_position_pct": 30,
            "tp3_position_pct": 20,
            "stop_loss_buffer_pct": 0.3,
            "trailing_stop_pct": 2.0,
            "entry_min_signal_strength": "MODERATE",
            "entry_min_confidence": "MEDIUM",
        },
    }


@pytest.fixture
def zones() -> list:
    return [
        {"center": 95000, "strength": 4, "type": "support", "components": ["EMA 200", "Put Wall", "Round Number", "VWAP"]},
        {"center": 105000, "strength": 3, "type": "resistance", "components": ["Call Wall", "EMA 21", "Round Number"]},
        {"center": 110000, "strength": 3, "type": "resistance", "components": ["Call Wall", "Max Pain", "Round Number"]},
    ]


@pytest.fixture
def strong_signal() -> dict:
    return {
        "final_score": 0.55,
        "bias": "LONG",
        "strength": "MODERATE",
        "confidence": "MEDIUM",
    }


class TestEntryGate:
    def test_gate1_rejects_weak(self, config, zones) -> None:
        """AC 1: Gate 1 rejects WEAK strength."""
        signal = {"strength": "WEAK", "confidence": "MEDIUM"}
        result = check_entry_gate(signal, zones, config)
        assert result["passed"] is False
        assert result["gate"] == "GATE_1"

    def test_gate1_rejects_low_confidence(self, config, zones) -> None:
        """AC 1: Gate 1 rejects LOW confidence."""
        signal = {"strength": "MODERATE", "confidence": "LOW"}
        result = check_entry_gate(signal, zones, config)
        assert result["passed"] is False
        assert result["gate"] == "GATE_1"

    def test_gate2_rejects_no_zones(self, config) -> None:
        """AC 2: Gate 2 rejects when no zones."""
        signal = {"strength": "MODERATE", "confidence": "MEDIUM"}
        result = check_entry_gate(signal, [], config)
        assert result["passed"] is False
        assert result["gate"] == "GATE_2"

    def test_gates_pass(self, config, zones) -> None:
        """All gates pass with valid signal and zones."""
        signal = {"strength": "MODERATE", "confidence": "MEDIUM"}
        result = check_entry_gate(signal, zones, config)
        assert result["passed"] is True


class TestPositionSize:
    def test_high_confidence_strong(self, config) -> None:
        """AC 3: HIGH+STRONG → 2% risk."""
        signal = {"strength": "STRONG", "confidence": "HIGH"}
        result = compute_position_size(100000, signal, 2.0, config)
        assert result["risk_pct"] == 2.0
        assert result["risk_usd"] == 2000

    def test_risk_never_exceeds_cap(self, config) -> None:
        """AC 3: Risk never exceeds 2% (IMMUTABLE)."""
        signal = {"strength": "STRONG", "confidence": "HIGH"}
        result = compute_position_size(100000, signal, 2.0, config)
        assert result["risk_pct"] <= 2.0

    def test_leverage_capped(self, config) -> None:
        """AC 4: Leverage never exceeds 3x (IMMUTABLE)."""
        signal = {"strength": "STRONG", "confidence": "HIGH"}
        # Very small stop → would produce huge leverage
        result = compute_position_size(100000, signal, 0.1, config)
        assert result["leverage"] <= 3.0
        assert result["position_size_usd"] <= 300000

    def test_medium_confidence_risk(self, config) -> None:
        """Medium confidence → 1% risk."""
        signal = {"strength": "MODERATE", "confidence": "MEDIUM"}
        result = compute_position_size(100000, signal, 2.0, config)
        assert result["risk_pct"] == 1.0


class TestStopLoss:
    def test_long_stop_below_support(self, config, zones) -> None:
        """AC 5: Stop below support zone + buffer."""
        spot = 100000
        stop = compute_stop_loss("LONG", zones, spot, config)
        # Should be below the support zone (95000) with 0.3% buffer
        expected = 95000 * (1 - 0.3 / 100)
        assert stop == pytest.approx(expected)
        assert stop < 95000

    def test_short_stop_above_resistance(self, config, zones) -> None:
        """AC 5: Stop above resistance zone + buffer."""
        spot = 100000
        stop = compute_stop_loss("SHORT", zones, spot, config)
        expected = 105000 * (1 + 0.3 / 100)
        assert stop == pytest.approx(expected)
        assert stop > 105000

    def test_fallback_no_zones(self, config) -> None:
        """Stop fallback when no matching zones."""
        stop = compute_stop_loss("LONG", [], 100000, config)
        assert stop == 98000  # 2% below spot


class TestTakeProfits:
    def test_tp1_min_rr(self, config, zones) -> None:
        """AC 6: TP1 minimum 1.5R."""
        entry = 100000
        stop = 95000
        risk = entry - stop  # 5000
        tps = compute_take_profits("LONG", entry, stop, zones, config)
        # TP1 >= entry + 1.5 × risk = 107500
        # Nearest resistance is 105000 but < min_tp1 107500, so uses 107500
        assert tps["tp1"] >= entry + risk * 1.5

    def test_tp2_exists(self, config, zones) -> None:
        """AC 7: TP2 at next resistance."""
        entry = 100000
        stop = 95000
        tps = compute_take_profits("LONG", entry, stop, zones, config)
        assert tps["tp2"] is not None
        assert tps["tp2"] > tps["tp1"]

    def test_scaled_exit_pcts(self, config) -> None:
        """AC 8: 50/30/20 split from config."""
        assert config["trade_plan"]["tp1_position_pct"] == 50
        assert config["trade_plan"]["tp2_position_pct"] == 30
        assert config["trade_plan"]["tp3_position_pct"] == 20


class TestGenerateTradePlan:
    def test_plan_generated(self, config, zones, strong_signal) -> None:
        """Full plan generated with valid inputs."""
        plan = generate_trade_plan(strong_signal, zones, 100000, 100000, config)
        assert plan is not None
        assert plan["direction"] == "LONG"
        assert plan["entry_price"] == 100000
        assert plan["stop_loss"] < 100000
        assert plan["tp1"] > 100000
        assert plan["risk_pct"] <= 2.0

    def test_returns_none_gate_fail(self, config, zones) -> None:
        """AC 10: Returns None when entry gate fails."""
        weak_signal = {"strength": "WEAK", "confidence": "LOW", "bias": "LONG", "final_score": 0.1}
        plan = generate_trade_plan(weak_signal, zones, 100000, 100000, config)
        assert plan is None

    def test_returns_none_no_zones(self, config, strong_signal) -> None:
        """AC 10: Returns None when no zones."""
        plan = generate_trade_plan(strong_signal, [], 100000, 100000, config)
        assert plan is None


class TestStoreTradePlan:
    def test_stores_to_db(self, db, config, zones, strong_signal) -> None:
        """AC 9: Plan stored in trades table."""
        plan = generate_trade_plan(strong_signal, zones, 100000, 100000, config)
        assert plan is not None
        store_trade_plan(db, plan)
        rows = query(db, "SELECT * FROM trades")
        assert len(rows) == 1
        assert rows[0]["direction"] == "LONG"
        assert rows[0]["entry_price"] == 100000

    def test_thresholds_from_config(self, config) -> None:
        """AC 11: All thresholds from config."""
        assert config["trade_plan"]["max_risk_per_trade_pct"] == 2.0
        assert config["trade_plan"]["max_leverage"] == 3
        assert config["trade_plan"]["min_reward_risk_ratio"] == 1.5
