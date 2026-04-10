# Trading System — Enhancement Plan

## Overview

Phased enhancement plan for the existing trading system. Based on analysis of the original proposal against current system state. Items that are already implemented, overkill for this scale, or not needed (bhavcopy reconciliation, Parquet storage, adjusted price handling, corporate action calendar, AMO orders) have been dropped.

---

## What We Already Have (No Rebuild Needed)

| Item | Location |
|---|---|
| Realistic Zerodha cost model (MIS + CNC) | `trader/costs.py` |
| Backtest engine with equity curve, Sharpe, drawdown | `trader/backtest/engine.py` |
| Parameter calibration (random + grid search) | `trader/calibration/` |
| Paper trading mode | `trader/orders/manager.py` |
| ORB strategy (15-min range, breakout on close) | `trader/strategies/orb.py` |
| VWAP mean reversion strategy | `trader/strategies/vwap.py` |
| Per-trade SL enforcement | `trader/risk/manager.py` |
| Daily loss limit + trading halt | `trader/risk/manager.py` |
| Telegram alerts | `trader/notifications/telegram.py` |

---

## Phase 1 — Quick Wins (No Architecture Change)

All changes are targeted edits to existing files. No new strategy classes or registry changes needed.

### 1.1 ORB Signal Quality Filters
**File:** `trader/strategies/orb.py`

- **Volume filter:** Skip entry if first-15-min cumulative volume < 1.5× 20-day average of first-15-min volume. Reduces false breakouts on low-volume days.
- **Gap filter:** Skip entry if today's open is > 2% above/below previous close. Gap days have different breakout dynamics.

### 1.2 Regime Overlay
**File:** `trader/risk/manager.py`, `config/config.yaml`

- On each entry validation, check if NIFTY 50 price > its 200-day SMA.
- If NIFTY < 200 DMA → block all new entry signals (exit signals still pass through).
- If NIFTY drawdown from 52-week high > 15% → block all new entry signals.
- Config param: `regime_filter: enabled: true` with `index_symbol: NSE:NIFTY 50`.
- Data comes from existing historical data layer — no new data source needed.

### 1.3 ATR-Based Position Sizing
**File:** `trader/risk/manager.py`

- Current formula: `qty = max_risk_per_trade / sl_distance`
- New formula: `qty = (capital × risk_pct) / (2 × ATR_14)`, capped at `max_position_pct` (e.g. 8%) of capital
- ATR_14 passed in from strategy via signal metadata or computed in risk manager from cached candles
- Config params: `atr_multiplier: 2`, `max_position_pct: 8`

### 1.4 Signal Logging
**Files:** `trader/data/store.py`, `trader/risk/manager.py`

- Add a `signals` table to SQLite: `(timestamp, instrument, strategy, direction, signal_type, accepted, reject_reason)`
- `RiskManager.validate()` writes to this table on every signal — accepted or rejected with reason
- Enables post-session analysis of signal quality and rejection rates

### 1.5 Weekly Circuit Breaker (Intraday)
**File:** `trader/risk/manager.py`, `config/config.yaml`

- Track weekly realised P&L (reset every Monday)
- If weekly P&L falls below `-weekly_loss_limit_pct` of capital → set `_weekly_halted = True`
- `_weekly_halted` blocks new entries until next Monday reset
- Config param: `weekly_loss_limit_pct: 4.0` (intraday config only)
- `reset_day()` on Monday resets weekly counter; `reset_day()` other days leaves it intact

---

## Phase 2 — New Strategy + Trailing Stop

### 2.1 VWAP Pullback Continuation
**File:** `trader/strategies/vwap_pullback.py` (new), `trader/strategies/registry.py`, `trader/calibration/param_space.py`, `config/config.yaml`

Different from existing `vwap.py` (mean reversion). This is a trend-continuation entry:

- **Pre-conditions:** Stock is above its 50-period SMA (daily or intraday) AND 1-month return > 0
- **Entry trigger:** Price is above VWAP → pulls back to touch VWAP → next candle closes bullish and resumes upward
- **Entry:** Buy on break of pullback candle high
- **Exit:** Price closes below VWAP (loss of trend support)
- Config params: `sma_period`, `vwap_touch_tolerance_pct`

### 2.2 Chandelier Trailing Stop (Interday)
**Files:** `trader/backtest/engine.py`, `trader/risk/manager.py`

- Current: SL is set at entry and never moves
- New: For interday (CNC) trades, SL trails as `highest_close_since_entry − chandelier_multiplier × ATR_22`
- Backtest engine: update `trade.stop_loss` each candle using the trailing formula (currently SL is static)
- Risk manager: track `_highest_close` per open position, update SL on each `on_candle` call
- Config param: `trailing_stop: chandelier`, `chandelier_period: 22`, `chandelier_multiplier: 3.0`
- Intraday trades keep the existing fixed SL behavior

---

## Phase 3 — Architecture Extension

### 3.1 Lightweight Universe Manager
**File:** `trader/universe/manager.py` (new)

- Maintain a list of NIFTY 200 constituents (stored as a static CSV, updated monthly)
- Daily ADTV filter: compute 20-day average daily volume × close for each symbol; exclude if < ₹5 crore (interday) or < ₹25 crore (intraday)
- Data source: existing Kite historical API — no new integrations
- `get_universe(mode)` returns filtered symbol list; called by scheduler pre-market
- `config_interday.yaml` / `config.yaml` watchlists become dynamically populated from this

### 3.2 Cross-Sectional Momentum (Interday)
**Files:** `trader/strategies/momentum_ranker.py` (new), `trader/scheduler/jobs.py`, `config/config_interday.yaml`

Architecture note: this is a portfolio-level strategy, not a per-symbol `on_candle` strategy. It runs once post-close.

- **Score:** `0.5 × R_6M + 0.3 × R_12M + 0.2 × R_3M`, excluding last 5 trading days
- **Trend filter:** Only rank stocks with price > 200 DMA
- **Selection:** Top 15 by score, equal weight
- **Rebalance:** Last Friday of each month
- **Exits:** 2× ATR SL from entry; Chandelier trailing stop (from Phase 2); hard exit if stock falls out of top 30 on rebalance
- **Scheduler job:** Post-close job calls `MomentumRanker.generate_rebalance()` → produces BUY/SELL signals → passes through RiskManager → OrderManager
- **Sizing:** ATR-based from Phase 1.3, capped at 8% per position

### 3.3 Walk-Forward Backtest
**File:** `scripts/calibrate.py`, `trader/calibration/runner.py`

- Add `--walk-forward` flag to `calibrate.py`
- Splits date range into overlapping windows: train N years, test 1 year, roll forward 1 year
- Reports in-sample vs out-of-sample metrics side by side
- Acceptance criteria before going live: Sharpe > 1.0 net of costs, max DD < 20% (interday) / < 10% (intraday), profit factor > 1.4, minimum 100 trades in test window

---

## Deferred / Out of Scope

| Item | Reason |
|---|---|
| NSE bhavcopy reconciliation | Kite API data reliable enough; complexity not justified |
| Parquet storage | SQLite sufficient at this scale |
| Adjusted vs unadjusted prices | Kite historical API already serves adjusted data |
| Corporate action calendar | Complex; regime overlay + universe ADTV filter partially mitigates |
| AMO orders | Defer until live interday validated in paper mode |
| Point-in-time survivorship-free universe | Correct in theory; historical constituent data hard to source |
| Multi-account / client money | Out of scope permanently |

---

## Implementation Notes

- All Phase 1 changes are additive/backward-compatible — no breaking changes to existing strategy interface
- Phase 2 trailing stop changes the `TradeRecord` update loop in backtest engine — needs careful testing
- Phase 3 momentum ranker introduces a new execution model (portfolio rebalance vs per-candle signal); keep it decoupled from the existing per-symbol strategy engine
- Paper trade each phase for minimum 2 weeks before enabling live orders
- Run `.venv/bin/pytest tests/ -q` after each phase
