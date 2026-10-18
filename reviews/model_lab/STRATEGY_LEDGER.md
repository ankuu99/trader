# Strategy ledger (TD-023) — every portfolio-simulation configuration, registered before it runs

Simulator: `research/model_lab/portfolio.py`. Every config is run with three score sources on identical rows, slots and
exits — the model, a coin (`ref:coin`) and production P(min) (`ref:prod_pmin`). Universe survivor-biased (TD-022):
read ₹ relative to the coin. **No configuration is promoted while the model is not frozen** (docs/04): these are
studies of the framework, not tuning.

## SC1 — capacity (owner: "Try all three options", 2026-10-18)

Problem (`S0_first_sims_20261018.md`): A01's picks bunch on sell-off days → 38 % of capital idle at 15 × ₹40k.
Common: run `A01_day_logit_t1z5`, day bars, ₹6L, exit = sell after 20 bars (the clean exit; stop/trail is a separate
study), costs `trader.costs`. Read: capital in use, net ₹, ₹/trade, money-weighted win %, max DD, Calmar, model vs
coin vs production; per year in the reports.

| ID | Option | Config | Status |
|---|---|---|---|
| SC1-0 | baseline | 15 × ₹40k, top-1 % causal threshold | DONE — ₹7.28 L (= coin median, 11/21), Calmar 0.22 (17/21), DD 34 % vs coin 51 %, use 62 % |
| SC1-1a | fewer, bigger slots | 7 × ₹80k, top-1 % | DONE — worse: ₹3.85 L, Calmar 0.07 (beats 4/21 coins); capital use 66 % |
| SC1-1b | fewer, bigger slots | 5 × ₹1.2L, top-1 % | DONE — worse: ₹5.59 L, Calmar 0.09 (8/21); use 74 % |
| SC1-2a | carry-over queue | 15 × ₹40k, top-1 %, queue 3 bars, drop if close > signal close +2 % | DONE — no help: ₹6.18 L, Calmar 0.15 (9/21); use 63 % |
| SC1-2b | carry-over queue | as 2a, queue 5 bars | DONE — no help: ₹6.57 L, Calmar 0.18 (12/21); use 64 % |
| SC1-3a | top-K per day | 15 × ₹40k, the best 1 score each day (no threshold) | DONE — ₹7.73 L, Calmar 0.24 (18/21); use 72 % |
| SC1-3b | top-K per day | best 2 each day | DONE — **best**: ₹10.40 L (19/21 coins), Calmar 0.27 (20/21), use 90 %; production same config ₹11.60 L / 0.30 |
| SC1-3c | top-K per day | best 3 each day | DONE — ₹10.15 L (19/21), Calmar 0.22 (19/21), use 93 %; production ₹11.34 L / 0.27 |

Luck band: each config also run with 20 extra coin seeds (`coin:101…120`) + the stored coin = 21 draws; "x/21" = coins the model beats. Results and reading: `reviews/model_lab/SC1_capacity_20261018.md`.

## SC2 — hold duration (owner: "Try different hold durations", 2026-10-18)

Day: SC1-3b framework (A01, ₹6L, 15 × ₹40k, best 2 per day, no stop/target/trail), exit = sell after H bars.
15m: A05, ₹6L, 15 × ₹40k, top-1 % causal threshold (the S0 baseline; top-K per 15m bar would trade ~50 a day),
sell after H bars. Each with model, production P(min) and coins (day 21 draws, 15m 11 draws).

| ID | TF | H (bars) | ≈ | Status |
|---|---|---|---|---|
| SC2-d5 | day | 5 | 1 week | DONE — all lose (costs); A01 −₹0.74 L, prod +₹5.70 L |
| SC2-d10 | day | 10 | 2 weeks | DONE — A01 ₹4.17 L (15/21), prod ₹9.29 L |
| SC2-d20 | day | 20 | 1 month (= SC1-3b) | DONE — A01 ₹10.40 L (19/21), Calmar 0.27 (20/21); prod ₹11.60 L / 0.30 — A01's best H |
| SC2-d40 | day | 40 | 2 months | DONE — A01 ₹7.15 L (4/21) fades; prod ₹12.31 L / 0.32 |
| SC2-d60 | day | 60 | 3 months | DONE — A01 ₹4.31 L (1/21), DD 70 %; **prod ₹11.54 L, Calmar 0.39, DD 31 %** |
| SC2-m25 | 15m | 25 | 1 session | DONE — everyone loses heavily (cost churn, 18k trades) |
| SC2-m125 | 15m | 125 | 1 week (= S0 15m) | DONE — A05 −₹4.77 L (0/11), prod −₹2.15 L |
| SC2-m500 | 15m | 500 | 1 month | DONE — **A05 ₹6.27 L, Calmar 0.36 (11/11 coins), DD 31 % vs coin 52 %**; prod ₹3.95 L / 0.11 |

SC2 results and reading: `reviews/model_lab/SC2_hold_20261018.md`.

## SC3 — exits on the two best SC2 frameworks (owner: "Do all three", 2026-10-18)

Frameworks: **P60** = production P(min) score, day, best 2 per day, max hold 60 bars; **M500** = A05 score, 15m,
top-1 % causal threshold, max hold 500 bars. ₹6L, 15 × ₹40k. Each exit set run with the framework's score and 11
coin draws (stored + seeds 101–110); P60 also with A01's score, M500 also with production's (cross-reference).
Fractions: stop/target vs entry price; trail = drop from the highest close since entry, active once that close is
≥ entry × (1 + activate).

| ID | Exit set | Status |
|---|---|---|
| SC3-x0 | none (time only) = SC2 baseline | PLANNED (re-run) |
| SC3-x1 | stop −20 % (production's black-swan stop) | PLANNED |
| SC3-x2 | stop −10 % | PLANNED |
| SC3-x3 | trail 10 % after +10 % | PLANNED |
| SC3-x4 | trail 15 % after +10 % | PLANNED |
| SC3-x5 | target +20 % | PLANNED |
| SC3-x6 | stop −20 % + trail 10 % after +10 % | PLANNED |

## SC4 — combined ranking, per-pick hold (owner, 2026-10-18; needs simulator S0c)

Day, ₹6L, 15 × ₹40k, best 2 per day from one pooled ranking of A01 and production P(min); each score converted to its
causal percentile (vs its own previous 60 sessions); a pick holds 20 bars if it came from A01, 60 if from production.
Controls: same with coin percentiles; and the two sleeves split (7 slots A01/20d + 8 slots production/60d, summed).

| ID | Config | Status |
|---|---|---|
| SC4-a | pooled A01 (hold 20) + production (hold 60), best 2/day | PLANNED (needs S0c) |
| SC4-b | split sleeves: 7 × ₹40k A01 best-1/day hold 20 + 8 × ₹40k production best-1/day hold 60 | PLANNED |
