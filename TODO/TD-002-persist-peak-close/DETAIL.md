# TD-002: Persist `_peak_close` across restarts

Source: `todo.md`, as of 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

- ~~**Persist `_peak_close` across restarts**~~ — DONE. `main.py` writes
  `<instrument>.peak_close` / `.max_gain_pct` to the `state` table each candle and
  restores them on startup via `strat.seed_position_state()` (`main.py:402-407`,
  live block; `main.py:291-295`, paper block).
