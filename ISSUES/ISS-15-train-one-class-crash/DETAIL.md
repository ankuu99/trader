# ISS-15: LRExtrema `_train` can fit a one-class sample set and crash the solver

Source: TD-018 detection campaign, 2026-10-18. Dated addenda below. Never delete.

---

`_train()` guards only on the TOTAL sample count (`len(rows) < MIN_SAMPLES_PER_CLASS * 2`), after dropping labelled
indices whose feature vector is `None` (not enough history). A feature pipeline with a long `min_history` can drop
every sample of one class early in a run, leaving ≥ 2×MIN rows that are all class 0 (or all 1). `LogisticRegression.fit`
then raises `ValueError: This solver needs samples of at least 2 classes`, which kills the whole backtest.

Observed: Stage B of EXP-06 (`addon_atr_dist`) and EXP-08 (`addon_sr`) on `exp/features`, FULL/HORIZON windows
(`lab_data/campaign/logs/stage_b_exp06.log`, first attempt). Half-year windows completed.

HEAD: latent — the production `extrema` pipeline has a short `min_history`, so no run has hit it (a hit would crash,
so no existing result depends on the behaviour). Any future long-history feature (regime horizons 1600, S/R
lookbacks) can trigger it live: an exception inside `on_candle` during warm-up or retrain.

Minimal fix (applied on `exp/features`, behaviour-identical for every run that did not crash):

```python
if len(set(labels)) < 2:
    return
```

right after the total-count guard. The validation-split path (`lr_extrema.py:558`) already checks per class.
