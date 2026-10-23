# Trader — System Design & Architecture

> An automated, long-only, delivery (CNC) swing-trading system for NSE equities via
> Zerodha/Kite. Supports `paper` and `live` execution modes plus an offline
> backtest/calibration toolchain that shares the live code paths as much as possible.

---

## 1. High-level architecture

```
                     ┌─────────────────────────────────────────────┐
                     │                 main.py                      │
                     │  (wires everything together, owns event loop)│
                     └─────────────────────────────────────────────┘
                              │              │              │
        ┌─────────────────────┘              │              └─────────────────────┐
        ▼                                    ▼                                     ▼
┌───────────────┐                  ┌──────────────────┐                ┌────────────────────┐
│   LiveFeed     │  ticks/candles   │   Strategies      │   Signal       │   RiskManager       │
│ (KiteTicker WS)│ ───────────────▶ │ (LRExtremaStrategy│ ─────────────▶ │ (sizing, halts,     │
│                │                  │  per instrument)  │                │  exposure caps)      │
└───────┬────────┘                  └──────────────────┘                └─────────┬───────────┘
        │ order updates                                                            │ Order
        ▼                                                                          ▼
┌────────────────┐   fills/cancels   ┌────────────────────┐    SQLite     ┌───────────────────┐
│  OrderManager   │ ◀──────────────▶ │   Store (SQLite)    │ ◀───────────▶ │ PortfolioTracker   │
│ (paper/live/GTT)│                   │ candles, orders,    │               │ (P&L, positions)   │
└────────┬────────┘                   │ trades, signals,    │               └────────────────────┘
         │ dispatch                   │ open_positions,     │
         ▼                            │ state               │
┌────────────────┐                    └─────────────────────┘
│ Telegram        │
│ notifications   │
└────────────────┘

Scheduler (APScheduler, IST):
  08:30 token reminder · 09:00 pre-market warm-up · 15:30 flush partial candle ·
  15:35 post-market summary/reset · every 30min heartbeat (09:00-15:30)
```

Offline tooling (`scripts/backtest.py`, `scripts/calibrate.py`, `scripts/screen.py`,
`scripts/backtest_rolling.py`) reuses `trader/backtest/engine.py`, which itself reuses
`RiskManager`, `OrderManager` (in paper mode, `kite=None`), and `LRExtremaStrategy` — so
backtest and live share the sizing/exit logic almost entirely. The only divergence is
fill-timing simulation (see §9).

---

## 2. Entry point — `main.py`

Responsibilities, in order of execution:

1. **Bootstrap**: parses `--config` override, loads `.env`, sets up logging
   (`trader/core/logger.py` → rotating files `system.log`, `orders.log`,
   `strategy.log`, `data.log` + console).
2. **Auth**: `create_kite()` (session auth).
3. **Capital seeding (live only)**: fetches `kite.margins()`, combines with persisted
   `cumulative_pnl` from SQLite `state` table, and calls
   `risk.seed_cumulative_pnl()`. Effective capital = `min(config_total + persisted_pnl,
   kite_cash)`.
4. **Instrument resolution**: fetches the full NSE instrument dump from Kite, maps
   `watchlist` symbols → instrument tokens. Missing symbols are logged and dropped.
5. **Strategy construction**: `build_strategies(symbol, config)` per watchlist symbol
   (registry pattern — currently only `LRExtremaStrategy`).
6. **Candle cache refresh + strategy warm-up**: re-warms the SQLite candle cache, then
   replays `historical_cache_days` of candles through each strategy's `on_candle()` so
   models are trained before the first live candle. Signals generated during warm-up are
   discarded.
7. **Phantom-state cleanup**: clears any `_entry_price`/`_held_bars`/`_peak_close`/
   `_trailing_active` left dangling by warm-up signals that never got a fill.
8. **Position restoration**:
   - **Paper mode**: restores open positions from SQLite `open_positions`, replays
     candles since entry to detect any "missed" exits (SL/target/hold_bars) that should
     have fired while the process was down, and either re-seeds strategy state via
     `seed_position_state()` or deletes the stale position and notifies via Telegram.
   - **Live mode**: reconciles `RiskManager`/strategy state against
     `kite.positions()` + `kite.holdings()` + the bot's own `open_positions` table
     (3-way check because CNC positions move through net-positions → T1 holdings →
     settled holdings). Also re-locks capital for any BUY orders that were `PENDING`
     when the bot restarted (`seed_pending_order`).
9. **Dashboard**: optionally starts a read-only UI (`trader/ui/server.py`,
   `config.ui.enabled`).
10. **Callbacks wired**:
    - `handle_order_update` — routes fills/cancels to `RiskManager`, `PortfolioTracker`,
      `Store`, Telegram, and the originating strategy.
    - `handle_candle` — drives strategy `on_candle()`, persists candles, computes
      live position metrics, logs signals (accepted/rejected with reason), and forwards
      approved orders to `OrderManager`.
    - `handle_tick` — drives strategy `on_tick()` for tick-speed SL/trailing exits.
11. **Scheduler hooks**: `pre_market` (re-warm cache + `feed.reconnect()`),
    `post_market` (refresh portfolio, reconcile stale GTT-closed positions, daily P&L
    notification, `risk.reset_day()`, `orders.clear_pending()`, `feed.disconnect()`),
    `heartbeat` (log open positions + capital).
12. **Run loop**: starts scheduler, runs `pre_market()` once immediately, starts the
    live feed (threaded), then blocks on `time.sleep(1)` until `KeyboardInterrupt`.

---

## 3. Data layer (`trader/data/`)

### `historical.py`
- `get_candles(kite, store, token, instrument, timeframe, from_dt, to_dt)` — cache-first
  fetch. Reads `store.latest_candle_timestamp()`, fetches only the missing tail from
  Kite, persists, returns the full requested range from SQLite.
- Handles Kite's API limits via `_date_chunks` (60 days/request for intraday, 2000 for
  daily) and retries with exponential backoff on `"Too many requests"`.
- `kite=None` is fully supported → cache-only mode (used by backtest workers after
  pre-fetch).
- `warm_up()` — convenience wrapper used pre-market and at startup.

### `live.py` — `LiveFeed`
- Wraps `KiteTicker`. Subscribes to `MODE_FULL` for all watchlist tokens.
- **Candle assembly**: buckets ticks into `timeframe_minutes`-wide candles anchored to
  market open (09:15 IST) — `_candle_bucket()` ensures live candle boundaries match
  Kite's historical-candle boundaries (critical: the model trains on historical candles
  and must see the same distribution live).
- **Volume**: Kite ticks carry *cumulative day volume*; the feed tracks a per-candle
  baseline and computes deltas, with day-rollover detection.
- **Timezone normalisation**: handles aware datetimes, naive-UTC (EC2 default), and
  naive-IST (local dev) tick timestamps uniformly — always buckets in IST wall-clock
  time.
- `disconnect()`/`reconnect()` — suspends/resumes the WebSocket across market close,
  clearing partial-candle state to avoid stale data on resume.
- `flush_partials()` — force-emits in-progress candles at 15:30 so the final partial
  candle of the day isn't lost.
- Dispatches: tick handlers, candle handlers, order-update handlers (live mode only).

### `store.py` — `Store` (SQLite, WAL mode)
Tables:
| Table | Purpose |
|---|---|
| `candles` | OHLCV per `(instrument, timeframe, timestamp)` — upserted |
| `orders` | full order lifecycle (PENDING/COMPLETE/REJECTED/CANCELLED) |
| `trades` | filled trade records linked to orders |
| `open_positions` | paper-mode position persistence across restarts, incl. live metrics (`current_price`, `pct_change`, `unrealised_pnl`, `peak_close`, `trailing_active`, `low_since_entry`, `pattern_top_trailing`) — used by the UI |
| `signals` | every signal evaluation (accepted or rejected, with reason and exit_reason) — UI/debugging |
| `state` | generic key→float persistence; currently only `cumulative_pnl` and per-instrument `peak_close`/`max_gain_pct` |

- Schema migrations are additive `ALTER TABLE ... ADD COLUMN` wrapped in
  try/except (idempotent on existing DBs).
- `clear_backtest_data()` wipes `candles/orders/trades/signals` — used only by
  `scripts/backtest.py`.
- DB size is logged at startup; warns above 500 MB.

---

## 4. Strategy layer (`trader/strategies/`)

### `base.py`
- `Strategy(ABC)` — `instrument`, `params`, `position: Direction | None`.
- `Signal` dataclass — `instrument, direction, signal_type, price_hint, strategy, atr,
  target_price, stop_loss_hint, exit_reason, timestamp`.
- Lifecycle contract: `on_candle()` (required), `on_tick()` (optional, tick-speed
  exits), `on_order_update()` (position state sync), `seed_position_state()` (restart
  recovery), `is_flat()`, `confirm_entry()` (for future multi-strategy confirmation
  filters — currently unused since there's only one strategy).
- **Strategies never import from `orders/` or `risk/`** — strict separation of signal
  generation from execution/sizing.

### `registry.py`
- `build_strategies(instrument, config)` — currently returns `[LRExtremaStrategy(...)]`
  if `strategies.lr_extrema.enabled`. Single-strategy-per-instrument today; the list
  return type anticipates future multi-strategy ensembles per instrument.

### `lr_extrema.py` — `LRExtremaStrategy`
A **self-training logistic-regression classifier** that learns what local price minima
(and maxima) look like for a given stock, retrains periodically, and trades the model's
own confidence.

**Pipeline:**
1. Accumulate candles in a `deque(maxlen=lookback_bars)`.
2. After `warmup_bars`, train (and retrain every `retrain_every` candles) on local
   extrema found via `_find_local_extrema` (±`extrema_order` neighbourhood window).
   Minima → class 0 (buy candidate), maxima → class 1 (sell candidate).
3. **Feature vector** (6 base features, 2 optional add-ons):
   `volume_ratio, norm_price, slope3, slope5, slope10, slope20` — all derived from
   % returns and rolling volume, making them scale-invariant across stocks/time.
   Optional: `drawdown_from_high` (Enhancement B), `macd_hist_norm`/`macd_hist_slope`
   (Enhancement C).
4. **Entry**: `P(local-min) >= threshold` AND `P(local-max) < veto_threshold`, then
   passes a stack of optional hard gates (volume ratio, norm price floor, prior-decline
   requirement, trend gate, RSI gate, Stochastic-RSI gate, MACD gate). All gate failures
   are collected and logged together (`last_filter_block`).
5. **Exits** — three layers:
   - **Tick-speed (`on_tick`)**: hard stop-loss (`stop_pct`), trailing-stop activation
     once `profit_pct` floor reached, trailing-stop exit (`trail_pct` from peak),
     optional breakeven stop, optional EOD forced close for trailing positions
     (`force_trailing_close_time`).
   - **Candle-speed (`on_candle`)**: max-hold timeout (`hold_bars`), pattern-top model
     exit (`P(local-max) >= sell_threshold` after `min_hold_before_exit` bars and
     `gain >= sell_min_pct`), and three *optional* "fundamental enhancement" exits:
     - **Stale exit (tier 1)**: best-gain-ever < `stale_min_gain_pct` after
       `stale_check_bars` → exit (thesis never worked).
     - **Stale exit (tier 2)**: current gain < `stale_min_gain_pct_2` at exactly
       `stale_check_bars_2` → exit (faded after early promise).
     - **Momentum-decay exit**: `P(local-min)` drops below
       `momentum_exit_p_min_floor` while gain is still small → model no longer
       believes the bottom thesis.
   - **Forward-return labelling (Enhancement A)**: optionally filters out "false
     bottom" minima from training labels unless price rose `min_return_pct` within
     `forward_bars` — improves label quality at the cost of fewer training samples
     (falls back to unfiltered labels if too few qualify).
6. **In-position phantom signals**: if entry conditions re-trigger while already
   holding, a Signal is still emitted (so the UI can show where re-entries *would* have
   fired) but `RiskManager` rejects it with `already_in_position`.
7. **Restart recovery**: `seed_position_state(peak_close, max_gain_pct)` restores
   in-memory trailing/progress state from `state` table; `_held_bars` is restored via a
   synthetic `on_order_update` fill carrying `_held_bars`.
8. **Trading-window gate**: checked once per candle (`config.trading_start`/`trading_end`,
   default 09:30–15:30 IST) — applies uniformly to entries and the candle-granularity
   exits; does not affect SL/trailing (tick-speed) which fire any time the position is
   open but within `on_tick`'s own window check.

**Per-instrument config**: `config.get_strategy_params(instrument, "lr_extrema")` deep-
merges `per_stock_params.<instrument>.lr_extrema` over the global `strategies.lr_extrema`
block — every param (threshold, forward_label, profit/stop/trail, etc.) can be
overridden per stock.

---

## 5. Risk layer (`trader/risk/manager.py`) — `RiskManager`

Single authority for **whether** a signal becomes an order and **how big** it is.

- **ENTRY validation** (`validate`):
  1. Daily-halt check (set when `_realised_pnl <= -daily_loss_limit`).
  2. Trading-window check (safety net; strategies pre-filter too).
  3. `max_open_positions` check (`open_positions + pending_orders`).
  4. Duplicate-instrument checks: already in position / pending order exists.
  5. SL price from `signal.stop_loss_hint` or `default_sl_pct` fallback; rejects if
     `sl_distance <= 0`.
  6. **Sizing**: `quantity = max_risk_per_trade // sl_distance`, then capped by:
     - `max_capital_per_stock_pct` of `(base_capital + cumulative_pnl)` if
       `compounding: true`, else of `total_capital`.
     - remaining `capital_available`.
  7. Rejects with `quantity_zero` if the capped quantity is ≤ 0.
  8. Target price from `signal.target_price` or `price + sl_distance * risk_reward`.
  9. Locks `expected_cost` in `_pending_orders` until the fill/cancel callback resolves
     it.
- **EXIT validation** (`_validate_exit`): bypasses all conflict checks — even allowed
  while halted — returns a SELL order for the full tracked quantity.
- **Capital accounting**: `capital_available = total_capital + cumulative_pnl -
  capital_deployed - pending`. `on_order_filled` / `close_position` maintain
  `_capital_deployed`, `_position_values`, `_realised_pnl` (resets daily),
  `_cumulative_pnl` (lifetime, persisted to SQLite in live mode).
- **Halt mechanism**: `_realised_pnl <= -daily_loss_limit` → `_halted = True` +
  Telegram alert; cleared by `reset_day()` (called post-market and at backtest day
  boundaries).
- **Restart seeding**: `seed_cumulative_pnl`, `seed_position`, `seed_pending_order`,
  `seed_realised_pnl` (the last can immediately trigger a halt if today's broker-side
  realised loss already breaches the limit, e.g. a GTT fired while the bot was down).
- `_last_reject_reason` — exposed to UI via the `signals` table for every rejection
  (`daily_halt`, `outside_trading_window`, `max_positions`, `already_in_position`,
  `pending_order_exists`, `sl_distance_zero`, `quantity_zero`).

---

## 6. Execution layer (`trader/orders/manager.py`) — `OrderManager`

### Paper mode
- `place()` queues the `Order` in `_pending_paper`.
- `on_candle()` fills queued orders:
  - **MARKET**: fills at next candle's `open` (realistic next-bar slippage).
  - **LIMIT**: fills only if price touches the limit during the candle (`low <= limit`
    for BUY, `high >= limit` for SELL), at exactly the limit price; otherwise stays
    pending across candles.
- `clear_pending()` — EOD cancellation of unfilled LIMIT orders; dispatches synthetic
  `CANCELLED` records so strategies clear `_entry_price` and risk releases the lock.

### Live mode
- `place()` → `kite.place_order()` (`MARKET` with `market_protection=-1`, or `LIMIT`
  at `price_hint`). On placement failure, dispatches a synthetic `REJECTED` so the
  strategy doesn't get permanently stuck waiting for a fill.
- `on_kite_order_update()` — normalises Kite websocket order postbacks:
  - Looks up the originating `Order` by `order_id`, falling back to
    `_instrument_orders` (needed because **GTT-triggered exits arrive with a new
    order_id** not tracked in `_live_orders`).
  - Reclassifies SELL fills against an ENTRY order as `signal_type=EXIT` so strategy
    state resets correctly.
  - After a confirmed BUY fill, if `config.gtt_enabled`, places a GTT OCO
    (`_place_gtt_sl`) — **GTT is currently disabled by default** (see §9).
  - On SELL fill or BUY reject/cancel, cleans up `_instrument_orders` to avoid stale
    GTT-recovery context.
- GTT OCO: SL leg is MARKET, target leg is LIMIT; trigger values rebased to the actual
  fill price if it differs from the signal-time `price_hint`.

All fills/cancels/rejects are persisted via `Store.upsert_order` and dispatched to
registered callbacks (`main.py`'s `handle_order_update`, and in backtest, the engine's
internal handler).

---

## 7. Portfolio (`trader/portfolio/tracker.py`) — `PortfolioTracker`

- **Paper mode**: maintains an in-memory `dict[symbol → Position]`, updated on each
  fill; computes realised P&L on SELL fills. **Not persisted** — resets on restart
  (open positions for paper are separately persisted via `open_positions` table and
  restored in `main.py`, but `PortfolioTracker`'s own realised-P&L history is lost).
- **Live mode**: `refresh()` pulls `kite.positions()["net"]` on demand (called from
  `post_market`), populating `unrealised_pnl`/`realised_pnl` directly from Kite.
- `log_summary()` — logs aggregate open count, unrealised, realised, net %, feeding
  the daily Telegram P&L report.

---

## 8. Scheduler (`trader/scheduler/jobs.py`)

APScheduler `BackgroundScheduler`, timezone `Asia/Kolkata`, weekdays only:

| Time | Job | Action |
|---|---|---|
| 08:30 | token reminder | Telegram nudge to refresh Kite token |
| 09:00 | pre-market | re-warm candle cache for all watchlist symbols, `feed.reconnect()` |
| 09:00–15:30, every 30 min | heartbeat | log open positions + capital_available |
| 15:30 | market close | `feed.flush_partials()` — emit final partial candle |
| 15:35 | post-market | refresh live positions, reconcile stale GTT-closed positions, Telegram daily P&L, `risk.reset_day()`, `orders.clear_pending()`, `feed.disconnect()` |

All hooks run inside try/except — one hook failing doesn't block the others.

---

## 9. Backtest engine (`trader/backtest/engine.py`)

Shared by `backtest.py`, `calibrate.py`, `screen.py`, `backtest_rolling.py`. **Never
imported in the live path.**

- Fresh `RiskManager`/`OrderManager(kite=None, mode="paper")`/`LRExtremaStrategy` per
  run — no cross-run state leakage.
- **Pre-warmup fetch**: fetches `historical_cache_days` (or `pre_warmup_days`) before
  `from_dt` so the model is trained before the measurement window starts; replayed
  through `on_candle()` with signals discarded, then phantom-state is cleared (same
  logic as live startup).
- **Regime features**: optionally forward-fills NIFTY 50 / India VIX closes into every
  candle as `_nifty_close`/`_vix_close` (currently unused by `LRExtremaStrategy`'s
  feature vector — present for future regime-aware strategies).
- **Multi-symbol chronological merge**: all symbols' candles are merged into one
  timestamp-ordered stream so `RiskManager` sees competing signals in real time —
  portfolio-level capital competition is realistic.
- **Day-boundary handling**: `risk.reset_day()` per calendar day (halt doesn't carry
  over); LIMIT-mode pending orders cleared at day boundary (mirrors Zerodha EOD rules).
- **Intrabar SL/target**: every candle checks `low <= sl` / `high >= target`; gap-
  adjusted fill (`min(sl, open)` / `max(target, open)`) if the candle opens through the
  level. If `trail_pct` is configured, `target=0` (trailing/pattern-top manage upside
  instead of a fixed target).
- **Trailing simulation**: feeds `candle["high"]` then `candle["close"]` through
  `strategy.on_tick()` — high updates the peak, close checks the trail distance.
- **Trade record** fields: `instrument, entry, exit, qty, pnl, cost, product, reason,
  entry_date, exit_date, held_candles`. `product` is `MIS` if entry/exit same calendar
  day else `CNC` (cost model switches accordingly).
- **Reason taxonomy**: `SL`, `TARGET`, `TRAILING`, `STRATEGY` (hold_bars / stale /
  momentum-decay exits all currently land here unless `exit_reason` is explicitly
  propagated — see Signal contract), `PATTERN_TOP`, `OPEN@END` (position still open at
  `to_dt`, closed at entry price as a conservative placeholder — **not** mark-to-market).
- `compute_metrics()` — `total_trades, win_rate, money_weighted_win_rate, total_pnl,
  return_pct, avg_win, avg_loss, sharpe_proxy, sortino_ratio, calmar_ratio,
  max_drawdown(_pct), profit_factor, monthly_returns`.

---

## 10. Configuration (`trader/core/config.py`)

- Single YAML file (`config/config.yaml`), loaded once into a module-level `config`
  singleton at import time. `TRADER_CONFIG` env var can point to an alternate file
  (used by backtest scripts to avoid mutating the live config).
- `.env` provides Kite/Telegram secrets; `KITE_API_KEY`/`KITE_API_SECRET` are required
  at import time (raises `EnvironmentError` if missing — **the whole process fails to
  import `trader.core.config` without valid secrets**, including for backtests).
- `get_strategy_params(instrument, strategy_name)` — deep-merges
  `per_stock_params.<instrument>.<strategy_name>` over `strategies.<strategy_name>`.
  Nested dicts merge key-by-key (`_deep_merge`); scalars/lists are overridden wholesale.
- `set_effective_capital()` mutates `_data["capital"]["total"]` at runtime (live-mode
  capital-cap-by-Kite-cash); `base_capital` is captured at construction time and never
  mutated — used as the compounding base so this runtime adjustment doesn't distort
  position sizing.
- `candle_minutes` mapping covers `minute/5minute/15minute/30minute/60minute/4hour/day`
  — note `4hour` is **not** a valid Kite historical interval (`historical.py`'s
  `INTERVALS` set excludes it) even though `config.py` maps it to 240 minutes; using
  `candle_timeframe: 4hour` would pass config validation but fail at the Kite API call.
- `trading_start`/`trading_end` parsed from `"HH:MM"` strings — used by
  `RiskManager`, `LRExtremaStrategy` (entry/candle-exit gate), and the backtest engine.

---

## 11. Notifications (`trader/notifications/telegram.py`)

- All functions are no-crash-safe: missing token/chat-id → debug log + `False`.
  `disable()` is called once by the backtest engine module so backtests never spam
  Telegram.
- Covers: order queued/filled/rejected, daily P&L, halt, GTT placed, trailing
  activated, positions restored (paper restart), token refresh reminder/confirmation,
  generic error, startup banner.

---

## 12. What the system supports today

- **Single strategy** (`LRExtremaStrategy`), one instance per watchlist instrument,
  long-only, CNC delivery.
- **Two execution modes**: `paper` (in-process simulation, SQLite-persisted open
  positions) and `live` (real Kite orders, optional GTT, full broker reconciliation on
  restart).
- **One timeframe at a time**, applied uniformly to every instrument
  (`config.candle_timeframe`).
- **Per-instrument parameter overrides** via `per_stock_params` (deep-merged), enabling
  different thresholds/forward-label settings/exit tuning per stock without code
  changes.
- **Three-layer exit stack**: hard SL + trailing (tick-speed), pattern-top model exit +
  hold_bars timeout + stale/momentum-decay exits (candle-speed) — all individually
  toggleable per stock.
- **Restart-safe state**: cumulative P&L, open positions (paper via SQLite, live via
  Kite reconciliation), trailing peak/max-gain (`state` table), pending-order capital
  locks.
- **Daily loss-limit circuit breaker** with Telegram alerting, auto-reset at
  post-market.
- **Cost-aware backtesting** (`trader/costs.py`) with MIS/CNC distinction, gap-adjusted
  intrabar SL/target fills, multi-symbol portfolio simulation with realistic capital
  competition.
- **Calibration tooling** (grid/random search, parallelised) and a **screener** across
  the full NSE EQ universe.
- **Read-only dashboard UI** for live monitoring (positions, signals, model scores,
  warm-up status).

---

## 13. Known limitations / what's NOT supported

- **No multi-timeframe support.** Every instrument and strategy uses the single global
  `candle_timeframe`. There's no mechanism for e.g. a daily-chart trend filter combined
  with a 15-minute entry trigger, or for running the same strategy on two timeframes
  simultaneously.
- **No short-selling / no derivatives.** `Direction` only has `BUY`/`SELL` where `SELL`
  is always an *exit* of a long position. `config.product` is hardcoded to `"CNC"`.
  Intraday (MIS) is only used implicitly in the backtest cost model when entry/exit
  happen same-day — it's never a live order type.
- **No true multi-strategy ensembles per instrument.** `registry.build_strategies()`
  returns a list (so the *plumbing* supports multiple strategies per instrument), but
  in practice only `LRExtremaStrategy` exists, and nothing in `main.py` arbitrates
  between multiple signals for the same instrument beyond "first one that validates
  wins" (RiskManager would reject the second as `already_in_position` /
  `pending_order_exists`).
- **`confirm_entry()` filter hook is unused** — designed for cross-strategy
  confirmation (e.g. a trend filter strategy gating an entry strategy) but no caller
  invokes it.
- **GTT is disabled by default** (`gtt_enabled: false`). Exit logic relies entirely on
  the bot being alive and processing candles/ticks. The systemd `Restart=always` +
  10s restart is the only safety net — a sufficiently long outage (or a SL breach
  during downtime) is only caught at next-startup reconciliation, not in real time.
- **Paper-mode portfolio P&L (`PortfolioTracker`) does not persist across restarts** —
  only `open_positions` and cumulative P&L (live-only) survive. Paper-mode realised
  P&L history resets to zero on restart (cumulative_pnl is not persisted for paper).
- **`_peak_close` / trailing state is best-effort across restarts** — persisted to the
  `state` table per-instrument but only on candles where the position is open; a crash
  between trailing activation and the next candle close could lose a small amount of
  peak-tracking precision (though `seed_position_state` mitigates this on restart).
- **Backtest "OPEN@END" positions are valued at entry price**, not mark-to-market at
  `to_dt` — a conservative simplification that slightly understates unrealised
  gains/losses for positions still open at the end of a backtest window.
- **Regime features (NIFTY/VIX) are fetched but unused** by the current feature vector
  — infrastructure exists in the backtest engine for future regime-aware strategies
  but `LRExtremaStrategy._compute_features` does not consume `_nifty_close`/
  `_vix_close`.
- **`4hour` candle timeframe is partially broken** — present in `config.candle_minutes`
  mapping but absent from `historical.py`'s valid `INTERVALS` set, so it would fail at
  the Kite historical-data call.
- **No position-level stop adjustment for splits/bonuses/corporate actions** — entry
  price and SL/target levels are computed purely from candle data; a corporate action
  during a held position would distort `_pct_gain`, SL, and target calculations.
- **Single Kite account / single capital pool** — no multi-account, no per-strategy
  capital partitioning beyond `max_capital_per_stock_pct`.
- **LIMIT order mode has no partial-fill handling** — paper-mode LIMIT fills are
  all-or-nothing at the limit price; live-mode partial fills aren't specifically
  reconciled beyond Kite's own `filled_quantity` reporting.
- **No options/futures, no basket orders, no algo order types (TWAP/VWAP/iceberg).**
- **Strategy retraining is synchronous and blocking** — `_train()` runs in the main
  candle-processing path; a slow `LogisticRegression.fit` on a large `lookback_bars`
  window for many instruments could introduce latency into live tick/candle handling
  (single-threaded `LiveFeed` candle dispatch).
- **No automatic universe rebalancing** — `watchlist`/`interested` are static config
  lists; adding/removing stocks is a manual config edit + restart (this is by design —
  see "Watchlist management" workflow — but means there's no live A/B testing of
  candidate stocks against the trading capital).

---

## 14. Key invariants / design decisions worth remembering

- Strategies are pure signal generators — no knowledge of capital, sizing, or order
  state. All of that lives in `RiskManager` + `OrderManager`.
- `EXIT` signals always bypass `RiskManager`'s conflict checks and use the
  *risk-tracked* quantity, not anything recomputed by the strategy.
- `signal_type` (`ENTRY`/`EXIT`) flows through `Order` → dispatched fill record →
  `strategy.on_order_update()` — this is the thread that keeps strategy-internal
  position state (`_entry_price`, `_held_bars`, `_peak_close`, `_trailing_active`)
  synchronized with what `RiskManager`/`OrderManager` believe is true.
- Warm-up (live and backtest) always runs candles through `on_candle()` with the
  resulting signals discarded, followed by an explicit phantom-state clear — this
  prevents "ghost" trailing stops from firing on the first real candle.
- Cost model (`trader/costs.py`) treats round-trip CNC cost as ~0.22% (mostly STT) —
  this is why calibration favours fewer, larger, higher-conviction trades over
  high-frequency churn.
