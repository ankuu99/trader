# Stock Qualification — NSE:CEATLTD — 2026-10-15

## Verdict: **WATCH**
Basing range, not a falling knife: the −25.5% drawdown is a sector-wide, cyclical input-cost
margin squeeze (natural rubber at 20-yr highs, crude ~$105, INR weakness). Revenue is at record
highs and credit is clean (CARE AA / Positive, 0% pledge). Three soft concerns keep it at WATCH.
(1) Margins are still compressing, and management guides Q3 raw-material costs +3–3.5% QoQ.
(2) The stock gapped down after results on 2026-10-15 and now sits at the floor of its 7-month
range. (3) The fundamental panel is INSUFFICIENT (no PIT data).
Quant and qualitative views agree on "range"; neither shows structural distress.

## Structural guard (quant)
- Verdict: RANGE_BOUND (confidence high, 374 days of history)
- Drawdown from peak: −25.5% (peak close 4,302.7 in Oct 2025; last 3,206.0) | 10.4% above the period low (2,903.1)
- Trailing returns: 1m −2.3% / 3m −16.3% / 6m −11.6% / 12m −8.6%
- Price path (daily cache): spike to a 4,438 high in Oct 2025, then a step-down through Feb–Mar 2026.
  Since Mar 2026 it has held a **~3,060–3,990 range**. Monthly lows: 3,133 (Mar), 3,094 (May), 3,061 (Jun),
  3,216 (Sep), 3,187 (Oct 15 intraday). The lows are flat-to-rising and the July high was 3,986.
  The pattern is basing rather than lower lows. Breaking below ~3,060 on a closing basis would invalidate the range read.
- Reading: the range is real, but price is at its floor right now after a results-day sell-off.

## Fundamental panel (Step 4)
- Verdict: INSUFFICIENT | quality_score: n/a | source: none (not in fvm.db / Trendlyne fetch failed)
- Fallback (web): revenue grew strongly while profit fell on margin pressure:
  - Q1 FY27 (2026-07-16): revenue ₹4,318 cr, +22.4% YoY. PAT ₹4 cr, −96% YoY. EBITDA margin 8.5% vs 11%. The quarter included a one-off ~₹50 cr Sri Lanka forex loss.
  - Q2 FY27 (2026-10-14): revenue ₹4,762 cr, +26.2% YoY, a record quarter. PAT ₹112 cr vs ₹186 cr a year earlier. Consolidated EBITDA margin 9.5%. It beat estimates.
  - Gross debt rose to ₹3,240 cr from ₹3,000 cr, funding a ₹1,205 cr two-wheeler capacity capex.
- Reading: there is no distress. This is a volume-growth business going through a commodity-cycle margin trough, so dips
  should be buyable once margins stabilise. Debt is rising but modest against a ~₹17k+ cr revenue run-rate.

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Filings / results | Q2 FY27: record revenue, PAT −40% YoY, beat estimates. Stock fell −4.5% to 3,206 on 349k volume (≈10× normal). Guide: RM +3–3.5% in Q3, gross margin ≈ flat if price hikes stick | 2026-10-14/15 | 🟡 |
| Filings / results | Q1 FY27: PAT −96% (input costs + one-off ₹50 cr forex). Stock fell −9.4% intraday to 3,471 | 2026-07-16/17 | 🟡 |
| Credit rating | CARE AA (Positive) / A1+ reaffirmed. Ind-Ra AA on NCDs. No downgrade or watch-negative found | 2026-01-12 | 🟢 |
| Promoter pledge / holding | Promoter (RPG) 47.29%, pledge 0.00%, stable | Jun 2026 qtr | 🟢 |
| Governance | No auditor/CFO/ID exits. Only routine GST demand orders (₹ tens of crore, immaterial), plus a favourable customs order | 2026-09-02 (customs) | 🟢 |
| Event window | Q2 results out 10-14, earnings call 10-15. The reaction is still being digested. Next event: Q3 FY27 results ~mid-Jan 2027 | 2026-10-14 → ~10-22 | 🟡 |
| Sector | The whole tyre sector faces FY27 margin pressure: NR ₹280/kg, crude >$100, INR 86→94/USD. Peers are taking 5–15% price hikes. The pressure is cyclical, not structural decline | 2026 | 🟡 |

## Why is it down 25%?
1. **Peak was a spike**: Oct 2025 ran to 4,438 on strong Q2 FY26 results plus a margin-expansion narrative,
   helped by cheap crude averaging ~$69 in FY26.
2. **Commodity reversal**: a Middle East shock drove crude above $100 and natural rubber to 20-year highs. The INR also weakened.
   Tyre margins swung from FY26 expansion to FY27 compression.
3. **Two profit misses**: Q1 FY27 (−96% PAT) and Q2 FY27 (−40% PAT) were each followed by a sell-off. Revenue and volumes kept
   growing through both (≈10% underlying volume growth).
This is an earnings-cycle de-rating within a sector-wide trough. It is not a business, balance-sheet, or governance
breakdown, so this is not the RMDRIP falling-knife pattern. The residual risk is that the margin trough deepens through Q3,
since RM is still rising. That could push price out of the bottom of the range toward the 2,900 period low.

## Recommendation
**WATCH. Do not add yet; no new entries before ~2026-10-22.**
- Re-check after ~1 week of post-results trading:
  - If daily closes hold above ~3,060, the range floor holds and the verdict can upgrade to FIT.
  - If it closes below ~3,060, the range is breaking down. Re-run the trend guard and expect DOWNTREND.
- Backtest edge exists only at **day** TF (2025-01→2026-10: day ₹23.3k vs 4hour ₹1.3k vs 15m −₹3.3k at ₹40k slots).
  If promoted, run `/calibrate NSE:CEATLTD` for an aggregated day-TF block, setting the in-block threshold. Then paper-trade first.
- Re-run the fund panel once the Trendlyne cookie is fresh to get a PIT quality score.
- Avoid the Q3 FY27 results window (~mid-Jan 2027).
