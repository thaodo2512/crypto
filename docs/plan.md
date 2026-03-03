# Implementation Plan

## Progress Tracker

| ID | Name | Status | Spec Sections | Est. LOC | Dependencies |
|----|------|--------|---------------|----------|--------------|
| SS-01 | Foundation & Infrastructure | ✅ DONE | §2, §14, §17, §18 | ~250 | None |
| SS-02 | Spot Data Collector | ✅ DONE | §3.2 | ~200 | SS-01 |
| SS-03 | Futures Data Collector | 🔲 TODO | §3.3 | ~250 | SS-01 |
| SS-04 | Options Data Collector (Deribit) | 🔲 TODO | §3.4 | ~200 | SS-01 |
| SS-05 | Sentiment & Macro Collector | 🔲 TODO | §3.5, §8 | ~200 | SS-01 |
| SS-06 | Data Health Monitor | 🔲 TODO | §3.6 | ~120 | SS-01 |
| SS-07 | Calculators (Greeks, GEX, CVD) | 🔲 TODO | §3.2, §3.4, §4.3 | ~300 | SS-01, SS-04 |
| SS-08 | Confluence Zone Calculator | 🔲 TODO | §7.2 | ~150 | SS-01, SS-07 |
| SS-09 | Signal 1: Spot Flow | 🔲 TODO | §4.1 | ~150 | SS-01, SS-02, SS-07 |
| SS-10 | Signal 2: Leverage Positioning | 🔲 TODO | §4.2 | ~180 | SS-01, SS-03 |
| SS-11 | Signal 3: Options Structure | 🔲 TODO | §4.3 | ~150 | SS-01, SS-07 |
| SS-12 | Signal 4: Mean Reversion | 🔲 TODO | §4.4 | ~150 | SS-01, SS-02, SS-05 |
| SS-13 | Signal 5: Event Risk | 🔲 TODO | §4.5 | ~150 | SS-01, SS-04, SS-05, SS-07 |
| SS-14 | Regime Detection & Adaptive Weights | 🔲 TODO | §5 | ~150 | SS-01, SS-02 |
| SS-15 | Signal Engine (Final Score) | 🔲 TODO | §6 | ~200 | SS-09→SS-14 |
| SS-16 | Trade Plan Generator | 🔲 TODO | §7 | ~300 | SS-08, SS-15 |
| SS-17 | Alert System | 🔲 TODO | §10 | ~150 | SS-15 |
| SS-18 | Telegram Bot Interface | 🔲 TODO | §12 | ~300 | SS-15, SS-16, SS-17 |
| SS-19 | AI Analysis Layer | 🔲 TODO | §11 | ~250 | SS-15, SS-18 |
| SS-20 | Evaluation & Performance Tracking | 🔲 TODO | §16 | ~400 | SS-15, SS-18 |
| SS-21 | Scheduler & Main Entry Point | 🔲 TODO | §9 | ~150 | SS-02→SS-06, SS-15, SS-17, SS-18 |
| SS-22 | Backtesting Framework | 🔲 TODO | §15 | ~200 | SS-15 |
| SS-23 | Streamlit Dashboard (Phase 3) | 🔲 TODO | §13 | ~200 | SS-15, SS-20 |

**Total: 23 sub-specs | ~4,500 estimated LOC**

## Dependency Graph

```
SS-01 (Foundation)
 ├── SS-02 (Spot Collector)
 │    ├── SS-09 (Signal 1: Spot Flow) ← also needs SS-07
 │    ├── SS-12 (Signal 4: Mean Reversion) ← also needs SS-05
 │    └── SS-14 (Regime Detection)
 ├── SS-03 (Futures Collector)
 │    └── SS-10 (Signal 2: Leverage)
 ├── SS-04 (Options Collector)
 │    ├── SS-07 (Calculators) ← also needs SS-01
 │    │    ├── SS-08 (Confluence Zones)
 │    │    ├── SS-09 (Signal 1: Spot Flow)
 │    │    ├── SS-11 (Signal 3: Options)
 │    │    └── SS-13 (Signal 5: Event Risk) ← also needs SS-05
 │    └── SS-13 (Signal 5: Event Risk)
 ├── SS-05 (Sentiment & Macro)
 │    ├── SS-12 (Signal 4: Mean Reversion)
 │    └── SS-13 (Signal 5: Event Risk)
 └── SS-06 (Health Monitor)

SS-09 + SS-10 + SS-11 + SS-12 + SS-13 + SS-14
 └── SS-15 (Signal Engine)
      ├── SS-16 (Trade Plan) ← also needs SS-08
      ├── SS-17 (Alert System)
      ├── SS-22 (Backtesting)
      ├── SS-18 (Telegram Bot) ← also needs SS-16, SS-17
      │    ├── SS-19 (AI Analysis Layer)
      │    └── SS-20 (Evaluation)
      │         └── SS-23 (Dashboard, Phase 3)
      └── SS-21 (Scheduler) ← needs SS-02→SS-06, SS-15, SS-17, SS-18
```

## Milestones

### Milestone 1: Data Pipeline (SS-01 → SS-06)
**Goal:** All data sources connected, flowing to DB, health monitored
- [x] Database initialized with all tables
- [x] Spot data (Binance) collecting successfully
- [ ] Futures data (Binance + Bybit + OKX) collecting successfully
- [ ] Options data (Deribit) collecting successfully
- [ ] Sentiment + macro calendar data collecting
- [ ] Health monitor reporting status via Telegram `/health`
- [ ] Integration test: all collectors run without errors for 1 hour

### Milestone 2: Signal Engine (SS-07 → SS-15)
**Goal:** All 5 signals computing, final score generated
- [ ] GEX, gamma flip, max pain calculating from Deribit data
- [ ] CVD calculating from spot trades
- [ ] All 4 directional signals producing scores in [-1, +1]
- [ ] Event risk producing modifier in [0, 1]
- [ ] Regime detection classifying market correctly
- [ ] Adaptive weights adjusting by regime
- [ ] Final score with consensus check producing valid output
- [ ] Integration test: full pipeline from raw data → final score

### Milestone 3: User Interface (SS-16 → SS-19)
**Goal:** Telegram bot delivering trade plans and AI analysis
- [ ] Trade plan with entry, stop, TP levels generating
- [ ] Confluence zones identifying support/resistance
- [ ] Alerts firing on threshold crossings
- [ ] All Telegram commands responding correctly
- [ ] AI daily briefing generating and sending
- [ ] /ai custom question command working
- [ ] Integration test: full cycle from data → signal → plan → Telegram

### Milestone 4: Evaluation & Polish (SS-20 → SS-23)
**Goal:** System tracking its own accuracy, dashboard available
- [ ] Outcome tracker filling prices at 4h/12h/24h/48h
- [ ] Component accuracy calculating per signal
- [ ] Regime performance tracking
- [ ] Weekly/monthly reports generating
- [ ] Backtesting framework running on historical data
- [ ] Streamlit dashboard displaying all metrics
- [ ] Full system integration test: 24h dry run

## Current Focus

**Next sub-spec:** SS-03 (Futures Data Collector)
**Blockers:** None
**Notes:** SS-01, SS-02 complete — SS-03 through SS-06 unblocked

---

## Session Log

### Session — 2026-03-03
**Sub-spec:** SS-01 Foundation & Infrastructure
**Status:** Completed and verified
**What was done:**
- Created 10 empty `__init__.py` files across all `custom/` subpackages
- Implemented `custom/utils/db.py` — 5 functions (`init_db`, `get_db`, `insert_row`, `query`, `get_latest`), 17 tables from §14, SQL injection protection via allowlists
- Implemented `custom/utils/normalizers.py` — 3 functions (`z_score`, `clip_score`, `normalize_range`) with edge case handling
- Created `main.py` skeleton — config loader (`load_config`) + DB init on startup
- Created `freqtrade/user_data/strategies/composite_strategy.py` — IStrategy skeleton with 3 placeholder methods
- Created `tests/conftest.py` — 3 fixtures (`db_path`, `db`, `config`)
- Created `tests/test_foundation.py` — 17 tests covering all 15 acceptance criteria + 2 edge cases
- Ran `/verify SS-01` — all 15 AC met, 17/17 tests pass, code quality PASS
- Updated `docs/plan.md` — SS-01 marked ✅, Milestone 1 DB checkbox checked
**Decisions made:**
- DB functions take `db_path` as first arg (not global state) for testability
- Table/column allowlists (`_VALID_TABLES`, `_VALID_ORDER_COLS`) prevent SQL injection without ORM overhead
- `conftest.py` uses `tmp_path` fixture for isolated DB per test (not `:memory:`) to match real file-based usage
**Issues/Notes:**
- SQLite auto-creates `sqlite_sequence` table for AUTOINCREMENT — tests filter it out when comparing table sets
- Unused `pathlib.Path` import was cleaned up during verify
**Next session should:**
- Run `/new-subspec SS-02` to create Spot Data Collector sub-spec
- SS-02 through SS-06 are all unblocked (depend only on SS-01)
- Could implement SS-02 through SS-06 in any order; SS-02 (Spot) recommended first as most modules depend on it
- Consider creating sub-specs for SS-02→SS-06 in batch, then implementing sequentially

### Session — 2026-03-03 (2)
**Sub-spec:** SS-02 Spot Data Collector
**Status:** Completed and verified
**What was done:**
- Created `docs/sub-specs/SS-02.md` — sub-spec with 13 acceptance criteria
- Implemented `custom/collectors/spot.py` — `SpotCollector` class with 5 async methods (`_get`, `fetch_price`, `fetch_orderbook`, `fetch_trades`, `fetch_technicals`), `CollectorError` exception, `_safe_float` helper
- Created `tests/test_spot_collector.py` — 16 tests covering all 13 AC + 3 edge cases
- Ran `/verify SS-02` — all 13 AC met, 33/33 tests pass (including SS-01 regression), code quality PASS
- Updated `docs/plan.md` — SS-02 marked ✅, Milestone 1 spot checkbox checked
- Updated `requirements.txt` — replaced `pandas-ta` with `ta`
**Decisions made:**
- Replaced `pandas-ta` with `ta` library — `pandas-ta` requires Python 3.12+, project runs on 3.10. The `ta` library provides identical indicators (RSI, EMA, BB, ADX) with compatible API
- `SpotCollector` stores `db_path` internally (passed via constructor) rather than per-method — cleaner API since all methods write to the same DB
- `_get()` is a private async method that handles all HTTP, error wrapping, and timeout — all public methods delegate to it, making it easy to mock in tests
- Tests mock `collector._get` with `AsyncMock` rather than patching aiohttp — simpler, faster, tests the business logic not the HTTP layer
- VWAP computed as cumulative (price×volume) / cumulative(volume) since daily VWAP from `ta` lib expects intraday data
**Issues/Notes:**
- `pytest-asyncio` needed upgrading — old version (1.3.0) silently skipped async tests. Upgraded to 1.3.0 (pip resolved to latest compatible). Tests now run with `asyncio: mode=strict`
- `pandas-ta` incompatibility with Python 3.10 discovered at test time — switched to `ta` library seamlessly
**Next session should:**
- Run `/new-subspec SS-03` to create Futures Data Collector sub-spec
- SS-03 (Futures), SS-04 (Options), SS-05 (Sentiment), SS-06 (Health) are all unblocked
- SS-03 recommended next — it unlocks SS-10 (Signal 2: Leverage Positioning)
- Pattern established: `CollectorError` + async `_get()` + config-driven thresholds — reuse for SS-03/SS-04/SS-05
