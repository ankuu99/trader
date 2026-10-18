# W5 — No-ML baselines: rules pipeline + passthrough model + OU s-score add-on
Written: 2026-10-18 · Tag: TD-018 (arms EXP-09, EXP-10) · Status: OPEN · Worktree: `../trader-2-wt/rules`, branch `exp/rules`

## Source

> […] i want uou to start multiple eorktrees to evaluatd all these and see if we gather any peformance gains […]

— `TODO/TD-018-extrema-model-campaign/DETAIL.md`, as of 2026-10-18. Arms EXP-09/EXP-10 in
`docs/01_Extrema_Model_Campaign.md`; ledger B-08 (rules baseline on `origin/simple_trader`), the ATHER review's
"lowest-of-20 + up-close" rule, Avellaneda & Lee (2010) OU s-score.

## Intent

Answer "does the ML add anything?" with deterministic rules that plug into the SAME strategy/exit stack:
a `features.type: rules` pipeline emits `[entry_score, top_score]` in [0, 1] and a `model.type: passthrough` model
returns them as `(p_min, p_max)`. Thresholds, veto, pattern-top, exits and risk all stay unchanged. Plus an `ou`
feature add-on so the ML model can also use the s-score (EXP-10 has both a rule and a feature variant).

Must NOT change: existing pipelines/models, default config behaviour, live paths, engine, config.yaml.

## Implementation steps

1. **`trader/features/ou.py`** — pure helper:
   ```python
   def ou_score(closes, window: int) -> tuple[float, float]:
       """(s_score, half_life_bars) from an AR(1) fit on log closes over the last window+1 bars:
       x_t = a + b·x_{t-1} + e. If 0 < b < 1: m = a/(1-b), sigma_eq = sqrt(var(e)/(1-b^2)),
       s = (x_last - m)/sigma_eq, half_life = -ln 2 / ln b. Otherwise (no mean reversion) → (0.0, inf).
       s is clipped to [-5, 5]. Needs len(closes) >= window + 1 else (0.0, inf)."""
   ```
   Use `numpy.polyfit` or closed-form OLS; `var(e)` with ddof=2.

2. **`trader/features/addon_ou.py` — `ou` add-on** (follow the registration convention in
   `to_develop/2026-10-18_TD-018_W2-feature-addons.md`: own module, `ADDONS["ou"] = Cls` at import, one import line in
   `trader/features/registry.py` right after the `from trader.features.addons import ...` line).
   Config: `window` (60). Names: `ou_s`, `ou_hl_norm` = `min(half_life / window, 2.0)` (2.0 when inf).
   `min_history = window + 1`.

3. **`trader/features/rules_features.py` — `RulesFeaturePipeline`**, registered as `rules` in `_REGISTRY`
   (`trader/features/registry.py`). Config (nested `features.rules`): `kind: rsi_bounce_ema | lowest_turn | ou`.
   `feature_names = ["entry_score", "top_score"]`. `compute(candles)` on closes:
   - `rsi_bounce_ema` (params `rsi_period` 14, `rsi_max` 35, `rsi_min_top` 70, `ema_period` 50):
     entry = 1.0 if RSI < rsi_max and close > prev_close and close > EMA else 0.0;
     top = 1.0 if RSI > rsi_min_top and close < prev_close else 0.0. RSI via `indicators.rsi_series`, EMA via `ema_series`.
   - `lowest_turn` (param `lowest_of` 20): entry = 1.0 if prev_close == min(closes[-lowest_of-1:-1]) and close > prev_close;
     top = 1.0 if prev_close == max(closes[-lowest_of-1:-1]) and close < prev_close.
   - `ou` (param `window` 60): `s, _ = ou_score(closes, window)`; entry = clip(-s / 3, 0, 1); top = clip(s / 3, 0, 1).
   `min_history` = what the kind needs (+1). Unknown kind → `ValueError`.

4. **`trader/models/passthrough.py` — `PassthroughModel(ExtremaModel)`**, registered as `passthrough` in
   `trader/models/registry.py`. `fit()` ignores the data and marks trained; `predict_proba(x) = (float(x[0]), float(x[1]))`;
   `feature_contributions` returns None. Docstring: only meaningful with `features.type: rules`.
   (The strategy still runs its labeler + retrain cadence; the fit is a no-op — acceptable.)

## Tests required

New `tests/test_rules_baselines.py`:
1. `test_ou_score_reverting` — a noisy sine around 100 (fixed seed): b in (0, 1), finite half-life; the s-score is
   strongly negative at a trough and positive at a crest.
2. `test_ou_score_random_walk_guard` — a pure trend (b ≥ 1) → (0.0, inf).
3. `test_ou_addon` — names, min_history, finite values; inf half-life → `ou_hl_norm == 2.0`.
4. `test_rules_rsi_bounce_ema` — hand-built series where every condition holds on the last bar → entry 1, top 0; flip one condition → entry 0.
5. `test_rules_lowest_turn` — prev bar is the 20-bar low and the last bar closes up → entry 1; otherwise 0.
6. `test_rules_ou_graded` — entry/top in [0, 1] and entry > 0 at a trough of the sine.
7. `test_passthrough_model` — untrained → `is_trained` False; after `fit` → True; `predict_proba([0.3, 0.8]) == (0.3, 0.8)`.
8. `test_strategy_with_rules` — `LRExtremaStrategy` with `features: {type: rules, rules: {kind: lowest_turn}}`,
   `model: {type: passthrough}`, threshold 0.99 on a synthetic oscillating series emits at least one ENTRY signal.
9. `test_unknown_kind_raises`.

Whole suite green; parity golden unchanged.

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] 9 new tests pass
- [ ] default pipelines/models unchanged (golden untouched)
- [ ] only the new modules, the two registry edits, one import line, and the test file changed

## Completion record
