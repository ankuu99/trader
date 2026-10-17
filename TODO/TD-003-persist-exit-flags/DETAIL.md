# TD-003: Persist trailing_active / pattern_top_trailing / partial_taken / breakeven_active

Source: `todo.md`, as of 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

- ~~**Persist `trailing_active` across restarts**~~ — DONE 2026-10-14 (live evidence:
  MAYURUNIQ scaled out 10-12, restart dropped the 4% remainder trail — 10-13 low 770.45
  under the ~779.5 trail, no exit — then sold half AGAIN on 10-14 15:15).
  `open_positions` now carries `trailing_active`, `pattern_top_trailing`,
  `partial_taken`, `breakeven_active` (written per decision candle AND at the
  scale-out fill via `store.save_exit_flags`, since a CAS 15:15 bar is persist-only);
  both restore paths pass them to `seed_position_state(..., exit_flags)`. Migration
  backfills `partial_taken=1` where `pattern_top_trailing=1`.
  `tests/test_exit_flag_restore.py`. Original note: `peak_close` and `max_gain_pct`
  survive a restart, but `trailing_active` does not: `seed_position_state()` takes
  only those two, so `PositionState.trailing_active` comes back `False`. It re-arms
  on the first tick where `pct >= profit_pct` (`trader/policy/extrema_exit.py:320`),
  so the common case self-heals. **The gap:** a position that armed trailing at an
  earlier peak and has since pulled back *below* its `profit_pct` floor — while still
  above the trail level `peak × (1 - trail_pct/100)` — silently disarms on restart.
  Downside protection is lost until price re-crosses the floor, which it may never do.
  Widest for stocks with a high floor and loose trail (CHENNPETRO: `profit_pct: 10`,
  `trail_pct: 4` → a ~6pp dead band). `pattern_top_trailing` positions are worse off:
  they arm trailing from the pattern-top branch regardless of `profit_pct`
  (`extrema_exit.py:268`, `:293`), so nothing re-arms them at all after a restart.
  `partial_taken` has a sharper failure mode than a lost trail: it guards the
  pattern-top scale-out to once per position (`extrema_exit.py:266`), so a restart
  re-arms it and a second scale-out can fire on the same position.
  Fix: persist `trailing_active`, `pattern_top_trailing`, `partial_taken` and
  `breakeven_active` the same way as `peak_close` (`main.py:608`), and widen
  `seed_position_state()` (`lr_extrema.py:405`) to restore them. The
  `open_positions` table already has a `trailing_active` column, but it is UI-only —
  nothing reads it back into strategy state.
