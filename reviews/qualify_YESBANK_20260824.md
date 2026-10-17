# Stock Qualification — NSE:YESBANK — 2026-08-24

## Verdict: **FIT**
Range-bound chart (high confidence) + STRONG fundamental panel + a 2026 credit-rating upgrade cycle across four agencies under SMBC ownership — quant and qualitative agree; no material red flags, only two minor yellows (DoT guarantee invocation, third-party SEBI insider case).

## Structural guard (quant)
- Verdict: RANGE_BOUND (confidence high, 369 days of history, as of 2026-08-21)
- Drawdown from peak: -10.5% | trailing returns: 1m -0.6% / 3m +4.3% / 6m +8.8% / 12m +21.1%
- Reading: gently rising oscillation — 12m +21% with a contained -10.5% drawdown and near-flat 1m; no strong directional trend. Matches the discovery scan (ER 0.002) and the backtest profile (82 trades, 65% WR, ₹13,882, #2 of 30). This is the shape LRExtrema wants.

## Fundamental panel (Step 4)
- Verdict: STRONG | quality_score: 0.75 | source: fetched (Trendlyne snapshot as of 2026-07-03)
- Red flags: none | Positives: YoY profit growth +34% and accelerating, operating margin trending up, ROCE rising, CFO/NP 6.10, no pledge
- `financial: true` — lender-style leverage / interest-coverage / operating-cash flags correctly suppressed as structural for a bank; judged on growth, returns, ownership
- Snapshot: Piotroski 6, DVM "Strong Performer, Under Radar" (D 75 / V 55.5 / M 56.3), FII +0.68pp QoQ, MF +0.7pp QoQ
- Promoter holding 0% is structural, not a flag: Yes Bank has no promoter post-2020 reconstruction; largest shareholder is SMBC (24.21%), with SBI and other institutions — the opposite of the pump-and-dump profile the promoter check screens for
- Reading: quality bank in a profit-acceleration phase → dips have a fundamental floor; supports mean-reversion entries

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Filings/announcements | 22nd AGM held via VC; all resolutions approved incl. equity/debt fund-raising enablers and auditor change (routine rotation, approved by shareholders — not a resignation) | 2026-08-19 | 🟢 |
| Filings/announcements | DoT invoked bank guarantees aggregating ₹281.44 Cr issued by Yes Bank | 2026-08-14 | 🟡 small vs ~₹1,071 Cr Q1 profit; monitor for follow-on |
| Filings/announcements | $850M medium-term-note programme — "no comments" letters from India INX / NSE IX; routine international debt-programme step | 2026-08-12 | 🟢 |
| Credit rating | Moody's upgrade Ba2 → **Ba1 (Stable)** | 2026-05 | 🟢 strong |
| Credit rating | ICRA upgrade to **AA (Stable)** from AA-; CARE to **AA+ (Stable)** from AA-; S&P inaugural **BB+ (Stable)** explicitly factoring SMBC group support | 2026 | 🟢 strong — upgrades are the inverse of the falling-knife predictor |
| Ownership transition (SMBC) | RBI approved SMBC acquiring up to 24.99% (letter dated 2025-08-22); CCI cleared the 20% purchase (~₹13,483 Cr) 2025-09; SMBC now largest shareholder at 24.21%; RBI in-principle nod for SMBC wholly-owned Indian subsidiary 2026-01 | 2025-08 → 2026-01 | 🟢 transition largely complete — a stabilising anchor, not an overhang |
| Event window (next 2 weeks) | AGM already passed (2026-08-19); Q2 FY27 results expected ~mid-October (Q2 FY26 was 2025-10-18); no earnings / record date / corporate action in the 2026-08-24 → 2026-09-07 window | — | 🟢 clear |
| Governance | SEBI insider-trading case around the 2022 Yes Bank share sale names PwC/EY executives and PE-linked individuals (19 noticees, ~16 settling); the bank itself is not the accused — third-party UPSI leakage | 2026-01 (show-cause Nov 2025) | 🟡 headline risk only |
| Sector | Private-bank NIMs troughed after the 125 bps cut cycle (Q2FY26 3.87%); 2026 outlook: NIM stabilisation, stable asset quality, Moody's stable sector outlook | 2026-01 | 🟢 no structural headwind |

## Tick-size / spread-granularity check (extra)
At ~₹22.8, NSE places the stock in the sub-₹250 band → tick size **₹0.01** (post the June-2024 NSE tick revision), i.e. one tick = **~0.044%** of price. With ₹222 Cr/day turnover the touch spread is realistically 1–2 ticks (~0.04–0.09%) — negligible against a 1.5–3% average move and small next to the 0.2% round-trip STT that already dominates costs. Had the old ₹0.05 tick applied, one tick would be ~0.22% (≈ a full round-trip STT) and worth worrying about; it does not. **No material spread-granularity drag.** Only residual nuance: SL/trail levels quantise to ₹0.01 (~0.04% steps), which is noise at stop_pct scale.

## Recommendation
Proceed: run `/calibrate NSE:YESBANK` (timeframe regime + threshold), then paper-trade 2–4 weeks before any watchlist add. Single most important reason: quant (RANGE_BOUND, high confidence) and fundamentals (STRONG, 0.75, rating-upgrade cycle under SMBC ownership) agree — the dip-recovery premise holds. Re-check only if the DoT guarantee matter escalates or ahead of the ~mid-October Q2 results window.
