# Model Lab L2b — volatility reference in the magnitude verdict + volatility-scaled T5 targets
Written: 2026-10-18 · Tag: TD-021 · Status: DONE

## Source

> also, the aim is to predict whether a given candle isa potential min or not and whether the future woudl result into
> a potential change in direction and by how much.

— `TODO/TD-021-model-lab-outside-lr-extrema/DETAIL.md`, as of 2026-10-18. Context: `reviews/model_lab/L2_day_round1_20261018.md`
§ "Addendum — A08 (pain) and the volatility check on A07/A08": both magnitude PASSes (A07 potential, A08 pain) are
mostly volatility forecasts — trailing 16-bar volatility alone ranks the 20-day max rise better than A07 (ρ 0.20 vs
0.16) and the pain almost as well as A08 (0.20 vs 0.23); A08 vs pain ÷ volatility ρ −0.02. The magnitude verdict had no
volatility reference to catch it. Owner approved both fixes 2026-10-18 ("yup, makes sense"). Built on
`to_develop/completed/2026-10-18_TD-021_L2a-magnitude-models.md`.

## Intent

1. A new reference `vol` (trailing realised volatility) that every magnitude model must beat: magnitude
   **PASS = WIN vs prod AND WIN vs rsi AND WIN vs vol**.
2. New T5 target columns scaled by the stock's own trailing volatility, so a model can only score by recognising a
   better-than-usual setup for *that* stock, not a jumpy stock.

**Must NOT change:** existing target columns (values byte-identical), the detection verdict (still prod AND coin), the
classification path, the run-directory contract, anything outside `research/model_lab/` and the named tests. No
imports from `trader.strategies/features/policy/backtest` in `research/model_lab/`. Do NOT run on real data and do
not touch `lab_data/` (a background run is writing there).

## Implementation steps

1. **`references.py`**
   - New reference name `"vol"`: score = `factors.own_factors(bars)["rv_16"]` (std of 1-bar log returns over the 16
     bars ending at t — causal, known at t's close). Same value for min and max side.
   - Add `"vol"` to both `REFS_MIN` and `REFS_MAX` (so `write_refs` with default names writes it once).

2. **`score.py`**
   - `magnitude_verdict`: `need` = `["prod_pmax", "rsi_hi", "vol"]` for side max, `["prod_pmin", "rsi", "vol"]` for
     side min. Missing any → `"NO_REF"` (unchanged mechanism). Refs keep |ρ|, model keeps signed ρ.
   - `main()` default `--refs` gains `"vol"` (append at the end).
   - `_REF_MAX` needs no entry for `vol` (it maps to itself via `.get(r, r)`); confirm.
   - The detection verdict is unchanged (required refs stay prod + coin); `vol` simply appears as one more column in
     the detection/curve tables.

3. **`report.py`** — the magnitude-verdict explanation line reads
   `PASS = WIN vs production P(min)/P(max) AND WIN vs RSI AND WIN vs trailing volatility (vol = rv_16); …` (rest as
   today). Add `vol` to the decile table as a third column (realised target by decile of `vol`), same format as the
   `prod_pmin` column, with its top-minus-bottom spread on the spread line.
   - `decile_table` is already generic; in `score_run` compute it for `vol` too when `vol` is among the refs; summary
     key `deciles` gains `"vol"`.

4. **`targets.py`** — inside `build_targets`, after `_t5`, add volatility-scaled T5 columns for every `H` in `hold_h`:
   - `s_t = std(log(c[t-15..t] / c[t-16..t-1]))` — the 16-bar rolling std of 1-bar log returns ending at t (pandas
     `rolling(16).std()`, ddof=1, identical to `factors.own_factors` `rv_16`); `S_H = s_t * sqrt(H)`; `S_H` = NaN
     where `s_t` is 0 or NaN (no divide warnings — `np.errstate` + `np.where`).
   - `t5_mfez_H{H}   = t5_mfe_H{H}    / S_H`   (upside in units of the stock's usual H-bar move)
   - `t5_maepz_H{H}  = t5_maepre_H{H} / S_H`   (pain before the peak, same units; ≤ 0)
   - `t5_retz_H{H}   = t5_ret_H{H}    / S_H`
   - `t5_edgez_H{H}  = (t5_mfe_H{H} + t5_maepre_H{H}) / S_H` — reward minus pain in volatility units (the stable form
     of "reward per unit of pain": no division by a near-zero dip).
   - NaN wherever the raw column is NaN. These are new columns only; existing columns must be byte-identical.
   - `lookahead()` already matches `^t5_.*_H(\d+)$` → H; `_is_continuous` already accepts them — confirm with tests.

## Tests required

Extend `tests/test_model_lab_targets.py`, `tests/test_model_lab_score.py`:
- `test_vol_ref_equals_rv16` — `ref_scores(bars, "vol", sym)` equals `own_factors(bars)["rv_16"]` (NaN-equal);
  `"vol"` in `REFS_MIN` and `REFS_MAX`.
- `test_vol_scaled_t5_columns` — on a synthetic bar series: for H in hold_h, each z column equals raw / (rv16·√H)
  (rtol 1e-9), `edgez` = (mfe + maepre)/S_H; flat stretch (σ = 0) → NaN with no RuntimeWarning; all pre-existing
  target columns identical to a build with the new code path removed (compare against the column list/values from
  a copy of the old function, or assert the set of old columns is unchanged and spot-check values equal the raw T5
  formulas).
- `test_vol_scale_is_causal` — changing bars strictly after t+H changes no z value at t; changing bar t−20 changes
  nothing at t (σ window is 16 bars ending at t).
- `test_vol_scaled_lookahead_and_continuous` — `lookahead("t5_mfez_H20") == 20`; `_is_continuous("t5_edgez_H20")`.
- `test_magnitude_verdict_requires_vol` — hand case: model beats prod and rsi but a `vol` ref equals the target →
  FAIL; with `vol` absent from models → `NO_REF`; model beats all three → PASS. Update
  `test_magnitude_verdict_hand_case` / the continuous end-to-end test fixtures to include a `vol` ref where they
  expect PASS.

Suites that stay green: the full suite.

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] existing target columns byte-identical; new columns `t5_{mfez,maepz,retz,edgez}_H{H}` for every H
- [ ] σ is the 16-bar trailing log-return std ending at t (== factors `rv_16`), scaled by √H; NaN when σ is 0/NaN
- [ ] magnitude PASS needs prod AND rsi AND vol; missing vol → NO_REF; detection verdict unchanged
- [ ] report shows the vol decile column and the new PASS wording
- [ ] no imports from `trader.strategies/features/policy/backtest` in `research/model_lab/`
- [ ] Do NOT run on real data; do not touch `lab_data/`

## Completion record
- **Completed:** 2026-10-18 · trader-implementer (sonnet) in a separate worktree (a live A05 run imported the main
  worktree's modules); validated by the main session — full suite 662 passed; diff matches every step; real-data
  check on RELIANCE day bars: all pre-existing target columns `equals()` the old build, 12 new columns
  (`t5_{mfez,maepz,retz,edgez}_H{5,20,60}`), `t5_mfez_H20` == mfe / (rv16·√20) independently recomputed.
  Sanity: median `t5_mfez_H20` 0.69, `t5_maepz_H20` −0.25, `t5_edgez_H20` 0.40 (units of the usual 20-day move).
- **Deviations (accepted):** old-column parity is asserted by column set in the unit test (value parity covered by the
  real-data check above).
