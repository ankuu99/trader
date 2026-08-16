# TODO

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

- **Handle EXIT order rejection in `on_order_update`** — if Kite rejects a SELL/EXIT
  order (rare but possible), the strategy is left in a stuck state: `position=BUY`
  but `_entry_price=None`, so `on_tick` returns None and no further exits fire until
  `hold_bars` timeout. Fix: in `on_order_update`, add a `REJECTED` branch for
  `signal_type == SignalType.EXIT` that re-sets `_entry_price` to the last known
  entry price (stored separately) so `on_tick` can retry the exit on the next tick.