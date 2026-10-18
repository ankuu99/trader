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
