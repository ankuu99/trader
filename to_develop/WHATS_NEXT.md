# What's next (suggested pickup order — owner decides)

All of the 2026-10-17 review fixes the owner approved are live (release-20261017d): ISS-01, ISS-02/TD-001, ISS-03, ISS-04, ISS-10.

1. **Field checks on the first live session (Mon 2026-10-19):** ISS-01 — after a buy, the "Kite margins |" line shows `net`
   dropping by the buy; TD-001 — any `Order skipped — insufficient_cash` shows as a rejected signal, not a broker reject/Telegram.
2. **TD-013** — owner funds the pool: equity ₹5.79L; add-ons start above ₹6L (+ realised P&L); full ₹60k pool at ₹6.6L.
3. **TD-009** dated re-checks: AJANTPHARM ~10-21, CEATLTD after 10-22, RBLBANK ~10-26.
4. **TD-015** — released 2026-10-17 (release-20261017e). Positions bought before it (all 12 current) have parent_notional 0 → remainder-based sizing; only MAYURUNIQ is actually affected.
5. **TD-014** — golden harness reads the live config.yaml.
6. **Model Lab (TD-021) + strategy sleeve (TD-023)** on `exp/model-lab` (worktree `../trader-2-wt/model-lab`), state 2026-10-19:
   ledgers `reviews/model_lab/LEDGER.md` / `STRATEGY_LEDGER.md`. **TD-022 `dayn` survivorship-free source DONE** (1,070 delisted
   names). On it: A01 still the best swing-low detector but its ₹ edge vs coins is gone; production P(min) as a ranker too; **A11
   ranker beats 11/11 coins (₹15.96L, DD 42 %)** — `SN_survivorship_free_20261019.md`. Production setup 2015→2026 lost 2018–20
   (PB-LONG). No lab strategy beats production on 2025–26 (SC6). Owner decisions pending: TD-023 exclusion-list rules (now the
   critical piece — docs/04 addendum 2026-10-19); then S1 = A11-ranked entries + exclusions on dayn, walk-forward.
7. Noted for later: ISS-05…ISS-09, ISS-11, ISS-12, ISS-13, ISS-15 (one-class training crash, latent) (non-funds broker rejects still retry by design); TD-005/006/007/010/011/012.
