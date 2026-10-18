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

## Arms

Arms tried so far: **0**.

| ID | Model | Target | TF | Universe | Split scheme | Pre-registered pass rule | Result | Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|
