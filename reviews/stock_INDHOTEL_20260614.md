# Stock Deep Dive — NSE:INDHOTEL — 2026-06-14

## Verdict
**CALIBRATE** — full-period P&L is positive (+₹5,172) but the edge has flatlined since
2025 (2023 +₹2.2k, 2024 +₹3.1k, 2025 −₹29, 2026 −₹119). The trailing edge is intact
(+₹13.8k); it's being bled out by STALE exits (−₹9.9k). Fundamentals are healthy — this
is a regime shift, not a broken stock, so recalibrate rather than remove.

## Performance
| Period | P&L | Trades | Win rate | Avg win | Avg loss |
|--------|-----|--------|----------|---------|----------|
| Full (2023-01-01→today) | +₹5,172 | 107 | 47.7% | ₹349.53 | −₹225.96 |
| Recent 6m | −₹128 | 17 | 47.1% | ₹219.80 | −₹209.60 |

R:R ≈ 1.55 (avg win / avg loss) — healthy when entries are right.

## Year-by-year
| Year | P&L | Trades | Win rate |
|------|-----|--------|----------|
| 2023 | +₹2,209 | 30 | 53.3% |
| 2024 | +₹3,111 | 33 | 45.5% |
| 2025 | −₹29 | 27 | 44.4% |
| 2026 (to date) | −₹119 | 17 | 47.1% |

Clear two-phase story: the entire profit was earned in 2023–2024 while the stock
oscillated. From 2025 onward (price correcting from the ₹875 high toward ~₹610) the
strategy treads water.

## Exit breakdown
| Reason | Trades | Total P&L | Avg P&L |
|--------|--------|-----------|---------|
| TRAILING | 39 | +₹13,841 | +₹354.89 |
| STRATEGY (hold_bars) | 16 | +₹1,231 | +₹76.93 |
| STALE | 52 | −₹9,899 | −₹190.37 |

**Diagnosis:** the trailing edge is strong and the only thing keeping the stock net
positive. But 52 of 107 trades (49%) exit STALE at −₹190 avg — these are entries that
fired on false local-minima during the downtrend and got cut by the stale timers
(20-bar/+0.5% and 100-bar/−2%). The fix is **fewer, higher-quality entries**, not exit
tuning — entries are too loose for the current choppy regime. No SL or OPEN@END exits,
so the 20% hard stop and EOD logic are not the issue.

## Config
- In watchlist: **yes** (actively traded)
- Active override:
  ```yaml
  per_stock_params:
    NSE:INDHOTEL:
      forward_label:
        enabled: true
        min_return_pct: 1.5
  ```
- Effective entry params: `threshold: 0.90`, `veto_threshold: 1.0`, `extrema_order: 10`,
  forward-labelling on at 1.5% / 150 bars.

## News & context
- **Q3 FY26**: EPS ₹6.35 (vs ₹4.09 YoY), revenue ₹29.0b (+12%), net income +55%,
  margin 31% — EPS beat estimates by 31%.
- **Q2 FY26 was soft** (EPS ₹2.00 vs ₹3.89, margin 13%) — lumpy quarter-to-quarter, but
  H2 recovered strongly.
- **Forward**: 24 analysts forecast FY26 revenue ₹98.2b (+5.6%), EPS +19% to ₹14.11;
  FY27 EPS +17% to ₹16.46. Consensus target **₹834** vs ~₹610–630 now.
- **Price**: corrected from 52-wk high ₹875 to ~₹610 — explains the strategy's 2025–26
  struggle (mean-reversion entries misfire in a sustained drawdown).
- No SEBI actions, promoter pledging, or governance flags found. Sector tailwinds intact
  (RevPAR growth 8–12% guided, rate cuts easing borrowing costs).

**Net:** fundamentals and sector are constructive; the quant decay is purely a
price-regime mismatch. Keep the name, fix the entries.

## Recommendation
**Recalibrate entries to be more selective.** The trailing edge works — the problem is
too many low-quality entries getting stale-stopped. Run `/calibrate NSE:INDHOTEL` to
grid threshold × forward_label; the "more selective" rule (higher `threshold` and/or a
higher `forward_label.min_return_pct`) should cut the STALE bleed while preserving the
TRAILING winners. Do **not** remove — fundamentals are healthy and the consensus target
implies meaningful upside if the price regime turns back to oscillating.

Optional deeper diagnostic: `/replay NSE:INDHOTEL` to confirm whether the false entries
cluster on specific P(local-min) ranges before changing params.
