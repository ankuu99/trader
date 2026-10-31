# Stock Qualification — NSE:ZYDUSLIFE — 2026-10-15

## Verdict: **WATCH** (structurally a FIT; held back by a fresh USFDA Form 483 at the flagship plant and the upcoming Q2 results)
The chart is range-bound with high confidence and the credit and ownership picture is clean (CRISIL AAA/Stable, net cash, ~75% promoter holding, 0% pledged). Two soft concerns stop it short of FIT. First, a USFDA inspection at **Moraiya** (Zydus's largest US-supply formulations plant) closed on **2026-10-13 with 5 observations**, two days ago. It comes on top of a **2026-06-02 warning letter at Baddi**. Second, Q2 FY27 results are probably due in early November. The quant and qualitative views mostly agree. The disagreement is about *timing*, not structure.

Discovery context (standalone backtest 2025-01→2026-10, ₹40k slots): 15m −₹3.8k, 4hour ₹13.5k, day ₹14.4k. Only an aggregated timeframe is worth pursuing.

## Structural guard (quant)
- Verdict: **RANGE_BOUND** (confidence **high**, 374 days of history)
- Drawdown from peak: **−6.0%** (peak 1215.0, last 1142.6) | 39% above the period low (822.1)
- Trailing returns: 1m +4.0% | 3m −1.0% | 6m +22.1% | 12m +15.9%
- Reading: oscillating with no one-way trend. The 6m rally has been followed by a flat 3m. Price hardly moved on the Moraiya 483 disclosure (10-13 close 1132.5 → 10-14 1124.7 → 10-15 1142.6), so the market is not yet reading it as serious.

## Fundamental panel (Step 4)
- Verdict: **INSUFFICIENT** | quality_score: n/a | source: none (not in fvm.db and the on-demand fetch failed, probably a stale TRENDLYNE_COOKIE)
- Web fallback, used in place of the panel:
  - FY26 was a record year: revenue ₹27,148 cr (+17%), net profit about $654M, EBITDA margin 31.2%.
  - Q1 FY27 (reported 2026-08-11): revenue ₹8,020 cr (+22% YoY), EBITDA ₹1,930 cr, PAT ₹940 cr.
  - Net-cash balance sheet.
- Red flags: none found on the fundamentals. | Positives: durable double-digit growth, high margins, net cash, AAA rating, no pledge.
- Reading: a quality business, so its dips should mean-revert rather than keep falling. A STRONG panel is likely if the panel is re-run with a fresh cookie.

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Filings: USFDA | Moraiya (Ahmedabad) formulations plant inspected 10-05 → 10-13; **5 observations**. Their nature has not been disclosed, and there is no mention of data integrity. Moraiya is the key US-supply site and received a warning letter back in 2019. | 2026-10-13 | 🟡 |
| Filings: USFDA | **Warning letter** at the Baddi formulations plant (talc / component testing, 21 CFR 210/211). The company says US supply continuity is maintained. | 2026-06-02 | 🟡 |
| Filings: USFDA | Ahmedabad injectable unit: 7 observations with no data-integrity findings, then an EIR with **VAI** classification (closed). | 2026-08-01 | 🟢 |
| Filings: USFDA | SEZ-II Ahmedabad: one observation. The US (New Jersey) office inspection on 09-22 → 09-25 found zero observations. | 2026 | 🟢 |
| Filings: board | Independent director A. S. Diwanji left on completing his tenure, not by resigning. No auditor or CFO exits were found. | 2026-05-12 | 🟢 |
| Filings: legal | The US subsidiary settled generic-pricing litigation for $5.9M. Delhi HC put a temporary restriction on Ikra supply; the company says the impact is not material. | 2026 (Jul) | 🟡 minor |
| Credit rating | CRISIL **AAA/Stable** and A1+ reaffirmed. No downgrade or watch was found. | 2025-09-09 (latest found) | 🟢 |
| Promoter pledge / holding | Promoters hold 75.0% (Zydus Family Trust 74.96%), **0% pledged**, no NDUs. In 2026-08 there was an intra-promoter-group transmission of 32,577 shares, which is not a sale. The Sep-26 shareholding pattern is not yet indexed. | Mar-2026 SHP | 🟢 |
| Event window | Q2 FY27 results have **no board-meeting intimation yet**. The prior pattern was Q2 FY26 on 2025-11-06 and Q1 FY27 on 2026-08-11, so expect **about 2026-11-05 to 11-12**. Also watch for any Moraiya escalation (OAI or warning letter) in the coming months. | expected early Nov 2026 | 🟡 |
| Governance / sector | No SEBI action or fraud allegation found. Sector: the US generic tariffs are deferred, with duty-free entry until 2028-08-01, then 100% from 2028 and 200% from 2029. That is a long-dated headwind, not an imminent one. The India branded business (+20%) gives a domestic cushion. | 2026 | 🟡 long-dated |

## Recommendation
**WATCH. Proceed with calibration, but do not add to the watchlist before Q2 results.**
- Calibrate on an aggregated timeframe only (`/calibrate NSE:ZYDUSLIFE`, comparing 4hour and day). 15m lost money standalone. Set `threshold` inside the aggregated block (see the day-TF threshold note).
- Re-run `/qualify` after the Q2 FY27 results (expected about 2026-11-05 to 11-12). On the earnings call, check how management characterises the Moraiya 483, and look for a warning letter or OAI escalation. Fix TRENDLYNE_COOKIE first so the fund panel returns a real verdict.
- Avoid fresh entries from about 1 week before the results date until about 2 sessions after it.
- Upgrade to FIT if the 483 is called procedural and closes toward VAI. Downgrade to AVOID if Moraiya gets OAI or an import alert, since it is the main US-supply plant.

The single most important reason: the structure and balance sheet support a FIT, but a 5-observation 483 at the flagship US plant landed two days ago and its severity is unknown until the company comments, most likely at Q2.

Sources: taxguru.in (Moraiya 483, 2026-10-13); fda.gov warning letter 722576 (Baddi, 2026-06-02); sahi.com (Ahmedabad injectable VAI, 2026-08-01); CRISIL rating rationale (2025-09-09); zyduslife.com SHP (Mar-26); filingreader.com (Q1 FY27, 2026-08-18); scanx.trade (director tenure, 2026-05-13); angelone.in ($5.9M settlement); moneylife.in / outlookbusiness.com (US generic tariffs).
