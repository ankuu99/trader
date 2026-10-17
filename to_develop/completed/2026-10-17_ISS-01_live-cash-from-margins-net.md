# Read live free cash from Kite margins `net`, not the opening `cash`
Written: 2026-10-17 · Tag: ISS-01 · Status: DONE (pending release + field validation)

## Source

> **1. MEDIUM-HIGH: the scale-in pool can be funded by money that isn't there after a same-day restart.** (main.py:84-85, 494)
> - `margins["available"]["cash"]` is the **opening** balance. It does not drop when the bot buys during the day.
> - After a restart on the same day as some buys, equity = cash + deployed counts those buys twice.
> - Seen in the server logs: the 10-15 evening restart logged `account_equity=611981 (cash=157733 + deployed=454248)`. The next boot showed the real figure, about ₹4.88L.
> - With the new code that restart would create a ₹12k pool, and lift effective capital to ₹6L, from money that doesn't exist.
> - Effect: during a mid-session crash or deploy, add-on and base orders compete for cash that isn't there, and Kite rejects them for insufficient funds. A same-day sell does the opposite (understates equity), which is the safe direction.
> - Fix: use `available.live_balance` or `net`. Confidence: verified (logs plus code).
>
> Addendum 2026-10-17 — `kite.margins('equity')` after the owner's ₹1L top-up: `available.cash` 25,102.9 = `opening_balance`; `intraday_payin` 100,000; `live_balance` 125,102.9; `net` 125,102.9.

— `ISSUES/ISS-01-scalein-pool-opening-cash-double-count/DETAIL.md`, as of 2026-10-17. Owner approval: "1. yes" (2026-10-17).
Related: ISS-04 (cumulative_pnl double count, separate guide), ISS-06 (fallback pool, out of scope), TD-001.

## Intent

`main.py::_fetch_kite_cash` feeds `_apply_effective_capital` (effective capital + live scale-in pool). It reads
`available.cash`, which is the day's opening balance: it ignores same-day buys (overstates equity after a
mid-session restart) and same-day pay-ins. Switch to Kite's `net` (net cash available for trading), falling back
to `available.live_balance`, then `available.cash`, and log the raw fields so the choice can be validated on the
first live session.

Must NOT change: the equity formula in `_apply_effective_capital` (cash + capital_deployed + scale_in_deployed),
`scale_in_pool`, `capital_available`, anything in the backtest path, the boot/09:00 retry flow, or paper mode.

## Implementation steps

1. **`trader/risk/manager.py`** — add a pure module-level function directly below `scale_in_pool`:

   ```python
   def free_cash_from_margins(margins: dict) -> float | None:
       """Live free cash from a Kite ``margins(segment="equity")`` payload.

       ``net`` first: it moves with same-day buys and pay-ins. ``available.cash`` is the
       day's OPENING balance — a mid-session restart after buys would count them twice
       (cash + deployed). Falls back to ``available.live_balance``, then ``available.cash``.
       None when no usable numeric field exists."""
   ```
   Behaviour: try, in order, `margins.get("net")`, `margins.get("available", {}).get("live_balance")`,
   `margins.get("available", {}).get("cash")`; return `float(value)` for the first value that is an `int` or
   `float` (not `bool`, not `None`, not a string). Negative values are returned as-is (debit balance). If
   `margins` is not a dict or nothing qualifies, return `None`. Guard `available` not being a dict.

2. **`main.py`**:
   - Extend the existing import `from trader.risk.manager import RiskManager, scale_in_pool` to also import
     `free_cash_from_margins`.
   - Rewrite the body of `_fetch_kite_cash()` (currently main.py:77-89):
     ```python
     try:
         margins = kite.margins(segment="equity")
     except Exception as e:
         logger.warning("Failed to fetch Kite margins: %s", e)
         return None
     avail = margins.get("available", {}) if isinstance(margins, dict) else {}
     cash = free_cash_from_margins(margins)
     logger.info(
         "Kite margins | net=%s live_balance=%s opening=%s cash=%s intraday_payin=%s debits=%s -> using %s",
         margins.get("net") if isinstance(margins, dict) else None,
         avail.get("live_balance"), avail.get("opening_balance"), avail.get("cash"),
         avail.get("intraday_payin"),
         (margins.get("utilised") or {}).get("debits") if isinstance(margins, dict) else None,
         f"{cash:.0f}" if cash is not None else "none",
     )
     if cash is None:
         logger.warning("Kite margins payload had no usable cash field: %s", margins)
     return cash
     ```
   - Update the docstring's first line to: `"""Live free equity cash from Kite margins (`net`), or None if the call fails.`
     Keep the rest of the docstring (RMS-offline note) unchanged.
   - Do not change any caller.

3. No other files.

## Tests required

New file **`tests/test_free_cash_from_margins.py`**:
- `test_prefers_net_over_opening_cash` — the real 2026-10-17 payload
  `{"net": 125102.9, "available": {"cash": 25102.9, "opening_balance": 25102.9, "live_balance": 125102.9, "intraday_payin": 100000}}` → `125102.9`.
- `test_intraday_buys_reduce_net` — `{"net": 3733.0, "available": {"cash": 157733.0, "live_balance": 3733.0}}` → `3733.0`
  (the 10-15 restart shape: opening cash 157,733, ₹154k bought that day).
- `test_falls_back_to_live_balance` — no `net` key → live_balance.
- `test_falls_back_to_cash` — no `net`, no `live_balance` → cash.
- `test_none_and_non_numeric_skipped` — `{"net": None, "available": {"live_balance": "abc", "cash": 10.0}}` → `10.0`;
  `True` is not accepted as a number.
- `test_negative_net_returned` — `{"net": -500.0}` → `-500.0`.
- `test_unusable_payload_returns_none` — `{}`, `{"available": None}`, `None` → `None`.

Suites that must stay green: whole `python -m pytest -q` except the known pre-existing failures
(ISS-10 `test_parity_golden`, ISS-11 `test_render_page_health_strip` during 09:15–15:30).

## Acceptance checklist
- [ ] full pytest green apart from ISS-10 / ISS-11
- [ ] new tests present and passing
- [ ] `_fetch_kite_cash` uses `free_cash_from_margins`; no other main.py behaviour changed
- [ ] no `trader.backtest` import added to main.py / trader/risk
- [ ] backtest path untouched (the new function is not called by the engine)
- [ ] owner's uncommitted work untouched (`git diff --stat` shows only manager.py, main.py, the new test)

## Completion record
- **Completed:** 2026-10-17 — implementer (general-purpose, sonnet, role file `.claude/agents/trader-implementer.md`); validated by the main session.
- **Commit:** the commit that moved this file to `completed/` (see `git log -- to_develop/completed/2026-10-17_ISS-01_live-cash-from-margins-net.md`).
- **Deviations:** none.
- **Validation:** diff read against every step; `python -m pytest -q` → 533 passed, 1 failed (`test_pipeline_golden`, ISS-10, pre-existing); 7 new tests in `tests/test_free_cash_from_margins.py`. Only `main.py`, `trader/risk/manager.py` and the new test touched. Backtest path unaffected (new function unused by the engine).
- **Notes:** not yet released. Field validation owed on the first live session with a buy: the `Kite margins |` log line must show `net` falling by the buy amount (opening `cash` unchanged). CLAUDE.md "Effective capital in live mode" updated.
