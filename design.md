# Trading System — Design & Architecture

## 1. Overview

The system is a personal, single-user automated trading application for NSE equities, connected to Zerodha via the KiteConnect API. It runs locally on a Mac, executes multiple intraday and interday strategies, enforces strict risk controls before placing any real order, and includes a parameter calibration framework for optimising strategy parameters via backtest.

The design is deliberately simple and modular — each concern lives in its own module, modules communicate through well-defined interfaces, and no module reaches into another's domain directly.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              main.py  (unified entry point)                 │
│   python main.py                    → intraday (MIS)        │
│   python main.py --config ...       → interday (CNC)        │
└────────────┬───────────────────────────────────┬────────────┘
             │                                   │
    ┌────────▼────────┐                 ┌────────▼────────┐
    │   Scheduler     │                 │   Auth/Session  │
    │  (APScheduler)  │                 │  (Kite token)   │
    └────────┬────────┘                 └────────┬────────┘
             │                                   │
    ┌────────▼────────────────────────────────────▼────────┐
    │                    KiteConnect API                    │
    │          (REST for orders/data, WS for ticks)         │
    └────┬──────────────────┬──────────────────┬───────────┘
         │                  │                  │
┌────────▼──────┐  ┌────────▼──────┐  ┌───────▼────────┐
│  data/live.py │  │data/historical│  │ orders/manager │
│  (KiteTicker) │  │  + store.py   │  │                │
└────────┬──────┘  └───────────────┘  └───────▲────────┘
         │  ticks                              │ orders
┌────────▼──────────────────────┐    ┌────────┴────────┐
│       Strategy Engine         │───▶│  Risk Manager   │
│  (base + RSI + ORB instances) │    │                 │
└───────────────────────────────┘    └─────────────────┘
```

---

## 3. Component Design

### 3.1 `core/` — Foundation

Two modules that every other component imports. Initialised first, before anything else.

**`core/config.py`**
- Loads `config.yaml` and merges with `.env` (via `python-dotenv`)
- Exposes a single `Config` object accessible everywhere via `config` singleton; `CONFIG_FILE` path exported
- Config file selected by `TRADER_CONFIG` env var (set before any trader import); defaults to `config/config.yaml`
- Validates required fields on startup (fail fast if API key is missing)

**`core/logger.py`**
- Configures Python's standard `logging` with rotating file handlers
- One log file per major component: `orders.log`, `strategy.log`, `data.log`, `system.log`
- All modules get a logger via `logger.get_logger(__name__)`

---

### 3.2 `auth/session.py` — Authentication

Kite issues a fresh access token daily via a browser-based OAuth flow. This module handles that.

- On startup, loads the stored access token from `.env` / token file
- Checks if the token is still valid (Kite tokens expire at midnight)
- If expired: raises an error prompting the user to run `scripts/login.py`
- `scripts/login.py` opens the browser login URL, captures the request token, exchanges it for an access token, and saves it

**Token storage:** written to a local `.token` file (gitignored), loaded into the `KiteConnect` instance at startup.

---

### 3.3 `data/` — Market Data

Three distinct responsibilities:

**`data/store.py` — SQLite interface**
- Single DB file: `data/market.db`
- Tables:
  - `candles(instrument, timeframe, timestamp, open, high, low, close, volume)`
  - `orders(order_id, instrument, type, qty, price, status, timestamp)`
  - `trades(trade_id, order_id, instrument, qty, price, timestamp)`
- Provides `read_candles()`, `write_candles()`, `upsert_order()` — no raw SQL outside this module

**`data/historical.py` — OHLCV fetch & cache**
- Fetches historical candles from Kite REST API
- Checks local DB first; only fetches missing date ranges from API
- Normalises and stores results via `store.py`
- Used by both backtesting and live strategy warm-up

**`data/live.py` — WebSocket tick feed**
- Wraps `KiteTicker`
- Subscribes to instruments in the watchlist on connect
- On each tick: calls `on_tick(tick)` on all registered strategy instances
- Reconnects automatically on disconnection (KiteTicker handles this natively)
- Also responsible for assembling ticks into completed candles and calling `on_candle(candle)` on strategies

---

### 3.4 `strategies/` — Strategy Engine

**`strategies/base.py` — Abstract base class**

```python
class Strategy(ABC):
    def on_tick(self, tick: dict) -> None: ...
    def on_candle(self, candle: dict) -> Signal | None: ...
    def on_order_update(self, order: dict) -> None: ...
    def confirm_entry(self, direction) -> bool: ...   # optional — filter role
```

- `Signal` is a dataclass: `(instrument, direction=BUY|SELL, signal_type=ENTRY|EXIT, price_hint)`
- Strategies do not place orders — they emit signals only
- Each strategy instance is configured with its own parameters from `config.yaml`
- Strategies maintain their own internal state (e.g. current RSI value, opening range high/low)

**`strategies/registry.py` — Single source of truth**
- `STRATEGY_CLASSES`: maps config key → class for all 10 strategies
- `FILTER_ONLY`: set of strategy names that only implement `confirm_entry()` and never emit signals (e.g. `adx`)
- `GROUP_COMPOSITIONS`: maps group config key → (primary strategy key, [filter keys])
- `build_strategies(symbol, config) -> list[Strategy]`: the one function all entry points call — no strategy logic in main.py, backtest.py, or calibrate.py

**`strategies/group.py` — StrategyGroup**
- `StrategyGroup(primary, filters)`: AND-logic combination layer
- ENTRY signals from primary are forwarded only if all filters return `True` from `confirm_entry()`
- EXIT signals always pass through unconditionally
- Each filter's `on_candle()` runs every bar to keep indicator state current

**Intraday strategies (5-minute candles, MIS)**

- `rsi.py` — RSI Mean Reversion: BUY when RSI crosses below `oversold`, SELL above `overbought`, exit at midpoint
- `orb.py` — Opening Range Breakout: establishes high/low from first N minutes (configurable), trades first breakout
- `vwap.py` — VWAP Reversion: enters when price deviates from VWAP by a configurable %, exits on mean reversion
- `supertrend.py` — Supertrend ATR-based trend filter: `confirm_entry()` checks trend direction; also usable standalone
- `bollinger.py` — Bollinger Band mean reversion: enters near bands, exits at midpoint
- `ema_pullback.py` — EMA Pullback in uptrend: enters on pullbacks to fast EMA when fast > slow

**Interday strategies (daily candles, CNC)**

- `ema_crossover.py` — EMA Crossover: BUY on golden cross (fast > slow), EXIT on death cross
- `rsi_ema.py` — RSI + EMA combo: RSI oversold + price above EMA for entry
- `breakout.py` — 52-week high breakout with configurable trailing stop
- `adx.py` — ADX trend strength filter: `confirm_entry()` only; `FILTER_ONLY` — never used standalone

**Strategy groups (AND-logic combos)**

- `orb_supertrend`: ORB primary + Supertrend filter (intraday)
- `rsi_bollinger`: RSI primary + Bollinger filter (intraday)
- `ema_adx`: EMA Crossover primary + ADX filter (interday)

---

### 3.5 `risk/manager.py` — Risk Management

Sits between strategy signals and the order manager. Every signal must pass through here before becoming an order.

Responsibilities:
- **Position sizing:** calculates quantity based on `max_risk_per_trade` and the SL distance
- **Daily loss limit:** tracks realised + unrealised P&L; halts all new entries if limit breached (₹600 default)
- **Max open positions:** rejects new entry signals if already at the limit
- **SL enforcement:** attaches a stop-loss price to every order; no order goes out without one
- **Square-off trigger:** at 3:15 PM, emits EXIT signals for all open positions regardless of strategy state

Paper trading mode: risk manager runs all checks but passes signals to a paper order simulator instead of the real order manager.

---

### 3.6 `orders/manager.py` — Order Management

Interfaces with Kite's order API.

- Places, modifies, and cancels orders via KiteConnect REST
- Tracks order lifecycle: `PENDING → OPEN → COMPLETE / REJECTED / CANCELLED`
- Persists every order and status update to `store.py`
- Exposes an `on_order_update(order)` callback (called by the order update WebSocket feed) which propagates updates to the active strategy

**Paper trading mode:** order placement calls are intercepted and simulated — fills are assumed at the next candle's open price.

---

### 3.7 `portfolio/tracker.py` — Portfolio & Positions

- Fetches current holdings and intraday positions from Kite on demand
- Tracks unrealised and realised P&L in memory (refreshed each candle)
- Provides position state to `risk/manager.py` for open position count and P&L checks

---

### 3.8 `backtest/engine.py` — Backtesting

Runs strategies against historical data without any live connectivity.

- Replays candles from `data/historical.py` in chronological order
- Calls `on_candle()` on strategy instances exactly as the live feed does
- Simulates fills: market orders fill at the next candle's open; limit orders fill if price is reached
- Tracks equity curve, per-trade P&L, max drawdown, win rate, Sharpe ratio
- **Transaction costs:** deducts real Zerodha charges (brokerage, STT, NSE transaction charges, SEBI charges, GST, stamp duty) from every trade's P&L via `trader/costs.py`
- Outputs a summary report showing gross P&L, transaction costs, net P&L, and net P&L % of capital
- `save_trades()` exports CSV with `gross_pnl`, `costs`, `net_pnl` columns
- Shares the same strategy code as live trading — no separate backtest strategy class
- `reset_daily=True` resets daily P&L between calendar days (intraday); set `False` for interday backtests

---

### 3.9 `scheduler/jobs.py` — Automation

Uses APScheduler to run tasks on a market-hours schedule (IST).

| Time | Job |
|---|---|
| 9:00 AM | Pre-market: warm up candle cache for active symbols and timeframes |
| 3:15 PM | Square-off: exit all open positions (MIS / `square_off_enabled` only) |
| 3:35 PM | Post-market: log portfolio summary, send Telegram P&L report, reset daily risk state |

- Square-off job is only registered when `config.square_off_enabled = true` (intraday MIS mode)
- Post-market resets `risk.reset_day()` always; additionally calls `risk.reset_positions()` for MIS only
- Pre-market warmup timeframes: `["5minute", "day"]` for intraday, `["day"]` for interday — derived from `config.candle_minutes`

---

### 3.10 `notifications/telegram.py` — Alerts

Fire-and-forget Telegram notifications. Skips silently if `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` are absent from `.env`.

Implemented events:
- System startup (mode, watchlist, strategy count)
- Order filled (instrument, direction, qty, fill price, strategy name)
- Order rejected (instrument, direction, reason)
- Daily P&L summary (realised, unrealised, trade count, net % of capital)
- Daily loss limit breached / trading halted

### 3.11 `costs.py` — Transaction Cost Calculator

Computes all Zerodha charges for equity trades. Used by the backtest engine to produce realistic net P&L.

- `order_cost(product, side, quantity, price)` — per-leg charges
- `round_trip_cost(product, quantity, entry_price, exit_price)` — entry + exit combined
- MIS: brokerage = min(0.03% × turnover, ₹20), STT = 0.025% sell-side, stamp = 0.003% buy-side
- CNC: brokerage = ₹0, STT = 0.1% both sides, stamp = 0.015% buy-side
- Both: NSE transaction charges 0.00307%, SEBI charges ₹10/crore, GST 18% on applicable fees

### 3.12 `calibration/` — Parameter Optimisation

Finds optimal strategy parameters by running backtests across a search space.

- `calibration/param_space.py` — `PARAM_SPACES` dict: candidate values for every strategy parameter; pure data, no trader imports
- `calibration/runner.py` — `CalibrationRunner`: runs random or grid search, aggregates metrics across symbols, ranks results
- `scripts/calibrate.py` — CLI entry point: `--strategy`, `--from`, `--to`, `--iterations`, `--metric`, `--mode`, `--update-config`
- Supported metrics: `sharpe` (default), `total_pnl`, `win_rate`, `max_drawdown`
- `--update-config` writes best params back to the active config YAML file
- Requires candle data already cached in SQLite — run `main.py` or `scripts/backtest.py` first

---

## 4. Data Flow — Live Trading

```
KiteTicker tick
    └─▶ data/live.py
            ├─▶ strategy.on_tick(tick)          # tick-level strategies
            └─▶ [candle assembled]
                    └─▶ strategy.on_candle(candle)
                                └─▶ signal = strategy.generate_signal()
                                        └─▶ risk/manager.validate(signal)
                                                └─▶ orders/manager.place(order)
                                                        └─▶ Kite REST API
                                                        └─▶ data/store.py (log)
```

Order status updates flow back via a separate Kite WebSocket:
```
Kite order update WS
    └─▶ orders/manager.on_order_update(order)
            ├─▶ data/store.py (persist)
            └─▶ strategy.on_order_update(order)  # strategy updates internal state
```

---

## 5. Data Flow — Backtesting

```
data/historical.py (loads candles from SQLite)
    └─▶ backtest/engine.py (replays candle by candle)
            └─▶ strategy.on_candle(candle)
                    └─▶ signal returned
                            └─▶ risk.validate(signal)
                                    └─▶ backtest/engine.py simulates fill at next open
                                            └─▶ costs.round_trip_cost() deducted
                                            └─▶ equity curve updated
```

---

## 6. Modes of Operation

Controlled by `env` field in `config.yaml`:

| Mode | Description |
|---|---|
| `development` | No live feed, no orders. Load historical data, run backtests. |
| `paper` | Live feed active, strategies run, orders simulated (no real money). |
| `live` | Full system. Real orders placed via Kite. |

`main.py` reads the mode at startup and wires components accordingly.

---

## 7. Key Design Principles

- **Strategies are signal-only.** They never call the order manager directly. This makes them testable in isolation and reusable in both backtest and live modes.
- **Risk manager is the single gatekeeper.** No order is placed without passing through it. This ensures risk rules are never bypassed.
- **Same strategy code in backtest and live.** The `on_candle` interface is identical; only the data source and order executor differ.
- **Fail fast on startup.** Missing credentials, invalid config, or expired token should abort immediately with a clear error — not fail silently mid-session.
- **No credentials in code or logs.** API keys and tokens are read from `.env` only; log formatters must not print sensitive fields.

---

## 8. Data Sources

All market data comes exclusively from Zerodha Kite:

| Data | Kite API | Notes |
|---|---|---|
| Live tick feed | KiteTicker WebSocket | Real-time, used in paper and live modes |
| Historical OHLCV | REST `/instruments/historical` | Cached locally in SQLite after first fetch |
| Instrument list | REST `/instruments` | Fetched pre-market, cached for the session |
| Order updates | KiteTicker WebSocket (order channel) | No postback URL needed |

Single session, single integration — no external data providers.

---

## 9. Technology Choices

| Concern | Choice | Reason |
|---|---|---|
| Kite connectivity | `kiteconnect` (official SDK) | Maintained by Zerodha, handles WS reconnect |
| Config | `pyyaml` + `python-dotenv` | Simple, no overhead |
| Scheduling | `APScheduler` | Lightweight, in-process, no external daemon needed |
| Storage | SQLite (`sqlite3` stdlib) | Zero setup, sufficient for this scale |
| Data manipulation | `pandas` | Industry standard for OHLCV work |
| Logging | Python stdlib `logging` | No extra dependency; rotating file handler built-in |
| Notifications | `requests` for Telegram HTTP API | Minimal dependency |
