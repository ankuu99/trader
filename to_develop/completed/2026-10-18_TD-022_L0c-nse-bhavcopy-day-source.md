# Model Lab L0c — survivorship-free daily source from NSE bhavcopy archives (`dayn` timeframe)
Written: 2026-10-18 · Tag: TD-022 · Status: DONE 2026-10-19 (after one rework)

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

**2026-10-19, main session: signed off after one rework.** Implementation (trader-implementer, twice) reviewed against
the guide and the addendum. Full pytest **700 passed**. Commits: first build (L0c, earlier on exp/model-lab) and the rework
b187999.

**Implementer deviations (accepted):**
- seed loop skips day_nse;
- dayn/weekn treated like day/week in factors;
- sequential security assignment rather than union-find;
- (rework) `build()` warns instead of raising when `ca_events.parquet` is missing;
- (rework) `adjust` returns 4 values.

**Real-data run (2008-01-01 → 2026-10-16):**
- 4,635 daily files plus 22 weekend special sessions, 0 unreadable.
- 4,045 securities, **1,070 delisted**.
- NSE corporate-actions API: 1,261 split/bonus events; 1,204 attached, 50 unmatched (`ca_unmatched.csv`), 11 with an
  observed gap ≠ factor by more than 25 %.

**Validation vs Kite `day` (2,406 overlapping symbols):**

| Check | First build (PREVCLOSE) | Rework |
|---|---|---|
| Median of per-symbol median level diff | 3.1 % | **0.00 %** |
| Mean share of days within 0.5 % (levels) | 0.40 | **0.87** |
| Symbols with ≥ 90 % of days within 0.5 % (levels) | — | 81 % (pre-registered gate: 85 %) |
| Daily-return agreement within 0.5 %: mean share of days | — | **0.993** |
| Symbols with ≥ 99 % / ≥ 95 % of days agreeing (returns) | — | **94.1 % / 96.5 %** |

**Deviation from the pre-registered level gate, accepted with reasons.** The remaining level gaps are constant offsets
that step at dividend ex-dates, mostly in 2025–26:
- GSFC steps on 2025-09-08 and 2026-09-11;
- PTC on 2026-08-10 and 2026-10-07;
- TNPL on 2026-09-17;
- BALMLAWRIE on 2025-09-16, 2026-03-11 and 2026-09-11.

So Kite folds (recent) dividends into its adjustment, and the NSE series adjusts only splits and bonuses, which is the
intended design. Level offsets do not change returns, and every lab factor and target is return-based. On returns, the
two sources agree.

**Large return mismatches (> 5 % on a day)** come to 1,892 days in 319 of 2,374 symbols, concentrated in a few names
where **Kite's own history is broken**:
- PRIVISCL: Kite close ₹0.05 in 2015–20;
- GNFC: Kite at half the NSE close in 2008–09 and 2013–16;
- HINDPETRO: NSE raw 2008-01-21 close 271.80 × three bonus factors (1/3, 2/3, 2/3) = 40.27, matching the NSE-adjusted
  series, while Kite shows 17.85, with each bonus gap_ratio ≈ 1.0.

The NSE source is the better series there. Return validation is kept in `nse_bhav/validation_returns.csv`.

**`dayn` is cleared for the pre-registered re-runs (ML-A01n, ML-A11n, SN-1..3).**

## Addendum 2026-10-19 — validation FAIL; rework the adjustment source and the fetch calendar

**What happened (main session, real run 2026-10-19).** Fetch/parse/build ran clean (4,635 files 2008-01-01 →
2026-10-16, 0 unreadable, 4,045 securities, 1,070 delisted). Validation against Kite FAILED: 2,406 overlapping
symbols, median of per-symbol median |adj close / Kite close − 1| = 3.1 %, mean share of days within 0.5 % = 0.40.
Root causes, both verified on raw rows:
1. **The guide's premise was wrong: bhavcopy PREVCLOSE is NOT adjusted on an ex-date.** RELIANCE 1:1 bonus
   2017-09-07: PREVCLOSE 1645.40 = the raw previous close, CLOSE 818.10; same on 2024-10-28 (2655.70 → 1334.35). So
   the PREVCLOSE rule detected almost no real splits/bonuses (RELIANCE had none of its two bonuses).
2. **Weekend special sessions are not fetched** (Budget Saturdays 2015-02-28, 2020-02-01, 2025-02-01; Sunday
   2026-02-01; other Saturday sessions). The next weekday's PREVCLOSE then refers to the missing session's close and
   the PREVCLOSE rule turned ordinary moves into false "corporate actions" (RELIANCE 2020-02-03 f=0.980,
   2026-02-02 f=0.965).

**New adjustment source — NSE corporate-actions API (probed 2026-10-19).**
`GET https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY`
returns JSON (one call per calendar year works: 1,524–2,692 rows per year, 2008 → 2026) after a warm-up
`GET https://www.nseindia.com/` on the same `requests.Session` with headers `User-Agent` (desktop Chrome),
`Accept: application/json,text/plain,*/*`, `Accept-Language: en-US,en;q=0.9`,
`Referer: https://www.nseindia.com/companies-listing/corporate-filings-actions`. Row keys include `symbol`, `isin`,
`series`, `subject`, `exDate` (`'07-Sep-2017'`), `faceVal`. Later-delisted names are present (HDFC 2010 split,
IVRCLINFRA 2010 bonus). 1,280 rows mention bonus/split.

### Changes (supersede the PREVCLOSE parts of steps 1 "build — adjustment")

A. **fetch calendar:** `fetch_range` iterates **every calendar day** (weekends included; a weekend 404 on both
   formats is logged `holiday_or_missing` like any holiday). Resumable: skip a date whose zip exists OR whose latest
   `fetch_log.csv` status is `holiday_or_missing` (no re-request), unless `--retry-missing` is passed. Rename
   `weekdays()` → `calendar_days()`; update its test.

B. **new stage `ca`:** `python -m research.model_lab.nse_bhav ca [--from 2008] [--to 2026]` — one request per
   calendar year (session warm-up once, headers above, ≤ 1 request/second, 3 retries with backoff, re-warm the
   session once on a 401/403), raw JSON saved to `NSE_BHAV_DIR/ca/{YYYY}.json` (skip a year whose file exists,
   except the current year which is always refreshed). Then parse all years into `NSE_BHAV_DIR/ca_events.parquet`:
   `symbol, isin, series, ex_date (datetime), subject, kind ("bonus"|"split"|"bonus+split"), factor (float)`.
   Unmatched/unparseable bonus/split subjects go to `ca_unparsed.csv` (symbol, ex_date, subject).

C. **subject parser `parse_ca_subject(subject) -> float | None`** (case-insensitive; returns the price factor
   applied to prices BEFORE the ex-date; None = not a price-adjusting event):
   - **Split:** regex on `(?:split|sub-?division)` followed by `from`/optional, then two face values written as
     `Rs`/`Re` with optional `.`, spaces, `/-`, e.g. `r[se]\.?\s*(\d+(?:\.\d+)?)` twice → `factor *= to / from`.
   - **Bonus:** `bonus` followed (optionally after `-`, `shares in the ratio of`) by `a\s*:\s*b` → `factor *= b / (a + b)`
     (NSE writes "Bonus a:b" = a new shares for every b held). **Ignore** bonuses of debentures / NCRPS / preference /
     DVR (the subject contains `deb`, `ncrps`, `preference` or `dvr` within the bonus clause) — they do not change
     the equity share count.
   - Both in one subject → multiply (kind `bonus+split`). Dividends, AGM, rights, demergers, schemes → None.
   - Must parse every one of these real subjects (expected factor in brackets):
     `' Bonus 1:1'` [0.5] · `'Bonus 1:10'` [10/11] · `'Bonus 1:2  '` [2/3] · `'Bonus 3 : 2'` [0.4] ·
     `'Bonus - 1:1'` [0.5] · `'Bonus shares in the ratio of 1:1'` [0.5] ·
     `' Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share'` [0.2] ·
     `'Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share '` [0.1] ·
     `'Fv Split Rs.10/- To Rs.2/'` [0.2] · `'Face Value Split From Rs.10/- To Rs.2/-'` [0.2] ·
     `'FV Split-Rs10/- to Re.1/-'` [0.1] · `'Face Value  Split From Rs. 5 To Rs. 2/-'` [0.4] ·
     `'Bonus 1:1 And Face Value Split From Rs.10/- To Re.1/-'` [0.05] ·
     `'Annual General Meeting/Dividend Rs.2/- Per Share/Bonus 1:1'` [0.5] ·
     `'Bonus 1:1 (Record Date Revised)'` [0.5];
     and return None for: `'Scheme Of Arrangement - Bonus Debentures 1:1'`, `'Sch Of Agmt- Bonus Deb1:1'`,
     `'Scheme of Arrangement - Bonus NCRPS 1:1'`, `'Bonus 1 DVR : 10 Eq Share'`,
     `'Annual General Meeting/Dividend - Rs 5 Per Share'`, `'Rights 1:5 @ Premium Rs 100/-'`.

D. **build — adjustment (replaces the PREVCLOSE rule; delete `ADJ_MIN_MOVE`/`ADJ_MIN_DIFF` use):** each
   `ca_events` row is attached to ONE security row: the first panel row on/after `ex_date` (within 5 calendar days)
   of the security whose rows on that date carry the event's ISIN; else of the security whose symbol equals the
   event's symbol on that date; else the event goes to `ca_unmatched.csv`. Duplicate events (same security, same
   attached date, same factor) count once; different events on the same date multiply. `f_t` = the attached
   factor (1 elsewhere); the backward cumulative product, OHLC × A_t and volume ÷ A_t are as before.
   `corporate_actions.parquet` gains columns `kind, subject, gap_ratio` where `gap_ratio = (open_t / close_{t−1}) / f_t`
   (raw prices of that security; NaN on its first row) — a QA number (≈ 1 when the price really jumped by the
   factor). The build summary adds `n_ca_matched, n_ca_unmatched, n_gap_suspect` (|gap_ratio − 1| > 0.25).
   Also write `prevclose_gaps.csv` (QA only, never used for adjustment): rows where
   |prevclose_t / close_{t−1} − 1| > 0.02 within a security that are not an attached ex-date
   (sec_id, date, prevclose, prev_close, ratio).

E. **validate:** unchanged, plus print the 20 worst symbols (by share within 0.5 %) with their sec_id.

### Tests (replace/extend `tests/test_model_lab_nse_bhav.py`)
- `test_parse_ca_subject_real_variants` — every subject listed in C with its factor (abs tol 1e-9) and the Nones.
- `test_ca_stage_saves_and_parses` — mocked session: warm-up GET then one GET per year returning a small JSON list;
  files written under `ca/`, existing past year skipped, `ca_events.parquet` built with the right factors, an
  unparseable bonus/split subject lands in `ca_unparsed.csv`.
- `test_adjustment_from_ca_events` (replaces `test_adjustment_split_and_bonus`): a synthetic security with a 1:1
  bonus and a later 10→2 split given as `ca_events` (raw prices halve / fifth on the ex-dates, PREVCLOSE raw as NSE
  writes it) → adjusted closes continuous, volume scaled inversely, last row unadjusted, `gap_ratio` ≈ 1,
  `corporate_actions.parquet` exactly the two events; an event whose ISIN matches nothing but whose symbol does is
  attached by symbol; an event matching nothing lands in `ca_unmatched.csv`.
- `test_prevclose_never_adjusts` — a row with prevclose ≠ previous close and no CA event → no adjustment, row listed
  in `prevclose_gaps.csv`.
- `test_calendar_days_and_missing_skip` — weekends included; a date logged `holiday_or_missing` is not requested
  again; `--retry-missing` requests it.
- Existing tests keep passing (update the ones that encoded weekday-only or PREVCLOSE adjustment).

### Acceptance (main session will run fetch → ca → parse → build → validate on real data)
- full pytest green; all items above; still no imports from `trader.*`; do NOT run real fetches or touch `lab_data/`.
- Real-data gate (main session): validation median-of-median |diff| ≤ 0.1 % and ≥ 85 % of overlapping symbols with
  ≥ 90 % of days within 0.5 %; residual worst symbols explained (demergers/rights that Kite treats differently) in
  the completion record.
