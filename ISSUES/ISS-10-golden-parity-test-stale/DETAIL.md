# ISS-10: `test_parity_golden` / pipeline golden fails on clean HEAD

Source: `todo.md`, as of 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

- **Golden parity `test_pipeline_golden` is STALE (pre-existing, NOT the restore
  fix)** — fails on the clean tree too, with numpy/sklearn matching the golden's
  pin (2.4.4/1.8.0); divergence traces to the stale-rearm commit f01f702 shipping
  without a golden regen. Regenerate with `REGEN_GOLDEN=1` in a dedicated reviewed
  commit per the test's own docstring.

## Addendum 2026-10-17 — fixed; original attribution was wrong

The f01f702 attribution above is WRONG. Bisect + 126-commit scan: the only output-changing commit is f9a7f9f (2026-06-18) — `config/config.yaml` `risk.trading_start` 09:30 → 09:15; the harness reads the real config. Re-baselined from a clean HEAD worktree; old→new 84→23 trades. Guide: `to_develop/completed/2026-10-17_ISS-10_regenerate-pipeline-golden.md`. Follow-up: TD-014.
