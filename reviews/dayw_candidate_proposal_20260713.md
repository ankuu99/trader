# Day-TF winner candidate ("dayw volk20") — validation report & paper-trade proposal

**Date:** 2026-07-13 (overnight validation) · **Status:** validated, NOT released — user decision pending
**Config:** `reviews/dayw_volk20_candidate.yaml` (complete, runnable via `--config`)

## What it is

The regime-detection campaign's new detection stack mounted on **day bars** (aggregated
in-memory from the 15m stream) for all 23 watchlist names:

- **Labels:** zigzag swing pivots with **volatility-scaled reversal** — `reversal = 2.0 × σ`
  (σ = std of bar-to-bar % returns over the training window, close-only, clamp [2%, 9%])
  — plus neutral class (ratio 2.0). No fixed reversal magic number.
- **Features:** `extrema_regime` — 6 base + 9 regime scalars (efficiency ratio, variance
  ratio, slope t-stat at 20/60/250 day-bar horizons).
- **Model:** `gbdt` (HistGradientBoosting, depth 3). Thresholds 0.65 entry / 0.60 pattern-top.
- **Per-stock (all 23 names):** `timeframe: day`, warmup 150 / lookback 400 bars,
  `retrain_every: 1` (**live-faithful** — matches the daily warm-up retrain exactly),
  day exit template: 10% profit floor → 4% trail, overnight holds (no force-close),
  stale 10/30 bars, hold cap 40 bars, hard stop 20%, pattern-top scale-out 50%.

## Validation results (2025-01-01 → 2026-07-11, ₹400k, scale-in off)

| Metric | Candidate (k=2.0) | Production baseline |
|---|---|---|
| Total P&L | ₹147.3k (+36.8%) | ₹170.9k (+42.7%) |
| Max drawdown | **10.8%** | 15.3% |
| Calmar | **2.11** | 1.72 |
| Sharpe* | **0.254** | 0.138 |
| Trades / win rate | 196 / 63.8% | 542 / 66.2% |
| Costs | ₹15.0k | ~₹31k |

**Robustness (every gate passed):**
- **k plateau:** k=2.0 ₹147.3k / k=2.5 ₹148.6k (within 1%); k=1.5 fails for a knowable
  reason (lands in the too-noisy ~3% label zone). Fixed-percent labels were a spike
  (5% great, 4%/6% 33–52% worse) — vol-scaling removed that fragility.
- **Rolling windows (6m, step 3m):** 6/7 profitable at both k=2.0 and k=2.5; the only
  "loss" is a 9-trade 10-day stub (−0.2%). **Correction window (2025-H1): +1.2% vs
  baseline −7.2%.** Fixed-5% reference: 7/7 incl. +6.6% in the correction.
- **Exit template:** trail 3/4/5% → Calmar 2.41 / 2.11 / 1.94, DD 10.4–10.8% — gentle
  plateau, no spike.
- **Clamps:** loosening [2,9]→[1.5,12] is bit-identical — clamps never bind.
- **Per-stock:** 13/18 traded names positive; worst-3 drag only −₹8.6k; TRAILING is the
  earning engine (+₹260k / 88 trades — it rides legs). ATHERENERG (the trending IPO that
  needed a special guard at 15m) makes +₹29.9k in 9 trades with no guard.

## Caveats

1. **Concentration:** top-5 names = 89% of P&L (GESHIP, ATHERENERG, CUMMINSIND, CUPID,
   MAYURUNIQ). The tail is benign but not additive.
2. **Absolute return is below baseline** in strong bull windows (+24.9% vs +43.5% in
   2026-Q2) — this is a defensive profile: it buys consistency and half the drawdown at
   the cost of bull-market upside.
3. 18 months of history, one market. Pre-2025 15m data is not in the local cache.
4. t2.micro warm-up cost for gbdt on day bars is untested (small windows ≤400 samples ×
   23 names — expected fine, should be measured on first paper run).

## Rollout options (user decision)

- **A (conservative):** paper-trade the full candidate config on EC2 for 2–4 weeks
  (env: paper), compare live paper fills vs backtest expectation, then decide.
- **B (surgical):** move only the top conviction names to the new stack via
  `per_stock_params` while the rest stay on production config — smallest blast radius,
  but loses the portfolio-level diversification the validation measured.
- **C (hold):** wait for a deeper history backfill (fetch pre-2025 15m data with a live
  token) and run 2024-inclusive rolling first.

Recommendation: **A** — the validation was portfolio-level, so the paper trade should be too.
