# Backtest: tick exits must see the candle low
Written: 2026-10-18 · Tag: ISS-14 · Status: OPEN

## Source

> `trader/backtest/engine.py:661` simulates ticks for `strategy.on_tick` as `[candle["high"], candle["close"]]`
> (+ an EOD tick). `ExtremaExitPolicy.tick_exit` (`trader/policy/extrema_exit.py:378`) evaluates the trailing stop,
> the trailing floor (`pct < profit_pct` / `sell_min_pct`) and the breakeven stop against `last_price` only. The
> candle **low** is used only for the hard SL (`engine.py:611`).
>
> Consequence: a 15m candle whose low pierces the trail / floor / breakeven level set before that candle, but which
> closes back above it, does not exit in backtest. Live checks every Kite tick (~1 s) and would exit at the floor.

— `ISSUES/ISS-14-backtest-trailing-ignores-candle-low/DETAIL.md`, as of 2026-10-18. Owner approved the fix 2026-10-18.

## Intent

Before the existing high/close simulated ticks, the engine checks whether the candle's **low** reached the highest
tick-exit level that was armed **before this candle** (trailing stop, trailing floor, breakeven floor). If so the
position exits at that level, gap-adjusted to the open (`min(level, open)`), and the high/close ticks are skipped.

Design decisions (fixed — do not change):
- **Pre-candle state only.** The level is computed from the strategy state as it stands before this candle's ticks.
  A trail armed or a peak raised by *this* candle's high never triggers on *this* candle's low (intrabar order is
  unknowable; we assume high-before-low only for things already armed). This is the conservative choice.
- **The hard stop stays where it is** — the engine's own `pos["sl"]` low-check (engine.py ~611) runs first and is
  untouched. The new level excludes the stop-loss branch of `tick_exit`.
- **Fill = `min(level, candle["open"])`; reason = the reason of the level that fired** (the highest level is the
  first one price meets on the way down).
- Live code is unaffected: live already sees every tick. The new strategy method is pure (reads state, mutates nothing)
  and is only called by the engine.
- Strategies without the method are unaffected (engine uses `getattr(..., None)`).
- The EOD force-close tick and pattern-top / candle-speed exits are unchanged.

This deliberately changes backtest output (authorised). It must NOT change live behaviour, `tick_exit` semantics,
or any non-backtest path.

## Implementation steps

1. **`trader/policy/extrema_exit.py`** — add a pure method to `ExtremaExitPolicy`, directly above `tick_exit`:

   ```python
   def tick_exit_level(self, strat) -> "tuple[float, str] | None":
       """Highest price at which tick_exit would fire on the CURRENT (pre-candle) state,
       excluding the hard stop (the backtest engine owns that via its own low check).
       Returns (level, reason_code) or None. Pure — mutates nothing. Used by the backtest
       engine to test the candle low (ISS-14); live sees every tick and never calls it."""
   ```
   Logic, mirroring `tick_exit` exactly (same attributes, same floors):
   - `pos = strat._pos`; return None if `pos.entry_price is None`.
   - Collect candidates `(level, reason)`:
     - breakeven: if `self._breakeven_stop_enabled and pos.breakeven_active` →
       `(pos.entry_price * (1 + self._breakeven_buffer_pct / 100), "BREAKEVEN")`.
     - trailing stop: if `pos.trailing_active and pos.peak_close is not None` →
       `(pos.peak_close * (1 - self._effective_trail_pct(strat) / 100), "TRAILING")`.
     - trailing floor: if `pos.trailing_active` and the same `_use_floor` condition as `tick_exit`
       (`_pt_trail = pos.pattern_top_trailing or pos.guard_trailing`; `_use_floor = (not _pt_trail) or self._pattern_top_floor_enabled`;
       `_floor_pct = self._sell_min_pct if _pt_trail else self._profit_pct`) →
       `(pos.entry_price * (1 + _floor_pct / 100), "TRAILING")`.
   - Return the candidate with the highest level, or None if there are none.
   - Note `_effective_trail_pct` reads cached `_regime_uptrend` / `_last_p_max`; that is the pre-candle value, which is
     what we want. Do not call anything that mutates state.

2. **`trader/strategies/base.py`** — add a default method to `Strategy`:
   ```python
   def tick_exit_level(self) -> "tuple[float, str] | None":
       """Backtest-only hook (ISS-14): the highest armed tick-exit price, or None."""
       return None
   ```

3. **`trader/strategies/lr_extrema.py`** — override next to `on_tick`:
   ```python
   def tick_exit_level(self):
       if self.is_flat() or self._pos.entry_price is None:
           return None
       return self._exit_policy.tick_exit_level(self)
   ```

4. **`trader/backtest/engine.py`** — in the tick-simulation block (currently ~line 653, the
   `if symbol in open_positions and _in_window and current_ts[0] != open_positions[symbol]["entry_date"]:` guard),
   **before** iterating `_ticks`:
   - `_lvl_fn = getattr(strategy, "tick_exit_level", None)`; `_lvl = _lvl_fn() if _lvl_fn else None`.
   - If `_lvl is not None and candle["low"] <= _lvl[0]`:
     - Call `strategy.on_tick({"last_price": candle["low"], "instrument_token": candle.get("instrument_token"), "timestamp": candle["timestamp"]})`.
       Feeding the low (not the level) makes the strategy's own conditions fire robustly (no float-equality edge) and
       lets it run its normal snapshot/reset path.
     - If it returns a signal: exit exactly like the existing tick-exit branch (pop position, `_consume_lots`,
       `risk.close_position`, `strategy.on_order_update(... COMPLETE ...)`) **but** with
       `exit_price = min(_lvl[0], candle["open"])` and `tick_reason = _lvl[1]`. Factor the shared exit code into a
       small local helper used by both branches rather than duplicating it.
     - Then skip the high/close/EOD ticks for this candle.
     - If it returns None (should not happen), fall through to the normal ticks unchanged.
   - Update the block comment to describe the low check (cite ISS-14).

5. **`trader/backtest/CLAUDE.md`** — add one bullet to the engine behaviours describing the pre-candle-level low check,
   fill `min(level, open)`, and that the hard SL check is unchanged.

## Tests required

New file `tests/test_backtest_trailing_low.py` (drive the engine the way `tests/test_partial_exit_flow.py` /
`tests/test_scale_in.py` do — reuse their fixture/helper style; build a strategy whose position state you set directly
if that is how those tests do it, otherwise drive it with a synthetic candle series):
1. `test_policy_level_pure` — `tick_exit_level` returns the max of the armed levels and leaves every `PositionState`
   field unchanged (compare `dataclasses.asdict` before/after).
2. `test_policy_level_none_when_unarmed` — trailing not active, breakeven off → None.
3. `test_low_pierce_exits_at_level` — trailing active, peak P, trail 2 %: a candle with open/high/close above
   `P×0.98` and low below it exits at `P×0.98`, reason `TRAILING`.
4. `test_gap_through_level_fills_at_open` — open already below the level → fill at open.
5. `test_level_armed_by_same_candle_does_not_fire` — trailing NOT active before the candle; the candle's high arms it
   and the low is below the would-be trail → no exit on that candle via the low check.
6. `test_breakeven_level_low_pierce` — breakeven enabled + armed; low below the BE floor → exit at floor, reason `BREAKEVEN`.
7. `test_strategy_without_hook_unchanged` — a strategy lacking `tick_exit_level` (e.g. `MeanReversion` or a stub)
   runs through the engine exactly as before.

Suites that must stay green: the whole suite. **Expected:** any test that pins exact backtest trades through
`run_backtest` with trailing exits may change. If one does, STOP and report which test and the diff — do not edit
expected values or goldens. (`test_parity_golden` replays Strategy→Risk→Orders without the engine and should not change.)

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] 7 new tests pass
- [ ] no trader.backtest import in live/UI
- [ ] `tick_exit` itself unchanged (diff shows no edits inside it)
- [ ] live paths (`main.py`, `trader/orders`, `trader/risk`, `trader/data/live.py`) untouched
- [ ] backtest output changes only via the new low check (main session re-runs the baseline before/after)

## Completion record
