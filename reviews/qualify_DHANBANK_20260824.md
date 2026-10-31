# Stock Qualification — NSE:DHANBANK (Dhanlaxmi Bank) — 2026-08-24

## Verdict: **WATCH**
Quant (RANGE_BOUND, high confidence) and the bank-corrected fundamental panel (STRONG 0.75) both point to FIT, but qualitative history disagrees softly: this is a boardroom-dispute-prone micro-cap bank with RBI nominee directors still seated, speculative-grade (BB+) Tier-II paper, the thinnest liquidity of the finalists (₹6.4Cr/day) — and its next historical flashpoint, the AGM, lands Sep 17–23, ~3.5 weeks out. Re-check after the AGM passes cleanly.

## Structural guard (quant)
- Verdict: **RANGE_BOUND** (confidence **high**, 369 days of history, as-of 2026-08-21)
- Drawdown from peak: **−6.9%** | trailing returns: 1m −1.8% / 3m +0.1% / 6m +40.8% / 12m +25.3%
- Reading: range-bound near its 52-week high — no falling-knife structure. The +40.8% 6m leg has flattened out (3m ≈ 0), i.e. the stock is consolidating a re-rating rather than trending; oscillation-friendly. Last close ₹33.73 vs peak ₹36.22.

## Fundamental panel (Step 4)
- Verdict (raw): `DISTRESS` | quality_score 0.714 | source: **fetched** (on-demand Trendlyne)
- **Bank correction (required)**: the on-demand fetch returned `sector: null`, so `financial` resolved **false** and the lender-structural `thin_interest_cover 1.2×` flag was NOT suppressed — it is the *sole* red flag behind DISTRESS, and interest coverage is meaningless for a bank (interest expense is its raw material). Re-running `build_panel(..., financial=True)` on the same factors gives:
- Corrected verdict: **STRONG** | quality_score: **0.75** | red flags: **none**
- Positives: YoY profit growth +68% (accelerating), revenue +22% YoY, operating margin trending up, ROCE rising, CFO/NP 6.15, **zero promoter pledge**
- Snapshot (2026-07-03): DVM **Strong Performer** (D 75.0 / V 66.8 / M 60.3), **Piotroski 7**, pledge 0.0, FII +0.1 pp QoQ
- Reading: quality/turnaround momentum is real and clean by the panel's own metrics — dips have a fundamental floor under them. Treat the file's printed DISTRESS as a sector-mapping artifact, not a signal.

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Filings/announcements | Q1 FY27 results: NP ₹24.91cr (~2× YoY vs ₹12.18cr), total income ₹484cr, GNPA 1.82%, NNPA 0.47% — clean, improving | 2026-07-29 | 🟢 |
| Filings/announcements | Board being rebuilt: Rajan T.K. appointed addl. independent director (5 yrs, from 2026-07-29); T.V. Rao addl. non-exec independent director (3 yrs, from 2026-09-01) — long-standing quorum/vacancy problem finally being addressed | 2026-07-29 / 2026-09-01 | 🟢 |
| Credit rating | ICRA **reaffirmed** BBB− (Stable) on FDs, A3 on CDs — "steady credit profile, improving asset quality" (2026 rationale); CARE reaffirmed Lower Tier-II bonds at **BB+; Stable**. No downgrade or watch-negative — but note the absolute level: BBB−/BB+ is bottom-of-investment-grade / speculative — a weak bank, not a strong one | 2026 (reaffirmations) | 🟡 |
| Promoter pledge / holding | No promoter pledge (0.0%); no identifiable promoter group in the classic sense — largest holder B. Ravi Pillai ~10%. FII +0.1 pp QoQ. No insider-selling signal found | snapshot 2026-07-03 | 🟢 |
| Capital raise / dilution | ₹297.5cr rights issue @ ₹21 completed Jan 8–28 2025 (allotment 2025-02-04), ratio 14:25 → ~56% share-count expansion; strengthened Tier-I. Prior ₹127cr rights attempt was blocked by boardroom quorum failure (2022). Serial capital-raiser — future dilution plausible but nothing announced now | 2025-01-28 (closed) | 🟡 |
| Event window (next ~2 wks) | **Nothing in Aug 24 – Sep 7.** But AGM (99th) is Sep 23 2026 via VC, record/cut-off Sep 17, book closure Sep 18–23 (intimated 2026-08-19) — just outside the window, and AGMs are exactly where this bank's fights have historically erupted (CEO removed by shareholder vote at the 2020 AGM) | 2026-09-17→23 | 🟡 |
| Governance / RBI | History: PCA Nov 2015 → exit Feb 2019; shareholders voted out CEO Gurbaxani (2020); RBI appointed nominee directors to the board (D.K. Kashyap 2020-09; nominees incl. Jayakumar Yarasi still seated — ongoing enhanced RBI scrutiny); Kerala HC board-seat litigation and the 2022 rights-issue quorum blockage. **Current state: quiescent** — RBI-approved MD&CEO Ajith Kumar KK since Apr 2024 (3-yr term → renewal due ~Apr 2027), independent-director vacancies being filled (Jul/Sep 2026), broker rating upgraded Sell→Hold (2026-04-22), no fresh dispute, SEBI action, or investigation found in 2025–26 | history 2015–2022; calm through 2026-08 | 🟡 |

## Backtest / liquidity context (from discovery)
- 2025-01→2026-08 live-strategy backtest: 94 trades, 67% win rate, ₹8,905 P&L (#6 of 30 finalists)
- ER 0.010, dd −6.9% — good mean-reversion texture; **but turnover ₹6.4Cr/day is the lowest of the finalists** — above the ₹50L floor, yet thin for a bank stock; expect wider spreads and gappier candles on bad-news days.

## Recommendation
**Hold off ~4 weeks; re-check on/after 2026-09-24 (day after the AGM).** The single most important reason: every hard datapoint dated 2026 is green (profit ~2× YoY, GNPA 1.82%, ratings reaffirmed Stable, board vacancies being filled), but this bank's specific failure mode — governance blow-ups at shareholder meetings under standing RBI-nominee scrutiny, with speculative-grade capital instruments — has a scheduled venue on Sep 23. If the AGM passes without incident and no rating/RBI action lands, upgrade to FIT and proceed to `/calibrate NSE:DHANBANK` + paper trading; size conservatively given the ₹6.4Cr/day liquidity. Any AGM dispute, rating downgrade, or fresh capital-raise announcement → AVOID.

*Note for the tooling: `fund_panel.py` printed `DISTRESS` only because the on-demand Trendlyne fetch left `sector` null, so `is_financial()` returned false and the interest-coverage flag fired on a bank. Corrected `financial=True` panel: STRONG / 0.75 / no red flags.*
