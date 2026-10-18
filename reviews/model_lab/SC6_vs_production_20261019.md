# SC6 — lab strategies vs the full production system, same window

Run 2026-10-19 · Branch `exp/model-lab` · Ledger: `STRATEGY_LEDGER.md` § SC6 · Owner request 2026-10-19 ("Sure try
that").

## Setup

- **Window:** the campaign FULL window, 2025-01-01 → 2026-10-16. ₹6L capital, 15 slots of ₹40k. Lab entries are
  allowed only from 2025-01-01 (earlier rows are excluded), and metrics are computed on the window only.
- **Production reference:** the TD-018 post-ISS-14 backtest of the full LR-Extrema system: watchlist, per-stock
  params and timeframes, 15m exits, scale-in, loss block. It made **₹4.39 L, worst drop 5.8 %, Calmar 6.18,
  money-weighted win 63.9 %**.
- **Lab side:** the S0 simulator on day bars, picking the best 2 a day with next-open fills and `trader.costs`.
  - Scores come from re-runs of the A01 / A11 recipes on the PIT top-200 plus the 21 watchlist names
    (`A01wl_day_logit_t1z5`, `A11wl_day_hgbq_edgez20`; only 5 of the 21 are in the top-200 on their own).
  - Production P(min) is replayed with the day template.
- **Universes:**
  - `wl`: the 21 watchlist names only;
  - `all`: the whole PIT top-200 plus the watchlist.
- **Controls:** each configuration is also run with 11 coin draws, i.e. random picks on the same rows with the same
  rules.

## Results

| Strategy | Universe | P&L | Worst drop | Calmar | Money-wtd win % | Trades | Coins: median P&L [range] | Beats coins on ₹ / Calmar |
|---|---|---|---|---|---|---|---|---|
| **Production (full system)** | watchlist | **₹4.39 L** | **5.8 %** | **6.18** | 63.9 | — | — | — |
| L1 A01, hold 20 | wl | ₹2.35 L | 8.9 % | 2.46 | 67.3 | 206 | ₹3.41 L [2.83–3.92] | 0/11 · 8/11 |
| L1 A01, hold 20 | all | ₹0.96 L | 14.9 % | 0.60 | 55.3 | 331 | ₹0.35 L [−0.59–1.50] | 10/11 · 10/11 |
| L2 prod ranker, hold 60, +20 % target | wl | ₹3.28 L | 12.4 % | 2.46 | 74.3 | 138 | ₹3.44 L [3.02–3.96] | 4/11 · 9/11 |
| L2 prod ranker, hold 60, +20 % target | all | ₹0.71 L | 15.6 % | 0.43 | 57.2 | 128 | ₹0.15 L [−0.11–0.76] | 10/11 · 9/11 |
| L3 A11, hold 60 | wl | ₹4.00 L | 9.0 % | 4.15 | 86.1 | 82 | ₹4.47 L [3.16–4.84] | 2/11 · **11/11** |
| L3 A11, hold 60 | all | −₹0.27 L | 14.9 % | −0.17 | 47.0 | 112 | ₹0.62 L [−0.17–1.14] | 0/11 · 0/11 |

By year (₹ L; model vs coin median):

| | 2025 | 2026 (to 16 Oct) |
|---|---|---|
| L1 wl | 1.09 vs 1.23 | 1.26 vs 2.15 |
| L1 all | 0.61 vs 0.37 | 0.35 vs −0.03 |
| L2 wl | 0.90 vs 1.20 | 2.38 vs 2.21 |
| L2 all | 0.37 vs 0.48 | 0.34 vs −0.05 |
| L3 wl | 1.73 vs 1.15 | 2.27 vs 3.29 |
| L3 all | 0.59 vs 0.43 | −0.86 vs 0.05 |

## What this says

1. **No lab strategy beats production in this window.** The closest is A11 on the watchlist: ₹4.00 L at a 9.0 %
   drop (Calmar 4.15) vs production's ₹4.39 L at 5.8 % (6.18).
2. **The watchlist itself carries most of the 2025–26 money.** Random picks on the 21 watchlist names, held 20–60
   days, made ₹2.8–4.8 L (median ₹3.4–4.5 L) in this window. The same random picks on the whole liquid universe made
   −₹0.6 to +₹1.5 L. The watchlist was chosen in 2025–26, so that gap is mostly hindsight selection, not an entry
   edge. (The production entry signal still beats random entries on the same names in its own engine, TD-018
   EXP-20/22. So production's edge over the watchlist's own drift is real but much smaller than ₹4.39 L suggests.)
3. **On the whole universe, 2025–26 was a poor window for everyone.** A01 (₹0.96 L) and the production ranker
   (₹0.71 L) beat 10/11 coins. A11 lost money. Drops of about 15 % against Calmars below 1 are not a deployable
   sleeve on this window alone.
4. **On the watchlist, A01 picks don't beat random picks on ₹.** It needs the breadth of the universe to find its
   deep lows.
5. Same story as PB-LONG: judge on a multi-year, non-hindsight universe (the TD-022 `dayn` source, once its
   re-validation passes), not on 2025–26 watchlist numbers.

## Caveats

- **Not like-for-like on mechanics.**
  - The lab side is day bars, next-open fills, fixed holds or a +20 % target, and 2 picks a day.
  - Production is 15m/4h/day per stock, with the stale/trail/pattern-top exit stack and scale-in.
  - What *is* matched: window, capital and slot size.
- **The lab exits were picked in-sample** on 2011–26 (SC2/SC3). The production per-stock settings were picked on
  2025–26.
- **Survivor universe:** `day` from Kite lists only today's names.

Raw results: scratchpad `sc6_res.json`; per-sim outputs under `lab_data/model_lab/portfolios/SC6-*`.
