# CLAUDE.md — Trader Project

Personal automated trading system built in Python, connected to Zerodha's Kite platform via KiteConnect API. Single user, single account. Runs on local Mac.

---

## Running Commands

Virtual environment is at `.venv/`. Always use:
```
.venv/bin/pytest tests/ -q        # run tests
.venv/bin/python <script>         # run scripts if needed
```
Or activate first: `source .venv/bin/activate`

---

## Project Structure

```
main.py                          # intraday entry point (MIS, 5-min candles)
main_interday.py                 # interday entry point (CNC, daily candles)
config/
  config.yaml                    # intraday runtime config
  config_interday.yaml           # interday runtime config
  .env                           # Kite credentials — never commit
trader/
  core/
    config.py                    # singleton `config` — import and use directly; CONFIG_FILE exported
    logger.py                    # setup() + get_logger()
  auth/session.py                # create_kite() — validates token, raises if expired
  costs.py                       # Zerodha transaction cost calculator (MIS + CNC)
  data/
    store.py                     # SQLite interface — all raw SQL lives here only
    historical.py                # warm_up() + get_candles() with cache
    live.py                      # LiveFeed — KiteTicker WebSocket, candle assembly
  strategies/
    base.py                      # Strategy ABC, Signal, Direction, SignalType enums
    group.py                     # StrategyGroup — AND-logic signal combination layer
    rsi.py                       # RSI mean reversion (intraday)
    orb.py                       # Opening Range Breakout (intraday)
    vwap.py                      # VWAP Reversion (intraday)
    supertrend.py                # Supertrend ATR-based trend filter (intraday)
    bollinger.py                 # Bollinger Band mean reversion (intraday)
    ema_pullback.py              # EMA Pullback in uptrend (intraday)
    ema_crossover.py             # EMA crossover (interday / daily candles)
    rsi_ema.py                   # RSI + EMA combo (interday)
    breakout.py                  # 52-week high breakout with trailing stop (interday)
    adx.py                       # ADX trend strength filter (interday, filter only)
  risk/manager.py                # RiskManager — sole gatekeeper between signals and orders
  orders/manager.py              # OrderManager — live Kite calls or paper simulation
  portfolio/tracker.py           # PortfolioTracker — positions and P&L
  scheduler/jobs.py              # APScheduler jobs aligned to IST market hours
  backtest/engine.py             # Backtest — replays candles, simulates fills, applies costs
  calibration/
    param_space.py               # PARAM_SPACES + GROUP_COMPOSITIONS — pure data, no trader imports
    runner.py                    # CalibrationRunner — backtest-based param search + display
  notifications/telegram.py      # Fire-and-forget Telegram alerts
scripts/
  login.py                       # OAuth flow — captures request_token, writes access token
  backtest.py                    # CLI backtest runner
  calibrate.py                   # CLI: find optimal strategy params via backtest
  test_telegram.py               # sends all 7 notification types
tests/                           # pytest unit tests
```

---

## Architecture Rules

**Signal flow (live):** Strategy → `RiskManager.validate()` → `OrderManager.place()`. Strategies never touch orders directly.

**Signal flow (backtest):** `Backtest.run()` replays candles → calls `strategy.on_candle()` → `risk.validate()` → simulates fill at next candle open.

**Config selection:** Set `TRADER_CONFIG` env var before importing any trader module to select a different config file. `main_interday.py` does this automatically. `scripts/backtest.py` and `scripts/calibrate.py` accept `--config`.

**Timezone:** All timestamps stored in SQLite are timezone-naive (IST wall-clock). `Store._to_naive()` strips tzinfo at the DB boundary. Never store tz-aware datetimes.

**Paper mode:** Controlled by `env: paper` in config.yaml. `OrderManager` queues paper fills and fills them at the next candle's open price. No real orders are placed.

**Strategy groups:** `StrategyGroup(primary, filters)` in `strategies/group.py`. ENTRY signals from primary are only forwarded if all filters return `True` from `confirm_entry()`. EXIT signals always pass through. Each filter's `on_candle()` still runs every bar to keep indicator state current.

**Market hours gate:** In `main.py`, strategy signals are only generated between 9:15–15:25 IST. `orders.on_candle()` and `portfolio.refresh()` run unconditionally on every candle.

**Paper fill isolation:** `candle["_symbol"]` is injected in `handle_candle()` before `orders.on_candle()`. `OrderManager._fill_pending_paper()` filters by instrument so INDHOTEL orders are never filled at NATIONALUM prices.

**Transaction costs:** `trader/costs.py` computes all Zerodha charges (brokerage, STT, NSE transaction charges, SEBI charges, GST, stamp duty) for MIS and CNC. The backtest engine deducts round-trip costs from every trade's P&L. `TradeRecord.costs` stores the cost amount for transparency.

---

## Intraday vs Interday

| Concern | Intraday | Interday |
|---|---|---|
| Entry point | `main.py` | `main_interday.py` |
| Config | `config/config.yaml` | `config/config_interday.yaml` |
| Product type | MIS | CNC |
| Candle timeframe | 5-minute | Daily (390-min bucket) |
| Square-off | 3:15 PM daily | Never — hold until signal |
| DB | `data/market.db` | `data/market_interday.db` |
| Strategies | RSI, ORB, VWAP, Supertrend, Bollinger, EMA Pullback (+ groups) | EMA Crossover, RSI+EMA, Breakout, EMA+ADX group |
| Post-market reset | `reset_day()` + `reset_positions()` | `reset_day()` only |

---

## RiskManager Behaviour

- `reset_day()` — resets daily P&L and halt flag only. **Positions are preserved.** Call this every day for both intraday and interday.
- `reset_positions()` — clears open position tracking. Call this at intraday session end (post-market in `main.py`). Do NOT call from `main_interday.py`.
- `square_off_enabled` — check `config.square_off_enabled` before registering the square-off scheduler job.

---

## Backtest Notes

- Each instrument/strategy backtest runs with an independent `RiskManager` and full capital. They do not share capital or position slots.
- The "Overall P&L" in backtest output is additive across isolated runs — not a realistic portfolio simulation.
- `reset_daily=True` (default) resets daily P&L between calendar days. Set `False` for interday backtests.
- SL is anchored to actual fill price, not signal `price_hint`.
- P&L is reported as: gross, transaction costs, and net. `BacktestReport.total_costs()` available.
- `save_trades()` CSV includes `gross_pnl`, `costs`, `net_pnl` columns.
- Costs use `config.product` (MIS vs CNC) to select the correct Zerodha charge schedule.

---

## Parameter Calibration

Find optimal strategy parameters by running backtests across a search space:

```
.venv/bin/python scripts/calibrate.py --strategy rsi --from 2026-03-01 --iterations 20
.venv/bin/python scripts/calibrate.py --strategy vwap --from 2026-03-01 --mode grid --update-config
.venv/bin/python scripts/calibrate.py --strategy orb_supertrend --from 2026-03-01 --metric total_pnl
```

- Supported strategies: `rsi`, `orb`, `vwap`, `supertrend`, `bollinger`, `ema_pullback`, `orb_supertrend`, `rsi_bollinger`
- Metrics: `sharpe` (default), `total_pnl`, `win_rate`, `max_drawdown`
- Modes: `random` (default, N iterations) or `grid` (exhaustive)
- `--update-config` writes best params back to config.yaml — **YAML comments are lost on rewrite** (PyYAML limitation)
- Requires candle data already cached — run `main.py` or `scripts/backtest.py` first

---

## Adding a New Strategy

1. Create `trader/strategies/my_strategy.py` subclassing `Strategy` from `base.py`
2. Implement `on_candle(candle) -> Signal | None` and `name` property
3. Optionally implement `confirm_entry(direction) -> bool` to act as a filter in a `StrategyGroup`
4. Add config section under `strategies:` in the relevant config yaml
5. Register in `main.py` or `main_interday.py` under the strategies list
6. Add to `_build_strategies()` in `scripts/backtest.py`
7. Add param search space to `PARAM_SPACES` in `trader/calibration/param_space.py`
8. Write unit tests under `tests/strategies/`

---

## Key Decisions

- **Data source:** Kite API only (REST for historical, KiteTicker WebSocket for live). No external providers.
- **Storage:** SQLite for candles, orders, trades. Single unified `candles` table with `instrument` + `timeframe` columns. Separate DB files for intraday vs interday to avoid mixing timeframes.
- **Paper trading:** 2 weeks paper run before going live.
- **Starting capital:** ₹2,00,000 intraday / ₹20,000 interday. Per-trade risk 2–5% depending on mode.
- **Telegram alerts:** Implemented but optional. Skips silently if token/chat ID missing in `.env`.
- **Deployment:** Local Mac. No AWS. Owner arranges static IP.

---

## Credentials

Never put secrets in source code or logs. All credentials live in `config/.env`:
- `KITE_API_KEY`
- `KITE_API_SECRET`
- `KITE_ACCESS_TOKEN` — refreshed daily via `scripts/login.py`
- `TELEGRAM_BOT_TOKEN` (optional)
- `TELEGRAM_CHAT_ID` (optional)

Token expires every day at midnight IST. Re-run `scripts/login.py` each morning before market open (or automate via launchd).
