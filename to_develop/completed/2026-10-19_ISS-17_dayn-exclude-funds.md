# ISS-17 — keep ETFs / fund units out of the `dayn` liquidity universe
Written: 2026-10-19 · Tag: ISS-17 · Status: DONE 2026-10-19

## Source

> Bhavcopy lists ETFs and other exchange-traded fund units under series EQ, and the L0c build put every security into
> the `day_nse` liquidity panel. … PIT top-200 on `dayn` therefore contained BANKBEES, GOLDBEES, LIQUIDBEES,
> LIQUIDCASE, NIFTYBEES and SILVERBEES in some years … Of the 4,045 securities, 376 have an ISIN starting with `INF`.

— `ISSUES/ISS-17-dayn-universe-includes-etfs/DETAIL.md`, 2026-10-19. Documented bug, pre-approved.

## Intent
A security is a **fund** iff any of its ISINs starts with `"INF"` OR `universe._is_etf("", last_symbol)` is True.
Funds keep their bar files (harmless) but are excluded from the `day_nse` liquidity panel, so they never enter a
`dayn`/`weekn` universe. **Must NOT change:** anything outside `research/model_lab/nse_bhav.py` and
`tests/test_model_lab_nse_bhav.py`; the `day` panel; adjustment logic. No network, do not touch `lab_data/`.

## Implementation steps
1. `nse_bhav.py`: add `is_fund(isins, last_symbol) -> bool` (isins = the list/array stored in `securities.isins`;
   tolerate None/NaN entries).
2. In `build()`: add column `is_fund` to the securities table before it is written; when `liquidity` is True call
   `universe.build_liquidity_panel(symbols=[...], interval="day_nse")` with `"NSE:" + file_name` of every NON-fund
   security (indices are excluded by the panel as today). Add `n_funds` to the returned summary dict.
3. Add a stage-less helper call path: `python -m research.model_lab.nse_bhav panel` rebuilds only the liquidity panel
   from the existing `securities.parquet` (same non-fund rule) — so the main session can apply the fix without a full
   rebuild. Securities files written before this change have no `is_fund` column: compute it on the fly.

## Tests (extend `tests/test_model_lab_nse_bhav.py`)
- `test_is_fund`: `["INF204KB14I2"]` → True; `["INE002A01018"]` + "RELIANCE" → False; `[None]` + "NIFTYBEES" → True;
  `["INE002A01018", "INF000000000"]` → True.
- `test_build_excludes_funds_from_panel`: synthetic panel with one stock and one fund (ISIN INF…) → bars written for
  both, `securities.parquet` has `is_fund` [False, True], `liquidity_day_nse.parquet` contains only the stock.
- `test_panel_stage_rebuilds_without_funds`: an existing `securities.parquet` WITHOUT `is_fund` + bar files → `panel`
  stage writes a panel without the fund.

## Acceptance checklist
- [ ] full pytest green · [ ] funds flagged and out of the panel · [ ] `panel` stage works on old securities files
- [ ] no other behaviour changed · [ ] no network / `lab_data/` untouched

## Completion record
Validated 2026-10-19 (main session): diff matches the guide; full pytest **706 passed** on the merged branch; commit ef6d50e. Implementer deviations accepted: `is_fund` also accepts a ';'-joined ISIN string (the stored format); indices are no longer rows of `liquidity_day_nse.parquet` (they were already filtered out of every universe). Real data: `nse_bhav panel` rebuilt the panel; PIT top-200 ever-members 505, none ETF-like.
