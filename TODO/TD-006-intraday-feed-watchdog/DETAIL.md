# TD-006: Intraday feed watchdog — reconnect mid-session when ticks go stale

Source: `todo.md`, as of 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

- **Intraday feed watchdog (follow-up to the 2026-08-28 dark-session fix)** — the
  self-healing reconnect only runs at 09:00 `pre_market()`. If the socket dies
  *during* the session (token invalidated mid-day, network drop that outlives
  kiteconnect's 50-attempt retry cap), nothing calls `feed.reconnect()` until the
  next morning. Obvious fix: have `main.py::heartbeat` (already scheduled, already
  calls `_check_token`) call `feed.reconnect()` when the market is open and the
  last tick is older than ~N minutes — the dashboard health strip already computes
  that staleness. Deliberately not done in the reconnect fix to keep main.py
  untouched.
  Same gap covers the dashboard "Reload token" button mid-session: it rebuilds the
  ticker (arming `_needs_reconnect`) but only 09:00 `pre_market()` calls
  `reconnect()`. Do NOT just add a second `feed.reconnect()` in `_reload_kite_token`
  — pre_market would then call it twice within seconds and the first connect is
  async (`callFromThread`), so `is_connected()` is still False on the second call
  and it double-connects. The watchdog is the right home for this too.
