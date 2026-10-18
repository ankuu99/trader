# SC1 — capacity study (TD-023), 2026-10-18

Owner: "Try all three options" (fewer bigger slots, carry-over queue, top-K per day). Configs pre-registered in
`STRATEGY_LEDGER.md`. All: A01 day scores (`A01_day_logit_t1z5`), ₹6L, sell after 20 bars, `trader.costs`, 2011–2026,
survivor-biased universe (TD-022). Each config run with the model, production P(min) and **21 coin draws** (stored
coin + seeds 101–120) on identical rows — the coin spread is the luck band.

| config | capital in use (model / coin median) | net ₹L model | production | coin median [10–90 %] | model beats coins | Calmar model | production | coin median [10–90 %] | model beats coins | max DD model / coin median |
|---|---|---|---|---|---|---|---|---|---|---|
| SC1-0 baseline 15×₹40k, top-1 % | 62 / 90 % | 7.28 | 6.38 | 7.14 [3.54–11.39] | 11/21 | 0.22 | 0.16 | 0.14 [0.06–0.29] | 17/21 | 34 / 51 % |
| SC1-1a 7×₹80k | 66 / 86 % | 3.85 | 2.65 | 6.81 [2.92–10.39] | 3/21 | 0.07 | 0.05 | 0.12 [0.04–0.25] | 4/21 | 55 / 56 % |
| SC1-1b 5×₹1.2L | 74 / 92 % | 5.59 | 2.87 | 8.20 [3.21–10.92] | 8/21 | 0.09 | 0.05 | 0.13 [0.04–0.26] | 8/21 | 68 / 64 % |
| SC1-2a queue 3 bars, +2 % cap | 63 / 92 % | 6.18 | 7.05 | 7.80 [4.96–8.82] | 4/21 | 0.15 | 0.18 | 0.16 [0.09–0.20] | 9/21 | 43 / 53 % |
| SC1-2b queue 5 bars, +2 % cap | 64 / 92 % | 6.57 | 6.59 | 7.60 [5.48–10.22] | 4/21 | 0.18 | 0.16 | 0.17 [0.12–0.21] | 12/21 | 40 / 49 % |
| SC1-3a best 1 per day | 72 / 92 % | 7.73 | 8.72 | 7.60 [3.84–10.66] | 11/21 | 0.24 | 0.23 | 0.13 [0.06–0.28] | 18/21 | 35 / 54 % |
| **SC1-3b best 2 per day** | **90 / 94 %** | **10.40** | 11.60 | 6.91 [4.05–9.35] | **19/21** | **0.27** | 0.30 | 0.14 [0.06–0.21] | **20/21** | 40 / 54 % |
| SC1-3c best 3 per day | 93 / 94 % | 10.15 | 11.34 | 6.74 [5.05–9.66] | 19/21 | 0.22 | 0.27 | 0.12 [0.08–0.22] | 19/21 | 48 / 57 % |

## Reading

1. **The luck band is wide.** One coin draw ranges ₹3.5 L–₹11.4 L on the same config. The single-coin comparisons in
   `S0_first_sims_20261018.md` (coin ₹7.57 L) and the first SC1 pass (coin top-3 ₹11.2 L) were one lucky draw; read
   every config against the band from now on.
2. **Top-K per day is the capacity fix.** Best 2 per day fills 90 % of capital and lifts A01 from ₹7.3 L to ₹10.4 L,
   beating 19 of 21 coins on ₹ and 20 of 21 on Calmar. Bigger slots concentrate risk (DD up to 68 %) and lose;
   the queue adds entries that are worse than the original picks (lows that kept falling, or the bounce already gone)
   and lowers ₹.
3. **But production P(min) does as well under the same framework**: best-2-per-day production ₹11.6 L / Calmar 0.30
   vs A01 ₹10.4 L / 0.27. Ranked across the whole universe each day, production's score is as good a money ranker as
   A01 at a 20-day hold. A01's detection win (AP, after-pick moves at the top-1 % rate) has not yet become a ₹ win.
4. In the threshold configs A01 wins on risk, not ₹: DD 34 % vs 51 % (coin) and 42 % (production) at baseline.

## Next (not run; for the owner)
- Exit study on the top-2-per-day framework (the exit is a fixed 20 bars; A01's picks need room — pain before peak).
- Hold horizon 5 / 20 / 60 bars at top-2: does A01's edge live at a different horizon than production's?
- Combine scores (A01 + production) — their picks may differ.
- Survivorship (TD-022) before any ₹ claim.
