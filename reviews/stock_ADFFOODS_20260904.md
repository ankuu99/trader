# Stock Deep Dive — ADFFOODS — 2026-09-04

## Verdict
**KEEP** (with a watch note) — positive full-period and recent-6m P&L, trailing-dominated exits,
qualify gate FIT (RANGE_BOUND + STRONG fundamentals); the watch note is that the profit is
concentrated in 2023 and 2026 with two mildly negative middle years.

## Performance
Backtest window 2023-01-01 → 2026-09-04, **4hour** TF (per-stock block), threshold 0.82.

| Period | P&L | Trades | Win rate | Avg win | Avg loss |
|--------|-----|--------|----------|---------|----------|
| Full   | **+₹13,731** | 45 | 53.3% | ₹2,875 | −₹2,632 |
| Recent 6m | +₹7,355 | 7 | 57.1% | ₹3,518 | −₹2,239 |

## Portfolio A/B evidence (2026-09-03, window 2025-01-01→2026-09-03, ₹4L baseline)
- Baseline: **+₹7.3k over 20 trades** — a modest but positive contributor.

## Year-by-year
| Year | P&L | Trades | Win rate |
|------|-----|--------|----------|
| 2023 | +₹13,974 | 15 | 60.0% |
| 2024 | −₹1,617 | 6 | 50.0% |
| 2025 | −₹6,305 | 10 | 40.0% |
| 2026 | +₹7,680 | 14 | 57.1% |

Profit concentration: 2023 + 2026 carry the name; 2024–2025 were mildly negative (the 2025-H1
correction cluster: Jan-2025 stale chain −₹9.4k plus a −₹6.1k timeout). 2026 has recovered
strongly (Apr–Jul: four consecutive ~+₹3.5k trailing winners off the Mar bottom).

## Exit breakdown
| Reason | Trades | Total P&L | Avg P&L |
|--------|--------|-----------|---------|
| TRAILING | 18 | +₹54,280 | +₹3,016 |
| PATTERN_TOP_PARTIAL | 5 | +₹13,313 | +₹2,663 |
| STRATEGY (timeout) | 5 | −₹12,124 | −₹2,425 |
| STALE | 9 | −₹18,627 | −₹2,070 |
| STALE_REARM | 8 | −₹23,110 | −₹2,889 |

Reasonable shape: 23/45 exits are trailing/pattern-top (+₹67.6k); no SL hits and no OPEN@END.
Losses are stale/timeout exits (−₹53.9k) cutting failed dips — the win/loss sizes are nearly
symmetric (₹2.9k vs −₹2.6k), so the 53% win rate is what keeps the name net positive. Thinner
margin of safety than GESHIP: a few extra failed dips per year flips a period negative, which
is exactly what 2024–25 shows. The two most recent trades (Jul 6, Aug 4 entries) were losing
STRATEGY timeouts (−₹4.8k, −₹1.0k) — the stock has gone sideways-down since July; not yet a
pattern (recent 6m still +₹7.4k), but the first thing to check at the next review.

## Config
- In watchlist: **yes**
- Active override (aggregated 4hour-TF block):
```yaml
NSE:ADFFOODS:
  lr_extrema:
    timeframe: 4hour
    warmup_bars: 100
    lookback_bars: 400
    threshold: 0.82
    retrain_every: 2
    extrema_order: 5
    exits: {hold_bars: 40, sell_min_pct: 7.0, hard_stop: {stop_pct: 20},
            trailing: {profit_pct: 10, trail_pct: 4},
            pattern_top: {sell_threshold: 0.85, min_hold_before_exit: 2},
            stale: {check_bars: 10, min_gain_pct: 0.5}, stale_2: {check_bars: 30, min_gain_pct: -2.0}}
```

## News & context (from qualify gate — `reviews/qualify_ADFFOODS_20260904.md`)
- **Qualify verdict: FIT** — guard RANGE_BOUND (high confidence; 12m +28%, DD −16.5%), fund
  panel **STRONG 0.929** (D/E 0.01, ROCE 22.4% rising, interest coverage 103×).
- FY26: revenue +15.9%, PAT +29.8%; Q3 FY26 all-time-high quarter; AGM 2026-08-12 passed,
  ₹0.60 dividend paid; promoter pledge small and falling (4.28% → 1.26%).
- No rating actions (essentially unlevered), no SEBI/governance findings, no event window in
  the next 2 weeks.

## Replay findings
- Not run — no diagnostic trigger strong enough to warrant it: recent 6m positive, exits
  trailing-dominated, and the two recent timeout losses are within normal variance for this
  name's symmetric win/loss profile.

## Recommendation
- **Keep as-is** — do not recalibrate on two losing trades; the 4hour block at 0.82 has just
  delivered four consecutive winners in Apr–Jul 2026 and the A/B contribution is positive.
- Watch item for the next review (post Q2 FY27 results, ~Nov): if the Jul-onward sideways-down
  drift produces another 2–3 stale/timeout losses and recent-6m goes negative, escalate to
  CALIBRATE (threshold sweep inside the 4hour block per the day-TF-calibration convention) —
  this name's edge is thin enough that entry selectivity matters.
