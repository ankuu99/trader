# SC3 exits and SC4 combined ranking (TD-023), 2026-10-18

Owner: "Do all three". Pre-registered in `STRATEGY_LEDGER.md`. ₹6L, 15 × ₹40k, `trader.costs`, survivor-biased
universe (TD-022 — in progress; every ₹ below is inflated in absolute terms, compare against the coins).
**Seven exit sets were tried per framework: picking the best of seven is in-sample selection.** The winner needs a
walk-forward choice (exit chosen on earlier years only) and the survivorship-free data before it means anything.

## SC3 — exits

**P60** = production P(min) score, day bars, best 2 per day, max hold 60 days (11 coin draws; A01 shown as reference)

| exits | net ₹L | A01 same exits | coin median [10–90 %] | beats coins ₹ | Calmar | A01 | coin median | beats coins | max DD % / coin median | money-wtd win % | avg held | ex-2020 ₹L |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| none (time 60) | 11.54 | 4.31 | 11.41 [8.34–12.95] | 7/11 | 0.39 | 0.06 | 0.25 | 10/11 | 31 / 47 | 60.1 | 60 | 10.51 |
| stop −20 % | 12.05 | 11.05 | 9.51 [6.72–12.73] | 9/11 | 0.35 | 0.25 | 0.20 | 11/11 | 36 / 51 | 59.3 | 52 | 9.77 |
| stop −10 % | 4.14 | 8.88 | 7.70 [5.60–9.97] | 0/11 | 0.08 | 0.20 | 0.14 | 1/11 | 54 / 56 | 52.8 | 39 | 2.71 |
| trail 10 % after +10 % | 12.13 | 8.16 | 8.77 [5.47–11.50] | 11/11 | 0.42 | 0.14 | 0.20 | 11/11 | 30 / 49 | 61.2 | 52 | 11.67 |
| trail 15 % after +10 % | 12.94 | 6.87 | 9.04 [7.83–12.14] | 11/11 | 0.44 | 0.12 | 0.21 | 11/11 | 31 / 46 | 61.4 | 55 | 12.02 |
| **target +20 %** | **14.57** | 9.22 | 9.90 [8.71–11.02] | **11/11** | **0.50** | 0.22 | 0.27 | **11/11** | 31 / 40 | 61.6 | 51 | 12.90 |
| stop −20 % + trail 10 % | 13.90 | 8.20 | 8.97 [6.91–11.39] | 11/11 | 0.36 | 0.20 | 0.21 | 11/11 | 41 / 49 | 60.1 | 45 | 13.23 |

**M500** = A05 score, 15m bars, top-1 % causal threshold, max hold 500 bars ≈ 1 month (production shown as reference)

| exits | net ₹L | production | coin median [10–90 %] | beats coins ₹ | Calmar | production | coin median | beats coins | max DD % / coin median | money-wtd win % | ex-2020 ₹L |
|---|---|---|---|---|---|---|---|---|---|---|---|
| none (time 500) | 6.27 | 3.95 | 6.38 [5.32–7.15] | 5/11 | 0.36 | 0.11 | 0.21 | 11/11 | 31 / 52 | 56.2 | 4.77 |
| stop −20 % | 5.15 | 3.28 | 6.25 [5.35–6.99] | 1/11 | 0.17 | 0.11 | 0.18 | 5/11 | 53 / 59 | 54.7 | 3.41 |
| stop −10 % | 4.05 | 2.84 | 4.99 [3.51–6.66] | 2/11 | 0.13 | 0.11 | 0.16 | 5/11 | 55 / 63 | 53.2 | 2.35 |
| **trail 10 % after +10 %** | **7.56** | 4.39 | 4.78 [4.21–7.71] | **9/11** | **0.37** | 0.18 | 0.15 | **11/11** | 37 / 58 | 57.4 | 5.17 |
| trail 15 % after +10 % | 3.58 | 4.17 | 6.20 [5.40–7.37] | 0/11 | 0.13 | 0.16 | 0.18 | 1/11 | 49 / 59 | 53.6 | 2.53 |
| target +20 % | 3.94 | 4.24 | 5.68 [4.23–7.12] | 0/11 | 0.16 | 0.13 | 0.19 | 5/11 | 44 / 54 | 53.8 | 1.81 |
| stop −20 % + trail 10 % | 5.60 | 4.00 | 5.65 [4.87–6.84] | 5/11 | 0.26 | 0.15 | 0.19 | 10/11 | 38 / 58 | 55.0 | 2.87 |

Reading:
1. **Tight stops destroy both** (−10 %: P60 ₹11.5 L → ₹4.1 L). The lows these scores buy dip further before they
   turn; a −20 % black-swan stop is harmless, a −10 % one is not — the same lesson as production's own history
   (tighter stops falsified 2026-07-05).
2. **Day P60: taking profit helps.** A +20 % target lifts ₹11.5 L → ₹14.6 L and Calmar 0.39 → 0.50, beating all 11
   coins on both; the trailing stops help less (Calmar 0.42–0.44).
3. **15m M500: only the 10 % trail after +10 % helps** (₹7.6 L, Calmar 0.37, 9/11 and 11/11 coins); target and the
   wider trail hurt. The two frameworks want different exits — consistent with "exits must suit the model".
4. A01's scores under the P60 framework stay well below production's at every exit.

## SC4 — combined ranking

| config | net ₹L | trades | Calmar | max DD % | money-wtd win % | vs 10 coin pairs ₹ / Calmar |
|---|---|---|---|---|---|---|
| SC4-a pooled (A01 hold 20 + production hold 60), best 2/day | 11.26 | 1,360 | 0.34 | 35 | 59.0 | 9/10 / 9/10 |
| SC4-b split sleeves (7 slots A01 + 8 slots production) | 7.31 | 1,837 | 0.18 | 44 | 54.7 | 2/10 / 4/10 |
| reference: production alone, P60 no exits | 11.54 | 976 | 0.39 | 31 | 60.1 | — |

Inside SC4-a the production picks earned ₹8.70 L and A01's ₹2.56 L. **Combining adds nothing over production alone**
and splitting the capital is worse.

## Where this leaves the framework (TD-023)
- The strongest result so far is the **existing production P(min) used as a whole-universe daily ranker** (best 2 per
  day, hold up to 3 months, +20 % target, −20 % disaster stop optional), not a new lab model. A01's lab detection win
  has not converted into ₹ under any framework tried.
- For 15m, A05 with a 1-month hold and a 10 % trail after +10 % is the one setup that beats coins on risk.
- Before trusting either: (a) survivorship-free re-run (TD-022 L0c, in build), (b) exit chosen walk-forward, not as
  the best of seven in hindsight.
