# Watchlist Review — 2026-07-28

Backtest window: 2023-01-01 → 2026-07-27 (full), 2026-01-29 → 2026-07-27 (recent 6m).
Per-stock params = config.yaml globals deep-merged with `per_stock_params`.

## Portfolio Summary
| Metric | Value |
|--------|-------|
| Full period P&L | ₹850,119 |
| Return | 212.5% |
| Trades | 1,288 |
| Win rate | 71.5% |
| Max drawdown | ₹130,841 |
| Recent 6m P&L | ₹243,779 (259 trades) |
| Stocks profitable (recent) | 21/23 (2 had zero signals) |

Portfolio health is strong and broadening — **21 of 21 stocks that traded in the last
6 months were profitable**, and 19 of 23 carry an `improving` trend. The issues below are
individual-name hygiene, not a systemic problem.

## Gate coverage note
`fund_panel.py` returned `INSUFFICIENT` for 12 of 23 names (small-caps not in `fvm.db`,
auto-fetch blocked by a stale `TRENDLYNE_COOKIE`). Those rows fall back to the trend guard
plus qualitative search. Refreshing the cookie and re-running would tighten this review.
No stock anywhere in the watchlist tripped `FALLING_KNIFE` or `DOWNTREND`.

## Recommendations

### ✅ KEEP
| Stock | Full P&L | Recent P&L | Trend | WR | Guard | Fund | Gate | News |
|-------|----------|------------|-------|-----|-------|------|------|------|
| NSE:CUPID | ₹123,677 | ₹24,162 | improving | 66.0% | SPIKE | OK 0.79 | WATCH | FY26 PAT +165%, pledge cut 36%→20%; parabolic |
| NSE:ENGINERSIN | ₹90,741 | ₹15,491 | improving | 85.7% | RANGE_BOUND | n/a | — | clean |
| NSE:CGPOWER | ₹65,301 | ₹15,961 | improving | 76.7% | RANGE_BOUND | STRONG 1.00 | — | clean |
| NSE:CUMMINSIND | ₹64,364 | ₹13,749 | improving | 75.9% | UPTREND | n/a | — | clean |
| NSE:STYLAMIND | ₹57,939 | ₹8,566 | stable | 70.8% | UPTREND | n/a | — | clean |
| NSE:RADICO | ₹56,387 | ₹16,126 | improving | 65.5% | UPTREND | STRONG 1.00 | FIT | quality uptrend — dips mean-revert (CUPID case) |
| NSE:TIPSMUSIC | ₹46,915 | ₹12,678 | improving | 73.1% | RANGE_BOUND | n/a | — | ideal MR profile |
| NSE:MAYURUNIQ | ₹32,152 | ₹13,872 | improving | 60.0% | RANGE_BOUND | n/a | — | clean |
| NSE:ACMESOLAR | ₹28,246 | ₹6,514 | improving | 62.5% | RANGE_BOUND | STRONG 0.71 | — | clean |
| NSE:CHENNPETRO | ₹21,793 | ₹3,790 | improving | 60.6% | UPTREND | n/a | — | clean |
| NSE:TVSMOTOR | ₹21,599 | ₹6,102 | improving | 71.6% | RANGE_BOUND | STRONG 1.00 | FIT | clean |
| NSE:ADFFOODS | ₹8,088 | ₹12,704 | improving | 54.3% | RANGE_BOUND | n/a | — | recent >> full — regime turned favourable |
| NSE:QUESS | ₹2,683 | ₹26,953 | improving | 66.7% | RANGE_BOUND | STRONG 0.86 | — | best recent performer (51 trades, 86% WR) |

### 👀 WATCH
| Stock | Full P&L | Recent P&L | Trend | WR | Guard | Fund | Gate | Concern |
|-------|----------|------------|-------|-----|-------|------|------|---------|
| NSE:THANGAMAYL | ₹112,791 | ₹18,218 | improving | 74.1% | **SPIKE** | n/a | WATCH | +283% 12m, +92% 3m — parabolic. Earnings-backed (Q4 PAT ₹143cr vs ₹31cr, SSS +38%), so not a pump, but a momentum break would hit the largest P&L contributor hardest |
| NSE:ATHERENERG | ₹82,712 | ₹6,390 | stable | 79.6% | UPTREND | **DISTRESS 0.57** | WATCH | Panel flags interest cover −3.1× and negative CFO — structural for a pre-profit EV maker, not fresh deterioration (FY26 income +66%, AGM +116%, D/E 0.20, no pledge). **Q1 FY27 results 2026-08-03** — event window |
| NSE:KPL | ₹28,552 | ₹15,345 | improving | 92.3% | SPIKE (low conf) | n/a | WATCH | Only 68 days of guard history; +67% 3m. Kwality Pharma fundamentals strong (Q4 PAT +75%). Trading beautifully (92% WR) but structurally unproven |
| NSE:IPCALAB | ₹5,952 | ₹9,686 | improving | 75.0% | RANGE_BOUND | STRONG 1.00 | — | Sparse: 4 full-period trades. Recent 6/6m at 83% WR is encouraging — let it accumulate history |
| NSE:SCHAEFFLER | ₹3,621 | ₹5,563 | improving | 50.0% | RANGE_BOUND | n/a | — | Sparse: 2 full trades, 2 recent. Ideal MR chart (12m +0.3%) but almost no signal flow |
| NSE:M&MFIN | ₹2,234 | ₹4,360 | improving | 100% | UPTREND | STRONG 0.75 | — | Sparse: 1 full trade. Financial — leverage flags correctly suppressed |

### 🔧 CALIBRATE
| Stock | Full P&L | Recent P&L | Trend | WR | Guard | Fund | Gate | Action |
|-------|----------|------------|-------|-----|-------|------|------|--------|
| NSE:REDTAPE | **−₹3,245** | ₹3,385 | improving | 68.9% | RANGE_BOUND | n/a | WATCH | 183 trades for a net loss = **churn**: 68.9% WR with costs eating the edge. Raise `threshold` / widen `profit_pct` to cut trade count, or remove. Governance caveat: auditor Emphasis-of-Matter on Sept-2025 Income Tax search (dated, and FY26 revenue +26% / NI +42% since) |
| NSE:GESHIP | ₹2,214 | ₹0 | declining | 100% | UPTREND | n/a | — | **Zero signals in 6 months**, 1 trade lifetime. UPTREND = weak mean-reversion fit. Calibrate or drop; no red flags (fleet at 41 vessels) |
| NSE:INDHOTEL | ₹4,609 | ₹0 | declining | 100% | RANGE_BOUND | n/a | — | **Zero signals in 6 months**, 1 trade lifetime — yet the chart is textbook range-bound (12m −2.7%, −12.9% off peak). Params are too tight for this name. The pending 30-Jun AGM re-check is now resolved: AGM held, ₹3.25 dividend, no red flags |

### ❌ REMOVE
| Stock | Full P&L | Recent P&L | Trend | Guard | Fund | Gate | Reason |
|-------|----------|------------|-------|-------|------|------|--------|
| NSE:SKYGOLD | **−₹9,204** | ₹4,164 | improving | **SPIKE** | OK 0.79 | **AVOID** | Worst full-period P&L on the list at a **28.6% win rate** over 7 trades. Guard shows a parabolic move (+34.6% 1m, +105.7% 6m) — momentum, not oscillation. Decisive: **₹10.7 cr fraud loss at a subsidiary, discovered 2026-07-15** — a live governance red flag, 13 days old. Recent +₹4,164 is 2 trades = noise |

(`Guard` = trend_guard structural verdict; `Fund` = fund_panel verdict + quality_score;
`Gate` = `qualify` verdict where the full gate was run. `n/a` = panel INSUFFICIENT.)

## Quant vs. qualitative disagreements (the informative cases)
1. **SKYGOLD** — recent P&L is positive and the trend reads `improving`, but that is 2 trades
   against a −₹9.2k / 28.6%-WR record, a parabolic chart, and a fresh subsidiary fraud.
   Qualitative wins: remove.
2. **THANGAMAYL** — the single best structural mismatch: `SPIKE` says "momentum, weak MR fit",
   yet it is the #2 lifetime earner (₹112.8k over 201 trades). The strategy is profitably
   buying dips inside a strong uptrend. Keep, but it is the largest single-name regime risk.
3. **ATHERENERG** — `DISTRESS` panel on a stock with ₹82.7k lifetime P&L and 79.6% WR. The
   flags are pre-profitability artifacts, not decline. Downgraded to WATCH rather than
   REMOVE, with an entry-caution window around the Aug-3 results.
4. **REDTAPE** — the only name where high trade count and a decent win rate still lose money.
   A cost/churn problem, which is a calibration fix, not a stock-quality one.

## New Candidates
None proposed this cycle — no fresh screen was run. If capacity is wanted after the SKYGOLD
removal, run `/discover` rather than adding from news, and note that
`project_fingerprint_discovery_null` warns raw screen winners are toxic without the
qualitative gate.

## Calibration outcomes (run 2026-07-28)

Full regime comparison (15minute global vs 4hour template vs day template vs the stock's
existing block), then a threshold sweep *inside* the winning regime.

| Stock | Winning regime | Result | Action taken |
|-------|----------------|--------|--------------|
| **NSE:GESHIP** | `current` (day block) — ₹50.2k/40t/80% beat 4hour ₹49.3k and 15m ₹19.1k | In-regime sweep: **0.82 → ₹56,664 / 39t / 84.6%** (+₹6,484 vs 0.80 baseline). 0.80 neighbour ₹50.2k; cliff at 0.85 (₹26.5k) | ✅ **APPLIED** — `threshold` 0.80 → 0.82 |
| **NSE:INDHOTEL** | `day` @0.88 on the template (₹32.6k/18t/88.9%) vs current ₹25.0k/14t/92.9% | In-regime sweep (with the validated `stale` 10/30): threshold is **flat** — best 0.85 = ₹25,578 (+₹573, −11.9pp WR), 0.88 = −₹110, 0.90 = baseline | ❌ **NO CHANGE** — see note below |
| **NSE:REDTAPE** | `4hour` @0.90, but only **+₹621 / 10t / 50% WR** | Every other leg negative: 15m −₹2.7k, day −₹2.9k, current −₹3.7k. The lone positive is a knife-edge — neighbours 0.88 = −₹8.5k, 0.85 = −₹11.0k. Also carries a **coverage warning** (cache starts 2023-08-11, warm-up needs ~2021-01) so trade counts are understated | ⚠️ **NO CHANGE — needs your decision** |

### Why INDHOTEL was left alone (important)
The template's `recommended_override` appeared to beat the current block by ₹7.6k — but the
template ships `stale.check_bars: 5` / `stale_2: 15`, i.e. it would **revert the stale-runway ×2
change validated 4/4 half-year windows and applied 2026-07-06**. Re-running the sweep inside the
existing block showed the threshold itself is worth nothing (+₹573 ≈ noise, at a 12pp win-rate
cost). So the entire apparent gain was the stale revert, not calibration. Reverting a
portfolio-wide validated finding for one stock is exactly the per-stock overfit to avoid, so
nothing was changed. INDHOTEL's zero-signals-in-6m is a regime artifact (it trades 14–25 times
over the full window), not miscalibration.

### REDTAPE — open decision
There is **no viable calibration**: the best leg across all four regimes is +₹621 over 10 trades
at a 50% win rate, sitting on a knife-edge with deeply negative neighbours. Combined with the
full-period −₹3.2k over 183 trades, the honest read is that REDTAPE has no edge for this
strategy. Recommended action is **removal**, but that was outside what you approved, so it has
been **left in the watchlist unchanged** pending your call.

## Suggested Actions
- [x] Remove: `NSE:SKYGOLD` — done (watchlist entry commented; `per_stock_params` block left
      dormant and inert)
- [x] Calibrate `NSE:GESHIP` — done, `threshold` 0.80 → 0.82 applied
- [x] Calibrate `NSE:INDHOTEL` — done, no change justified
- [ ] **Decide on `NSE:REDTAPE`** — no viable calibration; recommend removal
- [ ] Hold fresh entries in `NSE:ATHERENERG` around the 2026-08-03 Q1 results
- [ ] Refresh `TRENDLYNE_COOKIE` and re-run `fund_panel.py` for the 12 `INSUFFICIENT` names
- [ ] Re-check `NSE:KPL` guard once it has >6 months of history (currently low confidence)
- [ ] Optional: fetch deeper 15m history for REDTAPE to clear its coverage warning and re-test
