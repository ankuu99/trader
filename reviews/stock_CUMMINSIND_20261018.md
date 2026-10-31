# Stock Deep Dive — CUMMINSIND — 2026-10-18

Prompt: owner flagged "this is on continuous downfall".

## Verdict
**WATCH (keep trading, no config change)**. The fall is real: −23.6% from the late-May peak, 3m −15%.
It is a de-rating pullback in a STRONG, debt-free business that is still +16% over 12 months, not a
secular decline. The day-TF exit stack is handling it as designed. Four rounds into the slide were each
cut by STALE / STALE_REARM for a combined ≈ −₹6.2k. The ₹43.6k full-period edge is intact. Re-check after
Q2 FY27 results (~early-mid Nov).

## Performance
(Backtest 2023-01-01 → 2026-10-18, current config incl. scale-in + loss re-entry block; add-on lots count as separate trades.)

| Period | P&L | Trades | Win rate | Avg win | Avg loss |
|--------|-----|--------|----------|---------|----------|
| Full   | ₹43,600 | 65 | 60.0% | ₹1,743 | ₹−938 |
| Recent 6m (since 2026-04-21) | ₹937 | 13 | 30.8% | ₹1,681 | ₹−643 |

Recent months: May +₹3.8k, Jun +₹2.9k, **Jul −₹1.9k, Sep −₹2.2k, Oct −₹1.6k** (no trades in Aug closed).

## Year-by-year
| Year | P&L | Trades | Win rate |
|------|-----|--------|----------|
| 2023 | ₹10,888 | 11 | 63.6% |
| 2024 | ₹17,357 | 18 | 66.7% |
| 2025 | ₹6,841 | 12 | 75.0% |
| 2026 YTD | ₹8,514 | 24 | 45.8% |

## The decline, round by round (since the ₹6,005 peak, 2026-05-27)
| Round (parent entry) | Lots | Exit | Parent P&L | Add-on P&L | Reason |
|---|---|---|---|---|---|
| 2026-06-01 @ 5,676 | 3 | 2026-07-14 @ 5,491 | −₹1,386 | −₹518 | STALE_REARM |
| 2026-07-29 @ 5,378 | 3 | 2026-09-10 @ 5,170 | −₹1,758 | −₹900 | STALE_REARM |
| 2026-09-23 @ 5,000 | 3 | 2026-10-08 @ 4,872 | −₹1,110 | −₹420 | STALE |
| 2026-10-16 @ 4,654 | 1 | open | −₹93 | — | OPEN@END |
| **Total** | | | **−₹4,347** | **−₹1,838** | ≈ −₹6.2k |

Each round lost 2–4% on the parent and was out within 2–6 weeks. Each re-entry came 2–5% below the previous
exit, so the stale brake avoided riding the whole slide (−23.6% peak-to-now) with one lot. Add-ons amplified each losing round by ~40%. That is the
known cost of scale-in in corrections (2020Q1 counterfactual), and the budget cap and geometric decay keep it bounded.

## Exit breakdown
| Reason | Trades | Total P&L | Avg P&L |
|--------|--------|-----------|---------|
| TRAILING | 21 | ₹35,979 | ₹1,713 |
| PATTERN_TOP_PARTIAL | 9 | ₹20,987 | ₹2,332 |
| STRATEGY (hold timeout) | 8 | ₹8,502 | ₹1,063 |
| STALE | 17 | ₹−11,687 | ₹−687 |
| STALE_REARM | 9 | ₹−10,088 | ₹−1,121 |
| OPEN@END | 1 | ₹−93 | ₹−93 |

Healthy: trailing and pattern-top earn +₹57k, stale exits cost −₹22k at small average size, and there are zero
hard-stop (SL) exits. No SL or OPEN@END dominance, so a replay is not warranted.

## Config
- In watchlist: yes
- Active override (day timeframe):
```yaml
NSE:CUMMINSIND:
  lr_extrema:
    timeframe: day
    warmup_bars: 100
    lookback_bars: 400
    threshold: 0.8
    retrain_every: 1
    extrema_order: 5
    exits:
      hold_bars: 40
      sell_min_pct: 7.0
      hard_stop: {stop_pct: 20}
      trailing: {profit_pct: 10, trail_pct: 4, force_close_time: null}
      pattern_top: {sell_threshold: 0.85, min_hold_before_exit: 2}
      stale: {check_bars: 10, min_gain_pct: 0.5}
      stale_2: {check_bars: 30, min_gain_pct: -2.0}
```
- Live note: CUMMINSIND is F&O-eligible, so its day-TF decisions died in the 15:15 CAS window until the
  pre-auction flush shipped (release-20261012). Live history before that date is not representative.

## News & context
(Full gate: `reviews/qualify_CUMMINSIND_20261018.md`, verdict **WATCH**)
- Trend guard **RANGE_BOUND** (high confidence): −23.6% from peak, 12m +16.4%, 68% above period low.
- Fund panel **STRONG** 0.714: ROCE 37.6%, D/E 0, revenue +18%, no pledge, no red flags. Profit growth −8%
  and OPM trend negative.
- Q1 FY27 (2026-08-05): revenue +18%, standalone PAT ₹543 cr vs ₹590 cr, EBITDA margin ~18% vs 21.5% on commodity
  inflation; price hikes taken in Q2. Data centres are 40% of powergen, and demand is intact.
- MD Shveta Arya resigned effective 2026-08-31; no successor named yet.
- Oct slide (Oct 8 −2.2%, Oct 15 −3.3%) attributed to sector weakness and technicals; no company-specific trigger.
- No rating, SEBI or accounting issues; only routine tax-dispute disclosures.
- Probable cause of the "downfall": de-rating of an expensive name (EV/EBITDA 37) on margin compression plus the
  leadership gap, after a ~120% run.

## Replay findings
Not run. Exits are trailing/pattern-top dominated and the losing rounds are clean stale exits.

## Recommendation
- **Keep as-is.** Removing it now would lock in the drawdown-era losses and forfeit the recovery leg. This is the same
  lesson as the falsified loss-block and loss-budget studies: rebuys after a loss stack are where the edge lives,
  and knife-state entries were the best bucket.
- **Don't recalibrate on a 4-month slide.** Threshold or stale tuning on the current window would curve-fit the decline.
- **Re-check ~mid-Nov 2026** after Q2 FY27 results and any MD appointment. Escalate to REMOVE if (a) EBITDA margin
  compresses again despite the Q2 price hikes **and** (b) `trend_guard` flips to DOWNTREND / FALLING_KNIFE.
- Optional: avoid fresh entries around the results day (event-window distortion); there is no mechanism for this today.
