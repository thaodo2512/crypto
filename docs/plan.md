# Implementation Plan

## Progress Tracker

| ID | Name | Status | Spec Sections | Est. LOC | Dependencies |
|----|------|--------|---------------|----------|--------------|
| SS-01 | Foundation & Infrastructure | 🔲 TODO | §2, §14, §17, §18 | ~250 | None |
| SS-02 | Spot Data Collector | 🔲 TODO | §3.2 | ~200 | SS-01 |
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
- [ ] Database initialized with all tables
- [ ] Spot data (Binance) collecting successfully
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

**Next sub-spec:** SS-01 (Foundation & Infrastructure)
**Blockers:** None
**Notes:** Start here — everything depends on SS-01

---

## Session Log

_Sessions will be logged here via `/handover` command._
