# TD-005: Pre-15:25 cutoff for candle-close exits (CAS)

Source: `todo.md`, as of 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

  **Still open (CAS root cause):** consider a pre-15:25 cutoff for candle-close
  exits (mirror `trailing.force_close_time`) so last-candle exits execute next
  morning deliberately instead of dying in the 15:30–15:35 Closing Auction Session;
  with the restore fix they now retry next candle, but the first attempt still
  burns an order and a day of latency. Backtest has no CAS model (fills last-candle
  exits live cannot) — divergence remains.
