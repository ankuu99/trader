# Stock Qualification — NSE:ULTRACEMCO — 2026-09-27

## Verdict: **FIT** (structural) — with a thin-edge caveat for the 15m regime
Range-bound large-cap with AAA credit, zero pledge, clean governance and no event inside the
2-week window: nothing disqualifies it. Quant and qualitative agree. The only reservation is
economic, not structural: the discovery backtest (80 trades, ₹6.8k on ₹6L over 2025-01→2026-08)
is churn-shaped, so the stock must go through `/calibrate` (expect a 4hour/day regime to win)
before paper trading — do not add on the 15m global params.

Context from the discovery scan: RANGE_BOUND, ER 0.023, turnover ₹299 Cr/day, 6m +10%,
12m −10%, dd −13%; standalone 15m backtest 62.5% WR.

## Structural guard (quant)
`python scripts/trend_guard.py --symbol NSE:ULTRACEMCO --fetch --json` (as of 2026-09-25, 371 d history)
- Verdict: **RANGE_BOUND** (confidence **high**)
- Last close ₹11,155 | peak ₹12,791 | low ₹10,155
- Drawdown from peak: **−12.8%** | 9.8% above period low
- Trailing returns: 1m **−4.8%** / 3m +0.4% / 6m +9.8% / 12m −9.8%
- Reason: "12m return −9.8%, drawdown −12.8% from peak — no strong directional trend"
- Reading: a ₹10.2k–12.8k box for a year; no falling-knife signature. The −4.8% 1m dip is the
  kind of pullback the strategy is meant to buy, not a trend break. Liquidity (₹299 Cr/day) is
  far beyond anything the ₹6L book could move.

## Fundamental panel (Step 4)
`python scripts/fund_panel.py --symbol NSE:ULTRACEMCO --json` (source fvm.db, snapshot 2026-07-03)
- Verdict: **OK** | quality_score: **0.571** | sector: Construction Materials | financial: no
- Red flags: **none**
- Positives: revenue +16% YoY; D/E 0.26; CFO/NP 1.94; no promoter pledge
- Snapshot: durability 85, valuation 38, momentum 50 (DVM "Mid-range Performer"); Piotroski 7;
  promoter 59.33% (flat, +0.035 pp/qtr); MF +0.57 / FII −0.83 QoQ
- Softer metrics: YoY profit growth −3%, OPM trend −0.09, ROCE 11.9% and trending down
  (integration of India Cements / Kesoram assets), EV/EBITDA 21.2 (rich)
- Reading: solid balance sheet and cash conversion — a dip here is buyable, not a knife. Quality
  is "OK" rather than "STRONG" because returns are diluted by acquisitions and the valuation is
  full; that caps upside expectations but does not threaten dip recovery.

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Filings/announcements | Only filings in Sept are "material price movement" clarifications (Sep 11, 18, 21, 22) — company states purely market-driven, no undisclosed event. Q1 FY27 (Jul 20): PAT ₹2,599 Cr, +16.8% QoQ; FY26 revenue +16%, 200 MTPA capacity reached | 2026-09-22 | 🟢 |
| Board / KMP | No auditor or CFO exit. Company Secretary changed Dec 2025 (planned superannuation). MD succession announced: Jayant Dua to replace K.C. Jhanwar from 2027-01-01 (4-yr term) — orderly, pre-announced | 2026-07 | 🟢 |
| Credit rating | CRISIL **AAA/Stable, A1+ reaffirmed** (rationales Jul 23 and Aug 17, 2026); CARE reaffirmed Stable (Apr 10, Jun 24, Jul 23, 2026). No watch, no downgrade | 2026-08-17 | 🟢 |
| Promoter pledge / holding | Pledge 0%; promoter 59.33% flat; FII trimming (−0.83 pp QoQ), DII adding | 2026-07-03 | 🟢 |
| Event window | Q2 FY27 board meeting not yet intimated; last year's Q2 came ~Oct 18–20 and Q1 FY27 was Jul 20, so expect **~Oct 17–21, 2026** (3+ weeks out — outside the 2-week window). Trading-window closure ~Oct 1. No bonus/split/record date found | 2026-09-27 | 🟡 (re-check by Oct 10) |
| Governance | No SEBI action. Legacy CCI cartel penalty ₹1,804 Cr (2016 case) remains **stayed** — long-standing contingent liability, priced in. India Cements (subsidiary) CCI probe: no finding, no penalty. GST demand ₹2.28 Cr — immaterial | 2026-07 | 🟡 (known, static) |
| Sector | Cement prices range-bound through Sept (monsoon); Rs25–30/bag hikes attempted Sep 5 with uncertain hold; fuel (petcoke ~$147/t) squeezing spreads ~₹90–100/t QoQ; ICRA sees FY27 volumes +7–8%. Analysts trimming sector estimates on competitive intensity — a headwind to earnings, not a structural decline | 2026-09 | 🟡 |

## Recommendation
**Qualified — but calibrate before paper.** Structurally this is the archetype the strategy
wants: a liquid, AAA-rated, un-pledged large cap oscillating in a −13% box with no event in the
next two weeks. The decisive reservation is that the 15m backtest edge is marginal (₹6.8k on ₹6L
over 20 months from 80 trades ≈ ₹85/trade — STT-sized). CLAUDE.md flags "very high trade count
with low return" as churn, and a ₹11k stock with ER 0.023 is a natural 4hour/day candidate.

Next actions, in order:
1. `/calibrate NSE:ULTRACEMCO` — stage 1 regime comparison (15m global vs 4hour/day template);
   only proceed if the winner is clearly positive on both 2023+ and 2025+ windows.
2. If a regime shows real edge: paper trade 2–4 weeks, avoiding fresh entries Oct 15–22 around
   the Q2 FY27 print.
3. Re-check the event window by **Oct 10** (results-date intimation) and re-run the trend guard
   after Q2 if the 1m return worsens past −10% (would flip the box into DOWNTREND).

Sources: trend_guard.py / fund_panel.py (local, PIT); CRISIL rating rationales 2026-07-23 and
2026-08-17; CARE press releases 2026-04-10 / 06-24 / 07-23; BSE/NSE MPM filings Sep 11–22, 2026;
UltraTech Q1 FY27 press release (2026-07-20); Indian Cement Review Sept 2026 sector note;
Business Standard on CCI / India Cements.
