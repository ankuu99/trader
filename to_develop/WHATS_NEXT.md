# What's next (suggested pickup order — owner decides)

All of the 2026-10-17 review fixes the owner approved are live (release-20261017d): ISS-01, ISS-02/TD-001, ISS-03, ISS-04, ISS-10.

1. **Field checks on the first live session (Mon 2026-10-19):** ISS-01 — after a buy, the "Kite margins |" line shows `net`
   dropping by the buy; TD-001 — any `Order skipped — insufficient_cash` shows as a rejected signal, not a broker reject/Telegram.
2. **TD-013** — owner funds the pool: equity ₹5.79L; add-ons start above ₹6L (+ realised P&L); full ₹60k pool at ₹6.6L.
3. **TD-009** dated re-checks: AJANTPHARM ~10-21, CEATLTD after 10-22, RBLBANK ~10-26.
4. **TD-015** — released 2026-10-17 (release-20261017e). Positions bought before it (all 12 current) have parent_notional 0 → remainder-based sizing; only MAYURUNIQ is actually affected.
5. **TD-014** — golden harness reads the live config.yaml.
6. **Trough/peak model campaign (TD-018)** — round 1 DONE 2026-10-18: no detection arm beats production (0/12 on Stage A and on the full Stage-B
   backtest; the edge is the entry signal, coin-flip control EXP-20/22); the only
   robust signal is market timing (prior-day India VIX), which did not convert to P&L robustly. Read
   `reviews/extrema_campaign/CAMPAIGN_ROUND1_20261018.md`. Next options: TD-020 (news flag — find PIT event data),
   TD-019 (size_weight order) before any sizing idea. **TD-021 Model Lab** (docs/03) — L0 + L1 DONE 2026-10-18 on `exp/model-lab`
   (worktree `../trader-2-wt/model-lab`). Scoring is on the model's own terms (docs/03 §6). Next: finish the 15m PIT-universe fetch
   (`python -m research.model_lab.fetch intraday`, after `daily`), then L2 — pre-register arms in `reviews/model_lab/LEDGER.md` and run them. ISS-14 fixed — new baseline FULL ₹439.2k / Calmar 6.18.
7. Noted for later: ISS-05…ISS-09, ISS-11, ISS-12, ISS-13, ISS-15 (one-class training crash, latent) (non-funds broker rejects still retry by design); TD-005/006/007/010/011/012.
