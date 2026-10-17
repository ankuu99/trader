# ISS-10: `test_parity_golden` / pipeline golden fails on clean HEAD

Source: `todo.md`, as of 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

- **Golden parity `test_pipeline_golden` is STALE (pre-existing, NOT the restore
  fix)** — fails on the clean tree too, with numpy/sklearn matching the golden's
  pin (2.4.4/1.8.0); divergence traces to the stale-rearm commit f01f702 shipping
  without a golden regen. Regenerate with `REGEN_GOLDEN=1` in a dedicated reviewed
  commit per the test's own docstring.
