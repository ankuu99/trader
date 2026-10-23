# Trader — Rearchitecture Plan (`todo_revamp.md`)

> Goal state: an autonomous, *intelligent* long-only swing bot that trades frequently on
> genuine dip-entries / peak-exits, can run **many model families** (LR, kNN, NN, GBM)
> and **multi-timeframe** strategies, and **notices when it's wrong** and pulls capital
> before the loss limit does it crudely.

This plan is a **staged refactor**, not a rewrite. The execution/risk/data spine is sound
and stays. Every stage keeps backtest↔live parity and is independently shippable.

---

## 0. Guiding principles (do not violate)

1. **Backtest parity is sacred.** `trader/backtest/engine.py` reuses the live `Strategy`,
   `RiskManager`, `OrderManager`. Every stage must keep that true. After each stage, the
   parity harness (Stage 0) must stay byte-identical (until we deliberately change behaviour).
   **Stage 0 builds that harness — it ships before any refactor.**
2. **Strategies never import `orders/` or `risk/`.** Preserved.
3. **No param reaches `live` without out-of-sample validation it never saw during
   selection.** (Stage 5 enforces this in tooling.)
4. **Each stage is mergeable on its own** and leaves the system fully working.
5. **Config nesting mirrors the architecture, migrated per-stage in lockstep.** The flat
   `strategies.lr_extrema` block becomes nested sub-blocks (`model:`, `features:`, `labels:`,
   `entry_gates:`, `exits:`) — each block is the constructor input for the component extracted
   in that stage. Convention: **a disabled optional gate/exit is an *absent block*, not an
   `enabled: false` flag** (presence = enabled). Gates stay as optional plugins, never deleted.
   Each stage migrates its own block in `config.yaml` **and** all 16 `per_stock_params`
   overrides in the same commit (deep-merge already handles nested dicts).

---

## Target nested config schema (end state, after Stages 1–3)

```yaml
strategies:
  lr_extrema:
    enabled: true
    warmup_bars: 300
    lookback_bars: 1200
    retrain_every: 25
    extrema_order: 10
    threshold: 0.9
    veto_threshold: 1.0
    model:                          # → Stage 2 Model
      type: logistic                #   logistic | knn | gbm | mlp
    features:                       # → Stage 1 FeaturePipeline
      volume_ma_bars: 20
      depth:  { enabled: false, lookback_bars: 50 }
      macd:   { enabled: false, fast: 12, slow: 26, signal_period: 9, hist_lookback: 5 }
    labels:                         # → Stage 4 Labeler
      forward: { enabled: false, forward_bars: 150, min_return_pct: 2.0 }
    entry_gates:                    # → Stage 3 EntryPolicy — disabled gates simply ABSENT
      # volume:    { min_ratio: 1.2 }
      # norm_price:{ min: 0.3 }
      # prior_decline: {}
      # trend:     { lookback: 800, min_return: -20.0 }
      # rsi:       { period: 14, max: 30.0 }
      # stoch_rsi: { period: 14, smooth_k: 3, max: 20.0 }
      # macd:      { fast: 12, slow: 26, signal_period: 9, slope_ma_period: 3, slope_threshold: 0.0 }
    exits:                          # → Stage 3 ExitPolicy
      hold_bars: 200
      hard_stop:   { stop_pct: 20 }
      trailing:    { profit_pct: 5, trail_pct: 2, force_close_time: "15:25" }
      pattern_top: { sell_threshold: 0.85, sell_min_pct: 3.0, min_hold_before_exit: 1, floor_enabled: false }
      stale:       { check_bars: 20, min_gain_pct: 0.5 }        # absent = disabled
      stale_2:     { check_bars: 100, min_gain_pct: -2.0 }      # absent = disabled
      # breakeven:      { trigger_pct: 1.0, buffer_pct: 0.0 }
      # momentum_decay: { p_min_floor: 0.35, min_bars: 5 }
```

This collapses ~12 dead `*_enabled: false` flag-lines and makes each stock's config read as
"here is what this stock actually does." Mid-migration the block is partially nested (e.g.
after Stage 1 only `features:` is nested, the rest stays flat) — accepted cost of per-stage.

---

## Where the leverage actually is (summary of the critique)

| Area | Verdict | Stage |
|---|---|---|
| Execution / risk / data persistence / restart recovery | **Solid — keep** | — |
| Backtest↔live parity | **Solid — protect** | guardrail |
| Strategy = monolith (features+labels+model+policy welded) | **Primary blocker** | 1, 2, 3 |
| Per-stock data starvation (kills kNN/NN) | **Blocks fancy models** | 4 |
| Label quality (geometric extrema) | **Caps everything supervised** | 4b |
| Research process = overfitting machine | **Existential for autonomy** | 5 |
| No live-vs-expected feedback loop | **The "intelligent autonomous" gap** | 6 |
| Multi-timeframe | Real gap, partly dissolves into features | 7 |

Lower-priority / deliberately deferred: GTT re-enable, short-selling, options/futures,
partial-fill handling, corporate-action adjustment, multi-account. These are features,
not architecture — none changes whether the bot trades *intelligently*.

---

## Stage 0 — PRESTAGE: parity (characterization) harness ✅ *built*

**Why this must come first:** Stages 1–3 are behaviour-preserving refactors. The only way to
*prove* that is to capture the system's current numeric output, freeze it, and assert equality
after every refactor. Without this, "identical backtest output" is an aspiration, not a check.

**Why the pre-existing tests were not enough.** `tests/test_strategy_flows.py` stubs the model
(`_AlwaysMinModel`) and the scaler (`_PassthroughScaler`), so it deliberately bypasses
`_compute_features`, `_train`, `MinMaxScaler`, and real `predict_proba` — you could silently
break feature math and it would stay green. `tests/test_integration.py` (added with this stage)
runs the **real** chain with **no stubs**, but only asserts *sanity invariants*
(`entry_fills <= signals_entry`, capital never over-deployed, state consistency) — not exact
values. Neither pins behaviour. The parity layer below closes that gap.

### What now exists

- [x] **Real-chain integration harness** — `tests/test_integration.py` wires the actual
      `LRExtremaStrategy → RiskManager → OrderManager → Store` chain (mirrors `main.py`'s
      `handle_candle`/`handle_order_update`) via `PipelineRunner`. No model/scaler stubs.
- [x] **Real candle fixture** — `tests/fixtures/integration/candles.csv`: 1550 real
      **NSE:HAL** 15-minute candles, 2025-01-02 → 2025-03-28, exported from the cached
      `data/market.db`. (Generated, not hand-written — see "regenerating the fixture" below.)
- [x] **Golden characterization test** — `tests/test_parity_golden.py`, three checks:
  - **0a `test_feature_vector_golden`** — real `_compute_features` output at 6 indices, for
    both the 6-feature base vector and the 9-feature `depth+macd` variant, pinned to 1e-9 in
    `tests/fixtures/golden_features.json`. This is the targeted Stage-1 check.
  - **0b `test_pipeline_golden`** — full chain replayed over the HAL fixture; snapshots **every
    trade** (entry/exit/qty/pnl) and **every signal** (type/price) + aggregates, pinned to 1e-6
    in `tests/fixtures/golden_pipeline.json`. Covers Stages 2 (Model) & 3 (Policy).
  - **0c `test_pipeline_is_deterministic`** — two in-process runs must be byte-identical.
- [x] **Cross-process determinism verified** — identical SHA-256 over the full trade+signal
      snapshot across two fresh processes (baseline: 84 trades, 495 signals, +₹9,471.45 P&L).
- [x] **Regen workflow** — `REGEN_GOLDEN=1 pytest tests/test_parity_golden.py` rewrites the
      golden; normal runs assert equality. Behaviour changes regenerate the golden only in a
      **dedicated, reviewed commit** — never silently.

### Version binding (important)

Goldens were generated under **numpy 2.4.4 / scikit-learn 1.8.0**. The `lbfgs` solver can drift
across sklearn minor versions, which would fail the golden for the wrong reason.
- [ ] Pin `numpy` and `scikit-learn` in `requirements.txt` to the generation versions (record
      them; bump deliberately + regenerate golden in the same commit if upgrading).

### Known gap to fix as part of this stage

- [ ] **Pre-existing failing flow test:** `test_strategy_flows.py::test_no_new_entry_while_in_position`
      asserts the strategy never emits ENTRY while in position, but current code *intentionally*
      emits a phantom ENTRY (lr_extrema.py:498–522) so the UI can show where re-entries would
      fire (RiskManager rejects it `already_in_position`). The test contradicts shipped
      behaviour. Decide: fix the test to assert "ENTRY-while-in-position is emitted and rejected
      downstream," or change the behaviour. **Resolve before Stage 1** so `pytest tests/` is
      fully green and the baseline is trustworthy. (Not introduced by this stage — fails on
      unmodified `lr_extrema.py`.)

### How Stages 1–3 consume this

Each refactor PR must leave **0a + 0b byte-identical** (no `REGEN`). The two layers catch
different things — *verified by deliberate perturbation*:
- **0a (feature golden, 1e-9)** catches *any* drift in feature math — fails on a 1e-7 change to
  `norm_price`. This is the sensitive net for Stage 1.
- **0b (pipeline golden, 1e-6 on trades)** catches changes that alter *decisions/trades*. Note:
  it is **insensitive to a uniform scalar on a single feature**, because `MinMaxScaler` re-fits
  per training round and absorbs it before the model — a 5% scale on `norm_price` left every
  trade identical. 0b fails on anything that flips a model prediction or gate (e.g. loosening
  the entry `threshold` 10% changed the trade set immediately). So Stage 1 leans on 0a;
  Stages 2–3 (model/policy) lean on 0b.

The first intentional behaviour change is Stage 4 (pooled training / new labels) — that
regenerates the golden in a reviewed commit.

### Regenerating the candle fixture (if a different stock/period is wanted)

```bash
.venv/bin/python - <<'PY'
import sqlite3, csv
cur = sqlite3.connect('data/market.db').cursor()
rows = cur.execute("SELECT timestamp,open,high,low,close,volume FROM candles "
                   "WHERE instrument='NSE:HAL' AND timeframe='15minute' "
                   "AND timestamp>='2025-01-01' AND timestamp<'2025-04-01' ORDER BY timestamp").fetchall()
with open('tests/fixtures/integration/candles.csv','w',newline='') as f:
    w = csv.writer(f); w.writerow(['timestamp','open','high','low','close','volume'])
    for ts,o,h,l,c,v in rows:
        w.writerow([ts.replace('T',' '), f'{o:.2f}', f'{h:.2f}', f'{l:.2f}', f'{c:.2f}', int(v)])
PY
# then: REGEN_GOLDEN=1 pytest tests/test_parity_golden.py   (regenerate goldens to match)
```
New stocks / older dates not in `data/market.db` need a live Kite fetch first
(`scripts/kite_totp_refresh.py` to auth, then `get_candles`), per the data-fetch workflow.

**Definition of done:** `pytest tests/` green (after resolving the stale flow test); golden
files committed; harness proven to bite on a deliberate 1-bar feature change.

---

## Stage 1 — Extract the FeaturePipeline (model-agnostic features) ✅ *done*

> **Outcome:** `trader/features/` created (`base.py`, `indicators.py`, `extrema_features.py`);
> `lr_extrema.py` 960→756 lines; `features:` config block nested (config.yaml, calibrate, ui,
> test params migrated; no per_stock overrides needed feature keys). Parity golden 0a+0b+0c
> **byte-identical, no REGEN**. Scaler stayed with the strategy (moves in Stage 2).
> `calibrate.py` dropped the no-op `volume_ma_bars` grid dimension (CLAUDE.md: not sensitive).


**Why first:** every model family needs the *same* features. Today `_compute_features`,
`_linreg_slope`, `_rsi_series`, `_ema_series`, `_compute_macd_state`, `_compute_stoch_rsi_k`
all live inside `LRExtremaStrategy`. Pull them out once; everything downstream gets cheaper.

**New module:** `trader/features/pipeline.py`

```python
# trader/features/base.py
class FeaturePipeline(ABC):
    feature_names: list[str]          # stable ordering, introspectable
    min_history: int                  # bars required before output is valid
    def compute(self, candles: list[dict]) -> np.ndarray | None: ...

# trader/features/extrema_features.py
class ExtremaFeaturePipeline(FeaturePipeline):
    # exactly today's 6 base + optional depth + optional MACD features,
    # behind the same config toggles (depth_feature, macd_feature)
```

**Tasks**
- [ ] Move `_compute_features` + all indicator helpers (`_linreg_slope`, `_rsi_series`,
      `_ema_series`, `_compute_macd_state`, `_compute_stoch_rsi_k`) into
      `ExtremaFeaturePipeline`. Keep the optional depth/MACD add-ons behind the same config.
- [ ] `LRExtremaStrategy` holds a `self._features = ExtremaFeaturePipeline(params["features"])`
      and calls `self._features.compute(candles)` everywhere it currently calls
      `self._compute_features`.
- [ ] Indicator helpers used by *entry gates* (RSI/StochRSI/MACD gate state) move to a shared
      `trader/features/indicators.py` so both gates and features import one implementation.
      (The gates themselves stay in `LRExtremaStrategy` until Stage 3.)
- [ ] **Scaler stays with the strategy/model for now** — `MinMaxScaler` is a model-fitting
      artifact, not a feature definition. It moves to the Model in Stage 2. (Confirmed: the
      pipeline golden is insensitive to uniform feature scaling *because* of this scaler, so
      the split is clean.)

**Config sub-step (nest `features:` only, lockstep):**
- [ ] In `config.yaml`, move `volume_ma_bars`, `depth_feature`, `macd_feature` under a new
      `features:` block (rename `depth_feature`→`features.depth`, `macd_feature`→`features.macd`).
- [ ] Migrate the same keys in all 16 `per_stock_params` overrides that set them.
- [ ] `ExtremaFeaturePipeline` reads the nested `features` dict directly.
- [ ] Update `scripts/calibrate.py` `--params` paths and `scripts/ui.py` sidebar inputs that
      reference `volume_ma_bars`/depth/macd to the nested location.
- [ ] Everything else (threshold, exits, gates) stays flat this stage.

**Parity check (Stage 0 harness — no `REGEN`):**
- [ ] `test_feature_vector_golden` (0a) byte-identical — the primary proof for this stage.
- [ ] `test_pipeline_golden` (0b) byte-identical.
- [ ] full `tests/` suite: same pass/fail set as the Stage-0 baseline.

---

## Stage 2 — Extract the Model interface (LR/kNN/NN/GBM become swappable) ✅ *done*

> **Outcome:** `trader/models/` created (`base.py` `ExtremaModel` ABC, `logistic.py`
> `LogisticModel` owning the `MinMaxScaler`, `registry.py` `build_model`). The 5 inline
> `scaler.transform`/`classes_`/`predict_proba` blocks collapsed to
> `p_min, p_max = self._model.predict_proba(x)`; `self._trained` → `self._model.is_trained`;
> `_train` → `self._model.fit(X, y)`. `lr_extrema.py` 756→729 lines, sklearn import gone.
> `model:` config block added (default `logistic`). Updated consumers: `ui.py`,
> `replay_strategy.py` (**the latter had a latent Stage-1 break — `_compute_features` call —
> fixed here; a zsh glob silently skipped it in the Stage-1 sweep**), and the
> `test_strategy_flows` stubs (now implement the `ExtremaModel` interface). Parity golden
> 0a+0b+0c **byte-identical, no REGEN**. Centralized `predict_proba` uses missing-class→0.0;
> this collapses two *unreachable* single-class degenerate defaults (training requires ≥2 of
> each class, so `classes_` is always `[0,1]`) — observable parity confirmed by the golden.


**New module:** `trader/models/`

```python
# trader/models/base.py
class ExtremaModel(ABC):
    def fit(self, X: np.ndarray, y: np.ndarray) -> None: ...
    def predict_proba(self, X: np.ndarray) -> tuple[float, float]:  # (p_min, p_max)
        ...
    @property
    def is_trained(self) -> bool: ...

# trader/models/logistic.py   -> wraps today's LogisticRegression + MinMaxScaler
# trader/models/knn.py        -> KNeighborsClassifier (Stage 4 makes it viable)
# trader/models/gbm.py        -> LightGBM/XGBoost
# trader/models/mlp.py        -> small MLP (only meaningful after Stage 4)
```

- [ ] `LogisticModel` encapsulates `MinMaxScaler.fit_transform` + `LogisticRegression.fit`
      + the `classes_.index(0/1)` proba bookkeeping currently scattered across `on_candle`.
- [ ] `LRExtremaStrategy` owns `self._model: ExtremaModel`; replace the ~5 inline
      `predict_proba` blocks with single `p_min, p_max = self._model.predict_proba(X)` calls.
- [ ] Model choice driven by config: `strategies.lr_extrema.model.type: logistic|knn|gbm|mlp`.
- [ ] Registry passes the configured model into the strategy.

**Config sub-step (nest `model:`, lockstep):**
- [ ] Add a `model:` block with `type: logistic` (default). No flat keys move this stage —
      `model` is net-new config. `per_stock_params` only need a `model:` block if a stock
      overrides the model type (none do initially).

**Parity check (Stage 0 harness — no `REGEN`):** with `model.type: logistic`, `test_pipeline_golden`
(0b) byte-identical. This is the primary proof for this stage (0a unaffected — features unchanged).

> ⚠️ Do **not** ship kNN/NN as "working" until Stage 4. On per-stock data they overfit.
> Stage 2 only makes them *pluggable*; Stage 4 makes them *trustworthy*.

---

## Stage 3 — Extract the Policy engine (entry gates + exit stack) ✅ *done*

> **Outcome:** `trader/policy/` created (`base.py` `PositionState`/`ExitDecision`;
> `extrema_entry.py` `ExtremaEntryPolicy` = the 7 gates; `extrema_exit.py`
> `ExtremaExitPolicy` = candle + tick exit stack). `lr_extrema.py` 729→**421 lines**;
> `on_candle`/`on_tick` now orchestrate + delegate. Position state lives in `self._pos`
> (PositionState); 6 backward-compat property shims keep engine.py/main.py/replay/tests
> working unchanged (incl. main.py's `getattr` persistence).
>
> **Config nesting centralised in `config.flatten_strategy_params`** (not the policy layer)
> so the **live UI (`trader/ui`, which reads `config.strategy_config`) gets flat keys too** —
> verified the dashboard's `stop_pct`/`profit_pct`/`sell_threshold`/… resolve correctly.
> `config.yaml` global nested into `exits:`/`entry_gates:` (disabled gates omitted); only
> per_stock override needing migration was MCX (`profit_pct`/`trail_pct` → `exits.trailing`).
>
> **Verification:** (1) parity golden 0a+0b+0c byte-identical (code extraction, run before
> config migration to isolate risk); (2) per-stock equivalence check — exit/core/features
> exact + entry-gate flags & behaviour identical across global+16 stocks (the disabled-gate
> dormant-param diffs are behaviour-neutral); (3) end-to-end smoke on the real nested-config
> path. Deviation taken (approved): policies receive the strategy as context rather than a
> pure ModelView — fine for v1.


**Why:** entry gates and the exit stack are *trading policy*, identical regardless of which
model produced the score. Today they're ~400 lines welded into `on_candle`/`on_tick`. This
is the split that makes new strategies a config/plugin change instead of a rewrite.

**New module:** `trader/policy/`

```python
# trader/policy/base.py
@dataclass
class ModelView:                      # what policy sees each candle/tick
    p_min: float; p_max: float
    features: np.ndarray
    candle: dict
    position: PositionState | None    # entry_price, held_bars, peak, max_gain, flags

class EntryPolicy(ABC):
    def decide(self, view: ModelView) -> EntryDecision | None: ...   # gates live here
class ExitPolicy(ABC):
    def on_candle(self, view) -> ExitDecision | None: ...            # hold/pattern-top/stale/momentum
    def on_tick(self, view)   -> ExitDecision | None: ...            # hard SL/trailing/breakeven/EOD
```

- [ ] Move the 7 entry gates (volume_ratio, norm_price, prior-decline, trend, RSI,
      StochRSI, MACD) into `ExtremaEntryPolicy`. Keep `last_filter_block` aggregation.
- [ ] Move the exit stack (hold_bars, pattern-top, stale tier1/2, momentum-decay; tick:
      hard SL, trailing activation/exit, breakeven, force-EOD) into `ExtremaExitPolicy`.
- [ ] Position-state tracking (`_entry_price`, `_held_bars`, `_peak_close`,
      `_trailing_active`, `_pattern_top_trailing`, `_max_gain_pct`, `_breakeven_active`)
      becomes a `PositionState` object the policy mutates — and the single source of truth
      for `seed_position_state` / `_reset_position_state` / restart recovery.
- [ ] `LRExtremaStrategy.on_candle` shrinks to: append candle → maybe retrain → compute
      features → model.predict_proba → `exit_policy.on_candle` else `entry_policy.decide` →
      build Signal. Target: < 120 lines.

**Config sub-step (nest `entry_gates:` + `exits:`, lockstep — the big migration):**
- [ ] Build `entry_gates:` and `exits:` blocks per the target schema. **Disabled gates/exits
      are omitted entirely** (presence = enabled) — the 4 off gates + breakeven + momentum-decay
      drop out of `config.yaml`. `ExtremaEntryPolicy`/`ExtremaExitPolicy` instantiate a gate/exit
      only when its block is present.
- [ ] Migrate all 16 `per_stock_params` overrides: their flat exit/gate keys (`stop_pct`,
      `profit_pct`, `trail_pct`, `sell_threshold`, `hold_bars`, `stale_*`, etc.) move under the
      nested `exits:`/`entry_gates:` blocks. Largest single config edit — do it mechanically and
      lean on 0b to verify each stock's behaviour is unchanged.
- [ ] Update `scripts/calibrate.py` `--params` choices → nested paths, and `scripts/ui.py`
      sidebar inputs (threshold/profit/stop/trail/sell_* etc.) → nested locations.

**Parity check (Stage 0 harness — no `REGEN`):** `test_pipeline_golden` (0b) byte-identical on
seed config. **This is the big one** — most code and config move here; 0b is the gate.

**Net result of 1–3:** the base architecture you asked for —
`FeaturePipeline → ExtremaModel → {EntryPolicy, ExitPolicy}` as three plug points, wired by
the registry. A new strategy = pick a feature pipeline + a model + a policy in config.

---

## Stage 4 — Cross-sectional (pooled) training + better labels

This is the stage that makes kNN/NN/GBM *real* instead of overfit toys.

### 4a. Pooled training
**Problem:** each stock trains its own classifier on a few hundred noisy extrema. LR survives
it; kNN/NN do not.

- [x] Added `model.source: self_train | pooled` (default self_train → behaviour-neutral,
      golden byte-identical). In `pooled`, the strategy loads a frozen artifact and never
      self-trains in the candle loop (also removes the synchronous-retrain-in-candle risk).
- [x] `scripts/train_model.py` — pools `(features, labels)` across the cached universe over a
      train window (reusing `ExtremaFeaturePipeline` + `build_labeler`), fits one model, saves
      `.pkl` + `.meta.json` sidecar. `ExtremaModel.save/load` added (pickle).
- [x] Trained a pooled LR on 2023–2024 (cached): **32,986 balanced samples (16.5k/16.5k) × 7
      features from 23 symbols** — vs ~800/stock self-training (~40× data).
- [x] **Honest OOS comparison (pooled trained 2023–24, frozen, tested on 2025):** mixed —
      pooled wins MCX (+1.02% vs +0.29%), ~ties HAL, loses RECLTD/INDHOTEL. **Pooled is
      threshold-robust** (returns flat across thr 0.5–0.9; per-stock is fragile) and **trades
      far more** (30–47 vs 2–29 → serves the frequent-trades goal) but at **lower per-trade
      edge** (PF ~1.1–1.3).
- [x] Added `GBMModel` (sklearn HistGradientBoosting) + registry entry + `train_model
      --model-type`. Trained pooled-GBM on the same 33k samples. **Result: GBM ≈ LR on pooled
      data** (both PF ~1.2). The extra capacity bought nothing → the 6–7 generic technical
      features lack non-linear signal to exploit; more model power on the same features is a
      dead end.
- **STAGE 4 VERDICT (honest OOS, 6 stocks, 2025 H1): neither bet beats baseline.**
  `SUM ret%: per-stock +1.84  |  pooled-LR +0.20  |  pooled-GBM +0.08`. Per-stock self-training
  wins decisively via *selective* high-PF trades (HAL 3.53, TVS 3.29); pooled trades 2–3× more
  at thin PF ~1.2 — and the ~0.22% round-trip cost favours selectivity over frequency.
  Triple-barrier (4b) likewise failed OOS. **Keep per-stock self-training + ExtremaLabeler +
  LogisticModel as the live baseline.** All Stage-4 infra (Labeler / GBM / pooled trainer /
  save-load / `model.source`) is built, clean, behaviour-neutral-by-default, and ready if a
  future feature set justifies it — but the *research bets did not justify adoption now*.
- **Real signal for where to look next:** GBM≈LR says the bottleneck is **features**, not model
  or data volume. The durable Stage-4 win is the swappable architecture + the validation that
  stopped us shipping a worse system.
- [x] **Tested the feature lever — regime (NIFTY/VIX) features.** Added an optional `regime`
  add-on to `ExtremaFeaturePipeline` (nifty_slope, rel_strength, vix_norm; default off →
  golden byte-identical) consuming the already-fetched `_nifty_close`/`_vix_close`. Per-stock
  self-train OOS: `base +1.84 | +regime +1.32` — **net worse** (helps 3, hurts 3). This
  formulation/lookback adds noise.

### STAGE 4 META-CONCLUSION (tested, rejected, reverted)
Four research bets — **triple-barrier labels, pooled training, GBM, regime features** — were
each tested on honest OOS. **All four failed to beat the lean per-stock self-train + extrema +
LR baseline.** The consistent signal: that baseline is genuinely well-matched to this
strategy/universe/cost-structure (selective, high-PF trades beat frequent thin-edge ones).
Model capacity / data volume were never the constraint — **features/data are**.

**Decision (kept the foundation, stripped the dead research):**
- KEPT: the swappable Feature / Model / Policy / Labeler architecture (Stages 1–3 + the
  `Labeler` ABC + `ExtremaLabeler` + `build_labeler` plug point), config nesting, the
  walk-forward validator (Stage 5), and the parity test suite. All behaviour-identical to the
  original strategy, golden byte-identical — just maintainable + safe to extend.
- REMOVED (no value, added surface area): `TripleBarrierLabeler`, `GBMModel`,
  pooled training (`scripts/train_model.py`, `model.source`/save-load), regime features, and
  the `models/*.pkl` artifacts. Recoverable from this session's history if ever wanted; the
  abstractions they plugged into remain, so re-adding is a one-class change.
- [ ] `per_stock_params` stays — but now tunes **policy** (thresholds, exits) on top of one
      shared **model**. (Pooled's threshold-robustness already hints policy-tuning matters more
      than model-threshold once pooled.)

### 4b. Label quality (triple-barrier / meta-labeling)
**Problem:** `_find_local_extrema` labels are geometric and regime-dependent; no model beats
its labels. The forward-label enhancement is a step toward this but bolted on.

- [x] Added a `Labeler` abstraction in `trader/features/labels.py`:
  - `ExtremaLabeler` — today's geometric extrema + forward-return filter, **extracted
    verbatim from `_train` (golden byte-identical)**. `build_labeler` factory + `labels.type`
    config selector (default `extrema`, so nothing changes unless opted in).
  - `TripleBarrierLabeler` — symmetric triple barrier; class 0 = long touches +target before
    −stop within horizon, class 1 = the mirror. Barriers default to the strategy's exits.
- [x] Compared TripleBarrier vs Extrema on cached data (HAL, MCX, RECLTD). Three findings:
  1. **Exit-tied barriers fail** — tying the label stop to `stop_pct=20%` (a circuit-breaker,
     not a real exit) makes class 0 non-discriminative (nearly every candle "long-wins").
  2. **Balanced barriers + the extrema-tuned `threshold=0.9` → 0 trades** — triple-barrier
     produces a smoother probability distribution, so a swap REQUIRES recalibrating threshold.
  3. **In-sample threshold selection flattered it** (HAL +0.65%/PF6.2, MCX +1.04% at hand-picked
     thresholds) but **honest walk-forward — threshold calibrated on train, evaluated OOS —
     erased the edge**: extrema +0.53%/+0.96% vs triple-barrier +0.16%/−0.94% on HAL/MCX. The
     train-best threshold generalized poorly OOS (fitting noise).
- **Verdict: do NOT adopt triple-barrier as-is.** `ExtremaLabeler` stays the baseline. The
  infra (Labeler plug point, factory, `labels.type` selector, `TripleBarrierLabeler`) is in
  place for future experiments, but any adoption must clear walk-forward OOS first — which this
  config does not. **This is the Stage-5-before-Stage-4 thesis proving itself**: the harness
  caught an overfit that the in-sample comparison endorsed.
- Caveats on the test: 2 folds / 2–3 stocks / threshold-only calibration / single TB config
  (3/3/200) / no embargo. Not a final verdict on triple-barrier *in general* — a fuller barrier
  sweep might do better — but it kills this config and proves the methodology.

**Decision gate:** only keep pooled + new labels if Stage 5 walk-forward shows out-of-sample
improvement over the per-stock LR baseline. Otherwise revert — the architecture supports both.

---

## Stage 5 — Fix the research process (kill the overfitting machine) — *in progress*

**Problem:** `screen.py` (pick stocks that backtested well) → `calibrate.py` (fit per-stock
params to the same history) → `per_stock_params`. That's selection bias + multiple testing
at every step. For an autonomous bot this is existential — it will confidently deploy
overfit params.

- [x] **Purged/embargoed walk-forward as the only path to a live param set.**
      `scripts/walk_forward.py` already did fixed-param *model* OOS (non-overlapping test
      windows, model trained only on pre-test data). **Added a `--calibrate` mode** that does
      the missing piece — *parameter-selection* OOS: per fold, search the grid on the train
      window, pick the best params (`--unit per-stock` or `global`, reusing `calibrate.py`'s
      `PARAM_GRID`), then evaluate *those exact params* on the unseen test window via
      `run_backtest(per_symbol_params=...)`. Reports the **train→OOS gap** per run as the
      overfitting tell (verified it surfaces real overfit folds: train +1.73% → OOS −0.49%).
      *Remaining:* an explicit embargo gap between train and test (today they're adjacent,
      which can leak via overnight-hold positions spanning the boundary).
- [ ] **Holdout universe**: reserve a random slice of NSE EQ symbols the screener never sees;
      report performance on it separately as the honest generalization estimate.
- [ ] **Multiple-testing-aware ranking** in `screen.py`/`calibrate.py`: penalize for number
      of stocks × param combos tried (deflated Sharpe / Bonferroni-style haircut), not raw
      `return_pct`. Surface "trials run" in the output so a 2000-stock screen isn't read naively.
- [ ] **Deployment gate**: a small `scripts/promote.py` that refuses to write a stock into
      `per_stock_params` / `watchlist` unless it cleared walk-forward OOS thresholds. Encodes
      principle #3 as a tool, not a habit.

---

## Stage 6 — Closed-loop live-vs-expected drift detection (the "intelligent autonomous" part)

**Problem:** `live-review` is a *manual* skill. An autonomous bot should notice its own decay.

- [ ] Promote drift detection to a live component (`trader/monitor/drift.py`), driven by the
      existing scheduler (`post_market` hook):
  - per-stock, compare realized live fills vs the backtest expectation distribution
    (win-rate, avg P&L, hold time) → rolling KS / z-score drift signal.
  - actions, escalating: **flag** (Telegram) → **auto-pause stock** (stop new entries,
    keep managing open position) → **alert for recalibration**.
- [ ] Wire the unused stubs that already anticipate this:
  - **`confirm_entry()`** (base.py:107) — currently never called. Use it for a regime/trend
    *confirmation* layer gating entries (e.g. a NIFTY-trend filter strategy must confirm).
  - **NIFTY/VIX regime features** — already fetched into candles by the backtest engine
    (`_nifty_close`/`_vix_close`) but unconsumed. Feed them into the feature pipeline /
    confirm_entry so the bot is regime-aware instead of regime-blind.
- [ ] Persist drift state + pause decisions in the `state` table so they survive restarts.

---

## Stage 7 — Multi-timeframe (data + feature layer)

**Why last:** once features are a pipeline (Stage 1), much of the MTF need becomes "add a
daily-trend feature," not new machinery. Do the rest in the data layer.

- [ ] `LiveFeed` assembles **multiple** timeframe buckets per instrument simultaneously
      (e.g. 15m trigger + daily trend), not one global `candle_timeframe`. Reuse the existing
      `_candle_bucket` anchoring; add a per-timeframe bucket set.
- [ ] Strategy receives an **aligned multi-TF view** (latest closed bar of each timeframe).
      `FeaturePipeline.compute` signature extends to accept the multi-TF dict.
- [ ] Backtest engine builds the same aligned multi-TF stream from cached candles (merge by
      timestamp, forward-fill higher timeframe onto lower) — mirror live exactly.
- [ ] Fix the `4hour` bug surfaced in design.md §10: it's in `config.candle_minutes` but not
      in `historical.py` INTERVALS — either remove it or implement resampling from 60minute.

---

## Suggested target package layout (after Stages 1–3)

```
trader/
├── features/
│   ├── base.py            # FeaturePipeline ABC, Labeler ABC
│   ├── indicators.py      # RSI/EMA/MACD/StochRSI (shared by features + gates)
│   ├── extrema_features.py
│   └── labels.py          # ExtremaLabeler, TripleBarrierLabeler
├── models/
│   ├── base.py            # ExtremaModel ABC
│   ├── logistic.py  knn.py  gbm.py  mlp.py
├── policy/
│   ├── base.py            # EntryPolicy/ExitPolicy ABC, PositionState
│   ├── extrema_entry.py   # the 7 gates
│   └── extrema_exit.py    # hold/pattern-top/stale/momentum/trailing/breakeven/EOD
├── monitor/
│   └── drift.py           # Stage 6
└── strategies/
    ├── base.py            # unchanged contract
    ├── registry.py        # wires feature+model+policy from config
    └── lr_extrema.py      # thin orchestrator (~100 lines) over the three plug points
```

---

## Sequencing & risk

| Stage | Unblocks | Risk | Ship independently? |
|---|---|---|---|
| 0 Parity harness | all refactors | low (tests only) — **✅ built** | yes |
| 1 Features | everything | low (pure extract + golden test) | yes |
| 2 Model iface | model swaps | low | yes |
| 3 Policy | new strategies | **med** (most code moved — gate on golden trades) | yes |
| 4 Pooled + labels | trustworthy kNN/NN | med (behaviour change — decision-gated) | yes |
| 5 Walk-forward | honest validation | low (tooling only) | yes |
| 6 Drift loop | autonomy | med | yes |
| 7 Multi-TF | MTF strategies | **high** (live feed change) | yes |

**Stage 0 is done; do 1 → 2 → 3 next.** They're low-risk, parity-preserving, and turn "try kNN/NN/MTF" from a
rewrite into a config change. **Do 5 before 4** ships to live — you need the honest validation
harness *before* you start swapping models, or you'll just overfit faster with fancier tools.

---

## Open questions to resolve before Stage 4

- [ ] Pooled vs per-stock: one universe model, or per-sector models? (sector pooling may
      capture distinct dynamics while still escaping per-stock data starvation.)
- [ ] Triple-barrier barriers: fixed % or volatility-scaled (ATR)? Volatility-scaled is more
      principled but adds a param.
- [ ] Model artifact cadence: retrain pooled model weekly? monthly? on drift trigger?
- [ ] Does `confirm_entry` regime filter belong as a separate `Strategy` (ensemble) or as a
      gate inside `EntryPolicy`? (ensemble is cleaner long-term; gate is faster to ship.)

---

## Alternative strategies — first exploration (non-extrema alpha)

**Motivation:** all of Stage 4 stayed *inside* the extrema classifier (different label/model/
features). This probes genuinely different alpha — and is the more honest place to look, since
tweaks to the extrema model didn't help.

- [x] **De-coupled the backtest engine** — `run_backtest(..., strategy_cls=None)` (defaults to
  `LRExtremaStrategy`, golden byte-identical). The engine no longer hardcodes one strategy; any
  `Strategy` subclass can be backtested. (The `Strategy` ABC already existed; only the engine
  construction was coupled.)
- [x] `trader/strategies/mean_reversion.py` — `MeanReversionStrategy` (z-score dip-buyer, no ML;
  rule-based foil for "does the LR apparatus beat a 5-line rule?"). Uses the engine's intrabar
  stop via `stop_loss_hint`; no `on_tick` needed.
- [x] `trader/strategies/breakout.py` — `BreakoutStrategy` (Donchian channel; trend-following,
  orthogonal alpha — targets the strong-uptrend names where LRExtrema is silent, e.g. SOLARINDS).
- [x] **First OOS look (2026-H1, 5min, untuned):** `SUM ret%: extrema −1.08 | mean_rev −0.27 |
  breakout +0.01`. Reads: (1) extrema is **regime-sensitive** (was +1.84 on 2025-H1) → argues
  for diversification; (2) **mean-reversion was competitive** with the ML baseline (MCX PF 3.81)
  — "does ML earn its keep?" is unresolved, notable; (3) breakout was *correctly silent* on
  non-trending test names — and **SOLARINDS (the uptrend name) has no 5min data**, so its
  designed use-case is untested.
- **NOT a verdict** (single window). **Next, honestly:** (a) run all three through the
  walk-forward harness across folds/regimes; (b) fetch 5min data for the trending `interested`
  names so breakout can be evaluated where it's meant to work; (c) only then consider wiring a
  validated strategy into `registry.build_strategies` for live/paper. Strategies are
  backtest-only today (not registered for live) — correct until validated.
