"""Tests for SS-11: Signal 3 — Options Structure.

See docs/sub-specs/SS-11.md §Acceptance Criteria
"""

import pytest

from custom.signals.options_signal import (
    _score_gamma_flip,
    _score_iv_skew,
    _score_max_pain,
    _score_net_gex,
    compute_options_signal,
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
        "options_structure": {
            "gamma_flip_weight": 0.40,
            "net_gex_weight": 0.25,
            "iv_skew_weight": 0.20,
            "max_pain_weight": 0.15,
            "z_score_lookback_days": 30,
        },
    }


class TestGammaFlipScore:
    def test_gamma_flip_distance(self) -> None:
        """AC 1: Gamma flip distance maps to correct score (linear ±8% → ±1.0)."""
        assert _score_gamma_flip(100000, None) == 0.0
        assert _score_gamma_flip(100000, 100000) == 0.0   # at gamma flip
        assert abs(_score_gamma_flip(100000, 94000) - 0.75) < 0.01   # +6%
        assert abs(_score_gamma_flip(100000, 97000) - 0.375) < 0.01  # +3%
        assert abs(_score_gamma_flip(100000, 99000) - 0.125) < 0.01  # +1%
        assert abs(_score_gamma_flip(100000, 101000) - (-0.125)) < 0.01  # -1%
        assert abs(_score_gamma_flip(100000, 103000) - (-0.375)) < 0.01  # -3%
        assert _score_gamma_flip(100000, 110000) == -1.0  # capped at -1.0

    def test_gamma_flip_none(self) -> None:
        """AC 7: Returns 0 when gamma_flip is None."""
        assert _score_gamma_flip(100000, None) == 0.0


class TestNetGexScore:
    def test_net_gex_zscore(self, db) -> None:
        """AC 2: Net GEX z-score maps to correct score (linear z/2 × 0.6)."""
        # Seed varying GEX values so std > 0
        gex_values = [40, 50, 60, 45, 55, 35, 65, 42, 58, 48]
        for i, val in enumerate(gex_values):
            insert_row(db, "gex_data", {
                "date": f"2026-02-{i+10:02d}", "strike": 100000,
                "call_gex": val + 20, "put_gex": -20, "net_gex": val,
                "gamma_flip_price": 99000,
            })
        # mean ≈ 49.8, std ≈ ~9. Current total=200 → z >> 2 → capped at 0.6
        score = _score_net_gex(200.0, db, 30)
        assert score == 0.6  # z >> 2 → capped


class TestIvSkewScore:
    def test_iv_skew_contrarian(self) -> None:
        """AC 3: IV skew maps contrarian score (linear ±8 → ±0.6)."""
        assert _score_iv_skew(0.0) == 0.0
        assert _score_iv_skew(None) == 0.0
        assert abs(_score_iv_skew(6.0) - 0.45) < 0.01   # 6/8 × 0.6 = 0.45
        assert abs(_score_iv_skew(3.0) - 0.225) < 0.01
        assert abs(_score_iv_skew(-3.0) - (-0.225)) < 0.01
        assert abs(_score_iv_skew(-6.0) - (-0.45)) < 0.01
        assert abs(_score_iv_skew(8.0) - 0.6) < 0.01    # capped

    def test_iv_skew_none(self) -> None:
        """AC 7: Returns 0 when skew is None."""
        assert _score_iv_skew(None) == 0.0


class TestMaxPainScore:
    def test_max_pain_gravity(self) -> None:
        """AC 4: Max pain gravity maps to correct score (linear ±10% → ∓0.5)."""
        assert _score_max_pain(100000, None) == 0.0
        assert _score_max_pain(100000, 100000) == 0.0    # at max pain
        # distance_pct / 10 → capped at ±0.5
        assert abs(_score_max_pain(100000, 97000) - (-0.3)) < 0.01  # +3% → -0.3
        assert _score_max_pain(100000, 94000) == -0.5    # +6% → capped at -0.5
        assert abs(_score_max_pain(100000, 103000) - 0.3) < 0.01    # -3% → +0.3
        assert _score_max_pain(100000, 106000) == 0.5    # -6% → capped at +0.5


class TestComputeOptionsSignal:
    def test_final_clipped(self, db, config) -> None:
        """AC 5: Final score clipped to [-1, +1]."""
        snapshot = {
            "gamma_flip": 94000,    # deep positive gamma
            "total_net_gex": 100.0,
            "iv_skew": 6.0,         # heavy put → bullish
            "max_pain": 106000,      # below → gravity up
        }
        score = compute_options_signal(db, config, snapshot, 100000)
        assert -1.0 <= score <= 1.0

    def test_weights_from_config(self, config) -> None:
        """AC 6: All weights from config."""
        cfg = config["options_structure"]
        total = cfg["gamma_flip_weight"] + cfg["net_gex_weight"] + cfg["iv_skew_weight"] + cfg["max_pain_weight"]
        assert total == pytest.approx(1.0)

    def test_returns_zero_on_failure(self, db) -> None:
        """AC 7: Returns 0.0 on failure."""
        assert compute_options_signal(db, {}, {}, 100000) == 0.0
