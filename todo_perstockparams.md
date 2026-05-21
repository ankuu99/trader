# Per-Stock Parameter Overrides — Implementation Plan

## Goal

Allow each instrument in the watchlist to carry its own strategy parameter overrides
on top of global defaults, without breaking the single-config ergonomics for instruments
that don't need overrides.

## Config structure (target)

```yaml
strategies:
  lr_extrema:
    enabled: true
    # --- global defaults (apply to all instruments) ---
    threshold: 0.85
    stop_pct: 10
    profit_pct: 15
    hold_bars: 250
    # ... all other params ...

    per_instrument:                 # NEW block — keys are full instrument symbols
      NSE:CUPID:
        stop_pct: 12
        profit_pct: 18
        hold_bars: 200
      NSE:COROMANDEL:
        threshold: 0.80
        stop_pct: 7
```

Merge rule: global defaults → instrument overrides win. `per_instrument` key is
stripped before the merged dict is passed to the strategy constructor — strategy
sees a flat params dict either way.

---

## Files to change

### 1. `trader/core/config.py`

Add one method alongside the existing `strategy_config(name)`:

```python
def strategy_config_for_instrument(self, name: str, instrument: str) -> dict:
    base = dict(self._data["strategies"].get(name, {}))
    per = base.pop("per_instrument", {})
    overrides = per.get(instrument, {})
    return {**base, **overrides}
```

`strategy_config(name)` stays unchanged — used by calibrate.py where no
specific instrument is in scope.

---

### 2. `trader/strategies/registry.py`

Change `build_strategies(instrument, config)` to use the new method:

```python
# before
lr_cfg = config.strategy_config("lr_extrema")

# after
lr_cfg = config.strategy_config_for_instrument("lr_extrema", instrument)
```

This is the primary consumer — all live and backtest strategy construction goes
through here.

---

### 3. `config/config.yaml`

Add the `per_instrument` block under `strategies.lr_extrema` (initially empty
so behaviour is unchanged):

```yaml
strategies:
  lr_extrema:
    # ... existing params unchanged ...
    per_instrument: {}    # add after the last existing param
```

Populate with calibrated values per stock after running `calibrate.py` per
instrument.

---

### 4. `main.py` — paper position restore (line ~186)

The catch-up exit logic reads `stop_pct`, `profit_pct`, `hold_bars` from a flat
`lr_cfg` to reconstruct SL/target prices for positions held during downtime.

```python
# before (line 186)
lr_cfg = config.strategy_config("lr_extrema")

# after — use the specific instrument's merged params
lr_cfg = config.strategy_config_for_instrument("lr_extrema", instrument)
```

Move this line inside the `for pos in open_paper:` loop so each instrument gets
its own params.

---

### 5. `trader/backtest/engine.py` — per-instrument params support

Currently `run_backtest(kite, store, symbols, symbol_to_token, params, ...)` takes
a single flat `params` dict applied to all symbols.

Change the signature to accept either:
- `dict` — single flat params (backward compat, applied to all)
- `dict[str, dict]` — instrument → params map (per-instrument mode)

Detection: if any value in `params` is itself a dict, treat as instrument map.

Inside the engine where `LRExtremaStrategy(instrument, params)` is constructed:
```python
# resolve per-instrument or fall back to global
p = params.get(instrument, params) if isinstance(next(iter(params.values()), None), dict) else params
strategy = LRExtremaStrategy(instrument, p)
```

---

### 6. `scripts/backtest.py` — build per-instrument params map

```python
# before (line 76)
params = config.strategy_config("lr_extrema")

# after — build {instrument: merged_params} for the engine
params = {
    symbol: config.strategy_config_for_instrument("lr_extrema", symbol)
    for symbol in valid_watchlist
}
```

Also update the `Params` summary line at the end — print a note if instruments
have differing params rather than printing one flat dict.

---

### 7. `scripts/calibrate.py` — per-instrument base params

`base_params` (line 187) is used as the starting point for the calibration grid.
For a per-instrument calibration run, the base should start from that instrument's
current overrides (not just global defaults).

```python
# before
base_params = config.strategy_config("lr_extrema")

# after — if only one instrument in valid_watchlist, use its merged params
if len(valid_watchlist) == 1:
    base_params = config.strategy_config_for_instrument("lr_extrema", valid_watchlist[0])
else:
    base_params = config.strategy_config("lr_extrema")
base_params.pop("per_instrument", None)  # strip nested block
```

Optionally (later): add a `--write-back` flag that writes the best calibrated
params into the `per_instrument.<symbol>` block in `config.yaml` automatically.

---

## Implementation order

1. `trader/core/config.py` — add `strategy_config_for_instrument()` (5 lines, no risk)
2. `trader/strategies/registry.py` — swap one line (lowest risk, affects all paths)
3. `config/config.yaml` — add `per_instrument: {}` (no behaviour change)
4. `trader/backtest/engine.py` — add dict-of-dicts support (isolated to engine)
5. `scripts/backtest.py` — build per-instrument params map
6. `main.py` — move `lr_cfg` inside the restore loop
7. `scripts/calibrate.py` — per-instrument base params

## Validation after implementation

- `python scripts/backtest.py --from 2025-01-01` — verify results unchanged when
  `per_instrument` is empty
- Add one override (e.g. `NSE:CUPID: {stop_pct: 12}`) and verify the strategy for
  CUPID is constructed with `stop_pct=12` while others use the global default
- Paper trading smoke test: restart bot, check that paper position restore uses
  per-instrument `stop_pct` / `profit_pct` / `hold_bars` correctly

## What does NOT change

- Strategy constructor signature — still `LRExtremaStrategy(instrument, params: dict)`
- CLAUDE.md config key table — no new keys at the strategy level; `per_instrument`
  is a config-layer concept only
- Calibration workflow — same commands, same output format

## Notes

- `strategy_config(name)` (without instrument) stays for use cases where no
  instrument is in scope (calibrate.py multi-instrument mode, screen.py)
- The `per_instrument` block is stripped before params reach the strategy, so
  no strategy code needs to know it exists
- Walk-forward validation is strongly recommended before committing per-instrument
  overrides for a stock — naive calibration on the full history will overfit
