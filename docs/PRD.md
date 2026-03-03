# Crypto Signal Bot — Product Reference Document

## System Summary

Decision support tool for solo BTC/USDT swing traders (1-3 trades/week). Collects data from spot (Binance), futures (Binance/Bybit/OKX), and options (Deribit) markets. Computes 5 composite signals with adaptive regime-based weights. Delivers trade plans via Telegram with AI-powered narrative analysis (Claude API). Built on Freqtrade framework. Runs on a $5/mo VPS with all free-tier APIs. Total monthly cost: $5-8.

## Module Overview

| Module | Description | Key Files |
|--------|-------------|-----------|
| **Data Collectors** | Fetch data from 8 external APIs | `custom/collectors/` |
| **Calculators** | Greeks, GEX, CVD, confluence zones | `custom/calculators/` |
| **Signal 1: Spot Flow** | Real money flow direction (CVD, whales, OB) | `custom/signals/spot_flow.py` |
| **Signal 2: Leverage** | Futures positioning (funding, OI, L/S) | `custom/signals/leverage_positioning.py` |
| **Signal 3: Options** | MM hedge flows (GEX, gamma flip, skew) | `custom/signals/options_structure.py` |
| **Signal 4: Mean Reversion** | Overextension brake (RSI, VWAP, BB, F&G) | `custom/signals/mean_reversion.py` |
| **Signal 5: Event Risk** | Non-directional risk modifier | `custom/signals/event_risk.py` |
| **Regime Detector** | ADX + BB Width → 5 regimes | `custom/regime/detector.py` |
| **Adaptive Weights** | Regime → signal weight allocation | `custom/regime/adaptive_weights.py` |
| **Signal Engine** | Combine signals → final score + consensus | `custom/signals/engine.py` |
| **Trade Plan** | Levels, entry triggers, sizing, exits | `custom/trade_plan/` |
| **Telegram Interface** | Commands, reports, alerts | `custom/output/` |
| **AI Analysis** | Claude API narrative layer | `custom/ai/` |
| **Evaluation** | Outcome tracking, accuracy, reports | `custom/evaluation/` |
| **Scheduler** | APScheduler orchestration | `main.py` |
| **Backtesting** | Walk-forward validation | `tests/test_backtest.py` |
| **Dashboard** | Streamlit visualization (Phase 3) | `dashboard/app.py` |

## Key Thresholds & Parameters

| Parameter | Value | Spec Ref |
|-----------|-------|----------|
| Signal: no signal | \|score\| < 0.15 | §6.1 |
| Signal: weak | \|score\| 0.15–0.35 | §6.1 |
| Signal: moderate | \|score\| 0.35–0.60 | §6.1 |
| Signal: strong | \|score\| > 0.60 | §6.1 |
| Consensus: bullish/bearish threshold | ±0.15 | §6.1 |
| Weight smoothing factor (EMA) | 0.3 | §5.2 |
| Z-score lookback | 30 days | §4.1 |
| Confluence zone width | ±0.5% | §7.2 |
| Confluence min levels | 3 | §7.2 |
| Whale trade threshold | >$100,000 | §3.2 |
| Anti-spoof OB filter | \|imbalance\| > 0.6 | §4.1 |
| ADX regime period | 14 | §5.1 |
| Walk-forward train/test | 60d/30d | §15.2 |

## Safety Limits (IMMUTABLE)

| Limit | Value | Spec Ref |
|-------|-------|----------|
| Risk per trade cap | 2% | §7.4 |
| Max leverage | 3x | §7.4 |
| Event risk STAY OUT | >0.8 | §4.5 |
| Signal suspension | 2h pre Tier-1 → 1h post | §8.3 |
| Minimum R:R for entry | 1.5:1 | §7.5 |
| AI API daily limit | 10 calls | §11.10 |

## Non-Functional Requirements

| Metric | Target |
|--------|--------|
| Win rate | 55–60% |
| Risk:Reward ratio | 1:1.5 min, 1:2 ideal |
| Signal frequency | 3–7 per month |
| API calls/day | ~1,850 (within free tiers) |
| VPS cost | $4–5/mo |
| AI cost | $1–3/mo |
| Data staleness alert | >30 min |
| API latency alert | >5 sec |
| Alert cooldown (CRITICAL) | 15 min |
| Alert cooldown (WARNING) | 30 min |
| Alert cooldown (INFO) | 2 hours |

## Data Sources

| Source | Data | Cost | Fallback |
|--------|------|------|----------|
| Binance Spot | OHLCV, orderbook, trades | Free | Bybit/OKX |
| Binance Futures | Funding, OI, L/S, taker | Free | Bybit/OKX |
| Bybit | Funding, OI (validation) | Free | OKX |
| OKX | Funding, OI (validation) | Free | Bybit |
| Deribit | Options OI, IV, trades | Free | None (unique) |
| Coinglass | Liquidation data | Free* | OI-based estimate |
| Alternative.me | Fear & Greed Index | Free | Self-calculated proxy |
| FRED API | CPI, NFP, PCE actuals | Free | N/A |
| Anthropic API | AI narrative analysis | ~$1-3/mo | System works without it |
