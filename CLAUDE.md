# Crypto Signal Bot

## What is this?
A decision support tool for a solo BTC/USDT swing trader. It collects data from spot, futures, and options markets, computes 5 composite directional signals with adaptive regime-based weights, and delivers actionable trade plans via Telegram. Built on Freqtrade framework with custom signal modules. NOT an auto-trading bot.

## Architecture
- **Language:** Python 3.11+
- **Framework:** Freqtrade (exchange connectors, Telegram bot, backtesting, WebUI)
- **Database:** SQLite (migration path to PostgreSQL if >1GB)
- **Scheduler:** APScheduler
- **AI Layer:** Claude API (Anthropic SDK) for narrative analysis
- **Dashboard:** React + TailwindCSS + TradingView Lightweight Charts (FastAPI backend)
- **Deployment:** VPS ($5/mo), all APIs free tier

## Spec-Driven Development
- `docs/crypto-signal-bot-spec.md` ← Full master specification
- `docs/PRD.md`                    ← Condensed spec reference
- `docs/plan.md`                   ← Living implementation plan
- `docs/sub-specs/`               ← One detailed file per module

### Rules
1. Read the sub-spec before implementing any module
2. Never invent requirements — ask if unclear
3. Docstrings must reference sub-spec: `"""See docs/sub-specs/SS-XX.md §Y.Y"""`
4. Test names map to acceptance criteria, not implementation details
5. Config over hardcode — all thresholds go in `config/settings.yaml`, never in source code

## Project Structure
```
crypto-signal-bot/
├── CLAUDE.md                          # This file
├── main.py                            # Entry point, scheduler
├── requirements.txt
├── Dockerfile
├── .env.example
│
├── freqtrade/user_data/
│   ├── strategies/
│   │   └── composite_strategy.py      # Main strategy (extends IStrategy)
│   └── data/                          # Downloaded candle data
│
├── custom/                            # All custom modules
│   ├── api/                           # FastAPI web dashboard (REST + WebSocket)
│   ├── collectors/                    # Data fetchers (Deribit, Coinglass, FRED, F&G)
│   ├── calculators/                   # Greeks, GEX, CVD, confluence zones
│   ├── signals/                       # 5 composite signals + engine
│   ├── regime/                        # Market regime detection + adaptive weights
│   ├── trade_plan/                    # Levels, entry triggers, sizing, exits
│   ├── output/                        # Telegram commands, reports, alerts
│   ├── ai/                            # Claude API prompt builder + analyzer
│   ├── evaluation/                    # Outcome tracking, accuracy, reports
│   └── utils/                         # DB helpers, health monitor, normalizers
│
├── config/
│   ├── settings.yaml                  # All thresholds and tunable parameters
│   ├── macro_events_2026.json         # Annual macro calendar
│   └── freqtrade_config.json          # Freqtrade configuration
│
├── data/
│   └── signals.db                     # SQLite database
│
├── frontend/                          # React + TypeScript dashboard
│   ├── src/                           # React components, pages, hooks
│   └── dist/                          # Built static files (gitignored)
│
├── tests/                             # All tests
└── docs/                              # Specs, PRD, plan, sub-specs
```

## Code Standards
- **Type hints:** Required on all function signatures
- **Async:** Use `async/await` for all HTTP calls (aiohttp)
- **Logging:** Use Python `logging` module, never `print()`
- **Formatting:** Follow PEP 8, use `black` formatter
- **Naming:** snake_case for functions/variables, PascalCase for classes
- **Signal scores:** Always `float` in range `[-1.0, +1.0]`, use `numpy.clip()`
- **Error handling:** Log + neutralize (score=0) on data source failure, never crash
- **Docstrings:** Google-style, reference sub-spec section
- **Constants:** Define in `config/settings.yaml`, load via config module

## Key Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python main.py

# Run tests
pytest tests/ -v

# Syntax check
python -m py_compile custom/**/*.py

# Freqtrade backtesting
freqtrade backtesting --strategy CompositeStrategy --timerange 20260101-

# Frontend development
cd frontend && npm run dev

# Build frontend
cd frontend && npm run build
```

## Custom Slash Commands
- `/spec SS-XX` — Analyze sub-spec, generate implementation spec
- `/implement SS-XX` — Implement a sub-spec module with tests
- `/test SS-XX` — Write tests from acceptance criteria
- `/verify SS-XX` — Verify implementation against sub-spec
- `/new-subspec SS-XX` — Create a new sub-spec from master spec
- `/status` — Show project progress and test results
- `/handover` — Summarize session for continuity

## Memory & Context Management
1. **CLAUDE.md** — Always loaded, project overview and rules
2. **`.claude/settings.json`** — Permissions and hooks
3. **`.claude/commands/`** — 7 reusable slash commands
4. **Auto memory** — Session insights saved to `.claude/memory/`

### Guidelines
- Read the relevant sub-spec before implementing (keeps context focused)
- Don't read the full master spec unless doing cross-module analysis
- Use `/status` to orient yourself at session start
- Use `/handover` before ending a session

## Proactive Messaging & Subscribers
- **Subscriber system:** `subscribers` table in SQLite, managed via `/adduser`, `/removeuser`, `/subscribers` (admin-only commands)
- **Admin:** Determined by `TELEGRAM_CHAT_ID` env var; auto-added as subscriber on startup
- **Thread-to-event-loop bridge:** Scheduler (APScheduler, background thread) sends messages via `broadcast_sync()` → `asyncio.run_coroutine_threadsafe()` → bot's event loop
- **Proactive jobs:**
  - Signal report: every 4h (configurable via `telegram.signal_report_interval_hours`)
  - Alert check: every 2min (configurable via `telegram.alert_check_interval_seconds`)
  - Daily report: 08:05 UTC (5min after daily data collection; configurable via `telegram.daily_report_utc_hour`)
- **Message splitting:** Messages >4096 chars auto-split at newline boundaries
- **Startup order:** Create bot → start scheduler (with bot ref) → inject health_monitor/scheduler → auto-add admin subscriber → bot.start()

## Important Constraints (NEVER CHANGE)
- **Risk per trade cap:** 2% of portfolio (IMMUTABLE)
- **Leverage cap:** 3x (HARD LIMIT)
- **Event risk STAY OUT threshold:** 0.8 (IMMUTABLE)
- **Signal suspension:** 2h before Tier 1 macro event → 1h after (IMMUTABLE)
- **Minimum R:R for entry:** 1.5:1 (IMMUTABLE)
- **AI is advisory only:** AI output NEVER modifies signal scores or triggers trades
- **All system changes require human approval:** No auto-optimization
- **Signal score range:** Always [-1.0, +1.0] for directional, [0, 1.0] for event risk
- **Claude API rate limit:** Maximum 10 calls/day
