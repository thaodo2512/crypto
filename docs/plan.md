# Implementation Plan

## Progress Tracker

| ID | Name | Status | Spec Sections | Est. LOC | Dependencies |
|----|------|--------|---------------|----------|--------------|
| SS-01 | Foundation & Infrastructure | ✅ DONE | §2, §14, §17, §18 | ~250 | None |
| SS-02 | Spot Data Collector | ✅ DONE | §3.2 | ~200 | SS-01 |
| SS-03 | Futures Data Collector | ✅ DONE | §3.3 | ~250 | SS-01 |
| SS-04 | Options Data Collector (Deribit) | ✅ DONE | §3.4 | ~200 | SS-01 |
| SS-05 | Sentiment & Macro Collector | ✅ DONE | §3.5, §8 | ~200 | SS-01 |
| SS-06 | Data Health Monitor | ✅ DONE | §3.6 | ~120 | SS-01 |
| SS-07 | Calculators (Greeks, GEX, CVD) | ✅ DONE | §3.2, §3.4, §4.3 | ~300 | SS-01, SS-04 |
| SS-08 | Confluence Zone Calculator | ✅ DONE | §7.2 | ~150 | SS-01, SS-07 |
| SS-09 | Signal 1: Spot Flow | ✅ DONE | §4.1 | ~150 | SS-01, SS-02, SS-07 |
| SS-10 | Signal 2: Leverage Positioning | ✅ DONE | §4.2 | ~180 | SS-01, SS-03 |
| SS-11 | Signal 3: Options Structure | ✅ DONE | §4.3 | ~150 | SS-01, SS-07 |
| SS-12 | Signal 4: Mean Reversion | ✅ DONE | §4.4 | ~150 | SS-01, SS-02, SS-05 |
| SS-13 | Signal 5: Event Risk | ✅ DONE | §4.5 | ~150 | SS-01, SS-04, SS-05, SS-07 |
| SS-14 | Regime Detection & Adaptive Weights | ✅ DONE | §5 | ~150 | SS-01, SS-02 |
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
- [x] Futures data (Binance + Bybit + OKX) collecting successfully
- [x] Options data (Deribit) collecting successfully
- [x] Sentiment + macro calendar data collecting
- [x] Health monitor reporting status via Telegram `/health`
- [ ] Integration test: all collectors run without errors for 1 hour

### Milestone 2: Signal Engine (SS-07 → SS-15)
**Goal:** All 5 signals computing, final score generated
- [x] GEX, gamma flip, max pain calculating from Deribit data
- [x] CVD calculating from spot trades
- [x] All 4 directional signals producing scores in [-1, +1]
- [x] Event risk producing modifier in [0, 1]
- [x] Regime detection classifying market correctly
- [x] Adaptive weights adjusting by regime
- [ ] Final score with consensus check producing valid output
- [ ] Integration test: full pipeline from raw data → final score

### Milestone 3: User Interface (SS-16 → SS-19)
**Goal:** Telegram bot delivering trade plans and AI analysis
- [ ] Trade plan with entry, stop, TP levels generating
- [x] Confluence zones identifying support/resistance
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

**Next sub-spec:** SS-15 (Signal Engine — Final Score) or SS-08 (Confluence Zones)
**Blockers:** None
**Notes:** SS-09→SS-14 all complete (all 5 signals + regime detection). SS-15 is now unblocked. SS-08 is also unblocked (needed by SS-16 Trade Plan).

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

### Session — 2026-03-03 (3)
**Sub-spec:** SS-03 Futures Data Collector
**Status:** Completed
**What was done:**
- Created `docs/sub-specs/SS-03.md` — sub-spec with 17 acceptance criteria
- Implemented `custom/collectors/futures.py` — `FuturesCollector` class with 11 methods: `_get`, 6 private per-exchange fetch methods (`_fetch_{binance,bybit,okx}_{funding,oi}`), 3 helper methods (`_safe_fetch_ratio`, `_safe_fetch_taker`, `_safe_fetch_premium`), 3 public methods (`fetch_snapshot`, `fetch_oi_price_regime`, `fetch_liquidations`). Plus 3 module-level helpers (`_compute_weighted_funding`, `_compute_oi_change`, `_classify_regime`)
- Created `tests/test_futures_collector.py` — 20 tests covering all 17 AC + 3 edge cases
- Updated `docs/plan.md` — SS-03 marked ✅, Milestone 1 futures checkbox checked
**Decisions made:**
- Reused `CollectorError` from `custom/collectors/spot.py` rather than defining a new exception — single exception type for all collector failures
- `_get()` takes full URL (not base + endpoint) since this collector hits 4 different base URLs (Binance, Bybit, OKX, Coinglass)
- Graceful degradation: individual `_fetch_*` methods catch `CollectorError` and return `None` — `fetch_snapshot()` only raises if ALL 6 exchange calls return `None`
- `_compute_weighted_funding()` falls back to simple average if OI data is zero/unavailable
- OI-price regime uses `>=0` for "up" direction (zero change = neutral = same direction)
- `fetch_oi_price_regime()` uses `get_latest("futures_snapshot", 2)` to compare current vs previous snapshot
- Tests mock individual `_fetch_*` methods via `AsyncMock` for fine-grained control of per-exchange responses
**Issues/Notes:**
- All 53 tests pass (SS-01: 17 + SS-02: 16 + SS-03: 20)
- No new dependency issues — `futures.py` only uses `aiohttp`, `asyncio`, and stdlib
**Next session should:**
- Run `/new-subspec SS-04` for Options Data Collector (Deribit) — unlocks SS-07 (Calculators)
- SS-04, SS-05, SS-06 are all unblocked; SS-04 recommended next as it's on the critical path to SS-07 → SS-08 → signals
- Collector pattern is well-established: async `_get()`, per-source graceful degradation, config-driven, `CollectorError` on total failure

### Session — 2026-03-03 (4)
**Sub-spec:** SS-04 Options Data Collector (Deribit)
**Status:** Completed and verified
**What was done:**
- Created `docs/sub-specs/SS-04.md` — sub-spec with 14 acceptance criteria
- Implemented `custom/collectors/options.py` — `OptionsCollector` class with 6 public methods (`fetch_instruments`, `fetch_options_chain`, `fetch_index_price`, `fetch_dvol`, `fetch_large_trades`, `fetch_snapshot`), 1 private `_get`, 2 module helpers (`_parse_instrument_name`, `_safe_float`)
- Created `tests/test_options_collector.py` — 17 tests covering all 14 AC + 3 edge cases
- Ran `/verify SS-04` — all 14 AC met, 70/70 tests pass (including SS-01→SS-03 regression), code quality PASS
- Updated `docs/plan.md` — SS-04 marked ✅, Milestone 1 options checkbox checked
**Decisions made:**
- `_get()` takes endpoint path (not full URL) since all calls go to single Deribit base URL — simpler than SS-03's full-URL approach which hit 4 different base URLs
- `fetch_options_chain()` uses `get_book_summary_by_currency` for efficient batch fetch (1 API call) rather than per-instrument ticker calls (hundreds of calls)
- Aggregation by `(strike, expiry)` tuple key merges call+put into single `options_oi` row — matches DB schema from SS-01
- `_parse_instrument_name()` parses `BTC-28MAR26-85000-C` format into structured dict — module-level helper for reuse by both `fetch_instruments` and `fetch_options_chain`
- `fetch_snapshot()` treats instruments endpoint as critical (raises on failure) but all other endpoints degrade gracefully (return None/empty)
- Scope boundary: raw data collection only — Greeks, GEX, gamma flip, max pain, IV skew deferred to SS-07 (Calculators)
**Issues/Notes:**
- Unused `query` import discovered during `/verify` — cleaned up
- Test had incorrect assertion accessing `total_call_volume` key not in summary dict — fixed by removing the bad assertion
- All 70 tests pass (SS-01: 17 + SS-02: 16 + SS-03: 20 + SS-04: 17)
**Next session should:**
- Commit SS-04 changes (4 files: `custom/collectors/options.py`, `tests/test_options_collector.py`, `docs/sub-specs/SS-04.md`, `docs/plan.md`)
- Run `/new-subspec SS-05` for Sentiment & Macro Collector — unlocks SS-12 (Signal 4: Mean Reversion) and SS-13 (Signal 5: Event Risk)
- SS-05 and SS-06 are both unblocked; SS-05 recommended next as it provides data for 2 signals
- With SS-04 done, SS-07 (Calculators) is now unblocked (depends on SS-01 + SS-04)
- Milestone 1 progress: 4/6 sub-specs done (SS-01→SS-04), SS-05 and SS-06 remaining

### Session — 2026-03-03 (5)
**Sub-spec:** SS-04 Options Data Collector + SS-05 Sentiment & Macro Collector
**Status:** Both completed and verified
**What was done:**
- Created `docs/sub-specs/SS-04.md` — 14 acceptance criteria for Deribit options collector
- Implemented `custom/collectors/options.py` — `OptionsCollector` class with 6 public methods (`fetch_instruments`, `fetch_options_chain`, `fetch_index_price`, `fetch_dvol`, `fetch_large_trades`, `fetch_snapshot`), 2 module helpers (`_parse_instrument_name`, `_safe_float`)
- Created `tests/test_options_collector.py` — 17 tests, all passing
- Ran `/verify SS-04` — 14/14 AC met, cleaned up unused `query` import
- Committed SS-04 as `d01a944`
- Created `docs/sub-specs/SS-05.md` — 14 acceptance criteria for sentiment & macro collector
- Implemented `custom/collectors/sentiment.py` — `SentimentCollector` class with 7 public methods (`fetch_fear_greed`, `load_macro_calendar`, `get_upcoming_events`, `get_next_event`, `fetch_cpi_actual`, `classify_surprise`, `update_event_actual`)
- Created `tests/test_sentiment_collector.py` — 17 tests, all passing
- Ran `/verify SS-05` — 14/14 AC met, no issues
- Updated `docs/plan.md` — SS-04 and SS-05 marked ✅, Milestone 1 checkboxes updated
**Decisions made:**
- SS-04 `_get()` takes endpoint path (not full URL) since all calls go to single Deribit base URL
- SS-04 uses `get_book_summary_by_currency` for batch fetch (1 API call vs hundreds)
- SS-04 `_parse_instrument_name()` parses `BTC-28MAR26-85000-C` format — reused by both `fetch_instruments` and `fetch_options_chain`
- SS-05 `_get()` takes full URL (like SS-03) since it hits two different APIs (Alternative.me + FRED)
- SS-05 uses `get_db()` with explicit commit for UPDATE operations — `query()` from SS-01 is SELECT-only
- SS-05 `get_upcoming_events()` uses Python-side datetime filtering instead of SQL — more reliable across datetime format variations
- SS-05 `classify_surprise()` routes to inflation or NFP thresholds based on event type sets (`_INFLATION_EVENTS`, `_JOBS_EVENTS`)
- SS-05 `FRED_API_KEY` read from `os.environ.get()` at call time, not constructor — testable without env var
**Issues/Notes:**
- SS-04: Unused `query` import found during verify — cleaned up
- SS-04: Test had bad assertion accessing `total_call_volume` key not in summary dict — fixed
- SS-05: `query()` function doesn't commit (SELECT-only) — UPDATE statements need `get_db()` + explicit `conn.commit()`
- SS-05: SQLite datetime comparison unreliable with `HH:MM` vs `HH:MM:SS` — switched to Python-side filtering
- All 87 tests pass (SS-01: 17 + SS-02: 16 + SS-03: 20 + SS-04: 17 + SS-05: 17)
**Next session should:**
- Commit SS-05 changes (3 files: `custom/collectors/sentiment.py`, `tests/test_sentiment_collector.py`, `docs/sub-specs/SS-05.md`, `docs/plan.md`)
- Run `/new-subspec SS-06` for Data Health Monitor — last sub-spec in Milestone 1
- SS-06 depends only on SS-01 (done); completing it finishes Milestone 1 (Data Pipeline)
- After Milestone 1: SS-07 (Calculators), SS-10 (Signal 2), SS-14 (Regime Detection) are all unblocked
- Consider doing SS-07 next after SS-06 — it's on the critical path (unlocks SS-08, SS-09, SS-11, SS-13)

### Session — 2026-03-03 (6)
**Sub-spec:** SS-06 Data Health Monitor
**Status:** Completed and verified
**What was done:**
- Created `docs/sub-specs/SS-06.md` — sub-spec with 12 acceptance criteria
- Implemented `custom/utils/health.py` — `HealthMonitor` class with 6 methods (`_ensure_source`, `record_success`, `record_failure`, `get_source_status`, `check_latency_warning`, `get_health_report`)
- Created `tests/test_health_monitor.py` — 15 tests covering all 12 AC + 3 edge cases
- All 102 tests pass on first run (no fixes needed)
- Ran `/verify SS-06` — all 12 AC met, code quality PASS
- Updated `docs/plan.md` — SS-06 marked ✅, Milestone 1 health checkbox checked, current focus updated to SS-07
- **Milestone 1 (Data Pipeline) is now complete** — all 6 sub-specs done (SS-01→SS-06)
**Decisions made:**
- Purely in-memory tracking (no DB writes) — simplest approach, health state is ephemeral per process lifecycle
- `_ensure_source()` private method lazily creates source state dicts — no need to pre-register sources
- `get_source_status()` returns ISO timestamp strings (not datetime objects) for JSON serialization compatibility with Telegram responses
- `is_stale = True` when `last_success is None` (never succeeded) — conservative default
**Issues/Notes:**
- Simplest module so far — no external dependencies, no async, no DB, all tests passed on first run
- All 102 tests pass (SS-01: 17 + SS-02: 16 + SS-03: 20 + SS-04: 17 + SS-05: 17 + SS-06: 15)
**Next session should:**
- Commit SS-06 changes (4 files: `custom/utils/health.py`, `tests/test_health_monitor.py`, `docs/sub-specs/SS-06.md`, `docs/plan.md`)
- Start Milestone 2 (Signal Engine): run `/new-subspec SS-07` for Calculators (Greeks, GEX, CVD)
- SS-07 is on the critical path — unlocks SS-08 (Confluence Zones), SS-09 (Signal 1: Spot Flow), SS-11 (Signal 3: Options), SS-13 (Signal 5: Event Risk)
- Also unblocked: SS-10 (Signal 2: Leverage, depends on SS-01+SS-03) and SS-14 (Regime Detection, depends on SS-01+SS-02)
- Could parallelize: SS-07 + SS-10 + SS-14 are all independently unblocked

### Session — 2026-03-03 (7)
**Sub-spec:** SS-07 Calculators (Greeks, GEX, CVD)
**Status:** Completed and verified
**What was done:**
- Created `docs/sub-specs/SS-07.md` — sub-spec with 15 acceptance criteria
- Implemented `custom/calculators/greeks.py` — 7 functions + 1 helper (`compute_greeks`, `compute_gex`, `find_gamma_flip`, `compute_max_pain`, `compute_iv_skew`, `store_gex`, `compute_options_snapshot`, `_expiry_to_years`)
- Implemented `custom/calculators/cvd.py` — 3 functions (`compute_cvd_zscore`, `compute_cvd_divergence`, `compute_cvd_4h_confirmation`)
- Created `tests/test_greeks.py` — 14 tests covering 11 AC + 3 edge cases
- Created `tests/test_cvd_calc.py` — 6 tests covering 4 AC + 2 edge cases
- All 122 tests pass on first run (no fixes needed)
- Ran `/verify SS-07` — all 15 AC met, code quality PASS
- Updated `docs/plan.md` — SS-07 marked ✅, Milestone 2 GEX + CVD checkboxes checked
- Installed `py_vollib` dependency (was in requirements.txt but not installed)
**Decisions made:**
- `compute_greeks()` wraps `py_vollib.black_scholes.greeks.analytical` — catches ValueError/ZeroDivisionError/OverflowError, returns zeros on failure
- `py_vollib` API: `delta('c'/'p', S, K, t, r, sigma)`, `gamma(...)` — raises ValueError on T=0 or iv=0
- `r = 0.0` for all crypto options (no risk-free rate convention)
- `_expiry_to_years()` helper parses both `DDMMMYY` ("28MAR26") and `YYYY-MM-DD` formats for flexibility
- `compute_gex()` aggregates by strike (sums across expiries) — matches how downstream signals use it
- `find_gamma_flip()` uses cumulative net_gex from lowest strike upward, finds first sign change
- CVD z-score clipped to [-3.0, +3.0] (wider than signal [-1, +1] — signals do their own normalization)
- `_MIN_DATA_POINTS = 5` for CVD z-score — returns 0.0 if insufficient history
**Issues/Notes:**
- `py_vollib` was not installed despite being in requirements.txt — installed it (`pip install py_vollib` → also installed `scipy`, `py_lets_be_rational`, `simplejson`)
- py_vollib emits RuntimeWarning for edge cases (NaN in scalar divide) — suppressed by our try/except
- All 122 tests pass (SS-01:17 + SS-02:16 + SS-03:20 + SS-04:17 + SS-05:17 + SS-06:15 + SS-07:20)
**Next session should:**
- Commit SS-07 changes (6 files: `custom/calculators/greeks.py`, `custom/calculators/cvd.py`, `tests/test_greeks.py`, `tests/test_cvd_calc.py`, `docs/sub-specs/SS-07.md`, `docs/plan.md`)
- With SS-07 done, now unblocked: SS-08 (Confluence Zones), SS-09 (Signal 1: Spot Flow), SS-11 (Signal 3: Options), SS-13 (Signal 5: Event Risk)
- Also still unblocked: SS-10 (Signal 2: Leverage, depends on SS-01+SS-03) and SS-14 (Regime Detection, depends on SS-01+SS-02)
- Recommended next: SS-08 (Confluence Zones) or SS-09/SS-10/SS-11 (any of the 4 directional signals)
- Consider implementing signals in order: SS-09 → SS-10 → SS-11 → SS-12 then SS-13, SS-14 to prepare for SS-15 (Signal Engine)
