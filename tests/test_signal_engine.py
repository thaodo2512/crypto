"""Tests for SS-15: Signal Engine (Final Score).

See docs/sub-specs/SS-15.md §Acceptance Criteria
"""

import pytest

from custom.signals.engine import (
    apply_event_risk_penalty,
    assemble_signal,
    check_consensus,
    classify_signal,
    compute_confidence,
    compute_final_signal,
    compute_raw_score,
    store_signal,
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
        "signal_classification": {
            "no_signal_threshold": 0.15,
            "weak_threshold": 0.35,
            "moderate_threshold": 0.60,
        },
        "consensus": {
            "bullish_threshold": 0.15,
            "bearish_threshold": -0.15,
            "strong_consensus_multiplier": 1.3,
            "moderate_consensus_multiplier": 1.1,
            "conflict_multiplier": 0.5,
            "mixed_multiplier": 0.8,
        },
        "event_risk_penalty": {
            "high_risk_threshold": 0.7,
            "medium_risk_threshold": 0.4,
            "high_penalty": 0.4,
            "medium_penalty": 0.7,
            "low_penalty": 1.0,
        },
        "confidence": {
            "high_threshold": 0.75,
            "medium_threshold": 0.50,
        },
    }


class TestComputeRawScore:
    def test_weighted_sum(self) -> None:
        """AC 1: Raw score = weighted sum of 4 directional signals."""
        signals = {
            "spot_flow": 0.6,
            "leverage_pos": 0.4,
            "options_struct": -0.2,
            "mean_reversion": 0.3,
        }
        weights = {
            "spot_flow": 0.30,
            "leverage_pos": 0.25,
            "options_struct": 0.25,
            "mean_reversion": 0.20,
        }
        # 0.6×0.30 + 0.4×0.25 + (-0.2)×0.25 + 0.3×0.20
        # = 0.18 + 0.10 + (-0.05) + 0.06 = 0.29
        raw = compute_raw_score(signals, weights)
        assert raw == pytest.approx(0.29)

    def test_clipped_to_range(self) -> None:
        """AC 10: Raw score clipped to [-1, +1]."""
        signals = {
            "spot_flow": 1.0,
            "leverage_pos": 1.0,
            "options_struct": 1.0,
            "mean_reversion": 1.0,
        }
        weights = {
            "spot_flow": 0.5,
            "leverage_pos": 0.5,
            "options_struct": 0.5,
            "mean_reversion": 0.5,
        }
        # Sum = 2.0, should clip to 1.0
        raw = compute_raw_score(signals, weights)
        assert raw == 1.0


class TestCheckConsensus:
    def test_strong_consensus_bullish(self, config) -> None:
        """AC 2: STRONG_CONSENSUS when 3+ signals same direction."""
        signals = {
            "spot_flow": 0.5,
            "leverage_pos": 0.4,
            "options_struct": 0.3,
            "mean_reversion": -0.1,  # neutral
        }
        ctype, mult = check_consensus(signals, config)
        assert ctype == "STRONG_CONSENSUS"
        assert mult == 1.3

    def test_strong_consensus_bearish(self, config) -> None:
        """AC 2: STRONG_CONSENSUS bearish with 3+ signals."""
        signals = {
            "spot_flow": -0.5,
            "leverage_pos": -0.4,
            "options_struct": -0.3,
            "mean_reversion": 0.1,
        }
        ctype, mult = check_consensus(signals, config)
        assert ctype == "STRONG_CONSENSUS"
        assert mult == 1.3

    def test_conflict(self, config) -> None:
        """AC 3: CONFLICT when 2+ bullish AND 2+ bearish."""
        signals = {
            "spot_flow": 0.5,
            "leverage_pos": 0.4,
            "options_struct": -0.5,
            "mean_reversion": -0.4,
        }
        ctype, mult = check_consensus(signals, config)
        assert ctype == "CONFLICT"
        assert mult == 0.5

    def test_moderate_consensus(self, config) -> None:
        """AC 2: MODERATE_CONSENSUS when 2 same, 0 opposite."""
        signals = {
            "spot_flow": 0.5,
            "leverage_pos": 0.4,
            "options_struct": 0.05,   # neutral
            "mean_reversion": -0.10,  # neutral
        }
        ctype, mult = check_consensus(signals, config)
        assert ctype == "MODERATE_CONSENSUS"
        assert mult == 1.1

    def test_mixed(self, config) -> None:
        """Consensus: MIXED for other combinations."""
        signals = {
            "spot_flow": 0.5,
            "leverage_pos": -0.3,
            "options_struct": 0.05,
            "mean_reversion": 0.0,
        }
        ctype, mult = check_consensus(signals, config)
        assert ctype == "MIXED"
        assert mult == 0.8


class TestEventRiskPenalty:
    def test_high_risk_penalty(self, config) -> None:
        """AC 4: Event risk >0.7 applies ×0.4 penalty."""
        result = apply_event_risk_penalty(0.5, 0.8, config)
        assert result == pytest.approx(0.5 * 0.4)

    def test_medium_risk_penalty(self, config) -> None:
        """AC 5: Event risk 0.4–0.7 applies ×0.7 penalty."""
        result = apply_event_risk_penalty(0.5, 0.5, config)
        assert result == pytest.approx(0.5 * 0.7)

    def test_low_risk_no_penalty(self, config) -> None:
        """Event risk <0.4 applies no penalty (×1.0)."""
        result = apply_event_risk_penalty(0.5, 0.2, config)
        assert result == pytest.approx(0.5)

    def test_penalty_clips_to_range(self, config) -> None:
        """AC 10: Penalized score clipped to [-1, +1]."""
        result = apply_event_risk_penalty(-0.9, 0.1, config)
        assert -1.0 <= result <= 1.0


class TestClassifySignal:
    def test_neutral(self, config) -> None:
        """AC 6: NEUTRAL when |score| < 0.15."""
        bias, strength = classify_signal(0.10, config)
        assert bias == "NEUTRAL"
        assert strength == "NEUTRAL"

    def test_weak_long(self, config) -> None:
        """Classification: WEAK LONG for |score| 0.15–0.35."""
        bias, strength = classify_signal(0.25, config)
        assert bias == "LONG"
        assert strength == "WEAK"

    def test_moderate_short(self, config) -> None:
        """Classification: MODERATE SHORT."""
        bias, strength = classify_signal(-0.45, config)
        assert bias == "SHORT"
        assert strength == "MODERATE"

    def test_strong(self, config) -> None:
        """AC 7: STRONG when |score| > 0.60."""
        bias, strength = classify_signal(0.75, config)
        assert bias == "LONG"
        assert strength == "STRONG"


class TestComputeConfidence:
    def test_high_confidence(self, config) -> None:
        """AC 8: HIGH when ≥3/4 factors true (ratio ≥0.75)."""
        # All 4 factors true: consensus>1.0, event_risk<0.4, regime!=TRANS, |score|>0.35
        conf = compute_confidence(1.3, 0.1, "STRONG_TREND", 0.5, config)
        assert conf == "HIGH"

    def test_medium_confidence(self, config) -> None:
        """Confidence: MEDIUM when 2/4 factors true (ratio=0.50)."""
        # 2 factors: consensus>1.0 (True), event_risk<0.4 (True), regime TRANSITIONAL (False), |score|<0.35 (False)
        conf = compute_confidence(1.1, 0.2, "TRANSITIONAL", 0.20, config)
        assert conf == "MEDIUM"

    def test_low_confidence(self, config) -> None:
        """AC 9: LOW when <2/4 factors true (ratio<0.50)."""
        # 1 factor: consensus<1.0 (F), event_risk>0.4 (F), TRANSITIONAL (F), |score|>0.35 (T)
        conf = compute_confidence(0.5, 0.8, "TRANSITIONAL", 0.5, config)
        assert conf == "LOW"


class TestAssembleSignal:
    def test_output_schema(self, config) -> None:
        """AC 11: Output matches §6.2 schema."""
        signals = {
            "spot_flow": 0.6,
            "leverage_pos": 0.4,
            "options_struct": 0.3,
            "mean_reversion": 0.1,
        }
        weights = {
            "spot_flow": 0.30,
            "leverage_pos": 0.25,
            "options_struct": 0.25,
            "mean_reversion": 0.20,
        }
        result = assemble_signal(signals, weights, 0.1, "STRONG_TREND", 100000, config)

        # Check all required keys
        assert "timestamp" in result
        assert "btc_price" in result
        assert "final_score" in result
        assert "bias" in result
        assert "strength" in result
        assert "confidence" in result
        assert "regime" in result
        assert "event_risk" in result
        assert "consensus" in result
        assert "breakdown" in result
        assert "weights_used" in result

        # Check types
        assert isinstance(result["final_score"], float)
        assert result["bias"] in ("LONG", "SHORT", "NEUTRAL")
        assert result["strength"] in ("NEUTRAL", "WEAK", "MODERATE", "STRONG")
        assert result["confidence"] in ("HIGH", "MEDIUM", "LOW")
        assert -1.0 <= result["final_score"] <= 1.0

    def test_full_pipeline_values(self, config) -> None:
        """AC 1+2+10: Full pipeline produces correct values."""
        signals = {
            "spot_flow": 0.6,
            "leverage_pos": 0.5,
            "options_struct": 0.4,
            "mean_reversion": 0.1,  # neutral
        }
        weights = {
            "spot_flow": 0.35,
            "leverage_pos": 0.30,
            "options_struct": 0.20,
            "mean_reversion": 0.15,
        }
        result = assemble_signal(signals, weights, 0.1, "STRONG_TREND", 100000, config)

        # 3 bullish signals → STRONG_CONSENSUS (×1.3)
        assert result["consensus"] == "STRONG_CONSENSUS"
        # Low event risk → no penalty
        assert result["event_risk"] == 0.1
        # Score should be positive
        assert result["final_score"] > 0
        assert result["bias"] == "LONG"


class TestStoreSignal:
    def test_stores_to_db(self, db, config) -> None:
        """Signal stored in signals table."""
        signals = {
            "spot_flow": 0.5,
            "leverage_pos": 0.3,
            "options_struct": 0.2,
            "mean_reversion": -0.1,
        }
        weights = {"spot_flow": 0.25, "leverage_pos": 0.25, "options_struct": 0.25, "mean_reversion": 0.25}
        result = assemble_signal(signals, weights, 0.2, "MODERATE_TREND", 100000, config)

        store_signal(db, result)
        rows = query(db, "SELECT * FROM signals")
        assert len(rows) == 1
        assert rows[0]["bias"] == "LONG"
        assert rows[0]["regime"] == "MODERATE_TREND"


class TestComputeFinalSignal:
    def test_returns_neutral_on_failure(self, db) -> None:
        """AC 13: Returns neutral on failure."""
        # Empty DB and minimal config → should fail gracefully
        result = compute_final_signal(db, {})
        assert result["final_score"] == 0.0
        assert result["bias"] == "NEUTRAL"
        assert result["strength"] == "NEUTRAL"
        assert result["confidence"] == "LOW"

    def test_thresholds_from_config(self, config) -> None:
        """AC 12: All thresholds from config."""
        assert config["signal_classification"]["no_signal_threshold"] == 0.15
        assert config["consensus"]["strong_consensus_multiplier"] == 1.3
        assert config["event_risk_penalty"]["high_penalty"] == 0.4
        assert config["confidence"]["high_threshold"] == 0.75
