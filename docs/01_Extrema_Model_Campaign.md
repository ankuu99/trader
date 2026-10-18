# 01 — Trough/peak model evaluation campaign (protocol)

Written 2026-10-18 · Owner-approved plan 2026-10-18 ("fix ISS-14 then go ahead with this plan") · Tracker: TD-018.
Inventory & motivation: `reviews/extrema_model_research_inventory_20261018.md`. Ledger (every path, past and
future): `reviews/extrema_campaign/LEDGER.md`. Literature: `docs/02_Extrema_Literature_Review.md`.

Everything below is fixed **before** any arm is run. Changing a rule requires a DECISIONS.md row and a ledger note;
never change a rule after seeing a result.

## Question

The owner sees the bot missing good troughs. Prior work (ledger R-01, R-15) showed the production P(min) is a
"bar closed at its low" detector, and that better dip *identification* lost money because the extra dips were
shallow and the exit stack kills them. The campaign therefore asks: **can a different label / feature / model
rank "troughs that pay under our exits" better, and does that reach portfolio P&L?**

## Baseline (EXP-00)

`config/config.yaml` as of commit 5970eb5 (post-ISS-14 engine), unchanged: scale-in on, loss block 3 sessions,
₹6L @ 6.67 %, current 21-name watchlist with per-stock TF blocks. Runs:
`reviews/extrema_campaign/runs/baseline_postfix_iss14.json` (Stage B) and `runs/stage_a_baseline.json` (Stage A).

## Stage A — detection quality (`scripts/campaign/stage_a.py`)

- **Score run:** one cache-only portfolio backtest 2023-01-01 → 2026-10-16 with the engine's `model_scores` sink —
  the exact walk-forward (p_min, p_max) series each stock's strategy produced on its own strategy TF.
- **Truth ("tradeable trough"), model-independent, per stock:** bar t is good iff a long entered at close[t]
  reaches +`profit_pct` (trail arming) before any non-model exit fires on the close path — hard stop, stale tier-1,
  stale re-arm, stale_2, hold_bars — using that stock's own params. The same simulation gives the bar's outcome
  return (+profit_pct on success, else the exit return) = **EV proxy**, and its exit bar.
- **Windows:** calibration 2023-01-01 → 2024-12-31 · test 2025-01-01 → 2026-10-16.
- **Matched threshold:** per stock, the threshold whose firing count over the calibration window equals the
  baseline's at its configured threshold. Firings are deduped by position blocking (the next firing counts only after
  the previous one's simulated exit). Calibration never sees the test window.
- **Metrics (test window):** AUC(p_min vs good) over all bars; at the matched threshold: firings, precision, lift
  over the base rate, EV, event recall. ATHERENERG also scored against the 191 hand-labelled dips (±1 bar).
- **Gate to Stage B:** (median ΔAUC ≥ +0.03 **and** ΔAUC < 0 on ≤ ⅓ of stocks) **or** (median ΔEV@matched ≥
  +0.25 pp **and** ΔEV < 0 on ≤ ⅓ of stocks).

## Stage B — portfolio P&L (`scripts/campaign/run_windows.py`)

- Arm overlay + the Stage-A matched-threshold overlay, deep-merged onto the baseline config, cache-only.
- **Windows:** H1-25, H2-25, H1-26, H2-26 (2026-07-01 → 10-16), FULL 2025-01-01 → 2026-10-16, HORIZON
  2020-01-01 → 2026-10-16. Each an independent run from config capital. HORIZON is a robustness/crash check, not
  out-of-sample (thresholds were calibrated on 2023–24, inside it).
- **Pass:** Calmar ≥ baseline in ≥ 3/4 half-years **and** FULL P&L ≥ baseline **and** FULL DD ≤ baseline + 1 pp.
- Report trades, utilisation, exit-reason **counts** (never per-reason win rates), per-stock P&L. A pass on Stage B
  is a *candidate*, not a deployment: config/release needs the owner's go.

## Arms (one worktree per family, branch `exp/<family>`)

Each family is built from a `to_develop/` guide by the implementer, behind default-off config flags, with tests.
The main session validates (full pytest + diff), runs both stages, and writes the review.

| ID | Family (worktree) | Arm | Config sketch |
|---|---|---|---|
| EXP-01 | W1 labels | **Tradeable-trough labels:** class 0 = geometric minima whose forward path pays (+profit_pct before the exit sim fails); failed minima → class 2 (neutral); class 1 = geometric maxima unchanged | `labels.type: tradeable` |
| EXP-02 | W1 labels | Same, candidates = every `stride`-th bar (dense "would an entry here pay") | `labels.tradeable.candidates: all` |
| EXP-03 | W1 labels | `forward_label` re-test on the fixed engine (config only) | `forward_label.enabled: true` |
| EXP-04 | W2 path/shape | Lag stacking: append the t-1, t-2 feature vectors (any pipeline) | `features.lags: [1, 2]` |
| EXP-05 | W2 path/shape | Reversal bar shape: lower-wick ratio, body ratio, close-off-low × volume | `features.bar_shape.enabled` |
| EXP-06 | W2 path/shape | ATR-scaled trend distance: (close−EMA20)/ATR14, ATR14/close | `features.atr_dist.enabled` |
| EXP-07 | W3 market | Relative strength vs Nifty, Nifty drawdown, VIX level & change (backtest only; needs Nifty/VIX history) | `features.market.enabled` |
| EXP-08 | W4 structure | Touch-counted support/resistance: distance to support/resistance, touch count | `features.sr.enabled` |
| EXP-09 | W5 baselines | No-ML rules model (RSI14<35 + up-close + above EMA50; lowest-of-20 + up-close) | `model.type: rules` |
| EXP-10 | W5 baselines | OU s-score (Avellaneda–Lee) as features and as a rule | `features.ou.enabled` / `model.type: rules` |
| EXP-11+ | — | Arms proposed by the literature review / combinations of Stage-B passes | appended |

Arms that pass Stage A in more than one family are combined (EXP-11+) before Stage B where cheap.

## Documentation rules

- Every arm gets a ledger row **before** it runs; the row is updated with Stage A/B results and a status.
- Per-arm review: `reviews/extrema_campaign/EXP-NN_<slug>.md` (hypothesis, exact overlay, both stages' tables,
  verdict, what it rules out).
- Raw outputs: `reviews/extrema_campaign/runs/*.json` (committed). Score caches: `lab_data/campaign/scores/`
  (git-ignored, reproducible).
- Losing arms' code stays on their pushed `exp/*` branch (the ledger cites branch + commit). Only arms that pass
  Stage B merge to the main line, still default-off.
- Literature-derived arms cite `docs/02_Extrema_Literature_Review.md`.

## Operational notes

- All runs are `--cache-only` equivalents (no Kite fetch, no cache wipe). The 15m cache covers 2017-12 → 2026-10-16
  for the watchlist; Nifty/VIX 15m only 2023-11 → 2026-08-31 (EXP-07 needs a backfill first).
- Worktrees: `../trader-2-wt/<family>`, with `data/` and `config/.env` symlinked to the main checkout (runs are
  read-only on the candle cache).
- Runtime: logistic-model windows run in minutes; gbdt/long-lookback arms are much slower (~2 h per 18 months in
  July) — budget accordingly.
