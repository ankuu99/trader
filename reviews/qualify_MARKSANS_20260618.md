# Stock Qualification — NSE:MARKSANS — 2026-06-18

## Verdict: **WATCH** (weak fit — do not add now)
The company is clean fundamentally (no red flags found anywhere), but the chart is in a
**strong UPTREND** (+47% in 3m) — the textbook *weak fit* for LRExtrema: a trending name has
few local minima, so the strategy under-fires and what it does fire on is a poor mean-reversion
setup. This is a *fit* problem, not a loss/safety problem. Quant and qualitative don't disagree —
both say "good company, wrong shape for this strategy right now." Also low-confidence (71 days history).

## Structural guard (quant)
- Verdict: **UPTREND** (confidence **low** — only 71 trading days available even with `--fetch`)
- Drawdown from peak: 0.0% (last close ₹254.45 = peak) | 62.1% above period low
- Trailing returns: 1m +17.2% | 3m +47.1% | 6m n/a | 12m n/a
- Reading: Strong one-directional advance. Guard explicitly flags "3m return 47.1% ≥ 40% — strong trend, few local minima (weak fit for mean-reversion, not a loss risk)."

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Filings / announcements | Q4 FY26: net profit +63.6% to ₹148cr, sales +20.8% to ₹856cr; completed 100% acquisition of QliniQ B.V. (Netherlands) | Q4FY26 / 2026-06-16 | 🟢 |
| Credit rating | India Ratings issuer rating IND A, **Positive** outlook (latest found is 2022; no downgrade since) | 2022-09 (stale) | 🟢 |
| Promoter pledge / holding | Promoters 43.87%, **0% pledged**; fresh "no encumbrance" declaration filed | 2026-04-02 | 🟢 |
| Event window | Final dividend ₹0.90 recommended 26 May 2026 (AGM/record date likely early July — not confirmed within next 2 weeks). Unclaimed-dividend KYC deadline 17 Jun (immaterial) | 2026-05-26 | 🟡 |
| Governance / sector | No SEBI action / fraud / investigation. Pharma formulations sector stable; US-FDA exposure (export-led, FX-sensitive) | 2026 | 🟢 |

## Recommendation
**Do not add to the watchlist.** Single most important reason: the stock is in a **strong uptrend
(+47% / 3m)** — a structurally poor fit for a mean-reversion strategy, which needs oscillating /
range-bound price action. Nothing is *wrong* with the company; it's simply the wrong shape.

Next step: re-run the guard in a few months. Only revisit if it stops trending and settles into a
range (`RANGE_BOUND` at higher confidence) — then `/calibrate NSE:MARKSANS` + paper-trade. Chasing
it now would mean buying "local minima" inside an uptrend (entries that don't mean-revert).
