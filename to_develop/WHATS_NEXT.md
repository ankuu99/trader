# What's next (suggested pickup order — owner decides)

1. **Release TD-001 + ISS-04** (built + validated 2026-10-17, unreleased). After release check the startup lines:
   `Effective capital set … cum_pnl=0 sleeve=600000` and `Kite margins | net=…`.
2. **Field checks on the first live session:** ISS-01 — `net` drops by a buy; TD-001 — any `Order skipped — insufficient_cash`
   line shows up as a rejected signal (not a broker reject / Telegram).
3. **ISS-03** — make the DB's partial scale-out accounting proportional like the in-memory ledger and the backtest. Explained to
   the owner 2026-10-17 (impact: loss-block arming, pool usage, realised P&L after reboot); awaiting go. Only reachable once
   the pool is funded (TD-013).
4. **TD-013** — owner funds the pool: equity ₹5.79L (2026-10-17); needs > ₹6L base + realised P&L; full pool at +₹60k.
5. **TD-009** dated re-checks: AJANTPHARM ~10-21, CEATLTD after 10-22, RBLBANK ~10-26.
6. **TD-014** — golden harness reads the live config.yaml.
7. Noted for later: ISS-05…ISS-09, ISS-11, ISS-12, ISS-13 (non-funds broker rejects still retry by design); TD-005/006/007/010/011/012.
