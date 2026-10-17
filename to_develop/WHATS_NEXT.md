# What's next (suggested pickup order — owner decides)

1. **ISS-01** (live cash from margins `net`) — guide in `to_develop/`, implementer dispatched 2026-10-17; validate,
   archive, release. After the first live session with a buy, confirm in the "Kite margins |" log line that `net`
   dropped by the buy → flip to FIXED.
2. **ISS-04** (cumulative_pnl double count) — owner approved; needs one answer before the guide: do realised
   profits grow the base sleeve (matches the backtest) or fund the scale-in pool (owner's ₹6L-floor rule)?
3. **ISS-02 + ISS-13 + TD-001** — rejected add-on / entry re-fire. Owner: record the attempt, don't block while the
   model is bullish. Candidate: pre-order real-margin check (TD-001) so unfunded orders are never sent.
4. **ISS-03** — pro-rata (memory, and the backtest's RiskManager) vs FIFO (DB) after a partial scale-out on an
   add-on position. Explained to owner 2026-10-17; awaiting choice.
5. **TD-013** — owner funds the pool (equity ≈ ₹5.79L after the ₹1L top-up; base ₹6L, full pool at ₹6.6L).
6. **TD-009** dated re-checks: AJANTPHARM ~10-21, CEATLTD after 10-22, RBLBANK ~10-26.
7. Noted for later: ISS-05…ISS-12, TD-005/006/007/010/011/012.
