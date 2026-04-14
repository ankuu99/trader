# CLAUDE.md — Trader Project

Personal automated trading system built in Python, connected to Zerodha's Kite platform via KiteConnect API. Single user, single account. Runs on local Mac.

**Trading model:** CNC-only (delivery). Positions are held from hours to weeks — no forced intraday close. Candle timeframe is a config choice (5minute / 15minute / 30minute / 60minute / day); it determines signal generation frequency, not trade duration. Exits are driven by strategy signals or chandelier trailing stop. Each strategy owns its own exit logic (e.g. `MACDTargetStrategy.target_pct`).

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
main.py                          # unified entry point — intraday and interday
                                 #   python main.py                                       (intraday)
                                 #   python main.py --config config/config_interday.yaml  (interday)
main_interday.py                 # convenience wrapper — sets TRADER_CONFIG and calls main.py
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
    registry.py                  # build_strategies() — single source of truth for all strategy classes
    rsi.py                       # RSI mean reversion (intraday)
    orb.py                       # Opening Range Breakout with volume + gap filters (intraday)
    vwap.py                      # VWAP Reversion (intraday)
    vwap_pullback.py             # VWAP Pullback Continuation — trend + VWAP touch + resume (intraday)
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
  backtest/portfolio.py          # PortfolioBacktest — shared-capital multi-symbol backtest
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

**Unified entry point:** `main.py` is the single entry point. All behaviour is driven by config. Key config properties:
- `candle_timeframe` — controls LiveFeed bucket size and backtest timeframe (5minute / 15minute / 30minute / 60minute / day)
- `product` is always `"CNC"` — hardcoded; no MIS support

**Strategy registry:** `trader/strategies/registry.py` is the single source of truth for all strategy classes, group compositions, and filter-only strategies. `build_strategies(symbol, config)` is the one function all entry points call — `main.py`, `scripts/backtest.py`, `scripts/calibrate.py`. Adding a new strategy only requires editing `registry.py` and `calibration/param_space.py`.

**Strategy groups:** `StrategyGroup(primary, filters)` in `strategies/group.py`. ENTRY signals from primary are only forwarded if all filters return `True` from `confirm_entry()`. EXIT signals always pass through. Each filter's `on_candle()` still runs every bar to keep indicator state current.

**Market hours gate:** Applied only for intraday-frequency candle timeframes (5m / 15m / 30m / 60m). Signals blocked outside 9:15–15:30 IST. For daily candles, signals fire at close and execute at next morning's open. `orders.on_candle()` and `portfolio.refresh()` run unconditionally on every candle.

**Paper fill isolation:** `candle["_symbol"]` is injected in `handle_candle()` before `orders.on_candle()`. `OrderManager._fill_pending_paper()` filters by instrument so INDHOTEL orders are never filled at NATIONALUM prices.

**Transaction costs:** `trader/costs.py` computes all Zerodha charges (brokerage, STT, NSE transaction charges, SEBI charges, GST, stamp duty) for MIS and CNC. The backtest engine deducts round-trip costs from every trade's P&L. `TradeRecord.costs` stores the cost amount for transparency.

**ORB signal quality filters:** `orb.py` supports `volume_filter` and `gap_filter` params. Volume filter skips entry if first 15-min range volume < `volume_multiplier × 20-day average`; bypasses automatically until 5 days of history are collected. Gap filter skips entry if the day's open gaps more than `gap_pct` (default 2%) vs previous close. Both default to `false`; configure under `strategies.orb` in config.yaml.

**VWAP Pullback strategy (`vwap_pullback.py`):** 3-step trend continuation pattern. (1) Close > SMA (trend up). (2) Previous close above VWAP; current candle low touches VWAP within tolerance and closes near it → sets `AWAITING_RESUME` state with pullback high. (3) Next candle closes above the pullback high → ENTRY signal. Exit when close < VWAP. SMA window is cross-day (not reset daily); VWAP and pullback state reset each day.

**Signal audit log:** `store.py` maintains a `signals` table in SQLite. Each row records instrument, strategy, direction, signal_type, price_hint, whether it was accepted, and the rejection reason if blocked. Populated by passing `signal_logger=store.log_signal` to `RiskManager`.

**ATR in signals:** `Signal` carries an optional `atr: float | None` field. Strategies that compute ATR (currently `SupertrendStrategy`) populate it on ENTRY signals. Both `main.py` and `engine.py` pass `signal.atr` to `risk.validate(signal, atr=signal.atr)`. Strategies that don't set it get the 1%-of-price SL fallback.

---

---

## RiskManager Behaviour

- `reset_day(is_monday=False)` — resets daily P&L and halt flag. Pass `is_monday=True` on Mondays to also reset weekly P&L and weekly halt flag. **Positions are preserved.** Called automatically at each calendar day boundary in backtest engine and post-market in live.
- `reset_positions()` — clears open position tracking. Not called automatically; only use explicitly if needed.
- `update_regime(allowed: bool)` — called externally after computing NIFTY 200 DMA check. When `allowed=False`, all new ENTRY signals are blocked. EXIT signals always pass through. Only engaged when `config.regime_filter_enabled = true`.
- **Weekly circuit breaker:** tracks `_weekly_realised_pnl` across days. When loss exceeds `config.weekly_loss_limit`, sets `_weekly_halted = True` for the rest of the week. Resets automatically on Monday via `reset_day(is_monday=True)`. Only active when `config.weekly_loss_limit > 0`.
- **ATR-based position sizing:** when `config.atr_sizing_enabled = true`, quantity is computed as `risk_amount / (atr_multiplier × ATR)`. Otherwise `max_risk // sl_distance` is used. In both cases the result is capped at `max_position_pct` of total capital (0 = no cap). Pass `atr=signal.atr` to `validate()` — populated by strategies that compute ATR (Supertrend); others yield `None` and use the 1%-of-price SL fallback.
- **Signal logging:** construct `RiskManager(signal_logger=store.log_signal)` to write every signal decision (accepted/rejected + reason) to the `signals` SQLite table. The logger callable is optional — omit for backtest runs where audit trail is not needed.

---

## Backtest Notes

- Each instrument/strategy backtest runs with an independent `RiskManager` and full capital. They do not share capital or position slots.
- The "Overall P&L" in backtest output is additive across isolated runs — not a realistic portfolio simulation.
- Daily P&L counter always resets at each calendar day boundary (for loss-limit tracking). Positions are **never** force-closed at day end.
- Pending entry signals carry across day boundaries — a signal at 15:29 executes at next morning's open.
- SL is anchored to actual fill price, not signal `price_hint`.
- P&L is reported as: gross, transaction costs, and net. `BacktestReport.total_costs()` available.
- `save_trades()` CSV includes `gross_pnl`, `costs`, `net_pnl` columns.
- Costs use `config.product` (MIS vs CNC) to select the correct Zerodha charge schedule.
- **Chandelier trailing stop:** `Backtest(store, strategy, chandelier=True)` enables the Chandelier Exit. SL trails as `highest_high_since_entry − multiplier × ATR_22`, ratcheting up only — never lowering. Period and multiplier read from `config.trailing_stop.period/multiplier`. `chandelier=None` (default) reads from `config.trailing_stop.enabled`.
- **Strategy-owned exits:** There is no engine-level profit target. Each strategy handles its own exit signals (e.g. `MACDTargetStrategy` exits at `target_pct`). The engine only closes positions via SL hit, chandelier stop, or a strategy-emitted EXIT signal.
- **Portfolio backtest:** `PortfolioBacktest(store, capital)` in `backtest/portfolio.py` runs multiple symbols with shared capital. `deployed_cash` tracking prevents simultaneous positions from each consuming the full capital. Use `strategies_factory=` kwarg to inject explicit strategies (required in tests; defaults to `build_strategies` in production). Warm-up: 45 calendar days of pre-period candles are fed to strategies before the actual period starts to keep indicator state consistent across sub-period runs.

### Test config isolation
`tests/conftest.py` contains an autouse fixture that pins `total_capital=20,000`, `max_risk_per_trade_pct=1%`, `atr_based=False`, `max_position_pct=0` for every test. This prevents test assertions from breaking when live config values are tuned. Tests that specifically exercise ATR sizing or the position cap re-enable them via `monkeypatch`.

---

## Parameter Calibration

Find optimal strategy parameters by running backtests across a search space:

```
.venv/bin/python scripts/calibrate.py --strategy rsi --from 2026-03-01 --iterations 20
.venv/bin/python scripts/calibrate.py --strategy vwap --from 2026-03-01 --mode grid --update-config
.venv/bin/python scripts/calibrate.py --strategy orb_supertrend --from 2026-03-01 --metric total_pnl
```

- Supported strategies: `rsi`, `orb`, `vwap`, `vwap_pullback`, `supertrend`, `bollinger`, `ema_pullback`, `orb_supertrend`, `rsi_bollinger`
- Metrics: `sharpe` (default), `total_pnl`, `win_rate`, `max_drawdown`
- Modes: `random` (default, N iterations) or `grid` (exhaustive)
- `--update-config` writes best params back to config.yaml — **YAML comments are lost on rewrite** (PyYAML limitation)
- Requires candle data already cached — run `main.py` or `scripts/backtest.py` first

---

## Adding a New Strategy

1. Create `trader/strategies/my_strategy.py` subclassing `Strategy` from `base.py`
2. Implement `on_candle(candle) -> Signal | None` and `name` property
3. Optionally implement `confirm_entry(direction) -> bool` to act as a filter in a `StrategyGroup`
4. Add to `STRATEGY_CLASSES` in `trader/strategies/registry.py` (and `GROUP_COMPOSITIONS` if it's a group)
5. Add config section under `strategies:` in the relevant config yaml
6. Add param search space to `PARAM_SPACES` in `trader/calibration/param_space.py`
7. Write unit tests under `tests/strategies/`

**No changes needed** to `main.py`, `scripts/backtest.py`, or `scripts/calibrate.py`.

---

## Key Decisions

- **Data source:** Kite API only (REST for historical, KiteTicker WebSocket for live). No external providers.
- **Storage:** SQLite for candles, orders, trades, and signal audit log. Single unified `candles` table with `instrument` + `timeframe` columns. `signals` table for risk manager audit trail. Separate DB files for intraday vs interday to avoid mixing timeframes.
- **Paper trading:** 2 weeks paper run before going live.
- **Starting capital:** ₹50,000 intraday / ₹20,000 interday. Per-trade risk 1% of capital.
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
