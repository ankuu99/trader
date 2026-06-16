# Learnings — Improving LRExtremaStrategy (shape features → meta-labeling)

_Experimental log + conclusions, June 2026. Companion to `meta_labeling_plan.md`._

## The question we started with

Could the LRExtremaStrategy entry model be improved by giving it more information
about the **shape** of a price bottom (it currently sees only 6 scalars: volume,
norm_price, and 3/5/10/20-bar return slopes — which capture trend *direction* but
erase morphology like curvature, V vs straight knife, multi-segment kinks)?

## What we tried, and what happened

All experiments: 2024-06-01 → 2025-12-31, 15m, full watchlist, `--cache-only`.
Baselines differ by whether per-stock overrides are on (see each section).

### Track 1 — enrich the entry model (FAILED, consistently)

| Experiment | Mechanism | Result vs baseline |
|---|---|---|
| Plan 1: curvature feature | quadratic 2nd-order coeff per window | trades **+26–32%**, win rate ↓, Sharpe ↓ |
| Plan 2: segmented slopes | slope of 1st vs 2nd half of window (kink) | trades **+36%**, win rate ↓ (50%), Sharpe ↓ |
| Plan 5: window + MLP | raw price window → sklearn MLP (nonlinear) | trades **+107%**, win 42%, Sharpe halved, DD 2–4× |

**Decisive control:** for segmented slopes we raised `threshold` to match baseline's
trade count. Win rate stayed pinned at ~50% — it did **not** recover. So the features
didn't just loosen the boundary; they **degraded the model's ranking quality**.

**MLP hyperparameter sweep** (reg 0.001→1.0, capacity [32,16]→[8], window 24→12):
*every* variant fired ~2× trades at 41–44% win rate with Sharpe ~halved and DD 2–4×
worse. Tuning did not save it.

### THE KEY LEARNING

> **The LRExtrema primary is not feature-limited or model-limited.** Every attempt to
> add shape information or model capacity *loosened entry selectivity and degraded
> risk-adjusted returns* — more trades, lower precision. The model sits at a robustly
> good operating point that richer entry features do not beat; they make it worse.

This matched the codebase's own Stage-4 meta-conclusion (pooled training / GBM /
regime features were all tested and reverted): **the edge lives in selectivity and
the exit/policy layer, not in the sophistication of the entry signal.**

### Track 2 — meta-labeling (SUCCEEDED, OOS-validated)

Pivoted on the literature (López de Prado). Instead of a bigger *side* model, add a
**secondary precision filter**: keep the primary generating candidates, add an
xgboost model that predicts `P(this trade wins)` from **context** features (volatility,
regime/autocorrelation, dip depth, RSI, momentum, + the primary's own confidence) and
**vetoes low-quality firings**. Labels = triple-barrier outcomes of the primary's
historical firings (leakage-guarded: a firing is only labelled once its full barrier
window lies in the past).

**In-sample (per-stock OFF baseline = 758t, PF 1.81, Sharpe 0.173, DD 13.3%):**
- meta xgb @0.55: 256t, PF **2.68**, Sharpe **0.273**, DD **3.8%** (−66% trades)
- the gate's filtering power emerges at threshold ≥ 0.55 (at 0.50 it barely filters)

**Out-of-sample walk-forward (2025, 4 folds) — the decisive test:**
| | baseline | meta @0.55 |
|---|---|---|
| Avg win rate | 58.5% | **70.9%** |
| Avg profit factor | 1.52 | **3.79** |
| Avg max drawdown | 5.2% | **1.8%** |
| Calmar | 1.35 | **3.18** |
| Profitable folds | 3/4 | 3/4 |

The precision gain **survived OOS** (logistic leakage-canary also improved → no gross
leakage). Meta-labeling can't rescue a bad regime (the one losing fold stayed losing) —
it filters *within* a regime, exactly as the literature predicts.

**Scale-up recovers the only cost (lower absolute return):** with the filter taking
66% fewer trades and DD at 3.8%, the strategy is under-deployed. Raising the per-stock
cap 10%→20%:
| | trades | PF | pnl | ret% | sharpe | maxDD% |
|---|---|---|---|---|---|---|
| baseline meta-OFF cap10 | 758 | 1.81 | 280,209 | 112.1 | 0.173 | 13.3 |
| meta @0.55 cap10 | 256 | 2.68 | 148,736 | 59.5 | 0.273 | 3.8 |
| **meta @0.55 cap20** | 219 | **3.16** | **277,485** | **111.0** | **0.309** | 5.4 |

→ **same absolute return as baseline, ~2× Sharpe, half the drawdown, 1/3 the trades.**

**Meta is additive on the REAL live config (per-stock overrides ON):**
| | trades | win% | PF | sharpe | maxDD% |
|---|---|---|---|---|---|
| perstock-ON meta-OFF | 571 | 54.6 | 2.06 | 0.231 | 9.3 |
| perstock-ON meta @0.55 | 182 | 58.8 | **2.67** | **0.311** | **5.2** |

So meta helps even after per-stock tuning — it is not just cleaning up an untuned primary.

### Track 3 — better labels (mixed)

- **ATR-scaled triple-barrier labels (2×/2×):** *worse* than plain % barriers
  (PF 2.29 vs 2.68, DD 7.2% vs 3.8%). A 2×ATR profit barrier is easier to hit → more
  "win" labels → meta filters less. **Keep the % barriers (inherited from `exits`).**
- **Trend-scanning primary labels** (dynamic max-t-stat horizon, the principled answer
  to "make `extrema_order` dynamic"): *ultra*-selective at default `t_threshold=2.0` —
  31 trades/18mo, PF 3.37, Sharpe 0.422, DD 2.1%, but only ₹29k (too little capital
  deployed to be practical). A research lead; needs a `t_threshold` sweep to be usable.

## Conclusions / standing guidance for future work

1. **Don't enrich the entry model.** Shape features and bigger models reliably hurt on
   this strategy. The entry signal is good enough; selectivity is the lever.
2. **Meta-labeling is the validated improvement.** A separate precision filter (not a
   bigger primary) is what works. Recommended config: **meta @0.55 (binary, xgboost,
   % barriers) + per-stock overrides ON + cap20 scale-up.**
3. **Judge on risk-adjusted, OOS metrics** (PF, Sharpe, Calmar, walk-forward
   consistency) — not absolute P&L. The MLP "won" on P&L by doubling drawdown; that's a
   trap. Use trade-count-matched comparisons to separate signal quality from boundary
   loosening.
4. **Leakage guard is non-negotiable** for outcome-based labels: only label firings
   whose full barrier window is in the past. The logistic canary + walk-forward are the
   checks that it held.
5. **Production cost is real on t2.micro** (deferred): meta retrain is the expensive
   part. The right fix is the byte-identical O(n^2)->O(n*win) speedup in
   `MetaFilter.train` (bounded feature window) — it cuts the daily warm-up cost
   WITHOUT changing the retrain cadence or any results. Optionally shrink xgboost.

6. **DO NOT decouple `meta_retrain_every` from the primary's 25.** `retrain_every: 25`
   is intentional: 25 = one NSE trading day of 15-min candles (09:15-15:30). More
   importantly, the **live server restarts daily (08:15 cron) and retrains from
   scratch on every warm-up** — so live effectively retrains daily no matter what.
   Setting `retrain_every: 25` makes the BACKTEST mirror that live daily cadence
   (backtest-live parity). The meta-model also retrains on each daily restart's
   warm-up, so it too must stay on the daily (25) cadence; a larger meta cadence
   would break parity with live. Speed up via the bounded-window fix, never by
   changing cadence. (If ever changed, only use multiples of 25 to keep day-alignment.)

## Architecture notes (everything is opt-in, parity-golden preserved)

New components, all behind the existing Stage 1–4 factories:
- `trader/features/meta_features.py` — `MetaFeaturePipeline` (context features)
- `trader/models/meta.py` — `MetaModel` (xgboost | logistic)
- `trader/strategies/meta_filter.py` — `MetaFilter` (train + gate, no-op when off)
- `trader/features/labels.py` — `triple_barrier_label` (+ATR), `TrendScanningLabeler`
- `trader/features/indicators.py` — `atr_at`, `linreg_tstat`
- wired into `lr_extrema.py`; config block `meta_label:` (default `enabled: false`)
- 24 unit tests in `tests/test_meta_labeling.py`; parity golden green with meta off
- (Stripped after testing: curvature, segmented-slope. Kept dormant: window/MLP infra.)
