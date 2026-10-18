# Model Lab L0b — timeframe bars, causal factor library, hindsight targets T1–T5, leakage tests
Written: 2026-10-18 · Tag: TD-021 · Status: DONE

## Source

> then the model improvement plan shoudl simply treat those as time series data points (for one stock, volume, price,
> start/close, days min/ days max, etc, everything is a time series data, we can come up with so many more factors for
> a given candle and everything individually becoimes a time series), and see if it is able to find the local min or
> max […] also, the aim is to predict whether a given candle isa potential min or not and whether the future woudl
> result into a potential change in direction and by how much.
>
> predict forward need not be just oe candle at a time, after all that also woudl determine the hold period,
> potential. […] all time frames. both for min.

— `TODO/TD-021-model-lab-outside-lr-extrema/DETAIL.md`, as of 2026-10-18. Design: `docs/03_Model_Lab_Proposal.md`
§2 "Factor library", §3 "Targets", §8 "Traps". Sibling guide (built in parallel, shares no files):
`to_develop/2026-10-18_TD-021_L0a-lab-data-store-fetcher.md` — it creates `research/model_lab/store.py` with
`read_bars(symbol, interval, start=None, end=None) -> DataFrame[timestamp, open, high, low, close, volume]`
(naive IST, sorted, 15minute already filtered to the 09:15–15:15 grid) and `list_symbols(interval)`. **Do not create
or edit `store.py`;** import it lazily inside the functions that need it (`bars.load`, `build.main`), and no test of
yours may depend on it.

## Intent

Pure, deterministic, **strictly causal** DataFrame functions that turn native bars into:

1. bars for every lab timeframe, each with an `avail_ts` (the moment the bar's values are known);
2. a factor table per (symbol, timeframe): every column at bar *t* uses only data available at *t*'s `avail_ts`;
3. a target table per (symbol, timeframe): hindsight labels T1w, T1z, T2, T3, T4, T5, each with a known look-ahead;
4. leakage unit tests that prove 2 and 3;
5. a build CLI that writes both tables to parquet.

**Must NOT change:** anything under `trader/`, `scripts/`, `config/`, `main.py`. Imports allowed: `trader.data`,
`trader.core` (and `trader.auth` only if needed), stdlib, numpy, pandas, pyarrow. **Never** `trader.strategies`,
`trader.features`, `trader.policy`, `trader.backtest`. No torch in this guide.

**Already present (main session; do not edit):** `research/__init__.py`, `research/model_lab/__init__.py`,
`research/model_lab/paths.py` (`FACTORS_DIR`, `TARGETS_DIR`, `LOGS_DIR`, `check_disk`, `sym_file`). Read it first.

Conventions: prices in float64 in memory; parquet output float32 (except `timestamp`/`avail_ts` as
`datetime64[ns]`), zstd, `index=False`, atomic write (temp file + `os.replace`). Rolling windows use
`min_periods = window` unless stated (NaN until the window is full). Log returns are natural log. Percent values are
stated explicitly; everything else is a fraction.

## Implementation steps

### 1. `research/model_lab/synth.py` — synthetic data for tests (and later smoke runs)
```python
def synthetic_15m(n_sessions: int, seed: int, start: str = "2020-01-06", missing_frac: float = 0.0) -> pd.DataFrame
def synthetic_day(n_days: int, seed: int, start: str = "2019-01-01") -> pd.DataFrame
```
Business days (`pd.bdate_range`), 25 bars per session at 09:15, 09:30 … 15:15; GBM log-returns (σ 0.4 % per 15m bar,
small drift), open = previous close × (1 + small noise; larger noise on the first bar of a session), high/low enclosing
open and close, volume lognormal int. `missing_frac` drops that share of bars at random (never all bars of a
session). Day: same idea, σ 1.8 % per day, timestamp at midnight. Columns `timestamp, open, high, low, close, volume`.

### 2. `research/model_lab/bars.py` — timeframes and `avail_ts`
```python
TFS = ("15m", "30m", "60m", "4h", "dayagg", "day", "week")
SOURCE = {"15m": "15minute", "30m": "15minute", "60m": "15minute", "4h": "15minute",
          "dayagg": "15minute", "day": "day", "week": "day"}
def derive(src: pd.DataFrame, tf: str) -> pd.DataFrame
def load(symbol: str, tf: str, start=None, end=None) -> pd.DataFrame   # store.read_bars(symbol, SOURCE[tf]) -> derive
```
Output columns: `timestamp, open, high, low, close, volume, avail_ts, n_members`. OHLCV aggregation: first open, max
high, min low, last close, sum volume. `timestamp` = bucket start. **`avail_ts` = (last member's timestamp + 15 min)**
for intraday-derived TFs; for `day` = date + 15:30; for `week` = last member day + 15:30.
- `15m`: identity, `n_members = 1`.
- `30m` / `60m`: session-anchored buckets — bucket start = 09:15 + floor(minutes since 09:15 / N) × N. The 15:15 bar
  forms its own bucket (30m: 09:15 + 12×30; 60m: 09:15 + 6×60), as Kite's native bars do.
- `4h`: production boundaries (frozen, `trader/data/aggregator.py`): [09:15, 13:15) and [13:15, 15:15); members
  stamped ≥ 15:15 are DROPPED. `dayagg`: one bucket [09:15, 15:15), 15:15 bar dropped (the bars production's day-TF
  stocks trade on).
- `day`: native rows (no aggregation), `n_members = 1`.
- `week`: native day rows grouped by calendar week (Mon–Sun, `to_period("W-SUN")`); `timestamp` = first trading day of
  the week.
- **Incomplete final bucket:** for `30m`/`60m`/`4h`/`dayagg`, drop the LAST bucket of the frame if its last member is
  not the bucket's expected last slot (30m/60m: start + N − 15 min capped at 15:15; 4h: 13:00 / 15:00;
  dayagg: 15:00). For `week`, always drop the last week of the frame (its completeness is unknowable). Interior
  buckets with missing members are kept (data gaps), with their true `n_members`.

### 3. `research/model_lab/factors.py` — causal factor library
```python
HIGHER_TF = {"15m": ["60m", "day"], "30m": ["day"], "60m": ["day"], "4h": ["day", "week"],
             "dayagg": ["week"], "day": ["week"], "week": []}
HIGHER_SUBSET = ["ret_4", "ret_16", "dmin_20", "dmax_20", "dmin_100", "dmax_100", "rsi_14", "rv_16",
                 "atr_pct", "relvol_20", "bsl_20"]
def own_factors(bars) -> pd.DataFrame
def calendar_factors(bars, tf) -> pd.DataFrame
def market_factors(bars, own: pd.DataFrame, nifty: pd.DataFrame | None, vix_day: pd.DataFrame | None) -> pd.DataFrame
def higher_tf_factors(bars, higher: dict[str, pd.DataFrame]) -> pd.DataFrame
def compute_factors(bars, tf, nifty=None, vix_day=None, higher=None) -> pd.DataFrame
def cross_section(inputs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]
def monthly_expiry(d: date) -> date
```
All returned frames are row-aligned with `bars` (same length/order). `compute_factors` returns
`timestamp, avail_ts` + own + calendar + market + higher columns; **market and higher columns are always present**
(all-NaN when their input is None/empty), so every file of a timeframe has the same schema.

**own_factors** (o, h, l, c, v = OHLCV; `r1 = log(c / c.shift(1))`):
| Column(s) | Definition |
|---|---|
| `gap_1` | o / c.shift(1) − 1 |
| `body` | (c − o) / o |
| `uwick`, `lwick` | (h − max(o, c)) / o ; (min(o, c) − l) / o |
| `clv` | (c − l) / (h − l); 0.5 when h == l |
| `atr_14`, `atr_pct` | Wilder ATR: TR = max(h − l, \|h − c₋₁\|, \|l − c₋₁\|) (first bar: h − l), `TR.ewm(alpha=1/14, adjust=False).mean()`, NaN for the first 13 rows; `atr_pct` = atr_14 / c |
| `range_atr` | (h − l) / atr_14 |
| `r1`, `sd_256` | r1 ; r1.rolling(256).std() |
| `ret_{k}`, `retz_{k}` for k ∈ 1, 4, 16, 64, 256 | log(c / c.shift(k)) ; ret_k / (sd_256 × √k) |
| `dmin_{n}`, `dmax_{n}`, `bsl_{n}`, `bsh_{n}` for n ∈ 20, 50, 100, 250, 500, 1000 | c / l.rolling(n).min() − 1 ; c / h.rolling(n).max() − 1 ; bars since the lowest low of the last n bars incl. the current one (0 = this bar; ties → the MOST RECENT occurrence) ; same for the highest high. NaN until n bars exist. |
| `rsi_14` | Wilder RSI: gains/losses of c.diff(), `ewm(alpha=1/14, adjust=False)`, 100 − 100/(1 + RS); NaN for the first 14 rows; 50 when both averages are 0 |
| `stoch_14` | (c − l.rolling(14).min()) / (h.rolling(14).max() − l.rolling(14).min()); 0.5 when flat |
| `rv_{k}` for k ∈ 16, 64, 256 | r1.rolling(k).std() |
| `vov_64` | rv_16.rolling(64).std() / rv_16.rolling(64).mean() |
| `rngexp_20` | (h − l) / (h − l).rolling(20).mean() |
| `relvol_20` | v / v.shift(1).rolling(20).mean() (NaN when the mean is 0) |
| `volz_64` | z-score of log1p(v) vs its rolling(64) mean / std (NaN when std is 0) |
| `upvol_20` | Σ v·[c > o] / Σ v over 20 bars; 0.5 when Σ v = 0 |
| `lowbar_relvol_20` | v at the bar where the 20-bar lowest low sits (index t − bsl_20) / v.rolling(20).mean() |

`bsl_n`/`bsh_n` must be O(n·len) or better (monotonic deque or chunked `sliding_window_view`; no per-row Python
`rolling.apply`) and must match a brute-force implementation (test below).

**calendar_factors:** `tod` = minutes since 09:15 of the bar's `timestamp` (0 for `day`/`week`); `dow` = weekday
0–4; `dtme` = calendar days from the bar date to the last calendar day of its month; `dtexp` = calendar days to the
next monthly F&O expiry on or after the bar date (`monthly_expiry`); `sesspos` = 0-based index of the bar within its
session date ÷ bars-per-session (`15m` 25, `30m` 13, `60m` 7, `4h` 2; 0 for `dayagg`/`day`/`week`).
`monthly_expiry(d)`: last Thursday of d's month for dates before 2025-09-01, last Tuesday from 2025-09-01 (SEBI/NSE
expiry-day change); if d is after that month's expiry, use next month's. Holidays are ignored (documented
approximation).

**market_factors** (`nifty` = NIFTY 50 bars at the SAME timeframe, `vix_day` = native daily INDIA VIX bars):
- Same-TF Nifty join: compute `own_factors(nifty)` and LEFT-merge on `timestamp` (exact): `nifty_ret_1`,
  `nifty_ret_16`, `nifty_ret_64`, `nifty_dmax_250` (from nifty's `ret_*`, `dmax_250`).
- `beta_250` = `r1.rolling(250, min_periods=200).cov(nifty_r1) / nifty_r1.rolling(250, min_periods=200).var()` on the
  merged series; `resid_16` = ret_16 − beta_250 × nifty_ret_16; `rs_64` = ret_64 − nifty_ret_64.
- VIX (daily): on `vix_day` compute `vix_close` = close, `vix_pct_252` = `close.rolling(252, min_periods=200).rank(pct=True)`,
  `vix_ret_5` = log(close / close.shift(5)); give the VIX frame `avail_ts` = date + 15:30 and join with
  `pd.merge_asof(left_on="avail_ts", right_on="avail_ts", direction="backward", allow_exact_matches=False)` —
  STRICTLY earlier, so every bar of day D sees day D−1's VIX (the round-1 "prior-day VIX" signal). Output names:
  `vix_close_d1`, `vix_pct_252_d1`, `vix_ret_5_d1`.

**higher_tf_factors:** for each `htf` in the dict (already-derived bars of that TF), compute `own_factors(hbars)`,
keep `HIGHER_SUBSET`, prefix columns `h{htf}_` (e.g. `hday_rsi_14`, `h60m_ret_4`), attach the higher bars'
`avail_ts`, and `merge_asof` on `avail_ts` backward with `allow_exact_matches=False` (strictly completed higher
bars only).

**cross_section(inputs):** `inputs[symbol]` = frame with `timestamp, ret_16, ret_64, close` (one timeframe, many
symbols). Per symbol first compute `above_100 = close > close.rolling(100).mean()` (NaN until 100 bars). Stack, then
per `timestamp`: `xs_n` = number of symbols with non-NaN `ret_16`; `xs_rank_ret16`, `xs_rank_ret64` =
`rank(pct=True)` within the timestamp; `xs_breadth_100` = mean of `above_100` over symbols where it is defined.
Set the three xs values to NaN where `xs_n < 10`. Return per-symbol frames row-aligned with the inputs with columns
`xs_n, xs_rank_ret16, xs_rank_ret64, xs_breadth_100`. (The universe is whatever set is passed — the build passes the
whole built set; PIT universe selection is L0a's job and documented as such.)

### 4. `research/model_lab/targets.py` — hindsight labels
```python
SCALES = {"15m": [4, 12, 25, 75], "30m": [4, 13, 39], "60m": [3, 7, 21], "4h": [2, 6, 15],
          "dayagg": [3, 5, 10, 20], "day": [3, 5, 10, 20], "week": [2, 4, 8]}
HOLD_H = {"15m": [25, 125, 500], "30m": [13, 65, 260], "60m": [7, 35, 140], "4h": [2, 10, 40],
          "dayagg": [5, 20, 60], "day": [5, 20, 60], "week": [4, 13, 26]}
FWD_H = [1, 2, 4, 8, 16, 32, 64, 128]
ZZ_K = [2, 5, 10]; ZZ_SIGMA_WINDOW = 250; ZZ_CLAMP_PCT = (0.3, 25.0)
BARRIER_X = [3, 5, 7, 10]; BARRIER_Y = [3, 5, 10]          # percent
def zigzag_pivots(close: np.ndarray, thr_pct: np.ndarray, start: int = 0) -> list[tuple[int, int, int]]
def build_targets(bars, tf, **overrides) -> pd.DataFrame
def lookahead(col: str) -> int | None
```
`build_targets` returns `timestamp` + the columns below, row-aligned with `bars`; `overrides` may replace any of
`SCALES/HOLD_H` entries for `tf`, `FWD_H`, `ZZ_K`, `ZZ_SIGMA_WINDOW`, `ZZ_CLAMP_PCT`, `BARRIER_X`, `BARRIER_Y`
(keyword names in lower case: `scales, hold_h, fwd_h, zz_k, zz_sigma_window, zz_clamp_pct, barrier_x, barrier_y`).
Labels are 1.0 / 0.0 (or signed ints as floats), **NaN wherever the label is unresolved** (window runs off either end
of the data, σ not yet defined, zigzag state not yet confirmed). Never guess.

- **T1w** (w ∈ SCALES[tf]): `t1w_min_w{w}` = 1 if the first-occurrence argmin of `low[t−w … t+w]` is t (ties → the
  earliest bar wins); `t1w_max_w{w}` same with argmax of `high`. NaN when t < w or t + w > n − 1. Look-ahead w.
- **T1z** (k ∈ ZZ_K): σ_t (percent) = 100 × `(c / c.shift(1) − 1).rolling(ZZ_SIGMA_WINDOW).std()`; threshold
  thr_t = clip(k × σ_t, *ZZ_CLAMP_PCT). `zigzag_pivots(close, thr, start)` — classic close-based zigzag from `start`
  (first index with σ defined): before the first pivot track running max and min; the first reversal of ≥ thr (thr
  taken at the candidate extreme's index) from either confirms it. Then alternate: in a down leg the candidate low is
  the lowest close since the last pivot high (update on a strictly lower close); it is confirmed as a pivot low at the
  first bar whose close ≥ cand × (1 + thr_cand / 100); symmetric for highs. Returns `(pivot_idx, kind ∈ {−1 low,
  +1 high}, confirm_idx)`; the state machine reads bars sequentially and must only use `close[:i+1]` at step i.
  Columns: `t1z_min_k{k}` / `t1z_max_k{k}` = 1 at pivot lows / highs, 0 at other resolved rows; resolved rows are
  `start ≤ t ≤ last pivot_idx`; rows after the last pivot index and before `start` are NaN.
  `t1z_endbars_k{k}` = confirm_idx of the first pivot with pivot_idx ≥ t, minus t (NaN where unresolved). Look-ahead
  per row = that column.
- **T3** (k ∈ ZZ_K), from the same pivots: next pivot = first pivot with pivot_idx > t (strictly).
  `t3_ret_k{k}` = close[next] / close[t] − 1; `t3_bars_k{k}` = next − t; `t3_sig_k{k}` = 100 × t3_ret / σ_t;
  `t3_endbars_k{k}` = next's confirm_idx − t. NaN when there is no next pivot or σ_t is NaN.
- **T2** (h ∈ SCALES[tf]): σf_t = `(c / c.shift(1) − 1).rolling(ZZ_SIGMA_WINDOW).std()` (fraction);
  back = c[t] / c[t−h] − 1; fwd = c[t+h] / c[t] − 1; δ = 0.5 × σf_t × √h. `t2_up_h{h}` = 1 if back < −δ and fwd > δ
  else 0; `t2_dn_h{h}` = 1 if back > δ and fwd < −δ else 0; `t2_fwd_h{h}` = +1 if fwd > δ, −1 if fwd < −δ, else 0.
  NaN when t < h, t + h > n − 1 or σf_t is NaN. Look-ahead h.
- **T4** (h ∈ FWD_H): `t4_ret_h{h}` = log(c[t+h] / c[t]); NaN when t + h > n − 1. Look-ahead h.
- **T5** (H ∈ HOLD_H[tf]) — money targets, **entry e = open[t+1]** (decision at bar close, fill at the next open).
  Window W = bars t+1 … t+H inclusive; ALL T5 columns of that H are NaN when t + H > n − 1.
  `t5_mfe_H{H}` = max(high[W]) / e − 1; `t5_ttm_H{H}` = 1 + first-occurrence argmax of high[W] (bars after t,
  1…H); `t5_maepre_H{H}` = min(low[t+1 … t+ttm]) / e − 1 (includes the MFE bar); `t5_mae_H{H}` = min(low[W]) / e − 1;
  `t5_ret_H{H}` = close[t+H] / e − 1; for X ∈ BARRIER_X, Y ∈ BARRIER_Y: `t5_hit_x{X}_y{Y}_H{H}` = 1 if the first bar
  of W with high ≥ e·(1 + X/100) comes strictly before the first bar with low ≤ e·(1 − Y/100) (or the stop is never
  touched), else 0 (stop first, both in the same bar — conservative — or neither). Look-ahead H.
  Implementation: vectorised (`numpy.lib.stride_tricks.sliding_window_view` in row chunks of ≤ 5,000 so memory stays
  bounded); compute the first-hit offset per threshold once for the largest H and derive the smaller H from it.
- `lookahead(col)`: parse the column name → w / h / H for t1w/t2/t4/t5; None for t1z/t3 (use the `*_endbars_*`
  columns).

Performance budget: `build_targets` and `compute_factors` on 54,000 15m bars must each run in < 15 s on this laptop.

### 5. `research/model_lab/build.py` — CLI
`.venv/bin/python -m research.model_lab.build --tf 15m [--symbols NSE:A NSE:B …] [--what factors targets] [--no-xs]`
- Symbols default: `store.list_symbols(SOURCE[tf])` minus `NSE:NIFTY 50`, `NSE:INDIA VIX`.
- Inputs: `bars.load(sym, tf)`; Nifty = `bars.load("NSE:NIFTY 50", tf)`; VIX = `store.read_bars("NSE:INDIA VIX",
  "day")`; higher = `{htf: bars.load(sym, htf) for htf in HIGHER_TF[tf]}`. Missing market files → those columns NaN
  plus a warning (not an error).
- Factors: pass 1 computes `compute_factors` per symbol, writes `FACTORS_DIR/<tf>/<SYM>.parquet` and keeps only the
  small cross-section inputs in memory; pass 2 (unless `--no-xs`) runs `cross_section` and rewrites each file with the
  four xs columns appended (pass 1 writes them as NaN so the schema is stable).
- Targets: `build_targets` per symbol → `TARGETS_DIR/<tf>/<SYM>.parquet`.
- `check_disk()` before every write; skip symbols with fewer than 300 bars (log them); print per symbol rows and
  seconds, and at the end total files, total MB written, elapsed. Log file `LOGS_DIR/build_<tf>_<stamp>.log`.

## Tests required

New files (pure, synthetic data from `research/model_lab/synth.py`; no store, no network; whole set < 60 s):

`tests/test_model_lab_bars.py`
- `test_4h_and_dayagg_match_candle_aggregator` — feed `synthetic_15m(30, seed=1)` (complete sessions) through
  `trader.data.aggregator.CandleAggregator("4hour")` / `("day")` (`add()` per candle + final `flush()`); timestamps
  and OHLCV equal `derive(..., "4h")` / `derive(..., "dayagg")`.
- `test_30m_60m_buckets` — hand-built single session: bucket starts, OHLCV, the lone 15:15 bucket.
- `test_avail_ts_last_member_plus_15m` — every intraday TF; strictly increasing; `day`/`week` at 15:30.
- `test_incomplete_final_bucket_dropped` — truncate mid-bucket → last bucket dropped; final week always dropped.
- `test_week_grouping` — Mon–Fri rows of one calendar week form one bar stamped on the first trading day.

`tests/test_model_lab_factors.py`
- `test_own_factors_causal` — `synthetic_15m(70, seed=2)`; for cut ∈ {1100, 1400, n−1}: `own_factors(bars[:cut+1])`
  row `cut` equals the full computation's row `cut` (`assert_allclose(rtol=1e-9, atol=1e-12, equal_nan=True)`), all
  columns.
- `test_compute_factors_causal_every_tf` — for each tf in TFS: sources = synthetic 15m (seed 3, 90 sessions,
  `missing_frac=0.01`) and synthetic day (seed 4, covering the same dates plus 300 earlier days) for the stock, Nifty
  (seeds 5/6) and VIX (seed 7, day). Derive everything from the full sources, `compute_factors` with nifty, vix and
  higher. Then for 3 cut rows c (late enough that windows are full): T = row c's `avail_ts`; truncate EVERY source
  to rows whose own avail time (15m: ts + 15 min; day: date + 15:30) ≤ T; re-derive and recompute; the row with
  `timestamp == full.timestamp[c]` must exist and equal row c in every column.
- `test_cross_section_causal` — 12 synthetic symbols (seeds 10–21, 70 sessions); truncate all at a common time;
  xs values at the cut timestamp unchanged; `xs_n < 10` → NaN (drop symbols to 9).
- `test_higher_join_strictly_completed` — for 50 random 15m rows, `hday_rsi_14` equals `own_factors(day).rsi_14` of
  the last day bar with `avail_ts <` the row's `avail_ts` (computed by an explicit loop).
- `test_vix_is_prior_day` — every 15m bar of date D carries the VIX close of the previous VIX date.
- `test_bars_since_extreme_matches_bruteforce` — `bsl_n`/`bsh_n` vs a naive loop incl. tie cases.
- `test_monthly_expiry` — 2024-10 → Thu 2024-10-31; 2025-08 → Thu 2025-08-28; 2025-09 → Tue 2025-09-30; a date after
  the month's expiry rolls to next month.
- `test_schema_stable_without_market` — `compute_factors(bars, "15m")` (no nifty/vix/higher) has the same column
  list as with them.

`tests/test_model_lab_targets.py`
- `test_fixed_lookahead_columns_are_causal_beyond_horizon` — `synthetic_15m(60, seed=8)`; for cut c ∈ {700, 1100}:
  replace every bar after c with random garbage (new seed), recompute; for every column with `lookahead(col) = L`,
  rows t ≤ c − L are unchanged (equal_nan); in the unmodified full frame, rows t > n − 1 − L are NaN.
- `test_zigzag_columns_resolved_only_by_their_endbars` — same garbage protocol; for t1z/t3 columns, every row with
  `t + endbars ≤ c` (from the full frame) is unchanged.
- `test_zigzag_pivots_hand_series` — constant `thr_pct = 5`: a hand series with known swings yields exactly the
  expected (pivot_idx, kind, confirm_idx) list; a 4 % wiggle is not a pivot.
- `test_t1w_ties_and_edges` — V shape with a flat 2-bar bottom: only the first bottom bar is labelled; edges NaN.
- `test_t5_semantics` — hand bars: +5 % hit at offset 3 and −3 % at offset 2 → `hit_x5_y3 = 0`; target first →
  1; same-bar both → 0; neither → 0; ttm, maepre, mae, mfe, ret values exact; entry is next bar's open.
- `test_t2_t4_hand_values` — a V with known σ (override `zz_sigma_window`) gives `t2_up = 1` at the bottom; t4 log
  returns exact.
- `test_targets_runtime_budget` — `synthetic_15m(400, seed=9)` (10,000 bars) builds targets in < 5 s (skip with a
  clear message on CI-slow hosts is NOT allowed; keep the implementation fast).

Suites that stay green: the full suite.

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] every test above present and passing; none touch the network, `data/market.db` or `lab_data/`
- [ ] no file under `trader/`, `scripts/`, `config/`, `main.py` changed; `store.py` not created by this guide
- [ ] `research/model_lab/` imports only `trader.data` / `trader.core` / `trader.auth` from the trader package
- [ ] no full-sample statistics anywhere in factors (no `.mean()`/`.std()` over the whole column, no centred windows)
- [ ] higher-TF and VIX joins strictly earlier (`allow_exact_matches=False`); same-TF Nifty join exact on timestamp
- [ ] T5 entry = next bar's open; unresolved labels NaN, never 0
- [ ] performance budget met (report the timings for 54k bars: run `compute_factors` and `build_targets` on
      `synthetic_15m(2160, seed=1)` once and report seconds — do not add that as a test)
- [ ] Do NOT run `build.py` against real data (the store does not exist yet); the main session does it after L0a.

## Completion record
- **Completed:** 2026-10-18 · trader-implementer (sonnet), validated by the main session (full suite 619 passed; 26 new tests
  incl. per-TF causality parametrised over all 7 TFs). Code read: zigzag state machine, T5 first-hit ordering
  (`fx < H and fx < fy`, same bar → 0), next-open entry, T1w first-occurrence ties, strict VIX/higher-TF joins.
- **Commit:** see the L0 completion commit on `exp/model-lab`.
- **Deviations (accepted):** the per-TF causality test keeps daily sources to T + 3 calendar days for TFs whose chain
  includes `week` (the always-drop-last-week rule would otherwise remove the cut row) — the strict-join test covers the
  leak that this could mask; cut rows chosen at complete buckets; `monthly_expiry` picks Thu/Tue by expiry month;
  `sesspos` counts present bars in gapped sessions; an int64 bucket-key overflow was caught and fixed by the implementer.
- **Performance:** 54k synthetic 15m bars — `compute_factors` 0.30 s, `build_targets` 0.26 s. Real data: 3 × 15m stocks
  (54k bars each) built in 3.0 s; **15m factor files ≈ 9 MB per stock, targets ≈ 4 MB** → at universe scale L1 should
  compute factors on the fly rather than cache them (disk ~7.7 GB free).
- **Real-data sanity (CUPID 15m):** label rates t1w_min w4 4.8 % … w75 0.4 %; t1z_min k2 4.1 % / k5 0.6 % / k10 0.2 %;
  t5 hit +7/−5 within 25/125/500 bars 7 % / 33 % / 46 %; `hday_*` mostly NaN until the daily backfill (2008→) lands.
