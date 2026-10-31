# Partial scale-out: reduce persisted lots proportionally, like the in-memory ledger
Written: 2026-10-17 · Tag: ISS-03 · Status: DONE (pending release)

## Source

> **4. MEDIUM: a partial scale-out on a position with add-ons gets different accounting after the overnight reboot.** (risk/manager.py:685-699 vs store.py:583-611)
> - In memory, a partial sale reduces the add-on cost basis pro rata. The DB uses FIFO (parent lot sold first).
> - Since the box reboots daily, every such multi-day position goes through this.
> - After the reboot the pool usage, blended average entry, realised P&L, cumulative P&L and **whether the loss block arms** all change.
> - `/tmp/review_tests/test_restart_divergence.py` shows it: parent 100@100, add-on 50@90, partial 75@105, close @95.
>   - Pool: 2,250 without reboot vs 4,500 after reboot.
>   - Average entry: 96.67 vs 93.33.
>   - Loss block: armed without reboot, **not armed** after reboot.
> - The backtest has no reboots, so live and backtest disagree. Confidence: verified by test.

— `ISSUES/ISS-03-partial-scaleout-addon-restart-divergence/DETAIL.md` (see its 2026-10-17 impact addendum: the mix
also books phantom P&L into `cumulative_pnl`, ₹250 in the example, and the dashboard lot ladder shows oldest-first
numbers right after the scale-out). Owner, 2026-10-17: "yes, let;s build that."
Related: ISS-04 (cumulative P&L now sizes the base sleeve), TD-015 (out of scope, below).

## Intent

`RiskManager.reduce_position` (in memory, and in the backtest) reduces a scaled-in position's cost basis
**proportionally**: fraction `f = sold / held` comes off the parent and off every add-on lot. `Store.consume_position_lots`
(what the daily reboot re-seeds from, and what the dashboard ladder reads) consumes **oldest-first**. Make the DB
proportional too, in whole shares, so a reboot reproduces the in-memory state (to within one share per lot).

Also preserve each add-on lot's **original notional** so a reboot after a scale-out rebuilds `last_lot_notional`
(the size base for the next geometric add-on) the same as memory, which never shrinks it.

Must NOT change: `RiskManager` (reduce_position, close_position, seeding logic other than the `notional` read below),
the backtest engine and its FIFO per-lot trade records, `analytics.match_trades`, closed-trade / monthly dashboard
cards, the parent `entry_price` / `entry_time` (stale anchor), the DB schema (the new key lives inside the existing
`addon_lots` JSON).

## Implementation steps

1. **`trader/data/store.py::add_position_lot`** — add `"notional": fill_price * quantity` to the appended lot dict.
   Docstring: one sentence that `notional` is the lot's original ₹ size and is never reduced by scale-outs.

2. **`trader/data/store.py::consume_position_lots`** — replace the oldest-first body with proportional allocation:
   - read `qty`, `lots` as today; `sold = min(max(int(sold_qty), 0), qty)`; if `sold == 0` return without writing.
   - `parts = [parent_qty] + [int(l["qty"]) for l in lots]` with `parent_qty = max(qty - Σ lot qty, 0)` as today.
   - Largest-remainder split of `sold` over `parts` weighted by size: `ideal_i = parts_i * sold / qty`,
     `take_i = floor(ideal_i)`; hand the remaining `sold - Σ take_i` shares out one each in order of descending
     fractional part `ideal_i - take_i`, ties to the lower index (parent first). (Guarantees `take_i ≤ parts_i` and
     `Σ take_i == sold`.)
   - New lots: every add-on lot is KEPT with `qty = parts_i - take_i`, **including lots that reach 0** (keeps the tier
     count and the last-investment date intact across a reboot); all other keys (`price`, `date`, `notional`) unchanged.
   - Write `quantity = qty - sold` and `addon_lots = json.dumps(new_lots) if new_lots else None` (unchanged shape).
   - Rewrite the docstring: proportional, why (matches `RiskManager.reduce_position` and the backtest's ledger, so the
     daily reboot doesn't change avg cost, pool usage, realised/cumulative P&L or loss-block arming — ISS-03),
     whole shares via largest remainder, zero-qty lots retained.

3. **`trader/risk/manager.py::seed_scale_in`** — the only RiskManager change: `state["last_lot_notional"] =
   float(lot.get("notional") or lot_value)` (legacy lots without the key keep today's behaviour). `addon_value` and
   quantity still come from the CURRENT `qty × price` (a zero-qty lot adds nothing to either but still counts a tier).

4. **`trader/analytics.py::position_entry_legs`** — skip add-on lots whose `qty` is 0 when building `legs` (they carry
   no shares or cost; keep `addon_qty` / `avg_cost` maths otherwise identical). If after skipping no add-on leg remains,
   omit the position as today ("positions without add-ons are omitted").

5. **`main.py`** — only the comment above `store.consume_position_lots(instrument, quantity)` (~line 632): replace
   "Consumes lots FIFO (parent first, then add-ons)" with "Consumes lots proportionally — same as risk.reduce_position —"
   keeping the rest of the sentence.

## Tests required

In **`tests/test_scale_in.py`**:
- Replace `test_consume_position_lots_fifo_parent_first` with `test_consume_position_lots_proportional`:
  - parent 100 + lots 26 @95, 6 @93 (qty 132), consume 110 → quantity 22, lot qtys `[4, 1]`, parent 17
    (ideal 83.33/21.67/5.0 → takes 83/22/5).
  - parent 100 + lot 26, consume 50 → quantity 76, lot qty `[16]`, parent 60 (takes 40/10).
  - lot `price` / `date` / `notional` unchanged after consumption.
- Update `test_restart_seed_after_partial_scale_out`: parent 100 @100 + 26 @95, consume 110 → reseeded open qty 16,
  parent 13, `scale_in_deployed == pytest.approx(95.0 * 3)`; and within one share's price of the in-memory value
  `2470 * (1 - 110/126)` (`abs(diff) <= 95.0`).
- New `test_zero_qty_lot_kept_and_tier_preserved`: parent 3 @100 + lot 1 @95 (qty 4), consume 3 → ideal 2.25/0.75 →
  takes 2/1 → quantity 1, parent 1, `addon_lots == [{…, "qty": 0, …}]` (kept, length 1); reseed → open qty 1 and
  `risk._scale_in[INSTRUMENT]["addon_count"] == 1`; `position_entry_legs` omits the position (no non-zero add-on leg).
- New `test_notional_survives_scale_out`: add lot 26 @95 → `notional == 2470`; consume 110; reseed →
  `risk._scale_in[INSTRUMENT]["last_lot_notional"] == 2470`. Legacy lot dict without `notional` → falls back to
  `price × qty` (seed directly via `seed_scale_in`).

New **`tests/test_scaleout_reboot_parity.py`** — the reviewer's repro made permanent (use the loss-block config helper
`_block` from `tests/test_loss_reentry_block.py` and the scale-in config helper used in `tests/test_scale_in.py`):
- Path A (no reboot): `risk.on_order_filled(INST, 100.0, 100)`, `risk.on_order_filled(INST, 90.0, 50, addon=True)`,
  `risk.reduce_position(INST, 75, 105.0)`, then `risk.close_position(INST, 95.0)`.
- Path B (reboot after the scale-out): same fills/partial on a second RiskManager AND the Store
  (`upsert_open_position(INST, 100.0, 100, …)`, `add_position_lot(INST, 90.0, 50, …)`, `consume_position_lots(INST, 75)`);
  then a fresh RiskManager seeded exactly like main.py (parent = quantity − Σ lot qty → `seed_position`,
  `seed_scale_in`, `seed_cumulative_pnl(<path-B pre-reboot cumulative>)`), then `close_position(INST, 95.0)`.
- Assert after the scale-out / reseed: avg cost equal (`position_values / qty`, abs ≤ 0.01), `scale_in_deployed` equal
  (≤ 1 share × lot price); after the close: `cumulative_pnl` equal (abs ≤ 1.0) and both have the loss block armed
  (`loss_reentry_state` contains INST). With these numbers f = 0.5 exactly, so values should match exactly.

Whole suite green: `python -m pytest -q` (only ISS-11 may fail 09:15–15:30 IST).

## Acceptance checklist
- [ ] full pytest green (apart from ISS-11 in its window)
- [ ] FIFO test replaced, restart test updated, 3 new tests + parity file present and passing
- [ ] `Σ take == sold` and no lot goes negative for every case (assert inside the tests)
- [ ] RiskManager changed only in `seed_scale_in`'s `last_lot_notional` line; engine / match_trades untouched
- [ ] no schema change; `addon_lots` JSON shape backward compatible (legacy lots without `notional` still load)
- [ ] only store.py, manager.py, analytics.py, main.py (comment) and the test files touched

## Out of scope → TD-015
A position with NO add-ons that scales out and reboots re-seeds `last_lot_notional` from the reduced parent
(`seed_position` uses `entry_price × remaining qty`), so its first later add-on is sized off the smaller remainder;
memory keeps the original parent notional. Needs the original parent quantity persisted — tracked as TD-015.

## Completion record
- **Completed:** 2026-10-17 — implementer (general-purpose, sonnet); validated by the main session (diff limited to
  store.py / manager.py (1 line in seed_scale_in) / analytics.py / main.py comment + tests; `python -m pytest -q` 551 passed).
- **Commit:** see `git log -- to_develop/completed/2026-10-17_ISS-03_proportional-lot-consumption.md`.
- **Deviations:** none in the final diff (a first manager.py edit hit the wrong `last_lot_notional` line, in
  `on_order_filled`; the implementer caught it via 6 failing tests and moved it).
- **Notes:** no live add-on positions exist, so no migration. CLAUDE.md Scale-in → Persistence updated. TD-015 filed.
