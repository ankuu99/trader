# Stock Qualification — AJANTPHARM — 2026-10-15

## Verdict: **FIT** (structural) — with a promoter-pledge watch item and a Q2-results event window
Range-bound chart (high confidence), zero-debt AA+ business with 28% ROCE, no governance or
regulatory red flags. Quant and qualitative agree. The one soft concern is a ~18% promoter
pledge that is rolled continuously to fund family-level NCDs/loans: not a spike and not
company debt, but forced-selling risk to watch. Discovery context: the 15m backtest lost money
(−₹7.3k) while 4hour (₹16.7k) and day (₹17.5k) made money, so qualify it on an aggregated
timeframe only.

## Structural guard (quant)
- Verdict: **RANGE_BOUND** (confidence high, 374 days of history)
- Drawdown from peak: −9.6% (peak 3,718.2, last close 3,359.8; +40.7% above the period low of 2,388.4)
- Trailing returns: 1m −4.3% | 3m −2.7% | 6m +16.5% | 12m +39.4%
- Reading: a strong 12-month advance followed by a ~3-month sideways/shallow pullback. No
  directional breakdown, which is the regime LRExtrema is built for.

## Fundamental panel (Step 4)
- Verdict: **OK** | quality_score: **0.643** | source: fvm.db (snapshot 2026-07-03), sector Healthcare, non-financial
- Red flags: `promoter_pledge` (med): pledge 17.9%
- Positives: revenue +19% YoY, ROCE 27.9% and rising (+2.1), D/E 0.00 (interest coverage 541×),
  CFO/NP 0.85
- Other metrics: promoter holding 66.25% (flat, −0.003pp/qtr), DII trend +0.33, FII trend −0.24,
  OPM trend −1.34, profit growth in the panel +2% (stale vs Q1 FY27 +31%), Piotroski 5,
  DVM class "Expensive Rocket" (EV/EBITDA 25, valuation score 28.8)
- Reading: the business is sound enough that a dip should mean-revert rather than collapse.
  The pledge is at **promoter-family level** (trusts and Gabs Investments borrowing against
  shares). The company itself carries no debt. It still matters because it is a channel for
  forced supply if the stock drops sharply.

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Filings / announcements | Q1 FY27 (board 2026-07-30): revenue ₹1,626 cr (+24.8%), PAT ₹334 cr (+30.9%), US generics +57%, India +24%, Africa +29%; interim dividend ₹32 (record 2026-08-05). Management guided only **mid-to-upper-mid single-digit growth for the rest of FY27** (price erosion, new competition, thin launch pipeline). No auditor/CFO/director exits found. | 2026-07-30 | 🟡 (growth deceleration guided, which is mean-reversion-friendly and not distress) |
| Regulatory (USFDA) | Paithan plant inspection 2026-04-13→21: Form-483 with 5 observations; **EIR received July 2026 with VAI**, so the inspection is closed and no action is warranted. | 2026-04-22 / 2026-07 | 🟢 |
| Credit rating | **CARE AA+ Stable / A1+ reaffirmed** (₹72.5 cr bank facilities), citing consistent operating improvement and FY26 revenue growth of ~19%. No downgrade or watch. | 2026-08-12 | 🟢 |
| Promoter pledge / holding | Total pledge ~17.9% of equity (panel 2026-07-03). Pledges and releases churn constantly: Gabs Investments pledged 2.77M shares (2.22%) on 2026-06-02; RBL Bank pledge of 1.11M shares on 2026-06-10; releases on 2026-05-29, 06-19, 06-27 and 07-01; Aayush Agrawal released 1.74M shares (loan repayment) on 2026-09-16; **Aayush Agrawal Trust pledged 4.6 lakh shares to CTL Trusteeship for NCDs on 2026-09-28** (disclosed 2026-10-05), taking that trust's encumbrance to 9.69% of company equity (≈86% of its 11.29% holding). Promoter holding is stable at 66.25%. The pattern is rolling refinancing rather than a spike, but the encumbrance is heavy. | 2026-10-05 | 🟡 |
| Event window | **Q2 FY27 results not yet scheduled** (no board intimation found as of 2026-10-15). Last year the Q2 board met **2025-11-03** (intimation 2025-10-08) with an interim dividend (record date 2025-11-10). Expect Q2 FY27 results around **late Oct to the first week of Nov 2026**, probably with an interim dividend record date about a week later. This is outside the immediate 2-week window but close to it. | expected ~2026-11-03 | 🟡 |
| Governance / sector | No SEBI action, fraud or investigation found. Sector: US tariffs exempt generics duty-free until 2028-08-01, rising to 100% after that. Branded patented drugs are hit now. The risk is long-dated, but pharma names sell off on tariff headlines. Ajanta's mix (India + Africa/Asia branded + growing US generics) has moderate US exposure. | 2026 | 🟡 |

## Recommendation
**FIT on an aggregated timeframe (4hour or day), not 15m.** Next steps: `/calibrate NSE:AJANTPHARM`
with the 4hour/day template blocks (set `threshold` inside the block, as noted in the 2026-09-01
day-TF calibration memo), then paper-trade it.

Most important reason: a range-bound tape on a debt-free AA+ pharma with 28% ROCE is exactly
the setup where dips recover.

Re-check before adding:
1. **Q2 FY27 shareholding pattern** (due ~2026-10-21): confirm total pledge is ≤ ~18% and not
   rising. A jump above ~25%, or any invocation, means AVOID.
2. **Q2 results date**: once intimated (likely ~2026-11-03), block fresh entries from ~2 sessions
   before results through the interim-dividend record date.
3. Q2 commentary: confirm the guided slowdown stays a slowdown (single-digit growth) and does not
   turn into US price-erosion margin compression.

Sources: [Choice India: Aayush Agrawal Trust pledge](https://choiceindia.com/news/ajanta-pharma-promoter-aayush-agrawal-trust-share-pledge),
[FilingReader pledge wire (Jun–Aug 2026)](https://filingreader.com/news-wire/mumbai/2026-06-09/gabs-investments-pledges-222-stake-in-ajanta-pharma),
[CARE rating PR Aug 2026](https://www.careratings.com/upload/CompanyFiles/PR/202608120823_Ajanta_Pharma_Limited.pdf),
[NSE BM outcome 2026-07-30](https://nsearchives.nseindia.com/corporate/AJANTPHARM_30072026144134_BMOutcome30072026.pdf),
[Q1 FY27 results (Indian Pharma Post)](https://www.indianpharmapost.com/news/lite/ajanta-pharma-posts-rs-1626-billion-revenue-with-25-yoy-growth-in-q1-fy27-21173),
[USFDA Paithan EIR/VAI](https://medicaldialogues.in/amp/news/industry/pharma/ajanta-pharma-receives-usfda-eir-for-paithan-plant-inspection-closed-with-vai-status-174195),
[Q2 FY26 board date (Nov 3, 2025)](https://hdfcsky.com/news/ajanta-pharma-board-to-consider-q2-results-and-interim-dividend-on-november-3),
[US pharma tariff 2026](https://www.india-briefing.com/news/us-patented-pharma-tariff-2026-india-generic-drug-exports-exempted-43899.html)
