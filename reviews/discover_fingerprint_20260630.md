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

## Finding 2 (UPDATED 2026-07-01): the "quality tilt" was look-ahead — robust NULL under PIT
The first pass (single 2026-06-30 snapshot) showed a directionally-coherent quality tilt that
was *almost entirely look-ahead bias*. Re-running with **trade-period PIT** (per-stock median
factor vector over within-window as-of dates 2024-07-01 … 2026-01-01, no post-window data) makes
it collapse:

| factor | today-snapshot effect (p) | trade-period PIT effect (p) |
|---|---|---|
| yoy_profit_growth | **1.20** (0.042) | 0.33 (0.75) |
| roce_trend | 1.62 (0.076) | 0.02 (0.59) |
| roce | 0.48 (0.23) | 0.01 (0.96) |

CUPID *today* reads as a 30%-ROCE rocket; during the actual 2024–25 trade window it was an
ordinary ~16% name — indistinguishable from the field. The signal was the snapshot, not the stock.

**Robustness check — winners vs LOSERS only** (same coverage origin, differ only in outcome, so
no coverage-bias alibi): still NULL. ROCE 17.1 (win) vs 16.6 (los); yoy 0.17 vs 0.11 (p=0.47);
nothing survives Bonferroni. The largest residual is opm_trend (effect 0.99, p=0.083) — weak,
unconfirmed.

**Decisive conclusion:** once look-ahead is removed, LRExtrema winners have no fundamental
fingerprint distinguishing them from losers or the broad market. The hypothesis behind Steps 4–6
is not supported. LRExtrema's edge is price-structure / mean-reversion, **orthogonal** to the
fundamental profile of the name.

Artifacts: `reviews/fingerprint_step3_pit.json` (PIT), `reviews/fingerprint_step3.json` (snapshot).

---

### Appendix — original (look-ahead) snapshot pass, kept for the record
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

## Why we STOP — and why this is now a robust verdict, not just "underpowered"
The snapshot pass *looked* like an underpowered near-miss ("get more winners"). The PIT pass
shows the near-miss was look-ahead, and the null holds even winners-vs-losers. So more winners
will **not** rescue it — the in-window fundamentals genuinely do not separate. Steps 4–6
(similarity scoring, OOS validation, wiring into `discover`) are **not** executed, and there is
no data-collection path that obviously changes this. Tuning the bar to flip a snapshot p=0.042
would have been precisely the `project_meta_labeling` / FVM-milestone-A trap ("don't tune to
flip") — the PIT pass is exactly why that discipline mattered.

## Reconciling with "IPCALAB and QUESS are doing well"
True, and consistent — but it's a GATE result, not a GENERATOR result. The curated winners
include both quality names (IPCALAB, QUESS, CUPID → STRONG) *and* fundamentally weak ones
(GAYAPROJ, ATHERENERG → DISTRESS); the losers likewise include plenty of STRONG names. So:
- **`fund_panel` as a per-name gate adds value** — it correctly flags falling knives whose dips
  won't recover (RMDRIP, GAYAPROJ), which is the two-sided thesis working on the *dispose* side.
- **Fundamental similarity as a candidate generator does not** — you cannot find new winners by
  "looks fundamentally like IPCALAB." Quality is neither necessary (GAYAPROJ/ATHERENERG won
  without it) nor sufficient (many STRONG names are losers) for LRExtrema success.
Seeing the quality survivors and inferring a generative pattern is confirmation bias; the
cross-sectional data does not support it.

## Remaining caveats (do they threaten the null? no)
1. **Small N** (17 winners). Real, but the null holds winners-vs-losers at near-zero effect on
   the core factors (ROCE 17.1 vs 16.6) — this is not a knife-edge a few more names would flip.
2. **PIT** — now addressed. The trade-period grid is the fix; it *strengthened* the null.
3. **Coverage-biased contrast** — addressed via the winners-vs-losers check (same coverage
   origin); still null. A fully-covered random universe would only add weaker-quality names,
   which can only widen a real gap — there isn't one to widen.

## Recommendation
- **Do not build the fingerprint axis (Steps 4–6). Conclusion reached, not deferred.** The
  cross-sectional data says LRExtrema winners have no in-window fundamental signature, so
  fundamental *similarity* cannot generate candidates. Discovery stays price/fit-based
  (the existing `discover` skill).
- **Keep `fund_panel` as the per-name dispose gate** in `qualify` / `watchlist-review` — that
  use is validated (correctly STRONG on CUPID/IPCALAB/QUESS, correctly DISTRESS on
  GAYAPROJ; SKYGOLD false-DISTRESS fixed). Fundamentals filter falling knives; they do not
  predict mean-reversion edge.
- **If anything is worth a future look**, it is `opm_trend` (winners' operating margins trend up
  more; effect 0.99 but p=0.083, unconfirmed) — a margin-momentum hint, not a fingerprint. Only
  worth revisiting if the curated winner pool grows substantially from live-confirmed names.

## Artifacts
- `reviews/fingerprint_labels.json` — the label buckets.
- `reviews/fingerprint_step3.json` — the per-factor discrimination table.
