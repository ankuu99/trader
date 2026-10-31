# Stock Qualification — NSE:TIPSMUSIC — 2026-08-08

## Verdict: **FIT** (with a live event-window caveat)
Range-bound, high confidence, best fundamental profile of the three (Piotroski 8/9, ROCE
110%, debt-free, 64.15% promoter holding, no pledge). No governance or credit red flags. The
1m −9.3% is a margin-driven derating on deliberate content spend, not deterioration. One
active caveat: **an open-market buyback at ₹750 was approved 5 Aug** and will distort price
action while it runs.

## Structural guard (quant)
- Verdict: **RANGE_BOUND** (confidence high, 371 days history)
- Drawdown from peak: −10.9% (last 645.35 vs peak 724.35) | 33.2% above period low
- Trailing returns: 1m −9.3% | 3m −0.5% | 6m +20.2% | 12m +7.2%
- Reading: genuine oscillation — flat over 3m and 12m with ±10% swings. This is the cleanest
  structural fit of the three names.

## Fundamental panel (Step 4)
- Verdict: **STRONG** | quality_score 1.0 | source: fetched
- Red flags: none
- Positives: profit +93% YoY and accelerating, revenue +32%, margin expansion, **ROCE 110.2%**
  and rising, D/E 0.00, CFO/NP 0.91, no promoter pledge
- Snapshot (2026-07-03): D=80 V=31 M=67, **Piotroski 8/9**, pledge 0.0%, MF+FII QoQ +0.09pp,
  "Strong Performer, Getting Expensive"
- Reading: asset-light music-rights model with exceptional returns on capital and near-1.0
  cash conversion. Quality strongly supports dip recovery.

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Q1 FY27 results | Revenue ₹106.5 cr (+21% YoY from ₹88.1 cr); operating EBITDA ₹53.5 cr; PAT ₹43.9 cr | 2026-07-22 | 🟢 |
| Margin/QoQ | **PAT −26% QoQ** (₹43.7 cr vs ₹59.06 cr in Q4 FY26); EBITDA margin contracted to 50.3% — driven by content investment **+90% to ₹44.6 cr**, 73 new songs released | 2026-07-22 | 🟡 growth spend, not decay |
| Price reaction | Stock tumbled on the Q1 print; separately jumped 14% earlier on the buyback agenda | 2026-07-22 | 🟡 volatile |
| **Corporate action** | **Buyback approved 5 Aug 2026**: open market, up to ₹44.5 cr (min ₹33.4 cr), max ₹750/sh (~13% premium to the ~₹664 prior week close), ≤5,93,333 shares (0.46% of equity). Funded from free reserves, debt-free preserved. Promoters (64.15%) barred from participating. Still needs a shareholder special resolution | 2026-08-05 | 🔴 event window |
| Digital | YouTube subscribers 158.3m; "Tere Liye" in Spotify daily Top 10 | Q1 FY27 | 🟢 |
| Promoter | Taurani family 64.15%. UMG stake-sale talks stalled (UMG wanted a large stake); **company clarified the stake-sale report is factually incorrect**, no reportable event | 2026 | 🟡 recurring speculation |
| Governance | No SEBI action, auditor resignation, pledge or promoter selling found | — | 🟢 |
| Credit rating | No 2026 rating action found; debt-free | — | ⚪ |

## Reading of the live divergence
Only 2 live trades, −₹1,463, live avg loss −₹2,791 vs backtest −₹1,876. Far too thin to
condemn. Like CGPOWER, it has **no `per_stock_params` block** — running the global 15m
config. Currently holding a position entered 5 Aug 14:00, at −₹1,204 — that entry landed on
the exact day of the buyback board meeting.

## Recommendation
**Keep.** Structurally and fundamentally the strongest of the three; nothing here justifies
removal, and 2 trades is not evidence.

Two concrete cautions:
1. **While the open-market buyback is running**, the company itself is bidding under ₹750.
   That puts a synthetic floor under dips and distorts the volume feature the model relies on
   (volume_ratio at extrema). Expect the dip-detector to behave off-pattern.
2. Do not calibrate on 2 live trades. If a regime change is wanted, it needs rolling-window
   validation first, same as CGPOWER.

Re-check after the buyback completes and the shareholder special resolution passes.
