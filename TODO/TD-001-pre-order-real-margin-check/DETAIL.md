# TD-001: Pre-order real-margin check before live ENTRY (clamp qty to Kite available cash)

Source: `todo.md`, as of 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

## Capital / execution layer (from 2026-08-16 insufficient-funds forensics)

62 live broker rejections (49 in July) were "Insufficient funds" — the model called
the KPL/MAYURUNIQ dips correctly (p_min 0.87–0.98) but the orders died at Zerodha.
The slow-TF slot cap (`risk.max_slow_tf_positions`) was built for the
capital-turnover side but **FALSIFIED by A/B backtest** (2025-01→2026-08:
baseline ₹294k/Calmar 3.09 → cap=6 ₹242k → cap=4 ₹194k; DD not improved) —
slow-TF trades are the biggest winners, capping them churns capital into marginal
15m entries. It stays in code as a config-gated defensive option, OFF. That makes
these ledger/execution fixes the ONLY live path to capturing the rejected dips:

- **Pre-order real-margin check** — before placing a live ENTRY, fetch
  `kite.margins("equity")` available cash and clamp quantity to what the account can
  actually fund (skip if dust). Kills the insufficient-funds rejection class at the
  source and serialises same-candle signal races honestly (2026-08-14: CHENNPETRO
  filled at 15:15:02, MAYURUNIQ rejected at 15:15:03 with ₹1,430 available — the
  ATHERENERG sale proceeds hadn't settled into usable margin yet).

## Addendum 2026-10-17 — built

Built as a skip (not a clamp), owner-approved ("Item 2 should be built"). Guide: `to_develop/completed/2026-10-17_TD-001_pre-order-cash-check.md`.
