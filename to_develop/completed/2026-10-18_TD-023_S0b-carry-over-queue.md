# Strategy S0b — carry-over entry queue in the lab portfolio simulator
Written: 2026-10-18 · Tag: TD-023 · Status: DONE

## Source

> Try all yhree options

— owner, 2026-10-18, replying to the S0 first-sims finding (`reviews/model_lab/S0_first_sims_20261018.md`): A01's
picks bunch on sell-off days, so slots overflow on crash days and sit idle on calm ones (38 % of capital idle). The
three capacity options offered: (1) fewer, bigger slots, (2) a queue that buys tomorrow if the pick still qualifies,
(3) top-K per day instead of a threshold. Options 1 and 3 already exist (`slot`, `entry_mode="topk"`); this guide adds
option 2. Tracker: `TODO/TD-023-strategy-framework-for-lab-models/DETAIL.md`.

## Intent

Candidates that pass the entry rule but find no free slot are not lost: they wait in a queue for a few bars and are
entered later if a slot frees and the price has not run away. **With `queue_bars = 0` (default) behaviour is
byte-identical to today.**

**Must NOT change:** default behaviour, anything outside `research/model_lab/portfolio.py` and
`tests/test_model_lab_portfolio.py`. Do NOT run on real data; do not touch `lab_data/`.

## Implementation steps (`research/model_lab/portfolio.py`)

1. `SimSpec` gains `queue_bars: int = 0` and `queue_max_runup: float | None = None` (fraction, e.g. 0.02).
   CLI flags `--queue-bars`, `--queue-max-runup`.
2. Queue state: `queue: dict[symbol_index, {"signal_ts", "signal_idx", "signal_close", "score", "fold"}]`.
3. At each decision time t, **before** ranking entries (step d):
   - For every queued symbol that has a bar at t (index i): drop it if `i − signal_idx > queue_bars`, or if
     `queue_max_runup` is set and `close[i] > signal_close · (1 + queue_max_runup)`, or if the symbol is now held or
     has a pending entry, or if it is excluded on t's date. Queued symbols with no bar at t are kept unchanged.
   - Surviving queued items join the candidate pool with their **original** score. If a symbol is both a current
     candidate and queued, keep only the current one (and drop the queue item).
4. Rank the joint pool by score descending, ties by symbol ascending; fill free slots as today (pending entry, fill at
   the symbol's next bar open; the trade's `signal_ts` = t, the decision time).
5. After filling: every **current** candidate at t that was eligible (not held/pending, not in the re-entry gap) but got
   no slot is put in the queue (replacing any older queue item for that symbol) with `signal_idx` = its bar index at t,
   `signal_close` = close at t. Queue items that were in the pool and not filled stay queued (not refreshed).
   Nothing is queued when `queue_bars = 0`.
6. Trades gain a column `queued_from` (the original signal timestamp for queue entries, NaT otherwise).
   `summary.json`/report: count of entries from the queue, and the spec fields.

## Tests required (`tests/test_model_lab_portfolio.py`)
- `test_queue_off_is_identical` — the existing toy portfolios give identical trades with `queue_bars=0` explicitly.
- `test_queue_enters_crowded_out_candidate_later` — 1 slot, two candidates on day 1 (A higher), A held 2 bars:
  B enters when the slot frees within `queue_bars`, with `queued_from` = day 1.
- `test_queue_expires` — slot frees after more than `queue_bars` bars → B never enters.
- `test_queue_runup_drop` — B's close rises above `signal_close·(1+runup)` before the slot frees → dropped.
- `test_queue_and_current_rank_jointly` — a queued item with a higher original score beats a current candidate with a
  lower score.

## Acceptance checklist
- [ ] full pytest green
- [ ] `queue_bars=0` byte-identical to the S0 behaviour (existing tests unchanged and passing)
- [ ] queue ages in the symbol's own bars; run-up check on close; current candidate supersedes its queue item
- [ ] `queued_from` column + queue-entry count in the summary
- [ ] Do NOT run on real data; do not touch `lab_data/`

## Completion record
- **Completed:** 2026-10-18 · trader-implementer (sonnet); validated by the main session — full suite 679 passed;
  diff read against every step; real data: `queue_bars=0` on A01 reproduces the S0 baseline trades exactly (1,934
  trades, `DataFrame.equals`).
- **Implementer choice (accepted):** queued items also respect `reentry_gap_bars`.
- **Main-session addition:** score source `coin:<seed>` (coin generated on the fly with any seed on the run's rows;
  `coin:11` equals the stored `ref:coin`) so each config can be read against a luck band of many coin draws; test
  extended in `test_score_source_ref_and_pred`.
