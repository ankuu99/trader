# ISS-14: Backtest trailing/breakeven exits ignore the candle low

Source: found 2026-10-18 while inventorying detection work on other branches (`reviews/extrema_model_research_inventory_20261018.md`). Reproduced verbatim; dated addenda below. Never delete.

---

`trader/backtest/engine.py:661` simulates ticks for `strategy.on_tick` as `[candle["high"], candle["close"]]`
(+ an EOD tick). `ExtremaExitPolicy.tick_exit` (`trader/policy/extrema_exit.py:378`) evaluates the trailing stop,
the trailing floor (`pct < profit_pct` / `sell_min_pct`) and the breakeven stop against `last_price` only. The
candle **low** is used only for the hard SL (`engine.py:611`).

Consequence: a 15m candle whose low pierces the trail / floor / breakeven level set before that candle, but which
closes back above it, does not exit in backtest. Live checks every Kite tick (~1 s) and would exit at the floor.
The backtest therefore holds positions live would have sold, so trailing-exit results (and every exit A/B run so
far) carry an unquantified optimism.

`origin/handle_trailing` (2026-06-01/02, not merged) added an intrabar check: if the candle low breaks the floor
derived from the peak *before* this candle, fill at the floor (gap-adjusted to the open).

Open questions for the fix guide: order within the candle (low before high is unknowable — use the pre-candle
peak only, as the branch did); gap fills (`min(floor, open)`); whether the same applies to the trailing floor and
breakeven; size of the effect on the baseline (re-run 2025-01 → today before/after).
