# Model Lab L0c — survivorship-free daily source from NSE bhavcopy archives (`dayn` timeframe)
Written: 2026-10-18 · Tag: TD-022 · Status: TO DO

## Source

> Needed: a delisting-inclusive daily OHLCV source for NSE equities — candidates: NSE bhavcopy archives (daily all-stock
> files, include later-delisted names), or a vendor history. Then re-run the day-TF arms on that universe; A07 stays
> SUSPECT until then.

— `TODO/TD-022-survivorship-free-universe/DETAIL.md`, as of 2026-10-18. Owner go-ahead 2026-10-18 ("Do all three",
covering "fix the delisted-stock gap (TD-022) before trusting any ₹ figure").

**Probe (main session, 2026-10-18):** archives download with browser headers (HTTP 200). Of the top-500 EQ names by
traded value on 2012-01-02, 131 (26 %, ≈ 10 % of traded value) have no ISIN-issuer match on 2026-10-16 — delisted
or merged (JPASSOCIAT, RELCAPITAL, GITANJALI, EDUCOMP, JETAIRWAYS, SINTEX, PUNJLLOYD, VIDEOIND, BHUSANSTL, HDFC,
RANBAXY, SATYAMCOMP, …). Formats:
- **Old** `https://nsearchives.nseindia.com/content/historical/EQUITIES/{YYYY}/{MON}/cm{DD}{MON}{YYYY}bhav.csv.zip`
  (MON upper-case 3 letters, DD 2 digits), columns `SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,
  TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN` — **2008 files have no ISIN/TOTALTRADES columns**; last file 2024-07-05.
- **UDiFF** `https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip`, columns
  `TradDt, …, FinInstrmTp, ISIN, TckrSymb, SctySrs, …, OpnPric, HghPric, LwPric, ClsPric, LastPric, PrvsClsgPric, …,
  TtlTradgVol, TtlTrfVal, TtlNbOfTxsExctd, …` — available from at least 2024-07-05.

## Intent

1. Fetch and keep every NSE capital-market bhavcopy 2008-01-01 → today (resumable, polite).
2. Parse to one daily panel; identify **securities** across symbol renames and ISIN changes.
3. **Adjust for splits/bonuses/rights** using NSE's own adjusted PREVCLOSE (on an ex-date NSE sets PREVCLOSE to the
   adjusted previous close, so `prevclose_t / close_{t−1}` is the day's adjustment factor).
4. Write per-security daily bars as a new lab interval `day_nse` and a new timeframe **`dayn`** (+ `weekn`) that the
   whole lab (factors, targets, splits, runner, scorer, references, portfolio) can use, with a PIT liquidity panel.
5. Validate the adjusted series against Kite's adjusted daily bars for overlapping names.

**Must NOT change:** existing `day`/`week`/15m behaviour or files; existing runs; anything outside
`research/model_lab/`, `scripts/model_lab/prod_pmin.py` (one dict entry), and the named tests. No imports from
`trader.strategies/features/policy/backtest` in `research/model_lab/`. **Do NOT run the real fetch or touch
`lab_data/`** — tests use synthetic files; the main session runs the fetch.

## Implementation steps

1. **`research/model_lab/nse_bhav.py`** (new) — fetch + parse + build + validate, CLI stages
   `python -m research.model_lab.nse_bhav fetch|parse|build|validate [--from 2008-01-01] [--to YYYY-MM-DD]`.
   - Paths: `paths.NSE_BHAV_DIR = LAB_ROOT / "nse_bhav"`; raw zips under `raw/{YYYY}/{YYYYMMDD}.zip`, a
     `fetch_log.csv` (date, url, status, bytes); panel `panel/{YYYY}.parquet`; `securities.parquet`;
     `validation.csv`.
   - **fetch**: dates = every weekday in range (holidays 404). URL: old format for dates ≤ 2024-07-05, UDiFF after;
     on 404 try the other format once. Skip dates whose zip exists (resumable). Headers: a desktop-browser
     `User-Agent` and `Referer: https://www.nseindia.com/`. Rate: ≤ 2 requests/second, 3 retries with backoff on
     network errors / 5xx; a 404 on both formats is logged `holiday_or_missing` (not an error). `paths.check_disk()`
     before starting. Never raise on a single bad date.
   - **parse**: each zip → rows for series in **{EQ, BE, BZ}** only (equity, trade-for-trade, Z category); UDiFF rows
     need `FinInstrmTp == "STK"`. Normalised columns: `date, symbol, series, isin (str or NA), open, high, low, close,
     prevclose, volume (shares), value (₹), trades (NA when absent)`. One panel parquet per year (zstd). Drop rows with
     any non-positive OHLC or close outside [low, high] (count them in a parse log).
   - **build — securities**: sort the panel by date. A **security** is a chain of rows linked by EITHER the same ISIN
     OR the same symbol on consecutive trading days of that symbol (gap ≤ 30 calendar days). Implementation: union-find
     over (isin) and (symbol, run) keys, processing dates in order: a row whose ISIN was seen before joins that
     security; else a row whose symbol traded within the last 30 days joins that symbol's current security (this links
     ISIN changes on face-value splits and the pre-ISIN 2008–2010 rows); else a new security. If the same date would
     put two rows in one security (EQ and BE of the same stock), keep the EQ row. `sec_id` = first ISIN seen in the
     chain, else `"SYM:" + first symbol`. `securities.parquet`: sec_id, all symbols with (from, to), all ISINs, first
     and last date, `last_symbol`, `delisted` = last date < (last panel date − 30 days).
   - **build — adjustment**: per security, rows in date order; factor `f_t = prevclose_t / close_{t−1}` (previous row
     of the same security). Treat as a corporate action only when `|f_t − 1| > 0.02` AND `prevclose_t` differs from
     `close_{t−1}` by more than 1 tick-ish (`abs(diff) > 0.05`); otherwise `f_t = 1`. Cumulative backward factor
     `A_t = Π_{s>t} f_s` (A = 1 on the last row); adjusted `open/high/low/close = raw × A_t`, `volume = raw / A_t`
     (rounded to int), `value` unchanged. Record every factor ≠ 1 in `corporate_actions.parquet` (sec_id, date, f).
   - **build — bars**: write each security to `paths.BARS_DIR / "day_nse" / f"{name}.parquet"` with the lab store's
     day schema (`timestamp` normalised date, open, high, low, close, volume) via `store.write_bars`-equivalent atomic
     write, where `name = sym_file(last_symbol)`; if two securities share a last symbol, the one that ended earlier
     gets `name + "~" + sec_id` . Also copy Kite's `NSE:NIFTY 50` and `NSE:INDIA VIX` day bars into `day_nse`
     unchanged (indices are not in bhavcopy; market factors need them under the same interval).
   - **validate**: for every security whose `last_symbol` exists in Kite's `day` store: join on date; report per
     symbol the median |adj close / kite close − 1| and the share of days within 0.5 %; overall summary printed and
     written to `validation.csv`.

2. **Lab wiring for the new interval/timeframes** (mirror `day`/`week` everywhere):
   - `store.py`: `NATIVE += ("day_nse",)`; cleaning for `"day_nse"` = the `"day"` rules (normalise timestamp).
   - `bars.py`: `TFS += ("dayn", "weekn")`; `SOURCE["dayn"] = SOURCE["weekn"] = "day_nse"`; `derive` treats `dayn`
     like `day` and `weekn` like `week`.
   - `factors.py`: `HIGHER_TF["dayn"] = ["weekn"]`, `HIGHER_TF["weekn"] = []`; calendar `tod = 0` for `dayn`/`weekn`;
     any other `tf in ("day", "week")` branch includes the new keys.
   - `targets.py`: `SCALES`/`HOLD_H` entries for `dayn` = `day`'s, `weekn` = `week`'s.
   - `splits.py`: `EMBARGO["dayn"] = "5D"`, `EMBARGO["weekn"] = "21D"`. `score.py`: `BARS_PER_YEAR` entries
     (`dayn` 248, `weekn` 52); `TOL` derives automatically from SCALES.
   - `universe.py`: `build_liquidity_panel(symbols=None, interval="day")` reads that interval; panel file
     `liquidity_daily.parquet` for `day` (unchanged) and `liquidity_day_nse.parquet` for `day_nse`;
     `_load_panel(interval="day")`; CLI/`build` stage gains `--interval`. Index symbols excluded as today.
   - `source.py`: `LabSource.membership(years, top_n, tf)` loads the panel of `bars.SOURCE[tf]` (day-sourced TFs
     → `day`, `dayn/weekn` → `day_nse`; 15m-sourced TFs keep using the `day` panel as today). **`runner.py` passes
     `tf=spec.tf`** to `source.membership` (SynthSource already accepts `tf`).
   - `references.py` works unchanged via `bars.load` (`--tf dayn`); `scripts/model_lab/prod_pmin.py`:
     `_TF_TEMPLATE["dayn"] = _TF_TEMPLATE["day"]`.

## Tests required (new `tests/test_model_lab_nse_bhav.py`, plus small extensions)
- `test_parse_old_and_udiff_formats` — synthetic zips of both formats (incl. a 2008-style file without ISIN): rows,
  series filter (EQ/BE/BZ kept, others dropped), UDiFF `FinInstrmTp` filter, normalised columns, bad-OHLC drop.
- `test_url_for_date_and_fallback` — format by date; a mocked 404 on the primary triggers one try of the other;
  404 on both logs `holiday_or_missing`; existing zip skipped (no request).
- `test_security_chain_rename_isin_change_and_pre_isin` — symbol rename with the same ISIN → one security; ISIN
  change on the same symbol next day → one security; 2008 rows without ISIN joined to the same symbol's later ISIN;
  a symbol reused after a 60-day gap by a different ISIN → a new security; EQ+BE same day → EQ kept.
- `test_adjustment_split_and_bonus` — a 1:5 split (prevclose = close/5 on the ex-date) and a 1:1 bonus: adjusted
  closes continuous across the ex-dates, volume scaled inversely, last row unadjusted, small (|f−1| ≤ 2 %) moves
  ignored; `corporate_actions.parquet` lists exactly the two events.
- `test_build_writes_bars_and_indices` — bars written under `day_nse`, collision naming with `~sec_id`, NIFTY/VIX
  copied, `securities.parquet` delisted flag.
- `test_validate_against_kite` — synthetic Kite day bars equal to the adjusted series → median diff 0, share 1.0.
- `test_dayn_wiring` — `bars.load(sym, "dayn")` and `"weekn"` derive like day/week; `targets.build_targets(..,
  "dayn")` has the day columns; `EMBARGO`, `HIGHER_TF`, `BARS_PER_YEAR` have the new keys;
  `LabSource.membership(..., tf="dayn")` reads `liquidity_day_nse.parquet` (monkeypatched paths).
- Existing suites unchanged (day/week/15m behaviour identical).

## Acceptance checklist
- [ ] full pytest green
- [ ] old (incl. pre-ISIN 2008) and UDiFF formats parsed; EQ/BE/BZ only; resumable polite fetch with format fallback
- [ ] securities chain across renames, ISIN changes and pre-ISIN years; delisted flag
- [ ] split/bonus adjustment from NSE PREVCLOSE; events logged; small moves ignored
- [ ] `dayn`/`weekn` usable by factors, targets, splits, runner (membership from the `day_nse` panel), scorer, refs,
      portfolio; existing TFs unchanged
- [ ] validation against Kite implemented (run by the main session)
- [ ] no imports from `trader.strategies/features/policy/backtest` in `research/model_lab/`
- [ ] Do NOT run the real fetch; do not touch `lab_data/`

## Completion record
_(filled by the main session after validation)_
