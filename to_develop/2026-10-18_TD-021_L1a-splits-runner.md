# Model Lab L1a — PIT panel, split engine (purge + embargo), lab model wrapper, walk-forward runner
Written: 2026-10-18 · Tag: TD-021 · Status: OPEN

## Source

> date splits need to be dyanmic, dont just stick to one. also, a lot methodligcally would have changed year on year.

> […] see if it is able to find the local min or max, (with abiltiy to train on historical data (some precentage of
> over all time series) and then predict on the remaining treating that as future point by point evolution of the time
> series.

— `TODO/TD-021-model-lab-outside-lr-extrema/DETAIL.md`, as of 2026-10-18. Design: `docs/03_Model_Lab_Proposal.md`
§4 "Protocol" and §6 (rewritten 2026-10-18: the strategy does not judge the model). Built on L0
(`to_develop/completed/2026-10-18_TD-021_L0*.md`). Sibling guide built in parallel (shares no files, only the run
directory contract below): `to_develop/2026-10-18_TD-021_L1b-references-scoring.md`.

## Intent

The machinery that trains any lab model walk-forward and writes its per-bar scores, with no leakage:

1. **Data source** abstraction (real lab data, or synthetic for tests) + point-in-time (PIT) universe membership.
2. **Split engine:** expanding, rolling, anchor-sweep, leave-one-year-out (diagnostic), held-out stock groups; purge +
   embargo by each row's label end time.
3. **Lab model wrapper** (`fit/predict`) with two concrete models (pooled logistic, pooled HistGradientBoosting) so the
   runner is testable end to end. L2 adds more models and runs the experiments — L1a runs no experiment.
4. **Runner:** a training pool (subsampled, memory-bounded), one fitted model per fold, streamed per-symbol prediction
   on each fold's test rows, written in the run-directory contract.

**Must NOT change:** anything outside `research/model_lab/` and the new test files. No imports from
`trader.strategies`, `trader.features`, `trader.policy`, `trader.backtest`. Do not create or edit the sibling's files
(`references.py`, `score.py`, `report.py`, `scripts/model_lab/*`, `tests/test_model_lab_score*.py`).

## Run-directory contract (shared with L1b — implement exactly)

`paths.RUNS_DIR / <run_id>/` (`RUNS_DIR` and `REFS_DIR` already exist in `paths.py`; do not edit `paths.py`):
- `meta.json` — `{run_id, tf, scheme, target, model, model_params, features, universe_top_n, symbols, train_rows_per_fold,
  seed, created, elapsed_s}` (lists/dicts JSON-serialisable; datetimes ISO strings).
- `folds.parquet` — one row per fold: `fold_id` int32, `scheme` str, `train_start`, `train_end`, `test_start`,
  `test_end` (datetime64[ns]; train/test windows are half-open `[start, end)` on `avail_ts`), `holdout_group` int32
  (−1 when the scheme holds out no stocks).
- `scores/<SYM>.parquet` — `timestamp` datetime64[ns], `fold_id` int32, `score` float32 (+ optional `pred_*` float32
  columns for multi-output models). One row per (test bar, fold) the model scored. zstd, atomic write.

## Implementation steps

### 1. `research/model_lab/source.py`
```python
class LabSource:                       # real data (L0 store + bars + universe)
    def symbols(self) -> list[str]                         # store.list_symbols(SOURCE[tf]) minus index symbols
    def bars(self, symbol: str, tf: str) -> pd.DataFrame   # bars.load
    def nifty(self, tf: str) -> pd.DataFrame | None
    def vix_day(self) -> pd.DataFrame | None
    def membership(self, years: list[int], top_n: int | None) -> dict[int, set[str]]
class SynthSource:                     # tests: n synthetic stocks from synth.py (+ synthetic nifty/vix)
    def __init__(self, n_symbols: int, n_sessions: int, seed: int, plant: str | None = None)
def symbol_frames(source, symbol, tf, xs_table=None) -> tuple[pd.DataFrame, pd.DataFrame]
def build_xs_table(source, symbols, tf) -> pd.DataFrame
```
- `LabSource.membership(years, top_n)`: `{y: set(universe.liquid_universe(date(y, 1, 1), top_n))}`; `top_n=None` →
  every symbol with source data in that year. `SynthSource.membership` → all symbols every year.
- `symbol_frames` → `(factors, targets)` row-aligned: `factors.compute_factors(bars, tf, nifty, vix_day,
  higher={htf: source.bars(symbol, htf) for htf in HIGHER_TF[tf]})` and `targets.build_targets(bars, tf)`; when
  `xs_table` is given, left-merge its four `xs_*` columns on `timestamp` for that symbol (else they stay NaN).
- `build_xs_table`: run `cross_section` over all `symbols` (inputs = timestamp, close, `ret_16`, `ret_64` from
  `own_factors`) and return a long frame `symbol, timestamp, xs_n, xs_rank_ret16, xs_rank_ret64, xs_breadth_100`.
- `SynthSource(plant="ret_4")`: makes the `t1w_min_w4` target learnable for tests by construction — implement by
  overriding `symbol_frames` output for synthetic data only: set factor column `plant_signal` = the target value + noise
  (N(0, 0.3)) — the column exists only when `plant` is set. Never used outside tests.

### 2. `research/model_lab/splits.py`
```python
@dataclass(frozen=True)
class Fold:
    fold_id: int; scheme: str; train_start: pd.Timestamp; train_end: pd.Timestamp
    test_start: pd.Timestamp; test_end: pd.Timestamp; holdout_group: int = -1

EMBARGO = {"15m": "1D", "30m": "1D", "60m": "1D", "4h": "1D", "dayagg": "1D", "day": "5D", "week": "21D"}
def test_windows(data_start, data_end, step: str = "6M", min_train: str = "2Y") -> list[tuple[pd.Timestamp, pd.Timestamp]]
def expanding(data_start, data_end, step="6M", min_train="2Y") -> list[Fold]
def rolling(data_start, data_end, train_len: str, step="6M", min_train="2Y") -> list[Fold]
def anchor_sweep(data_start, data_end, anchors: list[str], step="6M", min_train="2Y") -> list[Fold]
def leave_one_year_out(data_start, data_end) -> list[Fold]
def with_stock_groups(folds: list[Fold], n_groups: int) -> list[Fold]
def stock_group(symbol: str, n_groups: int) -> int
def train_mask(fold, avail_ts, label_end_ts, symbols, tf, n_groups=None) -> np.ndarray
def test_mask(fold, avail_ts, symbols, n_groups=None) -> np.ndarray
def make_folds(scheme: str, data_start, data_end, **kw) -> list[Fold]
```
- `test_windows`: consecutive `[s, s + step)` windows aligned to calendar half-years for "6M" (Jan 1 / Jul 1) and
  quarters for "3M", starting at the first aligned date ≥ `data_start + min_train`, while `s < data_end`; the last
  window is clipped to `data_end` (partial window kept only if ≥ 30 days).
- `expanding`: `train = [data_start, test_start)`. `rolling`: `train = [max(data_start, test_start − train_len),
  test_start)`. `anchor_sweep`: for each anchor A, expanding folds with `data_start = A` (scheme name
  `anchor_<YYYY>`), only windows with ≥ `min_train` of training. `leave_one_year_out`: test = calendar year Y
  (`[Y-01-01, Y+1-01-01)`), train = everything else (`train_start = data_start`, `train_end = data_end`) — the purge
  removes the year ± embargo; scheme name `loyo` (DIAGNOSTIC ONLY — written into `meta.json` as `"diagnostic": true`).
  `fold_id`s are 0..n−1 in time order.
- `with_stock_groups(folds, G)`: each fold replicated G times with `holdout_group` g = 0..G−1 (fold ids renumbered).
- `stock_group(symbol, G)` = `int(md5(symbol).hexdigest(), 16) % G` (stable across runs/machines).
- **`train_mask`** (the leakage gate): a row is usable for training iff
  1. `train_start ≤ avail_ts < train_end`;
  2. `label_end_ts` is not NaT and **`label_end_ts < test_start − EMBARGO[tf]`** when the row is before the test
     window; for `loyo`, rows after the test window additionally need `avail_ts ≥ test_end + EMBARGO[tf]` (and rows
     inside `[test_start − embargo, test_end + embargo)` are always dropped);
  3. when `holdout_group ≥ 0`: `stock_group(symbol) != holdout_group`.
- **`test_mask`**: `test_start ≤ avail_ts < test_end` and, when `holdout_group ≥ 0`, `stock_group(symbol) ==
  holdout_group`.
- `make_folds(scheme, ...)` dispatches `"expanding" | "rolling_6M" | "rolling_1Y" | "rolling_2Y" | "rolling_3Y" |
  "anchor" | "loyo"`, with `n_groups` kw applying `with_stock_groups`.

### 3. Label end time — `research/model_lab/source.py`
```python
def label_end_ts(targets: pd.DataFrame, timestamps: pd.Series, col: str) -> pd.Series
```
For fixed-look-ahead columns (`targets.lookahead(col) = L`): the timestamp L rows later in the same symbol
(`timestamps.shift(-L)`), NaT when that is past the end. For zigzag columns (`t1z_*`, `t3_*`): the row's own
`*_endbars_*` column for the same k (`t1z_endbars_k{k}` for t1z, `t3_endbars_k{k}` for t3) → the timestamp that many rows
later; NaT when the endbars value is NaN. The label value is NaN wherever `label_end_ts` is NaT.

### 4. `research/model_lab/models.py`
```python
class LabModel(ABC):
    name: str
    def __init__(self, **params): ...
    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray, w: np.ndarray | None = None) -> None
    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray      # 1-D float score; higher = more likely positive class
MODELS: dict[str, type[LabModel]] = {"logistic": PooledLogistic, "hgb": PooledHGB}
def make_model(name: str, **params) -> LabModel
```
- `PooledLogistic`: fit-time median imputation + `StandardScaler` (both fitted on the training rows only, stored on the
  instance) → `sklearn.linear_model.LogisticRegression(C=params.get("C", 1.0), max_iter=1000, class_weight="balanced")`;
  `predict` = `predict_proba[:, 1]`.
- `PooledHGB`: `sklearn.ensemble.HistGradientBoostingClassifier(max_depth=params.get("max_depth", 3),
  learning_rate=0.05, max_iter=params.get("max_iter", 300), early_stopping=False, class_weight="balanced",
  random_state=seed)` — NaN handled natively; `predict` = `predict_proba[:, 1]`.
- One-class training data (all 0 or all 1) → raise `ValueError("one-class training set")` (the runner records the fold
  as skipped; cf. ISS-15).

### 5. `research/model_lab/runner.py`
```python
@dataclass
class RunSpec:
    run_id: str; tf: str; scheme: str; target: str
    model: str = "logistic"; model_params: dict = field(default_factory=dict)
    features: list[str] | None = None          # None = every factor column except timestamp/avail_ts
    universe_top_n: int | None = 100
    n_groups: int | None = None                # held-out stock groups
    max_train_rows: int = 2_000_000
    recency_half_life_days: float | None = None
    scheme_kw: dict = field(default_factory=dict)   # e.g. {"step": "6M", "anchors": [...]}
    seed: int = 7
    workers: int = 1
def run(spec: RunSpec, source=None) -> Path      # returns the run directory
```
`python -m research.model_lab.runner --run-id ... --tf 15m --scheme expanding --target t1z_min_k5 --model logistic
[--top-n 100] [--n-groups 5] [--max-train-rows ...] [--workers 8] [--features a b c]`.

Algorithm (memory-bounded; 16 GB laptop):
1. `symbols` = source symbols that are members in at least one year; data range = min/max timestamp over them
   (bars only — cheap pass); `folds = make_folds(...)`. Write `folds.parquet` first.
2. `xs = build_xs_table(source, symbols, tf)` (skip silently for `SynthSource` with < 10 symbols).
3. **Pass A — training pool** (per symbol, `ProcessPoolExecutor(workers)` when > 1): `symbol_frames`; rows kept iff the
   symbol is a member in the row's calendar year (PIT) and the target and its `label_end_ts` are defined. Keep feature
   columns (float32), `y`, `avail_ts`, `label_end_ts`, `symbol`. Subsample to respect `max_train_rows` overall:
   per-symbol cap = `max_train_rows / n_symbols`, ALL positive rows kept up to half the cap, negatives sampled uniformly
   (seeded by `seed` + symbol hash) for the rest. Record the sampling in meta (rows seen / kept, positives kept).
4. **Fit per fold:** rows = pool ∩ `train_mask`; sample weights = recency weights `0.5 ** (age_days / half_life)` with
   age measured from `train_end` (None → no weights). Fit `make_model(...)`; skip the fold on `ValueError` (record
   reason). Keep the fitted models in memory (or pickle to `runs/<id>/models/fold_<k>.pkl` when > 20 folds).
5. **Pass B — scoring:** per symbol recompute `symbol_frames` (do not keep pass-A frames), for each fold rows =
   `test_mask` ∩ PIT membership (calendar year of the row); predict on ALL such rows (labels may be NaN — prediction
   never needs the label); append `timestamp, fold_id, score`. Write `scores/<SYM>.parquet` once per symbol.
6. Write `meta.json` (incl. per-fold `train_rows`, `positives`, `skipped`), print a summary and the run directory.

Run ids are caller-chosen; refuse to overwrite an existing run directory unless `--overwrite`.
`paths.check_disk()` before writing scores.

## Tests required

New file `tests/test_model_lab_splits.py` (synthetic only, no `lab_data/`, < 60 s total):
- `test_test_windows_aligned_half_years` and quarter variant; partial last window rule (≥ 30 days).
- `test_expanding_rolling_anchor_shapes` — train ranges as specified; fold ids in time order; anchor scheme names.
- `test_train_mask_purges_by_label_end` — rows whose `label_end_ts ≥ test_start − embargo` are excluded even though
  their `avail_ts` is before the test; rows with NaT label end excluded.
- `test_loyo_embargo_both_sides` — no training row within `[test_start − embargo, test_end + embargo)`; rows after the
  year allowed only from `test_end + embargo`.
- `test_stock_groups_stable_and_disjoint` — same group for the same symbol across calls; train and test symbol sets
  disjoint per held-out fold; every symbol tested exactly once per time window.
- `test_label_end_ts_fixed_and_zigzag` — `t4_ret_h4` → 4 rows later; `t1z_min_k2` → endbars rows later; NaN label ↔
  NaT end.

New file `tests/test_model_lab_runner.py`:
- `test_runner_end_to_end_synthetic` — `SynthSource(n_symbols=6, n_sessions=60, seed=1, plant="ret_4")`, tf 15m,
  scheme expanding with `step="3M"` and a `min_train` that yields ≥ 2 folds, target `t1w_min_w4`, logistic, features
  `["plant_signal", "ret_4", "rsi_14"]`. Asserts: run dir has the contract files with the exact dtypes; every score row
  lies inside its fold's test window; ROC-AUC of `score` vs the target on scored rows > 0.75 (planted signal learned).
- `test_runner_never_trains_on_test_window` — instrument the model (a test subclass registered in `MODELS` that
  records the `avail_ts` max and `label_end_ts` max of what it was fitted on — pass them via a side channel the runner
  exposes, e.g. `runner._last_fit_rows` set in debug mode) → for every fold, max label end < test_start − embargo.
- `test_runner_pit_membership` — a source whose membership excludes symbol S in year Y: no training or scoring rows of S
  in Y.
- `test_runner_holdout_groups` — `n_groups=3`: each scored symbol appears only in folds whose `holdout_group` equals its
  group.
- `test_one_class_fold_skipped` — a target that is all-zero in the first fold's training range → fold recorded as
  skipped, run completes.

Suites that stay green: the full suite.

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] run-directory contract exactly as specified (names, dtypes, half-open windows)
- [ ] `train_mask` enforces label-end purge + embargo (and both sides for loyo); tests prove it
- [ ] PIT membership applied in BOTH training pool and scoring
- [ ] memory-bounded: pass-A frames not kept for pass B; pool capped by `max_train_rows`
- [ ] no imports from `trader.strategies` / `trader.features` / `trader.policy` / `trader.backtest`
- [ ] no sibling (L1b) file created or edited; `paths.py` not edited
- [ ] Do NOT run the runner on real data (the main session does that after validation)

## Completion record
