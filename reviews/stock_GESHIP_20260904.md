# Stock Deep Dive — GESHIP — 2026-09-04

## Verdict
**KEEP** — profitable every calendar year (full +₹34.0k, 30 trades, 76.7% WR), healthy
trailing/pattern-top exit mix, qualify gate FIT (AAA/Stable, STRONG fundamentals), and the
portfolio A/B shows it scales with capital (+₹13.3k → +₹29.5k at ₹5L).

## Performance
Backtest window 2023-01-01 → 2026-09-04, **day** TF (per-stock block), threshold 0.82.

| Period | P&L | Trades | Win rate | Avg win | Avg loss |
|--------|-----|--------|----------|---------|----------|
| Full   | **+₹34,027** | 30 | 76.7% | ₹2,479 | −₹3,285 |
| Recent 6m | +₹8,118 | 10 | 70.0% | ₹2,373 | −₹2,831 |

## Portfolio A/B evidence (2026-09-03, window 2025-01-01→2026-09-03, ₹4L baseline)
- Baseline: **+₹13.3k over 11 trades**
- ₹5L capital: **+₹29.5k over 22 trades** — the name is capital-starved at ₹4L; doubling of
  P&L when slots free up means the day-TF entries are being crowded out, not that the edge is thin.

## Year-by-year
| Year | P&L | Trades | Win rate |
|------|-----|--------|----------|
| 2023 | +₹3,831 | 1 | 100% |
| 2024 | +₹8,453 | 10 | 70.0% |
| 2025 | +₹8,877 | 7 | 85.7% |
| 2026 | +₹12,866 | 12 | 75.0% |

Positive every year, improving in 2026. (2023 is a partial year for the day-TF model —
warmup consumes early history.)

## Exit breakdown
| Reason | Trades | Total P&L | Avg P&L |
|--------|--------|-----------|---------|
| TRAILING | 15 | +₹41,532 | +₹2,769 |
| PATTERN_TOP_PARTIAL | 7 | +₹15,000 | +₹2,143 |
| STRATEGY (timeout) | 2 | −₹743 | −₹372 |
| STALE_REARM | 1 | −₹6,037 | −₹6,037 |
| STALE | 4 | −₹15,631 | −₹3,908 |
| OPEN@END | 1 | −₹94 | −₹94 |

Healthy shape: 22 of 30 exits are trailing/pattern-top (+₹56.5k); losses are confined to 5
stale exits (−₹21.7k) doing their job on dips that failed (the Oct–Dec 2024 correction cluster
and May/Aug 2026). No SL exits at all; the single OPEN@END is the position currently open
(entered 2026-08-27 at ₹1,315.50, marked flat).

Recent-6m months Jun/Aug/Sep read slightly negative, but that is 3 stale/open trades against a
+₹12.9k 2026 total — normal give-back inside a positive year, not a decay trend.

## Config
- In watchlist: **yes**
- Active override (aggregated day-TF block):
```yaml
NSE:GESHIP:
  lr_extrema:
    timeframe: day
    warmup_bars: 100
    lookback_bars: 400
    threshold: 0.82
    retrain_every: 1
    extrema_order: 5
    exits: {hold_bars: 40, sell_min_pct: 7.0, hard_stop: {stop_pct: 20},
            trailing: {profit_pct: 10, trail_pct: 4},
            pattern_top: {sell_threshold: 0.85, min_hold_before_exit: 2},
            stale: {check_bars: 10, min_gain_pct: 0.5}, stale_2: {check_bars: 30, min_gain_pct: -2.0}}
```

## News & context (from qualify gate — `reviews/qualify_GESHIP_20260904.md`)
- **Qualify verdict: FIT** — guard UPTREND (12m +44.8%, but last 3m −7.5%: currently
  oscillating in a higher range), fund panel **STRONG 0.929** (profit +198% YoY, D/E 0.08,
  zero pledge, Piotroski 7).
- CRISIL **AAA/Stable reaffirmed** 2026-02-23; ₹450 cr NCDs redeemed in full.
- Q1 FY27 was the company's most profitable quarter ever (₹1,309 cr); 18th straight interim
  dividend; Deloitte unmodified FY26 audit opinion; the only board exit was a GoI appointment.
- Watch item: 2026 shipping-sector rate softness — tanker markets (GESHIP's exposure) expected
  resilient, but re-check the guard after Nov Q2 results.

## Replay findings
- Not run — no diagnostic trigger (win rate strong, exits healthy, no SL/OPEN@END dominance,
  every year profitable).

## Recommendation
- **Keep as-is.** No calibration needed — day-TF block at threshold 0.82 is performing.
- The ₹5L A/B doubling suggests the real constraint on this name is portfolio capital/slots,
  not params; if capital is ever raised, GESHIP is a primary beneficiary.
- Re-check at the next watchlist review after Q2 FY27 results (~Nov 2026) for a sector-cycle
  turn.
