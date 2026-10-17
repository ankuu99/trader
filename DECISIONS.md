# Decisions

ADR-lite log, newest at the bottom. Superseded rows are struck through (~~…~~) with a pointer to the replacement — never deleted.
Decisions before 2026-10-16 live in CLAUDE.md ("Known design decisions", falsification notes) and `reviews/`.

| Date | Decision |
|---|---|
| 2026-10-16 | Pre-order risk rejects clear the strategy entry guard (`Strategy.on_pre_order_reject`), backtest + live — d9e7bc7, release-20261017. Pre-fix portfolio A/Bs are suspect (TD-011). |
| 2026-10-17 | Enable scale-in (50 % of previous lot, 2 tiers, 1-day spacing, 10 % pool) together with the loss re-entry block (3 sessions); countdown persisted across the daily reboot — 15d2fca, release-20261017b. Evidence: `reviews/scalein_lossblock_2020_horizon_20261017.md`. |
| 2026-10-17 | Live scale-in pool is never reserved out of the base: funded only by account equity above the config-file ₹6L, capped at 10 % × base — 15d2fca. Open question on profits vs pool: ISS-04. |
| 2026-10-17 | Adopt the tracking & agent-handoff system (DECISIONS / ISSUES / TODO / to_develop, spec-first implementer loop). `todo.md` migrated verbatim into TD-001…TD-007 (case-insensitive FS: `todo.md` and `TODO.md` cannot coexist). Existing docs keep their names; new design docs are numbered `docs/NN_…`. |
| 2026-10-17 | Review findings 2026-10-17: fix ISS-01 (live cash from margins `net`) and ISS-04 (cumulative_pnl double count); ISS-02 / ISS-03 to be discussed; ISS-05…ISS-09 noted for later. |
| 2026-10-17 | Add-on price rule ("add only below entry / previous buy") FALSIFIED (−₹110–137k 2020→2026, DD not improved) — not built. `reviews/addon_price_rule_20261017.md`, TD-008. |
