# ISS-16 — keep real hyphenated equity symbols in the Model Lab universe
Written: 2026-10-19 · Tag: ISS-16 · Status: TO DO

## Source

> While probing NSE bhavcopy archives for TD-022, BAJAJ-AUTO (top-10 by traded value in 2012) was missing from the
> lab's daily bars. Cause: `snapshot_instruments` skips any Kite NSE EQ instrument whose tradingsymbol contains "-"
> (`... or "-" in ts: continue`). The intent was to drop series-suffixed instruments (e.g. `XYZ-BE`, `XYZ-SM`, rights
> `-RE`, bonds `-N1`), but it also drops real equity symbols with a hyphen in the name (BAJAJ-AUTO, and any other
> hyphenated EQ ticker).

— `ISSUES/ISS-16-lab-universe-drops-hyphenated-symbols/DETAIL.md`, as of 2026-10-18. Documented bug, pre-approved.

**Probe (main session, 2026-10-19), Kite `instruments("NSE")`, segment NSE, type EQ:** 7,189 tradingsymbols contain
"-". The part after the last "-" is a **2-character** series code in every case except 5: `NAM-INDIA`, `HCL-INSYS`,
`BOSCH-HCIL`, `UMIYA-MRO`, `BAJAJ-AUTO` (codes seen: SG, N0–N9, NA–NS, SM, BE, GS, ST, TB, SF, GB, BZ, IV, RR, RL, …).
Series rows of the real names (`BAJAJ-AUTO-BE`) also end in a 2-character code.

## Intent

A Kite EQ tradingsymbol is a series/bond/instrument variant (dropped) **iff it contains "-" and the part after the
last "-" is exactly 2 characters long**. Everything else is kept (subject to the existing ETF filter).

**Must NOT change:** anything outside `research/model_lab/universe.py` and `tests/test_model_lab_fetch.py` (or a new
test file, see below). Do not run any fetch, do not touch `lab_data/`.

## Implementation steps

1. `research/model_lab/universe.py`: add

   ```python
   def _is_series_variant(ts: str) -> bool:
       """XYZ-BE, XYZ-SG, XYZ-N1 … (2-char code after the last '-') are series / bond variants; BAJAJ-AUTO is a stock."""
       return "-" in ts and len(ts.rsplit("-", 1)[1]) == 2
   ```

   and in `snapshot_instruments` replace `or "-" in ts` with `or _is_series_variant(ts)`.
2. Update the module docstring's limitations line only if it mentions hyphens (it does not today — leave it).

## Tests required (new `tests/test_model_lab_universe.py`)

- `test_is_series_variant`: True for `ABC-BE`, `ABC-SG`, `ABC-N1`, `BAJAJ-AUTO-BE`; False for `BAJAJ-AUTO`,
  `NAM-INDIA`, `HCL-INSYS`, `RELIANCE`.
- `test_snapshot_keeps_hyphenated_stocks`: a fake kite whose `instruments("NSE")` returns EQ rows `RELIANCE`,
  `BAJAJ-AUTO`, `BAJAJ-AUTO-BE`, `ABC-SG`, an ETF (`NIFTYBEES`), and a non-EQ row; `paths.UNIVERSE_DIR` monkeypatched
  to `tmp_path` → symbols are exactly `NSE:RELIANCE`, `NSE:BAJAJ-AUTO`.

## Acceptance checklist
- [ ] full pytest green
- [ ] only the 2-char-suffix rule changed; ETF and segment/type filters unchanged
- [ ] tests above present
- [ ] no fetch run; `lab_data/` untouched

## Completion record
_(filled by the main session after validation)_
