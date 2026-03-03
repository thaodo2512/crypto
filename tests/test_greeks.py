"""Tests for SS-07: Greeks, GEX, Gamma Flip, Max Pain, IV Skew.

See docs/sub-specs/SS-07.md §Acceptance Criteria
"""

from unittest.mock import patch

import pytest

from custom.calculators.greeks import (
    compute_gex,
    compute_greeks,
    compute_iv_skew,
    compute_max_pain,
    compute_options_snapshot,
    find_gamma_flip,
    store_gex,
)
from custom.utils.db import init_db, query


# ─── Fixtures ────────────────────────────────────────────


@pytest.fixture
def db(tmp_path) -> str:
    """Initialized test database."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


def _make_chain(strikes: list[float], spot: float = 100000) -> list[dict]:
    """Helper: create synthetic options chain for testing."""
    chain = []
    for s in strikes:
        chain.append({
            "strike": s,
            "expiry": "2026-06-28",
            "call_oi": 100.0,
            "put_oi": 80.0,
            "call_iv": 0.65,
            "put_iv": 0.70,
            "call_volume": 50.0,
            "put_volume": 40.0,
        })
    return chain


# ─── TestComputeGreeks ───────────────────────────────────


class TestComputeGreeks:
    """Tests for compute_greeks()."""

    def test_compute_greeks_call(self) -> None:
        """AC 1: Returns delta and gamma for call option."""
        result = compute_greeks(
            spot=100000, strike=100000, T=0.25, r=0.0, iv=0.65, option_type="call"
        )
        assert "delta" in result
        assert "gamma" in result
        assert 0.5 < result["delta"] < 0.7  # ATM call delta ~ 0.5-0.6
        assert result["gamma"] > 0

    def test_compute_greeks_put(self) -> None:
        """AC 2: Returns delta and gamma for put option."""
        result = compute_greeks(
            spot=100000, strike=100000, T=0.25, r=0.0, iv=0.65, option_type="put"
        )
        assert result["delta"] < 0  # put delta is negative
        assert result["gamma"] > 0  # gamma is same for call/put

    def test_compute_greeks_invalid_T(self) -> None:
        """AC 3: Returns zeros when T <= 0."""
        result = compute_greeks(
            spot=100000, strike=100000, T=0.0, r=0.0, iv=0.65, option_type="call"
        )
        assert result["delta"] == 0.0
        assert result["gamma"] == 0.0

        result_neg = compute_greeks(
            spot=100000, strike=100000, T=-0.1, r=0.0, iv=0.65, option_type="call"
        )
        assert result_neg["delta"] == 0.0
        assert result_neg["gamma"] == 0.0

    def test_compute_greeks_invalid_iv(self) -> None:
        """AC 3: Returns zeros when iv <= 0."""
        result = compute_greeks(
            spot=100000, strike=100000, T=0.25, r=0.0, iv=0.0, option_type="call"
        )
        assert result["delta"] == 0.0
        assert result["gamma"] == 0.0


# ─── TestComputeGex ──────────────────────────────────────


class TestComputeGex:
    """Tests for compute_gex()."""

    def test_compute_gex_formula(self) -> None:
        """AC 4: Calculates per-strike GEX with correct formula."""
        chain = _make_chain([90000, 100000, 110000])
        spot = 100000.0

        result = compute_gex(chain, spot)

        assert len(result) == 3
        assert result[0]["strike"] == 90000
        assert result[1]["strike"] == 100000
        assert result[2]["strike"] == 110000
        # call_gex should be positive, put_gex should be negative
        for item in result:
            assert item["call_gex"] > 0
            assert item["put_gex"] < 0
            assert item["net_gex"] == pytest.approx(
                item["call_gex"] + item["put_gex"], rel=1e-6
            )

    def test_gex_skips_missing_iv(self) -> None:
        """Edge: Rows with None IV are skipped gracefully."""
        chain = [
            {"strike": 100000, "expiry": "2026-06-28",
             "call_oi": 100, "put_oi": 80, "call_iv": None, "put_iv": None,
             "call_volume": 0, "put_volume": 0},
        ]
        result = compute_gex(chain, 100000.0)
        assert len(result) == 1
        assert result[0]["call_gex"] == 0.0
        assert result[0]["put_gex"] == 0.0
        assert result[0]["net_gex"] == 0.0


# ─── TestFindGammaFlip ───────────────────────────────────


class TestFindGammaFlip:
    """Tests for find_gamma_flip()."""

    def test_find_gamma_flip_sign_change(self) -> None:
        """AC 5: Finds strike where cumulative net_gex changes sign."""
        gex = [
            {"strike": 90000, "call_gex": 10, "put_gex": -20, "net_gex": -10},
            {"strike": 95000, "call_gex": 10, "put_gex": -15, "net_gex": -5},
            {"strike": 100000, "call_gex": 20, "put_gex": -5, "net_gex": 15},
            {"strike": 105000, "call_gex": 15, "put_gex": -3, "net_gex": 12},
        ]
        # cumulative: -10, -15, 0, +12 → flip at 100000 (cumulative goes from neg to non-neg)
        flip = find_gamma_flip(gex)
        assert flip == 100000

    def test_find_gamma_flip_no_change(self) -> None:
        """AC 6: Returns None when all GEX same sign."""
        gex = [
            {"strike": 90000, "call_gex": 20, "put_gex": -5, "net_gex": 15},
            {"strike": 100000, "call_gex": 25, "put_gex": -3, "net_gex": 22},
        ]
        # cumulative: +15, +37 → always positive
        flip = find_gamma_flip(gex)
        assert flip is None


# ─── TestComputeMaxPain ──────────────────────────────────


class TestComputeMaxPain:
    """Tests for compute_max_pain()."""

    def test_compute_max_pain_optimal(self) -> None:
        """AC 7: Returns strike that minimizes total pain."""
        # Simple 3-strike chain where middle strike should be max pain
        chain = [
            {"strike": 90000, "call_oi": 0, "put_oi": 100},
            {"strike": 100000, "call_oi": 50, "put_oi": 50},
            {"strike": 110000, "call_oi": 100, "put_oi": 0},
        ]
        # pain(90K) = 0×0 + 50×0 + 100×0 + 100×0 + 50×10K + 0×20K = 500K
        # pain(100K)= 0×10K + 50×0 + 100×0 + 100×10K + 50×0 + 0×0 = 1M
        # pain(110K)= 0×20K + 50×10K + 100×0 + 100×20K + 50×10K + 0×0 = 3M
        # Actually let me recalculate:
        # pain(K) = Σ call_OI × max(0, K - strike_i) + Σ put_OI × max(0, strike_i - K)
        # pain(90K) = 0×max(0,90K-90K) + 50×max(0,90K-100K) + 100×max(0,90K-110K) + 100×max(0,90K-90K) + 50×max(0,100K-90K) + 0×max(0,110K-90K)
        #           = 0 + 0 + 0 + 0 + 50×10K + 0 = 500K
        # pain(100K) = 0×max(0,100K-90K) + 50×max(0,100K-100K) + 100×max(0,100K-110K) + 100×max(0,90K-100K) + 50×max(0,100K-100K) + 0×max(0,110K-100K)
        #            = 0×10K + 0 + 0 + 0 + 0 + 0 = 0
        # Hmm that's 0. Let me fix: at K=100K: call part = 0×10K + 50×0 + 100×0 = 0; put part = 100×0 + 50×0 + 0×10K = 0
        # Total = 0. So K=100K has lowest pain.
        result = compute_max_pain(chain)
        assert result == 100000

    def test_compute_max_pain_empty(self) -> None:
        """AC 8: Returns None for empty chain."""
        assert compute_max_pain([]) is None


# ─── TestComputeIvSkew ───────────────────────────────────


class TestComputeIvSkew:
    """Tests for compute_iv_skew()."""

    def test_compute_iv_skew(self) -> None:
        """AC 9: Returns ATM put_IV minus ATM call_IV."""
        chain = [
            {"strike": 95000, "call_iv": 0.60, "put_iv": 0.70},
            {"strike": 100000, "call_iv": 0.55, "put_iv": 0.65},  # ATM
            {"strike": 105000, "call_iv": 0.50, "put_iv": 0.75},
        ]
        skew = compute_iv_skew(chain, spot=100000)
        assert skew == pytest.approx(0.10)  # 0.65 - 0.55

    def test_iv_skew_no_atm_data(self) -> None:
        """Edge: Returns None when ATM IV data is missing."""
        chain = [
            {"strike": 100000, "call_iv": 0.55, "put_iv": None},
        ]
        assert compute_iv_skew(chain, spot=100000) is None


# ─── TestStoreGex ─────────────────────────────────────────


class TestStoreGex:
    """Tests for store_gex()."""

    def test_store_gex_writes_db(self, db) -> None:
        """AC 10: Writes rows to gex_data table with correct fields."""
        gex_results = [
            {"strike": 90000, "call_gex": 10.5, "put_gex": -5.3, "net_gex": 5.2},
            {"strike": 100000, "call_gex": 20.1, "put_gex": -8.7, "net_gex": 11.4},
        ]
        count = store_gex(db, gex_results, gamma_flip=95000.0)

        assert count == 2
        rows = query(db, "SELECT * FROM gex_data")
        assert len(rows) == 2
        assert rows[0]["strike"] == 90000
        assert rows[0]["gamma_flip_price"] == 95000.0
        assert rows[1]["net_gex"] == pytest.approx(11.4)


# ─── TestComputeOptionsSnapshot ──────────────────────────


class TestComputeOptionsSnapshot:
    """Tests for compute_options_snapshot()."""

    def test_compute_options_snapshot(self, db) -> None:
        """AC 11: Returns summary dict with all computed values."""
        chain = _make_chain([90000, 100000, 110000])

        result = compute_options_snapshot(db, chain, spot=100000)

        assert "gamma_flip" in result
        assert "max_pain" in result
        assert "iv_skew" in result
        assert "total_net_gex" in result
        assert "gex_by_strike" in result
        assert isinstance(result["gex_by_strike"], list)
        assert len(result["gex_by_strike"]) == 3
        assert result["max_pain"] is not None
        # iv_skew should be 0.70 - 0.65 = 0.05 (ATM at 100000)
        assert result["iv_skew"] == pytest.approx(0.05)

        # Verify GEX was stored in DB
        rows = query(db, "SELECT * FROM gex_data")
        assert len(rows) == 3
