# TD-004: EXIT-rejection restore covers clocks + trail state

Source: `todo.md`, as of 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

- ~~**EXIT-rejection restore is PARTIAL — clocks and trail state are lost**~~ —
  **FIXED 2026-08-18** (uncommitted). `PositionState.snapshot_and_reset()` captures
  every position-tracking field at FULL-exit emission (survives `reset()` like
  `fill_price`); all 8 full-exit call sites in `trader/policy/extrema_exit.py` use
  it; the REJECTED/CANCELLED+EXIT branch in `lr_extrema.on_order_update` restores
  the whole snapshot (one-shot; falls back to the old entry-price-only restore when
  no snapshot exists, e.g. restart between emission and rejection). COMPLETE exit
  fills and new ENTRY fills discard the snapshot. Happy path proven byte-identical
  (pipeline snapshot before/after diff — see golden note below). Tests:
  `tests/test_exit_reject_restore.py` (7). Original live evidence: TVSMOTOR
  2026-08-17 — hold-bars(200) exit fired on the 15:15 candle → order at 15:30:01 →
  Zerodha CAS rejection → `held_bars` 200→0 → timeout exit slipped ~8 sessions.
