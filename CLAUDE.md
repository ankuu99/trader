# Trader — Project Reference for Claude Agents

## What this is
An automated equity trading system for Indian markets (NSE) using Zerodha/Kite. Supports paper and live modes. Strategies emit signals; a risk layer sizes and places orders; a live WebSocket feed assembles candles.

The system is **long-only, delivery (CNC) only**, targeting multi-day swing trades on NSE-listed equities. It is not an intraday system.

---

## Running the system

```bash
python main.py                        # paper/live trading (uses config/config.yaml)
python main.py --config <path>        # alternate config
python scripts/backtest.py --from 2025-01-01 [--to 2025-12-31] [--timeframe 5minute|15minute|...]
python scripts/calibrate.py --from 2025-01-01 [--mode grid|random] [--iterations 50] [--workers N] [--params profit_pct stop_pct ...]
python scripts/backtest_rolling.py --from 2024-01-01 --to 2025-12-31 [--window 6] [--step 3] [--symbols NSE:X] [--timeframe ...]
python scripts/screen.py --from 2025-01-01 [--min-trades 2] [--output results.csv] [--timeframe ...]
python scripts/kite_auth_server.py    # refresh Kite access token (run on EC2, open URL in any browser)
```

---

## Project layout

```
trader/
├── main.py                        # entry point — wires everything together
├── config/
│   ├── config.yaml                # all runtime config (env, capital, strategies, risk)
│   └── .env                       # secrets: KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN,
│                                  #          TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
├── scripts/
│   ├── backtest.py                # standalone backtest runner (thin wrapper over engine)
│   ├── calibrate.py               # grid/random param search for LRExtremaStrategy
│   ├── screen.py                  # backtest LRExtrema against all NSE EQ stocks
│   ├── backtest_rolling.py        # rolling-window backtest — slides window across date range, consolidated output
│   ├── kite_auth_server.py        # OAuth flow — runs on EC2, works from any SSH client
│   ├── trader.service             # systemd unit file for EC2 deployment
│   └── test_telegram.py           # smoke test for Telegram notifications
└── trader/
    ├── auth/session.py            # create_kite() — authenticates and validates token
    ├── backtest/
    │   ├── __init__.py
    │   └── engine.py              # run_backtest() + compute_metrics() — shared by all scripts
    ├── core/
    │   ├── config.py              # Config class + singleton `config`
    │   └── logger.py              # get_logger(), setup()
    ├── costs.py                   # Zerodha brokerage calculator (CNC/MIS)
    ├── data/
    │   ├── historical.py          # get_candles(), warm_up() via Kite REST
    │   ├── live.py                # LiveFeed — KiteTicker WebSocket → candle assembly
    │   └── store.py               # SQLite via Store class (candles, orders, signals, state, model_scores tables)
    ├── notifications/telegram.py  # Telegram bot alerts (order fill, P&L, halt, error, token reminder)
    ├── orders/manager.py          # OrderManager — paper fill simulation + live Kite orders + GTT
    ├── portfolio/tracker.py       # PortfolioTracker — paper position tracking / live Kite fetch
    ├── risk/manager.py            # RiskManager — signal validation, position sizing, exit routing
    ├── scheduler/jobs.py          # APScheduler — pre-market (09:00), post-market (15:35), token reminder (08:30)
    └── strategies/
        ├── base.py                # Strategy ABC, Signal dataclass, Direction/SignalType enums
        ├── registry.py            # build_strategies(instrument, config) factory
        └── lr_extrema.py          # LRExtremaStrategy — self-training logistic regression
```

---

## Config keys (config/config.yaml)

```yaml
env: paper | live
candle_timeframe: 5minute | 15minute | 30minute | 60minute | day
capital:
  total: 50000
  max_risk_per_trade_pct: 7.0
  daily_loss_limit_pct: 10.0
watchlist:
  - NSE:SYMBOL
interested:          # instruments shown in UI but not traded
  - NSE:SYMBOL
strategies:
  <name>:
    enabled: true | false
    ...params
risk:
  gtt_enabled: true | false       # master GTT on/off switch
  order_type: market | limit      # live mode only; paper always fills at next candle open
  max_open_positions: 5
  default_sl_pct: 2               # fallback SL% when signal has no stop_loss_hint
  risk_reward: 4                  # fallback target multiplier when signal has no target_price
  max_capital_per_stock_pct: 25.0
data:
  db_path: data/market.db
  historical_cache_days: 90
```

---

## Core data flow

```
LiveFeed (KiteTicker ticks)
  └─ assemble candles by timeframe
      └─ handle_candle() in main.py
          ├─ orders.on_candle()         → fills pending paper orders at open price
          └─ strategy.on_candle()       → returns Signal | None
              └─ risk.validate(signal)  → returns Order | None
                  └─ orders.place(order)
                      ├─ paper: queues in _pending_paper (fills next candle open)
                      └─ live:  kite.place_order() + optional GTT OCO

LiveFeed (KiteTicker on_order_update) [live mode only]
  └─ orders.on_kite_order_update()
      └─ _dispatch(record)
          └─ handle_order_update() in main.py
              ├─ BUY fill → risk.on_order_filled(), portfolio.on_order_filled()
              ├─ SELL fill → risk.close_position()
              ├─ telegram.notify_order_filled()
              └─ strategy.on_order_update()   → updates strategy position state + _entry_price
```

---

## Signal contract

`Signal` fields (from `trader/strategies/base.py`):
- `instrument`: `"NSE:SYMBOL"`
- `direction`: `Direction.BUY | Direction.SELL`
- `signal_type`: `SignalType.ENTRY | SignalType.EXIT`
- `price_hint`: float — indicative price (LTP / candle close)
- `strategy`: str — strategy name
- `atr`: float | None — optional ATR for risk sizing
- `target_price`: float | None — if set, RiskManager uses this as target (overrides risk_reward fallback)
- `stop_loss_hint`: float | None — if set, RiskManager uses this as SL price (overrides default_sl_pct fallback)
- `exit_reason`: str | None — EXIT only; reason code forwarded to backtest trade record (e.g. `"PATTERN_TOP"`); defaults to `"STRATEGY"` if absent

**EXIT signals** bypass RiskManager's position-conflict check. RiskManager returns a SELL Order using the quantity stored from the original ENTRY fill.

**`signal_type` flows through the Order and dispatched record** — `strategy.on_order_update()` reads it to distinguish entry fills (sets `_entry_price`) from exit fills (clears state).

---

## Adding a new strategy

1. Create `trader/strategies/<name>.py` — subclass `Strategy`, implement `name` property and `on_candle(candle) -> Signal | None`
2. Register in `trader/strategies/registry.py` — add to `build_strategies()`
3. Add config block under `strategies:` in `config/config.yaml`

Key rules:
- Strategies never import from `orders/` or `risk/`
- Use `self.is_flat()` to gate entries
- Set `self._entry_price = price_hint` at signal time to guard against re-entry while awaiting fill; override with real fill price in `on_order_update()`
- Pass `stop_loss_hint` and `target_price` in the ENTRY signal so RiskManager and the backtest engine use the strategy's own levels rather than config fallbacks
- Override `on_order_update()` if strategy needs to track fill state (e.g. `_entry_price`)
- For strategy-driven exits: emit `Signal(direction=BUY, signal_type=EXIT, ...)`

---

## RiskManager behaviour

- ENTRY signals: checks halt, max positions, duplicate instrument → sizes quantity
- EXIT signals: skips conflict check → returns SELL Order with stored quantity
- `_open_positions: dict[str, int]` — instrument → quantity
- `_position_values: dict[str, float]` — instrument → entry_price × qty (for capital tracking)
- `_cumulative_pnl: float` — lifetime P&L, never resets; persisted to SQLite `state` table in live mode so it survives restarts
- `capital_available` property — `total_capital + cumulative_pnl - capital_deployed - pending`; quantity is capped so portfolio never over-deploys. In live mode `total_capital` is capped at startup by Kite available cash (see Known design decisions)
- `seed_cumulative_pnl(pnl)` — called on startup in live mode to restore cumulative P&L from the `state` table
- `cumulative_pnl` property — read-only access to `_cumulative_pnl`
- `on_order_filled()` records deployed capital; `close_position()` frees it and adds to `_cumulative_pnl`
- `_last_reject_reason` — set at each rejection point (`daily_halt`, `max_positions`, `already_in_position`, `pending_order_exists`, `sl_distance_zero`, `quantity_zero`); surfaced in UI signals table

---

## OrderManager behaviour

- **Paper mode**: queues orders in `_pending_paper`; MARKET fills at next candle open, LIMIT fills only if price touches the limit level during a candle (low <= limit for BUY, high >= limit for SELL); fill price = limit price exactly
- **Live mode**: places order via `kite.place_order()` with `order_type=MARKET` (uses `market_protection=-1`) or `order_type=LIMIT` (uses `price=limit_price`); optionally places GTT OCO after BUY fill confirmation
- **EOD cancellation (LIMIT mode)**: unfilled LIMIT orders are cancelled at day boundary — `clear_pending()` dispatches CANCELLED for each so strategy clears `_entry_price` and risk releases capital
- GTT only placed on BUY/ENTRY orders, never on SELL/EXIT orders
- Dispatched fill records include `signal_type` and `target_price` from the original Order so callbacks can distinguish entry vs exit fills

---

## Backtest engine (`trader/backtest/engine.py`)

Shared by `backtest.py`, `calibrate.py`, and `screen.py`. Never called in live trading.

```python
trades = run_backtest(kite, store, symbols, symbol_to_token, params, from_dt, to_dt)
metrics = compute_metrics(trades, capital)
```

**Key behaviours:**
- Fetches all symbol candles upfront, merges into a single chronological stream — multi-stock portfolio simulation is correct (RiskManager sees competing signals at the real timestamp)
- Calls `strategy.on_order_update()` after every paper fill so `_entry_price` is updated to the actual fill price
- **Intrabar SL/target simulation always active** — checks `candle["low"] <= sl_price` and `candle["high"] >= target_price` on every candle; exits at the exact SL/target price (not next-candle open). **Gap-adjusted fills**: if the candle opens through the SL/target level (overnight gap), exit price is `min(sl, candle["open"])` for SL and `max(target, candle["open"])` for TARGET — the exact level is used only when the candle opens on the safe side of it. Notifies strategy via `on_order_update` so internal state is reset
- **LIMIT fill simulation** — in LIMIT mode, entry orders only fill when price actually touches the limit level; unfilled orders persist across candles within the day and are cancelled at day boundary
- **Daily loss limit is per-day** — `risk.reset_day()` is called at every day boundary, so a daily-loss-limit halt on one day does not carry over to subsequent days
- SL/target prices come from the signal's `stop_loss_hint` / `target_price` (strategy-supplied), falling back to `trigger_price` / RR computation
- `hold_bars` exits fire at candle close (time-based, actual close price used)
- `store.clear_backtest_data()` — called by `backtest.py` only, not by engine

**`compute_metrics` returns:** `total_trades, wins, losses, win_rate, money_weighted_win_rate, total_pnl, return_pct, avg_win, avg_loss, sharpe_proxy, max_drawdown, max_drawdown_pct`
- `sharpe_proxy = mean(pnl) / std(pnl)` — relative ranking only, labelled "Sharpe*" in output
- `money_weighted_win_rate = total_win_amt / (total_win_amt + total_loss_amt) * 100` — win rate weighted by P&L amount, not trade count
- `max_drawdown` — largest peak-to-trough decline on the cumulative P&L equity curve (absolute ₹)
- `max_drawdown_pct` — max_drawdown as % of capital
- `kite=None` is supported — workers pass `kite=None` after candles are pre-fetched; engine operates in cache-only mode

**Trade record keys:** `instrument, entry, exit, qty, pnl, cost, product, reason, entry_date, exit_date, held_candles`
- `held_candles` — number of candles the position was open (entry candle = 1); incremented per candle after order fill, before intrabar check; consistent across all exit paths (SL/TARGET intrabar, STRATEGY, OPEN@END)

**Reason values in trade records:** `SL`, `TARGET` (intrabar), `TRAILING` (trailing stop via on_tick), `STRATEGY` (strategy EXIT signal — hold_bars timeout), `PATTERN_TOP` (model detected local maximum while profitable), `OPEN@END`

**UI (scripts/ui.py):**
- Tab 1 trade table shows `Hold (d)` (calendar days), `Candles` (held_candles), and `Capital` (effective capital at trade entry) side by side
- Tab 2 (per-instrument) also has the `Capital` column; both tabs support chart interaction:
  - **Box-select on equity curve** → filters trade table to the selected date range
  - **Click on entry/exit marker** → highlights the corresponding trade row in the table
- Tab 3 hold-duration scatter uses candles on x-axis; hours shown in hover tooltip
- `lookback_bars` is exposed as a sidebar input (same as `warmup_bars`, `threshold`, etc.)
- Default instrument selection is `watchlist` only (not `watchlist + interested`) — matches `backtest.py` behaviour

---

## LRExtremaStrategy — deep dive (`trader/strategies/lr_extrema.py`)

### What it does
LRExtremaStrategy is a **self-training swing entry detector**. It learns what local price minima look like on a given stock using historical candles, then fires a BUY signal when the current candle looks like a local minimum — i.e., the price is likely near a short-term bottom and about to bounce.

The model retrains itself every `retrain_every` candles using the most recent history, so it adapts to the stock's current behaviour over time.

### How it works — step by step

1. **Candle accumulation**: Every candle is appended to an internal buffer. The model does nothing until `warmup_bars` candles have been seen.

2. **Extrema detection (training labels)**:
   Scans the historical candle buffer for local minima and maxima using a neighbourhood half-window of `extrema_order` bars.
   - A candle is a **local minimum** (class 0 = buy candidate) if its close is lower than all closes within ±`extrema_order` bars.
   - A candle is a **local maximum** (class 1 = sell/exit candidate) if its close is higher than all closes within ±`extrema_order` bars.
   - All other candles are unlabelled and excluded from training.

3. **Feature engineering (6 features per candle)**:
   - `volume_ratio` — current candle volume ÷ rolling mean over last `volume_ma_bars` candles. Scale-invariant: a spike reads as e.g. 2.5× regardless of whether the stock's average volume is 50K or 5M.
   - `norm_price` — `(close - low) / (high - low)` — where within the bar did price close? 0 = at the low (bearish bar), 1 = at the high (bullish bar)
   - LR slope over last 3 **% returns**
   - LR slope over last 5 **% returns**
   - LR slope over last 10 **% returns**
   - LR slope over last 20 **% returns**

   Slopes are computed over first-order % returns (not absolute prices), making them stationary and comparable across price levels and time periods. A local minimum tends to appear at the end of a declining return-slope sequence before a reversal. Requires at least 21 closes (20 returns).

4. **Logistic regression classifier**:
   Trained on the labelled extrema candles. Predicts P(class 0) = probability that the current candle is a local minimum.

5. **Entry signal**:
   Two gates must both pass before a BUY is emitted:
   1. `P(local-min) >= threshold` — model thinks current candle is a local minimum
   2. `P(local-max) < veto_threshold` — model does NOT simultaneously think a top is forming

   On entry: `stop_loss_hint = close × (1 - stop_pct/100)`, `target_price = None` — no fixed target; trailing stop and model exit manage the upside.

6. **Exit conditions** — three independent mechanisms across two methods:

   **`on_tick` (tick-speed, live ~1 sec / backtest candle-close granularity):**
   - **Hard stop**: `last_price <= entry_price × (1 - stop_pct/100)` → EXIT immediately (fires regardless of P&L)
   - **Trailing stop activation**: once `last_price >= entry_price × (1 + profit_pct/100)`, trailing activates and `_peak_close` starts tracking the high-water mark
   - **Trailing stop exit**: once trailing is active, fires when `last_price <= _peak_close × (1 - trail_pct/100)`
   - In backtest: engine feeds `candle["high"]` then `candle["close"]` as simulated ticks — high updates `_peak_close`, close checks trail; hard SL still fires intrabar via engine's low-check at exact SL price

   **`on_candle` (candle-granularity):**
   - **Max hold**: held `hold_bars` candles → EXIT at current close (reason: `STRATEGY`)
   - **Pattern top exit**: `P(local-max) >= sell_threshold` AND `held_bars >= min_hold_before_exit` AND `gain >= sell_min_pct` → EXIT at current close (reason: `PATTERN_TOP`). Only fires when gain meets the minimum floor — stop_pct handles anything below. Supplements trailing stop; whichever fires first exits.

   **`target_price=None`** means the backtest engine's fixed intrabar target check is disabled (`target=0`) when `trail_pct` is configured — trailing and pattern-top are the sole upside exits.

7. **Retraining**: every `retrain_every` new candles, the model is retrained on the updated buffer. This lets it adapt to regime changes (trending vs ranging periods).

### Config params

| Key | Default | Meaning |
|-----|---------|---------|
| `warmup_bars` | 200 | Candles before first training |
| `lookback_bars` | 600 | Rolling training window — deque maxlen; candles older than this are dropped. Must be >= `warmup_bars`. |
| `threshold` | 0.70 | Min P(local-min) to trigger BUY entry (higher = more selective) |
| `profit_pct` | 3.0 | Minimum profit % floor before trailing activates (not a fixed target) |
| `trail_pct` | 1.5 | Trailing stop distance % from peak once trailing is active |
| `stop_pct` | 3.0 | Hard stop-loss % from entry price |
| `hold_bars` | 150 | Max candles to hold before time-based exit |
| `retrain_every` | 50 | Retrain every N new candles |
| `extrema_order` | 5 | Neighbourhood half-window for extrema detection |
| `sell_threshold` | 0.65 | Min P(local-max) to trigger pattern-top EXIT |
| `sell_min_pct` | 2.0 | Min profit % required before pattern-top EXIT can fire — prevents exiting on trivial gains; stop_pct handles anything below this |
| `veto_threshold` | 0.50 | Max P(local-max) allowed at entry — blocks entry if model thinks a top is forming simultaneously |
| `min_hold_before_exit` | 3 | Min held_bars before pattern-top exit can fire — prevents immediate U-turn after entry |
| `volume_ma_bars` | 20 | Rolling window for volume normalisation (volume_ratio = current / mean). Not sensitive; calibration not needed. |

### What makes this strategy work (and when it fails)

**Works well on stocks that:**
- Exhibit clear mean-reverting or oscillating price behaviour — price bounces between loose support/resistance levels rather than trending strongly in one direction
- Have consistent volume patterns — volume spikes at local extrema (a key feature)
- Have moderate volatility — enough to reach the profit target within `hold_bars` candles without constantly hitting the stop
- Have sufficient liquidity — thin stocks have wide spreads and erratic candle patterns that confuse the features
- Are not in a strong one-directional trend — a stock in a confirmed uptrend may have very few "local minima" and the model won't generalise well

**Fails on stocks that:**
- Are strongly trending (all entries look like local minima in a falling market)
- Have extremely low volume / liquidity (penny stocks with days of zero volume)
- Have highly irregular candle patterns driven by news/events rather than technical structure
- Are in a prolonged sideways range so narrow that neither profit_pct nor stop_pct is reached within hold_bars

### Calibration (`scripts/calibrate.py`)

Grid or random search over all strategy params. Pre-fetches candles once; subsequent runs hit SQLite cache. Results ranked by `return_pct`. Runs combinations in parallel via `ProcessPoolExecutor` (uses all CPUs by default).

Use calibration to find the optimal parameter set for a specific stock before adding it to the watchlist.

```bash
python scripts/calibrate.py --from 2025-01-01 --mode random --iterations 100
python scripts/calibrate.py --from 2025-01-01 --mode random --iterations 100 --workers 4
python scripts/calibrate.py --from 2025-01-01 --params profit_pct stop_pct trail_pct  # vary only specified params
python scripts/calibrate.py --from 2025-01-01 --params sell_threshold veto_threshold min_hold_before_exit
```

**CLI flags:**
- `--workers N` — number of parallel worker processes (default: CPU count)
- `--params PARAM [PARAM ...]` — restrict search to these params; remaining params are fixed at config values. Choices: `warmup_bars`, `lookback_bars`, `threshold`, `profit_pct`, `trail_pct`, `stop_pct`, `hold_bars`, `retrain_every`, `extrema_order`, `sell_threshold`, `veto_threshold`, `min_hold_before_exit`, `volume_ma_bars`
- `--timeframe` — override candle timeframe for this run
- Worker processes suppress all logging below `CRITICAL` (spawned processes don't inherit parent logging config)

### Screening (`scripts/screen.py`)

Backtests the current config params against all ~2,000 NSE EQ stocks. Resumable — already-processed symbols read from output CSV. Rate-limited to ~3 req/sec.

```bash
python scripts/screen.py --from 2025-01-01 --output results.csv --min-trades 3
```

---

## Stock selection guidance (for AI agents helping identify candidates)

### Goal
Find NSE-listed equity stocks where the LRExtremaStrategy has historically generated profitable trades with the current (or calibrated) parameters.

### Primary workflow
1. Run `screen.py` over a representative backtest period (minimum 6 months, ideally 1–2 years)
2. Filter the results CSV for candidates worth investigating further
3. Run `calibrate.py` on promising candidates to find their optimal parameters
4. Paper trade candidates for 2–4 weeks before adding to live watchlist

### Screening result interpretation

The output CSV has columns: `symbol, total_trades, wins, losses, win_rate, total_pnl, return_pct, avg_win, avg_loss, sharpe_proxy`

**Good candidate signals:**
- `return_pct > 5%` over the backtest period (net of all costs)
- `win_rate >= 50%` — the strategy should be right more often than wrong
- `total_trades >= 3` — enough trades to have statistical signal (not just one lucky trade)
- `avg_win / abs(avg_loss) > 1.5` — wins should be meaningfully larger than losses (R:R)
- `sharpe_proxy > 0.3` — consistent, not just a few big wins masking many losses

**Red flags to exclude:**
- `total_trades == 1` — a single trade result is noise
- `total_pnl > 0` but `win_rate < 30%` — one outlier win masking systematic losses
- Very high `total_trades` with low `return_pct` — churning; transaction costs eating gains
- Stocks with erratic volume (check manually — `screen.py` doesn't filter for this)

### Fundamental / market context to layer on top
The screener is purely quantitative. When shortlisting, also consider:
- **Sector momentum**: prefer stocks in sectors with broad market tailwind
- **Liquidity**: daily average volume should be at least ₹50L turnover to ensure LIMIT orders fill without slippage
- **Corporate events**: avoid stocks near earnings, AGM, bonus/split record dates — these create abnormal candle patterns that confuse the model
- **Price band**: stocks in T-group or trade-to-trade (BE) segment have settlement constraints — avoid
- **Promoter holding**: very low promoter holding stocks can be targets for pump-and-dump, generating false extrema signals

### Watchlist management
- `watchlist` in config.yaml — stocks actively traded by the system
- `interested` in config.yaml — stocks shown in the UI for monitoring but not traded
- Move a stock from `interested` to `watchlist` only after calibration + paper trading validation

---

## Costs (`trader/costs.py`)

```python
from trader.costs import order_cost, round_trip_cost
order_cost(product="CNC", side="BUY", quantity=100, price=500.0)
round_trip_cost(product="CNC", quantity=100, entry_price=500.0, exit_price=510.0)
```

Covers: brokerage, STT, NSE transaction charges, SEBI charges, GST, stamp duty. CNC brokerage = zero.

**Cost dominance:** STT is 0.1% on both buy and sell sides for CNC (0.2% round-trip). A trade must move ~0.22% just to break even. Favour high-threshold, high-profit-pct params in calibration to keep trade count low and move size large.

**MIS vs CNC in backtest:** engine detects same-day entry+exit and applies MIS charges; multi-day positions use CNC charges.

---

## Notifications (`trader/notifications/telegram.py`)

Configured via `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. Safe to call when unconfigured (logs warning, no crash).

Functions: `notify_order_filled`, `notify_order_rejected`, `notify_daily_pnl`, `notify_halt`, `notify_error`, `notify_startup`, `notify_token_reminder`

**Token reminder:** scheduler fires `notify_token_reminder()` at 08:30 IST daily — prompts to run `python scripts/kite_auth_server.py` on EC2 before market open.

---

## Cloud deployment (AWS EC2)

- Instance: t2.micro, ap-south-1 (Mumbai), Ubuntu 24.04 LTS
- Elastic IP: `13.202.187.191` — whitelist this in Zerodha API settings
- SSH port: 9654 (not 22)
- Service: `systemd` unit at `scripts/trader.service`, managed as `trader` user
- Deploy: `ssh trader "cd /opt/trader && sudo -u trader git pull && sudo systemctl restart trader"`
- Deploy with deps change: `ssh trader "cd /opt/trader && sudo -u trader git pull && sudo -u trader .venv/bin/pip install -r requirements.txt && sudo systemctl restart trader"`
- Token refresh: automated via TOTP cron (runs daily 08:15 IST). Manual fallback: `python scripts/kite_auth_server.py` on EC2
- KITE_ACCESS_TOKEN expires midnight IST — auto-refreshed by cron at 02:45 UTC (08:15 IST) via `scripts/kite_totp_refresh.py`

---

## Live dashboard (`trader/ui/`)

Read-only Flask dashboard served in a daemon thread, bound to `127.0.0.1` only (loopback); reached via SSH tunnel. Auto-refreshes every 30s (`<meta http-equiv="refresh">`). `template.py` renders the whole page as a Python f-string (CSS inlined); it queries SQLite directly via `_read_db()` (never the passed `store` object) and reads live runtime data from `bot_state`. `server.py` wires the routes.

- **Date-range filter** — a top-right control (`?range=1w|1m|1q|1y|all` or `?from=&to=`) filters every historical dataset (orders, closed trades, equity/drawdown/utilisation graphs, exit-reason breakdown, per-stock scorecard, signals). Lives in the URL query string so it survives the 30s meta-refresh; POST actions redirect to `request.referrer` to preserve it. FIFO `match_trades()` runs on the **full** order set first, then trades are filtered by exit time. Equity curve rebaselines to 0 at window start. Live cards (Capital, P&L Today, open positions, persistent state) stay "now" snapshots, unfiltered.
- **Open Positions** — each row has two side-by-side sparklines over the **same** entry→now window: **Price (since entry)** (`_render_sparkline`, candles `WHERE timestamp >= entry_time`) and **Model (since entry)** (`_render_prob_sparkline` over `model_scores WHERE timestamp >= entry_time`, per-stock threshold/veto guides). They share the date range; coverage degrades gracefully if the position predates the recorded scores (line starts later, or a dash under 2 points) and self-heals as live candles append.
- **Watchlist — what the model is saying:**
  - **P(buy) / P(sell)** — the model's *instantaneous* `(p_min, p_max)` for the latest candle, with threshold/veto markers and a decision badge (ENTRY-READY / VETOED / WAITING / WARMING / IN POSITION / PENDING / PAUSED).
  - **Conviction** column — dual-line sparkline of recent `P(buy)` (green) / `P(sell)` (red) over the last 80 persisted candles, on a **fixed 0..1 axis** with dotted threshold/veto guides. A flat line pinned at the ceiling reads as model saturation (the stale-model failure mode), not a strong signal. Data from the `model_scores` table (see Known design decisions — warm-up backfills the trailing 80 candles, then live candles append).
  - **P(buy) explainability tooltip** — hovering the P(buy) cell shows the top feature drivers of the latest prediction. For the linear `LogisticModel` these are signed pushes toward BUY (`feature_contributions()` = `-coef × scaled_value`); ▲ = toward BUY, ▼ = against. Non-linear models (MLP) fall back to raw feature values. Sourced from `strategy.last_feature_drivers()`, published into `bot_state.model_scores[sym]["drivers"]` by `main.py` each candle.
- **`render_page()` must never import from `trader.backtest`** — the live/UI path stays independent of the backtest engine; shared analytics live in `trader/analytics.py` (`match_trades`, `compute_utilisation`, `drawdown_stats`, `exit_reason_breakdown`, `per_stock_scorecard`).

---

## Known design decisions

- **Product is always CNC** (delivery) — hardcoded in `Config.product`. No intraday/MIS support.
- **Long-only** — all signals are BUY direction. No short selling.
- **Paper state is in-memory** — does not survive restarts. Live mode re-fetches from Kite on startup.
- **Paper fill timing** — ENTRY orders fill at next candle open (realistic slippage). EXIT orders (stop/target) are simulated intrabar in the backtest engine at the exact SL/target price; in live mode orders fill within seconds.
- **Strategy exit price_hint** — trailing/stop exits set `price_hint` to the tick `last_price` at the moment of exit; time-based (hold_bars) exits use candle close.
- **Tick-speed exits (`on_tick`)** — hard stop and trailing stop are checked on every raw Kite tick in live mode (~1 sec granularity). `on_candle` handles entry signals, hold_bars timeout, and pattern-top exit. In backtest the engine simulates ticks by calling `strategy.on_tick` with `candle["high"]` then `candle["close"]` per candle. Hard SL still fires intrabar at the exact low price via the engine's own check. Trailing exits record as reason `"TRAILING"` in the trades list. `_peak_close` (the trailing high-water mark) is in-memory only and resets to current price on restart — see todo.md.
- **Pattern-top exit** — fires in `on_candle` when `P(local-max) >= sell_threshold`, `held_bars >= min_hold_before_exit`, and `close > entry_price`. Reason: `"PATTERN_TOP"`. Does not fire when underwater — stop_pct handles that. Supplements trailing stop; both can be active simultaneously and whichever fires first wins. Features (return-based slopes + volume ratio) are the same as used for entry, making the model's buy/sell predictions symmetric.
- **Warmup phantom-state clearing** — both the backtest engine (`engine.py`) and live startup (`main.py`) feed historical candles through `on_candle` before trading begins; this can trigger signals that never receive a fill, leaving `_entry_price`, `_held_bars`, `_peak_close`, and `_trailing_active` in a stale state. Both paths explicitly clear all four fields when `_entry_price is not None and position is None` at the end of warmup, preventing phantom trailing-stop exits on the first real trade.
- **GTT is disabled (`gtt_enabled: false`)** — strategy exit logic (profit%, stop%, hold_bars) is the sole exit mechanism in live trading, consistent with backtest behaviour. GTT was disabled because: (1) backtest never uses GTT so enabling it creates a live/backtest divergence; (2) GTT-triggered exits were not confirmed via `on_order_update`, leaving strategy state inconsistent after a GTT fire. Safety net is `Restart=always` + `RestartSec=10` in the systemd unit — bot restarts within 10s on any failure and resumes exit monitoring on the next candle.
- **Scheduler timezone** — IST (Asia/Kolkata). Pre-market at 09:00, post-market at 15:35.
- **Backtest engine is backtest-only** — `trader/backtest/engine.py` is never imported in live trading paths.
- **Effective capital in live mode** — on startup, `main.py` fetches `kite.margins(segment="equity")` and applies `effective_capital = min(config.total_capital, kite_available_cash)` via `config.set_effective_capital()`. This ensures the bot never tries to deploy more money than is actually in the account while still respecting the config ceiling. All derived values (`daily_loss_limit`, `max_risk_per_trade`, `max_capital_per_stock`) update automatically since they derive from `config.total_capital`. Paper mode is unaffected — it always uses the config value as-is. If the margins call fails, the system falls back to config capital and logs a warning.
- **Cumulative P&L persistence** — `RiskManager._cumulative_pnl` is persisted to the SQLite `state` table (key `cumulative_pnl`) in live mode via `store.set_state()` on each close. On startup, `main.py` restores it via `risk.seed_cumulative_pnl(store.get_state("cumulative_pnl"))`. This ensures `capital_available` is correct across restarts (deployed capital freed + lifetime P&L tracked). Paper mode does not persist — resets to 0 on restart.
- **`state` table in SQLite** — `store.get_state(key, default=0.0)` and `store.set_state(key, value)` provide a simple key/float persistence layer. Used for `cumulative_pnl` and per-stock pause flags (`<instrument>.paused`).
- **`model_scores` table in SQLite** — persists the model's `(p_min, p_max)` per candle for the dashboard's conviction-trajectory sparkline. Written in `main.py`'s `handle_candle` once the model is trained, via `store.write_model_score(instrument, timestamp, p_min, p_max)` (keyed on `(instrument, timestamp)`, trimmed to the last 500 rows per instrument). Read by the UI via `store.get_model_scores(instrument, limit)`. **Warm-up backfills the trailing 80 candles** (`_CONVICTION_BACKFILL` in `main.py`) so the sparkline is populated immediately on startup rather than growing in over the first ~80 live candles; because the model retrains progressively through warm-up, each backfilled score mirrors what live would have recorded at that point (no seam with the live points that follow). Only the trailing window is persisted — the sparkline shows 80, and writing all ~1,200 warm-up candles per symbol would be wasteful. The write is wrapped in try/except — purely cosmetic, a persistence failure never disturbs warm-up or the trading path. Backtest never writes it (consistent with "engine is backtest-only").

---

## Zerodha CNC order EOD rules (important)

| Order type | Used by this system | EOD behaviour |
|---|---|---|
| CNC Limit | Yes (when `order_type: limit`) | Cancelled at 3:30 PM if unfilled — simulated in backtest at day boundary |
| CNC SL / SL-M | No | Cancelled at 3:30 PM — must re-place next day |
| CNC Market | Yes (when `order_type: market`) | Fills immediately during market hours — no cancellation risk |
| GTT (Good Till Triggered) | **Disabled** (`gtt_enabled: false`) | Persists across days — not cancelled at EOD |

**Paper vs live simulation mismatch for end-of-day signals:**
In live mode a market order placed at e.g. 15:15 fills within seconds (same day). In paper mode the same signal queues and fills at the **next candle's open** (next trading day 09:15 if it's the last candle of the day). This means:
- Paper mode overstates overnight gap risk for entry signals that fire during market hours
- Backtest P&L will be slightly more pessimistic than live for late-day entry signals
- This is an accepted approximation — fixing it would require intraday fill simulation
