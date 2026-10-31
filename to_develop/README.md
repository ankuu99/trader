# to_develop — spec-first build loop

1. **Spec** — main session writes `YYYY-MM-DD_TAG_slug.md` (TAG = ISS-NN · TD-NNN · DOC-NN · DEC), self-contained, opening with a `## Source` block quoting the tracker entry verbatim.
2. **Build** — implementer subagent (`.claude/agents/trader-implementer.md`) follows the guide exactly; stops and reports on ambiguity or hard-rule conflict.
3. **Validate** — main session runs the full test suite and reads the diff against the acceptance checklist; never trusts the report alone.
4. **Archive** — append the Completion record, `git mv` the guide to `completed/` (the move is the sign-off), flip the ISS/TD status + marker + index row in the same commit. On fail: dated addendum in the guide, repeat.

Anything in this folder (not `completed/`) is open work.

## Template

```
# <Title>
Written: YYYY-MM-DD · Tag: <TAG> · Status: OPEN
## Source        > verbatim quote — <file>, as of <date>. Related: <ids>
## Intent        what changes, why, and what it must NOT change
## Implementation steps   numbered, file-by-file, exact APIs/signatures
## Tests required         new tests (name the suite) + suites that stay green
## Acceptance checklist   - [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30) · - [ ] new behaviour tested · - [ ] no trader.backtest import in live/UI · - [ ] backtest parity unchanged unless the guide says so · - [ ] <guide-specific>
## Completion record      (appended at archive) Completed · Commit · Deviations · Notes
```

## Dispatching the implementer

A new `.claude/agents/*.md` type is only registered when a Claude Code session starts. Until then (or as a fallback)
dispatch a `general-purpose` agent with `model: sonnet` and the prompt "read `.claude/agents/trader-implementer.md`
and follow it; implement `<guide path>`". In later sessions use `subagent_type: trader-implementer`.
