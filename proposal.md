# Systematic Trading Platform — Enhancement Proposal

## 1. Objective

Extend the existing Python trading platform to support two complementary modes on Indian equities (NSE):

1. **Interday swing trading** — portfolio-level systematic momentum, holding days to weeks, decisions made post-close, orders placed as AMO or at next-day open.
2. **Intraday swing trading** — single-session directional trades on liquid largecaps/F&O stocks, entered after the opening range and exited by 3:15 PM, no overnight exposure.

Both modes must share infrastructure (data, risk, execution, logging) but run as independent strategy tracks with separate capital buckets.

---

## 2. Capital Allocation Between Tracks

- Interday swing: 70% of capital
- Intraday swing: 20% of capital
- Cash buffer: 10% (for margin spikes, drawdown reserve)

Each track has its own drawdown kill-switch independent of the other.

---

## 3. Shared Infrastructure to Build

### 3.1 Universe Manager
- Maintain point-in-time NIFTY 200 / NIFTY 500 / F&O list
- Daily refresh from NSE bhavcopy + index constituent files
- Exclusion filters applied centrally:
  - T2T, GSM, ASM stage 2+
  - Within 5% of circuit limits
  - ADTV < ₹5 crore (interday), < ₹25 crore (intraday)
  - Pending corporate actions in next 5 trading days

### 3.2 Data Layer
- Daily bars: from broker API + NSE bhavcopy reconciliation
- Minute bars (1m, 5m, 15m): only for intraday universe (~150 stocks), stored in Parquet partitioned by date
- Adjusted vs unadjusted prices kept separate; backtests use adjusted, live orders use unadjusted
- Corporate action calendar maintained as a separate table

### 3.3 Risk & Order Layer (shared)
- Per-trade risk cap, per-track drawdown cap, portfolio gross exposure cap
- Idempotent order placement keyed by `(strategy_id, signal_date, symbol)`
- Order state machine: PENDING → PLACED → FILLED/PARTIAL/REJECTED → RECONCILED
- All rejections logged with reason

### 3.4 Logging & Post-Trade Analytics
- Signal log (generated, accepted, rejected + reason)
- Order log (placed, filled, slippage vs expected)
- Daily PnL attribution by strategy and by symbol
- Weekly auto-generated report

---

## 4. Interday Swing Module

### 4.1 Strategy: Cross-Sectional Momentum Core
- Universe: NIFTY 200, post-filters
- Score: `0.5 * R_6M + 0.3 * R_12M + 0.2 * R_3M`, skip most recent 5 trading days
- Trend filter: only stocks with price > 200 DMA
- Select top 15, equal weight, monthly rebalance (last Friday)
- Hold until exit signal or rebalance

### 4.2 Position Sizing
- ATR-based: `qty = (capital_per_track * 0.01) / (2 * ATR_14)`
- Cap any single position at 8% of track capital

### 4.3 Exits
- Stop loss: 2× ATR from entry
- Trailing stop: Chandelier exit (22-day high − 3 × ATR)
- Hard exit: stock drops out of top 30 of ranking on rebalance day

### 4.4 Regime Overlay
- If NIFTY < 200 DMA: halt new entries, cut gross to 50%
- If NIFTY drawdown from 52w high > 15%: halt new entries entirely

### 4.5 Execution
- Decisions generated post-close
- Orders placed as AMO; entry at next-day open
- Slippage budget: 0.15% largecap, 0.25% midcap

---

## 5. Intraday Swing Module

### 5.1 Strategy A: Opening Range Breakout (ORB)
- Universe: F&O stocks with ADTV > ₹100 crore (~80 names)
- Define opening range: 9:15–9:30 high/low
- Long entry: 5-min close above OR high with volume > 1.5× 20-day avg of first 15-min volume
- Short entry: mirror condition (only if stock has F&O for shorting)
- Filter: skip if gap > 2% at open; skip if NIFTY shows opposing gap

### 5.2 Strategy B: VWAP Pullback Continuation
- Stock trending up on daily (above 50 DMA, R_1M > 0)
- Intraday: price above VWAP, pulls back to touch VWAP, resumes with bullish 5-min candle
- Entry on breakout of pullback candle high
- Mirror for shorts

### 5.3 Position Sizing (Intraday)
- Risk per trade: 0.3% of intraday track capital
- Max concurrent positions: 4
- Stop: below opening range low (ORB) or below VWAP touch low (VWAP pullback)
- Target 1: 1R (book 50%), Target 2: trail with 5-min swing lows
- Hard time stop: square off all positions by 3:15 PM

### 5.4 Daily Loss Circuit Breaker
- If intraday track loses 1.5% in a day → stop trading for the day
- If loses 4% in a week → pause intraday module for one week, manual review

### 5.5 Execution
- MIS orders, bracket order semantics emulated in code (entry + SL + target managed by platform, not broker, since Zerodha removed BO)
- Use limit orders with 0.05% buffer; convert to market if unfilled in 30 seconds
- Latency target: signal-to-order under 2 seconds

---

## 6. India-Specific Constraints (apply to both tracks)

- STT, exchange charges, SEBI fees, stamp duty, GST modeled in backtest (~0.12% round-trip intraday, ~0.25% delivery)
- No trading in first 5 minutes (9:15–9:20) — wide spreads
- No new intraday entries after 2:30 PM
- Skip days: budget day, RBI policy day, expiry day for intraday module (optional but recommended)

---

## 7. Backtesting Requirements

- Point-in-time universe (no survivorship bias)
- Walk-forward: train 2017–2021, test 2022, roll forward yearly
- Realistic costs and slippage as above
- Separate backtest engines acceptable for daily vs intraday, but both must consume from the shared data layer
- Acceptance criteria before going live with real capital:
  - Sharpe > 1.0 net of costs over walk-forward
  - Max DD < 20% (interday), < 10% (intraday)
  - Minimum 100 trades in test window
  - Profit factor > 1.4

---

## 8. Paper Trading Phase

- Every new strategy runs in paper mode for minimum 2 months on live data via the same code path as production
- Compare paper fills vs theoretical backtest fills weekly
- Promote to live only if slippage and hit rate are within 20% of backtest expectations

---

## 9. Implementation Roadmap

**Phase 1 (Weeks 1–4): Foundation**
- Universe manager with India filters
- Shared risk/order layer with idempotency
- Logging and post-trade analytics scaffolding
- Backtest cost model upgrade

**Phase 2 (Weeks 5–8): Interday Swing**
- Momentum ranker + portfolio allocator
- ATR sizing, regime overlay
- Walk-forward backtest, paper trading start

**Phase 3 (Weeks 9–13): Intraday Swing**
- Minute-bar data pipeline
- ORB strategy implementation and backtest
- VWAP pullback strategy
- Intraday execution layer with emulated bracket orders
- Paper trading start

**Phase 4 (Weeks 14–16): Go-Live**
- Interday live with 25% intended capital, scale up over 4 weeks
- Intraday live with 25% intended capital after 2 months paper
- Weekly review cadence

---

## 10. Module Layout

```
platform/
  data/             # bhavcopy, minute bars, corp actions
  universe/         # filters, point-in-time membership
  features/         # ATR, VWAP, momentum scores
  strategies/
    interday/
      momentum_core.py
    intraday/
      orb.py
      vwap_pullback.py
  portfolio/
    allocator.py
    constraints.py
  risk/
    sizing.py
    killswitch.py
    regime.py
  execution/
    order_manager.py
    broker_kite.py
    bracket_emulator.py
  backtest/
    daily_engine.py
    intraday_engine.py
    costs_india.py
  logging/
    signal_log.py
    trade_log.py
    reports.py
```

---

## 11. Open Decisions for the User

- Broker: Zerodha Kite vs Upstox vs Dhan
- Minute data source: broker historical API vs paid vendor (GDFL, TrueData)
- Hosting: local machine vs VPS in Mumbai (latency matters for intraday)
- Whether to enable shorting via F&O for intraday module

---

## 12. Non-Goals

- HFT or sub-second strategies
- Options strategies (separate future project)
- Discretionary overrides during market hours
- Multi-account / client money management
