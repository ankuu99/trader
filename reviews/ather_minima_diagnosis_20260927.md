# ATHERENERG — why local minima are missed and why false positives fire (2026-09-27)

Question: on a single stock, why does the LRExtrema detector miss visually obvious
swing bottoms, and why does it fire where there is no bottom? Threshold is explicitly
out of scope — the question is the identification technique.

Setup: 15m cached candles 2025-05-06 → 2026-09-03 (8,172 bars), walk-forward with the
exact live params (`config.get_strategy_params("NSE:ATHERENERG")`: extrema_order 10,
lookback 1200, retrain 25, warmup 300, threshold 0.90, 7 features incl. depth),
`scripts/lab/harness.py::run_ml_harness` → 315 retrains, 7,873 scored bars.
Reference "true" dips (until hand labels exist): zigzag pivot lows at 2 / 3 / 5 %
minimum reversal on closes (uses the future — fine for ground truth).
Chart of one window: `reviews/ather_minima_20260927_example.png`.

## 1. Headline numbers

| | value |
|---|---|
| bars with P(min) ≥ 0.90 | 233 (3.0 %) → 146 firing episodes (run of fires, gap ≤ 3) |
| bars with P(min) ≥ 0.70 | 27 % of all bars; ≥ 0.50 on 57 % |
| recall of 3 % zigzag dips (fire within [−5, +10] bars) | 50 % (41 / 82) |
| recall of 5 % dips | 49 % (18 / 37) |
| episode precision (a 3 % dip within [−10, +5] bars of the first fire) | 34 % |
| lag of first fire vs the dip bar | median **−2 bars** (fires while still falling) |
| missed 3 % dips — best P(min) inside the window | median 0.85; 100 % had ≥ 0.70 |
| bar-level AUC of P(min) vs "within ±3 bars of a 3 % dip" | **0.60** |
| bar-level AUC of P(min) vs 40-bar trade outcome (up ≥ 3 %, dn ≥ −2 %) | **0.50** |

Threshold sweep (3 % reference; per-episode forward 40-bar outcome):

| thr | fire bars | episodes | recall | precision | median fwd best gain | share ≥ 2 % |
|---|---|---|---|---|---|---|
| 0.70 | 2148 | 665 | 100 % | 15 % | 2.1 % | 52 % |
| 0.80 | 974 | 437 | 90 % | 20 % | 2.2 % | 53 % |
| 0.85 | 528 | 275 | 74 % | 28 % | 2.5 % | 56 % |
| 0.90 | 233 | 146 | 50 % | 34 % | 2.8 % | 60 % |
| 0.95 | 63 | 43 | 26 % | 51 % | 3.0 % | 67 % |

The trade-off is flat: no threshold gives both. The *ranking* is the problem, which
confirms the premise that this is not a threshold issue.

## 2. Mechanism — the score is a "bar closed at its low" detector

Correlation of the walk-forward P(min) with each feature over all scored bars, and the
MinMax-scaled logistic coefficients (+ pushes toward MAX, − toward MIN; b ≈ −5.4):

| feature | corr with P(min) | coef (typical) | AUC vs 3 % dip when used ALONE |
|---|---|---|---|
| norm_price (close position in bar) | **−0.82** | **+2.1…+2.5** | 0.49 |
| drawdown_from_high (50-bar depth) | −0.46 | +1.6…+2.1 | **0.78** |
| slope20 / slope10 / slope5 / slope3 | −0.44 / −0.50 / −0.46 / −0.39 | +1.8 / +1.6 / +1.2 / +0.8 | 0.50 (all four) |
| volume_ratio | −0.24 | +0.5 | — |

Feature ablation at the same labels, same retrain cadence, same firing budget (top 3 %
of bars, ≈ the live 0.90):

| feature set | AUC vs 3 % dip | episodes | precision | recall | median fwd gain | share ≥ 3 % |
|---|---|---|---|---|---|---|
| live 7 features | 0.603 | 148 | 34 % | 52 % | 2.8 % | 49 % |
| without norm_price | **0.669** | 113 | 34 % | 44 % | 2.8 % | 48 % |
| without depth | 0.496 | 164 | 24 % | 43 % | 2.3 % | 40 % |
| depth only | **0.778** | 26 | **50 %** | 20 % | **4.0 %** | **73 %** |
| norm_price + depth only | 0.640 | 101 | 40 % | 37 % | 3.1 % | 52 % |
| norm_price only | 0.494 | 200 | 18 % | 35 % | 2.2 % | 39 % |
| slopes only | 0.497 | 137 | 23 % | 37 % | 2.3 % | 42 % |

Reading:

- **The only feature that knows where we are in the swing is depth.** The six
  bar-shape features (where the bar closed, the last-20-return slopes, volume) are
  coin-flips for "near a swing bottom" (AUC ≈ 0.50) — yet they carry the largest
  coefficients and explain most of the score's variance.
- **Why the fit lands there:** training labels are *minimum-vs-maximum* over a ±10-bar
  window. A bar that closed at its low after a run of negative returns is, by
  construction, far more likely to be the lowest close of its neighbourhood than a bar
  that closed at its high. So the classifier learns "did this bar fall" — perfectly
  separating the two label classes — which is not the trading question "is this the
  bottom of a swing worth buying". Label minima have median norm_price 0.24 vs 0.76 for
  maxima; the model then extrapolates: the 0.90 firings have median norm_price **0.07**.
- **Why it still makes money:** at 0.90 all seven pushes must line up, so the firing
  bars are also ~4 % below the 50-bar high (median dd50 −4.0 % false / −4.5 % true).
  The threshold works as a crude depth filter with noisy timing.

## 3. Why real bottoms are missed

The bottom bar of a swing is usually a reversal bar — it closes *off* its low
(median norm_price 0.30 at 3 % zigzag dips, 0.67 at the best missed ones). The model
penalises exactly that. The trace of the biggest missed dip (2026-04-07, +23 % bounce):

| bar | close | P(min) | norm_price | depth | slope5 |
|---|---|---|---|---|---|
| 04-07 14:00 | 771.5 | **0.83** | 0.00 | −2.7 % | −0.8 |
| 04-07 15:00 | 765.9 | 0.76 | 0.21 | −3.4 % | −1.4 |
| **04-07 15:15 (the low)** | **759.0** | **0.67** | **0.67** | **−4.3 %** | **−2.9** |
| 04-08 09:15 | 771.9 | 0.40 | 0.38 | −2.7 % | +2.4 |
| 04-08 09:30 | 778.9 | 0.14 | 0.98 | −1.8 % | +4.3 |

The deepest, steepest bar gets 0.67 because it closed in the upper third of its range;
a shallower bar earlier that closed exactly at its low got 0.83. Once the bounce
starts the slopes flip positive and P(min) collapses to 0.1–0.4, so the model can only
ever fire *during* the fall, never on or after the turn. Dips that fall with mid-range
closes (smooth declines, gap-down-then-recover bars) never reach 0.90; their best
P(min) sits at 0.80–0.88 — the whole "missed" population lives there
(29 of 41 missed 3 % dips had P(min) 0.7–0.9 at the dip bar; none ≥ 0.9).

## 4. False positives

Against the 3 % reference, 97 of 146 episodes are false. They are **not flat-price
events on this stock**: median 20-bar range 5.3 % (true: 5.4 %); only 1 of 97 had a
range under 2 %. What they are: bars closing at their low (median norm_price 0.10)
inside a decline that keeps going — the ten worst all have norm_price ≤ 0.18 and
forward 40-bar drops of −4.4 % to −7.9 %. 27 of 146 episodes start on the 09:15
opening bar (gap-downs; vol_ratio 3.0) with the same precision as the rest.

The "flat price sees a minimum" observation is real at the **sparkline** level, not at
0.90: in bars whose 20-bar range is under 1.5 %, P(min) ≥ 0.70 on 17 % of bars and
≥ 0.50 on more than half, but ≥ 0.90 on 0 %. That is the binary split
(P(min) + P(max) = 1 with no neutral class): a flat bar that closed lowish reads as
"more min than max". On ATHERENERG the ±10-bar training minima are mostly real
(median depth 2.6 %, only 6.5 % under 1 %) — on a calmer stock the flat-wiggle
labels would be a much larger share.

## 5. Things that do NOT fix the ranking (same harness, same reference)

| variant | AUC vs 3 % dip | precision @3 % budget | recall |
|---|---|---|---|
| live baseline | 0.603 | 34 % | 52 % |
| extrema + collapse_ties | 0.601 | 34 % | 51 % |
| extrema + neutral class 2.0 | 0.590 | 23 % | 37 % |
| extrema_order 5 / 20 | 0.576 / 0.601 | 33 % / 34 % | 50 % / 48 % |
| lookback 3000 | 0.593 | 31 % | 45 % |
| retrain_every 5 | 0.603 | 32 % | 49 % |
| + regime features (50/200/800), depth kept | 0.608 | 33 % | 52 % |
| zigzag vol-scaled k=2 + neutral (logistic) | 0.592 | 25 % | 43 % |
| zigzag + neutral + regime (logistic) | 0.579 | 24 % | 37 % |
| zigzag + neutral + regime, gbdt (lb 1200) | 0.553 | 16 % | 22 % |
| 0.90 + require an up-close within 2 bars | 0.603 | 36 % | 46 % |

Label window, lookback, cadence, neutral class, zigzag labels, regime features and
GBDT all leave the ranking where it is (the day-TF winner recipe was validated at day
bars with a 6000-bar window; at 15m/1200 it is worse). The one lever that moves it is
the **feature set** — removing the bar-shape feature or leaning on swing-position
features.

## 6. What this means (hypotheses to test, not decisions)

1. **The feature vector answers the wrong question.** Bar shape + short return slopes
   describe "is this bar falling"; the buy question is "how far into a swing are we, and
   has it turned". Candidate fix: swing-position features (depth at several lookbacks,
   distance from the N-bar low, bars since the high) plus a *reversal* bar-shape term
   (close vs previous close, lower-wick share) instead of the raw close position, and
   dropping or attenuating norm_price. Depth alone already ranks at 0.78 but is too
   smooth to time an entry (26 episodes) — it needs a trigger.
2. **Timing:** the model fires 2–5 bars before the bottom and goes quiet on the turn.
   A confirmation trigger (first up-close after a depth-qualified decline) trades
   recall for precision only marginally in the raw test above; with better ranking
   features it may do more.
3. **Labels:** min-vs-max is the root of the bar-direction shortcut. Min-vs-neutral did
   not help on its own (neutrals are random bars, still separable by bar shape); the
   label change only pays off together with the feature change.

All of the above is measured against a 3 % zigzag proxy for "visible bottom" and
against dip proximity — **not P&L**. Every earlier entry-side filter that looked good
on a detection metric lost money in the portfolio backtest (meta-labeling, knife gate,
cooldowns), so the order is: hand labels → re-score against human truth → backtest the
best feature-set variant through `backtest.py` on 2025-01→2026-08 vs ₹482k / Calmar 5.25.

## 7. Scored against the HUMAN labels (191 dips, full coverage 2025-05-06 → 2026-09-03)

Labels: `lab_data/ATHERENERG_15minute/labels.csv` (dips only). Human dips are finer than the
3 % zigzag proxy — median drop from the 50-bar high −3.3 % (IQR −5.0…−2.3), median 40-bar
bounce +4.0 %. 89 % of 3 % zigzag pivots are human dips, but only 40 % of human dips are
3 % pivots, so the proxy under-counted the shallower swings the user trades.

**The training-label definition is not the problem.** 79 % of human dips are exactly a
±10-bar extrema minimum (77 % on the exact bar; 91 % at ±5). The model is taught the right
bars; it just doesn't learn what makes them dips.

| variant (same matching as above; 182 human dips in the scored range) | AUC | episodes | precision | recall | lag | fwd 40-bar gain | share ≥ 3 % |
|---|---|---|---|---|---|---|---|
| **LIVE @0.90 (as traded)** | 0.54 | 146 | 38 % | **27 %** | −1 | 2.8 % | 49 % |
| LIVE @0.85 | 0.54 | 275 | 36 % | 48 % | −2 | 2.5 % | 44 % |
| LIVE @0.80 | 0.54 | 437 | 32 % | 68 % | −2 | 2.2 % | 38 % |
| without norm_price | 0.57 | 113 | 40 % | 25 % | −1 | 2.8 % | 48 % |
| depth only | 0.64 | 26 | 46 % | 8 % | −4 | 4.0 % | 73 % |
| every harness variant (§5) | 0.50–0.56 | 115–171 | 31–42 % | 20–32 % | | | |
| **rule: lowest close of last 20 bars** | | 293 | 45 % | 78 % | −2 | 2.2 % | 40 % |
| **rule: lowest close of 20, then next bar closes up** | | 338 | **51 %** | **78 %** | +1 | 2.2 % | 38 % |
| rule: same + depth ≤ −2 % | | 261 | 50 % | 60 % | +1 | 2.0 % | 37 % |
| live P ≥ 0.75 at t−1, up-close at t, depth ≤ −2 % | | 358 | 40 % | 60 % | −2 | 2.3 % | 38 % |

A two-line rule with no model beats the trained detector on both axes at the same time.
Univariate ranking power against "within ±3 bars of a human dip" (AUC):

| feature | AUC | | feature | AUC |
|---|---|---|---|---|
| RSI(14) | **0.69** | | slope20 (live) | 0.56 |
| % above 20-bar low close | **0.68** | | LIVE P(min) (all 7 features) | **0.54** |
| 20-bar return | 0.68 | | close vs prev close | 0.51 |
| % below 50-bar high (live depth) | 0.65 | | lower-wick share | 0.50 |
| 5-bar return | 0.64 | | norm_price (live) | 0.49 |
| volume_ratio (live) | 0.61 | | slope5 (live) | 0.42 |

Every swing-position feature beats the whole model on its own; every bar-shape feature is
at chance. The model combines one good feature (depth) with five noise features and lets
the noise dominate because noise separates min-labels from max-labels.

Recall of the live model by dip depth (depth at the dip bar): deeper than −5 % → 53 %,
−5…−3 % → 33 %, −3…−2 % → 13 %, shallower than −2 % → 3 %. Missed dips (132) all had a
best P(min) of 0.70–0.90 inside the window; median P(min) *on* the dip bar is 0.77 and
drops to 0.38 on the next bar (norm_price 0.29 → 0.81). The model sees the bottom as the
most likely bar locally, at a level the threshold never admits, and forgets it one bar later.

False positives at 0.90 vs human dips (90 of 146): none in a 20-bar range under 1.5 %
(flat-price firing does not happen at 0.90 on this stock); 39 % are 6–20 bars *early*
(fired on a close-at-low bar mid-decline), 46 % are more than 20 bars from any dip.

## 8. Built and backtested — FALSIFIED on P&L

Implemented (config-gated, default-off): `features.type: swing`
(`trader/features/swing_features.py`: volume_ratio, above_low_20/50, depth_20/50, ret_5/20,
rsi_14 — no bar-shape channel) and `entry_gates.turn: {lowest_of: N}`
(`trader/policy/extrema_entry.py`: previous bar is the lowest close of N, current bar closes
up). `tests/test_swing_features.py`. Harness vs the human dips (AUC 0.69 vs 0.54):

| detector | episodes | precision | recall |
|---|---|---|---|
| live @0.90 | 146 | 38 % | 27 % |
| swing @0.85 | 122 | 48 % | 42 % |
| swing @0.80 + turn20 | 152 | 51 % | 39 % |
| swing @0.60 + turn20 | 291 | 50 % | 68 % |

`backtest.py` 2025-01-01 → 2026-08-31 (cache re-fetched 2026-09-27; this run's baseline is
₹498k / Calmar 5.50 / DD 8.0 %, 814 trades, util 61 %):

| run | trades | win % | P&L | Calmar | max DD |
|---|---|---|---|---|---|
| ATHERENERG standalone — baseline | 58 | 77.6 | ₹44.1k | 8.89 | 0.8 % |
| ATHERENERG — swing 0.85 | 65 | 69.2 | ₹41.3k | 5.25 | 1.0 % |
| ATHERENERG — swing 0.80 + turn20 | 58 | 69.0 | ₹37.8k | 3.59 | 1.4 % |
| ATHERENERG — swing 0.60 + turn20 | 80 | 63.7 | ₹40.4k | 3.36 | 1.6 % |
| portfolio — baseline | 814 | 70.9 | **₹498k** | **5.50** | 8.0 % |
| portfolio — swing 0.85 on the 7 15m names only (fair) | 764 | 66.5 | **₹391k** | **3.46** | 10.2 % |
| portfolio — swing 0.85 global (confounded: day/4h thresholds uncalibrated, util 43 %) | 671 | 65.1 | ₹204k | 2.09 | 9.2 % |
| portfolio — swing 0.80 + turn20 global (confounded) | 542 | 62.4 | ₹97k | 1.24 | 7.6 % |

Per-stock in the fair run (baseline → swing): ATHERENERG +58.1k → +51.3k, CGPOWER +24.5k →
−12.2k, KPL +24.1k → +20.7k, QUESS +35.0k → +28.2k, THANGAMAYL +19.3k → +12.1k, TIPSMUSIC
−0.3k → −11.2k, TVSMOTOR +9.1k → +9.2k. Six of seven worse, one flat, utilisation identical
(62 %), so this is not a capital-starvation artefact.

**Why better identification loses money.** The extra dips the swing model catches are the
shallow 2–3 % swings the hand labels include (its recall gain lives there: live recall on
2–3 % dips is 13 %). Those trades do not move 0.5 % inside 40 bars and die on tier-1 stale
(ATHERENERG STALE exits 3 → 8–13, ≈ −₹1k each) while the trailing/scale-out winners stay flat
(₹46k → ₹43–46k). The live model's bias toward deep, close-at-low capitulation bars — the
"defect" of §2 — is exactly what selects the dips that bounce 3 %+ and pay for the exit stack.
Its firings bounce a median 2.8 % vs 2.2 % for the swing model. Detection quality against
human-visible bottoms is not the objective the portfolio rewards.

Same verdict as meta-labeling, the knife gate and the re-entry guards: do not re-tune. The
code stays as a dormant option for a future exit stack that can hold shallow swings.

## 9. Exit-side follow-up — trail arms at 3 % (user request) — also FALSIFIED

Hypothesis: the swing entries lose because the exit stack (trail arms at +7 %, tier-1 stale
at bar 40) cannot hold a shallow swing; arm the 2 % trail at +3 % instead (pattern-top
already needs 3 %), with and without the 50 % scale-out. Global `exits.trailing.profit_pct`
7 → 3; the aggregated-TF blocks keep their own 10 %/4 % so, as before, only the 7 15m names
change. Same window, same cache.

| entry | exit | trades | P&L | Calmar | max DD | trailing exits |
|---|---|---|---|---|---|---|
| live | current | 814 | **₹498k** | **5.50** | 8.0 % | 216 → ₹524k |
| live | trail @3 %, scale-out kept | 772 | ₹397k | 3.98 | 9.0 % | 315 → ₹548k |
| live | trail @3 %, no scale-out | 639 | ₹424k | 4.19 | 9.1 % | 316 → ₹708k |
| swing 0.85 | current | 764 | ₹391k | 3.46 | 10.2 % | 196 → ₹477k |
| swing 0.85 | trail @3 %, scale-out kept | 764 | ₹358k | 3.20 | 10.2 % | 311 → ₹539k |
| swing 0.85 | trail @3 %, no scale-out | 639 | ₹369k | 3.29 | 10.2 % | 308 → ₹674k |

ATHERENERG standalone: live/current ₹44.1k (Calmar 8.9) → live/trail@3 % ₹27.0k (4.95);
swing/current ₹41.3k → swing/trail@3 % ₹31.5k (4.81). Scale-out on/off is a no-op there.

Reading: arming the trail at 3 % costs the live entries ₹75–100k at the portfolio level —
trailing exits go from 216 to 315 but the extra ones are winners shaken out early (a 2 %
trail at +3 % exits on ordinary 15m noise), and the pattern-top scale-out, which pays
₹300k in the baseline, is starved because the trail fires first. Dropping the scale-out
recovers some of that (₹397k → ₹424k) but stays ₹74k below baseline. The entry × exit
interaction the hypothesis predicted appears only on ATHERENERG standalone
(swing beats live under the loose exit, ₹31.5k vs ₹27.0k); at the portfolio level the
swing entries are worse under every exit stack tested. Stale losses are unchanged across
all six runs (≈ −₹220k tier-1, ≈ −₹220k re-arm), so the loose trail does not rescue the
shallow-dip entries either — they never reach +3 %.

Do not enable `profit_pct: 3` at 15m. The 7 % arm / 2 % trail / 50 % scale-out stack stays.

## 10. Next step — from here

The identification question is answered (feature vector, not labels or threshold) and the
obvious fix is falsified on P&L (§8). If the shallow-swing recall is ever to pay, the
change has to be on the exit side (an exit stack that tolerates 2–3 % swings) or in the
label target (train on dips that *bounced ≥ X %*, i.e. `forward_label`, re-examined with
swing features) — not in the entry detector alone. The lab (`scripts/lab/export_stock.py`,
real-stock scenarios in `scripts/extrema_lab.py`) supports the same hand-label loop for any
watchlist name.

Scratch: `/private/tmp/claude-502/…/scratchpad/ather/` (scores.csv, retrains.pkl,
episodes.csv, dips3.csv, X_all7.npy, ablate*.log).
