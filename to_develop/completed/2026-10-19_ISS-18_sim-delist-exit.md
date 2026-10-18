# ISS-18 — DELIST exit in the portfolio simulator
Written: 2026-10-19 · Tag: ISS-18 · Status: DONE 2026-10-19

## Source

> Exits are evaluated only on bars of the held symbol. When a symbol's data ends (delisting, merger, suspension), a
> position in it stays open until the end of the whole simulation, then closes at the symbol's last close ("END"),
> holding one of the 15 slots for years. Pending entries on such a symbol would never fill either.

— `ISSUES/ISS-18-sim-slot-locked-after-delisting/DETAIL.md`, 2026-10-19. Documented bug, pre-approved.

## Intent
`SimSpec` gains `delist_grace_days: int | None = 7`. In `simulate`, at each global timestamp `t` (before step "c.
exits"), for every open position whose symbol's LAST bar timestamp `last_ts` satisfies `t > last_ts + delist_grace_days`
(calendar days): close it at the symbol's last close (`d["c"][-1]`), exit time `t`, bar index = last index, reason
`"DELIST"`, costs as usual (the existing `close()` handles MIS/CNC by date — use the symbol's last bar timestamp as the
exit date for the cost rule, i.e. call `close(si, d["c"][-1], d["ts"][-1], len-1, "DELIST")` so held_bars and the
trade's `exit_ts` reflect the last real bar). Also drop any `pend_in` / `pend_out` / `queue` entry for such a symbol.
`None` disables the rule (old behaviour). Equity/utilisation then see the slot free from that date.

**Must NOT change:** anything outside `research/model_lab/portfolio.py` and `tests/test_model_lab_portfolio.py`;
results of any sim where every symbol's data runs to the global end (all existing `day` sims).

## Tests (extend `tests/test_model_lab_portfolio.py`)
- `test_delist_exit_frees_slot`: two symbols; A's bars stop mid-way while held (hold 50 bars) → A closed with reason
  DELIST at its last close, exit_ts = A's last bar; after `last_ts + grace` the freed slot lets B be entered (n slots = 1,
  B's score high only after A's data ends).
- `test_delist_pending_entry_dropped`: a signal on the last bar of a symbol → pending entry dropped, no trade, slot free.
- `test_delist_none_keeps_old_behaviour`: `delist_grace_days=None` → reason END at the global end as before.
- Existing tests unchanged and green.

## Acceptance checklist
- [ ] full pytest green · [ ] DELIST rule as specified · [ ] None = old behaviour · [ ] no other file changed

## Completion record
Validated 2026-10-19 (main session): diff matches the guide; full pytest **706 passed** on the merged branch; commit 7c9b45c. Implementer placed the rule at the top of the per-timestamp loop (before steps a/b) — equivalent, accepted. Real data: SN-1..3 re-run on dayn with the rule (see STRATEGY_LEDGER SN).
