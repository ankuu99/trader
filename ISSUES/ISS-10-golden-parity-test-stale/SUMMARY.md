# ISS-10: `test_parity_golden` / pipeline golden fails on clean HEAD

- **Area:** tests
- **Status:** FIXED 2026-10-17 — golden re-baselined; drift was config (f9a7f9f trading_start 09:30→09:15), not code. Re-break risk: TD-014
- **Source:** `todo.md`, as of 2026-10-17
- **Fix commits:** see `git log -- tests/fixtures/golden_pipeline.json`
