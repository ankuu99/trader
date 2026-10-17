# Persist the original parent notional so add-on sizing survives a scale-out + reboot
Written: 2026-10-17 · Tag: TD-015 · Status: DONE (pending release)

## Source

> A position with NO add-ons that scales out and reboots re-seeds `last_lot_notional` from the reduced parent
> (`seed_position` uses `entry_price × remaining qty`), so its first later add-on is sized off the smaller remainder;
> memory keeps the original parent notional. Needs the original parent quantity persisted — tracked as TD-015.

— `TODO/TD-015-parent-notional-after-scaleout-reboot/DETAIL.md`, as of 2026-10-17.
Owner, 2026-10-17: "i am going to add the funding tomorrow itself, so we will ahve ample maount of funding very soon."
(→ build before the pool is funded.) Related: ISS-03 (lots keep their `notional`), ISS-04.

## Intent

The first add-on is sized `fraction_pct` % of the PARENT lot's original ₹ notional (`RiskManager._scale_in[inst]
["last_lot_notional"]`, set at the parent fill and never reduced by `reduce_position`). Both restart paths in `main.py`
rebuild it from the DB's remaining quantity, so after a pattern-top scale-out + the nightly reboot the first add-on is
half-size (live ≠ backtest). Persist the parent's original notional in `open_positions` and restore it at boot.

Must NOT change: add-on sizing logic, `reduce_position`, `seed_scale_in` (add-on lots already carry `notional`), the
backtest, the parent `entry_price` / `entry_time`. **No backfill**: existing rows get `parent_notional = 0`, which means
"unknown → today's behaviour" (only MAYURUNIQ is affected live — its one pre-existing scale-out).

## Implementation steps

1. **`trader/data/store.py`**
   - Migration list in the `open_positions` block: add `("parent_notional", "REAL DEFAULT 0")` (comment: original
     parent ₹ notional — sizes the first add-on after a scale-out + reboot, TD-015). Also add the column to the
     `CREATE TABLE IF NOT EXISTS open_positions` statement (`parent_notional REAL DEFAULT 0`) so fresh DBs have it.
   - `upsert_open_position`: write `parent_notional = entry_price * quantity` in BOTH the INSERT values and the
     `ON CONFLICT … DO UPDATE SET` clause (its only caller is a parent BUY fill — a new parent lot). Docstring: one line
     saying so.
   - `read_open_positions`: add `parent_notional` to the SELECT; return it as `float(... or 0.0)`.
   - `consume_position_lots`: do NOT touch `parent_notional`.

2. **`trader/risk/manager.py`** — new method right after `seed_position`:
   ```python
   def restore_parent_notional(self, instrument: str, notional: float) -> None:
       """Restart seeding: put back the parent lot's ORIGINAL ₹ notional (the base of the first add-on's
       geometric size). seed_position / on_order_filled rebuild it from the remaining quantity, which a
       pattern-top scale-out has shrunk (TD-015). No-op when notional <= 0 (legacy rows) or untracked."""
   ```
   Body: `state = self._scale_in.get(instrument)`; if `state is None or not notional or notional <= 0: return`;
   `state["last_lot_notional"] = float(notional)`.

3. **`main.py`** — in BOTH restore paths, immediately after the parent is seeded and BEFORE `risk.seed_scale_in(...)`:
   - paper path (~line 360, after `risk.on_order_filled(instrument, pos["entry_price"], _parent_qty, fill_ts=…)`)
   - live path (~line 434, after `risk.seed_position(instrument, _parent_qty, avg, entry_ts=_entry_ts)`)

   add `risk.restore_parent_notional(instrument, pos.get("parent_notional") or 0.0)`.
   (Order matters: `seed_scale_in` then overrides with the latest add-on lot's notional when add-ons exist — correct,
   since the next add-on sizes off the most recent lot.)

4. No other files.

## Tests required

New **`tests/test_parent_notional_restore.py`**:
- `test_upsert_stores_parent_notional` — `upsert_open_position(INST, 500.0, 100, …)` → `read_open_positions()[0]
  ["parent_notional"] == 50_000`.
- `test_scaleout_does_not_shrink_parent_notional` — after `consume_position_lots(INST, 50)` quantity is 50 and
  `parent_notional` is still 50,000.
- `test_reboot_after_scaleout_sizes_addon_like_memory` — under the scale-in config helper used in
  `tests/test_scale_in.py`: path A (no reboot) RiskManager `on_order_filled(INST, 500.0, 100)`,
  `reduce_position(INST, 50, 520.0)`; path B: Store upsert + consume 50, fresh RiskManager seeded like main.py's live
  path (`seed_position(INST, parent_qty, entry_price, entry_ts=…)`, `restore_parent_notional(INST, pos["parent_notional"])`).
  Assert `A._scale_in[INST]["last_lot_notional"] == B._scale_in[INST]["last_lot_notional"] == 50_000`.
- `test_legacy_row_keeps_old_behaviour` — `restore_parent_notional(INST, 0.0)` after `seed_position(INST, 50, 500.0)`
  leaves `last_lot_notional == 25_000`.
- `test_addon_lot_notional_still_wins` — parent seeded + `restore_parent_notional(INST, 50_000)` + `seed_scale_in(INST,
  [{"price": 480.0, "qty": 0, "notional": 24_000.0, "date": "2026-06-02T10:00:00"}])` → `last_lot_notional == 24_000`.
- `test_migration_adds_column` — create an old-schema `open_positions` table WITHOUT the column in a tmp sqlite file
  (copy the pre-change CREATE statement), insert a row, open it with `Store(...)`, then `read_open_positions()[0]
  ["parent_notional"] == 0.0`.

Whole suite green: `python -m pytest -q` (only ISS-11 may fail 09:15–15:30 IST).

## Acceptance checklist
- [ ] full pytest green (apart from ISS-11 in its window)
- [ ] new tests present and passing, incl. the migration test on an old-schema DB
- [ ] both restore paths call `restore_parent_notional` after parent seeding and before `seed_scale_in`
- [ ] `parent_notional` unchanged by `consume_position_lots`; no backfill of existing rows
- [ ] backtest untouched; no `trader.backtest` import added
- [ ] only store.py, manager.py, main.py and the new test file touched

## Completion record
- **Completed:** 2026-10-17 — implementer (general-purpose, sonnet); validated by the main session (diff vs every step; `python -m pytest -q` 557 passed).
- **Commit:** see `git log -- to_develop/completed/2026-10-17_TD-015_persist-parent-notional.md`.
- **Deviations:** none (`restore_parent_notional` sits between `seed_position` and `seed_scale_in`).
- **Notes:** no backfill — live MAYURUNIQ (scaled out before this change) keeps remainder-based sizing for its first add-on. CLAUDE.md Persistence bullet updated.
