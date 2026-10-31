# Pre-order cash check: skip (don't send) a live BUY the account can't fund
Written: 2026-10-17 · Tag: TD-001 (also resolves ISS-02, mitigates ISS-13) · Status: DONE (pending release + first live skip)

## Source

> - **Pre-order real-margin check** — before placing a live ENTRY, fetch
>   `kite.margins("equity")` available cash and clamp quantity to what the account can
>   actually fund (skip if dust). Kills the insufficient-funds rejection class at the
>   source and serialises same-candle signal races honestly (2026-08-14: CHENNPETRO
>   filled at 15:15:02, MAYURUNIQ rejected at 15:15:03 with ₹1,430 available — the
>   ATHERENERG sale proceeds hadn't settled into usable margin yet).

— `TODO/TD-001-pre-order-real-margin-check/DETAIL.md` (from todo.md), as of 2026-10-17.

> **2. MEDIUM: a broker-rejected add-on is re-placed on every decision candle.** … So a new add-on order goes out
> every 15m bar while P(min) stays above threshold, with a Telegram reject alert each time. Insufficient-funds
> rejects (#1, #3, #6) trigger this directly.

— `ISSUES/ISS-02-rejected-addon-refires-every-candle/DETAIL.md`, as of 2026-10-17.

Owner, 2026-10-17: "2 note it was tried, but dont block, given the model continues to remain bullish on that." →
after the proposal (check cash before every order; skip and record instead of sending; retry next candle while the
model stays bullish): "Item 2 should be built."

## Intent

Before a **live** ENTRY order (parent entry or scale-in add-on) is sent to Kite, read live free cash (`net`, via the
existing `_fetch_kite_cash()`, ISS-01). If the account cannot fund `quantity × price_hint × 1.01`, do NOT send the
order: release the risk pending lock, stamp the signal row `accepted=0` with
`reject_reason="insufficient_cash: need ₹X, have ₹Y"`, clear the strategy's pending-entry guard (parent entries) so
the next decision candle can try again, log at INFO. **No Telegram, no broker order, no block** — the stock keeps
trading; if the model is still bullish next candle and cash has arrived, it goes through.

Decisions carried by this guide (do not revisit):
- **Skip, don't clamp.** Quantity sizing stays exactly as risk.validate decided (clamping would be a live-only sizing
  rule the backtest doesn't have). A partial-size clamp is out of scope.
- **Fail open.** If the margins call fails (`None`), place the order as today.
- **Buffer 1 %** (`CASH_CHECK_BUFFER = 1.01`) for charges + market-order slippage.
- EXIT orders (and anything not `SignalType.ENTRY`) are never checked. NB: strategy EXIT *signals* use
  `Direction.BUY`, so gate on `order.signal_type == SignalType.ENTRY`, never on direction.
- Paper mode and the backtest are untouched.

Must NOT change: risk sizing, `risk.validate`, the broker-REJECTED path in `handle_order_update`, backtest engine,
`on_pre_order_reject` semantics.

## Implementation steps

1. **`trader/risk/manager.py`** — below `free_cash_from_margins`, add:
   ```python
   CASH_CHECK_BUFFER = 1.01  # charges + market-order slippage headroom for the pre-order cash check


   def unfunded_entry(order: "Order", free_cash: float | None,
                      buffer: float = CASH_CHECK_BUFFER) -> float | None:
       """₹ needed when a live ENTRY order can't be funded from `free_cash`, else None.

       None (= go ahead) for non-ENTRY orders and when free cash is unknown (margins call
       failed → fail open, place as before). Needed = quantity × price_hint × buffer."""
   ```
   `Order` is defined above in the same module, so reference it directly (no quotes needed if placed after the class —
   place the function after `class Order`). Return `need` (float) iff `order.signal_type == SignalType.ENTRY`,
   `free_cash is not None` and `free_cash < need`; else `None`. Import `SignalType` only if not already imported
   (check the module's imports).

2. **`trader/data/store.py`** — refactor `mark_signal_broker_rejected` into a generic method plus the existing one:
   ```python
   def mark_signal_rejected(self, instrument: str, direction: str, reason: str) -> bool:
       """<move the existing docstring's targeting rules here>; reject_reason is stored as given."""
   def mark_signal_broker_rejected(self, instrument: str, direction: str, reason: str) -> bool:
       return self.mark_signal_rejected(instrument, direction, f"BROKER: {reason}")
   ```
   Keep the `[:300]` truncation in the generic method. Behaviour of `mark_signal_broker_rejected` must be identical.

3. **`main.py`**:
   - Import `unfunded_entry` alongside the existing `trader.risk.manager` imports.
   - Change `_place_order(order)` to `_place_order(order, strategy=None, signal=None)` and, before `orders.place`, add:
     ```python
     if config.env == "live":
         need = unfunded_entry(order, _fetch_kite_cash() if order.signal_type == SignalType.ENTRY else None)
         if need is not None:
             ...skip (see below)...
             return
     ```
     Only call `_fetch_kite_cash()` for ENTRY orders (exits must not pay for an API call). The skip block:
     - `cash` = the value just fetched (keep it in a local; do not fetch twice).
     - `reason = f"insufficient_cash: need ₹{need:,.0f}, have ₹{cash:,.0f}"`
     - `logger.info("Order skipped — %s | %s%s", reason, order.instrument, " (add-on)" if order.addon else "")`
     - `risk.on_order_cancelled(order.instrument)`
     - `store.mark_signal_rejected(order.instrument, order.direction.value, reason)` inside `try/except Exception`
       (log at debug, like the broker path).
     - if `strategy` and `signal` are given: `hook = getattr(strategy, "on_pre_order_reject", None)`; call
       `hook(signal, "insufficient_cash")` when not None. (For an add-on the strategy holds a position, so the hook is a
       no-op by design.)
     - No telegram call.
   - Keep the existing docstring and add one sentence: live ENTRY orders the account can't fund are skipped before
     placement (TD-001).
   - Update the two call sites: `run_strategy_decision` → `_place_order(order, strategy, signal)`; the tick path →
     `_place_order(order, strat, signal)`.

4. No other files.

## Tests required

New **`tests/test_pre_order_cash_check.py`**:
- `test_funded_entry_goes_ahead` — ENTRY qty 10 @ 100, cash 2,000 → `None`.
- `test_unfunded_entry_returns_need` — ENTRY qty 10 @ 100, cash 500 → `1010.0` (approx, `pytest.approx`).
- `test_buffer_edge` — cash exactly 1,000 for qty 10 @ 100 → not None (needs 1,010).
- `test_addon_entry_checked` — `addon=True` ENTRY behaves the same.
- `test_exit_never_checked` — `signal_type=SignalType.EXIT`, cash 0 → `None`.
- `test_unknown_cash_fails_open` — cash `None` → `None`.
- `test_mark_signal_rejected_stores_reason_verbatim` (tmp_path Store) — log an accepted BUY ENTRY signal, call
  `mark_signal_rejected(..., "insufficient_cash: need ₹1,010, have ₹500")`, read the row back: `accepted == 0`,
  reason verbatim; and `mark_signal_broker_rejected` still stores `"BROKER: <reason>"`.

In **`tests/test_pre_order_reject_guard.py`** add `"insufficient_cash"` to the parametrize list of
`test_pre_order_reject_clears_pending_entry_guard`.

Whole suite green: `python -m pytest -q` (only ISS-11 `test_render_page_health_strip` may fail, 09:15–15:30 IST).

## Acceptance checklist
- [ ] full pytest green (apart from ISS-11 in its time window)
- [ ] new tests present and passing; `insufficient_cash` added to the guard-clearing parametrize
- [ ] check runs only in live mode and only for `SignalType.ENTRY` orders; margins fetched once per such order
- [ ] skip path: pending lock released, signal row stamped, guard hook called, no Telegram, no `orders.place`
- [ ] `mark_signal_broker_rejected` behaviour unchanged
- [ ] no backtest / paper behaviour change; no `trader.backtest` import added
- [ ] only `trader/risk/manager.py`, `trader/data/store.py`, `main.py` and the two test files touched

## Completion record
- **Completed:** 2026-10-17 — implementer (general-purpose, sonnet); validated by the main session (diff read vs every step; `python -m pytest -q` 542 passed).
- **Commit:** see `git log -- to_develop/completed/2026-10-17_TD-001_pre-order-cash-check.md`.
- **Deviations:** none. `unfunded_entry` placed after `class Order`, above `scale_in_pool`.
- **Notes:** the main.py skip branch lives inside `main()` and has no direct test (helper + store method are tested).
  Field check owed: first live `Order skipped — insufficient_cash` line + signal row `accepted=0` on the dashboard.
