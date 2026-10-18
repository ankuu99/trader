# What's next (suggested pickup order — owner decides)

All of the 2026-10-17 review fixes the owner approved are live (release-20261017d): ISS-01, ISS-02/TD-001, ISS-03, ISS-04, ISS-10.

1. **Field checks on the first live session (Mon 2026-10-19):** ISS-01 — after a buy, the "Kite margins |" line shows `net`
   dropping by the buy; TD-001 — any `Order skipped — insufficient_cash` shows as a rejected signal, not a broker reject/Telegram.
2. **TD-013** — owner funds the pool: equity ₹5.79L; add-ons start above ₹6L (+ realised P&L); full ₹60k pool at ₹6.6L.
3. **TD-009** dated re-checks: AJANTPHARM ~10-21, CEATLTD after 10-22, RBLBANK ~10-26.
4. **TD-015** — released 2026-10-17 (release-20261017e). Positions bought before it (all 12 current) have parent_notional 0 → remainder-based sizing; only MAYURUNIQ is actually affected.
5. **TD-014** — golden harness reads the live config.yaml.
6. **Model Lab (TD-021) + strategy sleeve (TD-023)** on `exp/model-lab` (worktree `../trader-2-wt/model-lab`), state 2026-10-19:
   ledgers `reviews/model_lab/LEDGER.md` (models) and `STRATEGY_LEDGER.md` (₹ sims). A01 (day deep lows) is the one clean model
   win; no lab strategy beats the full production system on 2025-01→2026-10 (SC6), and random picks on the watchlist make
   ₹2.8–4.8L there (hindsight selection). **PB-LONG:** production setup 2015→2026 lost 2018/19/20 (−48 % peak-to-trough,
   liquid names −₹2.05L 2015–20) — `reviews/model_lab/PB_LONG_prod_2015_20261019.md`. In progress: TD-022 L0c survivorship-free
   `dayn` source (rework after a validation fail: NSE corporate-actions API factors); then ML-A01n/A11n + SN-1..3 (pre-registered).
   Owner decisions pending: TD-023 exclusion-list rules (incl. a traded-value floor); walk-forward exit selection. ISS-16 fixed.
7. Noted for later: ISS-05…ISS-09, ISS-11, ISS-12, ISS-13, ISS-15 (one-class training crash, latent) (non-funds broker rejects still retry by design); TD-005/006/007/010/011/012.
