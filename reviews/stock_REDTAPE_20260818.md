# Stock Deep Dive — REDTAPE — 2026-08-18

## Verdict
**KEEP** — yesterday's "negative in every config" calibration verdict was a window artifact:
the 2025-01→now window is dominated by 2025's −₹28.0k correction year. 2024 (+₹11.7k) and
2026 YTD (+₹10.7k @ 82.9% WR) are solidly profitable on current params, the recent 6 months
are +₹7.7k @ 87% WR, and the stock passes every structural/fundamental/qualitative gate
(qualify verdict: **FIT**). Do not remove; do not blindly re-threshold off the 20-month window.

## Performance (full backtest 2023-01 → 2026-08-18, current params)
| Period | P&L | Trades | Win rate | Avg win | Avg loss |
|--------|-----|--------|----------|---------|----------|
| Full   | −₹10,472 | 208 | 67.3% | ₹813 | −₹1,828 |
| Recent 6m | **+₹7,729** | 31 | **87.1%** | ₹778 | −₹3,319 |

## Year-by-year
| Year | P&L | Trades | Win rate |
|------|-----|--------|----------|
| 2023 | −₹4,916 | 20 | 60.0% |
| 2024 | +₹11,728 | 90 | 73.3% |
| 2025 | **−₹28,015** | 57 | 49.1% |
| 2026 YTD | +₹10,730 | 41 | 82.9% |

The stock's edge is regime-dependent: it makes money in normal/range years and bleeds in the
2025 correction — same shape as the portfolio overall (the stale-rearm rule was validated for
exactly this reason).

## Exit breakdown (full period)
| Reason | Trades | Total P&L | Avg P&L |
|--------|--------|-----------|---------|
| PATTERN_TOP_PARTIAL | 64 | +₹49,815 | +₹778 |
| TRAILING | 41 | +₹36,073 | +₹880 |
| TRAILING_EOD_CLOSE | 33 | +₹26,848 | +₹814 |
| STRATEGY (hold timeout) | 11 | −₹11,131 | −₹1,012 |
| STALE | 32 | −₹48,917 | −₹1,529 |
| STALE_REARM | 27 | −₹63,160 | −₹2,339 |

Healthy winner engine (+₹112.7k from trailing/pattern-top) fully offset by the stale family
(−₹112.1k) — REDTAPE's losses are concentrated where every stock's are; this is a
portfolio-wide exit-rule question (stale gates are already validated ON), not a
REDTAPE-specific defect.

## Config
- In watchlist: yes (position re-opened 2026-08-18: 340 @ 124.63)
- Active override: `threshold: 0.88`, `forward_label: {enabled: true, min_return_pct: 1.0}` (15minute)

## News & context (from qualify — full report: reviews/qualify_REDTAPE_20260818.md)
- Trend guard: RANGE_BOUND (high confidence) — ideal mean-reversion regime
- Fund panel: STRONG, quality 1.0 — FY26 PAT +32.4%, ROCE 29.6%, D/E 0.38, Piotroski 8, no pledge
- CRISIL A / Positive outlook; clean Q1 FY27 audit review; no SEBI/governance issues
- 🟡 **AGM 2026-08-25 + ₹2/share final-dividend record date — event window for the next week**

## Recommendation
1. **Keep** REDTAPE in the watchlist on current params.
2. Consider pausing fresh entries until ~Aug 26 (AGM + record-date candle distortion per
   project policy) — the currently-open position is managed by exits as usual.
3. If any calibration change is ever applied, validate it per-year (2024 and 2026 must stay
   positive), not on a single 2025-heavy window.
