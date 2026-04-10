# Trading System Requirements

## Overview

A personal automated trading system built in Python, connected to Zerodha's Kite platform via the KiteConnect API. Designed for personal use — single-user, single-account.

---

## 1. Authentication & Session Management

- Authenticate with Zerodha Kite using KiteConnect API (API key + secret)
- Handle the OAuth login flow (browser-based redirect)
- Persist the access token across sessions to avoid re-login every run
- Auto-detect token expiry and prompt re-authentication
- Store credentials securely (env vars or encrypted config, not plaintext)

---

## 2. Market Data

### 2.1 Live Quotes
- Fetch real-time quotes for a watchlist of instruments
- Support NSE and BSE segments
- Data fields: LTP, OHLC, volume, bid/ask, OI (for F&O)

### 2.2 Historical Data
- Download historical OHLCV data for backtesting and analysis
- Configurable timeframe: 1min, 5min, 15min, 30min, 60min, day
- Support date-range queries
- Cache downloaded data locally to avoid redundant API calls

### 2.3 WebSocket Streaming (Live Feed)
- Subscribe to live tick data via KiteTicker
- Support LTP, quote, and full modes
- Reconnect automatically on disconnection
- Feed ticks into strategy engine in real time

---

## 3. Order Management

### 3.1 Order Placement
- Place market, limit, SL, and SL-M orders
- Support order types: regular, BO (bracket order), CO (cover order)
- Support exchange segments: NSE, BSE, NFO, MCX
- Support product types: CNC (delivery), MIS (intraday), NRML (F&O)

### 3.2 Order Lifecycle
- Modify open orders (price, quantity)
- Cancel open/pending orders
- Track order status: pending → open → complete / rejected / cancelled

### 3.3 Order Logging
- Log every order action with timestamp, instrument, type, quantity, price, and status
- Persist order log to disk (SQLite or CSV)

---

## 4. Portfolio & Position Tracking

- Fetch current holdings (long-term positions / CNC)
- Fetch intraday positions (MIS/NRML)
- Track unrealised and realised P&L
- Display net position per instrument

---

## 5. Strategy Engine

### 5.1 Strategy Interface
- Define a base `Strategy` class with standard hooks:
  - `on_tick(tick)` — called on each live tick
  - `on_candle(candle)` — called when a candle closes
  - `on_order_update(order)` — called on order status change
  - `generate_signals()` — produce buy/sell signals
- Allow multiple strategies to run simultaneously
- Strategies should be self-contained and configurable via parameters

### 5.2 Built-in Strategies (initial set)
- **RSI Mean Reversion** — buy oversold, sell overbought on NSE equities
- **Opening Range Breakout (ORB)** — trade breakout of first 15/30 min high/low
- Moving Average Crossover (SMA/EMA) — future consideration

### 5.3 Signal → Order Bridge
- Convert strategy signals into actual orders respecting risk controls
- Support paper trading mode (signals generated but no real orders placed)

---

## 6. Risk Management

- Starting capital: ₹20,000
- Max risk per trade: 1–2% of capital (₹200–₹400)
- Maximum number of open positions at any time (to be configured)
- Daily loss limit — halt trading if breached (e.g. 3% of capital = ₹600)
- Stop-loss enforcement: mandatory SL on every order
- Position sizing based on risk per trade (ATR-based optional, later)
- System initiates square-off at 3:15 PM IST; Zerodha's 3:20 PM auto square-off is the hard backstop

---

## 7. Backtesting

- Run strategies on historical data without live connectivity
- Simulate order fills (market orders fill at next candle open)
- Track equity curve, drawdown, win rate, Sharpe ratio
- Output a summary report per backtest run
- Allow parameter sweeping for optimisation (manual, not automated grid search initially)

---

## 8. Notifications & Alerts

- Telegram bot integration for:
  - Order placed / filled / rejected alerts
  - Daily P&L summary (end of day)
  - Risk limit breach alerts
  - System errors
- Optional: email alerts as fallback
- **Note:** Telegram integration to be implemented as a separate phase after core system is live

---

## 9. Scheduler & Automation

- Schedule strategy runs aligned to market hours (9:15 AM – 3:30 PM IST)
- Pre-market setup task (fetch instruments, warm up data cache)
- Post-market teardown task (square-off check, generate daily report)
- Configurable via cron or APScheduler

---

## 10. Data Storage

| Data | Storage |
|---|---|
| Historical OHLCV | Local SQLite or Parquet files |
| Tick data (optional) | Append-only CSV or SQLite |
| Orders & trades | SQLite |
| Config & credentials | `.env` file + `config.yaml` |
| Logs | Rotating log files |

---

## 11. Configuration

- Single `config.yaml` for all runtime parameters:
  - API credentials references (actual secrets in `.env`)
  - Watchlist of instruments
  - Strategy parameters
  - Risk limits
  - Notification settings
- Environment-specific overrides (dev / paper / live)

---

## 12. Logging & Monitoring

- Structured logging (timestamp, level, module, message)
- Separate log files per component (market data, orders, strategy)
- Log rotation to prevent unbounded disk usage
- CLI dashboard (optional, using `rich`) showing live positions and P&L

---

## 13. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Language | Python 3.11+ |
| Kite SDK | `kiteconnect` (official) |
| Latency (tick to signal) | < 500 ms |
| Reliability | Auto-restart on crash (systemd or supervisor) |
| Security | No credentials in source code or logs |
| Maintainability | Modular, one concern per module |
| Testing | Unit tests for strategy logic; integration tests mocked |

---

## 14. Deployment

- **Platform:** Local machine (Mac)
- **Static IP:** Owner to arrange a static IP on home/office internet connection
- **Process management:** launchd (Mac) or a simple shell script for auto-restart on crash
- **AWS deferred:** Cloud deployment not planned for now — can revisit if reliability or uptime becomes an issue

---

## 16. Interday (Positional/Swing) Trading

### Overview
A separate execution mode for holding positions overnight or across multiple days. Shares all core infrastructure with the intraday system — only config, entry point, and product type differ.

### Execution Model
- **Separate entry point:** `main_interday.py`
- **Separate config:** `config/config_interday.yaml`
- **Separate SQLite DB:** `data/market_interday.db` (avoids mixing candle timeframes)
- **Shared:** all `trader/` modules — auth, data, orders, risk, portfolio, notifications, backtest

### Key Differences from Intraday

| Concern | Intraday | Interday |
|---|---|---|
| Product type | MIS (auto sq-off) | CNC (delivery) |
| Candle timeframe | 5-minute | Daily |
| Square-off | 3:15 PM daily | None (hold until signal) |
| Daily P&L reset | Yes (post-market) | No (positions carry forward) |
| Risk — loss limit | Daily | Weekly / per-trade only |
| Strategies | RSI mean reversion, ORB | EMA crossover (initial) |
| Backtest reset | Per calendar day | Never (hold overnight) |

### Strategy
- **EMA Crossover (initial):** Fast EMA (9) / Slow EMA (21) on daily candles. Buy on golden cross, exit on death cross.
- Future: additional multi-day momentum and trend-following strategies

### Risk Management Adjustments
- No daily square-off enforced by the system (Zerodha CNC positions are never auto-closed)
- Per-trade SL still mandatory
- Weekly loss limit instead of daily (configurable)
- Position sizing same formula: `max_risk_per_trade ÷ SL distance`

### Scheduling
- Pre-market: warm up 1-year daily candle cache
- Post-market: refresh positions, log P&L — no reset of open positions
- No square-off job

---

## 18. Out of Scope (for now)

- Multi-user support
- Web UI / dashboard (beyond CLI)
- Options pricing / Greeks calculation
- Machine learning-based strategies
- Automated parameter optimisation
- HFT or sub-second latency requirements

---

## 19. Decisions

1. **Strategies (initial):** RSI mean reversion and Opening Range Breakout (ORB) — equities only (NSE), no F&O
2. **Paper trading:** 2 weeks, running in parallel with backtesting before going live
3. **Starting capital:** ₹20,000. Per-trade risk: 1–2% (₹200–₹400 max loss per trade)
4. **Telegram bot token:** Owner to set up via BotFather — deferred to notification phase
5. **Historical data storage:** Single unified SQLite DB with instrument column. Migrate to Parquet if performance degrades.
6. **Auto square-off:** System attempts square-off at 3:15 PM IST; Zerodha's 3:20 PM auto square-off acts as the hard backstop
