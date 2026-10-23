# ISS-01: Scale-in pool & effective capital use Kite opening cash — same-day restart double-counts buys

Source: Independent production-safety review 2026-10-17, finding 1 (`reviews/production_safety_scalein_lossblock_20261017.md`). Reproduced verbatim; dated addenda below. Never delete.

---

**1. MEDIUM-HIGH: the scale-in pool can be funded by money that isn't there after a same-day restart.** (main.py:84-85, 494)
- `margins["available"]["cash"]` is the **opening** balance. It does not drop when the bot buys during the day.
- After a restart on the same day as some buys, equity = cash + deployed counts those buys twice.
- Seen in the server logs: the 10-15 evening restart logged `account_equity=611981 (cash=157733 + deployed=454248)`. The next boot showed the real figure, about ₹4.88L.
- With the new code that restart would create a ₹12k pool, and lift effective capital to ₹6L, from money that doesn't exist.
- Effect: during a mid-session crash or deploy, add-on and base orders compete for cash that isn't there, and Kite rejects them for insufficient funds. A same-day sell does the opposite (understates equity), which is the safe direction.
- Fix: use `available.live_balance` or `net`. Confidence: verified (logs plus code).

## Addendum 2026-10-17 — Kite margins evidence (Saturday read)

`kite.margins('equity')` after the owner's ₹1L top-up: `available.cash` 25,102.9 = `opening_balance`; `intraday_payin` 100,000; `live_balance` 125,102.9; `net` 125,102.9. The field the bot reads (`cash`) missed the same-day payin as well as same-day buys.

## Addendum 2026-10-17 — fixed (1756139)

`free_cash_from_margins` (trader/risk/manager.py) reads `net` → `available.live_balance` → `available.cash`; `main.py::_fetch_kite_cash` uses it and logs all raw fields. Guide: `to_develop/completed/2026-10-17_ISS-01_live-cash-from-margins-net.md`. Not yet released.
