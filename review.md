# Live Trading Readiness Review

Reviewed: `trader/` and `main.py` on branch `simple_trader`.
Focus: logic correctness, state consistency, and real-money safety.

---

## CRITICAL — Must fix before going live

### 1. ✅ Daily loss limit is never enforced — FIXED
**File:** `trader/risk/manager.py` — `RiskManager` class

`_realised_pnl` is initialised to `0.0` and never updated anywhere. `_halted` is never set to `True`. The `daily_loss_limit` property exists in `Config` but is never read by `RiskManager.validate()` or any other method. `close_position()` frees capital but does not compute or accumulate the trade's P&L.

**Impact:** The system will keep placing orders regardless of how much money has been lost in a single day. The `notify_halt()` Telegram function exists but is never called.

**Fix:** In `close_position()`, accept `exit_price` and compute realised P&L. In `validate()`, check `_realised_pnl <= -daily_loss_limit` and set `_halted = True` + call `notify_halt()`.

---

### 2. ✅ GTT is never cancelled on strategy-driven exit — FIXED
**File:** `trader/orders/manager.py` — `_place_live()`

When a strategy emits an EXIT signal and the position is closed via a market SELL order, the GTT OCO that was placed on entry remains active on Zerodha's servers. If price later reaches the GTT trigger, it fires a second SELL on a position that no longer exists.

- For CNC, Zerodha may reject the sell (no holdings), but the behaviour is undefined and broker-dependent.
- No GTT ID is stored anywhere after placement, so there is no way to cancel it later.

**Fix:** Store the GTT trigger ID returned by `_place_gtt_sl()` (keyed by instrument). When a SELL/EXIT order completes, call `kite.delete_gtt(trigger_id)` to cancel the orphaned GTT.

---

### 3. ✅ Strategy `_entry_price` is never cleared on order rejection — FIXED
**File:** `trader/strategies/lr_extrema.py:124` and `trader/strategies/base.py:91-93`

When a BUY signal is emitted, `_entry_price` is set to `close` immediately (line 124) as a re-entry guard. If the live order is then REJECTED by the broker (insufficient margin, circuit limits, etc.), `on_order_update()` only handles `COMPLETE` status — `REJECTED` is a no-op in both the base class and `LRExtremaStrategy`.

**Impact:** After a single rejection, `_entry_price` stays set permanently. The strategy will never emit another ENTRY signal for this instrument until the process restarts.

**Fix:** In `LRExtremaStrategy.on_order_update()`, add handling for REJECTED/CANCELLED on ENTRY signals to clear `_entry_price`.

---

### 4. ✅ GTT-triggered fills lose all strategy context — FIXED
**File:** `trader/orders/manager.py` — `on_kite_order_update()`

When a GTT fires, Zerodha creates a new order with a new `order_id`. This order ID is not in `_live_orders`, so `original` is `None` (line 91). Consequences:

- `strategy` becomes `""` — the strategy's `on_order_update()` is never called
- `signal_type` becomes `None` — `handle_order_update` in `main.py` can't distinguish entry from exit
- The strategy's `_entry_price` and `position` are never reset, blocking future entries

**Impact:** After a GTT exit, the strategy is stuck in "in-position" state until restart.

**Fix:** Maintain a mapping of `instrument → original Order` (alongside the `order_id → Order` map) so that GTT fills can be matched back to the original entry context.

---

### 5. ✅ Last candle of the day is never emitted — FIXED
**File:** `trader/data/live.py:151-154` — `_process_tick()`

A completed candle is only emitted when the first tick of the *next* candle bucket arrives. The final candle of the trading day (e.g. 15:15–15:30 for 15-minute, or 15:00–16:00 for 60-minute) is never closed because no new tick arrives until 09:15 the next day.

**Impact:** Any exit signal that would fire on the last candle is delayed by ~18 hours. For a CNC long-only system the main risk is missing an end-of-day exit signal, though this is mitigated by the strategy using GTT for SL/target.

**Fix:** Add a scheduled job (or timer) that force-flushes all partial candles at 15:30 IST.

---

### 6. ✅ Live-mode P&L summary is always zero — FIXED
**File:** `trader/portfolio/tracker.py:35-36` and `main.py:133-142`

`PortfolioTracker.on_order_filled()` returns immediately in live mode (`if self._mode != "paper": return`). The `post_market()` function reads `portfolio._positions` to compute daily P&L, but this dict is empty because `portfolio.refresh()` is never called before the summary.

**Impact:** The daily Telegram P&L notification in live mode will always report `₹0.00`.

**Fix:** Call `portfolio.refresh()` at the start of `post_market()` when in live mode.

---

## HIGH — Significant logic issues

### 7. ✅ Volume feature is wrong in live mode — FIXED
**File:** `trader/data/live.py:169`

```python
partial["volume"] = volume  # Kite sends cumulative volume
```

Kite's `volume_traded` is cumulative for the day. The candle's `volume` field will contain the total day volume at candle close, not the volume traded during that candle's time window. The LR Extrema strategy uses volume as a feature for its logistic regression model.

**Impact:** The model is trained on historical per-candle volume (from Kite's REST API) but scores on cumulative day volume in live mode. This is a train/serve skew that will degrade prediction accuracy, especially later in the day when cumulative volume diverges most from candle volume.

**Fix:** Compute delta volume: `partial["volume"] = volume - self._last_day_volume.get(token, 0)`, resetting at day boundary.

---

### 8. ✅ Backtest: SL always wins when both SL and target hit same candle — FIXED
**File:** `trader/backtest/engine.py:179-180`

```python
sl_hit = pos["sl"] > 0 and candle["low"] <= pos["sl"]
tgt_hit = pos["target"] > 0 and candle["high"] >= pos["target"]
if sl_hit or tgt_hit:
    exit_price, reason = (pos["sl"], "SL") if sl_hit else (pos["target"], "TARGET")
```

When a candle's range spans both the SL and target price, SL is always chosen. This creates a pessimistic bias in backtest results. In reality, either could have been hit first depending on intrabar price action.

**Impact:** Backtest P&L understates actual performance. Calibration may over-fit to avoid this artefact (wider stops, higher targets).

**Fix:** When both trigger in the same candle, use the one closer to the open price (heuristic for which triggered first), or log it as ambiguous.

---

### 9. ✅ `handle_order_update` in `main.py` ignores REJECTED orders — FIXED (addressed by fix #3)
**File:** `main.py:77`

```python
if update.get("status") != "COMPLETE":
    return
```

REJECTED and CANCELLED statuses are silently dropped. In live mode, `on_kite_order_update` dispatches these, but `handle_order_update` exits early.

- `risk.on_order_filled()` is never called (correct — no fill happened)
- But no notification is sent to alert the user that a signal was lost
- Combined with issue #3, the strategy is now permanently stuck

**Fix:** For REJECTED/CANCELLED, call `telegram.notify_order_rejected()` and propagate to the strategy's `on_order_update()` so it can clear its guard state.

---

### 10. ✅ Open positions lost on restart (paper mode) — FIXED (live mode reconciled from Kite on startup)
**File:** `trader/risk/manager.py` — `__init__`

`_open_positions`, `_position_values`, and `_capital_deployed` are all in-memory with no persistence. After a crash or restart:

- RiskManager thinks all capital is available — could over-deploy
- Strategy `_entry_price` is reset to `None` — will re-enter positions already held
- Result: duplicate BUY orders on stocks already in portfolio

**Impact:** In live mode, Kite will happily fill a second BUY, doubling the position. No reconciliation with actual broker positions exists at startup.

**Fix:** On startup in live mode, call `kite.positions()` to seed `_open_positions` and `_capital_deployed`. Also reconcile strategy state from the database or broker.

---

## MEDIUM — Should fix

### 11. ✅ `max_capital_per_stock_pct` is set to 100% — ALREADY FIXED (config.yaml has 10.0%)
**File:** `config/config.yaml:47`

A single trade can consume all available capital. Combined with `max_risk_per_trade_pct: 7.0` and a tight stop of 2.5%, the risk-based sizing can produce positions worth significantly more than the total capital (capped only by available capital).

**Recommendation:** Set to 20-30% for multi-stock diversification unless single-stock concentration is intentional.

---

### 12. Watchlist contains BZ-group stocks
**File:** `config/config.yaml:13`

`NSE:SUPREMEENG-BZ` and `NSE:OMKARCHEM-BZ` are in the BZ (trade-to-trade) group. These stocks are typically illiquid with wide bid-ask spreads. Market orders can fill at prices far from the signal's `price_hint`.

**Recommendation:** Review whether these are intentional. If so, consider using LIMIT orders for BZ stocks.

---

### 13. No order timeout or stale-order cleanup
**File:** `trader/orders/manager.py`

In live mode, once an order is placed, there is no mechanism to detect if it stays in PENDING/OPEN state indefinitely (e.g., exchange connectivity issues). `_live_orders` will accumulate stale entries.

**Recommendation:** Add a periodic check that flags orders stuck in non-terminal states for longer than N minutes.

---

### 14. ✅ SQLite under concurrent access from WebSocket thread — FIXED (WAL mode + NORMAL sync)
**File:** `trader/data/store.py`

The Store creates a new `sqlite3.connect()` per call. In live mode, tick processing, candle handlers, and order update handlers can fire concurrently from the WebSocket thread. SQLite's file-level locking can produce `database is locked` errors under contention.

**Recommendation:** Use a single persistent connection with WAL mode (`PRAGMA journal_mode=WAL`), or serialize writes through a queue.

---

### 15. `_candle_bucket` breaks for `day` timeframe
**File:** `trader/data/live.py:188-191`

```python
def _candle_bucket(self, ts: datetime) -> datetime:
    minute = (ts.minute // self._timeframe) * self._timeframe
    return ts.replace(minute=minute, second=0, microsecond=0)
```

For `day` timeframe, `candle_minutes` = 390. `ts.minute // 390` = 0 always, so every tick maps to the same bucket (minute=0 of whatever hour). The candle is never emitted because `candle_start` never advances within the day.

**Impact:** No daily candle is ever emitted in live mode if using `day` timeframe. Currently mitigated because config uses `60minute`.

---

### 16. ✅ `post_market` P&L calculation is incorrect even in paper mode — FIXED
**File:** `main.py:135-138`

```python
positions = [p for p in portfolio._positions.values() if p.quantity != 0]
telegram.notify_daily_pnl(
    realised=sum(p.realised_pnl for p in positions),
    ...
)
```

`PortfolioTracker.on_order_filled()` creates a new `Position` with `realised_pnl=0.0` on every fill. SELL fills overwrite the position (same instrument key) with a new `Position` that also has `realised_pnl=0.0`. Realised P&L is never computed.

**Impact:** Daily P&L Telegram notification always shows `₹0.00` for realised P&L in paper mode too.

---

## LOW — Minor issues

### 17. RiskManager log message shows `config.risk_reward` even when using signal-supplied target
**File:** `trader/risk/manager.py:113-115`

The log message always prints `RR=%.1f` from `config.risk_reward`, even when the target was taken from `signal.target_price`. Misleading in logs.

---

### 18. ✅ `handle_candle` in `main.py` does O(N) scan for symbol lookup — FIXED
**File:** `main.py:99-101`

```python
symbol = next(
    (s for s, t in symbol_to_token.items() if t == candle.get("instrument_token")),
    None,
)
```

Builds a reverse lookup on every candle. Should use a pre-built `token_to_symbol` dict.

---

### 19. Exit Signal uses `direction=Direction.BUY` for a SELL action
**File:** `trader/strategies/lr_extrema.py:94`

The EXIT signal is emitted with `direction=Direction.BUY`, which is counterintuitive. `RiskManager._validate_exit()` overrides it to `Direction.SELL` in the Order. The CLAUDE.md documents this as intentional, but it creates a mismatch between Signal semantics and Order semantics that could confuse future development.

---

### 20. No graceful handling of Kite token expiry mid-session
**File:** `trader/auth/session.py`

Token is validated once at startup. If the token expires or is invalidated during the session (e.g., user logs in elsewhere), all API calls will fail silently or with exceptions. The WebSocket will disconnect and attempt to reconnect, but reconnection will also fail with an invalid token.

**Recommendation:** Catch `TokenException` in critical paths and send a Telegram alert prompting token refresh.

---

## Round 1 Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 6 | All marked ✅ |
| HIGH | 4 | All marked ✅ |
| MEDIUM | 6 | 3 fixed, 3 remain (#12, #13, #15) |
| LOW | 4 | 1 fixed, 3 remain (#17, #19, #20) |

---
---

# Round 2 Review — Post-fix

Reviewed all files in their current state after round 1 fixes were applied.
Focus: interaction bugs, edge cases under live conditions, and incomplete fixes.

---

## CRITICAL — Must fix before going live

### R2-1. ✅ GTT fill recovery assigns wrong `signal_type` — strategy stuck after GTT exit — FIXED
**File:** `trader/orders/manager.py:113-118` — `on_kite_order_update()`

When a GTT fires a SELL, the code recovers the original Order from `_instrument_orders`. But that Order is the original BUY ENTRY order, so `original.signal_type == SignalType.ENTRY`. The recovery code:

```python
if original is not None:
    recovered_signal_type = original.signal_type   # ← ENTRY, not EXIT
```

This dispatches to `handle_order_update` → `strat.on_order_update()` with `signal_type=ENTRY` + `direction="SELL"`. In the base class (`base.py:87-88`):

```python
if signal_type == SignalType.ENTRY:
    self.position = Direction(direction)   # ← sets self.position = Direction.SELL
```

In `lr_extrema.py:146-151`:

```python
if signal_type == SignalType.ENTRY:
    fill_price = order.get("price") or order.get("average_price")
    if fill_price:
        self._entry_price = float(fill_price)   # ← set to the EXIT price
```

**After a GTT SELL fires:**
- `self.position = Direction.SELL` (wrong — should be `None`)
- `self._entry_price = exit_fill_price` (wrong — should be `None`)
- `self.is_flat()` returns `False` forever
- Strategy never enters or exits again — permanently stuck

**Fix:** The recovery logic must override `signal_type` based on the fill direction. When `original` comes from `_instrument_orders` and the fill direction is `SELL`, force `recovered_signal_type = SignalType.EXIT`:

```python
if original is not None:
    if direction == "SELL" and original.signal_type == SignalType.ENTRY:
        recovered_signal_type = SignalType.EXIT
    else:
        recovered_signal_type = original.signal_type
```

---

### R2-2. ✅ Volume baseline never resets at day boundary — all candle volumes become 0 after first day — FIXED
**File:** `trader/data/live.py:160-172` — `_process_tick()`

When the market opens the next day, Kite resets `volume_traded` to near-zero. But `_vol_last[token]` still holds yesterday's final cumulative volume (e.g. 50,000,000). The new candle's volume is computed as:

```python
last_cumulative = self._vol_last.get(token, 0)   # 50_000_000
self._vol_baseline[token] = last_cumulative       # 50_000_000
"volume": max(0, volume - last_cumulative)         # max(0, 1000 - 50_000_000) = 0
```

**Impact:** From day 2 onward, every candle has `volume = 0`. The LR Extrema model's volume feature is always 0, degrading predictions. This undoes the round 1 volume fix — the delta logic is correct within a single day, but fails across the overnight boundary.

**Fix:** Detect the day boundary (when `volume < _vol_last[token]`, the cumulative has reset) and zero the baseline:

```python
last_cumulative = self._vol_last.get(token, 0)
if volume < last_cumulative:
    last_cumulative = 0   # day boundary: cumulative reset
self._vol_baseline[token] = last_cumulative
```

---

### R2-3. ✅ Strategies receive no historical candles — dead for 200+ bars after startup — FIXED
**File:** `main.py:156-161` (pre_market) and `trader/strategies/lr_extrema.py:101`

`pre_market()` calls `warm_up()` which caches historical candles in SQLite. But these candles are **never fed to the strategies**. The LR Extrema strategy only receives candles from the live WebSocket (starting at 09:15).

With `warmup_bars=200` and `candle_timeframe=60minute` (~6 candles/day), the strategy needs **33+ trading days** before it can train its model and emit any signal.

**Impact:** After every startup or restart, the strategy is completely silent for over a month. No entries, no exits, no signals of any kind.

**Fix:** After building strategies, read the cached candles from the store and replay them through each strategy's `on_candle()` (without acting on any signals) to warm up internal state:

```python
for symbol in valid_watchlist:
    df = store.read_candles(symbol, config.candle_timeframe, warmup_from, now)
    for strat in strategies:
        if strat.instrument == symbol:
            for _, row in df.iterrows():
                strat.on_candle(row.to_dict())  # warm up only, ignore signals
```

---

### R2-4. ✅ Halt blocks EXIT signals — traps losing positions — FIXED
**File:** `trader/risk/manager.py:47-50` — `validate()`

```python
if self._halted:
    logger.warning("Signal rejected — daily halt | %s", signal.instrument)
    return None
```

This rejects ALL signals including EXIT signals. When the daily loss limit is breached:
- No new entries can be placed (correct)
- No exits can be placed either (dangerous)
- Open positions continue to lose money with no way to exit
- GTT is the only safety net, but `gtt_enabled: false` in current config

**Impact:** After a halt, losing positions are trapped until GTT fires (if enabled) or until the next day's reset. This directly contradicts the purpose of a daily loss limit.

**Fix:** Allow EXIT signals through even when halted:

```python
if self._halted:
    if signal.signal_type == SignalType.EXIT:
        return self._validate_exit(signal)   # exits must always be allowed
    logger.warning("Signal rejected — daily halt | %s", signal.instrument)
    return None
```

---

### R2-5. ✅ `_place_live` exception leaves strategy permanently stuck — FIXED
**File:** `trader/orders/manager.py:215-217` and `trader/strategies/lr_extrema.py:124`

When `kite.place_order()` raises (network error, API down, rate limit), the exception propagates up through `orders.place()` → `handle_candle()` → `LiveFeed._emit_candle()` which catches it silently.

At this point the strategy has already set `_entry_price = close` (line 124 of lr_extrema.py), but:
- No order was placed, so no fill callback will arrive
- No REJECTED status will be dispatched (the order never reached Kite)
- `_entry_price` stays set permanently, blocking all future entries

This is the same class of bug as round 1 #3, but triggered via exception rather than rejection.

**Fix:** Either wrap `orders.place()` in `handle_candle` with a try/except that dispatches a synthetic REJECTED update to the strategy, or have `_place_live` catch the exception internally and dispatch a REJECTED record before re-raising.

---

## HIGH — Significant logic issues

### R2-6. ✅ Paper-mode P&L lost when same instrument is re-bought — FIXED
**File:** `trader/portfolio/tracker.py:38-57`

If you BUY RELIANCE (position created with `realised_pnl=0`), then SELL (position updated with `realised_pnl=500`), then BUY RELIANCE again:

```python
self._positions[symbol] = Position(
    instrument=symbol, quantity=quantity,
    average_price=fill_price,
)   # realised_pnl defaults to 0.0 — overwrites the previous 500
```

The `post_market` P&L sum will miss the first trade's realised P&L.

**Impact:** Paper-mode daily P&L Telegram notification understates actual performance. Only the last trade per instrument is reflected.

**Fix:** Accumulate realised P&L across trades. Either keep a running total separate from the Position, or add to the existing `realised_pnl` rather than overwriting:

```python
prior_pnl = self._positions.get(symbol)
prior_realised = prior_pnl.realised_pnl if prior_pnl else 0.0
self._positions[symbol] = Position(
    ..., realised_pnl=prior_realised,
)
```

---

### R2-7. ✅ `close_position` silently skips P&L when `exit_price` is 0 — FIXED
**File:** `trader/risk/manager.py:185-186`

```python
if qty and exit_price and freed:
```

`exit_price` is `0.0` by default. In `main.py:114`:

```python
fill_price = update.get("fill_price") or update.get("price") or 0.0
```

If both `fill_price` and `price` are missing or zero in the update dict (e.g. a Kite API edge case where `average_price` is 0 during a partial fill), `close_position` is called with `exit_price=0.0`. The condition `exit_price and freed` is `False`, so:
- Realised P&L is not computed
- Daily loss limit check is skipped
- Capital is freed but the loss is invisible

Additionally, the backtest engine calls `risk.close_position(symbol)` (without exit_price) at lines 108 and 206, so the risk manager's daily halt logic is never exercised during backtests. Backtest results don't simulate mid-day halts.

**Impact:** A real losing trade can silently bypass the daily loss limit if the fill price field is missing.

---

### R2-8. RSI and MACD strategies have no exit mechanism and no `stop_loss_hint`
**File:** `trader/strategies/rsi.py` and `trader/strategies/macd.py`

Both strategies emit ENTRY signals only — they never emit EXIT signals. They also don't provide `stop_loss_hint` or `target_price` in their signals.

In live mode with `gtt_enabled: false` (current config):
- Positions entered by RSI/MACD have **no exit path at all**
- The RiskManager computes SL/target from config defaults, but those are only used in the Order — nothing acts on them
- The position stays open until process restart

With `gtt_enabled: true`:
- GTT provides SL/target exits, but the strategy's `position` state is never reset (no EXIT `on_order_update` from GTT, same as R2-1)

Currently mitigated because both strategies are `enabled: false` in config. But if either is ever enabled, positions will accumulate without exits.

---

## MEDIUM — Should fix

### R2-9. `flush_partials` at 15:30 races with the 60-minute candle boundary
**File:** `trader/data/live.py:200-206` and `trader/scheduler/jobs.py:49-53`

With `candle_timeframe: 60minute`, candle boundaries are at 09:00, 10:00, ..., 15:00. The 15:00–16:00 candle is in progress when `flush_partials` fires at 15:30.

This flushes a partial 30-minute candle (15:00–15:30) as if it were a full 60-minute candle. The strategy sees a candle with only half the normal trading volume and a truncated price range. The LR model's slope features will be computed on this shorter window, potentially generating spurious signals.

**Fix:** Either move `flush_partials` to 15:35 (after post-market, giving a more complete candle) or tag the flushed candle so the strategy can identify it as partial.

---

### R2-10. `_candle_bucket` produces wrong boundaries for 60-minute candles
**File:** `trader/data/live.py:208-211`

```python
def _candle_bucket(self, ts: datetime) -> datetime:
    minute = (ts.minute // self._timeframe) * self._timeframe
    return ts.replace(minute=minute, second=0, microsecond=0)
```

For `timeframe=60`, `ts.minute // 60 == 0` for any valid minute (0–59). So `minute` is always 0 and `candle_start` is always `XX:00:00`. The candle boundary advances only when the **hour** changes (via the `ts` itself), which happens to be correct for 60-minute candles.

But: at 10:30 AM, `candle_start = 10:00`. At 11:00 AM, `candle_start = 11:00`. So `10:00 < 11:00` triggers a new candle. This means the 60-minute candles are actually aligned to clock hours (09:00–10:00, 10:00–11:00, ...), which matches NSE's session structure. This works correctly by coincidence.

However, this would break for any `timeframe > 60` (e.g. 120 minutes or 240 minutes), since `minute // 120 == 0` always, and the boundary never advances within the same hour. Currently not an issue since only 60-minute is used, but worth noting.

---

### R2-11. No deduplication of GTT order updates
**File:** `trader/orders/manager.py:84-150` — `on_kite_order_update()`

Kite can send multiple order updates for the same order (e.g., OPEN → COMPLETE). The COMPLETE status is processed. But if Kite sends duplicate COMPLETE callbacks (network retry, WebSocket reconnect), the same fill is processed twice:
- `risk.close_position()` called twice — second call finds nothing (instrument already popped), logs a warning but is benign
- `handle_order_update` in main.py sends duplicate Telegram notifications
- `strat.on_order_update()` called twice — second call is a no-op (already cleared)

**Impact:** Duplicate Telegram messages and confusing logs. Not dangerous but noisy.

**Fix:** Track processed order IDs in a set and skip duplicates.

---

### R2-12. `post_market` sends `total_trades=len(positions)` — not the actual trade count
**File:** `main.py:170`

```python
total_trades=len(positions),
```

`positions` is the number of entries in `portfolio._positions` (unique instruments), not the number of trades executed today. If you traded RELIANCE twice and INFY once, this reports 2 (instruments), not 3 (trades).

In live mode, `portfolio.refresh()` includes all positions from Kite (which could include positions from previous days), further inflating the count.

---

### R2-13. Startup reconciliation doesn't set `_held_bars` for seeded positions
**File:** `main.py:85-93`

The synthetic fill sent to strategies during live startup sets `_entry_price` via `on_order_update`, but `_held_bars` is reset to 0. If the position has been held for 100 bars before the restart, the strategy resets the hold counter. It will now hold for another 150 bars (full `hold_bars`) instead of the remaining 50.

**Impact:** Max-hold exits fire later than they should after a restart. Positions could be held much longer than intended.

---

## LOW — Minor issues

### R2-14. `_candles` list in LRExtremaStrategy grows unbounded
**File:** `trader/strategies/lr_extrema.py:67`

`self._candles.append(candle)` never trims old candles. Over months of running, this list grows continuously. Retraining iterates all candles to find extrema (O(n)) and computes features per extremum. Not a memory issue at 60-minute candles (~1500/year), but retraining time grows linearly.

---

### R2-15. Backtest engine doesn't pass `exit_price` to `risk.close_position()`
**File:** `trader/backtest/engine.py:108, 206`

```python
risk.close_position(instrument)    # no exit_price
risk.close_position(symbol)        # no exit_price
```

This means the risk manager's daily halt logic is never exercised during backtests. A strategy that passes calibration could be halted repeatedly in live trading due to sequential intraday losses that the backtest never simulated.

---

### R2-16. NSE holidays not handled by scheduler
**File:** `trader/scheduler/jobs.py`

Scheduler fires on all weekdays including NSE holidays (Republic Day, Diwali, etc.). On holidays:
- `pre_market` runs warm_up (benign but wasteful)
- `flush_partials` runs at 15:30 (nothing to flush — no ticks)
- `post_market` sends a P&L notification showing ₹0.00 (misleading)

---

## Round 2 Summary

| Severity | Count | Key theme |
|----------|-------|-----------|
| CRITICAL | 5 | GTT signal_type wrong, volume day-boundary, no strategy warmup, halt traps exits, exception-stuck strategy |
| HIGH | 3 | Paper P&L overwrite, silent zero-price close, entry-only strategies have no exit |
| MEDIUM | 5 | Flush timing, 60min coincidence, duplicate callbacks, trade count, held_bars reset |
| LOW | 3 | Unbounded candle list, backtest halt gap, holiday noise |

**Verdict:** The round 1 fixes addressed the original issues, but introduced a new critical bug in the GTT recovery path (R2-1) and left a day-boundary hole in the volume fix (R2-2). The most impactful gap for live readiness is the absence of strategy warm-up (R2-3) — without it, the system is functionally inert for a month after every startup. Fix R2-1 through R2-5 before going live.
