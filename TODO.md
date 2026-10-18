# TODO

Open points under `TODO/TD-NNN-<slug>/` (SUMMARY · DETAIL verbatim · DONE|PENDING marker). Open list: `ls TODO/*/PENDING`. IDs are permanent and never reused. Replaces the old free-form todo.md (migrated verbatim 2026-10-17, see TD-001…TD-007).

## Capital / execution

| ID | Status | Point |
|---|---|---|
| [TD-001](TODO/TD-001-pre-order-real-margin-check/DETAIL.md) | DONE 2026-10-17 (release-20261017d) | Pre-order real-margin check before live ENTRY (clamp qty to Kite available cash) |

## Trailing stop

| ID | Status | Point |
|---|---|---|
| [TD-002](TODO/TD-002-persist-peak-close/DETAIL.md) | DONE (pre-2026-10) | Persist `_peak_close` across restarts |
| [TD-003](TODO/TD-003-persist-exit-flags/DETAIL.md) | DONE 2026-10-14 | Persist trailing_active / pattern_top_trailing / partial_taken / breakeven_active |
| [TD-004](TODO/TD-004-exit-reject-restore/DETAIL.md) | DONE 2026-08-18 | EXIT-rejection restore covers clocks + trail state |

## Trailing stop / CAS

| ID | Status | Point |
|---|---|---|
| [TD-005](TODO/TD-005-cas-candle-close-exit-cutoff/DETAIL.md) | PENDING | Pre-15:25 cutoff for candle-close exits (CAS) |

## Live feed

| ID | Status | Point |
|---|---|---|
| [TD-006](TODO/TD-006-intraday-feed-watchdog/DETAIL.md) | PENDING | Intraday feed watchdog — reconnect mid-session when ticks go stale |

## Infra

| ID | Status | Point |
|---|---|---|
| [TD-007](TODO/TD-007-infra-cost-followups/DETAIL.md) | PENDING | Infra cost follow-ups (Phase 1 done; scoped IAM user, Phase 2 t4g, skip NSE holidays) |

## Scale-in research

| ID | Status | Point |
|---|---|---|
| [TD-008](TODO/TD-008-addon-price-rule-test/DETAIL.md) | DONE 2026-10-17 (falsified) | Test: add-on only when price is below the original / previous buy |

## Watchlist

| ID | Status | Point |
|---|---|---|
| [TD-009](TODO/TD-009-candidate-dated-rechecks/DETAIL.md) | PENDING | Dated re-checks of 2026-10-15 discovery candidates |
| [TD-010](TODO/TD-010-watchlist-add-calibrated-names/DETAIL.md) | PENDING | Decide whether to add AJANTPHARM / ABCAPITAL / TATASTEEL to the traded watchlist |
| [TD-012](TODO/TD-012-thangamayl-review/DETAIL.md) | PENDING | THANGAMAYL review |

## Research hygiene

| ID | Status | Point |
|---|---|---|
| [TD-011](TODO/TD-011-revalidate-prefix-portfolio-abs/DETAIL.md) | PENDING | Re-validate portfolio A/Bs run before the reject-freeze fix (2026-10-16) |

## Owner action

| ID | Status | Point |
|---|---|---|
| [TD-013](TODO/TD-013-fund-scalein-pool/DETAIL.md) | PENDING | Fund the scale-in pool (account equity above the ₹6L base) |

## Tests

| ID | Status | Point |
|---|---|---|
| [TD-014](TODO/TD-014-isolate-golden-from-live-config/DETAIL.md) | PENDING | Isolate the parity golden harness from the live config.yaml |

## Scale-in / persistence

| ID | Status | Point |
|---|---|---|
| [TD-015](TODO/TD-015-parent-notional-after-scaleout-reboot/DETAIL.md) | DONE 2026-10-17 (release-20261017e) | Persist original parent notional (add-on sizing after scale-out + reboot) |

## Dashboard

| ID | Status | Point |
|---|---|---|
| [TD-016](TODO/TD-016-stock-names-link-to-drilldown/DETAIL.md) | DONE 2026-10-17 (release-20261017f) | Every stock name on the dashboard links to /stock/<sym> |
| [TD-017](TODO/TD-017-stock-page-date-range/DETAIL.md) | DONE 2026-10-18 (release-20261018a) | Date-range filter on the /stock and /chart pages |

## Detection research

| ID | Status | Point |
|---|---|---|
| [TD-018](TODO/TD-018-extrema-model-campaign/DETAIL.md) | PENDING — round 1 done 2026-10-18 (no arm passes; TD-020 open) | Trough/peak model evaluation campaign — docs/01, ledger, worktree arms |
| [TD-019](TODO/TD-019-size-weight-before-capital-cap/DETAIL.md) | PENDING (discovered 2026-10-18) | `size_weight` applied before the per-stock capital cap — downsizing inert when the cap binds |
| [TD-020](TODO/TD-020-news-no-news-decline-flag/DETAIL.md) | PENDING (blocked on PIT event data) | News/no-news decline flag (EXP-15, Chan 2003) — the one untested arm with new which-dip information |
