# Stock Deep Dive — NSE:CUPID — 2026-06-14

## Verdict
**KEEP** — one of the strongest names on the book: +₹31,724 over 230 trades, profitable
every calendar year, edge driven by a clean trailing-stop engine (+₹62.6k of TRAILING
P&L). Recent 6m still positive (+₹2,513, 67% WR). No override needed — global params work.

## Performance
| Period | P&L | Trades | Win rate | Avg win | Avg loss |
|--------|-----|--------|----------|---------|----------|
| Full (2023-01-01→today) | +₹31,724 | 230 | 50.9% | ₹548.71 | −₹287.39 |
| Recent 6m | +₹2,513 | 12 | 66.7% | ₹532.58 | −₹436.94 |

R:R ≈ 1.91 — wins nearly 2× losses, and the strategy wins more than half the time.

## Year-by-year
| Year | P&L | Trades | Win rate |
|------|-----|--------|----------|
| 2023 | +₹8,495 | 72 | 52.8% |
| 2024 | +₹7,616 | 73 | 39.7% |
| 2025 | +₹14,311 | 74 | 58.1% |
| 2026 (to date) | +₹1,301 | 11 | 63.6% |

Remarkably consistent — positive every year, with 2025 the best. Note 2024 won only
40% of the time yet still made ₹7.6k: big trailing winners (avg win ₹779 that year)
carried it. That's the strategy working as designed, not luck.

## Exit breakdown
| Reason | Trades | Total P&L | Avg P&L |
|--------|--------|-----------|---------|
| TRAILING | 118 | +₹62,593 | +₹530.45 |
| STRATEGY (hold_bars) | 18 | −₹4,017 | −₹223.18 |
| STALE | 94 | −₹26,852 | −₹285.66 |

**Healthy profile.** TRAILING is the dominant, hugely profitable exit (the ideal
signature). STALE (94 trades, −₹26.9k) and hold_bars (−₹4k) are the expected cost of
fishing for entries — but unlike INDHOTEL, here the trailing winners *dwarf* the stale
bleed (+₹62.6k vs −₹26.9k). No SL or OPEN@END exits — stops and EOD logic are clean.

## Config
- In watchlist: **yes** (actively traded)
- Active override: **none (global params)** — `threshold: 0.90`, forward_label off.
  Calibration not warranted; the global config is already performing strongly.

## News & context
- **Q3 FY26 blowout**: consolidated net profit +196% YoY to ₹32.8 Cr; revenue +102% to
  ₹93.5 Cr.
- **FY26 full year**: EPS ₹0.81 (vs ₹0.30), revenue ₹3.91b (+113%), net income +165%.
- **Guidance**: targeting ₹600 Cr revenue / ₹180 Cr PAT by FY27 at 30% margins.
- **Order win**: secured a 5-year (2025–2030) South Africa national condom procurement
  programme worth ~₹115 Cr (USD 12.98m) — multi-year revenue visibility.
- **Price**: at all-time high ₹160 (12 Jun 2026); stock has run ~620%.
- ⚠️ **Valuation risk**: ~197 P/E — richly priced; momentum/froth is the main risk. A
  sharp valuation de-rate could produce sustained drawdowns that the mean-reversion
  entries would misread (the same regime trap that hurt INDHOTEL). Worth monitoring, not
  acting on.
- No SEBI actions, promoter pledging, or governance flags found.

## Recommendation
**Keep as-is, no changes.** Best risk/reward profile on the watchlist with a clean,
trailing-driven edge and supportive fundamentals. Do not add an override — global params
already deliver. Single watch-item: the ~197 P/E means a momentum unwind is the key
forward risk; re-review if the stock enters a sustained multi-month downtrend, which is
the one regime where this strategy's entries degrade.
