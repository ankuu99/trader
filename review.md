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

### R2-8. ✅ RSI and MACD strategies removed — no longer applicable

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

---
---

# Round 3 Review — Post-fix

Reviewed all files in their current state after round 2 fixes were applied.
Focus: interaction bugs between fixes, startup sequencing, and remaining state inconsistencies.

---

## CRITICAL — Must fix before going live

### R3-1. ✅ Synthetic fill missing `direction` field — crashes live startup — FIXED
**File:** `main.py:86-94` and `trader/strategies/base.py:84-88`

The live reconciliation loop sends a synthetic fill to strategies:

```python
synthetic_fill = {
    "status": "COMPLETE",
    "signal_type": SignalType.ENTRY,
    "price": float(p["average_price"]),
    "instrument": instrument,
    # NO "direction" key
}
strat.on_order_update(synthetic_fill)
```

In `base.py:84-88`:

```python
direction = order.get("direction")       # → None
if signal_type == SignalType.ENTRY:
    self.position = Direction(direction)  # → Direction(None) → ValueError!
```

`Direction` is a `str, Enum`. Calling `Direction(None)` raises `ValueError: None is not a valid Direction`.

**Impact:** The system crashes on startup whenever there are open positions in Kite. This is exactly the scenario where reconciliation is most needed (restart during live trading).

**Fix:** Add `"direction": "BUY"` to the synthetic fill dict:

```python
synthetic_fill = {
    "status": "COMPLETE",
    "signal_type": SignalType.ENTRY,
    "direction": "BUY",
    "price": float(p["average_price"]),
    "instrument": instrument,
}
```

---

### R3-2. ✅ Reconciliation before warm-up — warm-up overrides reconciled position state — FIXED
**File:** `main.py:78-107`

The startup sequence is:

1. **Line 79-94:** Live reconciliation — sets `_entry_price` on strategies for open positions
2. **Line 96-107:** Warm-up — replays ALL cached candles through `on_candle()`

During warm-up, `on_candle()` executes the full entry/exit logic. If any historical candle triggers an exit condition against the reconciled `_entry_price`, the strategy clears `_entry_price` and emits an EXIT signal (discarded by the warm-up loop).

**After warm-up:** strategy is flat (`_entry_price = None`) but a real position exists in Kite and RiskManager. Consequences:
- Strategy emits a NEW entry signal for the same instrument
- RiskManager correctly rejects it ("already in position")
- Strategy's `_entry_price` is set to the new signal price (line 124 of lr_extrema.py) — never cleared because order is rejected before `on_order_update` fires
- Strategy is now stuck with a phantom `_entry_price` that blocks all future entries AND has wrong price for exit calculations

**Fix:** Move reconciliation AFTER warm-up. The warm-up builds the model and indicator state; reconciliation then overrides position state to match reality:

```python
# 1. Warm-up (model + indicators only)
for symbol in valid_watchlist:
    df = store.read_candles(...)
    for _, row in df.iterrows():
        for strat in strats_for_symbol:
            strat.on_candle(candle)

# 2. Reconcile (override position state)
if config.env == "live":
    kite_pos = kite.positions()
    risk.seed_from_kite(kite_pos)
    for p in kite_pos.get("net", []):
        ...
        strat.on_order_update(synthetic_fill)
```

Additionally, after reconciliation, explicitly clear `_entry_price` for strategies whose instruments do NOT have open positions (to clean up any phantom state from warm-up entries):

```python
open_instruments = {f"NSE:{p['tradingsymbol']}" for p in kite_pos.get("net", []) if p["quantity"] > 0}
for strat in strategies:
    if strat.instrument not in open_instruments:
        strat._entry_price = None
        strat.position = None
```

---

## HIGH — Significant logic issues

### R3-3. ✅ Warm-up runs before cache refresh — strategies train on stale data — FIXED
**File:** `main.py:96-107` and `main.py:208`

Startup sequence:

1. **Line 96-107:** Warm-up reads candles from SQLite cache
2. **Line 208:** `pre_market()` calls `warm_up()` which fetches fresh candles from Kite API into SQLite

If the system was stopped for several days and restarts, the warm-up at step 1 uses stale cached data (missing the last N days of candles). The fresh data fetched at step 2 is never replayed through the strategies.

**Impact:** The LR Extrema model is trained on an incomplete dataset. More critically, the model's most recent features (slopes, volume) are computed from outdated candles, potentially making inaccurate predictions for the first `retrain_every` live candles.

**Fix:** Swap the order — call the cache refresh before warm-up:

```python
# Refresh cache first
for symbol in valid_watchlist:
    token = symbol_to_token[symbol]
    warm_up(kite, store, token, symbol, config.candle_timeframe,
            config.historical_cache_days)

# Then warm up strategies from fresh cache
for symbol in valid_watchlist:
    df = store.read_candles(symbol, config.candle_timeframe, warmup_from, datetime.now())
    ...
```

---

### R3-4. ✅ Paper-mode SELL path doesn't accumulate prior `realised_pnl` — R2-6 fix incomplete — FIXED
**File:** `trader/portfolio/tracker.py:38-47`

The R2-6 fix correctly preserves `prior_realised` on the BUY path (line 53). But the SELL path overwrites it:

```python
if direction == "SELL":
    existing = self._positions.get(symbol)
    if existing and existing.quantity > 0:
        pnl = (fill_price - existing.average_price) * existing.quantity
        self._positions[symbol] = Position(
            instrument=symbol,
            quantity=0,
            average_price=existing.average_price,
            realised_pnl=pnl,    # ← should be: existing.realised_pnl + pnl
        )
```

Scenario: BUY RELIANCE → SELL (+500) → BUY RELIANCE (preserves 500) → SELL (+300):
- After second SELL: `realised_pnl = 300` (should be `800`)
- The 500 from the first round-trip was preserved on BUY but lost on SELL

**Impact:** Paper-mode daily P&L notification understates cumulative performance when the same instrument is traded multiple times in one day.

**Fix:**
```python
realised_pnl=existing.realised_pnl + pnl,
```

---

### R3-5. ✅ No guard against `fill_price=0` on BUY fill — capital tracking broken — FIXED
**File:** `main.py:128-132` and `trader/risk/manager.py:150-154`

```python
# main.py
fill_price = update.get("fill_price") or update.get("price") or 0.0
if direction == "BUY":
    risk.on_order_filled(instrument, fill_price, quantity)  # fill_price could be 0.0
```

```python
# risk/manager.py
def on_order_filled(self, instrument: str, fill_price: float, quantity: int):
    deployed = fill_price * quantity   # 0.0 if fill_price is 0
    self._position_values[instrument] = deployed  # 0.0
    self._capital_deployed += deployed  # unchanged
```

If fill_price is 0 (API edge case, partial fill, or deserialization bug):
- Position is registered with 0 deployed capital
- `capital_available` is not reduced → system can over-deploy on next entry
- When later closed: `freed = 0.0`, so `if qty and exit_price and freed` is False — P&L not computed, daily loss limit not checked

**Impact:** A single corrupt fill silently disables capital tracking and loss limits for that position.

**Fix:** Guard in `on_order_filled`:
```python
def on_order_filled(self, instrument: str, fill_price: float, quantity: int):
    if fill_price <= 0:
        logger.error("BUY fill with price=0 for %s — cannot track capital", instrument)
        return
    ...
```

---

## MEDIUM — Should fix

### R3-6. ✅ Post warm-up phantom position — strategy blocked for up to `hold_bars` candles — FIXED (folded into R3-2)
**File:** `trader/strategies/lr_extrema.py:110-137` (entry logic during warm-up)

During warm-up, signals are discarded but `_entry_price` is still set inside `on_candle()` at line 124 when the model triggers an entry. Exit conditions (profit/stop/hold) may clear it on subsequent warm-up candles. But if an entry fires in the **last few candles** of warm-up and no exit triggers before warm-up ends:

- `_entry_price` is set, `position` is `None` (no `on_order_update` called)
- Live candles arrive → exit management runs (line 71: `self._entry_price is not None`)
- Max hold: strategy waits up to 150 candles (~25 trading days at 60min) before clearing

During this time, no new entries can fire (line 110 requires `self._entry_price is None`).

**Impact:** After startup, strategy may be silently blocked for up to 25 trading days. In paper mode this is a missed opportunity; in live mode (with R3-2 fixed by moving reconciliation after warm-up) it means the reconciliation will override this, making it benign in live mode but still problematic in paper mode.

**Fix:** After warm-up completes, clear ephemeral entry state for strategies that don't have a real broker position:

```python
# After warm-up, clear phantom entries (paper mode or instruments not in Kite positions)
for strat in strategies:
    if strat._entry_price is not None and strat.position is None:
        logger.info("Clearing phantom entry state after warm-up | %s", strat.instrument)
        strat._entry_price = None
        strat._held_bars = 0
```

---

### R3-7. ✅ `risk.reset_day()` clears halt but not `_open_positions` — stale positions accumulate — FIXED
**File:** `trader/risk/manager.py:209-212` and `main.py:188`

```python
def reset_day(self):
    self._realised_pnl = 0.0
    self._halted = False
```

Called by `post_market()` at 15:35 IST. Resets P&L and halt flag but does NOT clear `_open_positions` or `_capital_deployed`.

In CNC (delivery) mode, positions carry over to the next day, so not clearing `_open_positions` is correct for held-overnight positions. But positions that were closed via GTT during the day (when the GTT fires on Kite's side but the order update was missed — documented edge case in CLAUDE.md) will remain as phantom entries in `_open_positions` forever.

**Impact:** Over time, `_open_positions` accumulates stale instruments. `max_open_positions` check eventually prevents all new entries even though those positions no longer exist.

**Fix:** In live mode, cross-reference `_open_positions` with broker state during `post_market`:

```python
def post_market():
    portfolio.refresh()
    # Reconcile risk manager with actual broker positions
    if config.env == "live":
        kite_pos = kite.positions()
        live_instruments = {f"NSE:{p['tradingsymbol']}" for p in kite_pos.get("net", []) if p["quantity"] > 0}
        stale = set(risk._open_positions.keys()) - live_instruments
        for inst in stale:
            logger.warning("Removing stale position from risk tracker | %s", inst)
            risk.close_position(inst, 0.0)
    ...
```

---

### R3-8. ✅ Warm-up candle dict missing `instrument_token` key — FIXED
**File:** `main.py:102-106`

```python
for _, row in df.iterrows():
    candle = row.to_dict()
    candle["_symbol"] = symbol
    for strat in strats_for_symbol:
        strat.on_candle(candle)
```

`store.read_candles()` returns columns: `timestamp, open, high, low, close, volume`. There is no `instrument_token` column. The warm-up candle dict is missing this key.

`LRExtremaStrategy.on_candle()` does not use `instrument_token`, so this is currently benign. But `OrderManager.on_candle()` (which processes these same candles in the backtest engine) expects `_symbol` for matching. If any future strategy or handler requires `instrument_token`, it will fail silently (returning None from `.get()`).

**Impact:** Currently benign. Potential source of silent bugs if the candle contract is assumed to include `instrument_token` elsewhere.

---

## LOW — Minor issues

### R3-9. `handle_candle` doesn't guard against `symbol=None`
**File:** `main.py:146-148`

```python
def handle_candle(candle: dict):
    symbol = token_to_symbol.get(candle.get("instrument_token"))
    candle["_symbol"] = symbol   # could be None
    orders.on_candle(candle)     # _symbol=None → no paper fills match (benign)
```

If a tick arrives for a token not in `token_to_symbol` (shouldn't happen normally, but could if the instrument list is refreshed mid-session or Kite sends ticks for indices), `symbol` is None. The candle is passed to `orders.on_candle()` (which compares against instrument names — no match, benign) and then to strategies (the loop `strategy.instrument != symbol` skips all, also benign).

**Impact:** Silent no-op. The candle is processed without error but does nothing useful. A debug log would help identify phantom tokens.

---

### R3-10. `pre_market` warm-up runs daily at 09:00 but also called at startup (line 208)
**File:** `main.py:208` and scheduler at 09:00

If the system starts before 09:00, `pre_market()` runs immediately at startup (line 208) and then again at 09:00 via the scheduler — duplicating the Kite API calls. With ~20 symbols and rate limits of ~3 req/sec, this adds ~7 seconds of redundant API calls.

If the system starts after 09:00 (e.g., mid-day restart), the scheduler won't fire `pre_market` until the next day, but the startup call at line 208 ensures the cache is refreshed.

**Impact:** Minor redundancy. Not harmful but wasteful of Kite API quota.

---

## Round 3 Summary

| Severity | Count | Key theme |
|----------|-------|-----------|
| CRITICAL | 2 | Synthetic fill crash, reconciliation/warm-up ordering |
| HIGH | 3 | Stale warm-up data, P&L accumulation, fill_price=0 |
| MEDIUM | 3 | Phantom entry, stale positions, missing candle key |
| LOW | 2 | None guard, duplicate pre_market |

**Verdict:** The most urgent fix is R3-1 (Direction(None) crash) which makes live startup impossible when positions exist. R3-2 (reconciliation ordering) is the most architecturally significant — without it, the warm-up and reconciliation fixes from R2-3 actively fight each other. R3-3 (cache before warm-up) ensures the model trains on current data. These three form a coherent startup-sequencing fix: refresh cache → warm up strategies → reconcile from broker. The remaining issues are correctness improvements that reduce edge-case risk.

---
---

# Round 4 Review — Post-fix

Reviewed all files in their current state after round 3 fixes were applied.
Focus: concurrency, state integrity under edge cases, and remaining correctness gaps.

---

## HIGH — Significant logic issues

### R4-1. Thread safety: scheduler jobs race with WebSocket callbacks on shared mutable state
**File:** `main.py:206-232` (post_market), `trader/scheduler/jobs.py:66-72` (_run), `trader/data/live.py:103-105` (_on_ticks)

Three threads touch the same objects without synchronization:

| Thread | Accesses |
|--------|----------|
| KiteTicker WebSocket | `risk.validate()`, `risk.on_order_filled()`, `risk.close_position()`, `portfolio.on_order_filled()`, `strategy.on_candle()`, `strategy.on_order_update()` |
| APScheduler (15:35) | `risk._open_positions` (read, line 217), `risk.close_position()` (write, line 220), `risk.reset_day()` (write, line 232), `portfolio.refresh()` (write), `portfolio._positions` (read) |
| APScheduler (15:30) | `feed.flush_partials()` → `_emit_candle()` → `handle_candle()` → `risk.validate()`, `strategy.on_candle()`, `orders.place()` |

The `flush_partials` call at 15:30 runs `handle_candle` on the **scheduler thread** while the WebSocket thread may still be processing late ticks that also call `handle_candle`. LiveFeed's `self._lock` serializes candle emission, but `handle_candle` itself (and everything it calls — strategy, risk, orders) is not protected by any lock.

At 15:35, `post_market` mutates `risk._open_positions` and `risk._realised_pnl` while a late order update on the WebSocket thread might be doing the same.

**Impact:** Race conditions can corrupt `_capital_deployed`, `_realised_pnl`, or `_open_positions`. Worst case: daily loss limit check reads a stale `_realised_pnl` and doesn't trigger halt; or `reset_day()` zeroes `_realised_pnl` while `close_position` is mid-write, losing the P&L delta.

**Fix:** Add a threading lock that guards all shared state mutations. The simplest approach is a single global lock acquired in `handle_candle`, `handle_order_update`, and each scheduler hook:

```python
import threading
_state_lock = threading.Lock()

def handle_candle(candle: dict):
    with _state_lock:
        ...  # existing body

def handle_order_update(update: dict):
    with _state_lock:
        ...  # existing body

def post_market():
    with _state_lock:
        ...  # existing body
```

---

### R4-2. Duplicate BUY COMPLETE order updates double-count `_capital_deployed`
**File:** `trader/risk/manager.py:150-165` and `trader/orders/manager.py:152-155`

If Kite sends duplicate COMPLETE callbacks for the same BUY order (network retry, WebSocket reconnect), both are dispatched to `handle_order_update`:

1. First COMPLETE: `on_kite_order_update` finds `original` in `_live_orders`, dispatches, pops from `_live_orders` (line 153).
2. Second COMPLETE (same order_id): `_live_orders.get(order_id)` → None. Falls back to `_instrument_orders.get(instrument)` → finds the original (BUY entry still there). Dispatches again.

Both trigger `risk.on_order_filled(instrument, fill_price, quantity)`:

```python
def on_order_filled(self, instrument, fill_price, quantity):
    self._open_positions[instrument] = quantity     # overwrite — OK
    deployed = fill_price * quantity
    self._position_values[instrument] = deployed    # overwrite — OK
    self._capital_deployed += deployed               # ADDITIVE — doubled!
```

`_capital_deployed` accumulates `deployed` twice. `capital_available` is now understated by the position's value, potentially blocking the next entry with "Quantity is 0 — available capital ₹0".

**Impact:** A single duplicate order update can consume the entire portfolio's capital headroom. New entries are rejected until `post_market` or `close_position` frees capital.

**Fix:** Guard against re-adding an instrument already in `_open_positions`:

```python
def on_order_filled(self, instrument: str, fill_price: float, quantity: int):
    if fill_price <= 0:
        logger.error(...)
        return
    if instrument in self._open_positions:
        logger.warning("Duplicate fill for %s — ignoring", instrument)
        return
    self._open_positions[instrument] = quantity
    ...
```

---

## MEDIUM — Should fix

### R4-3. OPEN@END backtest trades always show negative P&L due to costs
**File:** `trader/backtest/engine.py:231-248`

```python
last_close = pos["entry"]  # conservative: assume no price change
net, cost, product = _net_pnl(pos["entry"], last_close, pos["qty"], ...)
```

When the backtest ends with open positions, exit price is set to entry price. Gross P&L is zero, but `_net_pnl` deducts round-trip transaction costs (~0.22% for CNC). Every OPEN@END trade has a guaranteed loss.

In calibration (`calibrate.py`), strategies that hold fewer trades to maturity look worse because their OPEN@END trades accumulate phantom transaction costs. This biases calibration toward strategies that close positions quickly, penalising longer-hold strategies.

**Fix:** Use the last candle's close price for each symbol:

```python
# Track last close per symbol during replay
last_closes: dict[str, float] = {}
for candle in merged_candles:
    last_closes[candle["_symbol"]] = candle["close"]
    ...

# Use actual last close for OPEN@END
for symbol, pos in list(open_positions.items()):
    last_close = last_closes.get(symbol, pos["entry"])
    ...
```

---

### R4-4. Startup cache refresh is duplicated — 40+ redundant API calls
**File:** `main.py:78-83` and `main.py:252`

The startup sequence:
1. **Lines 78-83:** Loop over all symbols, call `warm_up()` → fetches from Kite API, writes to SQLite
2. **Line 252:** `pre_market()` → same loop, same `warm_up()` calls

The second pass at line 252 checks `cached_latest` and mostly skips fetching (cache is fresh from step 1). But it still opens a SQLite connection per symbol, queries `MAX(timestamp)`, and compares — ~20 redundant queries.

**Fix:** Remove the explicit cache refresh at lines 78-83 and call `pre_market()` before warm-up instead:

```python
pre_market()  # refresh cache once

# Then warm up strategies from fresh cache
warmup_from = datetime.now() - timedelta(days=config.historical_cache_days)
for symbol in valid_watchlist:
    ...
```

This also eliminates the separate `pre_market()` call at line 252.

---

### R4-5. `log_summary` excludes closed positions — paper-mode P&L log is always zero
**File:** `trader/portfolio/tracker.py:83-94`

```python
def log_summary(self):
    positions = [p for p in self._positions.values() if p.quantity != 0]
    total_realised = sum(p.realised_pnl for p in positions)
```

After a SELL, the position has `quantity=0` and `realised_pnl=trade_pnl`. The filter `quantity != 0` excludes it. So `total_realised` only includes realised P&L from **open** positions (which is always 0 since no partial fills occur in this system).

Meanwhile, `post_market` in main.py uses `list(portfolio._positions.values())` **without** the quantity filter for the Telegram notification. So the Telegram message shows correct P&L, but the log shows ₹0.00.

**Impact:** Log files show `realised=0.00` every day even when trades were profitable. Misleading for debugging without Telegram access (e.g., reviewing EC2 logs).

**Fix:** Remove the quantity filter for the realised sum, or sum all positions:

```python
all_positions = list(self._positions.values())
open_positions = [p for p in all_positions if p.quantity != 0]
total_unrealised = sum(p.unrealised_pnl for p in open_positions)
total_realised = sum(p.realised_pnl for p in all_positions)
```

---

### R4-6. `on_order_filled` guard (R3-5) creates orphan position in strategy with no risk tracking
**File:** `trader/risk/manager.py:150-156` and `main.py:160-169`

When `fill_price <= 0`, `on_order_filled` returns early. But `handle_order_update` continues:

```python
if direction == "BUY":
    risk.on_order_filled(instrument, fill_price, quantity)  # returns early
portfolio.on_order_filled(...)   # tracks position
strat.on_order_update(update)    # sets position = BUY, _entry_price = 0
```

After this:
- Strategy has `position = Direction.BUY` and `_entry_price = 0.0` (or fill_price if 0)
- RiskManager has NO record of this instrument in `_open_positions`
- Strategy exit check: `pct = (close - 0.0) / 0.0` → **ZeroDivisionError** crash

Even if `_entry_price` is not exactly 0.0 (the `or` chain yields 0.0), the strategy's percentage calculation at `lr_extrema.py:75` divides by `_entry_price`:

```python
pct = (close - self._entry_price) / self._entry_price * 100.0
```

**Impact:** If a BUY fill with price=0 reaches the strategy, the process crashes on the next candle with `ZeroDivisionError`.

**Fix:** Guard at the `handle_order_update` level — reject the fill entirely if price is invalid:

```python
fill_price = update.get("fill_price") or update.get("price") or 0.0
if status == "COMPLETE" and fill_price <= 0:
    logger.error("Fill with price=0 for %s — treating as REJECTED", instrument)
    for strat in strategies:
        if strat.instrument == instrument:
            strat.on_order_update({**update, "status": "REJECTED"})
    return
```

---

## LOW — Minor issues

### R4-7. BZ/BE stocks remain in watchlist — trade-to-trade and limited liquidity
**File:** `config/config.yaml:24,30` (BZ) and lines `19,26,27,32,33` (BE)

Active BZ stocks: `NSE:FEL-BZ`, `NSE:SHRENIK-BZ`. Active BE stocks: `NSE:MAHASTEEL-BE`, `NSE:SEYAIND-BE`, `NSE:EQUIPPP-BE`, `NSE:ORTINGLOBE-BE`, `NSE:ARTNIRMAN-BE`.

BZ (trade-to-trade) stocks require compulsory delivery — no intraday square-off. This system uses CNC/delivery so that's compatible. But BZ stocks typically have very low liquidity: wide bid-ask spreads mean market orders can fill significantly away from the signal's `price_hint`, eroding the 2.5% stop distance.

BE stocks have periodic surveillance restrictions (additional margin, price bands). Orders may be rejected during restriction periods with no automatic recovery.

**Impact:** Not a bug — operational risk. Market orders on illiquid stocks can slip 1-3%, eating most of the 5% profit target.

---

### R4-8. Late ticks after `flush_partials` create a phantom mini-candle
**File:** `trader/data/live.py:201-207` and `134-182`

After `flush_partials` clears `_partials` at 15:30, Kite may deliver a few trailing ticks (post-close or auction data). These create a new partial candle entry. When the next day's first tick arrives at 09:15, this phantom partial is emitted as a complete candle covering 15:30 to ~09:15 — a ~17.5-hour candle with 1-2 ticks of data.

The strategy processes this as a regular candle, but its OHLCV is meaningless (essentially a single-tick candle). The volume is near-zero. The close price is the last post-close tick, which may differ from the actual settlement price.

**Impact:** One garbage candle per day per instrument. The LR model's slope features are slightly distorted. The model retrains periodically, diluting the impact over time. LOW severity in practice.

---

## Round 4 Summary (continued below)

| Severity | Count | Key theme |
|----------|-------|-----------|
| HIGH | 2 | Thread safety race, duplicate fill capital double-count |
| MEDIUM | 4 | OPEN@END cost bias, duplicate cache refresh, log P&L mismatch, ZeroDivisionError on price=0 |
| LOW | 2 | BZ/BE liquidity risk, phantom post-close candle |

**Verdict:** No CRITICAL issues remain — the startup sequence (cache → warm-up → phantom cleanup → reconciliation) is now correct, and the Direction(None) crash is fixed. The highest-priority Round 4 fix is R4-1 (thread safety). Since APScheduler runs jobs on a background thread and KiteTicker runs on another, shared state is accessed without locks. A single `threading.Lock` guarding `handle_candle`, `handle_order_update`, and each scheduler hook would eliminate this class of bug. R4-2 (duplicate fill capital) should also be fixed before live — it can be triggered by normal Kite WebSocket reconnection behaviour and silently blocks all new entries.

---
---

# Round 5 Review — Limit Order Mode

Reviewed after `order_type: limit` was added to config and `_place_live` was updated.
Focus: correctness of limit order handling across all code paths.
**Note:** GTT is currently disabled (`gtt_enabled: false`). Issues that are dormant under this config are marked accordingly.

---

## HIGH — Must fix before using limit orders in live mode

### L1. ✅ Capital not locked while limit order is pending — FIXED
**File:** `trader/risk/manager.py` — `on_order_filled()` and `validate()`

`on_order_filled()` (which records deployed capital) is only called when a fill is COMPLETE. While a limit BUY is sitting unfilled in Kite, `capital_available` does not reflect the pending order. If a second signal fires for the same instrument before the first limit fills, `validate()` passes the duplicate-position check (`instrument not in _open_positions` is True — the first order hasn't filled yet) and a second order is placed.

With a single strategy and `_entry_price` guard, the re-entry window is narrow: only the exact candle between the EXIT phantom clear (see L3) and the pending BUY fill arriving. But a second strategy or a mid-session restart could trigger it more reliably.

**Fix approach:** Track pending capital separately in RiskManager — deduct at order placement and release on CANCELLED/REJECTED. Confirm with user before implementing.

---

### L2. ✅ Strategy clears `_entry_price` on phantom EXIT while limit is pending — FIXED
**File:** `trader/strategies/lr_extrema.py:71-99` and `trader/risk/manager.py:131-136`

**Sequence:**
1. Limit BUY placed → `_entry_price = price_hint` (re-entry guard set)
2. Price moves ≥ `profit_pct` or ≤ `-stop_pct` before the limit fills
3. Strategy exit block runs (condition: `self._entry_price is not None`)
4. EXIT signal emitted → strategy clears `_entry_price = None`, `_held_bars = 0`
5. RiskManager correctly blocks the SELL (`quantity = 0` in `_open_positions`, returns None)
6. **Re-entry guard is now gone** — strategy is fully reset
7. Original limit order is still pending in Kite
8. Next candle: strategy can fire a fresh ENTRY → second limit order placed
9. Both limits eventually fill → two open positions for same instrument, but RiskManager only has one

**Impact:** Double position possible. In practice requires a large intrabar move (≥ `profit_pct` = 4% or ≤ `-stop_pct` = 2%) between signal and fill — uncommon on 5-min candles but possible on volatile days.

**Fix approach:** On EXIT emission, check whether the exit signal was accepted (non-None return from RiskManager) before clearing `_entry_price`. This requires wiring the RiskManager response back into the strategy — a structural change. Alternatively, skip the exit management block entirely until position is confirmed (status=COMPLETE). Confirm with user before implementing.

---

## MEDIUM — Significant for limit mode correctness

### L3. Paper mode ignores limit price — always fills at next candle open
**File:** `trader/orders/manager.py:61-93` — `on_candle()`

Paper mode fills pending orders at `candle["open"]` unconditionally. A BUY limit at ₹100 fills even if next candle opens at ₹105. This makes paper mode more optimistic than live: limit orders that would miss in live trading appear to fill in paper. Backtested returns under `order_type: limit` are overstated.

**Fix approach:** In `on_candle`, skip fill if `order.price_hint` is set and `fill_price > order.price_hint` for BUY orders (limit price missed). The pending order would remain until the next candle. Confirm with user before implementing.

---

### L4. `_instrument_orders` not cleaned up when limit BUY is CANCELLED
**File:** `trader/orders/manager.py:162-165` — `on_kite_order_update()`

```python
if status in ("COMPLETE", "REJECTED", "CANCELLED"):
    self._live_orders.pop(order_id, None)
    if status == "COMPLETE" and direction == "SELL":
        self._instrument_orders.pop(instrument, None)
```

When a CNC limit BUY is CANCELLED at 3:30 PM (unfilled at EOD), it is removed from `_live_orders` but stays in `_instrument_orders`. This map is used to recover GTT fill context — a future GTT SELL for the same instrument would find the stale BUY entry and recover wrong context.

**Dormant while `gtt_enabled: false`.** Will become active if GTT is re-enabled.

**Fix approach:** Also pop `_instrument_orders` on CANCELLED/REJECTED of BUY orders. One-line change.

---

### L5. GTT placed before limit fill — ghost GTT with no position backing it
**File:** `trader/orders/manager.py:250-251` — `_place_live()`

```python
if config.gtt_enabled and order.direction == Direction.BUY:
    self._place_gtt_sl(order, symbol)
```

GTT OCO is placed immediately after limit order submission, not after fill confirmation. If the limit never fills (price moves away, cancelled at EOD), the GTT remains active on Zerodha — armed to SELL a position that was never entered.

**Dormant while `gtt_enabled: false`.** Will become active if GTT is re-enabled.

**Fix approach:** Move `_place_gtt_sl` call to inside `on_kite_order_update` when status=COMPLETE and direction=BUY. Confirm with user before implementing.

---

## Round 5 Summary

| ID | Severity | Active? | Issue |
|----|----------|---------|-------|
| L1 | HIGH | Yes | Capital not locked while limit pending — allows double orders |
| L2 | HIGH | Yes | Phantom EXIT clears re-entry guard while limit is pending |
| L3 | MEDIUM | Yes | Paper mode ignores limit price — always fills, overstates returns |
| L4 | MEDIUM | Dormant | `_instrument_orders` stale after CANCELLED limit BUY |
| L5 | MEDIUM | Dormant | GTT placed before limit fill — ghost GTT with no position |

**Verdict:** Limit orders are not safe to use in live mode today. L1 and L2 are the critical blockers — both can result in double positions. L3 means paper testing under `order_type: limit` gives falsely optimistic results. L4 and L5 are dormant until GTT is re-enabled. Recommend keeping `order_type: market` until L1 and L2 are fixed.

---
---

# Round 6 Review — Multi-day Position Tracking & GTT Capital Flow

Reviewed after GTT was re-enabled and the L5 fix (GTT placed after fill) was applied.
Focus: position state correctness across restarts, capital tracking for multi-day CNC holds, and GTT-triggered exit accounting.

---

## HIGH — Significant logic issues

### R6-1. ✅ Multi-day CNC positions lost on restart — capital tracking broken — FIXED
**File:** `trader/risk/manager.py` — `seed_from_kite()` and `main.py` startup

`seed_from_kite()` calls `kite.positions()`, which returns **only today's traded positions**. A CNC position bought 3 days ago with no activity today returns with `quantity=0` and is skipped. On any restart:

- `_open_positions` is empty
- `_capital_deployed` is 0
- System believes full capital is available
- New entries can be placed on top of existing holdings, over-deploying capital
- When GTT eventually fires (SELL), `close_position()` finds nothing in `_open_positions` — capital tracking and P&L computation are both skipped silently

**Root cause:** `kite.positions()` ≠ `kite.holdings()`. Multi-day CNC holdings live in `kite.holdings()`, not `kite.positions()`. Using `kite.holdings()` directly would also pick up the user's manual holdings unrelated to this bot.

**Fix:** Seed from the bot's own `open_positions` SQLite table on restart. The DB only contains what this bot placed. Cross-check against `kite.holdings()` to detect positions closed externally (e.g. GTT fired while system was down) and call `close_position()` for those:

```python
def seed_from_db(store, risk, strategies, config):
    db_positions = store.read_open_positions()   # reads open_positions table
    kite_holdings = {h["tradingsymbol"]: h for h in kite.holdings()}
    for row in db_positions:
        instrument = row["instrument"]
        symbol = instrument.split(":")[-1]
        if symbol not in kite_holdings or kite_holdings[symbol]["quantity"] <= 0:
            # Position was closed externally (GTT or manual) while bot was down
            logger.warning("Position %s in DB but not in holdings — treating as closed", instrument)
            risk.close_position(instrument, kite_holdings.get(symbol, {}).get("last_price", 0.0))
            store.delete_open_position(instrument)
            continue
        qty = row["quantity"]
        avg = row["entry_price"]
        risk._open_positions[instrument] = qty
        risk._position_values[instrument] = avg * qty
        risk._capital_deployed += avg * qty
        # Restore strategy state
        for strat in strategies:
            if strat.instrument == instrument:
                strat.on_order_update({"status": "COMPLETE", "signal_type": SignalType.ENTRY,
                                       "direction": "BUY", "average_price": avg, "instrument": instrument})
```

---

### R6-2. ✅ GTT-triggered P&L not accounted for on restart — daily loss limit blind spot — FIXED
**File:** `trader/risk/manager.py` — `__init__` and `main.py` startup

`_realised_pnl` always starts at `0.0` on startup. If a GTT fires while the system is running, `close_position()` is called via the WebSocket callback and P&L is accumulated correctly. But if the system restarts after a GTT fires today:

- The exit already happened at Zerodha
- `_realised_pnl = 0.0` on restart
- The loss from the GTT exit is invisible
- If the loss was large enough to trigger the daily halt, the bot doesn't know — it will continue placing new entries

**Fix:** On startup, read the realised P&L from `kite.positions()` net entries (Kite returns a `realised` field per position for the current day) and seed `_realised_pnl`:

```python
for p in kite_positions.get("net", []):
    realised = float(p.get("realised", 0.0))
    risk._realised_pnl += realised
    if not risk._halted and risk._realised_pnl <= -config.daily_loss_limit:
        risk._halted = True
        logger.warning("Halt triggered from seeded P&L on startup | pnl=%.2f", risk._realised_pnl)
```

---

## MEDIUM — Should fix

### R6-3. ✅ L5: GTT placed before fill confirmation — ghost GTT on unfilled limit orders — FIXED
**File:** `trader/orders/manager.py` — moved `_place_gtt_sl` from `_place_live()` to `on_kite_order_update()`

GTT is now placed only after `status == "COMPLETE" and direction == "BUY"` is confirmed via WebSocket. If the limit order is rejected, cancelled, or never fills (EOD cancellation at 3:30 PM), no GTT is placed.

---

### R6-4. ✅ `_instrument_orders` not cleaned up when BUY order is CANCELLED — FIXED
**File:** `trader/orders/manager.py:162-165` — `on_kite_order_update()`

When a BUY order is CANCELLED (e.g. unfilled limit at EOD), it is removed from `_live_orders` but remains in `_instrument_orders`. This map is the fallback used to recover context for GTT-triggered fills. A future GTT SELL for the same instrument (from a later re-entry) would find the stale BUY entry from the original cancelled order — wrong strategy context, wrong quantity.

**Fix:** One-line change — also pop `_instrument_orders` when a BUY is CANCELLED or REJECTED:

```python
if status in ("COMPLETE", "REJECTED", "CANCELLED"):
    self._live_orders.pop(order_id, None)
    if status == "COMPLETE" and direction == "SELL":
        self._instrument_orders.pop(instrument, None)
    if status in ("REJECTED", "CANCELLED") and direction == "BUY":
        self._instrument_orders.pop(instrument, None)
```

---

### R6-5. ✅ GTT `last_price` uses signal price_hint, not actual fill price — FIXED
**File:** `trader/orders/manager.py` — `_place_gtt_sl()` called from `on_kite_order_update()`

After the L5 fix, `_place_gtt_sl(original, symbol)` is called with the original Order, which has `price_hint = candle close at signal time`. For limit orders, the actual fill price may differ from `price_hint`. The GTT `last_price` parameter is used by Zerodha to validate that the trigger values straddle the current price. If slippage is large, the validation check could fail.

**Fix:** Pass the actual `fill_price` as `last_price` in the GTT call:

```python
# In on_kite_order_update, after the COMPLETE BUY check:
if status == "COMPLETE" and direction == "BUY" and config.gtt_enabled and original is not None:
    self._place_gtt_sl(original, symbol, last_price=fill_price)

# In _place_gtt_sl, accept optional last_price override:
def _place_gtt_sl(self, order: Order, symbol: str, last_price: float | None = None):
    price = last_price or order.price_hint
    result = self._kite.place_gtt(..., last_price=price, ...)
```

---

## Round 6 Summary

| ID | Severity | Issue |
|----|----------|-------|
| R6-1 | HIGH | Multi-day CNC positions lost on restart — seed from DB not kite.positions() |
| R6-2 | HIGH | GTT P&L not seeded on restart — daily loss limit blind on same-day restart |
| R6-3 | MEDIUM | ✅ L5 fixed — GTT only placed after fill confirmation |
| R6-4 | MEDIUM | `_instrument_orders` stale after CANCELLED BUY — wrong GTT context |
| R6-5 | MEDIUM | GTT last_price uses signal price_hint, not actual fill price |

**Verdict:** R6-1 is the most impactful — any restart during live trading (crash, deploy, token refresh) loses track of all multi-day positions. The bot will attempt to over-deploy capital and miss GTT P&L accounting. R6-2 is a daily loss limit blind spot. R6-4 and R6-5 are lower risk but both affect GTT correctness directly. Fix R6-1 and R6-2 before going live with GTT enabled.

---

## Round 7 — Backtest / script sync review

Non-critical gaps identified during a sync review of `main.py`, `scripts/backtest.py`, `scripts/calibrate.py`, `scripts/screen.py`, and `trader/backtest/engine.py`. None affect live trading.

### R7-1. `OPEN@END` backtest trades use entry price as exit — P&L always shows as −costs

**File:** `trader/backtest/engine.py:304`

```python
last_close = pos["entry"]   # should be last known candle close for the symbol
```

Positions still open at `to_dt` are closed at the entry price, so gross P&L = 0 and net P&L = −transaction costs. The real mark-to-market value is ignored. Makes backtest returns slightly pessimistic for unclosed positions but also masks unrealised losses.

**Severity:** Low — affects reporting only; no live trading impact.

---

### R7-2. `backtest.py` calls `store.clear_backtest_data()` on the live database

**File:** `scripts/backtest.py:47`

`store.clear_backtest_data()` wipes the `orders` and `signals` tables from `data/market.db` — the same file used by the live trader. Running a backtest while the live service is active destroys live order history. `calibrate.py` and `screen.py` correctly skip this call.

**Severity:** Medium in theory — harmless in practice because backtesting is always run locally, never on the EC2 live server.

---

### R7-3. Backtest engine is hardcoded to `LRExtremaStrategy`

**File:** `trader/backtest/engine.py:215`

```python
strategy_map.update({symbol: LRExtremaStrategy(symbol, params) for symbol in symbol_candles})
```

Only `LRExtremaStrategy` is instantiated. Any other strategy registered in `registry.py` is invisible to backtest/calibrate/screen. Not a current issue (single strategy), but any new strategy addition will need a matching engine change.

**Severity:** Low — no impact until a second strategy is added.

---

### R7-4. Paper mode catch-up exit recomputes SL/target from current config, not original signal

**File:** `main.py:138–140`

On restart, the paper mode catch-up logic recomputes stop and target prices from `lr_cfg.get("stop_pct")` and `lr_cfg.get("profit_pct")`. The `open_positions` table does not store the original SL/target from the signal. If config values change between sessions, the catch-up uses the new values and may incorrectly classify a candle as an SL/target hit.

**Severity:** Low — only affects paper mode restart edge case.

---

### R7-5. Dead debug line in `screen.py`

**File:** `scripts/screen.py:112`

```python
# breakpoint()
```

Harmless leftover comment from debugging.

**Severity:** Trivial.

---

## Round 7 Summary

| ID | Severity | Issue |
|----|----------|-------|
| R7-1 | Low | `OPEN@END` P&L shows 0 gross — uses entry price not last candle close |
| R7-2 | Medium* | `backtest.py` clears live DB tables — safe only because backtest never runs on EC2 |
| R7-3 | Low | Engine hardcoded to LRExtrema — new strategies need manual engine update |
| R7-4 | Low | Paper catch-up exit uses current config SL/target, not original signal values |
| R7-5 | Trivial | Dead `# breakpoint()` in `screen.py` |

**Verdict:** None of these affect live trading. R7-2 is the only one worth revisiting if the workflow ever changes (e.g. EC2 backtest runs or a second strategy).
