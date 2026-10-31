# Stock Qualification — NSE:ADANIENT — 2026-08-24

## Verdict: **AVOID**
Quant and qualitative disagree — the chart is RANGE_BOUND (high confidence) and the US legal
overhang is resolving, but the fundamental panel returns **DISTRESS** with two high-severity
red flags (negative operating cash vs reported profit, −92% YoY profit collapse), and per the
qualification rule a DISTRESS panel takes the worse of the views: the business may not support
dip recovery. Re-check after Q2 FY27 results (~late Oct 2026) when one-time charges wash through.

## Structural guard (quant)
- Verdict: RANGE_BOUND (confidence high, 369 days of history, as of 2026-08-21)
- Drawdown from peak: −6.7% | trailing returns: 1m −0.4% / 3m +10.3% / 6m +37.2% / 12m +35.6%
- Reading: range-bound / mild uptrend — no strong directional trend, 70.4% above period low.
  Structurally a good LRExtrema chart (matches the discovery scan: ER 0.011, ₹504Cr/day
  turnover, 76 trades / 70% WR / ₹15,299 in the 2025-01→2026-08 backtest).

## Fundamental panel (Step 4)
- Verdict: **DISTRESS** | quality_score: **0.286** | source: fvm.db (snapshot as_of 2026-07-03)
- Red flags: **negative_operating_cash** (high — CFO/NP −0.28) · **profit_collapse** (high —
  YoY PAT −92%) | Positives: revenue +10% YoY · low leverage (D/E 0.17)
- Supporting metrics: interest coverage 2.57, ROCE 6.1% (trend −5.1), OPM trend −0.94,
  EV/EBITDA 52 (richly valued — caps upside), pledge 0.8%, promoter holding 74.67% (stable/rising)
- Reading: distress → dip may not recover on business support. Caveats worth noting: the panel
  snapshot (2026-07-03) predates Q1 FY27; the −92% collapse is partly a FY25 exceptional-gain
  base effect, and the Q1 FY27 headline loss is a one-time ₹2,644 Cr OFAC charge over record
  operating EBITDA (+49%). But negative operating cash at a capex-heavy incubator with 2.6×
  interest coverage and 6% ROCE is a genuine quality deficit, not purely optics — this is not a
  SKYGOLD-style soft single-year artifact (two independent high-severity flags).

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Filings/announcements | Q1 FY27 (quarter to Jun-2026): net LOSS ₹1,160 Cr on the one-time ₹2,644 Cr OFAC settlement; operationally record EBITDA ₹5,642 Cr (+49%), revenue +50%. Q4 FY26 filed on time 2026-04-30. No auditor/CFO resignation at AEL in 2026 (internal auditor rotated to EY — routine restructuring). | 2026-07-29 | 🟡 |
| Credit rating | ICRA reaffirmed **AA− Stable** / A1+ (2025-12-22, again 2026-05-27); CARE reaffirmed AA− Stable / A1+. No downgrade, no watch-negative — the strongest anti-falling-knife evidence. | 2026-05-27 | 🟢 |
| Promoter pledge / holding | Pledge 0.8% (negligible), promoter holding 74.67% and trending up (+0.21pp/qtr). FII trend mildly negative (−0.84pp QoQ). | 2026-07-03 (snapshot) | 🟢 |
| Event window | Nothing in the next ~2 weeks: AGM held 2026-06-24, Q1 FY27 results done 2026-07-29; next results ~late Oct 2026. 1:1 bonus + ₹1.3 dividend ex-date was 2025-06-13 (past). | — | 🟢 |
| Governance / sector | **OFAC settlement $275M (₹2,644 Cr) for 32 apparent Iran-sanctions violations** on LPG imports Nov-2023→Jun-2025 (agreement 2026-05-14, announced 2026-05-18) — settled with cooperation credit, but a real compliance-failure record. US SEC civil case settled $18M (2026-05-15); **US DOJ criminal bribery indictment dismissed with prejudice 2026-08-10/11** (judge noted "concerning" DOJ irregularities). SEBI: Hindenburg-probe allegations dismissed (final orders Sep-2025); minimum-public-shareholding settlement with SEBI still pending (~₹2,500 Cr recovery sought vs token settlement offers). Group headline risk is structurally elevated and event-driven — news gaps, not technical structure, move this stock. | 2026-08-11 | 🟡 |

## Recommendation
Do NOT add NSE:ADANIENT to the watchlist now, despite it being the best backtest of the
discovery batch — the fund panel's DISTRESS verdict (negative operating cash + profit collapse,
quality_score 0.286) is exactly the falling-knife-fuel the backtest cannot see, and the
qualification rule is explicit that a DISTRESS panel overrides a clean chart. The single most
important reason: **operating cash flow is negative against reported profit at 2.6× interest
coverage — a dip here relies on sentiment, not business support, to mean-revert.**

Concrete next action: re-run `/qualify NSE:ADANIENT` after Q2 FY27 results (~late Oct 2026)
and the next fvm.db snapshot refresh. If CFO/NP turns positive and the profit base normalises
(the OFAC one-timer and FY25 base effect washed out) while ratings stay AA− Stable, the verdict
likely upgrades — the chart structure, liquidity, and backtest fit are already there.
