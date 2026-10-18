# Campaign scaffold: exit-outcome simulator, feature add-on registry, lag stacking
Written: 2026-10-18 · Tag: TD-018 · Status: OPEN

## Source

> okay with all the framework level fixes done, we are in a very good state now. i want to revist the model for
> detecting the troughs and peaks. […] i want uou to start multiple eorktrees to evaluatd all these and see if we
> gather any peformance gains […] Fix the 14 then go agead with this plan. Continue autonomously now.

— `TODO/TD-018-extrema-model-campaign/DETAIL.md`, as of 2026-10-18. Protocol: `docs/01_Extrema_Model_Campaign.md`.

## Intent

Three shared, default-off building blocks that the campaign's worktree arms build on, so the arms never edit the
same lines:

1. **`trader/policy/outcome.py`** — one canonical "what would our non-model exits do to a long entered at bar t"
   simulator, used by the new tradeable-trough labeler (worktree W1) and by `scripts/campaign/stage_a.py`.
2. **`trader/features/addons.py`** — a registry of *feature add-ons* (extra columns appended to any pipeline's
   vector) plus an `AddonPipeline` wrapper. Worktree arms add one add-on class each and one registry line.
3. **`LagPipeline`** (same file) — appends the inner vector at t-1, t-2, … (ledger EXP-04 / branch idea B-02).

**Must NOT change:** default behaviour. With no `features.<addon>.enabled` and no `features.lags`, `build_feature_pipeline`
returns exactly the same object type it returns today (parity golden + every existing test stays green). Add-on and
lag columns are always APPENDED after the inner vector, so positional entry gates (`x[0]`, `x[1]`, `x[5]`) are unaffected.
No live-path, config.yaml, or engine changes.

## Implementation steps

1. **New `trader/policy/outcome.py`:**
   ```python
   def simulate_exit_outcomes(closes, params: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
       """For every bar t: (good, outcome_ret_pct, exit_index) of a long entered at closes[t] under the
       stock's NON-MODEL exits on the close path. good = reached +profit_pct (trail arming) first.
       outcome_ret_pct = profit_pct on success, else the return at the exit bar; NaN when the outcome is
       unresolved because the data ends first (truncation guard — never guess)."""
   ```
   Move the body of `simulate_exits` from `scripts/campaign/stage_a.py` **verbatim** (it reads the flattened param
   keys `profit_pct, stop_pct, hold_bars, stale_exit_enabled, stale_check_bars, stale_min_gain_pct,
   stale_rearm_enabled, stale_rearm_cur_floor_pct, stale_exit_2_enabled, stale_check_bars_2, stale_min_gain_pct_2`).
   Accept `closes` as any sequence (convert with `np.asarray(closes, dtype=float)`). Then make
   `scripts/campaign/stage_a.py` import it (`from trader.policy.outcome import simulate_exit_outcomes as simulate_exits`)
   and delete its local copy. `scripts/campaign/headroom_probe.py` imports `simulate_exits` from stage_a — keep that name
   importable from stage_a.

2. **New `trader/features/addons.py`:**
   ```python
   class FeatureAddon(ABC):
       name: str = ""                       # config key under `features:` and registry key
       def __init__(self, cfg: dict): ...   # cfg = features[<name>] block
       @property
       @abstractmethod
       def feature_names(self) -> list[str]: ...
       @property
       @abstractmethod
       def min_history(self) -> int: ...
       @abstractmethod
       def compute(self, candles: list[dict]) -> list[float]:
           """Values for the LAST candle. Must return len(feature_names) finite floats; return neutral
           values (0.0) rather than None when data is short or an input is missing."""

   ADDONS: dict[str, type[FeatureAddon]] = {}   # empty in this guide; worktree arms register here

   class AddonPipeline(FeaturePipeline):
       def __init__(self, inner: FeaturePipeline, addons: list[FeatureAddon]): ...
       feature_names -> inner.feature_names + each addon's names (in order)
       min_history   -> max(inner.min_history, each addon.min_history)
       compute(candles) -> None if len(candles) < min_history or inner returns None,
                           else np.concatenate([inner_vec, addon values...]).astype(float)

   class LagPipeline(FeaturePipeline):
       def __init__(self, inner: FeaturePipeline, lags: list[int]): ...   # lags sorted, unique, all >= 1
       feature_names -> inner names + [f"{n}_lag{k}" for k in lags for n in inner names]
       min_history   -> inner.min_history + max(lags)
       compute(candles) -> None if len(candles) < min_history; else inner.compute(candles) followed by
                           inner.compute(candles[:-k]) for each k; None if any part is None.
   ```
   `candles` may be a deque — convert with `list(candles)` once before slicing.
   Expose `_smoother` passthrough is NOT needed (the regime pipeline reads its own).

3. **`trader/features/registry.py`** — after building the base pipeline:
   ```python
   enabled = [ADDONS[k]((cfg.get(k) or {})) for k in ADDONS if (cfg.get(k) or {}).get("enabled")]
   pipe = AddonPipeline(base, enabled) if enabled else base
   lags = cfg.get("lags") or []
   if lags: pipe = LagPipeline(pipe, [int(k) for k in lags])
   return pipe
   ```
   Iterate `ADDONS` in registry (insertion) order so column order is deterministic. Update the module docstring
   (add-ons + lags, appended after the base vector).

4. **Strategy attribute access:** `lr_extrema.py` and `meta_filter.py` only use `compute`, `feature_names`,
   `min_history` — verify no caller reaches into pipeline internals (e.g. `_smoother`, `_depth_enabled`) on the
   object returned by the registry; if one does, report it (do not work around it).

## Tests required

New `tests/test_feature_addons.py`:
1. `test_default_pipeline_type_unchanged` — `build_feature_pipeline({})` and `({"type": "swing"})` return
   `ExtremaFeaturePipeline` / `SwingFeaturePipeline` instances (not wrappers).
2. `test_addon_appends_columns` — register a dummy add-on in a fixture (monkeypatch `ADDONS`), enable it, assert
   names/values appended after the base 6, base columns identical to the unwrapped pipeline, `min_history` = max.
3. `test_lag_pipeline_values` — `lags: [1, 2]` on the default pipeline: length 18, the `_lag1` block equals the
   unwrapped pipeline on `candles[:-1]`, `_lag2` on `candles[:-2]`; returns None below `min_history`.
4. `test_lags_wrap_addons` — both enabled: order is base, addon, then lagged copies of (base+addon).
5. `test_deque_input` — compute accepts a `collections.deque`.

New `tests/test_outcome_sim.py`:
6. `test_success_before_stale` — closes rising to +profit_pct at bar 5 → good, ret == profit_pct, exit idx 5.
7. `test_stale_tier1_fails` — flat closes, stale check 4 / min gain 0.5 → not good, exit at bar t+4.
8. `test_hard_stop` — −stop_pct drop → not good, ret ≤ −stop.
9. `test_truncated_is_nan` — a bar too close to the end with no resolution → ret NaN.
10. `test_matches_stage_a` — `scripts.campaign.stage_a.simulate_exits is simulate_exit_outcomes`.

All existing suites stay green; `test_parity_golden` must not change.

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] 10 new tests pass
- [ ] default `build_feature_pipeline` output byte-identical (golden untouched)
- [ ] no trader.backtest import in live/UI; no edits to main.py / engine / config.yaml
- [ ] `ADDONS` empty after this guide (arms register their own)

## Completion record

- **Completed:** 2026-10-18 · **Commit:** see `git log -- trader/features/addons.py` (scaffold commit)
- **Validation:** 581 passed, 1 known ISS-11 failure (09:15–15:30 clock); 10 new tests; registry returns the
  unwrapped base pipeline when nothing is enabled (golden untouched); `ADDONS` empty.
- **Deviations:** tests monkeypatch `trader.features.registry.ADDONS` (registry imports the dict by name — same
  object). Main session added a `__main__` guard to `scripts/campaign/headroom_probe.py`.
- **For arms:** register an add-on by defining it in its own module and adding it to `ADDONS` there; import that
  module from `trader/features/registry.py` (one line per arm) so registration happens before any build.
