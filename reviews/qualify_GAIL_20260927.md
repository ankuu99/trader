# Stock Qualification — NSE:GAIL — 2026-09-27

## Verdict: **FIT** (structurally) — with a thin-edge caveat
Range-bound at high confidence, no disqualifier anywhere (Maharatna PSU, AAA reaffirmed twice
*during* the 2026 Hormuz LNG shock, no pledge, no governance noise, no event window). Quant and
qualitative agree. The one soft concern is economic, not structural: the standalone 15m backtest
(77 trades, 66% WR, ₹9.3k on ₹6L, 2025-01→2026-08) is ~₹120/trade ≈ 0.3% per ₹40k slot — barely
above the 0.22% CNC round-trip cost. GAIL qualifies for *calibration*, not for the watchlist as-is.

Context: fresh Nifty 500 discovery scan flagged RANGE_BOUND, ER 0.015, turnover ₹144 Cr/day,
6m +27%, 12m −2%, dd −11%.

## Structural guard (quant)
`python scripts/trend_guard.py --symbol NSE:GAIL --fetch --json` (as of 2026-09-25, 371 days)
- Verdict: **RANGE_BOUND** (confidence **high**)
- Drawdown from peak: −11.0% (peak close 194.04, low close 135.4, last 172.7 — mid-range, 27.5% above low)
- Trailing returns: 1m −1.0% | 3m +0.3% | 6m +27.5% | 12m −1.6%
- Reading: the 12m round-trip is flat; the +27% 6m leg is the V-recovery off the 23-Mar-2026 shock
  low (₹134.36, Qatar/Petronet force majeure), and the last quarter has been a genuine sideways
  oscillation (3m +0.3%, 1m −1%). Liquidity is not a concern (Nifty 50, ₹144 Cr/day).
  Caveat: part of the 2026 range was *headline-driven* (−30% into Mar-23, +8% gap on the 8-Apr
  ceasefire headline) — the Hormuz crisis is still live (Sep-2026), so gap risk on geopolitical
  news is above normal for a large-cap PSU.

## Fundamental panel (Step 4)
- Verdict: **INSUFFICIENT** | quality_score: n/a | source: none
  (`fund_panel.py` → "not in fvm.db and could not fetch (not in Trendlyne master, or stale
  TRENDLYNE_COOKIE)". GAIL is a Nifty 50 name, so this is almost certainly a stale cookie — worth
  refreshing before the next qualify run.)
- Web fallback (Q1 FY27, board-approved 31-Jul-2026): standalone revenue ₹38,982 Cr, PAT ₹4,292 Cr,
  adjusted PAT +127% YoY (LPG/gas-marketing windfall from the price spike — partly cyclical, not
  run-rate). Transmission 122 mmscmd, FY27 guidance raised to 123 (from 119). PATA petchem at 100%
  utilisation but still loss-making at $10.5/MMBtu landed gas; breakeven guided for FY27.
  Fitch (11-Mar-2026, no rating action): leverage could rise to 2.5–3.0x (vs 1.8x) under a prolonged
  Hormuz closure; ratings "supported by strong linkages to the Indian government".
- Ownership: GoI 51.52% (31-Mar-2026), promoters 51.8% (Jun-2026 qtr); FII 15%, DII 26.7%, public 6.5%.
  Sovereign promoter → no pledge, no promoter-selling risk.
- Red flags: none | Positives: sovereign ownership, AAA balance sheet, regulated transmission cash flows
- Reading: not a falling-knife candidate — a dip here is buyable on balance-sheet grounds; the
  earnings swing factor (LNG price, petchem) drives oscillation rather than secular decline.

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Filings/announcements | Q1 FY27 results + earnings call (31-Jul); final dividend ₹0.50/sh, record date 2-Sep-2026 (passed); 42nd AGM held. No delayed results, no qualified opinion. | 2026-07-31 / 2026-09-02 | 🟢 |
| Board / CFO | Director (Finance) & CFO R K Jain superannuated 30-Jun-2026 → Satish Kumar Sinha (30+ yrs at GAIL) from 1-Jul-2026 — scheduled retirement, not a resignation. Four independent directors ceased 28-Mar-2026 on tenure completion (routine PSU ID-vacancy pattern). No auditor change found. | 2026-07-01 / 2026-03-28 | 🟢 |
| Credit rating | ICRA **reaffirmed** `[ICRA]AAA (Stable)/[ICRA]A1+` (rationale explicitly discusses the 28-Feb-2026 Iran conflict and Strait-of-Hormuz LNG disruption; cites sovereign financial flexibility). CARE press release (reaffirmation) 6-Aug-2026. Fitch Mar-2026 comment flagged leverage headroom but took no action. No downgrade / watch anywhere. | 2026-04-28 / 2026-08-06 | 🟢 |
| Promoter pledge / holding | GoI ~51.5% stable; no pledge possible; no OFS announced. | 2026-06 qtr | 🟢 |
| Event window | Dividend record date already passed (2-Sep). Q2 FY27 results expected ~2nd week Nov (Q2 FY26 was 11-Nov-2025) — outside the 2-week window. GAIL Gas ₹3,000 Cr IPO targeted by Mar-2027, no DRHP yet — value-unlock narrative, not a candle-distorting event. | — | 🟢 |
| Governance / sector | No SEBI action, fraud, or investigation found for GAIL in 2026. Sector: Hormuz crisis ongoing — Asian spot LNG $18–22/MMBtu, Qatar (>40% of India's LNG) constrained, contracted Petronet supply went to zero on 4-Mar-2026; India LNG imports nonetheless at a 6-yr high in Aug-2026. Downstream margin pressure flagged for Sep onward; CGD/fertiliser demand resilient; unified tariff ₹80.97/MMBtu supportive for transmission. Brokerages: Emkay upgrade to Buy TP ₹200 (24-Sep-2026), UBS Buy TP ₹215. | 2026-09 | 🟡 (exogenous headline risk, both directions) |

## Recommendation
**Run `/calibrate NSE:GAIL` before anything else** — the structure is clean but the 15m edge is
marginal (0.3%/trade vs 0.22% cost; 77 trades in 20 months reads as churn on a low-vol large-cap).
Test the 4hour/day template blocks: a Nifty-50 PSU may not reach `profit_pct` inside 15m
`hold_bars` often enough, and slow-TF blocks are where this book's winners live. Add to paper only
if calibration clears a meaningful ₹/trade bar (not just positive P&L) on both 2023+ and 2025+
windows. Single most important reason: **nothing disqualifies GAIL — the question is whether the
oscillation is wide enough to pay for itself, and only calibration answers that.**
Re-check the qualitative side before the ~10-Nov Q2 FY27 results and if a Hormuz headline moves
the stock >5% in a day (headline gaps are the one regime the model reads badly).

### Sources (timestamped)
- trend_guard.py run 2026-09-27 (data to 2026-09-25); fund_panel.py run 2026-09-27 (INSUFFICIENT)
- ICRA rationale 28-Apr-2026: https://www.icra.in/Rating/GetRationalReportFilePdf?id=142680
- CARE press release 6-Aug-2026: https://www.careratings.com/upload/CompanyFiles/PR/202608140846_GAIL_India_Limited.pdf
- Fitch comment 11-Mar-2026 (via multibagg.ai); BS "cessation of directors" 28-Mar-2026; psuconnect / indianmasterminds CFO change 1-Jul-2026
- Q1 FY27: niftytrader.in, indianmasterminds.com, GuruFocus call highlights (31-Jul-2026)
- Shareholding Jun-2026: choiceindia / groww / trendlyne pages
- Sector: Kpler 24-Jul-2026, Bloomberg 1-Sep-2026, webindia123 31-Aug-2026, S&P Global 2-Mar-2026
- Emkay upgrade: BusinessToday 24-Sep-2026; GAIL Gas IPO: discoveryalert.com Sep-2026
