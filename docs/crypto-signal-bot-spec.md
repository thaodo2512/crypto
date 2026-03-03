# Crypto Signal Bot — System Specification

**Version:** 1.2  
**Last Updated:** February 28, 2026  
**Status:** Draft  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Data Sources & Collection](#3-data-sources--collection)
4. [Signal Engine](#4-signal-engine)
   - 4.1 Composite Signal 1: Spot Flow
   - 4.2 Composite Signal 2: Leverage Positioning
   - 4.3 Composite Signal 3: Options Structure
   - 4.4 Composite Signal 4: Mean Reversion
   - 4.5 Signal 5: Event Risk (Modifier)
5. [Adaptive Weight Engine](#5-adaptive-weight-engine)
6. [Final Score Calculation](#6-final-score-calculation)
7. [Trade Decision Layers](#7-trade-decision-layers)
   - 7.1 Layer 1: Directional Bias
   - 7.2 Layer 2: Key Price Levels & Confluence Zones
   - 7.3 Layer 3: Entry Triggers
   - 7.4 Layer 4: Position Sizing
   - 7.5 Layer 5: Exit Plan
8. [Macro Economic Calendar](#8-macro-economic-calendar)
9. [Scan Intervals & Scheduling](#9-scan-intervals--scheduling)
10. [Alert System](#10-alert-system)
11. [AI Analysis Layer (Claude API)](#11-ai-analysis-layer-claude-api)
12. [Telegram Bot Interface](#12-telegram-bot-interface)
13. [Dashboard (Streamlit)](#13-dashboard-streamlit)
14. [Database Schema](#14-database-schema)
15. [Backtesting Framework](#15-backtesting-framework)
16. [Performance Evaluation & Feedback Loop](#16-performance-evaluation--feedback-loop)
17. [Tech Stack & Dependencies](#17-tech-stack--dependencies)
18. [Project Structure](#18-project-structure)
19. [Deployment](#19-deployment)
20. [Development Roadmap](#20-development-roadmap)
21. [Limitations & Known Risks](#21-limitations--known-risks)
22. [Appendix](#22-appendix)

---

## 1. Executive Summary

### 1.1 Purpose

This system is a **decision support tool** (not an auto-trading bot) that collects crypto market data from spot, futures, and options markets, computes directional signals using a composite scoring system with adaptive weights, and delivers actionable trade plans via Telegram.

### 1.2 Core Design Principles

- **Composite over individual indicators:** 5 independent composite signals replace 14+ correlated raw indicators, eliminating double-counting and reducing false signals.
- **Adaptive over static:** Weights adjust automatically based on detected market regime (trending vs. ranging), so the system performs consistently across different market conditions.
- **Consensus over score magnitude:** A +0.3 score with 4/4 signals agreeing is fundamentally different from +0.3 where 2 signals are bullish and 2 are bearish. The system explicitly tracks and penalizes internal conflict.
- **5-layer decision framework:** Directional bias alone is insufficient. The system provides price levels, entry triggers, position sizing, and exit plans — all required before placing a trade.
- **Safety first:** Macro events, gamma flip proximity, liquidation cascades, and options expiry risk automatically reduce signal confidence or suspend signals entirely.

### 1.3 Target Asset

BTC/USDT (primary). ETH/USDT (secondary, future expansion). Altcoin options liquidity is insufficient for reliable signal generation.

### 1.4 Target User

Solo crypto trader making 1-3 swing/position trades per week, checking signals once or twice daily via Telegram on mobile.

### 1.5 Expected Performance

| Metric | Target |
|---|---|
| Win rate | 55–60% |
| Risk:Reward ratio | 1:1.5 minimum, 1:2 ideal |
| Risk per trade | 1–2% of portfolio |
| Max leverage | 3x (hard cap) |
| Signal frequency | 3–7 actionable signals per month |
| False signal filtering | Consensus check removes ~40% of weak signals |

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        VPS ($5/mo)                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              FREQTRADE (Core Framework)              │   │
│  │                                                       │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │   CCXT   │  │ Custom   │  │  Strategy Engine  │   │   │
│  │  │ Exchange │  │Collectors│  │  (Signal Logic)   │   │   │
│  │  │Connectors│  │          │  │                    │   │   │
│  │  └────┬─────┘  └────┬─────┘  └────────┬───────────┘   │   │
│  │       │             │                  │               │   │
│  │       ▼             ▼                  ▼               │   │
│  │  ┌──────────────────────────────────────────────┐     │   │
│  │  │            SQLite Database                    │     │   │
│  │  └──────────────────────────────────────────────┘     │   │
│  │                                                       │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │ Telegram │  │   WebUI  │  │    Scheduler     │   │   │
│  │  │   Bot    │  │(built-in)│  │  (APScheduler)   │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              CUSTOM MODULES                          │   │
│  │                                                       │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │  Signal  │  │ Adaptive │  │   Macro Event    │   │   │
│  │  │  Engine  │  │ Weights  │  │    Calendar      │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │   GEX    │  │Confluence│  │   Trade Plan     │   │   │
│  │  │Calculator│  │  Zones   │  │   Generator      │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │  AI Analysis Layer (Claude API)              │   │   │
│  │  │  Prompt Builder → API Call → Parse Response  │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────┐                               │
│  │  Streamlit Dashboard    │  (Optional, Phase 3)          │
│  └─────────────────────────┘                               │
└─────────────────────────────────────────────────────────────┘

External APIs (all FREE):
  ├─ Binance Spot API
  ├─ Binance Futures API
  ├─ Bybit API
  ├─ OKX API
  ├─ Deribit API
  ├─ Coinglass Free Tier
  ├─ Alternative.me (Fear & Greed)
  ├─ FRED API (Macro data)
  └─ Anthropic API (Claude AI analysis)
```

### 2.2 Framework Choice Rationale

The system uses **Freqtrade** as its core framework, extended with custom modules. Freqtrade provides data download/storage, exchange connectors (via CCXT), Telegram bot, backtesting engine, strategy base class, position sizing, performance tracking, and WebUI — eliminating ~70% of boilerplate code.

Custom code is limited to the signal engine, GEX calculator, adaptive weights, confluence zones, macro calendar, and trade plan generator — the parts that are unique to this system's design.

### 2.3 Total Cost

| Item | Monthly Cost |
|---|---|
| VPS (Hetzner/Vultr) | $4–5 |
| All exchange data APIs | $0 |
| Freqtrade + CCXT | $0 (open source) |
| Anthropic API (Claude Sonnet) | ~$1–3 (1–2 calls/day) |
| **Total** | **$5–8/month** |

---

## 3. Data Sources & Collection

### 3.1 Source Registry

| Source | Type | Data | Cost | Stability | Fallback |
|---|---|---|---|---|---|
| Deribit API | Options | OI, IV, volume, trades, order book | Free | 9/10 | None (unique) |
| Binance Spot API | Spot | OHLCV, order book, aggTrades, ticker | Free | 8/10 | Bybit/OKX |
| Binance Futures API | Futures | Funding, OI, klines, L/S ratio, taker ratio, premium index | Free | 8/10 | Bybit/OKX |
| Bybit API | Futures | Funding, OI (cross-validate) | Free | 7/10 | OKX |
| OKX API | Futures | Funding, OI (cross-validate) | Free | 7/10 | Bybit |
| Coinglass Free Tier | Aggregated | Liquidation data, aggregated metrics | Free* | 6/10 | Estimate from OI changes |
| Alternative.me | Sentiment | Fear & Greed Index | Free | 5/10 | Self-calculated proxy |
| FRED API | Macro | CPI, NFP, PCE actual values | Free | 9/10 | N/A |

*Coinglass free tier: ~100 requests/day. Sufficient for 2–3 daily snapshots.

### 3.2 Spot Market Data (Binance Spot API)

**Endpoints:**

| Endpoint | Data | Used For |
|---|---|---|
| `GET /api/v3/ticker/24hr` | Price, 24h volume, price change | Market overview |
| `GET /api/v3/klines` | OHLCV candles (1m → 1M) | Technical indicators |
| `GET /api/v3/depth?limit=20` | Order book snapshot | Order book imbalance |
| `GET /api/v3/aggTrades` | Aggregated trades | CVD calculation, whale detection |
| `GET /api/v3/ticker/bookTicker` | Best bid/ask | Spread monitoring |

**Derived Metrics:**

- **CVD (Cumulative Volume Delta):** Sum of buyer-aggressor volume minus seller-aggressor volume over time. Calculated from aggTrades where `trade_price >= ask` counts as buy aggression and `trade_price <= bid` counts as sell aggression.
- **Order Book Imbalance:** `(total_bid_depth - total_ask_depth) / (total_bid_depth + total_ask_depth)` from top 20 levels. Range: [-1, +1].
- **Whale Trade Detection:** Filter aggTrades where `value > $100,000`. Track ratio: `whale_buy_volume / (whale_buy_volume + whale_sell_volume)`.
- **Volume Ratio:** `current_volume / SMA(volume, 20)`. Values > 1.5 indicate unusual activity.
- **Technical Indicators (via pandas-ta):** RSI(14), EMA(21/55/200), VWAP, Bollinger Bands(20, 2), ADX(14).

### 3.3 Futures Market Data

**Binance Futures API (Primary):**

| Endpoint | Data | Used For |
|---|---|---|
| `GET /fapi/v1/fundingRate` | Funding rate history | Leverage sentiment |
| `GET /fapi/v1/openInterest` | Current OI | Total open positions |
| `GET /futures/data/openInterestHist` | OI history | OI trend tracking |
| `GET /fapi/v1/klines` | Futures OHLCV | Futures price data |
| `GET /futures/data/topLongShortPositionRatio` | Top trader L/S ratio | Smart money proxy |
| `GET /futures/data/globalLongShortAccountRatio` | Global L/S ratio | Retail proxy |
| `GET /futures/data/takerlongshortRatio` | Taker buy/sell ratio | Aggressive flow |
| `GET /fapi/v1/premiumIndex` | Mark price, index price | Basis calculation |

**Cross-Validation (Bybit + OKX):**

| Exchange | Endpoints | Purpose |
|---|---|---|
| Bybit | `/v5/market/funding/history`, `/v5/market/open-interest` | Validate Binance funding + OI |
| OKX | `/api/v5/public/funding-rate`, `/api/v5/public/open-interest` | Validate Binance funding + OI |

**Derived Metrics:**

- **Aggregated Funding Rate:** Weighted average across Binance, Bybit, OKX. Weight = exchange OI proportion.
- **Futures Basis:** `(futures_price - spot_price) / spot_price × 100`. Annualized: `basis × (365 / days_to_expiry)`.
- **OI-Price Regime:** Classified as `NEW_LONGS` (OI↑ Price↑), `NEW_SHORTS` (OI↑ Price↓), `LONG_CLOSING` (OI↓ Price↓), or `SHORT_CLOSING` (OI↓ Price↑).
- **Smart vs. Retail Divergence:** Compare top trader L/S ratio (smart money proxy) against global account L/S ratio (retail proxy). Divergence = actionable signal.

### 3.4 Options Market Data (Deribit API)

**Endpoints:**

| Endpoint | Data | Used For |
|---|---|---|
| `GET /public/get_instruments` | Active contracts list | Enumerate all BTC options |
| `GET /public/ticker` | Price, IV, OI per instrument | Full options chain |
| `GET /public/get_book_summary_by_currency` | Summary across all options | Quick overview |
| `GET /public/get_order_book` | Order book depth | Options order flow |
| `GET /public/get_last_trades_by_currency` | Recent trades | Unusual activity detection |
| `GET /public/get_index_price` | BTC index price | Spot reference for calculations |

**Derived Metrics (Self-Calculated):**

- **Greeks (Delta, Gamma):** Calculated via Black-Scholes using `py_vollib` with IV from Deribit.
- **GEX (Gamma Exposure):** Per strike: `call_gex = gamma × call_OI × spot² × 0.01`, `put_gex = gamma × put_OI × spot² × 0.01 × (-1)`, `net_gex = call_gex + put_gex`.
- **Gamma Flip Point:** The strike price where cumulative net GEX changes sign. Above flip = positive gamma (MM dampens moves). Below flip = negative gamma (MM amplifies moves).
- **Max Pain:** The strike K that minimizes total intrinsic value: `pain(K) = Σ call_OI × max(0, K - strike_i) + Σ put_OI × max(0, strike_i - K)`. Max pain = K with lowest pain.
- **IV Skew:** `ATM put IV - ATM call IV`. Positive skew = market pricing more downside risk.
- **Put/Call Ratio:** Both by OI and by volume.
- **Call/Put Walls:** Strikes with highest call OI (resistance) and highest put OI (support).

### 3.5 Sentiment & Macro Data

| Source | Endpoint | Data |
|---|---|---|
| Alternative.me | `GET https://api.alternative.me/fng/` | Fear & Greed Index (0–100) |
| FRED API | `GET /fred/series/observations?series_id=CPIAUCSL` | CPI actual values |
| Static Calendar | Local JSON/Python file | FOMC, CPI, NFP, PPI, PCE dates |

### 3.6 Data Health Monitoring

Every data source is monitored with:

- **Last successful fetch timestamp:** Alert if > 30 minutes stale.
- **Response time tracking:** Alert if latency > 5 seconds.
- **Schema validation:** Verify response structure on every fetch. Detect API changes early.
- **Fallback chain:** If primary source fails 3 consecutive times, switch to fallback. If no fallback exists, neutralize the affected indicator (score = 0) rather than using stale data.
- **Telegram health report:** Available via `/health` command showing all source statuses.

---

## 4. Signal Engine

The signal engine produces 5 composite signals, each answering a distinct question about the market. All scores are normalized to the range **[-1.0, +1.0]** where negative = bearish and positive = bullish. Signal 5 (Event Risk) is a non-directional modifier in range **[0, 1.0]**.

### 4.1 Composite Signal 1: Spot Flow

**Question:** "Where is real money actually flowing?"

**Rationale:** Spot market reflects genuine capital movement. Futures can be manipulated with leverage, options can be skewed by MM positioning, but spot flow = real money changing hands. When all other signals conflict, spot flow is the tiebreaker.

**Inputs:**

| Input | Source | Update Frequency |
|---|---|---|
| CVD (24h, 4h) | Binance aggTrades | Every 1 hour |
| Whale trade ratio | Binance aggTrades (> $100k) | Every 1 hour |
| Order book imbalance | Binance depth | Every 15 minutes |
| Volume ratio | Binance klines | Every 1 hour |

**Calculation Logic:**

```
Component 1 — CVD Analysis (weight: 50%):
  - Compute CVD direction (positive/negative)
  - Compare CVD direction with price direction:
    - Same direction → confirmed trend → score follows CVD z-score
    - Opposite direction → DIVERGENCE → amplified contrarian signal (1.5×)
  - Cross-check with 4h CVD: if 4h contradicts 24h → reduce by 0.7×
  - Z-score normalization: (CVD - mean_30d) / std_30d, clipped to [-1, +1]

Component 2 — Whale Trade Ratio (weight: 25%):
  - Score = (whale_ratio - 0.5) × 2
  - Range: [-1, +1] where 0 = balanced, +1 = all buys, -1 = all sells

Component 3 — Order Book Imbalance (weight: 25%):
  - Score = imbalance value (already [-1, +1])
  - Anti-spoof filter: if |imbalance| > 0.6, reduce to 50% (likely spoofed)

Volume Multiplier (does not change direction):
  - volume_ratio > 1.5 → multiply by 1.3 (high volume confirms)
  - volume_ratio < 0.5 → multiply by 0.6 (low volume weakens)
  - Otherwise → linear interpolation: 0.7 + (volume_ratio × 0.4)

Final = clip((C1×0.50 + C2×0.25 + C3×0.25) × volume_multiplier, -1, +1)
```

### 4.2 Composite Signal 2: Leverage Positioning

**Question:** "How are leveraged traders positioned, and is the crowd overextended?"

**Rationale:** Leverage positioning reflects expectations and risk appetite — distinct from actual spot flow. Extreme positioning often precedes squeezes (contrarian signal), while moderate positioning confirms trend (momentum signal). This signal uses **both** momentum and contrarian logic depending on extremity.

**Inputs:**

| Input | Source | Update Frequency |
|---|---|---|
| Aggregated funding rate | Binance + Bybit + OKX | Every 1 hour |
| OI change % (24h) | Binance + Bybit + OKX | Every 15 minutes |
| Price change % (24h) | Binance | Every 15 minutes |
| Top trader L/S ratio | Binance | Every 1 hour |
| Retail L/S ratio | Binance | Every 1 hour |
| Taker buy/sell ratio | Binance | Every 1 hour |

**Calculation Logic:**

```
Component 1 — Funding Rate (weight: 30%):
  CONTRARIAN at extremes, MOMENTUM at moderate levels:
  - funding > 0.05% → score: -0.8 to -1.0 (crowded long → bearish)
  - funding 0.03–0.05% → score: -0.3 to -0.8
  - funding 0.01–0.03% → score: 0.0 (normal)
  - funding 0 to -0.01% → score: +0.1
  - funding -0.01 to -0.03% → score: +0.3 to +0.6
  - funding < -0.03% → score: +0.8 to +1.0 (short squeeze setup)

Component 2 — OI-Price Regime (weight: 30%):
  - OI↑ + Price↑ → NEW_LONGS → +0.6 to +1.0 (continuation)
  - OI↑ + Price↓ → NEW_SHORTS → -0.6 to -1.0 (bearish pressure)
  - OI↓ + Price↓ → LONG_CLOSING → -0.3 (capitulation, near bottom)
  - OI↓ + Price↑ → SHORT_CLOSING → +0.3 (squeeze, but weak)
  OI threshold: 1% change to trigger regime classification.

Component 3 — Smart vs. Retail Divergence (weight: 25%):
  - Top long + Retail short → +0.8 (smart money setup)
  - Top short + Retail long → -0.8 (retail trap)
  - Both aligned → ±0.2 (crowded)
  L/S thresholds: > 1.1 = net long, < 0.9 = net short.

Component 4 — Taker Aggression (weight: 15%):
  - Score = clip((taker_ratio - 1.0) × 3, -1, +1)

Final = clip(C1×0.30 + C2×0.30 + C3×0.25 + C4×0.15, -1, +1)
```

**Internal Consistency Check:**

After computing components, check agreement:
- 3+ components same direction → consistency_multiplier = 1.3
- 2 same direction, 0 opposite → 1.1
- 2+ positive AND 2+ negative → 0.5 (strong internal conflict)
- Otherwise → 0.8

Apply: `final_score *= consistency_multiplier` (then re-clip).

### 4.3 Composite Signal 3: Options Structure

**Question:** "Are market maker hedge flows supporting or opposing the current price direction?"

**Rationale:** Options market makers hedge their positions by buying/selling spot BTC. Their hedging creates large, predictable flows. Understanding whether MMs are in positive gamma (dampening moves) or negative gamma (amplifying moves), and where the gamma flip point is relative to price, reveals hidden support/resistance and volatility regime.

**Inputs:**

| Input | Source | Update Frequency |
|---|---|---|
| OI by strike (all expiries) | Deribit | Every 4 hours |
| IV by strike | Deribit | Every 4 hours |
| BTC spot price | Deribit index price | Every 4 hours |
| DVol Index | Deribit | Every 4 hours |

**Calculation Logic:**

```
Component 1 — Gamma Flip Distance (weight: 40%):
  flip_distance_pct = (spot - gamma_flip) / spot × 100
  - distance > +5% → +0.8 (deep positive gamma, stable)
  - distance +2% to +5% → +0.5
  - distance 0 to +2% → +0.2 (caution)
  - distance -2% to 0 → -0.5 (entered negative gamma)
  - distance < -2% → -0.8 (deep negative gamma, dangerous)

Component 2 — Net GEX Level (weight: 25%):
  Normalize via z-score against 30-day history.
  - z-score > 1 → +0.6 (strong positive = stable market)
  - z-score 0 to 1 → +0.3
  - z-score -1 to 0 → -0.3
  - z-score < -1 → -0.6 (strong negative = volatile ahead)

Component 3 — IV Skew (weight: 20%):
  CONTRARIAN: high put IV = fear = buying opportunity, high call IV = greed = selling opportunity.
  - skew > +5 → +0.6 (heavy put demand = contrarian bullish)
  - skew +2 to +5 → +0.3
  - skew -2 to +2 → 0.0
  - skew -5 to -2 → -0.3
  - skew < -5 → -0.6 (heavy call demand = contrarian bearish)

Component 4 — Max Pain Gravity (weight: 15%):
  mp_distance_pct = (spot - max_pain) / spot × 100
  - distance > +5% → -0.5 (gravity pulls down)
  - distance +2% to +5% → -0.3
  - distance -2% to +2% → 0.0 (near max pain)
  - distance -5% to -2% → +0.3
  - distance < -5% → +0.5 (gravity pulls up)

Final = clip(C1×0.40 + C2×0.25 + C3×0.20 + C4×0.15, -1, +1)
```

**GEX Calculation Detail:**

```
For each active BTC option instrument on Deribit:
  1. Parse instrument name → extract strike, expiry, type (call/put)
  2. Compute time_to_expiry in years
  3. Get IV and OI from ticker data
  4. Calculate gamma using Black-Scholes: gamma(spot, strike, T, r, IV)
  5. call_gex = gamma × call_OI × spot² × 0.01
  6. put_gex = gamma × put_OI × spot² × 0.01 × (-1)
  7. net_gex_at_strike = call_gex + put_gex

Gamma Flip Point:
  Sort strikes ascending.
  Compute cumulative net_gex from lowest strike upward.
  Flip point = strike where cumulative net_gex changes sign.
  
Assumption: MMs are net short options (selling to retail/funds who buy).
This holds ~70-80% of the time in crypto options markets.
When wrong, GEX signal inverts — tracked via backtest accuracy.
```

### 4.4 Composite Signal 4: Mean Reversion

**Question:** "Is the market overextended and due for a pullback or bounce?"

**Rationale:** Signals 1–3 are primarily momentum-based (follow the trend). Signal 4 acts as a brake — when the market is overextended, it pulls the final score back toward neutral, preventing FOMO entries at tops or panic sells at bottoms. Its logic is **inverse** to momentum: when everything looks bullish, this signal turns bearish, and vice versa.

**Inputs:**

| Input | Source | Update Frequency |
|---|---|---|
| RSI(14) | Binance klines (via pandas-ta) | Every 24 hours |
| Price vs. VWAP | Binance klines | Every 24 hours |
| Futures basis (annualized) | Binance premium index | Every 1 hour |
| Fear & Greed Index | Alternative.me | Every 24 hours |
| Bollinger Band position | Binance klines (via pandas-ta) | Every 24 hours |

**Calculation Logic:**

```
Component 1 — RSI (weight: 30%):
  - RSI > 80 → -1.0 (extreme overbought)
  - RSI 70–80 → -0.5 to -1.0
  - RSI 55–70 → 0.0
  - RSI 45–55 → 0.0
  - RSI 30–45 → +0.5
  - RSI < 20 → +1.0 (extreme oversold)

Component 2 — Price vs. VWAP (weight: 20%):
  vwap_distance = (price - vwap) / vwap × 100
  - distance > +5% → -0.8
  - distance +2% to +5% → -0.3
  - distance -2% to +2% → 0.0
  - distance -5% to -2% → +0.3
  - distance < -5% → +0.8

Component 3 — Futures Basis (weight: 20%):
  annualized_basis = basis_pct × 365
  - basis > 30% → -0.8 (overheated)
  - basis 15–30% → -0.4
  - basis 5–15% → 0.0 (healthy)
  - basis -5% to 5% → +0.3
  - basis < -5% (backwardation) → +0.8

Component 4 — Fear & Greed (weight: 15%):
  - F&G > 80 → -0.8 (extreme greed = sell signal)
  - F&G 60–80 → -0.3
  - F&G 40–60 → 0.0
  - F&G 20–40 → +0.3
  - F&G < 20 → +0.8 (extreme fear = buy signal)

Component 5 — Bollinger Band Position (weight: 15%):
  bb_position = (price - bb_lower) / (bb_upper - bb_lower)
  - position > 0.95 → -0.8 (touching upper)
  - position 0.80–0.95 → -0.4
  - position 0.20–0.80 → 0.0 (mid range)
  - position 0.05–0.20 → +0.4
  - position < 0.05 → +0.8 (touching lower)

Final = clip(C1×0.30 + C2×0.20 + C3×0.20 + C4×0.15 + C5×0.15, -1, +1)
```

**Fear & Greed Fallback Proxy (if Alternative.me is unavailable):**

```
fg_proxy = (
  (1 - volatility_percentile) × 25 +
  min(25, max(0, funding_rate × 500 + 12.5)) +
  min(25, volume_ratio × 12.5) +
  min(25, max(0, price_change_7d × 2.5 + 12.5))
)
Range: 0–100, same interpretation as original index.
```

### 4.5 Signal 5: Event Risk (Modifier)

**Question:** "How likely is a sudden, unpredictable price move?"

**Rationale:** Event Risk is **not directional** — it doesn't say long or short. It measures the probability of a sharp move in either direction. When event risk is high, the system reduces confidence on all directional signals, potentially suspending trade recommendations entirely.

**Inputs:**

| Input | Source | Update Frequency |
|---|---|---|
| Hours to nearest options expiry | Deribit instruments | Every 4 hours |
| Expiry notional (BTC) | Deribit OI | Every 4 hours |
| Long/short liquidation (24h) | Coinglass | Every 1 hour |
| Gamma flip distance | Computed (Signal 3) | Every 4 hours |
| DVol Index | Deribit | Every 4 hours |
| Macro event proximity | Static calendar | Every 24 hours |

**Calculation Logic:**

```
Risk Component 1 — Options Expiry:
  - Expiry < 24h AND notional > 10,000 BTC → 0.8
  - Expiry < 48h AND notional > 5,000 BTC → 0.4
  - Otherwise → 0.0

Risk Component 2 — Liquidation Cascade:
  total_liq = long_liq + short_liq (24h)
  - total > $200M → 0.9 (cascade in progress)
  - total > $100M → 0.5
  - total > $50M → 0.2
  - Otherwise → 0.0

Risk Component 3 — Gamma Flip Proximity:
  - |flip_distance_pct| < 1% → 0.7 (very close to flip)
  - |flip_distance_pct| < 3% → 0.3
  - Otherwise → 0.0

Risk Component 4 — Implied Volatility:
  - DVol > 80 → 0.8
  - DVol 60–80 → 0.4
  - DVol 40–60 → 0.1
  - DVol < 40 → 0.0

Risk Component 5 — Macro Event (NEW):
  upcoming = events within next 24 hours
  - Tier 1 event < 2h away → 0.95
  - Tier 1 event < 6h away → 0.70
  - Tier 1 event < 24h away → 0.40
  - Tier 2 event < 2h away → 0.60
  - Tier 2 event < 6h away → 0.30
  - Tier 3 event < 2h away → 0.30
  - Otherwise → 0.0

Final Event Risk = max(all components)
Range: [0, 1.0] where 0 = calm, 1.0 = extreme risk.

OVERRIDE: If event_risk > 0.8 → system outputs "STAY OUT" regardless of signal score.
```

---

## 5. Adaptive Weight Engine

### 5.1 Market Regime Detection

The system detects the current market regime using ADX(14) and Bollinger Band Width percentile (90-day lookback). Regime determines how much weight each composite signal receives.

**Regime Classification:**

| Regime | ADX | BB Width %ile | Interpretation |
|---|---|---|---|
| `STRONG_TREND` | > 30 | > 60th | Clear, strong directional move |
| `MODERATE_TREND` | > 25 | > 40th | Directional but not extreme |
| `WIDE_RANGE` | < 25 | < 50th | Range-bound, moderate volatility |
| `TIGHT_RANGE` | < 20 | < 30th | Low volatility squeeze |
| `TRANSITIONAL` | Other | Other | Regime unclear, changing |

**Weight Allocation by Regime:**

| Signal | Strong Trend | Moderate Trend | Wide Range | Tight Range | Transitional |
|---|---|---|---|---|---|
| Spot Flow | 0.35 | 0.30 | 0.20 | 0.15 | 0.25 |
| Leverage Positioning | 0.30 | 0.25 | 0.20 | 0.20 | 0.25 |
| Options Structure | 0.20 | 0.25 | 0.30 | 0.30 | 0.25 |
| Mean Reversion | 0.15 | 0.20 | 0.30 | 0.35 | 0.25 |

**Logic:**
- Trending markets → momentum signals (Spot Flow, Leverage) get higher weight, mean reversion is reduced (it generates false signals during trends).
- Ranging markets → Mean Reversion and Options (pinning/support/resistance) get higher weight, momentum signals are reduced (false breakouts).
- Transitional → equal weights with reduced confidence.

### 5.2 Weight Smoothing (EMA)

To prevent weight whipsawing when ADX oscillates near thresholds:

```
smoothing_factor = 0.3
weight_t = smoothing × new_regime_weight + (1 - smoothing) × previous_weight
```

A regime must persist for approximately 3+ days before weights shift significantly. This prevents the system from overreacting to single-day noise.

---

## 6. Final Score Calculation

### 6.1 Computation Pipeline

```
Step 1: Compute 5 signals
  spot_flow       ∈ [-1, +1]
  leverage_pos    ∈ [-1, +1]
  options_struct  ∈ [-1, +1]
  mean_reversion  ∈ [-1, +1]
  event_risk      ∈ [0, 1]

Step 2: Detect regime → get adaptive weights
  weights = adaptive_weight_engine.get_weights(regime)

Step 3: Compute raw score
  raw_score = Σ(signal_i × weight_i) for i ∈ {1,2,3,4}
  Range: [-1, +1]

Step 4: Consensus check
  Count signals > +0.15 (bullish), < -0.15 (bearish), otherwise neutral.
  - 3+ same direction → STRONG_CONSENSUS → multiplier = 1.3
  - 2 same, 0 opposite → MODERATE_CONSENSUS → multiplier = 1.1
  - 2+ positive AND 2+ negative → CONFLICT → multiplier = 0.5
  - Otherwise → MIXED → multiplier = 0.8

  adjusted_score = clip(raw_score × consensus_multiplier, -1, +1)

Step 5: Event risk penalty
  - event_risk > 0.7 → confidence_penalty = 0.4
  - event_risk 0.4–0.7 → confidence_penalty = 0.7
  - event_risk < 0.4 → confidence_penalty = 1.0

  final_score = adjusted_score × confidence_penalty

Step 6: Classify
  |score| < 0.15 → NEUTRAL (no signal)
  |score| 0.15–0.35 → WEAK
  |score| 0.35–0.60 → MODERATE
  |score| > 0.60 → STRONG

  direction = LONG if score > 0, SHORT if score < 0

Step 7: Confidence level
  confidence_factors = [
    consensus_multiplier > 1.0,
    event_risk < 0.4,
    regime ≠ TRANSITIONAL,
    |final_score| > 0.35,
  ]
  confidence = sum(factors) / len(factors)
  - ≥ 0.75 → HIGH
  - ≥ 0.50 → MEDIUM
  - < 0.50 → LOW
```

### 6.2 Output Schema

```json
{
  "timestamp": "2026-02-28T08:00:00Z",
  "btc_price": 65700,
  "final_score": 0.31,
  "bias": "LONG",
  "strength": "WEAK",
  "confidence": "MEDIUM",
  "regime": "MODERATE_TREND",
  "event_risk": 0.45,
  "consensus": "MIXED",
  "breakdown": {
    "spot_flow": 0.64,
    "leverage_pos": 0.42,
    "options_struct": -0.18,
    "mean_reversion": -0.31
  },
  "weights_used": {
    "spot_flow": 0.30,
    "leverage_pos": 0.25,
    "options_struct": 0.25,
    "mean_reversion": 0.20
  }
}
```

---

## 7. Trade Decision Layers

### 7.1 Layer 1: Directional Bias

Provided by the signal engine output above. This is the "should I lean long or short today?" answer.

### 7.2 Layer 2: Key Price Levels & Confluence Zones

**Level Sources:**

| Source | Level Type | Origin |
|---|---|---|
| Call/Put Walls | Resistance/Support | Deribit OI by strike |
| Gamma Flip Price | Bull/Bear boundary | Self-calculated GEX |
| Max Pain | Expiry magnet | Self-calculated from OI |
| EMA 21/55/200 | Dynamic S/R | Binance klines |
| VWAP | Institutional fair value | Binance klines |
| High Volume Nodes | Strong S/R | Spot volume profile |
| Liquidation Clusters | Hunt zones | Coinglass data |
| Round Numbers | Psychological | $60k, $65k, $70k etc. |

**Confluence Zone Detection:**

A confluence zone is defined as a price area within ±0.5% where **3 or more** independent levels cluster. Zones are ranked by the number of overlapping levels (strength 3, 4, 5+).

```
Algorithm:
  1. Collect all levels with their prices and types.
  2. Sort by price ascending.
  3. For each level, find all other levels within ±0.5% of its price.
  4. If count ≥ 3 → create a zone with center = mean(prices), components = list of types.
  5. Merge overlapping zones.
  6. Classify: support zones (below price) and resistance zones (above price).
```

### 7.3 Layer 3: Entry Triggers

The system generates entry conditions, not automatic entries. Three trigger types:

**Limit Entry:** When confluence zone is far from current price (> 3%). Place limit order at zone center.

**Confirmation Entry:** When price reaches a zone, require ≥ 2 of 3 confirmations before entering:
1. Price action: pin bar, engulfing candle, or hammer at zone.
2. Volume spike: > 1.5× average volume at zone.
3. CVD confirmation: CVD flipping in direction of bias at zone.

**Breakout Entry:** When price breaks a key level (gamma flip, major call/put wall) with volume > 1.5× average and OI increasing (real breakout vs. fake).

**Entry Decision Gate:**

```
Gate 1: Signal strength ≠ "WEAK" and confidence ≠ "LOW" → pass / reject
Gate 2: Nearest confluence zone exists → pass / wait
Gate 3: If at zone, ≥ 2 confirmations → ENTER / WAIT
```

### 7.4 Layer 4: Position Sizing

Fixed fractional risk model. Never risk more than 2% of portfolio on a single trade.

```
Risk allocation by signal quality:
  HIGH confidence + STRONG signal → 2% risk
  HIGH or STRONG (one of two) → 1.5% risk
  MEDIUM confidence → 1% risk
  LOW confidence → 0.5% risk (minimum)

Position size = risk_amount / stop_distance
Leverage cap = 3× (hard limit, regardless of signal quality)
```

### 7.5 Layer 5: Exit Plan

Defined **before** entry, never modified during the trade.

**Stop Loss:** Below support confluence zone + 0.3–0.5% buffer. Never placed at round numbers (easily hunted).

**Take Profit (Scaled Exit):**
- TP1: 50% of position at nearest resistance zone (minimum 1.5R).
- TP2: 30% of position at next resistance zone (target 2–3R).
- TP3: 20% trailing stop using EMA(21) or -2% from local high.

After TP1 is hit, stop loss moves to breakeven.

**Time Stop:** If trade hasn't moved meaningfully in 48 hours, re-evaluate. If next day's signal flips → close regardless of P&L. If signal turns neutral → tighten stop.

---

## 8. Macro Economic Calendar

### 8.1 Event Tiers

| Tier | Events | Typical BTC Impact | Frequency |
|---|---|---|---|
| **Tier 1** | FOMC Rate Decision + Press Conference, CPI, Non-Farm Payrolls | 2–5%+ move | ~20/year |
| **Tier 2** | PPI, PCE, FOMC Minutes, GDP, Jobless Claims (anomalous) | 1–3% move | ~25/year |
| **Tier 3** | ISM Manufacturing/Services, Retail Sales, Consumer Confidence, Fed speeches | 0.5–1% (on surprise) | ~40/year |

### 8.2 Data Source

**Primary:** Static Python/JSON calendar file updated once per year. FOMC, CPI, NFP dates are published by the Fed and BLS in advance.

**Post-Release Actual Data:** FRED API (free) to fetch actual values for comparison against forecasts.

### 8.3 System Behavior Around Macro Events

```
24h before Tier 1 event:
  → Telegram alert: "CPI release tomorrow 13:30 UTC"
  → Event Risk component activated (0.40)

6h before:
  → Telegram warning: "CPI in 6 hours"
  → Event Risk increases (0.70)
  → Signal confidence reduced
  → Bias may override to NEUTRAL

2h before:
  → Telegram: "CPI IMMINENT — 2 hours"
  → Event Risk: 0.95 (EXTREME)
  → ALL SIGNALS SUSPENDED
  → Output: "DO NOT TRADE — Macro event imminent"

Release:
  → Fetch actual from FRED API
  → Compare actual vs. forecast
  → Send Telegram: actual value, surprise magnitude, expected impact

1h after release:
  → Resume signal calculation
  → Send post-macro signal update with market reaction context
```

### 8.4 Surprise Impact Assessment

```
For inflation data (CPI, PCE, PPI):
  surprise = actual - forecast
  > +0.2 → VERY_BEARISH (hotter than expected = hawkish Fed)
  +0.1 to +0.2 → BEARISH
  -0.1 to +0.1 → NEUTRAL
  -0.2 to -0.1 → BULLISH
  < -0.2 → VERY_BULLISH (cooler than expected = dovish Fed)

For jobs data (NFP):
  surprise = actual - forecast (in thousands)
  > +100k → BEARISH (too strong = Fed stays tight)
  +50k to +100k → NEUTRAL
  -50k to +50k → BULLISH (goldilocks)
  < -50k → VERY_BEARISH (recession fears)
```

---

## 9. Scan Intervals & Scheduling

### 9.1 Standard Schedule

| Interval | Data Collected | API Calls |
|---|---|---|
| Every 2 min | BTC price (Binance ticker) | ~720/day |
| | Alert checks: gamma flip, confluence zones, liquidation | |
| Every 15 min | Order book snapshot (Binance spot depth) | ~96/day |
| | Futures OI (Binance + Bybit + OKX) | |
| | Futures basis (Binance premium index) | |
| | Taker buy/sell ratio | |
| Every 1 hour | Funding rate (Binance + Bybit + OKX) | ~72/day |
| | L/S ratio (top trader + retail) | |
| | CVD calculation (from recent trades) | |
| | Whale trade scan | |
| | Coinglass liquidation summary | |
| Every 4 hours | Deribit full options scan (all instruments) | ~600/day |
| | Recalculate: GEX, gamma flip, max pain, IV skew | |
| | Recalculate: composite signals 1–4 | |
| | Update signal score + bias | |
| Every 24 hours (08:00 UTC) | Full daily report via Telegram | |
| | Technical indicators (RSI, EMA, BB, VWAP, ADX) | |
| | Regime detection + adaptive weights update | |
| | Fear & Greed Index | |
| | Confluence zones recalculate | |
| | Macro calendar scan (events in next 48h) | |
| | Performance tracking (fill yesterday's results) | |
| | Database maintenance | |

**Estimated total: ~1,850 API calls/day.** All within free tier limits.

### 9.2 Adaptive Schedule (Event-Driven Acceleration)

When `event_risk > 0.7`, scan intervals tighten:

| Data | Normal | Elevated Risk |
|---|---|---|
| Price | 2 min | 30 sec |
| Futures | 15 min | 5 min |
| Options | 4 hours | 30 min |
| Signals | 4 hours | 30 min |

This ensures the system is most attentive when markets are most dangerous.

### 9.3 Rate Limits Reference

| Exchange | Limit | Headroom |
|---|---|---|
| Binance Spot | 1,200 req/min | ~99% unused |
| Binance Futures | 2,400 req/min | ~99% unused |
| Bybit | 120 req/min | ~95% unused |
| OKX | 20 req/2s | ~90% unused |
| Deribit | 20 req/s | ~80% unused (during full scan) |
| Coinglass Free | ~100 req/day | ~95% unused |

---

## 10. Alert System

### 10.1 Alert Types

| Priority | Trigger | Condition |
|---|---|---|
| 🔴 CRITICAL | Gamma flip breach | Price crosses gamma flip point |
| 🔴 CRITICAL | Liquidation cascade | Total liquidation > $100M in 1 hour |
| 🔴 CRITICAL | Macro event imminent | Tier 1 event < 2 hours away |
| 🟡 WARNING | Funding extreme | Weighted funding > 0.05% or < -0.03% |
| 🟡 WARNING | Large options expiry | > 10,000 BTC notional within 24h |
| 🟡 WARNING | CVD divergence | CVD direction opposes price direction |
| 🟡 WARNING | OI regime change | Regime classification changes |
| 🟡 WARNING | Macro event approaching | Tier 1 event < 24 hours away |
| 🟢 INFO | Signal score change | Score crosses threshold (±0.35 or ±0.60) |
| 🟢 INFO | Entry condition met | Price at zone + confirmations ≥ 2 |
| 🟢 INFO | Post-macro update | Signal resume after macro event |

### 10.2 Alert Cooldown

To prevent alert spam:
- Same alert type: minimum 30-minute cooldown.
- CRITICAL alerts: 15-minute cooldown (more urgent).
- INFO alerts: 2-hour cooldown.

---

## 11. AI Analysis Layer (Claude API)

### 11.1 Purpose

The quantitative signal engine produces scores, but numbers alone lack context. The AI Analysis Layer takes **all system data** — signals, raw metrics, levels, macro events, recent performance — compiles it into a structured prompt, sends it to Claude via the Anthropic API, and receives a natural-language daily briefing that explains the "why" behind the numbers, identifies hidden risks, and provides an actionable narrative.

This is the final interpretation layer: **Data → Signals → AI Narrative → Human Decision**.

### 11.2 When AI Analysis Runs

| Trigger | Prompt Type | Description |
|---|---|---|
| Daily 08:00 UTC | Full Daily Briefing | Comprehensive analysis with all data |
| Signal score crosses ±0.35 or ±0.60 | Signal Change Analysis | Explain what changed and why |
| Post-macro event (1h after) | Macro Impact Analysis | Interpret data release + market reaction |
| User command `/ai` | On-Demand Analysis | Current snapshot with AI interpretation |
| User command `/ai [question]` | Custom Question | User asks specific question about market data |

### 11.3 Prompt Architecture

The prompt is constructed from a **system prompt** (static, defines Claude's role and rules) and a **data payload** (dynamic, compiled from current system state).

**System Prompt (Static):**

```
You are a crypto market analyst assistant embedded in an automated signal 
system. Your role is to interpret quantitative data and provide clear, 
actionable analysis for a swing trader.

RULES:
1. You receive structured market data from the signal system. This data 
   is REAL and CURRENT — trust it.
2. Be direct and concise. Lead with the conclusion, then explain.
3. Always state your confidence level and what could invalidate your view.
4. When signals conflict, explain WHY they conflict and which one 
   matters most in the current context.
5. Never fabricate data. Only reference numbers provided in the data payload.
6. Flag risks the quantitative system might miss: narrative shifts, 
   correlation breakdowns, unusual patterns in the data.
7. Keep response under 400 words for daily briefing, under 200 words 
   for alerts.
8. Use Vietnamese language for all responses.
9. Format for Telegram (plain text, use emoji sparingly, no markdown 
   headers).

TRADING CONTEXT:
- Asset: BTC/USDT
- Style: Swing trade (1-5 day holds)
- Risk: 1-2% per trade, max 3x leverage
- Portfolio size provided in data payload
- The trader checks Telegram 1-2 times per day
```

**Data Payload Template (Dynamic):**

```
=== MARKET SNAPSHOT ===
Timestamp: {timestamp}
BTC Price: ${price} ({change_24h}% 24h)
24h Volume: ${volume} ({volume_vs_avg}x average)

=== COMPOSITE SIGNALS ===
Final Score: {score} | Bias: {bias} | Strength: {strength} | Confidence: {confidence}

Signal 1 — Spot Flow: {spot_flow}
  Components: CVD={cvd}, Whale ratio={whale_ratio}, OB imbalance={ob_imbalance}
  Note: {spot_flow_note}

Signal 2 — Leverage Positioning: {leverage_pos}
  Components: Funding={funding}%, OI regime={oi_regime}, Smart/Retail={smart_retail}, Taker={taker}
  Note: {leverage_note}

Signal 3 — Options Structure: {options_struct}
  Components: Gamma flip=${gamma_flip} ({flip_distance}% away), Net GEX={net_gex}, IV skew={iv_skew}
  Note: {options_note}

Signal 4 — Mean Reversion: {mean_reversion}
  Components: RSI={rsi}, VWAP dist={vwap_dist}%, Basis={basis}%, F&G={fear_greed}, BB pos={bb_pos}
  Note: {mean_reversion_note}

Signal 5 — Event Risk: {event_risk}
  Active risks: {risk_details}

=== REGIME ===
Current: {regime} (ADX={adx}, BB Width %ile={bb_width_pctile})
Weights: SF={w_sf}%, LP={w_lp}%, OS={w_os}%, MR={w_mr}%
Consensus: {consensus} ({n_bull} bullish, {n_bear} bearish, {n_neutral} neutral)

=== KEY LEVELS ===
Support Zones:
{support_zones}

Resistance Zones:
{resistance_zones}

Gamma Flip: ${gamma_flip} | Max Pain: ${max_pain} (expiry: {next_expiry})

=== MACRO CONTEXT ===
Upcoming events (next 48h):
{macro_events}

Last macro event: {last_macro} — Actual: {actual} vs Forecast: {forecast} — Impact: {impact}

=== OPTIONS MARKET ===
Put/Call OI Ratio: {pc_ratio}
DVol: {dvol}%
Largest call wall: ${call_wall} ({call_wall_oi} contracts)
Largest put wall: ${put_wall} ({put_wall_oi} contracts)
Net GEX profile: {gex_summary}

=== FUTURES MARKET ===
Aggregated Funding: {funding_weighted}%
OI Total: ${oi_total} ({oi_change_24h}% 24h)
Long Liquidation 24h: ${long_liq}
Short Liquidation 24h: ${short_liq}
Top Trader L/S: {top_ls} | Retail L/S: {retail_ls}

=== RECENT PERFORMANCE ===
Last 5 signals: {recent_signals}
Win rate (30d): {win_rate}%
Current open position: {open_position}

=== QUESTION ===
{question_or_default}
```

**Default question (for daily briefing):**

```
Based on all the data above, provide:
1. Your overall market read for the next 24-48 hours (2-3 sentences)
2. The single most important thing the trader should pay attention to today
3. If there is a trade setup, describe it. If not, explain why sitting out is correct.
4. One risk or scenario the quantitative signals might be missing
```

### 11.4 Prompt Builder Implementation

```python
class AIPromptBuilder:
    """
    Compiles all system data into a structured prompt for Claude API.
    """
    
    def __init__(self, db, signal_engine, config):
        self.db = db
        self.signal_engine = signal_engine
        self.config = config
        self.system_prompt = self._load_system_prompt()
    
    def build_daily_briefing(self) -> dict:
        """Build the full daily analysis prompt."""
        data = self._collect_all_data()
        payload = self._format_payload(data)
        question = (
            "Based on all the data above, provide:\n"
            "1. Your overall market read for the next 24-48h\n"
            "2. The single most important factor today\n"
            "3. Trade setup if available, or why to sit out\n"
            "4. One risk the quantitative signals might miss"
        )
        return {
            "system": self.system_prompt,
            "user": payload + f"\n=== QUESTION ===\n{question}"
        }
    
    def build_signal_change(self, old_score, new_score) -> dict:
        """Build prompt when signal crosses threshold."""
        data = self._collect_all_data()
        payload = self._format_payload(data)
        question = (
            f"Signal just changed from {old_score:.2f} to {new_score:.2f}. "
            "What caused this shift? Is it meaningful or noise? "
            "Should the trader act on it?"
        )
        return {
            "system": self.system_prompt,
            "user": payload + f"\n=== QUESTION ===\n{question}"
        }
    
    def build_macro_reaction(self, event, actual, forecast) -> dict:
        """Build prompt after macro data release."""
        data = self._collect_all_data()
        payload = self._format_payload(data)
        question = (
            f"{event} just released: Actual={actual} vs Forecast={forecast}. "
            "How is the market reacting? Does this change the medium-term outlook? "
            "When is it safe to trade again?"
        )
        return {
            "system": self.system_prompt,
            "user": payload + f"\n=== QUESTION ===\n{question}"
        }
    
    def build_custom_question(self, user_question: str) -> dict:
        """Build prompt for user's custom question via /ai command."""
        data = self._collect_all_data()
        payload = self._format_payload(data)
        return {
            "system": self.system_prompt,
            "user": payload + f"\n=== QUESTION ===\n{user_question}"
        }
    
    def _collect_all_data(self) -> dict:
        """Gather latest data from all system components."""
        return {
            "price": self.db.get_latest_price(),
            "signals": self.signal_engine.get_latest_signals(),
            "regime": self.signal_engine.get_regime(),
            "levels": self.db.get_confluence_zones(),
            "options": self.db.get_latest_options_summary(),
            "futures": self.db.get_latest_futures_snapshot(),
            "macro": self.db.get_upcoming_macro_events(hours=48),
            "performance": self.db.get_recent_performance(days=30),
            "open_position": self.db.get_open_position(),
        }
    
    def _format_payload(self, data: dict) -> str:
        """Format collected data into the payload template."""
        # ... template string formatting with all data fields
        pass
```

### 11.5 API Integration

```python
import aiohttp

class ClaudeAnalyzer:
    """
    Sends compiled prompts to Claude API and parses responses.
    """
    
    API_URL = "https://api.anthropic.com/v1/messages"
    MODEL = "claude-sonnet-4-5-20250929"  # Cost-effective for daily analysis
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.prompt_builder = None  # Set during initialization
    
    async def analyze(self, prompt: dict) -> str:
        """Send prompt to Claude and return analysis text."""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        
        payload = {
            "model": self.MODEL,
            "max_tokens": 1024,
            "system": prompt["system"],
            "messages": [
                {"role": "user", "content": prompt["user"]}
            ]
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.API_URL, headers=headers, json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["content"][0]["text"]
                else:
                    error = await resp.text()
                    return f"⚠️ AI analysis unavailable: {resp.status}"
    
    async def daily_briefing(self) -> str:
        """Generate daily AI briefing."""
        prompt = self.prompt_builder.build_daily_briefing()
        return await self.analyze(prompt)
    
    async def signal_change_analysis(self, old, new) -> str:
        """Analyze a significant signal change."""
        prompt = self.prompt_builder.build_signal_change(old, new)
        return await self.analyze(prompt)
    
    async def macro_reaction(self, event, actual, forecast) -> str:
        """Analyze market reaction to macro event."""
        prompt = self.prompt_builder.build_macro_reaction(event, actual, forecast)
        return await self.analyze(prompt)
    
    async def custom_question(self, question: str) -> str:
        """Answer user's custom question with full market context."""
        prompt = self.prompt_builder.build_custom_question(question)
        return await self.analyze(prompt)
```

### 11.6 Token & Cost Estimation

**Per API call:**

| Component | Estimated Tokens |
|---|---|
| System prompt | ~400 tokens |
| Data payload | ~1,200–1,500 tokens |
| Response | ~300–500 tokens |
| **Total per call** | **~2,000–2,400 tokens** |

**Daily usage (typical):**

| Trigger | Calls/Day | Tokens/Day |
|---|---|---|
| Daily briefing (08:00 UTC) | 1 | ~2,200 |
| Signal change (occasional) | 0–2 | 0–4,400 |
| Post-macro (event days only) | 0–1 | 0–2,200 |
| User `/ai` commands | 0–3 | 0–6,600 |
| **Typical total** | **1–3** | **~2,200–8,800** |

**Monthly cost (Claude Sonnet):**

```
Conservative (1 call/day):  ~66,000 tokens/month  ≈ $0.40–0.60
Typical (2 calls/day):      ~132,000 tokens/month  ≈ $0.80–1.20
Heavy use (5 calls/day):    ~330,000 tokens/month  ≈ $2.00–3.00
```

**Negligible cost** — less than the VPS itself. Using Claude Sonnet (not Opus) keeps costs minimal while providing excellent analysis quality.

### 11.7 Response Handling & Delivery

AI analysis is delivered through the existing Telegram bot:

**Daily Briefing (automatic):**

```
📊 SIGNAL REPORT — 28 Feb 2026 08:00 UTC
━━━━━━━━━━━━━━━━━━━━━━━━
[... existing quantitative report ...]

━━━ 🤖 AI ANALYSIS ━━━

{claude_response}

━━━━━━━━━━━━━━━━━━━━━━━━
```

The AI analysis is appended to the existing daily report — not a replacement but an enhancement. The trader sees raw numbers first (for those who want data), then the AI narrative (for interpretation).

**On-Demand (via /ai command):**

```
User: /ai tại sao options signal lại bearish trong khi spot flow bullish?

Bot:
🤖 AI ANALYSIS (28 Feb 14:30 UTC)
━━━━━━━━━━━━━━━━━━━━━━━━

{claude_response_to_specific_question}

━━━━━━━━━━━━━━━━━━━━━━━━
⚡ Based on data as of 14:30 UTC
```

### 11.8 Example AI Output

Given the mockup data from the system demo, Claude might produce:

```
🤖 AI PHÂN TÍCH — 28 Feb 2026

Thị trường đang trong trạng thái MÂU THUẪN. Spot flow và leverage 
đều bullish (CVD +$65M, new longs forming), nhưng options structure 
đang cảnh báo — giá chỉ cách gamma flip $500 (0.8%). Nếu mất $65,200, 
MM sẽ bán spot để hedge → amplify đà giảm.

⚡ QUAN TRỌNG NHẤT HÔM NAY: Expiry 8,500 BTC trong 12 giờ. Max pain 
$63,000 thấp hơn giá hiện tại 4%. Sau expiry, hedge unwind có thể tạo 
selling pressure ngắn hạn. Đợi sau 00:00 UTC rồi mới đánh giá lại.

📋 KHUYẾN NGHỊ: CHƯA VÀO LỆNH. Mặc dù bias lean long, event risk quá 
cao (0.45 + expiry sắp tới). Kịch bản tốt nhất: giá pullback về zone 
$63,300 sau expiry → entry long tại đó với 4 confirmations. Set alert 
tại $63,500.

⚠️ RỦI RO ẨN: Fear & Greed 72 (Greed) + RSI 68 — retail đang FOMO. 
Khi retail bullish + smart money mới bắt đầu long = thường đúng ngắn hạn 
nhưng signal sẽ yếu dần. Nếu vào lệnh, nên giảm size xuống 1% thay vì 1.5%.
```

### 11.9 Fallback & Error Handling

```
If Claude API fails:
  → Log error
  → Send Telegram report WITHOUT AI section
  → Append note: "⚠️ AI analysis temporarily unavailable"
  → Retry on next scheduled trigger

If API response is empty or malformed:
  → Skip AI section
  → No impact on quantitative signals (they are independent)

If API key is not configured:
  → AI module disabled entirely
  → System functions normally without it
  → Log: "AI Analysis Layer disabled — no API key"
```

The AI layer is **strictly additive** — it never modifies signal scores, levels, or trade plans. If Claude API is down, the system continues operating exactly as designed. The AI adds interpretation, not computation.

### 11.10 Safety Guardrails

- Claude receives **read-only data**. It cannot execute trades, modify signals, or change system configuration.
- AI output is always clearly labeled with 🤖 emoji to distinguish from quantitative output.
- The system prompt explicitly instructs Claude to never fabricate data or make guarantees.
- AI recommendations are advisory — the quantitative trade plan (entry, stop, TP, size) remains the primary decision framework.
- Rate limiting: maximum 10 API calls per day to prevent runaway costs from bugs.

---

## 12. Telegram Bot Interface

### 12.1 Automatic Messages

| Time | Message | Content |
|---|---|---|
| 08:00 UTC daily | Full Signal Report | All 5 signals, breakdown, levels, risks, opportunities + AI analysis |
| Event-driven | Alerts | Per Section 10 |

### 12.2 User Commands

| Command | Response |
|---|---|
| `/signal` | Quick signal: score, bias, confidence, 5-signal bar chart |
| `/breakdown` | Detailed breakdown of all signal components |
| `/levels` | Support/resistance confluence zones with strength |
| `/entry long` | Full long trade plan: entry, stop, TPs, size |
| `/entry short` | Full short trade plan |
| `/risk` | Event risk check: expiry, liquidation, gamma flip, macro |
| `/regime` | Current market regime + weight allocation |
| `/performance` | 30-day summary: win rate, total R, equity curve |
| `/performance week` | Last 7 days detailed breakdown |
| `/performance signals` | Component-level accuracy (which signal is best/worst) |
| `/performance regime` | Accuracy by market regime |
| `/performance ai` | AI vs. quantitative agreement analysis |
| `/performance levels` | Confluence zone hold rates |
| `/health` | Data source status, latency, uptime |
| `/macro` | Upcoming macro events in next 7 days |
| `/ai` | On-demand AI analysis of current market state |
| `/ai [question]` | AI answers a specific question using all system data as context |

---

## 13. Dashboard (Streamlit)

Optional, implemented in Phase 3. Runs on same VPS, accessed via browser for deep analysis.

### 13.1 Tabs

| Tab | Contents |
|---|---|
| Signals | Final score gauge, composite signal bars, signal history (30d line chart) |
| Options/GEX | GEX by strike (bar chart), gamma flip vs. price (line chart), IV surface, OI heatmap |
| Price Levels | Candlestick chart with overlaid confluence zones, level table |
| Futures | Multi-exchange funding chart, OI chart, basis chart, L/S ratio |
| Performance | Equity curve, win rate over time, signal accuracy by regime |

---

## 14. Database Schema

Using SQLite for initial deployment. Migration path to PostgreSQL if data exceeds 1GB.

### 14.1 Spot Data

```sql
CREATE TABLE spot_price (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, quote_volume REAL, num_trades INTEGER
);

CREATE TABLE spot_cvd (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    cvd_1h REAL, cvd_4h REAL, cvd_24h REAL,
    buy_volume REAL, sell_volume REAL
);

CREATE TABLE spot_orderbook (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    bid_depth_usd REAL, ask_depth_usd REAL,
    imbalance REAL, spread_bps REAL
);

CREATE TABLE spot_whale_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    side TEXT, price REAL, quantity REAL, value_usd REAL
);

CREATE TABLE spot_technicals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    rsi_14 REAL, ema_21 REAL, ema_55 REAL, ema_200 REAL,
    vwap REAL, bb_upper REAL, bb_lower REAL, bb_width REAL,
    adx_14 REAL, volume_sma_20 REAL, volume_ratio REAL
);
```

### 14.2 Futures Data

```sql
CREATE TABLE futures_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    funding_binance REAL, funding_bybit REAL, funding_okx REAL,
    funding_weighted_avg REAL,
    oi_binance_usd REAL, oi_bybit_usd REAL, oi_okx_usd REAL,
    oi_total_usd REAL,
    oi_change_1h_pct REAL, oi_change_4h_pct REAL, oi_change_24h_pct REAL,
    futures_price REAL, spot_price REAL,
    basis_pct REAL, annualized_premium_pct REAL,
    top_trader_ls_ratio REAL, account_ls_ratio REAL, global_ls_ratio REAL,
    taker_buy_sell_ratio REAL,
    taker_buy_volume REAL, taker_sell_volume REAL
);

CREATE TABLE futures_liquidations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    long_liq_usd REAL, short_liq_usd REAL,
    total_liq_usd REAL, liq_ratio REAL
);

CREATE TABLE futures_oi_price (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    price REAL, total_oi REAL,
    oi_change_pct REAL, price_change_pct REAL,
    regime TEXT
);
```

### 14.3 Options Data

```sql
CREATE TABLE options_oi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    expiry TEXT NOT NULL, strike REAL NOT NULL,
    call_oi REAL, put_oi REAL,
    call_iv REAL, put_iv REAL,
    call_volume REAL, put_volume REAL
);

CREATE TABLE gex_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    strike REAL NOT NULL,
    call_gex REAL, put_gex REAL, net_gex REAL,
    gamma_flip_price REAL
);

CREATE TABLE options_large_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    instrument TEXT, direction TEXT,
    amount REAL, price REAL, iv REAL, value_usd REAL
);
```

### 14.4 Signals & Performance

```sql
CREATE TABLE daily_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    btc_price REAL, fear_greed INTEGER, dvol REAL,
    put_call_ratio_oi REAL, put_call_ratio_volume REAL,
    regime TEXT, adx REAL, bb_width_percentile REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    final_score REAL, bias TEXT, strength TEXT, confidence TEXT,
    regime TEXT, event_risk REAL, consensus TEXT,
    spot_flow REAL, leverage_pos REAL, options_struct REAL, mean_reversion REAL,
    weights_json TEXT,
    btc_price_at_signal REAL,
    btc_price_4h_later REAL, btc_price_12h_later REAL,
    btc_price_24h_later REAL, btc_price_48h_later REAL,
    correct INTEGER,
    magnitude_24h_pct REAL
);

CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER REFERENCES signals(id),
    entry_timestamp TEXT, exit_timestamp TEXT,
    direction TEXT, entry_price REAL, exit_price REAL,
    stop_loss REAL, tp1 REAL, tp2 REAL, tp3 REAL,
    position_size_usd REAL, risk_pct REAL,
    pnl_usd REAL, pnl_pct REAL, r_multiple REAL,
    exit_reason TEXT
);

CREATE TABLE macro_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, time_utc TEXT NOT NULL,
    event TEXT NOT NULL, tier INTEGER NOT NULL,
    forecast REAL, actual REAL, previous REAL,
    surprise REAL, impact TEXT
);

CREATE TABLE ai_analysis_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    prompt_type TEXT NOT NULL,
    prompt_tokens INTEGER,
    response_tokens INTEGER,
    response_text TEXT,
    ai_bias TEXT,
    ai_confidence TEXT,
    ai_key_factor TEXT,
    ai_recommended_action TEXT,
    btc_price_at_analysis REAL,
    btc_price_24h_later REAL,
    ai_direction_correct INTEGER,
    quant_score_at_time REAL,
    quant_bias_at_time TEXT,
    ai_agreed_with_quant INTEGER,
    agreement_correct INTEGER,
    disagreement_who_right TEXT
);

CREATE TABLE level_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    level_price REAL NOT NULL,
    level_type TEXT NOT NULL,
    strength INTEGER NOT NULL,
    components TEXT,
    price_reached_zone INTEGER,
    zone_held INTEGER,
    price_at_test REAL,
    bounce_magnitude_pct REAL,
    break_magnitude_pct REAL
);
```

---

## 15. Backtesting Framework

### 15.1 Approach

Use Freqtrade's built-in backtesting engine for standard price-based strategies. For composite signal backtesting (which includes non-standard data like GEX), implement a custom walk-forward validator.

### 15.2 Walk-Forward Validation

```
Period 1:  Train days 1–60   → Test days 61–90
Period 2:  Train days 31–90  → Test days 91–120
Period 3:  Train days 61–120 → Test days 121–150
...
Window slides forward by 30 days each iteration.
Train period: 60 days. Test period: 30 days.
```

Only regime weights are optimized. All signal thresholds remain fixed to prevent overfitting.

### 15.3 Metrics Tracked

| Metric | Definition |
|---|---|
| Win rate | % of signals where price moved in predicted direction within 24h |
| Average R:R | Mean reward-to-risk ratio across all trades |
| Sharpe ratio | Risk-adjusted return |
| Max drawdown | Largest peak-to-trough decline |
| Signal accuracy by regime | Win rate segmented by STRONG_TREND, TIGHT_RANGE, etc. |
| Component contribution | Which composite signal contributed most to winning trades |

### 15.4 Immediate Backtestable vs. Forward-Only

| Signal Component | Backtestable? | Historical Data Available? |
|---|---|---|
| Signal 2 (Leverage) | ✅ Yes | Binance 6–12mo history |
| Signal 4 (Mean Reversion) | ✅ Yes | Binance klines, F&G full history |
| Signal 1 (Spot Flow - partial) | ⚠️ Klines yes, CVD no | CVD requires tick data (collect from now) |
| Signal 3 (Options) | ❌ Not immediately | Deribit has no free historical OI by strike |
| Signal 5 (Event Risk) | ⚠️ Partial | Macro calendar yes, liquidation history no |

**Recommendation:** Immediately backtest Signal 2 + Signal 4. Collect live data for Signals 1, 3, 5 starting from day one. Full system backtest possible after 3 months of collected data.

---

## 16. Performance Evaluation & Feedback Loop

The system must track every prediction it makes, compare against actual outcomes, and surface actionable insights about what works, what doesn't, and why. This is the mechanism that transforms a static system into one that improves over time.

### 16.1 Outcome Tracking — How Predictions Are Scored

Every time the signal engine produces a score, the system records the BTC price at that moment. A background job then fills in actual prices at fixed intervals afterward:

```
Signal generated at T:
  btc_price_at_signal = $65,700

Background job fills in later:
  T + 4h  → btc_price_4h_later  = $65,400
  T + 12h → btc_price_12h_later = $65,900
  T + 24h → btc_price_24h_later = $66,200
  T + 48h → btc_price_48h_later = $66,800
```

**Correctness Definition:**

A signal is "correct" if the price moved in the predicted direction by the relevant time horizon:

```
For bias = LONG:
  correct_4h  = (price_4h > price_at_signal)
  correct_12h = (price_12h > price_at_signal)
  correct_24h = (price_24h > price_at_signal)
  correct_48h = (price_48h > price_at_signal)

For bias = SHORT:
  correct_4h  = (price_4h < price_at_signal)
  ... (inverse)

For bias = NEUTRAL:
  correct_24h = (|price_24h - price_at_signal| / price_at_signal < 1%)
  (Neutral is "correct" if price stayed flat within 1%)

Primary metric: correct_24h (matches swing trade horizon)
Secondary: correct_48h (captures delayed moves)
```

**Magnitude Scoring — Beyond Binary Win/Loss:**

Binary correct/incorrect misses nuance. A STRONG LONG signal where price went up 5% is much better than one where price went up 0.1%. The system also tracks:

```
direction_magnitude_24h = (price_24h - price_at_signal) / price_at_signal × 100
  → If bias = LONG and magnitude = +3.2% → strong confirmation
  → If bias = LONG and magnitude = -1.5% → wrong, moderate loss

signal_quality_score = magnitude × sign(alignment)
  Where alignment = +1 if direction matches bias, -1 if opposite
  Range: unbounded, but typically [-5%, +5%]
```

### 16.2 Component-Level Accuracy — Which Signal Is Pulling Its Weight?

This is the most important tracking for improvement. The system evaluates each of the 4 directional composite signals independently:

```
For each signal snapshot:
  Record: spot_flow, leverage_pos, options_struct, mean_reversion
  Record: actual price change 24h later

Component accuracy (rolling 30 days):
  spot_flow_accuracy = correlation(spot_flow_scores, actual_24h_changes)
  leverage_accuracy  = correlation(leverage_scores, actual_24h_changes)
  options_accuracy   = correlation(options_scores, actual_24h_changes)
  mean_rev_accuracy  = correlation(mean_rev_scores, actual_24h_changes)
```

**Monthly Component Report:**

```
📊 COMPONENT PERFORMANCE — January 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Signal               Accuracy    Win Rate    Contribution
─────────────────────────────────────────────────────────
Spot Flow            0.42        63%         ████████░░ Strongest
Leverage Pos         0.31        58%         ██████░░░░ Good
Options Struct       0.18        52%         ███░░░░░░░ Weak
Mean Reversion       0.28        61%         █████░░░░░ Good

Insights:
• Options Structure underperforming — GEX assumption may
  be wrong more often this month (high fund selling)
• Spot Flow carrying the system — CVD divergence signals
  were particularly accurate
• Mean Reversion saved 3 trades from FOMO entries

Recommendation:
  Consider reducing Options weight by 5% and redistributing
  to Spot Flow until GEX accuracy improves.
```

This directly informs weight optimization — if a signal consistently underperforms, its weight should decrease.

### 16.3 Regime-Specific Performance

The same signal performs differently in different regimes. The system tracks accuracy segmented by regime:

```
                    STRONG_TREND  MODERATE_TREND  WIDE_RANGE  TIGHT_RANGE
────────────────────────────────────────────────────────────────────────
Overall Win Rate    65%           58%             52%         55%
Spot Flow           72%           60%             45%         48%
Leverage Pos        68%           62%             50%         52%
Options Struct      48%           55%             58%         65%
Mean Reversion      40%           52%             68%         72%
────────────────────────────────────────────────────────────────────────
n (sample size)     12            18              15          9
```

This validates (or invalidates) the adaptive weight allocation. If Mean Reversion shows 72% accuracy in TIGHT_RANGE but only 40% in STRONG_TREND, the current weight scheme (higher MR weight in range, lower in trend) is confirmed correct.

### 16.4 AI Analysis Accuracy Tracking

The AI analysis layer also needs evaluation. After each AI briefing, the system records:

```sql
CREATE TABLE ai_analysis_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    prompt_type TEXT NOT NULL,        -- 'daily_briefing', 'signal_change', 'macro_reaction', 'custom'
    prompt_tokens INTEGER,
    response_tokens INTEGER,
    response_text TEXT,

    -- Extracted predictions from AI response (parsed automatically)
    ai_bias TEXT,                     -- What direction did AI recommend?
    ai_confidence TEXT,               -- How confident was AI?
    ai_key_factor TEXT,               -- What did AI say was most important?
    ai_recommended_action TEXT,       -- 'enter_long', 'enter_short', 'wait', 'close'

    -- Outcome tracking (filled in 24h later)
    btc_price_at_analysis REAL,
    btc_price_24h_later REAL,
    ai_direction_correct INTEGER,     -- Did AI's directional call match reality?

    -- Comparison with quantitative signal
    quant_score_at_time REAL,
    quant_bias_at_time TEXT,
    ai_agreed_with_quant INTEGER,     -- Did AI agree with the numbers?
    agreement_correct INTEGER,        -- When they agreed, were they right?
    disagreement_who_right TEXT       -- When they disagreed, who was right? 'ai', 'quant', 'neither'
);
```

**Key Metrics from AI Tracking:**

```
AI vs. Quantitative Agreement Analysis (30 days):

  Times AI agreed with quant signal:     18/24 (75%)
  When they agreed → correct:            14/18 (78%) ← High confidence zone
  When they agreed → wrong:               4/18 (22%)

  Times AI disagreed with quant signal:   6/24 (25%)
  When AI was right, quant wrong:          3/6 (50%)
  When quant was right, AI wrong:          2/6 (33%)
  Both wrong:                              1/6 (17%)

Insight: When AI and quant system AGREE, confidence should be HIGH (78% hit rate).
When they DISAGREE, it's a genuine uncertainty zone — reduce position size.
```

This creates a **meta-confidence layer**: agreement between AI and quantitative signals becomes a signal in itself.

### 16.5 Confluence Zone Accuracy

Track whether identified support/resistance zones actually held:

```sql
CREATE TABLE level_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    level_price REAL NOT NULL,
    level_type TEXT NOT NULL,          -- 'support', 'resistance'
    strength INTEGER NOT NULL,         -- Number of confluences (3, 4, 5+)
    components TEXT,                   -- JSON: which levels formed the zone

    -- Outcome (filled in by background job)
    price_reached_zone INTEGER,        -- Did price actually test this zone?
    zone_held INTEGER,                 -- If tested, did it hold? (bounce/reject)
    price_at_test REAL,               -- Exact price when zone was tested
    bounce_magnitude_pct REAL,         -- How far did it bounce? (% from zone)
    break_magnitude_pct REAL           -- If broken, how far did it go? (% past zone)
);
```

**Monthly Confluence Report:**

```
📍 CONFLUENCE ZONE ACCURACY — January 2026

Strength    Zones    Tested    Held     Hold Rate
──────────────────────────────────────────────────
5+ levels   3        3         3        100%
4 levels    8        6         5        83%
3 levels    14       9         5        56%

Insight: 4+ confluence zones are highly reliable (85%+ hold rate).
3-level zones are barely better than random.

Recommendation: Raise minimum confluence threshold from 3 to 4
for trade entry consideration.
```

### 16.6 Automatic Weekly & Monthly Reports

**Weekly Report (every Monday 08:00 UTC via Telegram):**

```
📊 WEEKLY REVIEW — Week 4, Jan 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Signals generated: 12
Actionable (MODERATE+): 5
Trades taken: 3

Results:
  ✅ Win:  2 (avg +2.1R)
  ❌ Loss: 1 (avg -1.0R)
  Net: +3.2R (+$320 on $10k)

Best signal:  Spot Flow (+0.72 → price +3.8% in 24h)
Worst signal: Options Struct (-0.31 → price +1.2%, wrong)

Regime this week: MODERATE_TREND (5/7 days)
AI agreement rate: 80% (4/5 actionable signals)

🔧 SYSTEM NOTES:
• Coinglass response time degrading (avg 2.3s, was 0.8s)
• Options signal accuracy below average — reviewing GEX calc
```

**Monthly Report (1st of each month, also sent to AI for deeper analysis):**

The monthly report contains all metrics above, plus the full component accuracy breakdown and regime performance table. This monthly report is additionally sent to the AI Analysis Layer with a special prompt:

```
=== MONTHLY PERFORMANCE DATA ===
{full_monthly_stats}

=== QUESTION ===
You are reviewing one month of system performance. Based on the data:
1. Which signals are working well and which are underperforming?
2. Are the adaptive weights appropriate for recent market conditions?
3. Suggest specific parameter changes (with reasoning) to improve next month.
4. Are there patterns in the losing trades that the system should learn from?
5. Any structural issues or blind spots you notice?
```

Claude then generates an **AI improvement report** — essentially the system asking AI to audit itself. This is sent to the user, who decides whether to implement the suggested changes.

### 16.7 Feedback Loop — How Evaluation Drives Improvement

```
┌──────────────────────────────────────────────────────────┐
│                    FEEDBACK LOOP                          │
│                                                          │
│  Daily:                                                  │
│    Signal generated → Price recorded → 24h later:        │
│    outcome filled → correct/incorrect flagged            │
│                                                          │
│  Weekly:                                                 │
│    Aggregate daily outcomes → weekly report               │
│    Component accuracy updated → detect underperformers   │
│                                                          │
│  Monthly:                                                │
│    Full performance audit                                │
│    AI reviews performance data → suggests improvements   │
│    Component accuracy by regime → validate weight scheme │
│    Confluence zone accuracy → adjust thresholds          │
│                                                          │
│  Quarterly:                                              │
│    Walk-forward weight re-optimization                    │
│    Train on last 60 days → test on last 30               │
│    Only adjust: regime weights, NOT signal thresholds    │
│    Compare new weights vs old → adopt if improvement > 3%│
│                                                          │
│  What changes automatically:                             │
│    ✅ Nothing — all changes require human approval        │
│                                                          │
│  What the system RECOMMENDS changing:                    │
│    📋 Regime weight allocation                           │
│    📋 Confluence zone minimum strength threshold         │
│    📋 Signal component weights (within ±10% range)       │
│    📋 Confidence level definitions                       │
│                                                          │
│  What NEVER changes:                                     │
│    🔒 Risk per trade cap (2%)                            │
│    🔒 Leverage cap (3x)                                  │
│    🔒 Event risk STAY OUT threshold (0.8)                │
│    🔒 Signal suspension around macro events              │
│    🔒 Minimum R:R for entry (1.5:1)                      │
└──────────────────────────────────────────────────────────┘
```

**Critical design principle:** The system RECOMMENDS changes but NEVER auto-applies them. The user reviews the monthly AI report, decides which suggestions make sense, and manually updates configuration. This prevents the system from overfitting to recent data or drifting into dangerous territory.

### 16.8 Minimum Data Requirements

The evaluation metrics require minimum sample sizes to be statistically meaningful:

| Metric | Minimum Samples | Time to Accumulate |
|---|---|---|
| Overall win rate | 30 signals | ~2 months |
| Component accuracy | 30 signals | ~2 months |
| Regime-specific accuracy | 15 per regime | ~3–6 months |
| AI vs. quant agreement value | 20 disagreements | ~4–6 months |
| Confluence zone accuracy | 20 tested zones per strength | ~3 months |
| Weight re-optimization | 90 days of data | 3 months |

The system displays "insufficient data" warnings on any metric that hasn't reached minimum sample size, preventing premature conclusions.

### 16.9 Background Jobs for Outcome Tracking

```python
class OutcomeTracker:
    """
    Background job that fills in actual prices for past signals
    and computes correctness.
    Runs every 1 hour.
    """

    HORIZONS = {
        'btc_price_4h_later':  timedelta(hours=4),
        'btc_price_12h_later': timedelta(hours=12),
        'btc_price_24h_later': timedelta(hours=24),
        'btc_price_48h_later': timedelta(hours=48),
    }

    def run(self):
        """Fill in outcomes for signals that have matured."""
        current_price = self.get_current_price()
        current_time = datetime.utcnow()

        # Find signals missing outcome data
        pending = self.db.query("""
            SELECT id, timestamp, bias, btc_price_at_signal,
                   btc_price_4h_later, btc_price_12h_later,
                   btc_price_24h_later, btc_price_48h_later
            FROM signals
            WHERE btc_price_48h_later IS NULL
            AND timestamp > datetime('now', '-3 days')
        """)

        for signal in pending:
            signal_time = parse(signal['timestamp'])
            elapsed = current_time - signal_time

            for field, horizon in self.HORIZONS.items():
                if signal[field] is None and elapsed >= horizon:
                    # Fetch historical price at exact horizon time
                    target_time = signal_time + horizon
                    price = self.get_price_at_time(target_time)
                    self.db.update_signal(signal['id'], {field: price})

            # Compute correctness once 24h data available
            if signal['btc_price_24h_later'] is None and elapsed >= timedelta(hours=24):
                price_24h = self.get_price_at_time(signal_time + timedelta(hours=24))
                correct = self._evaluate_correctness(
                    signal['bias'],
                    signal['btc_price_at_signal'],
                    price_24h
                )
                magnitude = (price_24h - signal['btc_price_at_signal']) / signal['btc_price_at_signal'] * 100
                self.db.update_signal(signal['id'], {
                    'btc_price_24h_later': price_24h,
                    'correct': correct,
                    'magnitude_24h_pct': magnitude
                })

    def _evaluate_correctness(self, bias, price_at, price_after):
        if bias == 'LONG':
            return 1 if price_after > price_at else 0
        elif bias == 'SHORT':
            return 1 if price_after < price_at else 0
        else:  # NEUTRAL
            return 1 if abs(price_after - price_at) / price_at < 0.01 else 0
```

### 16.10 Performance Telegram Commands

| Command | Response |
|---|---|
| `/performance` | 30-day summary: win rate, total R, equity curve |
| `/performance week` | Last 7 days detailed breakdown |
| `/performance signals` | Component-level accuracy (which signal is best/worst) |
| `/performance regime` | Accuracy by market regime |
| `/performance ai` | AI vs. quantitative agreement analysis |
| `/performance levels` | Confluence zone hold rates |

---

## 17. Tech Stack & Dependencies

### 17.1 Core

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.11+ |
| Framework | Freqtrade | Latest stable |
| Exchange Library | CCXT | Latest (via Freqtrade) |
| Database | SQLite | 3.x (built-in) |
| Scheduler | APScheduler | 3.x |
| Notifications | python-telegram-bot | 20.x |

### 17.2 Data & Calculation

| Library | Purpose |
|---|---|
| pandas | Data manipulation |
| numpy | Numerical computation |
| pandas-ta | Technical indicators (RSI, EMA, BB, VWAP, ADX) |
| py_vollib | Black-Scholes options pricing (delta, gamma) |
| aiohttp | Async HTTP for custom API calls |
| fredapi | FRED API wrapper for macro data |

### 17.2.1 AI Analysis

| Library | Purpose |
|---|---|
| anthropic | Official Anthropic Python SDK for Claude API |

### 17.3 Dashboard (Phase 3)

| Library | Purpose |
|---|---|
| streamlit | Dashboard framework |
| plotly | Interactive charts |

### 17.4 Full requirements.txt

```
freqtrade
ccxt
pandas
numpy
pandas-ta
py_vollib
aiohttp
python-telegram-bot>=20.0
APScheduler>=3.0
fredapi
anthropic>=0.30.0
streamlit
plotly
```

---

## 18. Project Structure

```
crypto-signal-bot/
│
├── freqtrade/                     # Freqtrade installation
│   └── user_data/
│       ├── strategies/
│       │   └── composite_strategy.py    # Main strategy (extends IStrategy)
│       └── data/                        # Downloaded candle data
│
├── custom/                        # Custom modules (all new code)
│   ├── __init__.py
│   │
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── deribit_options.py           # Deribit OI, IV, volume
│   │   ├── coinglass.py                 # Liquidation data
│   │   ├── sentiment.py                 # Fear & Greed + proxy
│   │   └── macro_calendar.py            # Static calendar + FRED
│   │
│   ├── calculators/
│   │   ├── __init__.py
│   │   ├── greeks.py                    # Black-Scholes delta, gamma
│   │   ├── gex.py                       # GEX, gamma flip, max pain
│   │   ├── cvd.py                       # Cumulative Volume Delta
│   │   └── confluence.py                # Confluence zone finder
│   │
│   ├── signals/
│   │   ├── __init__.py
│   │   ├── spot_flow.py                 # Composite Signal 1
│   │   ├── leverage_positioning.py      # Composite Signal 2
│   │   ├── options_structure.py         # Composite Signal 3
│   │   ├── mean_reversion.py            # Composite Signal 4
│   │   ├── event_risk.py               # Signal 5 (modifier)
│   │   └── engine.py                    # Final score calculation
│   │
│   ├── regime/
│   │   ├── __init__.py
│   │   ├── detector.py                  # Market regime detection
│   │   └── adaptive_weights.py          # Weight engine + EMA smoothing
│   │
│   ├── trade_plan/
│   │   ├── __init__.py
│   │   ├── levels.py                    # Price level aggregation
│   │   ├── entry.py                     # Entry trigger logic
│   │   ├── sizing.py                    # Position sizing
│   │   └── exit.py                      # Stop loss + take profit
│   │
│   ├── output/
│   │   ├── __init__.py
│   │   ├── telegram_commands.py         # Custom /signal, /levels, /ai, etc.
│   │   ├── report_builder.py            # Format daily report
│   │   └── alert_manager.py             # Alert logic + cooldowns
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── prompt_builder.py            # Compile system data → prompt
│   │   ├── claude_analyzer.py           # API call + response parsing
│   │   └── system_prompt.txt            # Static system prompt for Claude
│   │
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── outcome_tracker.py           # Background job: fill in prices, score correctness
│   │   ├── component_accuracy.py        # Per-signal accuracy tracking
│   │   ├── regime_performance.py        # Accuracy by market regime
│   │   ├── level_accuracy.py            # Confluence zone hold rate tracking
│   │   ├── ai_accuracy.py              # AI vs quant agreement tracking
│   │   └── reports.py                   # Weekly/monthly report generator
│   │
│   └── utils/
│       ├── __init__.py
│       ├── health_monitor.py            # API health checks
│       ├── db.py                        # Database helpers
│       └── normalizers.py               # Z-score, clipping utilities
│
├── config/
│   ├── settings.py                      # API endpoints, tokens, thresholds
│   ├── macro_events_2026.json           # Annual macro calendar
│   ├── freqtrade_config.json            # Freqtrade configuration
│   └── .env                             # API keys (ANTHROPIC_API_KEY, etc.)
│
├── dashboard/
│   └── app.py                           # Streamlit dashboard (Phase 3)
│
├── data/
│   └── signals.db                       # SQLite database
│
├── tests/
│   ├── test_signals.py
│   ├── test_gex.py
│   ├── test_confluence.py
│   ├── test_ai_prompts.py
│   ├── test_evaluation.py
│   └── test_backtest.py
│
├── main.py                              # Entry point, scheduler
├── requirements.txt
├── Dockerfile                           # Optional containerization
└── README.md
```

**Total estimated custom code: ~2,600 lines** (excluding Freqtrade's ~100,000+ lines that come for free).

---

## 19. Deployment

### 19.1 Recommended: VPS

| Provider | Spec | Cost |
|---|---|---|
| Hetzner CX22 | 2 vCPU, 4GB RAM, 40GB SSD | €3.79/mo |
| Vultr Cloud Compute | 1 vCPU, 1GB RAM, 25GB SSD | $5/mo |
| DigitalOcean Droplet | 1 vCPU, 1GB RAM, 25GB SSD | $4/mo |
| Oracle Cloud Free Tier | 4 ARM cores, 24GB RAM | $0 (forever free) |

### 19.2 Setup Steps

```bash
# 1. Provision VPS (Ubuntu 24.04)
# 2. Install dependencies
sudo apt update && sudo apt install -y python3.11 python3-pip git
pip install --break-system-packages -r requirements.txt

# 3. Install Freqtrade
git clone https://github.com/freqtrade/freqtrade.git
cd freqtrade && pip install -e .

# 4. Configure
cp config/freqtrade_config.json.example config/freqtrade_config.json
# Edit: add Telegram token, exchange keys (if needed)

# 5. Initialize database
python -c "from custom.utils.db import init_db; init_db()"

# 6. Start bot
python main.py

# 7. (Optional) Set up as systemd service for auto-restart
sudo systemctl enable crypto-signal-bot
```

### 19.3 Monitoring

- **Process manager:** systemd (auto-restart on crash).
- **Logs:** Rotated daily, stored in `/var/log/crypto-signal-bot/`.
- **Health endpoint:** `/health` Telegram command shows all system metrics.
- **Alerting:** Telegram alert if bot itself is down (external uptime monitor like UptimeRobot, free tier).

---

## 20. Development Roadmap

| Week | Phase | Deliverable | Effort |
|---|---|---|---|
| 1 | Setup | Freqtrade installed, Binance connected, Telegram bot running | Low |
| 2 | Data Collection | Deribit collector, Coinglass, F&G, macro calendar. All data flowing to DB | ~400 LOC |
| 3 | Signal Engine | GEX calculator, 4 composite signal calculators, adaptive weights | ~800 LOC |
| 4 | Integration | Custom strategy class, Telegram commands, confluence zones, trade plan | ~400 LOC |
| 4–5 | AI Layer | Prompt builder, Claude API integration, /ai command, daily AI briefing | ~300 LOC |
| 5 | Evaluation | Outcome tracker, component accuracy, regime performance, level tracking, reports | ~500 LOC |
| 6 | Testing | Dry-run (paper trading), backtest Signal 2+4, tune thresholds + prompts | Testing |
| 7+ | Polish | Streamlit dashboard, AI monthly reviews, ongoing optimization | ~200 LOC |

**Total new code: ~2,600 lines over 7–8 weeks.**

Each week produces a **usable increment:**
- Week 1: Raw data report via Telegram (already useful as daily briefing).
- Week 2: Options data + GEX visible in reports.
- Week 3: Signal scores in reports.
- Week 4: Full trade plans with entry/exit + AI analysis.
- Week 5: System starts tracking its own accuracy.
- Week 6+: Validated, tuned system with performance data accumulating.

---

## 21. Limitations & Known Risks

### 21.1 Signal Accuracy Limitations

| Issue | Impact | Mitigation |
|---|---|---|
| GEX assumption (MM = net seller) | GEX may invert 20–30% of the time | Track GEX accuracy, reduce weight when wrong |
| Black swan events | All signals useless | Event risk module suspends signals |
| Market microstructure evolution | Patterns may decay over 6–12 months | Periodic weight re-optimization |
| Single-exchange CVD (Binance) | Incomplete spot flow picture | Add Bybit/OKX spot data later |
| Order book spoofing | False imbalance signals | Anti-spoof filter (cap extreme values) |
| Invisible whale activity (OTC, iceberg) | Whale signal misses smart whales | Accept as known blind spot |

### 21.2 Technical Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Binance API breaking change | Medium (1–2×/year) | Collector breaks | CCXT handles most changes; fallback to Bybit/OKX |
| Coinglass removes free tier | Medium | Lose liquidation data | Estimate from OI changes; pay $20–30/mo if needed |
| Alternative.me goes offline | Medium-High | Lose Fear & Greed | Self-calculated proxy function |
| Deribit API downtime | Low | Options signal offline | Score options signal as 0 (neutral) |
| VPS downtime | Low | Miss data + alerts | systemd auto-restart; daily health check |
| SQLite performance at scale | Low (years away) | Slow queries | Migrate to PostgreSQL if DB > 1GB |
| Anthropic API downtime/changes | Low | Lose AI analysis | System continues without AI layer; quantitative signals unaffected |
| AI hallucination in analysis | Low-Medium | Misleading narrative | System prompt constraints; AI is advisory only, never modifies signals |
| Anthropic pricing increase | Low | Higher monthly cost | Switch to smaller model; AI layer is optional and removable |

### 21.3 Expectation Setting

This system is a **decision support tool**, not a profit guarantee. Expected win rate of 55–60% means **40–45% of signals will be wrong**. The edge comes from:
1. Cutting losses small (1–2% risk per trade).
2. Letting winners run (1.5–2R target).
3. Avoiding bad trades (consensus check + event risk filtering).
4. Removing emotional decision-making.

A trader following the system with discipline should outperform their emotional trading, but **will still experience losing streaks** of 5–8 trades. This is statistically expected and not a system failure.

---

## 22. Appendix

### 22.1 Glossary

| Term | Definition |
|---|---|
| **GEX** | Gamma Exposure — measures the hedging obligation of options market makers |
| **Gamma Flip** | Price level where market maker positioning shifts from stabilizing to amplifying |
| **Max Pain** | Strike price where total options value is minimized at expiry |
| **CVD** | Cumulative Volume Delta — running sum of buyer vs. seller aggression |
| **IV Skew** | Difference between put and call implied volatility at same distance from ATM |
| **Confluence Zone** | Price area where 3+ independent support/resistance levels cluster |
| **ADX** | Average Directional Index — measures trend strength (not direction) |
| **Basis** | Difference between futures and spot price, often annualized |
| **Funding Rate** | Periodic payment between long and short futures holders |
| **DVol** | Deribit Volatility Index — crypto equivalent of VIX |

### 22.2 Signal Priority Hierarchy

When signals conflict: **Spot Flow > Futures Positioning > Options Structure > Mean Reversion > Sentiment**. This reflects the spectrum from hard data (actual money flow) to soft data (sentiment indices).

### 22.3 Key Thresholds Quick Reference

| Parameter | Value |
|---|---|
| Signal classification: no signal | \|score\| < 0.15 |
| Signal classification: weak | \|score\| 0.15–0.35 |
| Signal classification: moderate | \|score\| 0.35–0.60 |
| Signal classification: strong | \|score\| > 0.60 |
| Maximum risk per trade | 2% of portfolio |
| Maximum leverage | 3× |
| Minimum R:R for entry | 1:1.5 |
| Confluence zone threshold | ≥ 3 overlapping levels within ±0.5% |
| Confirmation entry requirement | ≥ 2 of 3 confirmations |
| Event risk "STAY OUT" threshold | event_risk > 0.8 |
| Signal suspension (macro) | 2h before Tier 1 event → 1h after |
| Weight smoothing factor | 0.3 (EMA) |
| Z-score normalization lookback | 30 days |
| Regime detection (ADX) period | 14 days |
| Walk-forward train window | 60 days |
| Walk-forward test window | 30 days |

---

*End of specification.*
