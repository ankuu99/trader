# TODO

## Trailing stop — known gaps

- **Persist `_peak_close` across restarts** — on restart, `_peak_close` resets to
  the current tick price instead of the historical high-water mark. Trailing still
  works but uses a lower peak, giving a slightly looser exit. Fix: save `_peak_close`
  to the `open_positions` table in SQLite alongside `entry_price` and restore it in
  the paper and live reconciliation blocks in `main.py`.

- **Handle EXIT order rejection in `on_order_update`** — if Kite rejects a SELL/EXIT
  order (rare but possible), the strategy is left in a stuck state: `position=BUY`
  but `_entry_price=None`, so `on_tick` returns None and no further exits fire until
  `hold_bars` timeout. Fix: in `on_order_update`, add a `REJECTED` branch for
  `signal_type == SignalType.EXIT` that re-sets `_entry_price` to the last known
  entry price (stored separately) so `on_tick` can retry the exit on the next tick.