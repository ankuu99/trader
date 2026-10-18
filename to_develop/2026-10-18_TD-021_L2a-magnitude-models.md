# Model Lab L2a — magnitude models (regression + quantiles), magnitude verdict, after-pick by year
Written: 2026-10-18 · Tag: TD-021 · Status: OPEN

## Source

> also, the aim is to predict whether a given candle isa potential min or not and whether the future woudl result into
> a potential change in direction and by how much.
>
> predict forward need not be just oe candle at a time, after all that also woudl determine the hold period, potential.

— `TODO/TD-021-model-lab-outside-lr-extrema/DETAIL.md`, as of 2026-10-18. Context: day round 1
(`reviews/model_lab/L2_day_round1_20261018.md`) — models that find lows MORE precisely picked SMALLER moves; the only
arm that won on both (A01) was trained on deep swing lows. The owner approved (2026-10-18) the next step: train models
to predict **how big the move is, the hold time and the pain**, not only "is this a low". Built on L0/L1
(`to_develop/completed/2026-10-18_TD-021_L*.md`).

## Intent

1. Regression and quantile models in the lab (same `LabModel` contract), so a run can target T3/T4/T5 continuous
   columns (e.g. `t5_ret_H20`, `t5_mfe_H20`, `t5_maepre_H20`, `t5_ttm_H20`, `t3_ret_k5`).
2. Runner support for continuous targets (uniform sampling, `pred_*` columns).
3. Scorer: a **magnitude verdict** (does the model rank future move size better than production P(min) and the
   references, fold by fold and year by year), a decile table, and an **after-pick-by-year** table for every run (the
   ad-hoc check done for A01 becomes standard; informational).
4. Fix `t3_sig` divide-by-zero.

**Must NOT change:** the binary-classification path's behaviour (existing runs re-scored must give identical detection
verdicts), the run-directory contract (only adds optional `pred_*` columns, already allowed), anything outside
`research/model_lab/` and the named tests. No imports from `trader.strategies/features/policy/backtest` in
`research/model_lab/`.

## Implementation steps

1. **`targets.py`** — in T3, `t3_sig_k{k}` = NaN where σ_t is 0 or NaN (use `np.errstate` + `np.where`); no other change.

2. **`models.py`** — add a class attribute `task: str` (`"classify"` on the two existing models) and three regressors
   (`task = "regress"`):
   - `PooledRidge` (`"ridge"`): fit-time median imputation + `StandardScaler` + `Ridge(alpha=params.get("alpha", 1.0))`.
   - `PooledHGBReg` (`"hgb_reg"`): `HistGradientBoostingRegressor(max_depth=params.get("max_depth", 3),
     learning_rate=0.05, max_iter=params.get("max_iter", 300), early_stopping=False, random_state=seed)`.
   - `PooledHGBQuantile` (`"hgb_q"`): one `HistGradientBoostingRegressor(loss="quantile", quantile=q, …same params)`
     per q in `params.get("quantiles", [0.1, 0.5, 0.9])`; `predict` returns the q = 0.5 model (or the middle quantile
     when 0.5 is absent); new optional method `predict_multi(X) -> dict[str, np.ndarray]` with keys `q10`, `q50`, `q90`
     (`f"q{round(q*100):02d}"`).
   - Regressors: before fitting, **winsorise y** to the [0.5, 99.5] percentiles of the training y (bounds stored on the
     instance; prediction unaffected). Raise `ValueError("degenerate training set")` when fewer than 100 rows or
     y is constant. Sample weights passed through (`sample_weight`).
   - Register all three in `MODELS`.

3. **`runner.py`**
   - Task from `MODELS[spec.model].task`. `classify` keeps today's binary check and positive-preserving sampling.
     `regress`: target must be numeric with ≥ 2 distinct non-NaN values (else `ValueError`); sampling is uniform
     random over eligible rows up to the per-symbol cap (seeded as today); meta records `task`.
   - Pass B: when the fitted model is a regressor, also write `pred_<target>` = the score; when it has
     `predict_multi`, write `pred_<target>_<key>` for each key (float32).
   - `meta.json` gains `"task"`.

4. **`score.py`**
   - `_is_continuous(target)`: True for targets starting `t3_`, `t4_`, `t5_` except `t5_hit_*` and `*_endbars_*`.
   - **Magnitude verdict** (computed only when the run target is continuous; stored in the summary as
     `magnitude`): for each fold and each calendar year with ≥ 200 evaluated rows where the realised run target is
     defined: ρ_model = Spearman(model score, realised target) and, for each ref, ρ_ref = |Spearman(ref score, realised
     target)| (absolute: a reference may rank in either direction — this makes the comparison harder for the model).
     `fold_win_share`/`year_win_share` = share of groups with ρ_model > ρ_ref; **WIN = both ≥ 2/3**; magnitude
     **PASS = WIN vs `prod_pmin` AND WIN vs `rsi`** (coin is trivially beaten; RSI had the largest after-pick moves in
     round 1, so it is the harder reference). Also report pooled ρ per model.
     For continuous runs the headline verdict becomes the magnitude verdict; the detection verdict is still computed
     (with the model score as the ranking) and reported below it.
   - **Decile table** (continuous runs): pool all evaluated rows; bin by deciles of the model score; per decile the
     mean and median realised target, and the same table binning by `prod_pmin`. Report the top-minus-bottom decile
     spread for each.
   - **After-pick by year** (every run, informational): picks exactly as in the after-pick profile at rate 0.01; per
     calendar year mean and median of `t5_ret_H{H} − COST` and pick count for the model and `prod_pmin` (and the
     mirrored ref for max side); `years_model_mean_gt_prod`, `years_model_median_gt_prod`; the same pooled numbers
     excluding QA-flagged symbols (symbols with `n_jumps_30 > 0` in `paths.LAB_ROOT / f"qa_{SOURCE interval}.csv"`, where
     the interval is `bars.SOURCE[tf]`; skip the line if the file is missing) and excluding the calendar year 2020.
   - All new tables go to `score_summary.json` (keys `magnitude`, `deciles`, `afterpick_by_year`).

5. **`report.py`** — new sections: "Magnitude verdict" (headline for continuous runs: fold/year win shares per ref,
   pooled ρ, PASS/FAIL), "Deciles", "After-pick by year (informational — not a pass condition)" with the
   years-won counts and the ex-QA / ex-2020 lines.

## Tests required

Extend `tests/test_model_lab_runner.py` / `tests/test_model_lab_score.py`, new `tests/test_model_lab_models.py`:
- `test_regressors_fit_predict_and_winsorise` — ridge / hgb_reg / hgb_q on synthetic X with y = 2·x0 + noise + a few
  1e6 outliers: predictions finite, rank-correlate with x0 (> 0.8), outliers clipped (stored bounds); hgb_q
  `predict_multi` keys q10/q50/q90 with q10 ≤ q50 ≤ q90 on ≥ 95 % of rows; degenerate y raises.
- `test_runner_regression_end_to_end` — `SynthSource(plant=...)` extended (or a test subclass) so a factor predicts a
  continuous target (e.g. `t4_ret_h4`): run with `hgb_q` → `scores/` has `score`, `pred_t4_ret_h4`,
  `pred_t4_ret_h4_q10/q50/q90`; meta `task == "regress"`; Spearman(score, target) on scored rows > 0.3.
- `test_classification_path_unchanged` — the existing synthetic classification run gives identical scores before/after
  (fixed seed; compare to a stored small array or to a second run with the same seed).
- `test_magnitude_verdict_hand_case` — fake run dir where the model score = realised target + small noise and a ref =
  random: WIN vs the ref, PASS when the refs listed are that ref plus fake `prod_pmin`/`rsi` that are random; a ref that
  is −target (perfect inverse) is NOT beaten (absolute ρ).
- `test_deciles_monotone_for_perfect_score` — decile means strictly increasing for score = target.
- `test_afterpick_by_year_counts` — hand data across 3 years: years-won counts and the ex-2020 line computed as
  specified; QA file absent → line skipped without error.
- `test_t3_sig_zero_sigma_is_nan` — flat price stretch → `t3_sig_*` NaN, no RuntimeWarning (use
  `pytest.warns`-free `warnings.catch_warnings(record=True)` assertion).

Suites that stay green: the full suite.

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] classification runs unchanged (re-scoring an existing run gives the same detection verdicts)
- [ ] regressors winsorise y on training data only; quantile model exposes q10/q50/q90
- [ ] magnitude verdict uses |ρ| for refs, signed ρ for the model; PASS needs prod_pmin AND rsi
- [ ] after-pick-by-year present for every run, labelled informational, with ex-QA and ex-2020 lines
- [ ] no imports from `trader.strategies/features/policy/backtest` in `research/model_lab/`
- [ ] Do NOT run on real data; do not touch `lab_data/` (a background download writes there)

## Completion record
