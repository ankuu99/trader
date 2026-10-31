# Plan — testing the Bruni et al. 2026 ideas in the extrema lab

Source: "Stock market movement prediction with CNN-based classification of space-filling
curves" (Applied Soft Computing 202, 2026). Extracted text cached in the session
scratchpad; PDF at `~/Downloads/1-s2.0-S1568494626013748-main.pdf`.

## What we take, what we skip

The paper's own ablation + McNemar tests say the edge is **labels + preprocessing**,
not the Hilbert/CNN representation (1D CNN, LSTM, ResNet, Z-curve all statistically
indistinguishable). So:

| Paper component | Verdict | Why |
|---|---|---|
| Averaged 10v10 directional label | **TEST** — Idea 1 | Their biggest framing change; maps cleanly to our labeler plug point |
| Gaussian smoothing of the input + acceleration-gated edge extension | **TEST** — Idea 2 | +6pp and +2.5pp in their ablation, the two dominant effects |
| Hilbert curve → 8×8 image → CNN | **SKIP** | Not significant in their own tests; our MLP/window-features arm was already falsified; adds a DL dependency for nothing |
| Their trading sim (θ=0.7 gate, 10-day blocks, K·σ trailing) | **SKIP for now** | We already have a richer exit stack; the K·σ adaptive trail idea is a separate future experiment at most |

Both ideas are **config-gated, default-off**, consistent with the existing alt-stack
convention. Day TF is the natural home (paper is daily; matches the day-TF winner
candidate stack).

## Idea 1 — `AvgTrendLabeler` (`labels.type: avg_trend`)

New labeler in `trader/features/labels.py`, registered in `build_labeler`.

Rule, for bar t with window n (`labels.avg_trend.window`, default 10):

- `μ_future = mean(close[t+1 .. t+n])`, `μ_past = mean(close[t-n+1 .. t])`
- class 0 (buy/up) if `μ_future > μ_past`, else class 1 (sell/down)

Design decisions:

1. **Dense labels.** Unlike extrema/zigzag (sparse turning points), every eligible bar
   gets a label. This is the point: the model becomes an Up/Down regime classifier,
   and its **Down→Up transition** is the tradeable "bottom" event. No sample
   starvation — a 1200-bar window gives ~1180 samples, so the lb6k pairing is
   optional, not required.
2. **Truncation guard.** The last n bars of the training window have unresolved
   futures — drop them (same principle as `triple_barrier_label` returning None).
   Also skip `t < max(n, 20)` (feature min_history).
3. **Optional deadband** (`labels.avg_trend.deadband_pct`, default 0 = off): drop bars
   where `|μ_future/μ_past − 1| < deadband_pct/100`. The paper is strictly binary, but
   borderline labels are coin flips; a small deadband is our standard noise hygiene.
   Sweep 0 / 0.25 / 0.5.
4. **Neutral class does NOT apply** — with dense two-sided labels there is no
   "neither" mass problem (that fix exists because extrema labels are sparse).
5. **Lab metric mapping**: for `--labels-only` evaluation, dense labels can't be
   scored as-is (precision assumes sparse event indices). Score the **class-transition
   indices** (1→0 transitions vs true minima, 0→1 vs true maxima) instead. Small
   helper in the benchmark/metrics layer, only used for this labeler family.
   Full-model arms need no metric change — `crossings()` already scores rising edges
   of P(min) ≥ thr, which is exactly the Down→Up confidence flip.
6. **Threshold regime is different.** Dense balanced labels → P(min) hovers near 0.5
   rather than saturating; fixed 0.90/0.85 is wrong out of the gate. Arms must sweep
   thresholds (0.60/0.70/0.80) and include a quantile rule.

## Idea 2 — causal Gaussian smoothing of the close channel (`features.smoothing`)

Config block consumed by the feature pipelines (wired in `build_feature_pipeline` /
`FeaturePipeline` base so all pipeline types get it uniformly):

```yaml
features:
  smoothing:
    enabled: true
    window: 21        # W, Gaussian kernel width (σ = W/6), bars
    edge: accel       # accel | constant | linear
    slope_bars: 10    # γ — regression window for the linear extension
```

Design decisions:

1. **Smooth the close series only.** The paper uses closes only. Our features also
   consume high/low/volume (`norm_price`, `volume_ratio`) — leave those raw; smoothed
   closes feed the return-slope features (and regime features when
   `extrema_regime` is active).
2. **Causal everywhere — no centered smoothing at training time.** This is the one
   place we deliberately deviate from the paper. They smooth training segments with
   real future bars and approximate that at test time via extrapolation. In our
   per-bar pipeline that would put future closes inside training *features* — leakage
   the live path can't reproduce, and exactly the class of bug we've been burned by.
   Instead: at every bar i (train and inference alike), extend `closes[..i]` by W/2
   synthetic points using the paper's acceleration rule, apply the Gaussian kernel,
   take the smoothed value at i. Train/test representations are identical by
   construction — which their ablation says is what actually matters (truncated-
   everywhere ≈ raw; the killer was train/test inconsistency + edge distortion).
3. **Acceleration rule** (from §3.2.2): let a = second difference at the end of the
   smoothed-so-far series; a_low = μ − σ of accelerations over the trailing training
   year. Extension is constant if `a ≥ 0` or `a ≤ a_low`, else linear with the
   γ-bar regression slope. Implement `constant` and `linear` as forced modes so the
   ablation arms exist.
4. **Cost**: O(W) per bar per retrain window. At day TF this is trivial; fine at 15m too.
5. Unit tests: kernel normalization, causality (feature at bar i unchanged when future
   bars are mutated), extension-mode selection, parity when `enabled: false`.

## Benchmark plan (`scripts/lab/benchmark.py` arms)

> **Stage L result (2026-07-15): PASS — decisive.** `avg_trend` n=25 transition
> labels score P=1.0/R=1.0 on all four trend/noise scenarios (s2/s4/s5/s7),
> beating zigzag_r1.5 (P 0.70 on the noise ladder, 0.94 on regime switches), and
> keep P=1.0 with R≈0.86 on the hard oscillation scenarios (s3/s6) vs zigzag's
> R≈0.65. Window sensitivity: n=10 too noisy (P 0.59–0.70 under noise), n=50 too
> slow for multi-frequency (R 0.18) — **n=25 (one trading day of 15m bars) is the
> operating point**. Deadband 0.25 adds nothing at n=25 (already perfect) and
> costs recall on s3/s6. Run: `lab_data/benchmark_runs/labels_20260715_231809.csv`.

Stage L — label quality only (cheap, run first):

- `avgtrend_n10`, `avgtrend_n10_db025` (deadband 0.25) via `--labels-only` with the
  transition-index scoring. Compare against `zigzag` vol-scaled and `base` extrema.
- **Kill criterion**: if avg_trend transition labels are not at least comparable to
  zigzag vol-scaled on the trend scenarios (s2/s5/s7) — the label is the heart of the
  paper — stop here and record a NULL.

> **Stage M result (2026-07-16): BOTH IDEAS KILLED per the pre-set criteria.**
> Run: `lab_data/benchmark_runs/stage_m_paper.csv`.
>
> **avg_trend as an entry detector: FAIL.** The Stage-L label quality did not
> survive the walk-forward model. Logistic on dense labels fires constantly
> (400–800 firings vs ~99 truths; dip P@10 ≈ 0.10 on every trend/noise scenario).
> `avgtrend_gbdt_t70` (regime features + gbdt) is far better — P@10 0.33–0.49,
> 4–6× chance, recall 0.7–0.99, zero median lag — but its firings sit
> **1.1–2.3% above the trough** on trend scenarios (gate: ≤0.5%), and it's below
> `winner_gbdt` on precision everywhere. This is structural, not tunable: the
> 10v10 averaged label *confirms* a turn ~window/2 bars after it, so the model's
> Down→Up flip is inherently that late. Good regime classifier, wrong tool for
> dip-entry timing. (The paper's own trading sim rides 10-day regime blocks —
> it never claims trough-proximal entries.)
>
> **Smoothing on the winner recipe: NULL.** `smooth_on_winner` vs `winner_gbdt`
> dip P@10: s1 0.979 vs 0.959, s2 0.766 vs 0.794, s3 0.737 vs 0.782, s4 0.402
> vs 0.367, s5 0.460 vs 0.452, s6 0.655 vs 0.692, s7 0.633 vs 0.625 — parity
> within noise (4 up, 3 down, both 7/7 PASS). Edge-mode ablation: `linear` is
> marginally the best variant on s3/s6 but collapses on s1 (0.503). Fails the
> "improve ≥2 scenario families" bar → not carried to Stage B.
>
> **Stage B: not run** — no surviving arm (per kill criteria; no tuning
> expeditions to flip a fail).

Stage M — full model arms (all through the existing scenario matrix + criteria):

| Arm | Labels | Features | Model | Thr |
|---|---|---|---|---|
| `avgtrend_log` | avg_trend n=10 | extrema | logistic | sweep 0.60/0.70/0.80 + quantile |
| `avgtrend_gbdt` | avg_trend n=10 | extrema_regime | gbdt | sweep |
| `avgtrend_smooth` | avg_trend n=10 | extrema + smoothing W=21 accel | logistic | sweep |
| `smooth_on_winner` | zigzag vol-scaled k=2 + neutral 2.0 | extrema_regime + smoothing | gbdt @ 0.65/0.60 | fixed |
| `smooth_edge_ablation` | (winner recipe) | smoothing edge=constant / linear | gbdt | fixed |

`smooth_on_winner` is the orthogonal test: does the paper's preprocessing improve our
already-validated day-TF winner recipe? That's the highest-value single arm.

Pass bar: existing lab criteria (trend: dip P@10 ≥ 2× chance, R@10 ≥ 0.30,
med-%-above-trough ≤ 0.5; oscillation: P@10 ≥ 0.50), and to be *interesting* an arm
must match or beat `winner_gbdt` on the scenarios it passes.

Stage B — backtest bridge (only for arms that clear Stage M):

- Day-TF backtest via `backtest.py` / `backtest_rolling.py` on the current watchlist,
  2024-01 → 2026-07 plus the rolling half-year windows, comparing against the day-TF
  winner candidate (Calmar 2.11, DD 10.8%, 6/7 windows) and production baseline.
- `calibrate.py`/`screen.py` untouched — same rule as scale-in: validate portfolio
  effects only through backtest scripts.
- No live/config changes come out of this plan; a winning result feeds the same
  review process as the day-TF candidate (proposal doc in `reviews/`).

Kill criteria summary:
- Stage L fail → NULL memory ("averaged directional label falsified at label level"), stop.
- `smooth_on_winner` no better on ≥2 scenario families → smoothing NULL, don't carry to Stage B.
- Stage B worse Calmar than the existing day-TF candidate → record and stop; no tuning
  expeditions to flip a fail (fingerprint-discovery rule).

## Implementation order & size

1. `AvgTrendLabeler` + factory entry + unit tests (~80 lines total).
2. Transition-index scoring for dense labelers in the lab (~30 lines).
3. Stage L run → go/no-go.
4. Smoothing preproc + edge extension + unit tests (~120 lines).
5. Stage M arms (config-only) → run matrix.
6. Stage B only on survivors.

Steps 1–3 are independent of 4–5; if the label dies at Stage L, smoothing
(`smooth_on_winner`) is still worth running on its own — the two ideas are orthogonal.
