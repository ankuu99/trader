# Shape-Learning Feature Plan — LRExtremaStrategy

## Motivation

Today the model is a **logistic regression over 6 scalars**
(`volume_ratio, norm_price, slope3, slope5, slope10, slope20` — see
`trader/features/extrema_features.py`). The four slope features are *lossy
linear summaries* of the trailing window: they capture average direction and
magnitude but throw away **morphology** — curvature, where the turn happened,
multi-segment structure. As a result the model cannot distinguish a true
V-bottom from a falling knife when their slope-summaries coincide. This is the
mechanical root of the documented "falling knife" failure mode.

These five plans progressively add *shape* information, from cheapest
(curvature scalar) to a true sequence model. **Test them one by one**, each
backtested against the current 6-scalar baseline.

---

## Interdependency summary (read this first)

| # | Plan | Touches | Depends on | Redundant with |
|---|------|---------|------------|----------------|
| 1 | Curvature features | `ExtremaFeaturePipeline` only | none | — |
| 2 | Segmented slopes | `ExtremaFeaturePipeline` only | none | partial overlap w/ 1 |
| 3 | Raw trajectory | `ExtremaFeaturePipeline` + model regularization | none | — |
| 4 | Shapelets / DTW | `ExtremaFeaturePipeline` (+ exemplar build step) | none | — |
| 5 | Sequence model | **new model + new window pipeline** | model registry | makes 1–4 largely moot |

**Are 1–4 independent? Yes — fully.** All four are *additive, opt-in feature
columns* appended to the base vector, consumed unchanged by the existing
`LogisticModel`. Each is gated by its own config flag (mirroring the existing
`depth:` / `macd:` opt-in pattern). There is **no ordering dependency** and no
functional coupling — you can implement, enable, disable, or combine any subset.
Implementing #1 teaches the exact plumbing pattern for #2–#4.

**Is #5 independent? Orthogonal, not additive.** It changes the *model contract*
(currently `vector -> (p_min, p_max)`); a sequence model consumes the raw
**window**, not a fixed scalar vector. It does not depend on #1–#4, and it
largely **subsumes** them (the network learns shape directly from the window).
#5 can in principle be combined with #1–#4 as auxiliary scalar inputs (a hybrid),
but that is an advanced variant, not a prerequisite.

### Cross-cutting constraints (apply to ALL five)

1. **Parity golden test** (`tests/test_parity_golden.py`): the base 6-feature
   vector must stay byte-identical when new flags are OFF. Every addition is
   **off by default**. Run this test after each change.
2. **`min_history` / warmup interplay**: each plan raises the minimum candles
   `compute()` needs. Update `ExtremaFeaturePipeline.min_history` and ensure
   `warmup_bars` (default 200) comfortably exceeds it.
3. **`feature_names` must stay aligned** with the column order in `compute()` —
   it's the introspectable contract (used by UI/debug). Append new names in the
   same conditional order as the columns.
4. **Scaling/regularization**: `LogisticModel` owns its own scaling. Low-dim
   additions (#1, #2) are fine as-is; high-dim additions (#3, #4) likely need L2
   regularization in the model to avoid overfitting per-stock data.
5. **Calibration unchanged**: new params should be exposed to
   `scripts/calibrate.py` if you want to tune them.

---

## Plan 1 — Curvature features (cheapest, highest signal-per-effort)

### Idea
A linear slope cannot tell a V (concave-up reversal) from a straight decline.
Fit a **quadratic** `y = a·x² + b·x + c` over the trailing window of % returns
(or normalized closes) and use the 2nd-order coefficient `a` as the feature.
`a > 0` ⇒ concave-up ⇒ decline decelerating / turning (real bottom signature);
`a < 0` ⇒ accelerating decline (falling knife). This directly attacks the
knife problem with **one or two scalars**.

### Changes
- **File:** `trader/features/extrema_features.py`
- Add helper in `trader/features/indicators.py`:
  `quadratic_curvature(values: list[float]) -> float` — least-squares quadratic
  fit, return coefficient `a` (use `np.polyfit(x, y, 2)[0]`). Add a unit test.
- In `ExtremaFeaturePipeline.__init__`, read nested config:
  ```yaml
  features:
    curvature:
      enabled: false        # default OFF for parity
      windows: [10, 20]     # compute curvature over these return-windows
  ```
- In `compute()`, after the slope block, if enabled append one curvature value
  per window (computed over the same `returns` array used for slopes — note
  `returns` currently holds the last 20 returns; for window>20 you must widen
  the returns computation, see min_history below).
- Update `feature_names` (e.g. `curv10`, `curv20`) and `min_history`
  (`max(21, max(windows)+1)`).

### Test
```bash
python -m pytest tests/test_parity_golden.py        # base vector unchanged (flag off)
python -m pytest tests/ -k curvature                # new helper
# enable curvature in config, then:
python scripts/backtest.py --from 2024-06-01 --to 2025-12-31
```
Compare `total_pnl`, `return_pct`, `win_rate`, `max_drawdown_pct` to baseline.

### Expected effect / risk
- **Upside:** fewer falling-knife entries (negative curvature should suppress
  P(local-min) once the model weights it).
- **Risk:** quadratic fit is sensitive to the single most recent point; noisy on
  short windows. Prefer windows ≥ 10. Low overfitting risk (1–2 features).

---

## Plan 2 — Segmented slopes (kink detection)

### Idea
A real bottom is a **kink**: negative slope then positive slope. A single slope
over the whole window erases this. Split the trailing window in half and emit
`slope_first_half` and `slope_second_half` (and optionally their difference).
The model can then learn "down then up" directly.

### Changes
- **File:** `trader/features/extrema_features.py` (reuses existing
  `linreg_slope` — no new indicator needed).
- Config:
  ```yaml
  features:
    segmented_slope:
      enabled: false
      window: 20            # split into 2 halves of 10
      include_delta: true   # also emit (second_half - first_half)
  ```
- In `compute()`, if enabled: take the last `window` returns, split, append
  `linreg_slope(first)`, `linreg_slope(second)`, optionally the delta.
- Update `feature_names` (`slope_h1`, `slope_h2`, `slope_kink`) and
  `min_history` (`max(21, window+1)`).

### Test
Same harness as Plan 1. Parity test must pass with flag off.

### Expected effect / risk / overlap
- **Overlap with Plan 1:** both encode "the decline is turning." Curvature is
  smoother; segmented slopes are sharper/more interpretable. **Test separately
  first**, then optionally together — they are not mutually exclusive but may be
  partially redundant. If both help individually, A/B the combination.
- **Risk:** low. 2–3 extra linear features.

---

## Plan 3 — Raw trajectory features (model sees the path)

### Idea
Stop summarizing. Feed the **normalized last-N closes** as N features so the
linear model sees the actual path. Normalize per-window (z-score or
min-max over the window) to stay scale-invariant across stocks.

### Changes
- **File:** `trader/features/extrema_features.py`
- Config:
  ```yaml
  features:
    trajectory:
      enabled: false
      length: 15           # number of trailing closes to emit
      norm: zscore         # zscore | minmax
  ```
- In `compute()`, if enabled: take last `length` closes, normalize
  (`(x-mean)/std` or `(x-min)/(max-min)`), append all `length` values.
- `feature_names`: `traj0..traj{length-1}`. `min_history = max(21, length)`.

### Model dependency (the one soft coupling)
Adding 15 features to a logistic regression on per-stock data **will overfit**
without regularization. Before enabling, ensure `LogisticModel` uses L2
(`C` / `penalty='l2'`) — expose it via the `model:` config block if not already.
This is the only plan that benefits from a model-side change.

### Test
Same harness, but **watch for overfitting**: compare in-sample vs
walk-forward (`scripts/backtest_rolling.py`) — a big in-sample gain with poor
rolling performance means overfit.

### Expected effect / risk
- **Upside:** genuine path awareness; can learn template-like bottoms.
- **Risk:** high dimensionality vs small per-stock training sets. Mitigate with
  regularization and a modest `length` (10–15).

---

## Plan 4 — Shapelets / DTW template matching

### Idea
Define a small library of **exemplar bottom shapes** (hand-picked, or mined from
historically profitable entries). Feature = distance (DTW or Euclidean on
normalized windows) from the current window to each exemplar. "Shape
recognition" in the classic sense, still no deep learning.

### Changes
- **New file:** `trader/features/shapelets.py` — exemplar storage + distance
  function (`dtw_distance` or simple normalized-Euclidean to start; DTW is more
  robust to time-warping but heavier).
- **Exemplar build step (one-time, offline):** a script that scans historical
  candles, finds geometric minima that *did* bounce (reuse `forward_label`
  logic in `trader/features/labels.py`), extracts their normalized windows, and
  clusters them (k-means) into K exemplars saved to a file (per-stock or pooled).
- **File:** `trader/features/extrema_features.py`
- Config:
  ```yaml
  features:
    shapelets:
      enabled: false
      exemplars_path: data/shapelets/<symbol>.npy
      window: 15
      metric: euclidean    # euclidean | dtw
  ```
- In `compute()`, if enabled: normalize last `window` closes, append distance to
  each exemplar. `feature_names`: `shape_dist0..K-1`.

### Test
Same backtest harness. **Independence note:** the exemplar-build step reuses the
`forward_label` filter but does NOT require it to be enabled in live config —
it's an offline data-prep dependency, not a runtime one.

### Expected effect / risk
- **Upside:** explicit good-shape matching; interpretable distances.
- **Risk:** quality depends entirely on exemplar selection; per-stock exemplars
  need enough history. More moving parts (offline build + file artifact +
  staleness). Start with Euclidean before DTW.

---

## Plan 5 — Sequence model (true morphology learning)

### Idea
Replace the scalar→logistic paradigm with a model that ingests the **window**
and learns shape end-to-end: 1D-CNN (cheapest), small LSTM, or tiny transformer.
This is the real version of "learn the shape over 5/10/15 candles."

### Architectural change (the only structural one)
The current contract is `FeaturePipeline -> vector -> ExtremaModel`. A sequence
model needs a **window**, not a fixed vector. Two pieces:

1. **New pipeline** `trader/features/window_features.py` — emits a
   `(window, n_channels)` array per candle: channels = e.g. normalized close,
   normalized volume, norm_price per bar. Implements the same `FeaturePipeline`
   ABC but returns a 2-D array. Note: this stretches the "single vector"
   contract — either flatten and document, or generalize `compute()`'s return
   type and update consumers in `lr_extrema.py` (`self._features.compute`).
2. **New model** `trader/models/sequence.py` implementing `ExtremaModel`
   (`fit`, `predict_proba`, `is_trained`). Register in
   `trader/models/registry.py` under `type: cnn` / `type: lstm`.
   ```yaml
   model:
     type: cnn
     window: 20
     channels: [close, volume, norm_price]
     epochs: 30
     lr: 0.001
   ```

### Dependencies / constraints
- Adds a deep-learning dep (torch). Per `registry.py`, non-logistic models were
  deferred because they **overfit per-stock data**. A sequence model is the most
  prone of all — realistically needs **pooled cross-sectional training** (train
  one model across many stocks), which is a larger project than #1–#4.
- `retrain_every` semantics change: refitting a net every 50 candles is
  expensive — consider train-once + periodic fine-tune.

### Test
- Start with a frozen pooled model; backtest with `--cache-only` across the full
  watchlist. Heavy emphasis on **walk-forward** (`backtest_rolling.py`) — this
  is where overfit shows.

### Expected effect / risk
- **Upside:** highest ceiling; learns morphology #1–#4 only approximate.
- **Risk:** highest. Overfitting, training cost, live/backtest determinism,
  new heavy dependency. **Do this last, only if #1–#4 show shape information
  genuinely helps.**

---

## Recommended testing order

1. **Plan 1 (curvature)** — cheapest, isolated, directly targets the knife.
2. **Plan 2 (segmented slopes)** — cheap, compare and combine with #1.
3. **Plan 3 (raw trajectory)** — first real "path" test; needs regularization.
4. **Plan 4 (shapelets)** — if #3 shows path info helps but is noisy.
5. **Plan 5 (sequence model)** — only if #1–#4 prove shape matters; needs pooled
   training to be viable.

Each step: enable the flag → run `backtest.py` and `backtest_rolling.py` →
compare to baseline on `return_pct`, `win_rate`, `max_drawdown_pct`, and
walk-forward consistency. Keep `tests/test_parity_golden.py` green throughout.
