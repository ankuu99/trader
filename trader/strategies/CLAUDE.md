# LRExtremaStrategy mechanics (`trader/strategies/lr_extrema.py`, `trader/policy/`)

Loaded when working under `trader/strategies/`. Moved from the root CLAUDE.md 2026-10-17; the root keeps the design decisions, falsified experiments and the alternative detection stack.

## How it works — step by step

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
   - **Stale re-arm** (`exits.stale.rearm: {enabled, cur_floor_pct}`, **enabled 2026-08-16**): tier-1 stale keys on best-gain-since-entry and is one-shot — any early pop ≥ `min_gain_pct` disarms it for the life of the position (every deep-underwater backtest trade, 117/117, got there this way). With rearm on, the progress check re-runs at every `check_bars` multiple over a ROLLING window: EXIT (reason: `STALE_REARM`) iff best gain over the last `check_bars` bars < `min_gain_pct` AND current gain < `cur_floor_pct` (−2%). The current-loss condition spares dip-then-recover winners — recovery is real above −4%, so never tighten the floor there. VALIDATED: beats baseline 4/4 half-year windows 2025-01→2026-08 (+₹67k, 2025-H1 correction −16.2k → +2.7k); static per-trade sims understate it (freed capital redeploys)
   - **Pattern top exit**: `P(local-max) >= sell_threshold` AND `held_bars >= min_hold_before_exit` AND `gain >= sell_min_pct` → EXIT at current close (reason: `PATTERN_TOP`). Only fires when gain meets the minimum floor — stop_pct handles anything below. Supplements trailing stop; whichever fires first exits.

   **`target_price=None`** means the backtest engine's fixed intrabar target check is disabled (`target=0`) when `trail_pct` is configured — trailing and pattern-top are the sole upside exits.

7. **Retraining**: every `retrain_every` new candles, the model is retrained on the updated buffer. This lets it adapt to regime changes (trending vs ranging periods).

## Config params

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
