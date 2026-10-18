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
| SC1-0 | baseline | 15 × ₹40k, top-1 % causal threshold | DONE 2026-10-18 (S0 first sims) |
| SC1-1a | fewer, bigger slots | 7 × ₹80k, top-1 % | PLANNED |
| SC1-1b | fewer, bigger slots | 5 × ₹1.2L, top-1 % | PLANNED |
| SC1-2a | carry-over queue | 15 × ₹40k, top-1 %, queue 3 bars, drop if close > signal close +2 % | PLANNED (needs S0b) |
| SC1-2b | carry-over queue | as 2a, queue 5 bars | PLANNED (needs S0b) |
| SC1-3a | top-K per day | 15 × ₹40k, the best 1 score each day (no threshold) | PLANNED |
| SC1-3b | top-K per day | best 2 each day | PLANNED |
| SC1-3c | top-K per day | best 3 each day | PLANNED |
