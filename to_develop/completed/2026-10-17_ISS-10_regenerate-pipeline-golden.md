# Attribute and regenerate the stale pipeline golden
Written: 2026-10-17 · Tag: ISS-10 · Status: DONE

## Source

> - **Golden parity `test_pipeline_golden` is STALE (pre-existing, NOT the restore
>   fix)** — fails on the clean tree too, with numpy/sklearn matching the golden's
>   pin (2.4.4/1.8.0); divergence traces to the stale-rearm commit f01f702 shipping
>   without a golden regen. Regenerate with `REGEN_GOLDEN=1` in a dedicated reviewed
>   commit per the test's own docstring.

— `ISSUES/ISS-10-golden-parity-test-stale/DETAIL.md` (migrated from todo.md), as of 2026-10-17.
Owner, 2026-10-17: "deploy another agent to fix the golden test. it is painful to watch it fail all the time."

## Intent

`tests/test_parity_golden.py::test_pipeline_golden` has failed on every clean HEAD since at least f01f702, so it
no longer protects anything and hides real regressions. Re-baseline `tests/fixtures/golden_pipeline.json` — but
only after proving that every difference comes from an **intended** behaviour change that shipped since the
golden was generated (3a277c5). numpy 2.4.4 / scikit-learn 1.8.0 already match the pin, so this is behaviour drift,
not library drift.

**This guide explicitly authorises regenerating `tests/fixtures/golden_pipeline.json`** once steps 1–4 succeed.
Must NOT change: `tests/fixtures/golden_features.json` (that test passes — leave it), the test file's assertions,
any production code, the owner's uncommitted work in the main working tree.

## Implementation steps

1. **Work in a clean temporary worktree at HEAD** — the main tree has the owner's uncommitted edits in
   `trader/policy/*`, `trader/features/*`, `trader/core/config.py`; the golden must never encode them:
   `git worktree add /Users/abhisheksingh/.claude/jobs/f7920f0f/tmp/golden_wt HEAD`
   and run everything below from there (use the main repo's interpreter, `python -m pytest`).
2. **Confirm the failure** there: `python -m pytest tests/test_parity_golden.py -q`. Expect only
   `test_pipeline_golden` to fail.
3. **Find which commits changed the output.** Use `git bisect` inside the worktree between `3a277c5` (good —
   golden generated there) and `HEAD` (bad), with
   `git bisect run python -m pytest tests/test_parity_golden.py::test_pipeline_golden -q -x`.
   If a commit in between cannot run the test (import error / missing fixture), `git bisect skip` it. Record the
   first bad commit. Then, because more than one later commit may have changed the output again, generate the
   golden at that first-bad commit into a scratch file (copy the worktree, `REGEN_GOLDEN=1` there, keep the
   resulting json OUTSIDE the repo, then `git checkout -- tests/fixtures`) and continue bisecting from that commit
   to HEAD against the scratch golden, repeating until HEAD matches. Result: an ordered list of commits that
   changed the pipeline output. `git bisect reset` when done.
4. **Attribute each commit.** For each one, `git show --stat <sha>` + read its message and state in one line what
   behaviour it intentionally changed (e.g. f01f702 stale re-arm; d9e7bc7 pre-order reject clears the entry
   guard; 15d2fca scale-in / loss block defaults). **Stop and report without regenerating** if any commit in the
   list does not, on its face, intend to change trading behaviour (pure refactor, UI, docs, tests) — that would
   be an unintended regression, which is exactly what this harness exists to catch.
5. **Summarise the old → new difference.** Before regenerating, load the old `golden_pipeline.json` and the new
   snapshot (scratch regen at HEAD) and report: trade count, total P&L (sum of trade pnl), signal count, first
   differing trade/signal (index, timestamp, fields). Put this summary in your report.
6. **Regenerate** in the temp worktree at HEAD: `REGEN_GOLDEN=1 python -m pytest tests/test_parity_golden.py -q`,
   then run the whole file without the env var three times — must pass every time (determinism).
7. **Copy only `tests/fixtures/golden_pipeline.json`** from the worktree into the main repo, then in the MAIN repo
   run `python -m pytest -q` (whole suite). If the golden test fails in the main tree only, the owner's uncommitted
   work changes default behaviour — do NOT adjust anything; report it.
8. Update the "Pinned at generation time" line in `tests/test_parity_golden.py` docstring only if the versions
   differ (they should not), and add one docstring line: `Regenerated 2026-10-17 at <HEAD sha> (ISS-10) — drift
   attributed to: <commit list>.`
9. Remove the worktree: `git worktree remove --force <path>`.

## Tests required
No new tests. `tests/test_parity_golden.py` (all three tests) green in both the clean worktree and the main tree;
whole suite green except ISS-11 (`test_render_page_health_strip`, only fails 09:15–15:30 IST).

## Acceptance checklist
- [ ] ordered list of output-changing commits, each attributed to an intended behaviour change
- [ ] old → new summary (trades, P&L, signals, first difference) in the report
- [ ] golden regenerated from a clean HEAD worktree, never from the main working tree
- [ ] `golden_features.json` unchanged; no production code changed
- [ ] parity file passes 3× in the worktree and once in the main tree; full suite green apart from ISS-11
- [ ] worktree removed; nothing committed

## Completion record
- **Completed:** 2026-10-17 — implementer (general-purpose, sonnet); validated by the main session (parity file 3/3 green in the main tree; diff = fixture + one docstring line; `git show f9a7f9f` confirms `risk.trading_start` 09:30 → 09:15; no stray worktree).
- **Commit:** see `git log -- to_develop/completed/2026-10-17_ISS-10_regenerate-pipeline-golden.md`.
- **Deviations:** the guide's hypothesis (f01f702 stale re-arm) was wrong. The ONLY output-changing commit is
  f9a7f9f "updated config for stocks" (2026-06-18): `config/config.yaml` `risk.trading_start` 09:30 → 09:15 — proven by
  reverting just that line (old golden passes 3/3). All 126 later commits (incl. f01f702, d9e7bc7, 15d2fca) match the
  f9a7f9f re-baseline. Bisect needed the scratch-golden method; one invalid overlapping scan was discarded and re-run.
- **Old → new (HAL fixture, 1550 candles):** trades 84 → 23, P&L +9,471 → −1,257, signals 495 → 154; first diff = trade 0
  exit 4245.2 → 4251.9.
- **Notes:** the harness reads the real `config/config.yaml` (the test's `trading_start: 09:00` does not shield
  `risk.trading_start`), so any config edit can break the golden again → TD-014.
