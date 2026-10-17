# Stock Qualification — NSE:RBLBANK — 2026-10-15

## Verdict: **WATCH**
No disqualifier found. Ratings were upgraded to AAA (ICRA 2026-06-25, CareEdge 2026-07-15) after Emirates NBD (ENBD) took control, and governance is clean. Three soft concerns hold it back from FIT:
1. **A post-results sell-off is still running.** Q2 FY27 came out 2026-10-12. The stock fell −7.1% on 2026-10-13 on 39.2M shares, about 11× normal volume, and has fallen on every session since: ₹417.7 → ₹374.3 (−10.4%) by 2026-10-15.
2. **Credit cost is rising.** It was ₹771 Cr, up 53% YoY and 29% QoQ.
3. **The fundamental panel returned `INSUFFICIENT`.**

Quant and qualitative mostly agree. The disagreement is with the backtest: its 2025-01→2026-10 window spans a change of ownership, so its P&L comes mostly from a takeover rerating, not from steady oscillation (see below).

## Structural guard (quant)
- Verdict: RANGE_BOUND (confidence high, 374 trading days, as of 2026-10-15)
- Drawdown from peak: −12.5% (peak close ₹428.0 on 2026-09-23, last ₹374.3) | trailing returns: 1m −7.3% / 3m +3.2% / 6m +17.1% / 12m +30.7%
- Reading: by the guard's definition there is no strong directional trend. The monthly shape tells a different story: a near-monotonic rerating from ₹146 (2025-01 low) to ₹429.6 (2026-09 high), about +180%.
  - 2025-04→09: rally on the turnaround.
  - 2025-10: step up on the ENBD deal announcement (₹262 → ₹331).
  - 2025-11→2026-04: a ₹287–₹345 consolidation box.
  - 2026-05→09: a second leg up after regulatory approval and closing (₹318 → ₹430).

  This is a "quality uptrend with pullbacks" profile like ABCAPITAL, not a pure oscillation band. The −48% drawdown in 2024 came from the pre-ENBD stress in unsecured lending (credit cards and microfinance), when the bank was standalone and had no strategic parent. That falling-knife setup is materially de-risked now.

## Fundamental panel (Step 4)
- Verdict: **INSUFFICIENT** | quality_score: n/a | source: none (`fund_panel.py`: "Not in fvm.db and could not fetch — not in Trendlyne master, or stale TRENDLYNE_COOKIE")
- Web fallback (Q2 FY27 press release 2026-10-12 and media coverage):
  - Red flags: credit cost ₹771 Cr (+53% YoY from ₹503 Cr, +29% QoQ from ₹597 Cr); muted CASA growth; NIM-pressure guidance (2026-10-13 coverage).
  - Positives: PAT ₹482 Cr (+170% YoY, +90% QoQ); NII ₹2,131 Cr (+37% YoY); NIM 4.61%; cost-to-income ratio improved to 56.5%; GNPA 1.02% (from 2.32%); NNPA 0.29% (from 0.57%); capital hugely boosted by the ~₹26,000 Cr primary infusion.
- Ownership: ENBD is the promoter with ~60% of the expanded capital. The preferential allotment completed in June 2026, and the open offer at ₹282.38 (2026-06-01→12) received **zero** tenders because the market was far above the offer price. Pledge data was not retrieved, but a 60% strategic foreign-bank promoter is the opposite of the pump-and-dump profile.
- `financial: true` in spirit. Lender leverage and coverage measures are structural for a bank, so the bank was judged on asset quality, returns and ownership.
- Reading: profitability and asset quality are clearly improving, and parent support puts a floor under dips. Rising credit cost is the one deteriorating line to watch.

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Filings/announcements | Q2 FY27 results approved 2026-10-12 (board meeting and 19:00 analyst call). PAT +170%, GNPA 1.02%, credit cost +53% YoY. The stock fell −7.1% the next day on about 11× volume and kept falling to 2026-10-15. Analysts cited valuation after the rally, weak CASA and NIM pressure. | 2026-10-12 / 10-13 | 🟡 |
| Filings — ownership | ENBD received all approvals (2026-05-15) and completed the 60% acquisition (~2026-06-18). Its 3 India branches are to be merged into RBL, making RBL a listed foreign-bank subsidiary. The open offer got zero tenders (2026-06-19). | 2026-05→06 | 🟢 |
| Filings — management | ED Rajeev Ahuja retired at the end of his term (2026-02-20). The Head of Internal Audit superannuated and a successor took over 2026-05-01. RBI approved the Chairman's second term from 2026-05-21. All routine; there were no auditor, CFO or independent-director resignations and no qualified opinion. | 2026-02 → 05 | 🟢 |
| Credit rating | ICRA upgraded to [ICRA]AAA (Stable) and removed the watch on 2026-06-25, then assigned an AAA issuer rating on 2026-07-07. CareEdge upgraded to CARE AAA (Stable) on 2026-07-15. CareEdge Global assigned BBB+ to the USD 1 bn EMTN programme. All three cite ENBD's expected extraordinary support. | 2026-06-25 / 07-07 / 07-15 | 🟢 |
| Promoter pledge / holding | ENBD holds ~60% (929.1M shares). No pledge or selling was surfaced. The panel could not verify this point-in-time. | 2026-06 | 🟢 (unverified) |
| Event window | Q2 results are out (2026-10-12), but the post-results drift is still live (3 down sessions). Next is Q3 FY27, expected mid/late January 2027 (date not yet announced). RBLBANK is F&O-eligible, so the CAS 15:14:15 pre-auction flush applies. | 2026-10-12 → | 🟡 |
| Governance / sector | No current SEBI or RBI action found; RBI penalties and the SEBI consent settlement are historical (pre-2022). Sector: stress in cards and microfinance peaked in FY25–26 and is described as normalising, but India Ratings has a "deteriorating" outlook on microfinance, and RBL has meaningful card and microfinance exposure. That fits the rising credit cost. | 2026 | 🟡 |

## Recommendation
**WATCH. Re-check around 2026-10-26**, after the post-results selling has settled (about 8 sessions):
1. Re-run `python scripts/trend_guard.py --symbol NSE:RBLBANK --fetch --json`. If the verdict is still RANGE_BOUND and the drawdown from peak has held shallower than about −20% (above about ₹342, the top of the Nov–Apr box), upgrade to **FIT**. If it slides into the old ₹290–₹345 box on continued volume, keep it on WATCH until Q3.
2. Verify the panel in the logged-in Trendlyne session (pledge, Piotroski, credit-cost trend).
3. If it upgrades, run `/calibrate NSE:RBLBANK`. The 4hour block led the standalone backtest (₹27.4k vs 15m ₹18.3k vs day ₹7.2k). Discount that number, though: the 2025-01→2026-10 window is mostly a takeover rerating, which is regime-specific. Validate on the post-closing stretch (2026-06→) as well. Then paper-trade before any live add.
4. No fresh entries in the ~2 weeks around Q3 FY27 results (mid/late January 2027).

Most important reason: nothing disqualifies it, and ENBD ownership plus the AAA upgrades remove the 2024-style falling-knife risk. But the stock is mid-way through an earnings-driven repricing, with credit cost rising, so qualifying it today would mean buying into a sell-off that has not yet shown where it stops.

Sources: [Q2 FY27 press release (NSE)](https://nsearchives.nseindia.com/corporate/RBLBANK_12102026164837_IntimationPressReleaseQ2FY2627Signed.pdf), [Upstox Q2 coverage](https://upstox.com/news/market-news/earnings/rbl-bank-q2-earnings-net-profit-jumps-170-to-482-crore-nii-up-23-yo-y-lender-hikes-provisions-by-53/article-201707/), [Equentis — shares slide 8%](https://www.equentis.com/blog/rbl-bank-shares-slide-8-despite-strong-q2-results-heres-why/), [ICRA intimation 2026-06-25](https://nsearchives.nseindia.com/corporate/RBLBANK_25062026174437_IntimationCreditRating_25062026_signed.pdf), [ICRA intimation 2026-07-07](https://nsearchives.nseindia.com/corporate/RBLBANK_07072026181446_IntimationCreditRating_07072026Signed.pdf), [ENBD approvals (DFM)](https://feeds.dfm.ae/documents/2026/May/15/ee2699ad-c8c4-41d0-9e47-164fe7ff5fe6/Press%20Release%20%20%20Emirates%20NBD%20Receives%20All%20Regulato.pdf), [Open offer zero tenders](https://filingreader.com/news-wire/mumbai/2026-06-19/emirates-nbd-open-offer-for-rbl-bank-fails-to-attract-shares), [Senior management change (NSE)](https://nsearchives.nseindia.com/corporate/RBLBANK_24042026185614_ChangeinSeniorManagementSigned.pdf), [Gulf News — ENBD India expansion](https://gulfnews.com/business/banking/emirates-nbd-clears-path-for-india-expansion-eyes-more-growth-overseas-1.500447294). Price and volume figures come from the local `candles` table (day TF).
