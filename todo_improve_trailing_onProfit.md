# Decouple the trailing "floor" from the trailing "arm" threshold

## Context

The LRExtrema trailing-stop has two independent checks in `ExtremaExitPolicy.tick_exit`
(`trader/policy/extrema_exit.py:356-370`):

1. **Peak-drawdown trail**: `drawdown_from_peak <= -trail_pct` → exit.
2. **Trailing floor**: once `trailing_active` (armed when `pct >= profit_pct`), if
   `pct < profit_pct` on a *later* tick → exit immediately.

The floor is hard-wired to the **same value that arms trailing** (`profit_pct`). So the
instant price ticks back through the arming line — even by a paisa, even one tick later —
it exits, regardless of how wide `trail_pct` is set. This is tighter than, and independent
of, the peak-drawdown check, and it is **not loosened** by either `trail_conf_enabled` or
`trail_regime_enabled` (both only touch the peak-drawdown distance via
`_effective_trail_pct`, never `_floor_pct`).

We diagnosed this live on **NSE:CHENNPETRO, 2026-07-13** (`profit_pct=10`, `trail_pct=4`):
price armed trailing right at 1199.55 (10% gain), ticked back to 1198.40 (9.895%) one
instant later, and floor-exited — then ran to 13%+ minutes later. The user reports this
whipsaw pattern recurring across multiple stocks/dates and wants the mechanism loosened.

Notably, **pattern-top trailing already solved this for itself** — its floor uses
`sell_min_pct` (independent of its own arm condition), with an off-switch
(`pattern_top_floor_enabled`, added in `59c5b5a` specifically because "premature exits
when the stock dips briefly after the peak"). Normal trailing never got the equivalent
decoupling. This plan gives it one, via a new `trail_floor_pct` knob, sibling to
`profit_pct`/`trail_pct`, defaulting to `profit_pct` (byte-identical to today) so nothing
in live/backtest changes until a stock's `per_stock_params` explicitly sets a lower value.

**Out of scope**: the backtest engine only probes tick-level exits at candle high and
close (never the low) — `trader/backtest/engine.py:649-680` — so it under-counts floor
whipsaws vs. live. That asymmetry is a separate, larger fix and is deferred; validation
here leans on unit tests (exact) + live/paper monitoring (directional), not backtest counts.

## Design

New YAML knob, plain sibling scalar (not a toggle block):

```yaml
strategies:
  lr_extrema:
    exits:
      trailing:
        profit_pct: 10   # arms trailing
        trail_pct: 4     # peak-drawdown distance (unchanged)
        floor_pct: 6     # NEW, optional — exit floor once armed; defaults to profit_pct
```

With `floor_pct=6`: trailing arms at 10% gain as before, but a pullback only floor-exits
once gain falls back to 6% — between 6% and 10% only the peak-drawdown `trail_pct` check
can fire. Whichever of the two (peak-drawdown or floor) trips first still wins, same as today.

## Implementation

**1. `trader/core/config.py`**
- `flatten_strategy_params` (~line 63-68): add one line alongside the existing
  `trailing.profit_pct` / `trailing.trail_pct` sibling resolution:
  ```python
  _set(p, "trail_floor_pct", trailing, "floor_pct")
  ```
  Same `_set` helper already used for every other plain scalar in this block — no new
  pattern needed (this is not a boolean toggle like `confidence_sizing`/`regime_widening`,
  so it doesn't need the "presence enables" treatment).
- `TF_SENSITIVE_PARAMS` (line 19-23): add `"trail_floor_pct"` next to `"trail_pct"`,
  `"profit_pct"` — it's timeframe-sensitive the same way and must be overridden per-stock
  on aggregated (4hour/day) timeframes.

**2. `trader/policy/extrema_exit.py`**
- `__init__`, right after `self._profit_pct = params.get("profit_pct", 3.0)` (line 37):
  ```python
  # Independent floor for normal (non-pattern-top) trailing. Defaults to profit_pct
  # (legacy: the arm threshold doubles as the exit floor). Set lower to create a
  # buffer zone — trailing arms at profit_pct but only floor-exits once price falls
  # back to trail_floor_pct; between the two, only the peak-drawdown trail_pct
  # check applies.
  self._floor_pct_normal: float = float(params.get("trail_floor_pct", self._profit_pct))
  ```
- Add a one-time guard: if `self._floor_pct_normal > self._profit_pct`, `logger.warning`
  that the floor is tighter than legacy and likely a misconfiguration (no clamping —
  just surfaced loudly).
- `tick_exit` floor branch (line 365-370): replace `self._profit_pct` with
  `self._floor_pct_normal` in the `_floor_pct = ... else self._profit_pct` line. The
  `pattern_top_trailing` branch (`_sell_min_pct`, gated by `pattern_top_floor_enabled`)
  is untouched — confirmed by tracing lines 264-297 that pattern-top trailing never
  falls through to this branch once `pos.pattern_top_trailing` is set.

**3. `scripts/calibrate.py`**
- `PARAM_GRID` (line 36-53): add
  ```python
  "trail_floor_pct": [5, 7, 10, 15, 20],
  ```
  `_KEYS` and the `--params` CLI choices derive from this automatically — no other
  change needed there.
- **Gotcha to document in a comment above the new row**: the grid can't express "unset →
  mirrors profit_pct." If `trail_floor_pct` is omitted from `--params`, it gets fixed at
  the grid's first entry (5), *not* at whatever `profit_pct` is. Always pass
  `--params profit_pct trail_pct trail_floor_pct ...` together when calibrating this.

**4. Tests**
- `tests/test_exit_policy_toggles.py` (pattern: `test_flatten_resolves_regime_widening`):
  - `test_flatten_resolves_trail_floor_pct` — `floor_pct: 6` in YAML → `trail_floor_pct == 6`.
  - `test_trail_floor_pct_default_preserves_legacy` — no `floor_pct` set →
    `pol._floor_pct_normal == pol._profit_pct`.
- `tests/test_exit_reasons.py` (pattern: `test_trailing_stop_exit_tagged_trailing`):
  - `test_trailing_floor_buffer_zone_does_not_exit_above_floor` — `profit_pct=10,
    trail_floor_pct=6, trail_pct=4`, `entry=100, peak=110`, tick at `109.9` (9.9% gain,
    within trail_pct of peak) → `tick_exit` returns `None`.
  - `test_trailing_floor_exits_at_floor_pct` — same setup, tick at `105.9` (5.9% gain,
    still within `trail_pct` of the peak so the drawdown check doesn't fire first) →
    exit fires with `exit_reason == "TRAILING"`.
  - This reproduces the CHENNPETRO shape (`profit_pct=10, trail_pct=4`) exactly.

**5. Validation**
- Regression parity: run `scripts/backtest_rolling.py` across the full watchlist
  before and after the code change (no YAML edits yet) — trade counts/`return_pct` per
  stock must be identical, proving the change is inert until opted in.
- CHENNPETRO-specific search:
  `python scripts/calibrate.py --from 2024-01-01 --params profit_pct trail_pct trail_floor_pct stop_pct`
  — compare a `trail_floor_pct` a few points below `profit_pct` against the legacy
  (`floor_pct == profit_pct`) baseline for trade count / avg P&L per trade.
- This plan does **not** apply any `per_stock_params` change (CHENNPETRO or otherwise) —
  that's a follow-up decision after reviewing calibrate/backtest output, done separately
  once you've seen numbers.

**6. `CLAUDE.md`**
- LRExtremaStrategy config param table: add a `floor_pct` row (→ `trail_floor_pct`,
  default unset/= `profit_pct`, decouples the exit-floor from the arm threshold), and a
  footnote on the existing `profit_pct` row noting it doubles as the legacy floor.
- "Exit conditions" trailing-stop-exit bullet: add the floor's OR-condition explicitly.
- Calibration section: add `trail_floor_pct` to the documented `--params` choices/example.

## Verification
- `pytest tests/test_exit_policy_toggles.py tests/test_exit_reasons.py -k floor` — new
  tests pass; full suite still green (no regressions to existing trailing/toggle tests).
- `python scripts/backtest_rolling.py --from 2024-01-01 --to 2025-12-31` before/after the
  code change, diffed — must be identical (no YAML touched yet).
- `python scripts/calibrate.py --from 2024-01-01 --params profit_pct trail_pct trail_floor_pct stop_pct`
  scoped to CHENNPETRO — inspect whether a buffered floor improves trade outcomes before
  ever touching `config/config.yaml`.
