# Model Lab — experiment ledger (TD-021)

One row per arm × split scheme, **written before the run** (multiple-testing discipline, docs/03 §8). Append-only: a
re-run gets a new row pointing at the old one. Every reported "win" quotes the number of arms tried so far.
Design: `docs/03_Model_Lab_Proposal.md`. Predecessor (inside-LR-Extrema arms): `reviews/extrema_campaign/LEDGER.md`.

Terms (owner, DECISIONS 2026-10-18): **model** = scores a candle as entry/exit and the coming move; **strategy** =
everything around it. The lab judges models with the strategy held fixed; negatives are scoped to the construct tested.

**Status vocabulary:** PLANNED · RUNNING · PASS (beats production P(min) on top-k payoff in most folds AND most years) ·
FAIL · NULL (no effect beyond noise) · PARTIAL (one regime/TF) · ABORTED (bug; see note).

## Infrastructure

| ID | Phase | Deliverable | Status | Guide / commit |
|---|---|---|---|---|
| ML-L0a | L0 | Parquet bar store, staged Kite fetcher, PIT liquidity universe, data QA | DONE 2026-10-18 | `to_develop/completed/2026-10-18_TD-021_L0a-lab-data-store-fetcher.md` |
| ML-L0b | L0 | Timeframe bars + `avail_ts`, causal factor library, targets T1–T5, leakage tests, build CLI | DONE 2026-10-18 | `to_develop/completed/2026-10-18_TD-021_L0b-bars-factors-targets.md` |
| ML-L1a | L1 | PIT panel, split engine (expanding/rolling/anchor/LOYO/stock groups, purge + embargo), lab model wrapper, walk-forward runner | DONE 2026-10-18 | `to_develop/completed/2026-10-18_TD-021_L1a-splits-runner.md` |
| ML-L1b | L1 | References (coin, RSI, lowest-of-N, production P(min) replay), curve scorer on hindsight truth, run report | DONE 2026-10-18 | `to_develop/completed/2026-10-18_TD-021_L1b-references-scoring.md` |
| ML-S01 | L1 | Pipeline smoke on real data (NOT an arm: 6 hindsight-picked watchlist names, 15m, expanding, `t1z_min_k5`, logistic) | DONE — pipeline OK; exposed + fixed the event-clustering flaw | `reviews/model_lab/runs/smoke_l1_logit_t1z5.md` |

## Arms

Arms tried so far: **4** (A01–A04 pre-registered 2026-10-18 before any run).

| ID | Model | Target | TF | Universe | Split scheme | Pre-registered pass rule | Result | Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| ML-A01 | pooled logistic (median impute + scaler, balanced) on all factors | `t1z_min_k5` | day (native) | PIT top-200 by trailing 252-session median traded value, re-ranked each Jan 1 (2009→) | expanding, 6M test windows, min train 3Y, embargo 5D | PASS = event-AP beats prod_pmin (day template replay) AND coin in ≥ 2/3 of folds AND ≥ 2/3 of years (≥ 10 pivots) on the primary truth (docs/03 §6); all-truths verdict reported alongside | event AP 0.295 vs prod 0.171 / coin 0.055; 32/32 folds, 16/16 yrs. After-pick (1 %): net 3.67 % vs prod 2.73 %, 12/16 yrs | PASS 2026-10-18 | `runs/A01_day_logit_t1z5` + `L2_day_round1_20261018.md` |
| ML-A02 | pooled HistGBDT (depth 3, 300 iters, balanced) on all factors | `t1z_min_k5` | day (native) | PIT top-200 by trailing 252-session median traded value, re-ranked each Jan 1 (2009→) | expanding, 6M test windows, min train 3Y, embargo 5D | PASS = event-AP beats prod_pmin (day template replay) AND coin in ≥ 2/3 of folds AND ≥ 2/3 of years (≥ 10 pivots) on the primary truth (docs/03 §6); all-truths verdict reported alongside | event AP 0.294 vs 0.171 / 0.055; 32/32, 16/16. After-pick ≈ prod (2.72 % vs 2.73 %), hit-rate 0.43 vs 0.37 | PASS 2026-10-18 | `runs/A02_day_hgb_t1z5` + `L2_day_round1_20261018.md` |
| ML-A03 | pooled logistic on all factors | `t1w_min_w10` | day (native) | PIT top-200 by trailing 252-session median traded value, re-ranked each Jan 1 (2009→) | expanding, 6M test windows, min train 3Y, embargo 5D | PASS = event-AP beats prod_pmin (day template replay) AND coin in ≥ 2/3 of folds AND ≥ 2/3 of years (≥ 10 pivots) on the primary truth (docs/03 §6); all-truths verdict reported alongside | event AP 0.471 vs prod 0.245 / coin 0.150; 32/32, 16/16. After-pick BELOW prod (1.81 % vs 2.73 %) | PASS 2026-10-18 (detection only) | `runs/A03_day_logit_t1w10` + `L2_day_round1_20261018.md` |
| ML-A04 | pooled HistGBDT on all factors | `t1w_min_w10` | day (native) | PIT top-200 by trailing 252-session median traded value, re-ranked each Jan 1 (2009→) | expanding, 6M test windows, min train 3Y, embargo 5D | PASS = event-AP beats prod_pmin (day template replay) AND coin in ≥ 2/3 of folds AND ≥ 2/3 of years (≥ 10 pivots) on the primary truth (docs/03 §6); all-truths verdict reported alongside | event AP 0.520 vs 0.245 / 0.150; 32/32, 16/16. After-pick BELOW prod (1.30 % vs 2.73 %) | PASS 2026-10-18 (detection only) | `runs/A04_day_hgb_t1w10` + `L2_day_round1_20261018.md` |
