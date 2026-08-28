# TODO

## Capital / execution layer (from 2026-08-16 insufficient-funds forensics)

62 live broker rejections (49 in July) were "Insufficient funds" — the model called
the KPL/MAYURUNIQ dips correctly (p_min 0.87–0.98) but the orders died at Zerodha.
The slow-TF slot cap (`risk.max_slow_tf_positions`) was built for the
capital-turnover side but **FALSIFIED by A/B backtest** (2025-01→2026-08:
baseline ₹294k/Calmar 3.09 → cap=6 ₹242k → cap=4 ₹194k; DD not improved) —
slow-TF trades are the biggest winners, capping them churns capital into marginal
15m entries. It stays in code as a config-gated defensive option, OFF. That makes
these ledger/execution fixes the ONLY live path to capturing the rejected dips:

- **Fix cumulative_pnl double-count in `capital_available`** — at startup
  `effective_capital = min(config_cap, kite_cash + deployed)` (main.py:440-443) is
  account *equity*, which already contains all realised P&L; `capital_available`
  (risk/manager.py:111) then adds `_cumulative_pnl` (₹21k) on top again, so the bot
  permanently believes it has ~₹21k more than the account holds and always attempts
  one order more than can be funded. Fix: when the equity cap binds, seed the ledger
  so `total_capital + cumulative_pnl` equals real equity (e.g. set effective capital
  to `equity − cumulative_pnl`), or stop adding pnl when capital was set from equity.

- **Pre-order real-margin check** — before placing a live ENTRY, fetch
  `kite.margins("equity")` available cash and clamp quantity to what the account can
  actually fund (skip if dust). Kills the insufficient-funds rejection class at the
  source and serialises same-candle signal races honestly (2026-08-14: CHENNPETRO
  filled at 15:15:02, MAYURUNIQ rejected at 15:15:03 with ₹1,430 available — the
  ATHERENERG sale proceeds hadn't settled into usable margin yet).

- **Freeze entry guard on broker insufficient-funds rejects** — an exchange-REJECTED
  entry logs "clearing entry guard" and re-fires every candle (STYLAMIND July: dozens;
  KPL 2026-08-07: ×2). The reject→re-fire fix only froze the guard for PRE-order
  rejects; extend the same session-freeze to broker rejections (at minimum for
  insufficient-funds, where retrying without new cash is guaranteed futile).

## Trailing stop — known gaps

- ~~**Persist `_peak_close` across restarts**~~ — DONE. `main.py` writes
  `<instrument>.peak_close` / `.max_gain_pct` to the `state` table each candle and
  restores them on startup via `strat.seed_position_state()` (`main.py:402-407`,
  live block; `main.py:291-295`, paper block).

- **Persist `trailing_active` across restarts** — `peak_close` and `max_gain_pct`
  survive a restart, but `trailing_active` does not: `seed_position_state()` takes
  only those two, so `PositionState.trailing_active` comes back `False`. It re-arms
  on the first tick where `pct >= profit_pct` (`trader/policy/extrema_exit.py:320`),
  so the common case self-heals. **The gap:** a position that armed trailing at an
  earlier peak and has since pulled back *below* its `profit_pct` floor — while still
  above the trail level `peak × (1 - trail_pct/100)` — silently disarms on restart.
  Downside protection is lost until price re-crosses the floor, which it may never do.
  Widest for stocks with a high floor and loose trail (CHENNPETRO: `profit_pct: 10`,
  `trail_pct: 4` → a ~6pp dead band). `pattern_top_trailing` positions are worse off:
  they arm trailing from the pattern-top branch regardless of `profit_pct`
  (`extrema_exit.py:268`, `:293`), so nothing re-arms them at all after a restart.
  `partial_taken` has a sharper failure mode than a lost trail: it guards the
  pattern-top scale-out to once per position (`extrema_exit.py:266`), so a restart
  re-arms it and a second scale-out can fire on the same position.
  Fix: persist `trailing_active`, `pattern_top_trailing`, `partial_taken` and
  `breakeven_active` the same way as `peak_close` (`main.py:608`), and widen
  `seed_position_state()` (`lr_extrema.py:405`) to restore them. The
  `open_positions` table already has a `trailing_active` column, but it is UI-only —
  nothing reads it back into strategy state.

- ~~**EXIT-rejection restore is PARTIAL — clocks and trail state are lost**~~ —
  **FIXED 2026-08-18** (uncommitted). `PositionState.snapshot_and_reset()` captures
  every position-tracking field at FULL-exit emission (survives `reset()` like
  `fill_price`); all 8 full-exit call sites in `trader/policy/extrema_exit.py` use
  it; the REJECTED/CANCELLED+EXIT branch in `lr_extrema.on_order_update` restores
  the whole snapshot (one-shot; falls back to the old entry-price-only restore when
  no snapshot exists, e.g. restart between emission and rejection). COMPLETE exit
  fills and new ENTRY fills discard the snapshot. Happy path proven byte-identical
  (pipeline snapshot before/after diff — see golden note below). Tests:
  `tests/test_exit_reject_restore.py` (7). Original live evidence: TVSMOTOR
  2026-08-17 — hold-bars(200) exit fired on the 15:15 candle → order at 15:30:01 →
  Zerodha CAS rejection → `held_bars` 200→0 → timeout exit slipped ~8 sessions.

  **Still open (CAS root cause):** consider a pre-15:25 cutoff for candle-close
  exits (mirror `trailing.force_close_time`) so last-candle exits execute next
  morning deliberately instead of dying in the 15:30–15:35 Closing Auction Session;
  with the restore fix they now retry next candle, but the first attempt still
  burns an order and a day of latency. Backtest has no CAS model (fills last-candle
  exits live cannot) — divergence remains.

- **Golden parity `test_pipeline_golden` is STALE (pre-existing, NOT the restore
  fix)** — fails on the clean tree too, with numpy/sklearn matching the golden's
  pin (2.4.4/1.8.0); divergence traces to the stale-rearm commit f01f702 shipping
  without a golden regen. Regenerate with `REGEN_GOLDEN=1` in a dedicated reviewed
  commit per the test's own docstring.
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
