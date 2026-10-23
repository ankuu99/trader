# trader-2 — index

Automated long-only CNC swing-trading bot for NSE (Zerodha/Kite). Agent/project reference: **CLAUDE.md**.

## Trackers
- `DECISIONS.md` — dated decision log (ADR-lite).
- `ISSUES.md` → `ISSUES/ISS-NN-*/` — reported problems (`ls ISSUES/*/PENDING` = open).
- `TODO.md` → `TODO/TD-NNN-*/` — open points (`ls TODO/*/PENDING` = open).
- `to_develop/` — spec-first build guides (open work); `to_develop/completed/` — signed off;
  `to_develop/WHATS_NEXT.md` — suggested pickup order; `to_develop/README.md` — the loop + template.
- `.claude/agents/trader-implementer.md` — implementer subagent; `.claude/skills/` — repeatable procedures.

## Docs
- `docs/` — design docs (`Aggregated_Timeframes_Design.md`, `CORE_INFRASTRUCTURE.md`, FVM_*, Trendlyne_*).
  New design docs are numbered `docs/NN_<name>.md`.
- Root plans: `aws_plan.md`, `infra_cost_plan.md`, `exit_action_plan.md`, `meta_labeling_plan.md`,
  `shape_features_plan.md`, `avg_trend_paper_plan.md`, `todo_revamp.md` (rearchitecture plan),
  `todo_improve_trailing_onProfit.md`, `design.md`, `requirements.md`, `usage_instructions.md`.
- Learnings: `exit_mechanism_learnings.md`, `meta_labeling_learnings.md`, `neutral_class_learnings.md`.
- `reviews/` — dated analyses, A/B results, qualify/discovery reports, code reviews.
