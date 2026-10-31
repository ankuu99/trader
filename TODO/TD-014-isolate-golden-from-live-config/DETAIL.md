# TD-014: Isolate the parity golden harness from the live config.yaml

Source: ISS-10 implementer report, 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

> **Harness coupling:** `test_pipeline_golden` reads the real `config/config.yaml`. The test config sets `trading_start` to 09:00, but the real `risk.trading_start` still reaches the pipeline. Any future edit to `config.yaml` can therefore break the golden again. I did not touch this (out of scope), but you may want a follow-up to isolate the test from the real config.

Out-of-scope item of `to_develop/completed/2026-10-17_ISS-10_regenerate-pipeline-golden.md`. Isolating it changes the golden output again → needs its own re-baseline in the same commit.
