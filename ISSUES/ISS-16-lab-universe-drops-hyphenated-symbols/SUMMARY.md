# ISS-16: Model Lab universe drops every symbol containing a hyphen (BAJAJ-AUTO, …)

- **Area:** Model Lab data (TD-021, `research/model_lab/universe.py::snapshot_instruments`)
- **Status:** FIXED 2026-10-19 (37029f5) — rule: a 2-char code after the last '-' is a series/bond variant; 7 real names now kept and fetched; existing runs A01–A11 / SC1–SC6 were made without them (not re-run; the `dayn` source has them natively)
- **Source:** Main session, 2026-10-18 (TD-022 bhavcopy probe)
- **Fix commits:** 37029f5 (code + tests); data refetch + panel rebuild 2026-10-19
