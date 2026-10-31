# Core Infrastructure — Module Reference

> Purpose: a ground-truth map of the **reusable infrastructure** in this codebase,
> documented independently of `LRExtremaStrategy`. Read this before building a new
> strategy framework (e.g. an inter-day/week/month fundamentals + technical system).
> It tells you what already exists, what the contracts are, and what is strategy-
> specific (and therefore replaceable) vs. truly generic plumbing.
>
> Scanned from `main.py`, `scripts/backtest.py`, and every module they touch.

---

## 0. The big picture — how a candle becomes a trade

There are **two entry points** that share the *same* domain objects (Strategy,
RiskManager, OrderManager, Store, costs):

```
LIVE  (main.py)                          BACKTEST (scripts/backtest.py → engine.py)
──────────────                           ────────────────────────────────────────
KiteTicker WebSocket ticks               Historical candles from SQLite/Kite
   → LiveFeed assembles candles             → engine merges all symbols chronologically
   → handle_candle(candle)                   → for each candle in time order:
       → orders.on_candle()  (paper fills)      → orders.on_candle() (paper fills)
       → strategy.on_candle() → Signal          → intrabar SL/target check
       → risk.validate(signal) → Order          → strategy.on_tick() (trailing sim)
       → orders.place(order)                     → strategy.on_candle() → Signal
   → handle_tick(tick)                           → risk.validate() → orders.place()
       → strategy.on_tick() → Signal
       → risk.validate() → orders.place()
```

**The crucial design invariant:** a Strategy is fed candles/ticks and emits
`Signal` objects; it *never* imports `orders/` or `risk/`. RiskManager turns a
Signal into a sized `Order`; OrderManager places/simulates the Order and dispatches
fill records back. This separation is what lets the *identical* strategy code run
in live and backtest. **Keep this contract in any new framework.**

Everything below is grouped as **(A) generic plumbing — reuse as-is**, and
**(B) coupled to LRExtrema — expect to rewrite/generalize**.

---

## A. GENERIC PLUMBING (reuse as-is for any strategy)

### A1. Auth — `trader/auth/session.py`
- `create_kite() -> KiteConnect`: builds a `KiteConnect`, sets the access token
  from `config.kite_access_token` (env var `KITE_ACCESS_TOKEN`), and validates it
  with a `kite.profile()` call. Raises `RuntimeError` with a clear "re-authenticate"
  message on missing/expired token.
- Token expires midnight IST; refreshed out-of-band (TOTP cron on EC2, see CLAUDE.md).
- **Fully reusable.** No strategy coupling.

### A2. Config — `trader/core/config.py`
- Singleton `config = _load()` reads `config/config.yaml` + `config/.env`.
  Required env: `KITE_API_KEY`, `KITE_API_SECRET`.
- `Config` exposes typed properties: `env`, `total_capital`, `max_risk_per_trade`,
  `daily_loss_limit`, `watchlist`, `interested`, `max_open_positions`, `gtt_enabled`,
  `order_type` (MARKET/LIMIT), `default_sl_pct`, `risk_reward`, `max_capital_per_stock`,
  `product` (hardcoded `"CNC"`), `candle_timeframe`, `candle_minutes`, `db_path`,
  `historical_cache_days`, `ui_enabled`/`ui_port`, `trading_start`/`trading_end`,
  `compounding`, `base_capital`.
- **Runtime capital override:** `set_effective_capital(amount)` rewrites
  `capital.total` in memory so all derived caps recompute. Used in live mode to cap
  to broker cash. `base_capital` preserves the original for compounding math.
- **Per-strategy params:**
  - `strategy_config(name)` → flattened params for a strategy.
  - `get_strategy_params(instrument, strategy_name)` → deep-merges `per_stock_params[instrument][strategy]` over the base, then flattens.
- **`flatten_strategy_params()` (lines 31–146): LRExtrema-specific.** It translates
  the nested human-facing YAML (`entry_gates:`, `exits:`, `model:`, `forward_label:`)
  into flat keys the LRExtrema strategy reads. **A new strategy will need its own
  flattening (or just read nested config directly).** The deep-merge + per-stock
  override machinery (`_deep_merge`, `get_strategy_params`) is generic and worth keeping.

### A3. Persistence — `trader/data/store.py`
SQLite wrapper; **all raw SQL lives here.** WAL mode, `Row` factory, context-managed
connections with commit/rollback. Tables:

| Table | Purpose | Reusable? |
|---|---|---|
| `candles` | OHLCV per (instrument, timeframe, timestamp). PK dedups. | ✅ generic |
| `orders` | full order lifecycle (status, mode, prices, timestamps) | ✅ generic |
| `trades` | filled trade legs linked to orders | ✅ generic |
| `open_positions` | paper-mode positions that survive restarts (+ live position metrics for UI) | ✅ mostly generic; some cols (peak_close, trailing_active, pattern_top_trailing) are exit-mechanism specific |
| `signals` | every signal validation event (accepted/rejected + reason) | ✅ generic |
| `state` | key→float KV store (`cumulative_pnl`, `<inst>.paused`, `<inst>.peak_close`, …) | ✅ generic |
| `model_scores` | per-candle (p_min, p_max) for the UI conviction sparkline | ⚠️ LRExtrema-specific shape (two probabilities) |

Key methods: `write_candle`/`write_candles`/`read_candles`/`latest_candle_timestamp`,
`upsert_order`, `write_trade`, `log_signal`, `get_state`/`set_state`/`read_state`/`delete_state`,
`upsert_open_position`/`update_position_metrics`/`update_position_quantity`/`delete_open_position`/`read_open_positions`,
`read_pending_live_orders`, `clear_backtest_data` (wipes candles/orders/trades/signals).
- Migrations are done inline via `ALTER TABLE ... ADD COLUMN` wrapped in try/except.
- Timestamps stored as naive-IST ISO strings (`_to_naive` strips tz).
- **Reuse the Store wholesale.** For a new strategy you'd likely (a) keep candles/
  orders/trades/signals/state untouched, (b) generalize `model_scores` if you want a
  different per-candle diagnostic, (c) maybe add a `fundamentals` table.

### A4. Historical data — `trader/data/historical.py`
- `get_candles(kite, store, token, instrument, timeframe, from_dt, to_dt)`:
  cache-first. Reads cached latest timestamp, fetches only the missing tail from
  Kite, persists, returns the full range from SQLite. `kite=None` ⇒ cache-only.
- `warm_up(kite, store, token, instrument, timeframe, lookback_days)`: ensures N
  days of recent candles are cached (called pre-market + at startup).
- Kite request caps handled via `_date_chunks` (60 days/req intraday, 2000/req day).
- `_fetch_with_retry`: exponential backoff on "Too many requests".
- Valid `INTERVALS`: minute, 3/5/10/15/30/60minute, **4hour**, day.
- **Fully reusable.** A weekly/monthly system would call this with `timeframe="day"`
  and resample, OR you add `"week"/"month"` handling (Kite has **no native week/month
  interval** — you fetch `day` data and aggregate to W/M yourself; note this).

### A5. Live feed — `trader/data/live.py`
- `LiveFeed(api_key, access_token, timeframe_minutes)`: wraps `KiteTicker`.
- Assembles ticks into candles bucketed to **9:15-IST-aligned** boundaries
  (`_candle_bucket`) so live OHLCV matches Kite historical OHLCV exactly.
- Per-candle volume = cumulative-day-volume delta (handles day-rollover reset).
- Registers handlers: `register_tick_handler`, `register_candle_handler`,
  `register_order_update_handler`. Lifecycle: `subscribe(tokens)`, `start(threaded)`,
  `stop`, `disconnect` (market close), `reconnect` (market open), `flush_partials`
  (force-emit in-progress candles at 15:30).
- Timezone handling: detects UTC servers (EC2) and shifts tick timestamps to IST.
- **Reusable for any intraday strategy.** For a pure daily/weekly/monthly system you
  may not need the WebSocket at all — you could run once-daily on the day's closed
  candle (a cron-driven batch rather than a streaming loop). Worth deciding early.

### A6. Costs — `trader/costs.py`
- `order_cost(product, side, quantity, price)` and
  `round_trip_cost(product, quantity, entry_price, exit_price)`.
- Zerodha CNC vs MIS: brokerage, STT, NSE txn, SEBI, GST, stamp. CNC brokerage = 0.
- **Cost dominance:** STT 0.1% each side for CNC ⇒ ~0.22% round-trip break-even.
  A swing/positional system clears this easily; a churning intraday one does not.
- **Fully reusable.** Any new framework should price trades through this.

### A7. Notifications — `trader/notifications/telegram.py`
- Functions: `notify_order_filled`, `notify_order_rejected`, `notify_order_queued`,
  `notify_daily_pnl`, `notify_halt`, `notify_error`, `notify_startup`,
  `notify_token_reminder`, `notify_positions_restored`, `notify_trailing_activated`,
  `notify_gtt_placed`. Safe when unconfigured. `telegram.disable()` mutes it
  (called by backtest/calibrate).
- **Reusable.** `notify_trailing_activated`/`notify_gtt_placed` are exit/GTT-specific
  but harmless; add your own event notifications as needed.

### A8. Scheduler — `trader/scheduler/jobs.py`
- APScheduler (BackgroundScheduler, IST). Hook registration:
  `on_pre_market` (09:00), `on_midday` (13:20), `on_market_close` (15:30),
  `on_post_market` (15:35), `on_heartbeat` (every 30 min during market hours).
  Plus a fixed 08:30 token-reminder job.
- **Reusable.** A daily/weekly system would mostly use `on_post_market` (run the
  strategy on the day's closed candle) and drop the intraday heartbeat.

### A9. Portfolio tracker — `trader/portfolio/tracker.py`
- Paper: tracks fills locally (`on_order_filled`). Live: `refresh()` pulls from
  `kite.positions()`. `log_summary()` logs unrealised/realised/net.
- Note: this is a **reporting** layer; capital/risk accounting authority lives in
  RiskManager, not here. **Reusable.**

### A10. UI — `trader/ui/`
- Read-only Flask dashboard, loopback-only, 30s meta-refresh. Renders from SQLite +
  `BotState`. **Must never import from `trader.backtest`** — shared analytics live in
  `trader/analytics.py` (`match_trades`, `compute_utilisation`, `drawdown_stats`,
  `exit_reason_breakdown`, `per_stock_scorecard`).
- Much of the *content* (conviction sparkline, P(buy)/P(sell), drivers) is LRExtrema-
  specific, but the **scaffolding** (date-range filter, equity/drawdown/utilisation
  charts, open-positions table) is generic.

---

## B. THE TRADING CORE (generic contract, some LRExtrema coupling)

### B1. Signal contract — `trader/strategies/base.py`
The **interface every strategy implements.** This is the most important contract to
preserve.

```python
class Strategy(ABC):
    def __init__(self, instrument, params)
    name (property)                       # required
    on_candle(candle) -> Signal | None    # required — entry/exit decisions
    on_tick(tick) -> Signal | None        # optional — tick-speed exits (default no-op)
    on_order_update(order) -> None        # update self.position on fill/reject
    seed_position_state(peak_close, max_gain_pct)  # restart restore (default no-op)
    is_flat() -> bool
    confirm_entry(direction) -> bool      # for confirmation-filter strategies
```

`Signal` dataclass fields:
`instrument, direction (BUY/SELL), signal_type (ENTRY/EXIT), price_hint, strategy,
atr?, target_price?, stop_loss_hint?, exit_reason?, timestamp?, size_weight?
(confidence sizing), exit_fraction? (scale-out)`.

- `on_order_update` default already handles position state: ENTRY fill → set
  `position`; full EXIT fill → clear; partial EXIT → leave open.
- **`seed_position_state(peak_close, max_gain_pct)` is exit-mechanism-specific
  naming** (trailing high-water mark) — generalize the signature if your exits differ.
- **For a new framework:** subclass `Strategy`, keep the Signal contract. The fields
  `size_weight`, `exit_fraction`, `atr`, `stop_loss_hint`, `target_price` are all
  generic and useful for a fundamentals+technical positional system. You can ignore
  what you don't use.

### B2. RiskManager — `trader/risk/manager.py`
Turns a `Signal` into a sized `Order`, enforces all risk gates, tracks capital & P&L.

`validate(signal) -> Order | None`:
- EXIT → `_validate_exit` (bypasses conflict checks; sells stored qty, or a fraction
  if `exit_fraction` set; exits allowed even when halted).
- ENTRY gates, in order: daily halt → trading window (`config.trading_start/end`) →
  max open positions (open + pending) → already in position → pending order exists →
  per-stock pause.
- **Sizing:** `sl_distance = price - sl_price`; `quantity = max_risk_per_trade // sl_distance`.
  SL comes from `signal.stop_loss_hint` else `default_sl_pct`. Then capped by:
  (1) `size_weight` (confidence multiplier), (2) `max_capital_per_stock` (compounding-
  aware), (3) `capital_available`. Rejects with `quantity_zero` / `sl_distance_zero`
  if degenerate.
- Target = `signal.target_price` else `price + sl_distance × risk_reward`.
- `_last_reject_reason` is set at every rejection point and surfaced in the UI.

Capital/P&L state:
- `_open_positions {inst: qty}`, `_position_values {inst: entry×qty}`, `_capital_deployed`,
  `_pending_orders {inst: expected_cost}` (pre-fill lock), `_realised_pnl` (daily),
  `_cumulative_pnl` (lifetime, persisted to `state` in live).
- `capital_available = total_capital + cumulative_pnl − deployed − pending`.
- `on_order_filled`, `close_position` (accrues realised + cumulative, triggers daily-
  loss halt), `reduce_position` (scale-out), `reset_day`.
- Restart seeding: `seed_cumulative_pnl`, `seed_realised_pnl`, `seed_position`,
  `seed_pending_order`.
- Pause: `pause`/`unpause`/`is_paused` (blocks new entries, never exits).

**This is almost entirely generic and excellent to reuse.** The only thing to
revisit for a positional/weekly system: the **fixed-%-stop sizing model**. A
fundamentals system might size by conviction/Kelly/equal-weight rather than
SL-distance. But `validate()` already supports `stop_loss_hint`, `target_price`, and
`size_weight`, so you can drive sizing from the signal without touching RiskManager.

### B3. OrderManager — `trader/orders/manager.py`
Places/simulates orders, dispatches normalized fill records to callbacks.

- `place(order)` → paper or live. `register_update_callback(cb)`.
- **Paper** (`_place_paper` + `on_candle`): queues order; MARKET fills at **next
  candle open**; LIMIT fills only if the candle touches the limit (low≤limit BUY /
  high≥limit SELL) at the limit price. `clear_pending()` cancels unfilled at EOD
  (dispatches CANCELLED so strategy/risk clean up).
- **Live** (`_place_live`): `kite.place_order` MARKET (market_protection=-1) or LIMIT
  (price=limit). On BUY-fill confirmation optionally places a **GTT OCO**
  (`_place_gtt_sl`, rebased to actual fill price). `gtt_enabled: false` currently.
- `on_kite_order_update`: normalizes KiteTicker postbacks; handles GTT fills (recovers
  context via `_instrument_orders`), cross-exchange/external SELL reconciliation by
  symbol, and forces SELL→EXIT signal_type.
- Dispatched record carries `signal_type`, `target_price`, `partial` so callbacks
  distinguish entry/exit/scale-out fills.

**Reusable.** GTT logic is optional (disabled). The paper-fill simulation is the key
piece that keeps backtest ≈ live.

### B4. Backtest engine — `trader/backtest/engine.py`
`run_backtest(kite, store, symbols, symbol_to_token, params, from_dt, to_dt, …)` →
list of trade dicts. `compute_metrics(trades, capital)` → metrics dict.

- **Fresh RiskManager + OrderManager(paper) + strategy instances per call** (no state
  leak). Multi-symbol: fetches all candles, merges into one chronological stream so
  RiskManager sees competing signals at the real timestamp.
- Pre-warmup window (`pre_warmup_days`, default `historical_cache_days`) trains the
  model before the scored window begins. Phantom warm-up entry state is cleared.
- **Exit simulation (always on):** intrabar SL/target via candle low/high at exact
  level (gap-adjusted to open if the candle gaps through); `on_tick` fed
  `high` then `close` to simulate trailing; an EOD synthetic tick at `trading_end`
  on the last in-window bar so live-style force-close fires.
- Daily boundary: LIMIT `clear_pending()` + `risk.reset_day()`.
- Trade record keys: `instrument, entry, exit, qty, pnl, cost, product, reason,
  entry_date, exit_date, held_candles`. Reasons: `SL, TARGET, TRAILING, STRATEGY,
  PATTERN_TOP, STALE, …, OPEN@END`.
- `compute_metrics`: total/wins/losses, win_rate, money_weighted_win_rate, total_pnl,
  return_pct, avg_win/loss, sharpe_proxy, sortino, calmar, profit_factor, max_drawdown
  (₹ and %), monthly_returns.

**⚠️ LRExtrema coupling to fix for a new strategy:**
- Line 24: `from trader.strategies.lr_extrema import LRExtremaStrategy` and it is the
  **default `strategy_cls`** (line 404). There IS a `strategy_cls` parameter to inject
  a different class — use it, or generalize the import.
- Regime feature injection (NIFTY/VIX `_regime_at`, 4h `ht_trend` `_htf_regime_at`,
  `htf_trend_regime` from `trader/features/indicators.py`) is wired into every candle
  dict (`_build_candle`). This is feature-engineering for LRExtrema; a new strategy
  can ignore those `_*` keys or you can strip them.
- The trailing/`on_tick` simulation and EOD force-close assume an intraday trailing-
  stop exit model. A daily/weekly positional system with end-of-day decisions may not
  need the tick simulation at all — but it's harmless (no-op `on_tick` returns None).

`scripts/backtest.py` is a thin CLI over the engine: parses dates/timeframe/symbols,
builds `per_symbol_params`, runs, then prints a rich ANSI summary (monthly/yearly
breakdown, exit-reason histogram, per-stock stacked bars, capital-utilisation table,
ASCII capital/position charts) and dumps a CSV to `backtest_results/`. All of that
presentation is reusable; none of it is strategy-specific beyond the exit-reason labels.

---

## C. main.py — the live wiring (read as the integration spec)

`main()` sequence:
1. `create_kite()`, `Store`, `RiskManager`.
2. Live only: fetch `kite.margins`, seed cumulative P&L from `state`.
3. `OrderManager`, `PortfolioTracker`, `BotState`.
4. Resolve instrument tokens from `kite.instruments("NSE")`; validate watchlist.
5. Restore per-stock pause flags from `state`.
6. `build_strategies(symbol, config)` per watchlist symbol (registry factory).
7. `warm_up()` candle cache (+ 4h cache if `ht_trend` gate enabled).
8. **Warm-up replay:** feed cached candles through `strategy.on_candle` (signals
   discarded) to train; backfill trailing-80 `model_scores` for the UI sparkline.
9. Clear phantom warm-up entry state (entry_price set but position None).
10. Restore open positions: paper from `open_positions` table (with missed-exit
    catch-up sweep); live reconciled against `kite.holdings()` + `kite.positions()`
    (T+0/T+1 CNC settlement states), seed realised P&L, re-lock pending orders, then
    `set_effective_capital(min(config, cash+deployed))`.
11. Start dashboard if enabled.
12. Register `handle_order_update` callback (routes BUY/SELL/partial fills to risk +
    portfolio + store + strategy + telegram).
13. Build `handle_candle` (orders.on_candle → store candle → per-strategy on_candle →
    persist model_scores + position metrics → log signal → risk.validate → orders.place)
    and `handle_tick` (per-strategy on_tick → validate → place).
14. Scheduler hooks (pre_market/midday/post_market/heartbeat/market_close).
15. `LiveFeed.subscribe/register/start`; in live also register
    `orders.on_kite_order_update` as the order-update handler.
16. Loop on `time.sleep(1)` until interrupt.

The HTF (4h) regime gate plumbing (`_get_htf_regime`, `_htf_close_time`) is
LRExtrema-feature support — skip for a new strategy.

---

## D. Recommendations for the new (fundamentals + technical, multi-timeframe) framework

1. **Keep the Strategy/Signal/RiskManager/OrderManager/Store/costs contract intact.**
   That separation is the most valuable asset here and is strategy-agnostic. Your new
   strategy is just a new `Strategy` subclass emitting `Signal`s.
2. **Decide the run model early.** LRExtrema is intraday-candle-driven (LiveFeed +
   tick exits). A weekly/monthly fundamentals system is more naturally a **daily batch**:
   run once after close on the day's candle, emit positional entries/exits. If so, you
   can bypass `LiveFeed`/`on_tick` and drive `handle_candle` from a scheduled
   `day`-timeframe fetch instead of the WebSocket. RiskManager/OrderManager/backtest
   engine still apply.
3. **Timeframe:** Kite has no native week/month interval — fetch `day` candles and
   aggregate to W/M yourself, or feed daily candles and let the strategy maintain
   higher-timeframe state internally (like LRExtrema does for 4h).
4. **Fundamentals data is new.** There's no fundamentals source today. Plan a new
   fetcher + a `fundamentals` table in Store (financials, ratios, events calendar).
   Keep it cache-first like `historical.py`.
5. **Sizing:** drive it from the Signal (`stop_loss_hint`, `target_price`,
   `size_weight`) so you don't have to modify RiskManager. If you need conviction/
   equal-weight/Kelly sizing, compute it in the strategy and pass `size_weight`, or
   extend RiskManager with an alternate sizing path behind a config flag.
6. **Backtest engine reuse:** pass `strategy_cls=YourStrategy` to `run_backtest` (the
   hook already exists). Generalize the hardcoded `LRExtremaStrategy` import and strip
   the NIFTY/VIX/4h regime injection if you don't want those `_*` candle keys.
7. **Config:** either write a new `flatten_strategy_params`-style mapper for your
   nested config, or have your strategy read nested config directly. Reuse
   `get_strategy_params` deep-merge + `per_stock_params` for per-stock overrides.
8. **`model_scores`/UI conviction** is two-probability-specific — generalize or drop
   for a non-classifier strategy.

### Quick reuse scorecard
| Module | Verdict |
|---|---|
| auth/session, costs, scheduler, historical, store (candles/orders/trades/signals/state), portfolio | **Reuse as-is** |
| live feed | Reuse if intraday; optional/skip for daily-batch |
| RiskManager, OrderManager, Strategy/Signal base | **Reuse contract**; tweak sizing via Signal |
| backtest engine | Reuse via `strategy_cls=`; strip LRExtrema import + regime injection |
| backtest.py reporting | Reuse presentation; relabel exit reasons |
| config `flatten_strategy_params`, `model_scores`, UI conviction, HTF/regime features | **LRExtrema-specific — rewrite or drop** |
| LRExtremaStrategy, registry, features/indicators | Replace entirely |
