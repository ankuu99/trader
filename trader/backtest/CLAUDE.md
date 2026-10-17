# Backtest engine (`trader/backtest/engine.py`)

Loaded when working under `trader/backtest/`. Moved from the root CLAUDE.md 2026-10-17.

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

**`compute_metrics` notes:**
- `sharpe_proxy = mean(pnl) / std(pnl)` — relative ranking only, labelled "Sharpe*" in output
- `money_weighted_win_rate = total_win_amt / (total_win_amt + total_loss_amt) * 100` — win rate weighted by P&L amount, not trade count
- `max_drawdown` — largest peak-to-trough decline on the cumulative P&L equity curve (absolute ₹)
- `max_drawdown_pct` — max_drawdown as % of capital
- `kite=None` is supported — workers pass `kite=None` after candles are pre-fetched; engine operates in cache-only mode
- `model_scores` (optional sink dict) — when passed, the engine appends `{timestamp, close, p_min, p_max}` per strategy-TF decision bar per symbol via `strategy.score_current()` (pure, position-independent — the exact model the run traded with, same retrain cadence). In-memory only: the SQLite `model_scores` table stays live-only; zero cost when omitted (backtest.py/calibrate.py don't pass it; scripts/ui.py does)

**Trade record notes:**
- `held_candles` — number of candles the position was open (entry candle = 1); incremented per candle after order fill, before intrabar check; consistent across all exit paths (SL/TARGET intrabar, STRATEGY, OPEN@END); per-lot when scale-in add-ons exist
- `addon_tier` — 0 = parent lot; 1..N = scale-in add-on lots (one record per lot, shared exit)

**Reason values in trade records:** `SL`, `TARGET` (intrabar), `TRAILING` (trailing stop via on_tick), `STRATEGY` (strategy EXIT signal — hold_bars timeout), `PATTERN_TOP` (model detected local maximum while profitable), `OPEN@END`
