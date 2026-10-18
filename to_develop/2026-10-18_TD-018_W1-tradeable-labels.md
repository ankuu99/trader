# W1 — Tradeable-trough labeler (`labels.type: tradeable`)
Written: 2026-10-18 · Tag: TD-018 (arms EXP-01, EXP-02) · Status: OPEN · Worktree: `../trader-2-wt/labels`, branch `exp/labels`

## Source

> […] i want uou to start multiple eorktrees to evaluatd all these and see if we gather any peformance gains […]

— `TODO/TD-018-extrema-model-campaign/DETAIL.md`, as of 2026-10-18. Arms EXP-01/EXP-02 in
`docs/01_Extrema_Model_Campaign.md`; ledger rows R-01, R-02, R-08, B-01.

## Intent

Train the primary model on the target the P&L actually rewards: a trough that reaches +profit_pct before our
non-model exits (stale tier-1, stale re-arm, stale_2, hard stop, hold timeout) fire. Today class 0 = every geometric
minimum, so the model learns "the bar fell". The new labeler keeps geometric maxima as class 1 (so P(max) and the
pattern-top exit keep their meaning), labels candidate bars whose simulated long PAYS as class 0, and the candidates
that FAIL as class 2 (neutral) — the model learns to tell a paying dip from a non-paying one.

Must NOT change: any existing labeler, the default `labels.type: extrema`, live paths, engine, config.yaml.

## Implementation steps

1. **`trader/policy/outcome.py`** — add an optional `indices` argument to `simulate_exit_outcomes(closes, params, indices=None)`:
   when given, only those bars are simulated (the other entries of the returned arrays stay `good=False`,
   `ret=NaN`, `exit=n-1`). Default `None` = all bars (current behaviour; stage_a unchanged). This is the hot path
   during training — loop only over `indices`.

2. **`trader/features/labels.py`** — new `TradeableLabeler(Labeler)`:
   - Config (nested `labels.tradeable`): `candidates: extrema | all` (default `extrema`), `stride: int` (default 5,
     only for `all`), `failed_class: neutral | drop` (default `neutral`), `fallback_geometric: bool` (default true).
   - Reads `extrema_order` and `labels.collapse_ties` exactly like `ExtremaLabeler`; exit params come from the same
     flattened `params` dict the strategy passes to `build_labeler` (keys listed in `outcome.py`).
   - `label(candles)`:
     1. `closes`; `minima, maxima = find_local_extrema(closes, extrema_order)` (+ `collapse_clusters` if collapse_ties).
     2. Candidates: `minima` (extrema) or `range(20, len(candles), stride)` (all).
     3. `good, ret, _ = simulate_exit_outcomes(closes, params, indices=candidates)`; drop candidates whose `ret` is
        NaN (unresolved inside the training window — the truncation guard; this is what keeps it leak-free).
     4. class 0 = candidates with `good`; failed candidates → class 2 (`neutral`) or dropped (`drop`).
     5. class 1 = all `maxima` (when `candidates: all`, remove any maxima index that is also a candidate to keep
        labels unique — a bar gets exactly one class).
     6. If class 0 < `MIN_SAMPLES_PER_CLASS` and `fallback_geometric`: log a warning (same style as forward_label's)
        and use the geometric minima as class 0 with no class 2 for this round. If class 1 < MIN → return `[], []`.
   - Order of returned lists: class 0, then class 1, then class 2 (deterministic).
   - `dense = False` for `extrema`, `True` for `all` (set per instance).
   Register in `build_labeler` (`ltype == "tradeable"`) and add it to the error message list. Docstring: cite this
   guide and explain the class semantics.

3. No strategy change is needed (3-class training already flows through the logistic/gbdt models: `predict_proba`
   returns P(class 0), P(class 1)). Verify `LogisticModel` and `GBDTModel` handle a 3-class fit; report if not.

## Tests required

New `tests/test_tradeable_labels.py` (build candles with a helper like `tests/test_swing_features.py::_candles`;
params via `flatten_strategy_params` of a small nested dict with `exits: {trailing: {profit_pct: 5}, stale: {check_bars: 5,
min_gain_pct: 0.5}, hold_bars: 30, hard_stop: {stop_pct: 20}}`, `extrema_order: 2`):
1. `test_paying_minimum_is_class0` — a V that rallies +6 % within 5 bars → that minimum is class 0.
2. `test_failing_minimum_is_neutral` — a minimum followed by a flat drift (stale fires) → class 2.
3. `test_failed_drop_mode` — `failed_class: drop` → the failing minimum is absent.
4. `test_unresolved_tail_dropped` — a minimum in the last bars of the window (outcome unresolved) is not labelled.
5. `test_maxima_class1_unchanged` — class-1 indices equal `ExtremaLabeler`'s maxima on the same candles.
6. `test_all_candidates_stride` — `candidates: all, stride: 3` → class-0/2 indices are a subset of range(20, n, 3); no index has two classes.
7. `test_fallback_geometric` — no paying minimum at all → class 0 = geometric minima, no class 2, warning logged.
8. `test_outcome_indices_subset` — `simulate_exit_outcomes(..., indices=[i])` equals the full run at bar i.
9. `test_strategy_trains_with_tradeable` — an `LRExtremaStrategy` with `labels: {type: tradeable}` trains on a
   synthetic oscillating series and `score_current()` returns two floats.

Whole suite green; parity golden unchanged.

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] 9 new tests pass
- [ ] default labeler behaviour unchanged (golden untouched)
- [ ] no edits outside `trader/policy/outcome.py`, `trader/features/labels.py`, the new test file
- [ ] training-time cost: report the wall time of test 9 and of one `label()` call on 1,200 candles (candidates: all, stride 5)

## Completion record
