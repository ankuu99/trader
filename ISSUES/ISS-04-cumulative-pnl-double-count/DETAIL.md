# ISS-04: `capital_available` adds cumulative_pnl on top of Kite equity that already contains it

Source: Independent production-safety review 2026-10-17, finding 3; previously `todo.md` (2026-08-16 insufficient-funds forensics). Reproduced verbatim; dated addenda below. Never delete.

---

**3. MEDIUM (old bug, new exposure): `cumulative_pnl` is counted twice.** (risk/manager.py:128)
- `capital_available` adds `cumulative_pnl` on top of a Kite equity figure that already includes realised P&L.
- Now that the pool equals equity above ₹6L, base entries plus pool together promise ₹cum_pnl more than the account's cash.
- It's harmless right now only because `cumulative_pnl` is 0.0 in the state table. It comes back as profitable trades close.

## Original entry — todo.md, as of 2026-10-17

- **Fix cumulative_pnl double-count in `capital_available`** — at startup
  `effective_capital = min(config_cap, kite_cash + deployed)` (main.py:440-443) is
  account *equity*, which already contains all realised P&L; `capital_available`
  (risk/manager.py:111) then adds `_cumulative_pnl` (₹21k) on top again, so the bot
  permanently believes it has ~₹21k more than the account holds and always attempts
  one order more than can be funded. Fix: when the equity cap binds, seed the ledger
  so `total_capital + cumulative_pnl` equals real equity (e.g. set effective capital
  to `equity − cumulative_pnl`), or stop adding pnl when capital was set from equity.
