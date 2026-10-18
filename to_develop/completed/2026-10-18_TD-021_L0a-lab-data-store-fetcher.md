# Model Lab L0a — parquet bar store, staged Kite fetcher, point-in-time universe, data QA
Written: 2026-10-18 · Tag: TD-021 · Status: DONE

## Source

> what I woudl suggest it create a vanialla framework, that only utilizes the current framework to get the stock
> related information. then the model improvement plan shoudl simply treat those as time series data points […]
> few poitners for the data, you are free to pull latest fresh data from kite using the standard authetnication
> mechianm as and when required. […] all stocks are canddiates. all time frames.

— `TODO/TD-021-model-lab-outside-lr-extrema/DETAIL.md`, as of 2026-10-18. Design: `docs/03_Model_Lab_Proposal.md`
§1 "Data" and § "Start here". Sibling guide (built in parallel, shares no files):
`to_develop/2026-10-18_TD-021_L0b-bars-factors-targets.md`.

## Intent

Give the lab its own candle history, separate from `data/market.db`, plus the tools to grow it in stages:

1. **Parquet bar store.** One file per (native interval, symbol) under `lab_data/model_lab/bars/<interval>/`.
   Intervals stored: `15minute` and `day` only (every other timeframe is derived in L0b).
2. **Seed** the store from the existing cache (`data/market.db`, opened READ-ONLY): zero Kite requests.
3. **Staged fetcher** CLI: market series (NIFTY 50, INDIA VIX), daily bars for all NSE EQ names, 15m bars for a
   point-in-time liquid universe. Resumable through a per-interval manifest.
4. **Point-in-time (PIT) universe**: an instrument snapshot plus a daily liquidity panel (trailing median traded
   value), so the intraday universe for year Y is chosen only from data before Y.
5. **QA report**: per symbol coverage and suspicious jumps (possible unadjusted corporate actions).

**Must NOT change:** anything under `trader/`, `scripts/`, `main.py`, `config/`. Never write to `data/market.db`
(open it read-only with a `file:…?mode=ro` URI). No imports from `trader.strategies` or `trader.backtest`.

**Already present (written by the main session; do not edit):** `research/__init__.py`,
`research/model_lab/__init__.py`, `research/model_lab/paths.py` (constants `LAB_ROOT`, `BARS_DIR`, `UNIVERSE_DIR`,
`LOGS_DIR`, `MIN_FREE_GB`; helpers `sym_file`, `file_sym`, `free_gb`, `check_disk`). Read it first.

**Why parquet and not a second `Store`** (docs/03 suggested a `Store` on a separate path): the disk had 7.8 GB free on
2026-10-18; SQLite costs ~155 B per candle vs ~25 B in zstd parquet. Recorded in DECISIONS.

**Facts established on 2026-10-18** (do not re-probe):
- Kite 15m history starts in early 2015 (2015-01 empty, 2016-01 present). Day history goes back past 2008.
- `kite.instruments("NSE")`: 10,239 rows with `instrument_type == "EQ"` and `segment == "NSE"`; 3,050 of them have no
  `-` in `tradingsymbol` (the plain EQ series); ~369 of those look like ETFs.
- `data/market.db` holds 15minute for 105 symbols (from 2017-12 at the earliest) incl. `NSE:NIFTY 50` and
  `NSE:INDIA VIX` (from 2019-06), and day for 532 symbols from 2023-06. It contains 1,210 off-grid 15minute rows
  (ISS-12: minutes not a multiple of 15, or times outside 09:15–15:15). Timestamps are naive IST ISO strings.

## Implementation steps

1. **New `research/model_lab/store.py`** (no Kite import; pure file IO):
   ```python
   NATIVE = ("15minute", "day")
   COLS = ["timestamp", "open", "high", "low", "close", "volume"]

   def bar_path(symbol: str, interval: str) -> Path        # BARS_DIR / interval / f"{sym_file(symbol)}.parquet"
   def clean_bars(df: pd.DataFrame, interval: str) -> pd.DataFrame
   def read_bars(symbol: str, interval: str, start=None, end=None) -> pd.DataFrame
   def write_bars(symbol: str, interval: str, df: pd.DataFrame) -> int   # returns rows in the file after merge
   def list_symbols(interval: str) -> list[str]            # "NSE:..." symbols that have a file
   def coverage(symbol: str, interval: str) -> tuple[pd.Timestamp, pd.Timestamp] | None   # (min, max) timestamp
   def load_manifest(interval: str) -> dict[str, dict]     # BARS_DIR/interval/_manifest.json; {} if missing
   def update_manifest(interval: str, symbol: str, req_from: datetime, req_to: datetime) -> None
   ```
   - `clean_bars`: keep `COLS` only; `timestamp` → `pd.to_datetime`, tz-aware → convert to `Asia/Kolkata` then drop
     tz (naive IST, matching `Store._to_naive`); drop rows with any non-positive open/high/low/close or NaN price;
     volume → int64 (negative or > 2**62 → 0). For `15minute` only, keep rows whose minute % 15 == 0 and whose time
     is within 09:15–15:15 inclusive (drops ISS-12 off-grid rows). For `day`, normalise timestamp to midnight.
     Drop duplicate timestamps (keep last), sort ascending, reset index.
   - `write_bars`: `check_disk()` first; read existing file (if any), concat, `clean_bars`, write to a temp file in
     the same directory then `os.replace` (atomic). Parquet: `engine="pyarrow"`, `compression="zstd"`, `index=False`;
     prices float64, volume int64, timestamp `datetime64[ns]`.
   - `read_bars`: `clean_bars`-shaped DataFrame (empty with `COLS` if no file), filtered to `start <= ts <= end` when
     given (accept `datetime`, `date`, or str).
   - Manifest: `{symbol: {"from": iso, "to": iso}}` = the widest range ever **requested** for the symbol (min of froms,
     max of tos). It records requests, not data, so symbols listed after `from` are not re-requested for their
     pre-listing years every run. Write it atomically (temp + `os.replace`).

2. **New `research/model_lab/universe.py`:**
   ```python
   def snapshot_instruments(kite) -> pd.DataFrame
   def latest_snapshot() -> pd.DataFrame                   # newest UNIVERSE_DIR/nse_eq_*.csv
   def build_liquidity_panel(symbols: list[str] | None = None) -> pd.DataFrame
   def liquid_universe(asof, top_n: int, panel: pd.DataFrame | None = None, min_sessions: int = 200) -> list[str]
   def intraday_fetch_list(years: list[int], top_n: int, panel: pd.DataFrame | None = None) -> list[str]
   ```
   - `snapshot_instruments`: rows of `kite.instruments("NSE")` with `segment == "NSE"`, `instrument_type == "EQ"`,
     no `-` in `tradingsymbol`, and NOT ETF-like (`"ETF" in name.upper()` or `tradingsymbol` ends with `BEES`, `ETF`
     or `IETF`, or `"BEES" in tradingsymbol`). Columns: `symbol` (`"NSE:" + tradingsymbol`), `tradingsymbol`,
     `instrument_token`, `name`, `lot_size`, `tick_size`. Save to `UNIVERSE_DIR/nse_eq_<YYYYMMDD>.csv` (today) and
     return it. Survivorship (no delisted names) is a known limitation; write it in the module docstring.
   - `build_liquidity_panel`: from the stored `day` bars of every symbol (or `symbols`), compute per symbol and date
     `tv = close * volume` and `med_tv_252 = tv.shift(1).rolling(252, min_periods=200).median()` — the
     **shift(1) is required** so the value at date D uses only sessions before D. Long format columns
     `date, symbol, med_tv_252, n_sessions` (n_sessions = count of prior sessions); save to
     `UNIVERSE_DIR/liquidity_daily.parquet` (zstd) and return it.
   - `liquid_universe(asof, top_n)`: for each symbol, take its last panel row with `date < asof` (strictly before);
     require `n_sessions >= min_sessions` and a row within the 10 calendar days before `asof` (still trading);
     return the top `top_n` symbols by `med_tv_252`, ties broken by symbol name. Exclude `NSE:NIFTY 50` and
     `NSE:INDIA VIX`.
   - `intraday_fetch_list(years, top_n)`: union over `y in years` of `liquid_universe(date(y, 1, 1), top_n)`,
     sorted.

3. **New `research/model_lab/fetch.py`** — CLI `.venv/bin/python -m research.model_lab.fetch <stage> [opts]`.
   Reuse `trader.data.historical._fetch_with_retry` and `_date_chunks` (do not copy them). Chunking: 60 days for
   `15minute`, 2000 days for `day` (same constants as `trader.data.historical`). Kite via
   `trader.auth.session.create_kite()`; on failure print: run `.venv/bin/python scripts/kite_totp_refresh.py
   --no-restart` and exit 2.
   Stages:
   - `seed` — no Kite. Open `data/market.db` read-only (`sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, path =
     `REPO_ROOT / "data" / "market.db"`). For every `(instrument, timeframe)` with timeframe in `NATIVE`, read rows,
     `write_bars`, then `update_manifest(interval, symbol, min_ts, max_ts)` from the cleaned data. Print per-interval
     totals.
   - `market` — `NSE:NIFTY 50` and `NSE:INDIA VIX` (tokens from `kite.instruments("NSE")` by `tradingsymbol`):
     `15minute` from `--from` (default 2015-01-01) and `day` from `--day-from` (default 2008-01-01), to `--to`
     (default: now).
   - `daily` — `day` bars from `--day-from` (default 2008-01-01) for every symbol of the latest snapshot (take a new
     snapshot with `--snapshot`, or automatically if none exists), or `--symbols`.
   - `intraday` — `15minute` from `--from` (default 2015-01-01) for `--symbols`, or else
     `intraday_fetch_list(years=--years, top_n=--top)` (defaults: years 2016..current year, top 100) unioned with every
     symbol that already has a `15minute` file (so the seeded names are backfilled to `--from` too).
   - `qa` — no Kite; see step 4.
   Common rules for the fetching stages:
   - **Gap logic per symbol from the manifest**: if no manifest entry → request `[from, to]`. Otherwise request only
     `[from, m.from)` when `from < m.from` and `(m.to, to]` when `to > m.to` (skip a side when it is < 1 day). After a
     successful symbol, `update_manifest` with the requested range. A symbol that raises: log it, record nothing,
     continue (`--fail-fast` re-raises).
   - Each chunk result → DataFrame (`date` renamed to `timestamp`) → `write_bars` once per symbol (concat the
     chunks; do not rewrite the file per chunk).
   - Throttle: sleep `--sleep` seconds (default 0.34) after every request (Kite allows ~3 historical req/s;
     `_fetch_with_retry` already backs off on "Too many requests").
   - `--dry-run`: print the number of symbols and the estimated request count (chunks) and exit without Kite calls
     for data (the instrument list call is allowed).
   - `--max-symbols N` limits the run (for smoke tests).
   - `check_disk()` before each symbol; stop cleanly with a message when it raises.
   - Log to stdout and to `LOGS_DIR/fetch_<stage>_<YYYYmmdd_HHMMSS>.log`: one line per symbol (rows written, file
     min/max, seconds), and a final summary (symbols done / failed / requests / elapsed).
   - Symbols with no instrument token in today's instrument list (renamed/delisted) are logged as `no_token` and
     skipped.

4. **QA** — `research/model_lab/qa.py` with `qa_report(interval: str) -> pd.DataFrame`, and the `qa` stage writes it
   to `LAB_ROOT/qa_<interval>.csv` and prints the flagged rows. Per symbol: `rows, first, last, dup_ts` (should be 0),
   `max_jump_pct` and `max_jump_ts` = the largest `|open[t] / close[t-1] - 1|` (in %), `n_jumps_30` = count of such
   jumps > 30 % (likely unadjusted splits/bonuses — the lab does not fix them, it flags them), and `zero_vol_frac`
   (share of bars with volume 0). Sort by `max_jump_pct` descending.

## Tests required

New file `tests/test_model_lab_store.py` (pure, no Kite, no network; redirect `BARS_DIR`/`UNIVERSE_DIR` to `tmp_path`
via `monkeypatch.setattr` on the modules that use them):
- `test_clean_bars_drops_offgrid_15m` — rows at 09:20, 15:16, 15:25, 15:30, 09:00 are dropped; 09:15, 12:45,
  15:15 kept; duplicate timestamps keep the last.
- `test_clean_bars_tz_aware_to_naive_ist` — a `+05:30` timestamp 09:15 stays 09:15 naive.
- `test_write_read_roundtrip_and_merge` — two overlapping writes merge, sorted, deduplicated; `coverage` matches.
- `test_write_is_atomic_temp_cleanup` — no temp files remain after a write.
- `test_manifest_widens_only` — later narrower requests don't shrink the recorded range.
- `test_gap_ranges` — expose the gap computation as a pure helper `fetch.gap_ranges(manifest_entry, req_from,
  req_to) -> list[tuple[datetime, datetime]]` and test: no entry; fully covered; older backfill only; newer tail
  only; both sides; < 1 day side skipped.
- `test_liquidity_panel_is_pit` — synthetic day bars: changing the volume on date D does not change `med_tv_252` at
  date D (only from D+1 on).
- `test_liquid_universe_strictly_before_asof` — a symbol whose liquidity spikes on `asof` itself is not ranked by it;
  stale symbols (last row > 10 days before asof) are excluded; index symbols excluded.
- `test_snapshot_filters` — a fake instrument list (dict rows) with EQ/BE-suffix/ETF/BEES/INDICES rows → only the
  plain non-ETF EQ names survive.
- `test_seed_reads_market_db_readonly` — build a tiny SQLite file with the `candles` schema (incl. one off-grid
  row), point the seed at it (make the source path a parameter: `seed(db_path: Path)`), assert parquet rows match the
  on-grid rows, the manifest is written, and the source file's bytes are unchanged.
- `test_qa_flags_jump` — a 50 % overnight jump is reported with its timestamp.

Suites that stay green: the full suite (`.venv/bin/python -m pytest -q`).

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] new tests above present and passing, none touching network or `data/market.db`
- [ ] no file under `trader/`, `scripts/`, `config/`, `main.py` changed
- [ ] `research/model_lab/` imports only from `trader.data`, `trader.auth`, `trader.core` (plus stdlib/pandas/numpy/pyarrow)
- [ ] `seed` never opens `data/market.db` writable (URI `mode=ro`)
- [ ] fetcher resumable via manifest; `--dry-run` makes no historical-data calls
- [ ] atomic writes (temp + `os.replace`) for parquet and manifest
- [ ] Do NOT run any fetching stage against Kite (the main session runs them after validation); `seed` and `qa` may be
      run for a smoke test only if `lab_data/model_lab/` is empty before and is deleted afterwards — prefer tests.

## Completion record
- **Completed:** 2026-10-18 · trader-implementer (sonnet), validated by the main session (full suite 619 passed with L0b; 11 new tests).
- **Commit:** see the L0 completion commit on `exp/model-lab`.
- **Deviations (accepted):** tests patch `paths.BARS_DIR`/`UNIVERSE_DIR` (modules read them at call time); `qa` takes
  `--interval day|15minute|all`; `intraday` builds the liquidity panel if missing; `gap_ranges` uses ±1 s instead of
  half-open bounds; tokens looked up over `NSE` + `INDICES` segments; `--dry-run` still calls `instruments()`.
- **Main-session fix:** default `--to` = end of yesterday (23:59), not now — a run during market hours would have stored
  today's still-forming bars and the manifest would never re-request them.
- **Validation runs:** `seed` → 105 × 15m (2.75M rows, 58 MB, ~21 B/candle) + 532 × day; `market` → NIFTY 50 / INDIA VIX
  15m from 2015-01-09, day from 2008 (VIX from 2009-03); `daily` (2,679 symbols, ~11.2k requests) started in background.
