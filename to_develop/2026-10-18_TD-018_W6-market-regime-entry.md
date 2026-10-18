# W6 — Market-regime entry modulation (prior-day India VIX percentile)
Written: 2026-10-18 · Tag: TD-018 (arm EXP-18) · Status: OPEN · Worktree: `../trader-2-wt/regime`, branch `exp/regime`

## Source

> […] i want uou to start multiple eorktrees to evaluatd all these and see if we gather any peformance gains […]

— `TODO/TD-018-extrema-model-campaign/DETAIL.md`, as of 2026-10-18. Evidence: ledger EXP-12 (stratification),
`scripts/campaign/market_headroom_probe.py` (prior-day VIX median AUC 0.638 vs tradeable troughs, 86 % of stocks),
`scripts/campaign/vix_by_year.py` (edge > 0.5 AUC within 6/7 years 2020–26), `scripts/campaign/trades_by_market.py`
(baseline FULL: entries in the VIX "stress" tercile made ₹332.7k of ₹419k; "calm" entries avg +0.17 %/position).
Literature: Nagel (2012) — reversal returns are a liquidity premium that rises with VIX (`docs/02` §7).

## Intent

A default-off decision-layer modulation: the strategy reads the market state at entry time (prior-session India VIX
percentile vs its own trailing year) and adjusts the entry threshold and/or the order size per state. It does NOT
change P(min), features, labels, exits, or risk caps. Live is unaffected until a later wiring TD: live candles carry no
`_mkt_*` keys → state "unknown" → no modulation.

## Implementation steps

1. **Engine context injection — `trader/backtest/engine.py`.** After the existing NIFTY/VIX regime fetch (which fills
   `_nifty_ts/_nifty_cl/_vix_ts/_vix_cl`), build a date-keyed table of PRIOR-SESSION market context:
   - daily close per date = last 15m close of that date (VIX and NIFTY separately);
   - `vix_pct[d]` = fraction of the previous `vix_lookback_days` daily VIX closes (strictly before d's prior session)
     that are below the prior session's close — i.e. for date d use the session before d as "today" and the
     `vix_lookback_days` sessions before that as the reference; require ≥ 60 reference sessions else None;
   - `nifty_dd60[d]` = prior session NIFTY close / max(NIFTY closes over the 60 sessions ending at that prior session) − 1.
   `vix_lookback_days` comes from the strategy params `market_regime.vix_lookback_days` (default 250; one global value —
   read it from `params`, not per symbol).
   In `_build_candle` add `"_mkt_vix_pct"` and `"_mkt_nifty_dd60"` (None when unavailable). Only compute when any
   symbol's params have `market_regime.enabled` true; otherwise inject None (zero cost, byte-identical trades).
   Aggregated bars inherit these keys from their last member candle (existing aggregator behaviour — verify).

2. **Runner support** — `scripts/campaign/run_windows.py::_run_window` and `scripts/campaign/stage_a.py::score_run`:
   pass `{**{s: 0 for s in watchlist}, "NSE:NIFTY 50": 256265, "NSE:INDIA VIX": 264969}` as `symbol_to_token` so the
   engine reads the regime series from the cache (cache-only; `kite=None`). Same in `scripts/campaign/save_trades.py`.

3. **Strategy — `trader/strategies/lr_extrema.py`.** Read the nested block `market_regime` from params
   (flatten_strategy_params leaves unknown nested blocks as-is — verify):
   ```yaml
   market_regime:
     enabled: false
     vix_lookback_days: 250
     calm_below: 0.333        # vix_pct <  calm_below  → "calm"
     stress_above: 0.667      # vix_pct >  stress_above → "stress"; otherwise "mid"; None → "unknown"
     calm:   {threshold_delta: 0.0, size_mult: 1.0, block: false}
     mid:    {threshold_delta: 0.0, size_mult: 1.0, block: false}
     stress: {threshold_delta: 0.0, size_mult: 1.0, block: false}
   ```
   In the flat-entry branch of `on_candle`, when enabled and the state is known:
   - `thr_eff = self._threshold + state.threshold_delta`, clamped to [0.0, 1.0]; use `thr_eff` in place of
     `self._threshold` for BOTH the `p_min >= threshold` check and the signal_log condition;
   - `state.block` → treat as a gate block: `last_filter_block = "market_regime=<state>"`, log type "BLOCKED", return None
     (same path as `ExtremaEntryPolicy` blocks, so the entry guard is not armed);
   - `size_mult != 1.0` → `size_weight = size_mult` (multiply with the meta size_weight when both are set).
   The in-position (add-on) ENTRY branch and all exits are unchanged. Unknown state or disabled → exactly today's path.
   Store the state on the strategy as `self.last_market_state` (str | None) for diagnostics.

4. **Docs** — one bullet in `trader/strategies/CLAUDE.md` (entry section) and one in `trader/backtest/CLAUDE.md`
   (context injection) stating the feature is default-off, backtest-only until live wiring.

## Tests required

New `tests/test_market_regime_entry.py`:
1. `test_disabled_is_identity` — enabled false: a strategy fed candles with `_mkt_vix_pct` behaves identically
   (same signals) to one fed candles without the keys.
2. `test_state_classification` — vix_pct 0.1/0.5/0.9/None → calm/mid/stress/unknown.
3. `test_threshold_delta` — stub the model's `predict_proba` (monkeypatch) to return p_min 0.86: threshold 0.85 + calm
   delta +0.05 → no ENTRY in calm; same candle in stress → ENTRY.
4. `test_block_calm` — calm block → no signal, `last_filter_block == "market_regime=calm"`, entry guard not armed.
5. `test_size_mult` — stress size_mult 0.5 → Signal.size_weight == 0.5; combined with a meta size_weight 0.8 → 0.4.
6. `test_engine_injects_context` — a store seeded with NIFTY/VIX 15m candles over > 70 sessions and one stock:
   with `market_regime.enabled` the candles reaching the strategy carry `_mkt_vix_pct` in [0, 1] computed from the
   PRIOR session only (assert a hand-computed value for one date); with it disabled the keys are None.
7. `test_no_lookahead` — changing the VIX close of session d does not change `_mkt_vix_pct` on session d.

Whole suite green; parity golden unchanged.

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] 7 new tests pass
- [ ] disabled ⇒ byte-identical backtest (main session re-runs a baseline window to confirm)
- [ ] no live-path edits (main.py, trader/data/live.py, orders, risk)

## Completion record
