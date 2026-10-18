# Strategy S0c — combined ranking of several scores with a per-pick hold
Written: 2026-10-18 · Tag: TD-023 · Status: DONE

## Source

> Do all three

— owner, 2026-10-18, approving (1) combining the two models: "rank by both, then hold A01's picks about 20 days and
production's about 60" (from `reviews/model_lab/SC2_hold_20261018.md`: A01's edge is a ~20-day bounce, production
P(min) is best held 40–60 days). Pre-registered as SC4 in `reviews/model_lab/STRATEGY_LEDGER.md`. Tracker:
`TODO/TD-023-strategy-framework-for-lab-models/DETAIL.md`.

## Intent

Let one simulated sleeve rank candidates from several score sources at once. Scores live on different scales, so
each is converted to a **causal percentile** (vs its own recent history) before pooling; each pick remembers which
source chose it and is held for that source's hold length. **With `sources = ()` (default) behaviour is
byte-identical to today.**

**Must NOT change:** default behaviour; anything outside `research/model_lab/portfolio.py` and
`tests/test_model_lab_portfolio.py`. Do NOT run on real data; do not touch `lab_data/`.

## Implementation steps (`research/model_lab/portfolio.py`)

1. `SimSpec` gains `sources: tuple = ()` — a tuple of `(score_source, hold_bars)` pairs, e.g.
   `(("run", 20), ("ref:prod_pmin", 60))`. When non-empty it replaces `score_source` and the time stop:
   `hold_bars` stays required but is ignored for positions (keep it in the spec for the report).
2. Loading: for every source, load the per-symbol score arrays exactly as `_load_symbol` does for that
   `score_source` (same rows: the run's scored rows; a `ref:` NaN row is NaN for that source only). Symbols are kept
   if at least one source has a finite score; a symbol missing a `ref:` file is simply NaN for that source.
3. **Causal percentile per source** — new pure helper
   `causal_percentiles(dates, scores, window) -> np.ndarray` (same shape as `scores`): for a row on calendar date D,
   `pct = (# scores of THIS source on the previous `window` distinct dates strictly before D that are ≤ the row's
   score) / (# such scores)`; NaN when the score is NaN or fewer than `window` prior dates exist (warm-up). Same date
   pool definition as `causal_thresholds` (`window = spec.window_sessions`). Excluded rows are NaN before pooling,
   as today.
4. **Combine**: per row, `combined = max over sources of pct`; the winning source is the one with the highest pct;
   ties → the source listed first. Keep the winning source's raw score as `raw` (for tie-breaking).
5. Entry selection runs on `combined` exactly as today: `rate` mode → candidate when `combined ≥ 1 − rate`;
   `topk` mode → the K best rows by `combined`. **Ranking key: combined descending, then the winning source's raw
   score descending, then symbol ascending.** (With one source, ranking within a date then equals today's raw-score
   ranking in `topk` mode.)
6. Every pending entry and position stores `hold` = the winning source's `hold_bars` and `source` = its
   `score_source` string; the time stop uses the position's own `hold`. The carry-over queue (if on) keeps the
   source and hold of the original pick.
7. Trades gain a column `source` (the winning `score_source`, or the spec's `score_source` when `sources` is empty).
   Summary/report: trades and net ₹ per source.

## Tests required (`tests/test_model_lab_portfolio.py`)
- `test_sources_empty_is_identical` — existing toy portfolios unchanged with `sources=()`.
- `test_single_source_topk_equals_plain` — `sources=(("run", H),)` with `entry_mode="topk"` gives the same trades
  (symbol, entry/exit times and prices) as `score_source="run", hold_bars=H`.
- `test_causal_percentiles` — hand case: values, warm-up NaN, changing scores on/after D leaves D's percentiles
  unchanged.
- `test_per_pick_hold_and_source` — two sources with different holds on a toy: a pick won by source B is held
  `hold_B` bars and its `source` column says B; ties between sources go to the first listed.
- `test_source_missing_ref_is_nan_for_that_source_only` — a symbol with no ref file still trades via the other source.

## Acceptance checklist
- [ ] full pytest green
- [ ] `sources=()` byte-identical; single-source topk equals the plain run
- [ ] percentiles strictly causal (previous `window_sessions` dates of the same source)
- [ ] per-position hold from the winning source; `source` column; per-source summary
- [ ] Do NOT run on real data; do not touch `lab_data/`

## Completion record
- **Completed:** 2026-10-18 · trader-implementer (sonnet) in a separate worktree; validated by the main session —
  full suite 684 passed; diff read against every step; real-data use in SC4 (pooled A01 + production: per-source
  trades 598 / 762, holds 20 / 60 applied).
- **Implementer choices (accepted):** percentile warm-up counts dates with finite scores of that source (a
  single-source run therefore enters nothing in its first `window` dates — the equality test NaNs those dates on
  the plain side); equity start = first date with any finite raw source score; `source` column on every trades
  frame; no CLI flag for `sources` (Python API only).
