# Stock Deep Dive — REDTAPE — 2026-09-04

## Verdict
**REMOVE** — negative in every portfolio configuration tested (−₹20.8k baseline A/B) and negative
standalone over the full period; the loss engine is structural (high churn + stale-exit losses
swamping small wins), not a regime or news problem — the stock itself qualifies FIT.

## Performance
Backtest window 2023-01-01 → 2026-09-04, 15minute TF, per-stock override active.

| Period | P&L | Trades | Win rate | Avg win | Avg loss |
|--------|-----|--------|----------|---------|----------|
| Full   | **−₹11,989** | 212 | 67.0% | ₹809 | −₹1,812 |
| Recent 6m | +₹3,711 | 33 | 81.8% | ₹724 | −₹2,640 |

The recent-6m positive is thin and fragile: May 2026 (+₹6.5k) carries it; Jun/Aug/Sep are all
negative (−₹2.3k / −₹2.2k / −₹1.5k). Win rate 67–82% with avg loss 2.2–3.6× avg win is the
classic churn signature — many tiny scale-out wins, a steady drip of large stale losses.

## Portfolio A/B evidence (2026-09-03, window 2025-01-01→2026-09-03, ₹4L baseline)
- Baseline: REDTAPE contributes **−₹20.8k over 103 trades**
- All-15m variant: −₹21.5k
- ₹5L capital: −₹25.6k (more capital → more losses, unlike GESHIP which doubled its profit)
- Negative in *every* configuration tested — no capital level or TF mix rescues it.

## Year-by-year
| Year | P&L | Trades | Win rate |
|------|-----|--------|----------|
| 2023 | −₹4,901 | 20 | 60.0% |
| 2024 | +₹11,748 | 90 | 73.3% |
| 2025 | **−₹27,989** | 57 | 49.1% |
| 2026 | +₹9,153 | 45 | 80.0% |

One good year (2024) bracketed by losses; 2025 alone erased 2024 2.4× over. Net of the four
years: negative. The 2026 recovery does not offset the portfolio-level A/B, which is negative
even over the 2025–2026 window that contains it.

## Exit breakdown
| Reason | Trades | Total P&L | Avg P&L |
|--------|--------|-----------|---------|
| PATTERN_TOP_PARTIAL | 65 | +₹50,425 | +₹776 |
| TRAILING | 42 | +₹36,496 | +₹869 |
| TRAILING_EOD_CLOSE | 33 | +₹26,831 | +₹813 |
| STRATEGY (timeout) | 11 | −₹11,099 | −₹1,009 |
| STALE | 32 | −₹48,890 | −₹1,528 |
| STALE_REARM | 29 | **−₹65,753** | −₹2,267 |

Unhealthy shape: the two stale buckets (61 trades, **−₹114.6k**) exceed the entire winning side
(140 trades, +₹113.8k). The stale exits are doing their job — cutting dead positions — but the
model keeps buying dips that go nowhere on this name, and at 15m cadence it does so ~60 times a
year. This is entry-quality failure at high frequency, not an exit-tuning problem.

## Config
- In watchlist: **yes**
- Active override:
```yaml
NSE:REDTAPE:
  lr_extrema:
    threshold: 0.88
    forward_label:
      enabled: true
      min_return_pct: 1.0
```
(15minute base TF; global params otherwise.)

## News & context (from qualify gate — `reviews/qualify_REDTAPE_20260904.md`)
- **Qualify verdict: FIT** — trend guard RANGE_BOUND (high confidence; 12m −3.2%, DD −28.5%
  from peak), fund panel **STRONG 1.00** (ROCE 29.6%, D/E 0.38, zero pledge, profit accelerating).
- FY26 results strong (revenue +19.6%, PAT +32%); ₹2 dividend; AGM 2026-08-25 passed cleanly.
- CRISIL A / Positive outlook (Aug 2024, no downgrade since); no SEBI/governance issues.
- **The disagreement is the finding**: a fundamentally sound, range-bound stock on which the
  strategy still loses — the edge simply isn't there on this name's 15m microstructure.

## Replay findings
- Not run. The exit-reason forensic already isolates the failure mode (stale-dominated losses
  from over-frequent dip entries), and the removal case rests on the portfolio A/Bs, which no
  per-candle diagnosis can overturn. A replay would only be warranted if attempting a day-TF
  re-qualification later.

## Recommendation
- **Remove NSE:REDTAPE from the watchlist** (config.yaml `watchlist` + drop its
  `per_stock_params` block). Requires user confirmation — not applied.
- Do NOT re-calibrate at 15m: threshold 0.88 + forward_label 1.0 is already the calibrated
  override and it still loses; the A/B shows no configuration works.
- Optional future path: re-screen at day TF via `/calibrate` only if a later discovery run
  surfaces it again — fundamentals (STRONG) mean the name isn't toxic, just a bad 15m fit.
