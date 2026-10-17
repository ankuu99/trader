# TD-011: Re-validate portfolio A/Bs run before the reject-freeze fix (2026-10-16)

Source: `project_backtest_reject_freeze_bug` memory / `reviews/reject_freeze_rerun_20261016.md`. Reproduced verbatim; dated addenda below. Never delete.

---

Every capital-crowded backtest before d9e7bc7 is path-dependent noise — re-run before trusting it. Already re-run: capital scaling, scale-in, slow-TF cap, cooldown, discount, loss block. Candidates not yet re-run (unverified list — check reviews/ first): stale-runway ×2, stale re-arm, pattern-top trend guard, all-15m conversion, swing features, peak-based stop.
