# Neutral-class experiment — log & evidence

_Started 2026-07-03. Motivation: live FPs in both P(min) and P(max) causing useless
entries. Structural hypothesis: the binary model (class 0 = min, class 1 = max,
trained ONLY on extrema candles) is forced to emit P(min)+P(max)=1 on every candle,
including the ~90% that are neither — a hard-falling ordinary candle reads as
P(min)≈1. The #8 training diagnostic cannot see this FP class because its holdout
contains only labelled extrema._

Plan: (0) outcome-based firing baseline → (1) neutral class in labeler →
(2) threshold recalibration + A/B validation → (3) rollout incl. trader UI.

---

## Phase 0 — Baselines (2026-01-01 → 2026-07-01, 15m, live config, cache-only)

### Backtest baseline (scripts/backtest.py)

| metric | value |
|---|---|
| Total P&L | ₹67,851 (+27.14%) |
| Trades | 404, win 68.6%, PF 1.71 |
| Sharpe* / Sortino / Calmar | 0.214 / 0.312 / 9.896 |
| Max DD | ₹15,750 (6.3%) |
| **STALE bucket** | **111t, wr 3%, −₹83,052** ← the FP-dip cost |
| PATTERN_TOP_PARTIAL | 131t, +₹70,531 |
| TRAILING(+EOD) | 143t, +₹90,677 |
| CSV | backtest_results/portfolio_20260101_20260701_15m_20260703_010708.csv |

### Firing-precision baseline (scripts/diag_firings.py, new)

Grading: symmetric race +3% vs −3% within 200 bars (triple-barrier; tie/time
conservative). Every scored candle counted, position state cleared each candle.

Portfolio pooled:

| thr | dipN | dip_prec | topN | top_prec |
|---|---|---|---|---|
| 0.80 | 4659 | 0.53 | 3715 | 0.52 |
| 0.85 | 2590 | 0.54 | 1900 | 0.51 |
| 0.90 (live) | 1120 | **0.55** | 694 | **0.50** |
| 0.95 | 293 | 0.58 | 168 | 0.57 |

**Findings:**
1. Dip firing precision at live threshold ≈ 0.55; top ≈ 0.50 (coin flip). The
   strategy earns via payoff asymmetry (avg fwd peak ~+8% vs trough ~−5%), not
   detection quality.
2. Precision-vs-threshold curve is nearly FLAT — P(min) magnitude above 0.80
   carries almost no outcome information. Probability is uncalibrated wrt outcomes.
3. CUPID is INVERTED (0.57@0.80 → 0.32@0.98): highest confidence = worst outcomes,
   the falling-knife artifact of the forced binary split.
4. M&MFIN ~0.40 flat at all thresholds — also the only loser in the backtest.
   IPCALAB healthiest (0.71–0.86, rising with threshold — properly calibrated).

**Success criteria for the neutral class:** firing precision at the operating
threshold rises materially (esp. CUPID/M&MFIN de-inverting), STALE bucket shrinks,
AND portfolio P&L/Calmar not worse than the backtest baseline above.

---

## Phase 1 — Implementation (2026-07-03)

`labels.neutral: { enabled, ratio, margin_bars }` in ExtremaLabeler — class-2
samples ≥ margin bars from every geometric extremum, deterministic evenly-spaced
sampling. LogisticRegression goes multinomial automatically; predict_proba already
indexes by class. feature_contributions gained a 3-class branch; `model.class_weight`
exposed. Parity when disabled: full suite green (only pre-existing stale
test_parity_golden failure, confirmed on clean tree). Also fixed the broken
`backtest.py --config` (added `Config.reload`).

Note: with extrema_order=10 the ±10-bar exclusion zones cap available neutral
candidates well below ratio=1.0's target — effective neutral share is smaller than
requested. Smoke (CUPID): p_min+p_max mean 0.795 (was ≡1.0), min 0.078.

## Phase 2 — Results (2026-01-01 → 2026-07-01, cache-only)

### Firing precision WITH neutral (diag --neutral --wide-grid)

Portfolio dip precision now RISES with threshold — calibration is fixed:
0.54@0.40 → 0.57@0.60 → 0.61@0.70 → 0.66@0.80 → 0.79@0.90 (baseline: flat ~0.55).
Top side stays flat ~0.50 — neutral does NOT fix top calibration.
CUPID and M&MFIN remain INVERTED under neutral (their high-confidence dips are
real falling knives — per-stock property, not a model artifact).
CSV: backtest_results/diag_firings_neutral_20260101_20260701.csv

### Backtest A/B (global threshold sweeps, per-stock thresholds stripped)

| config | trades | P&L | Calmar | max DD | STALE bucket |
|---|---|---|---|---|---|
| **baseline (binary, live cfg)** | 404 | **₹67,851** | **9.90** | 6.3% | 111t −₹83.0k |
| neutral t0.50 s0.60 | 483 | ₹44,749 | 3.80 | 10.4% | 149t −₹106.6k |
| neutral t0.60 s0.60 | 404 | ₹62,452 | 7.22 | 7.9% | 111t −₹77.1k |
| **neutral t0.60 s0.55** | 425 | **₹67,931** | 8.30 | 7.5% | — |
| neutral t0.60 s0.50 | 436 | ₹67,774 | 8.27 | 7.5% | — |
| neutral t0.65 s0.60 | 322 | ₹54,965 | 8.85 | 5.6% | — |
| neutral t0.70 s0.60 | 248 | ₹37,891 | 6.03 | 5.5% | 74t −₹45.4k |
| neutral ratio=2.0 | 217 | ₹30,695 | 6.77 | 3.9% | — |
| neutral class_weight=balanced | 588 | ₹31,135 | 2.10 | 12.7% | — |
| neutral + per-stock thr (diag-picked) | 375 | ₹53,883 | 6.41 | 7.5% | — |

### Verdict (this window)

Neutral class **fixes probability calibration** (real, measurable, monotone
precision curve) but **does not beat baseline P&L**: best config (t0.60/s0.55)
exactly matches ₹67.9k with worse Calmar (8.3 vs 9.9). At matched trade volume the
precision edge is tiny (0.57 vs 0.55); the big precision gains live at thresholds
that fire too rarely to pay. The STALE bucket barely shrinks at matched volume —
consistent with [[project_peak_detection_vs_pnl]]: detection quality and realized
P&L are decoupled by the exit mechanism.

Per-stock diag-picked thresholds HURT (₹53.9k) — lowering thresholds on inverted
names adds churn; inversion means "don't trade the model's confidence", not
"recalibrate it".

**Status: NOT adopted. Config stays enabled:false.** Remaining honest branch:
rolling-window / regime validation of t0.60/s0.55 (2023–26) before final burial —
its value would be robustness (calibrated scores make probability-driven logic
like momentum_decay meaningful), not this window's P&L.

---

## Phase 2b — momentum_decay under calibrated scores: ROBUST NULL (2026-07-03)

Hypothesis: probability-driven exits failed historically because P(min) was
uncalibrated; under neutral scores, "P(min) < floor while underwater" should cut
STALE losers early. Swept p_min_floor {0.10,0.20,0.30} × min_bars {5,10,20} on
neutral t0.60/s0.55, plus binary controls (floor 0.30/0.50, min_bars 10).

| config | trades | P&L | Calmar |
|---|---|---|---|
| no momentum_decay (baseline) | 404 | **₹67,851** | **9.90** |
| no momentum_decay (neutral best) | 425 | ₹67,931 | 8.30 |
| neutral, best of 9 (f0.20/b20) | 523 | ₹27,223 | 3.46 |
| neutral, worst (f0.10/b5) | 524 | ₹14,766 | 1.93 |
| **binary control f0.30/b10** | 457 | **₹30,805** | 5.53 |

ALL 11 variants far below baseline. Failure mode is uniform: 200–560 decay exits;
even where the MOMENTUM_DECAY bucket itself is positive (+₹19.4k at f0.30/b20),
portfolio P&L collapses because each early exit forfeits a would-be trailing/
pattern-top winner (per-bucket P&L is circular — portfolio number is the truth).
The binary control BEAT every calibrated variant → calibration was NOT the reason
probability-driven exits fail. They fail because the strategy's edge is holding
through noise for asymmetric bounces; any extra early-exit path destroys more
upside than it saves downside (same lesson as direct pattern-top exit, meta-veto,
stale tightening). The bar-20/100 stale exits are already near-optimal dead-money
cuts.

**Do not revisit momentum_decay. Do not assume calibration unlocks
probability-driven exit logic — tested, falsified.**
