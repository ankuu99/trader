# Model Lab L1b — reference scores (coin, rules, production replay), curve-based scorer, run report
Written: 2026-10-18 · Tag: TD-021 · Status: OPEN

## Source

> no, again you will end up digressing, i already told we do not want to be contaiend in the current construct. why
> are we restricting ourselves to the current bouadaries of the straetgy? why restrict to same number of picks? if we
> are finding more entries andexists so be it, why restrict? that will not help us find the right model then. strategy
> part comes later.

— owner, 2026-10-18 (this session; recorded in DECISIONS 2026-10-18 and `docs/03_Model_Lab_Proposal.md` §6 on
`exp/model-lab`). Tracker: `TODO/TD-021-model-lab-outside-lr-extrema/`. Sibling guide built in parallel (shares no
files): `to_develop/2026-10-18_TD-021_L1a-splits-runner.md` — read its **"Run-directory contract"** section; this guide
only READS run directories in that format. Built on L0 (`to_develop/completed/2026-10-18_TD-021_L0*.md`).

## Intent

Score any model **on its own terms** against hindsight truth, across ALL firing rates, with production LR-Extrema
P(min), a coin and simple rules as reference curves — never through the strategy:

1. **Reference scores** per (tf, symbol): coin, RSI, lowest-of-N turn (and their top-side mirrors), and the
   **production P(min)/P(max) replayed** on the lab's bars for any stock.
2. **Scorer:** event-based turning-point curves (catch rate, precision, lateness, distance from the low) over a grid of
   firing rates; turn-classification metrics; move-size / path rank correlations and quantile helpers; an
   after-pick profile (potential, pain, hold, net-of-cost return — informational); per fold / year / regime breakdowns;
   a dominance verdict.
3. **Report** written to `reviews/model_lab/runs/<run_id>.md` plus machine-readable files in the run directory.

**Must NOT change:** anything outside `research/model_lab/{references,score,report}.py`, `scripts/model_lab/`, and the
new test files. `research/model_lab/*` must not import `trader.strategies`/`features`/`policy`/`backtest`; ONLY
`scripts/model_lab/prod_pmin.py` may import `trader.strategies` (it is the production replay). Do not edit
`paths.py` (`RUNS_DIR`, `REFS_DIR` already exist) or any L1a file (`source.py`, `splits.py`, `models.py`,
`runner.py`). Read-only use of L0 modules (`bars`, `factors`, `targets`, `store`, `universe`).

## Implementation steps

### 1. `research/model_lab/references.py`
```python
REFS_MIN = ("coin", "rsi", "low10", "low20", "low50")
REFS_MAX = ("coin", "rsi_hi", "high10", "high20", "high50")
def ref_scores(bars: pd.DataFrame, name: str, symbol: str, seed: int = 11) -> np.ndarray
def write_refs(tf: str, symbols: list[str], names: list[str], seed: int = 11) -> None
def read_ref(tf: str, name: str, symbol: str) -> pd.DataFrame | None   # timestamp, score[, p_max]; None if missing
```
- `coin`: `np.random.default_rng([seed, int(md5(symbol).hexdigest()[:8], 16)]).random(len(bars))`.
- `rsi`: `100 − rsi_14` (from `factors.own_factors`); `rsi_hi`: `rsi_14`. NaN where RSI is NaN.
- `low{N}`: 1.0 when close[t] > close[t−1] AND close[t−1] == min(close[t−N … t−1]); else 0.0 (NaN for t < N).
  `high{N}` mirrored (close[t] < close[t−1] AND close[t−1] == max(close[t−N … t−1])).
- Storage `paths.REFS_DIR/<tf>/<name>/<SYM>.parquet`: `timestamp` datetime64[ns], `score` float32 (zstd, atomic
  write, `check_disk()` first). CLI: `python -m research.model_lab.references --tf 15m [--symbols …] [--refs …]`
  (default symbols: every symbol with source bars, minus the index symbols; default refs: REFS_MIN + REFS_MAX deduped).

### 2. `scripts/model_lab/prod_pmin.py` — production P(min)/P(max) replay (the reference to beat)
`.venv/bin/python scripts/model_lab/prod_pmin.py --tf 15m [--symbols …] [--params global|per-stock] [--workers N]`
- Bars: `research.model_lab.bars.load(symbol, tf)`.
- Params: `global` → `config.strategy_config("lr_extrema")`; `per-stock` → `config.get_strategy_params(symbol,
  "lr_extrema")` only when `config.strategy_timeframe(symbol)` corresponds to `tf` (`15minute`↔`15m`, `4hour`↔`4h`,
  `day`↔`dayagg`), else global (log which was used per symbol).
- `strat = LRExtremaStrategy(symbol, params)`; for each bar in order: `strat.on_candle({"timestamp": <python
  datetime>, "open", "high", "low", "close", "volume"})`, then `s = strat.score_current()` → `p_min, p_max` (NaN, NaN
  when None). `score_current` is pure and position-independent (it is exactly what the backtest engine's
  `model_scores` sink records), and retraining is not gated by position state, so the replay needs no order fills.
  Ignore returned signals.
- Write `paths.REFS_DIR/<tf>/prod_pmin/<SYM>.parquet` (`timestamp`, `score` = p_min, `p_max`) and the mirror
  `paths.REFS_DIR/<tf>/prod_pmax/<SYM>.parquet` (`timestamp`, `score` = p_max) so top-side targets can use it.
  `meta.json` beside them: params mode per symbol, config hash (sha1 of the json-dumped params), seconds per symbol.
- `--workers N` → `ProcessPoolExecutor` over symbols (each process imports config itself).
- Silence strategy logging below WARNING inside workers.

### 3. `research/model_lab/score.py`
```python
RATES = [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2]   # share of bars at/above the threshold
TOL = {tf: targets.SCALES[tf][0] for tf in targets.SCALES}          # match tolerance in bars (15m: 4)
BARS_PER_YEAR = {"15m": 25*248, "30m": 13*248, "60m": 7*248, "4h": 2*248, "dayagg": 248, "day": 248, "week": 52}
COST = 0.0022
def picks(score: np.ndarray, tau: float, tol: int) -> np.ndarray          # positions of cluster starts
def match_events(pick_pos, pivot_pos, tol) -> list[tuple[int, int]]       # greedy one-to-one, nearest first
def event_counts(score, truth, pos, low, high, close, tau, tol, side) -> dict
def event_ap(points: list[dict]) -> float
def spearman(a, b) -> float
def pinball(y, pred, q) -> float
def coverage(y, lo, hi) -> float
def score_run(run_id: str, refs: list[str], targets: list[str] | None = None, tf: str | None = None) -> dict
```
Definitions (exact):
- **Rows evaluated:** for each symbol in the run, the run's score rows (all folds), left-joined on `timestamp` with
  every listed ref; the evaluation set is rows where the model score AND every listed ref score are non-NaN. Report
  per-ref coverage (= share of the run's rows where that ref is non-NaN) in the summary. Positions (`pos`) are row
  numbers in the symbol's full `bars.load(symbol, tf)` frame, so distances are in bars even when rows are missing.
  Truth/targets: `targets.build_targets(bars, tf)`.
- **Picks (events, not bars):** firing bars = evaluated rows with score ≥ τ; consecutive firings whose position gap is
  ≤ `tol` form ONE pick, located at its first firing bar.
- **Pivots:** evaluated rows where the truth column == 1 (rows where truth is NaN are neither pivots nor judgeable;
  picks located on such rows are counted as `unjudged` and excluded from precision).
- **Matching:** pick p matches pivot q when |pos_p − pos_q| ≤ tol; one-to-one, process candidate pairs in increasing
  |distance| (ties: earlier pick first).
- `event_counts` → `{picks, unjudged, matched, pivots, lateness_med (pos_p − pos_q over matches; negative = early),
  dist_med_pct (min-side: 100·(close[p]/low[q] − 1); max-side: 100·(1 − close[p]/high[q])), bars}`.
- **Threshold per rate:** for each (fold, model) τ_r = the (1 − r) quantile of that model's scores over the fold's
  evaluated rows (pooled across symbols). Binary scores (rules) collapse to their natural threshold; keep the points as
  computed (duplicates allowed). Counts are summed over symbols (micro-average): `precision = matched / (picks −
  unjudged)`, `recall = matched / pivots`, `picks_per_stock_year = picks / (bars / BARS_PER_YEAR[tf])`.
- **`event_ap(points)`** (threshold-free summary of a curve): sort points by recall ascending, drop duplicate recalls
  keeping the max precision, AP = Σ (R_i − R_{i−1}) · P_i with R_0 = 0.
- **Turn (T2):** for `t2_up_h*` (min side) / `t2_dn_h*` (max side): bar-level ROC-AUC and average precision
  (`sklearn.metrics`) of each model's score over evaluated rows with defined truth, per fold.
- **Move size / path:** per fold, Spearman of each model's score with realised `t3_ret_k5`, `t4_ret_h16`, and for the
  middle hold horizon H = `HOLD_H[tf][1]`: `t5_mfe_H{H}`, `t5_maepre_H{H}`, `t5_ttm_H{H}`. If the run's scores have
  `pred_<target_col>` columns, also Spearman(pred, realised target_col); for `pred_<target_col>_q<NN>` columns (NN = 05,
  50, 95 …) report `pinball` at q = NN/100 and `coverage` of the outermost pair.
- **After-pick profile (informational, money-aware view, never a pass condition):** at rates 0.002, 0.01, 0.05 over
  all picks (pooled): mean and median of `t5_mfe_H{H}`, `t5_maepre_H{H}`, `t5_ttm_H{H}`, `t5_ret_H{H}`, the net
  `t5_ret_H{H} − COST`, and the rate of `t5_hit_x5_y3_H{H}` (picks with NaN T5 excluded and counted).
- **Breakdowns of event AP** (same pooled-count method): per fold; per calendar year (rows pooled over folds by the
  year of `timestamp`); per VIX regime (tercile of prior-day VIX percentile: `< 1/3`, `< 2/3`, else — from
  `store.read_bars("NSE:INDIA VIX", "day")`: `close.rolling(252, min_periods=200).rank(pct=True)`, joined strictly to
  the previous date); per Nifty trend (prior-day `NIFTY 50` day close / close 50 sessions earlier − 1: > +3 % up,
  < −3 % down, else flat). Regimes missing data → bucket `na`.
- **Verdict** for each detection truth column and each ref: `fold_win_share` = share of folds with ≥ 10 pivots where
  model AP > ref AP; `year_win_share` likewise over years with ≥ 10 pivots. **WIN vs a ref = both ≥ 2/3.** Overall
  **PASS = WIN vs `prod_pmin` (or `prod_pmax` for max-side truth) AND WIN vs `coin`.** Otherwise FAIL. When prod is not
  in `refs`, overall = `NO_REF`.
- Detection truth columns evaluated: the run's target if it is a `t1w_*`/`t1z_*` column, plus every `t1w_{side}_w*`
  and `t1z_{side}_k*` of the TF (side = min or max from the run target's name; t2/t3/t4/t5 targets → side min).
- `score_run` returns and writes `RUNS_DIR/<run_id>/score_summary.json` (verdicts, AP per fold/year/regime per model,
  T2/Spearman tables, after-pick profile, coverage) and `RUNS_DIR/<run_id>/curves.parquet` (columns: `scope`
  (`all`/`fold`/`year`), `key`, `model`, `truth`, `rate`, `tau`, `picks`, `unjudged`, `matched`, `pivots`,
  `precision`, `recall`, `picks_per_stock_year`, `lateness_med`, `dist_med_pct`).
- Model name in outputs: `model` = `meta.json["model"]` for the run, ref names as given.

### 4. `research/model_lab/report.py`
`python -m research.model_lab.score --run <run_id> --refs prod_pmin coin rsi low10 low20 low50` runs `score_run`
then writes `reviews/model_lab/runs/<run_id>.md`:
- header: run meta (tf, scheme, target, model, universe, folds, rows), **arms tried so far** = number of data rows in
  the "## Arms" table of `reviews/model_lab/LEDGER.md`, ref coverage;
- verdict table (truth × ref: fold/year win shares, WIN/—) and the overall PASS/FAIL/NO_REF line;
- pooled curve table per truth column: one row per rate, columns per model `prec / recall / picks per stock-year`;
- per-year and per-fold AP tables (models as columns); regime tables;
- T2 AUC/AP table; Spearman table; after-pick profile table (labelled "informational — not a pass condition");
- a footer line: "Scored on the model's own terms (docs/03 §6): hindsight truth across all firing rates; the strategy
  does not judge the model."
Plain markdown tables, numbers rounded (precision/recall 3 dp, AP 4 dp, % 2 dp).

## Tests required

New file `tests/test_model_lab_score.py` (synthetic, tmp dirs via monkeypatching `paths.RUNS_DIR`/`REFS_DIR`/
`BARS_DIR`; no network, no `lab_data/`):
- `test_picks_cluster_events` — firings at positions 10, 11, 13, 30 with tol 4 → picks at 10 and 30.
- `test_match_events_one_to_one_nearest` — two picks near one pivot → one match (the nearer); a pick between two
  pivots matches the nearer; tolerance boundary inclusive.
- `test_event_counts_lateness_and_distance` — hand series: pivot low at pos 50 (low 100), pick at 52 with close 101.5
  → lateness +2, dist 1.5 %; unjudged pick on a NaN-truth row excluded from precision.
- `test_event_ap_hand_points` — known (recall, precision) points → exact AP; duplicate recalls keep max precision.
- `test_perfect_and_random_scores` — synthetic bars + targets: score = truth (+ tiny noise) → recall ≈ 1 at the
  pivot rate and AP > 0.9; coin → AP ≈ pivot base rate (± tolerance); perfect beats coin in the verdict.
- `test_score_run_contract_end_to_end` — build a fake run dir in tmp (meta.json, folds.parquet with 2 folds,
  scores/<SYM>.parquet for 3 synthetic symbols with bars written via `store.write_bars` into a tmp `BARS_DIR`), refs
  written with `write_refs`; `score_run` writes `score_summary.json` + `curves.parquet` with the specified columns;
  verdict keys present; report markdown produced (patch the reviews output dir to tmp — expose
  `report.REPORT_DIR` as a module constant).
- `test_pinball_and_coverage` — hand values.
- `test_refs_rules` — `low10`/`high10` fire exactly where defined; `coin` deterministic per (seed, symbol) and
  different across symbols.

New file `tests/test_model_lab_prod_replay.py`:
- `test_prod_replay_matches_score_current` — synthetic 15m (40 sessions), params = global config params with
  `warmup_bars=100, lookback_bars=300, retrain_every=25` overridden; run the replay function (expose
  `replay_symbol(bars, symbol, params) -> pd.DataFrame` in `scripts/model_lab/prod_pmin.py`, importable via
  `importlib` from its path) → NaN before the model is trained, finite after; deterministic across two runs; equals an
  independent `LRExtremaStrategy` fed the same bars and queried with `score_current()` at 3 checked bars.

Suites that stay green: the full suite.

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] scoring is threshold-curve based over RATES; events not bars; no matched-pick-count anywhere; no strategy exits
- [ ] after-pick profile and net-of-cost labelled informational, never part of the verdict
- [ ] reads the L1a run-directory contract exactly; no L1a file or `paths.py` edited
- [ ] only `scripts/model_lab/prod_pmin.py` imports `trader.strategies`
- [ ] report written to `reviews/model_lab/runs/<run_id>.md` with the arms-tried count
- [ ] report the replay timing for one synthetic 10,000-bar 15m series (seconds) — not a test
- [ ] Do NOT run the replay or the scorer on real data (the main session does that after validation)

## Completion record
