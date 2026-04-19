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

## Summary

| Severity | Count | Key theme |
|----------|-------|-----------|
| CRITICAL | 6 | Loss limit unenforced, GTT orphaning, stuck strategy state, missing candles |
| HIGH | 4 | Volume skew, backtest bias, silent rejections, no state recovery |
| MEDIUM | 6 | Config risk, concurrency, P&L reporting |
| LOW | 4 | Logging, minor inefficiency, naming |

**Verdict:** The system is well-structured and works correctly in paper/backtest mode. However, it is **not ready for live trading** without fixing the 6 critical issues — particularly the unenforced daily loss limit (#1), orphaned GTTs (#2), and stuck strategy state after rejection (#3, #4). These can cause unbounded losses or missed trades in production.
