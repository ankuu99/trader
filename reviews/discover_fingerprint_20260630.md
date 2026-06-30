# Fundamental-Fingerprint Discovery — First Run (2026-06-30)

Executes `docs/FVM_Discovery_Plan.md` Steps 1–3. **Outcome: NULL at the disciplined bar
— stop here, do not build similarity scoring.** Two real, reusable findings came out of
the attempt. This is the meta-labeling guardrail working as designed, not a failure.

## What was built
- `scripts/fingerprint_label.py` — Step 1 labeller. Segment-clean winner/loser/baseline
  buckets from the NSE-wide screen CSV ∪ calibrated config names.
- `scripts/fingerprint_discover.py` — Steps 2–3. PIT factor vectors (reuses `factors.py`)
  + per-factor robust discrimination (median gap in MAD units + Mann-Whitney U, Bonferroni).

## Finding 1 (the big one): the raw screen "winners" are toxic
42 names clear the modest bar (ret≥5%, WR≥50%, trades≥3). The set is **heavily
contaminated** with exactly the names the strategy must never trade:
- **ELECTHERM** (the documented fraud-pump), **AQYLON** (FALLING_KNIFE −83% story-stock),
  **RMDRIP** (FALLING_KNIFE −73%), **TARAPUR** (illiquid microcap), plus a long tail of
  penny/story microcaps (E2E, RADAAN, TVVISION, PANACHE, TCIFINANCE, PKTEA…).
A mean-reversion backtest prints fake wins on a pump's oscillations. **A fingerprint
trained on this pool would learn the fundamentals of pumps, not quality.**
→ The labeller now splits **curated winners** (20, calibrated ∪ vetted watchlist, minus
removed — the trusted training set) from **screen-only winners** (18, untrusted, score-only).

## Finding 2: directionally coherent quality tilt, but under-powered (NULL)
Curated winners (17 with fundamentals) vs contrast (121 losers+baseline):

| factor | med_win | med_con | effect (MAD) | p | survives Bonferroni (α=0.005) |
|---|---|---|---|---|---|
| yoy_profit_growth | 0.50 | 0.11 | **1.20** | 0.042 | no |
| roce_trend | 2.72 | 0.30 | **1.62** | 0.076 | no |
| earnings_consistency | −0.23 | −0.44 | 0.82 | 0.75 | no |
| growth_acceleration | 0.068 | −0.010 | 0.51 | 0.081 | no |
| roce | 19.96 | 15.57 | 0.48 | 0.23 | no |
| cfo_to_np | 0.67 | 1.11 | −0.88 | 0.18 | no |
| debt_to_equity | 0.10 | 0.07 | 0.33 | 0.87 | no |
| interest_coverage | 10.3 | 17.5 | −0.57 | 0.53 | no |

Winners **do** lean toward the two-sided thesis — higher profit growth, faster-rising
ROCE, more consistent earnings (CUPID-style quality compounders). But at N=17 and
Bonferroni over 10 factors, **nothing clears the bar**. The strongest single factor
(yoy_profit_growth, p=0.042) is significant only uncorrected.

## Why we STOP (and do not relax the bar)
The plan's explicit exit: no significant discriminator → keep `fund_panel` as a per-name
gate, do not ship a similarity fingerprint. Tuning the threshold to flip a p=0.042 into a
"signal" is precisely the `project_meta_labeling` / FVM-milestone-A trap ("don't tune to
flip"). Steps 4–6 (similarity scoring, OOS validation, wiring into `discover`) are **not**
executed.

## Caveats that suppress the signal (the path to a real test, not a workaround)
1. **Small N.** 17 trusted winners. The fix is *more winners*, not a looser bar:
   fill HAL/MARKSANS/MCX (blocked today by the Trendlyne 50/day quota), and grow the
   curated pool from live-confirmed names over time.
2. **PIT look-ahead.** This pass used a single 2026-06-30 snapshot for every name, not each
   winner's trade-period fundamentals (the screen CSV records no per-trade dates). A real
   verdict needs trade-period PIT — which can only *weaken* a look-ahead-inflated signal,
   reinforcing the null.
3. **Coverage-biased contrast.** The 121 contrast names are whatever the mid-cap-first
   daily ingest has fetched — skewed toward decent-quality mid/large-caps, which makes
   "winner vs contrast" harder and masks a real tilt. A random-sampled, fully-covered
   universe is the honest contrast.

## Recommendation
- **Do not build the fingerprint axis yet.** `fund_panel` remains the per-name fundamental
  gate (now also de-falsed for working-capital growers — see SKYGOLD fix).
- **Re-run when** (a) curated winners ≥ ~30 with fundamentals, (b) trade-period PIT is wired,
  (c) the universe is ~80% covered for an unbiased contrast. If the quality tilt survives
  *those* conditions, proceed to Step 4. If not, the honest conclusion is that fundamentals
  gate (dispose) but do not generate (propose) candidates for this strategy.

## Artifacts
- `reviews/fingerprint_labels.json` — the label buckets.
- `reviews/fingerprint_step3.json` — the per-factor discrimination table.
