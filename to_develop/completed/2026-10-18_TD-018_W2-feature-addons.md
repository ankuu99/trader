# W2 — Feature add-ons: bar shape, ATR distance, support/resistance, market context
Written: 2026-10-18 · Tag: TD-018 (arms EXP-05, EXP-06, EXP-07, EXP-08) · Status: OPEN · Worktree: `../trader-2-wt/features`, branch `exp/features`

## Source

> […] i want uou to start multiple eorktrees to evaluatd all these and see if we gather any peformance gains […]

— `TODO/TD-018-extrema-model-campaign/DETAIL.md`, as of 2026-10-18. Arms in `docs/01_Extrema_Model_Campaign.md`;
ledger rows B-03, B-04, B-05, B-12, R-15.

## Intent

Four independent, default-off feature add-ons on the scaffold in `trader/features/addons.py`. Each appends columns
after the base vector of whatever pipeline is configured (so positional gates are safe). Each is enabled by
`features.<name>.enabled: true`. Must NOT change: default pipelines, live paths, engine, config.yaml, aggregator.

**Registration convention (fixed):** each add-on lives in its own module `trader/features/addon_<name>.py`, defines a
`FeatureAddon` subclass with `name = "<name>"`, and registers itself at import time with `ADDONS["<name>"] = Cls`.
`trader/features/registry.py` gets one import line per module (`from trader.features import addon_<name>  # noqa: F401`)
placed directly after the existing `from trader.features.addons import ...` line, in this order:
bar_shape, atr_dist, sr, market.

All values must be finite floats; return the documented neutral value when history is short or an input is missing.

## Implementation steps

1. **`trader/features/addon_bar_shape.py` — `bar_shape`** (EXP-05: the reversal bar the model misses; ATHER review).
   Config: `vol_bars` (default 20). Names: `lower_wick`, `upper_wick`, `body`, `clv_x_vol`, `close_vs_prev_low`.
   For the last candle, `rng = high - low`:
   - `lower_wick = (min(open, close) - low) / rng`, `upper_wick = (high - max(open, close)) / rng`,
     `body = (close - open) / rng` (all 0.0 when rng == 0);
   - `clv = ((close - low) - (high - close)) / rng` (0.0 when rng == 0); `vr = volume / mean(volume over last vol_bars)`
     (1.0 when the mean is 0); `clv_x_vol = clv * min(vr, 5.0)`;
   - `close_vs_prev_low = (close - prev_low) / prev_low` using the previous candle's low (0.0 if no previous candle).
   `min_history = vol_bars`.

2. **`trader/features/addon_atr_dist.py` — `atr_dist`** (EXP-06; branch idea `ema20_dist`).
   Config: `ema_period` (20), `atr_period` (14). Names: `ema_dist_atr`, `atr_ratio`.
   `ema` = last value of `indicators.ema_series(closes[-5*ema_period:], ema_period)`;
   `atr = indicators.atr_at(candles, len(candles) - 1, atr_period)`;
   `ema_dist_atr = (close - ema) / atr` clipped to [-10, 10] (0.0 if atr == 0); `atr_ratio = atr / close`.
   `min_history = max(5 * ema_period, atr_period + 1)`.

3. **`trader/features/addon_sr.py` — `sr`** (EXP-08; `todo_sr_logic.md` on `origin/handle_trailing`, Phase 4 = features).
   Config: `lookback` (300), `pivot_order` (3), `tol_pct` (1.5), `min_touches` (2), `cap` (0.25).
   Names: `sup_dist`, `sup_touches`, `res_dist`, `res_touches`.
   - Window = the last `lookback` closes **excluding the current bar** (pivots must be confirmed by bars inside the
     window — `find_local_extrema` already excludes the final `pivot_order` bars of what it is given, so pass
     `closes[-lookback-1:-1]`).
   - Pivot prices = closes at minima ∪ maxima. Cluster: sort ascending; walk, starting a new cluster when a price is
     more than `tol_pct` % above the current cluster's mean; a level = cluster mean, touches = cluster size; keep levels
     with touches ≥ `min_touches`.
   - `sup` = highest level ≤ close; `res` = lowest level > close.
     `sup_dist = (close - sup) / close`, `res_dist = (res - close) / close`, each clipped to `[0, cap]`;
     missing level → dist = `cap`, touches = 0. Touch counts as floats.
   `min_history = lookback + 1`.

4. **`trader/features/addon_market.py` — `market`** (EXP-07; backtest-only context — live candles carry no
   `_nifty_close`/`_vix_close`, so live would see neutral zeros; that is acceptable for an experiment and must be
   stated in the module docstring).
   Config: `ret_bars` (20), `dd_bars` (50), `vix_bars` (20). Names: `rel_strength`, `nifty_dd`, `vix_level`, `vix_chg`.
   Read `c.get("_nifty_close")` / `c.get("_vix_close")` from the candles (the backtest engine injects them; aggregated
   bars inherit them from their last member). If the last candle lacks either value → all four 0.0.
   - `rel_strength = (close/close[-ret_bars-1] - 1) - (nifty/nifty[-ret_bars-1] - 1)` (0.0 if the lagged nifty is missing);
   - `nifty_dd = nifty / max(nifty over the last dd_bars candles that have it) - 1`;
   - `vix_level = vix / 20.0 - 1.0`; `vix_chg = vix / vix[-vix_bars-1] - 1` (0.0 if missing).
   `min_history = max(ret_bars, vix_bars) + 1`.

5. **Runner support** — `scripts/campaign/run_windows.py::_run_window` and `scripts/campaign/stage_a.py::score_run`
   currently pass `{s: 0 for s in watchlist}` as `symbol_to_token`, so the engine skips the regime fetch. Add the two
   regime symbols to that map in both places: `{**{s: 0 for s in watchlist}, "NSE:NIFTY 50": 256265, "NSE:INDIA VIX": 264969}`.
   (Cache-only — the engine reads them from the local candle store; nothing is fetched with `kite=None`.)
   Confirm by a short assertion in a test that a run with `kite=None` and a store containing NIFTY candles yields
   candles with non-None `_nifty_close` (reuse the store-fixture style of `tests/test_scale_in.py`).

## Tests required

New `tests/test_feature_addons_w2.py`:
1. `test_registered` — after `import trader.features.registry`, `ADDONS` has exactly the four keys in order.
2. `test_bar_shape_values` — hand-computed values on one hammer candle (long lower wick) and on a zero-range candle.
3. `test_atr_dist_values` — constant-slope series: `ema_dist_atr` sign and `atr_ratio` vs a hand computation.
4. `test_sr_levels` — a series bouncing three times off 100 and twice off 110 with close at 104 → `sup_dist ≈ 0.04`,
   `sup_touches == 3`, `res_dist ≈ 0.0577`, `res_touches == 2`; and no levels → (cap, 0, cap, 0).
5. `test_sr_no_lookahead` — changing the CURRENT bar's close only changes the distances, never the levels/touches.
6. `test_market_values_and_missing` — candles with `_nifty_close`/`_vix_close` give hand-computed values; candles
   without them give four zeros.
7. `test_pipeline_append_order` — enabling all four on the default pipeline gives 6 + 5 + 2 + 4 + 4 = 21 columns,
   base 6 identical to the unwrapped pipeline.
8. `test_runner_regime_symbols` — the runner/engine regime fetch test from step 5.

Whole suite green; parity golden unchanged.

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] 8 new tests pass
- [ ] default pipeline output unchanged (golden untouched)
- [ ] only the four new modules, one registry import block, the two runner lines and the test file changed
- [ ] every add-on returns finite floats on a 30-candle series with zero volume and flat prices

## Completion record

- **Completed:** 2026-10-18 · **Commit:** exp/features @ d54a0c0 (not merged)
- **Validation:** 590 passed, 1 known ISS-11 clock failure; 8 required + 1 finite-values test.
- **Deviations:** sup_dist assertion tolerance (0.0385 vs the guide's ≈0.04); market add-on treats non-positive Nifty/VIX as missing.
- **Result:** EXP-05/06/08 ≈ 0 or worse, EXP-07 +0.010 ΔAUC — all FAILED Stage A.
