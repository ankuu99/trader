# Stock Qualification — NSE:CGPOWER — 2026-08-08

## Verdict: **FIT**
Range-bound, high confidence, STRONG fundamentals, no material red flags. The one scary
headline ("auditor resigns", 30 Jul) is benign on inspection — mandatory rotation to align
with parent TII. Quant and qualitative agree; the live losses are a chop-execution problem,
not a structural one.

## Structural guard (quant)
- Verdict: **RANGE_BOUND** (confidence high, 371 days history)
- Drawdown from peak: −10.0% (last 879.0 vs peak 976.5) | 65.6% above period low
- Trailing returns: 1m −3.5% | 3m +0.6% | 6m +44.5% | 12m +33.1%
- Reading: **not a downtrend.** The July grind from ~950 to ~830 that produced six losing
  live round-trips was a ~12% pullback inside a wide range, already recovered to 879. Flat
  over 3m with large swings inside = high-amplitude chop, which is the regime that generates
  many entries and few follow-throughs.

## Fundamental panel (Step 4)
- Verdict: **STRONG** | quality_score 1.0 | source fvm.db
- Red flags: none
- Positives: profit +49% YoY and accelerating, revenue +22%, margin expansion, ROCE 21.5%,
  D/E 0.00, CFO/NP 0.67, no promoter pledge
- Snapshot (2026-07-03): D=45 V=23 M=60, Piotroski 4/9, pledge 0.0%, MF+FII QoQ −0.01pp,
  "Expensive Rocket"
- Note: richly valued (EV/EBITDA 54) — caps upside, less critical for dip-buying
- Reading: quality supports dip recovery. Low Durability (45) and Valuation (23) are the
  caveats — an expensive name derates faster on any miss.

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Q1 FY27 results | Standalone sales +16% to ₹3,061 cr; PBT +27% to ₹487 cr; EBITDA margin 16.9% vs 15.4%. Consolidated PAT ₹308–313 cr, +15.5% YoY | 2026-07-25 | 🟢 |
| Order book | Unexecuted backlog ₹17,333 cr, **+45% YoY** | 2026-06-30 | 🟢 |
| Filings — auditor | S R B C & Co LLP resigning eff. 14 Aug 2026 — **to align with parent TII's mandatory rotation under s.139**, not a dispute | 2026-07-30 | 🟢 (benign) |
| Segment | Power Systems sales +31%, PBIT margin 23.1% (+209bps); Industrial +6% | 2026-07-25 | 🟢 |
| New capacity | CG Semi OSAT facility, Sanand — commercial production began | 2026-07-04 | 🟡 execution/capex risk |
| Governance — history | SEBI concluded the 2019-20 Avantha fund-diversion case: Thapar barred 5y + ₹10 cr fine, 11 entities, ₹30.15 cr total. **Former** management; company now Murugappa/TII-owned | concluded | 🟢 (resolved, historical) |
| Credit rating | No 2026 rating action found for CGPOWER specifically; sector credit ratios improved (ICRA FY26 credit ratio 3.1x) | — | ⚪ no signal |

## Reading of the live divergence
8 live round-trips, 2 wins, −₹4,568 against a same-window backtest of 20 trades for ₹389 net.
Neither the business nor the trend explains this. What does: CGPOWER is the **only**
underperformer with no `per_stock_params` block — it runs the global 15m config while the
rest of the watchlist has been moved to calibrated 4hour/day regimes. A 15m dip-detector in
a ±12% chop fires constantly and pays STT both ways each time. The backtest agrees it's
churn (80% WR but losers average −₹2,718).

## Recommendation
**Do not remove.** The disqualifier gate passes cleanly on every axis — this is a
structurally sound, range-bound, fundamentally strong name, i.e. exactly the LRExtrema
target profile. The problem is the timeframe regime, not the stock.

Next action: rolling-window validation (`backtest_rolling.py`, half-year windows) to test
whether 15m has ever had edge here, then a regime calibration if it hasn't. Diff any
`recommended_override` against current config before applying — the day/4hour template ships
stale `check_bars` 5/15 and would silently revert the validated stale ×2 (10/30).
