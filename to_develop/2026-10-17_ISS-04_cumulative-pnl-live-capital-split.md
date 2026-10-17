# Live capital split: stop double-counting realised P&L; profits grow the base sleeve first
Written: 2026-10-17 · Tag: ISS-04 · Status: OPEN

## Source

> **3. MEDIUM (old bug, new exposure): `cumulative_pnl` is counted twice.** (risk/manager.py:128)
> - `capital_available` adds `cumulative_pnl` on top of a Kite equity figure that already includes realised P&L.
> - Now that the pool equals equity above ₹6L, base entries plus pool together promise ₹cum_pnl more than the account's cash.
> - It's harmless right now only because `cumulative_pnl` is 0.0 in the state table. It comes back as profitable trades close.
>
> (todo.md, 2026-08-16) … Fix: when the equity cap binds, seed the ledger so `total_capital + cumulative_pnl` equals
> real equity (e.g. set effective capital to `equity − cumulative_pnl`), or stop adding pnl when capital was set from equity.

— `ISSUES/ISS-04-cumulative-pnl-double-count/DETAIL.md`, as of 2026-10-17.
Owner, 2026-10-17: "4. yes we shoudl fix." → asked (a) profits grow the base sleeve first, pool = equity above
base + profits (matches the backtest) vs (b) everything above ₹6L incl. profits funds the pool → "Item 4 should be a."
Related: ISS-01 (live cash = margins `net`, done), ISS-06 (out of scope).

## Intent

Live, the base trading sleeve is `config.total_capital + risk.cumulative_pnl` (that is what `capital_available` and the
compounding per-stock cap use). `_apply_effective_capital` sets `total_capital = min(base, equity)` — when the equity
cap binds, the sleeve becomes `equity + cum_pnl` (double count), and the pool `equity − base` also claims the profits.

New rule (option a, mirrors the backtest where the sleeve compounds and the pool sits on top):
- sleeve ceiling `S = base + cum_pnl`
- `effective_total = max(0, min(base, equity − cum_pnl))` → `effective_total + cum_pnl = min(S, equity)`
- `pool = min(cap, max(0, equity − S))` (reuse `scale_in_pool(equity, S, cap)`)

With `cum_pnl = 0` (today's live value) this is byte-identical to the current behaviour. With losses (`cum_pnl < 0`) the
sleeve shrinks like the backtest's compounding, so a cash top-up above the shrunken sleeve funds the pool — intended.

Must NOT change: `capital_available`, `scale_in_pool`, the compounding per-stock cap, `config.scale_in_budget_cap`,
backtest/paper (they never call `_apply_effective_capital`), ISS-01's cash source.

## Implementation steps

1. **`trader/risk/manager.py`** — below `scale_in_pool`, add:
   ```python
   def live_capital_split(account_equity: float, base_capital: float,
                          cumulative_pnl: float, pool_cap: float) -> tuple[float, float]:
       """(effective total_capital, scale-in pool) for live mode.

       The base sleeve is total_capital + cumulative_pnl (what capital_available and the
       compounding per-stock cap use), so realised profits grow the sleeve first — as in the
       backtest — and only equity above base + profits funds the add-on pool. Kite equity
       already contains realised P&L: setting total_capital = equity would count it twice.
       effective_total + cumulative_pnl = min(base + cumulative_pnl, equity); floor 0."""
   ```
   Body: `sleeve = base_capital + cumulative_pnl`; `effective = max(0.0, min(base_capital, account_equity - cumulative_pnl))`;
   `pool = scale_in_pool(account_equity, sleeve, pool_cap)`; return `(effective, pool)`.

2. **`main.py::_apply_effective_capital`**:
   - Import `live_capital_split` with the other `trader.risk.manager` imports.
   - Replace `effective = min(config_ceiling, account_equity)` with
     `effective, pool = live_capital_split(account_equity, config_ceiling, risk.cumulative_pnl, config.scale_in_budget_cap)`.
   - In the scale-in block, delete the `pool = scale_in_pool(...)` line and use the `pool` from the split.
   - Extend the "Effective capital set" log line with `cum_pnl=%.0f sleeve=%.0f` (sleeve = `config_ceiling + risk.cumulative_pnl`).
   - Set `bot_state.capital_floor = config_ceiling + risk.cumulative_pnl` next to `bot_state.account_equity`.
   - In the scale-in log line, replace "equity %.0f above base %.0f" values with equity above the sleeve and the sleeve.
     Keep the wording otherwise; change the "no add-ons until the account holds more than the base" tail to
     "… more than base + realised P&L".
   - Update the comment block above the function: mention that cumulative P&L is NOT added on top of equity (ISS-04).
   - If `scale_in_pool` is no longer used in main.py after this, remove it from the import.

3. **`trader/ui/state.py`** — add `capital_floor: float | None = None` next to `account_equity`, with a one-line comment
   ("live: base + realised P&L — equity above it funds scale-in").

4. **`trader/ui/template.py`** (Account equity row, ~line 1618):
   `_base = getattr(bot_state, "capital_floor", None)`; if `None`, fall back to `getattr(config, "base_capital", total)`.
   Label text: when `capital_floor` is set and differs from `config.base_capital` by ≥ ₹1, render
   `vs ₹{floor} base + realised P&L`; otherwise keep `vs ₹{base} base`. Keep the rest of the row as is.

## Tests required

New **`tests/test_live_capital_split.py`**:
- `test_zero_pnl_matches_previous_behaviour` — cum 0: (494k → (494k, 0)), (630k → (600k, 30k)), (700k → (600k, 60k)) with
  base 600k, cap 60k.
- `test_profits_grow_sleeve_before_pool` — cum +50k: equity 650k → (600k, 0); 680k → (600k, 30k); 730k → (600k, 60k).
- `test_account_below_sleeve_no_double_count` — cum +50k, equity 550k → effective 500k (effective + cum == equity), pool 0.
- `test_losses_shrink_sleeve` — cum −50k: equity 550k → (600k, 0) [600k − 50k = 550k sleeve]; equity 600k → (600k, 50k).
- `test_invariants` — for equity in range(300k, 900k, 10k) and cum in (−100k, 0, 50k, 150k) with equity ≥ cum:
  `eff + cum <= equity + 1e-6` and `eff + cum + pool <= equity + 1e-6` and `pool <= cap` and `eff >= 0`.
- `test_floor_zero` — equity 10k, cum 50k → effective 0.0.

Extend **`tests/test_ui_render_page.py`** only if a render test for the Account equity row already exists (grep
`Account equity`); if it does, add a case with `bot_state.capital_floor = 650_000` asserting "base + realised P&L"
appears. If none exists, do not create a new render harness — report that.

Whole suite green (`python -m pytest -q`; only ISS-11 may fail 09:15–15:30 IST).

## Acceptance checklist
- [ ] full pytest green (apart from ISS-11 in its window)
- [ ] new tests present and passing
- [ ] with cum_pnl = 0 the live outputs are identical to before (test_zero_pnl_matches_previous_behaviour)
- [ ] `capital_available`, `scale_in_pool`, backtest/paper untouched; no `trader.backtest` import added
- [ ] dashboard falls back cleanly when `capital_floor` is None
- [ ] only manager.py, main.py, trader/ui/state.py, trader/ui/template.py and tests touched

## Completion record
(appended at archive)
