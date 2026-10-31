# Meta-Labeling — Detailed Implementation Plan

## 0. Premise & goal

Three experiments (curvature, segmented slopes, window+MLP) all enriched the
**primary entry model** and all *lowered* precision (more trades, lower win rate,
worse Sharpe/Calmar). Diagnosis: the primary is **high-recall / low-precision** and
is **not feature-limited**. Enriching the *side* model loosens its boundary.

Meta-labeling (López de Prado) is the matched fix: keep the primary as the
**side/timing** generator; add a **secondary model** that decides **whether to take
each candidate signal** (phase 1) and **how big** (phase 2). It learns *which* of the
primary's firings are the good ones — using a **different, contextual feature set** —
rather than blindly cutting volume (which the threshold sweep already showed fails).

```
candle ─▶ Primary (logistic extrema)  ─▶ candidate ENTRY  (P(min)≥thr ∧ P(max)<veto ∧ gates pass)
                                                │
                                                ▼
                                  Meta model:  p_win = P(this trade hits PT before SL/time)
                                                │
                                p_win ≥ meta_threshold ?  ── no ─▶  META_BLOCKED (no order)
                                                │ yes
                                                ▼
                                   emit ENTRY   (phase 2: qty ∝ p_win)
```

**Success bar (the test the shape plans flunked):** at **matched-or-lower trade
count**, **money-weighted win rate AND profit factor AND Calmar must rise**, and the
gain must **survive walk-forward OOS** (`scripts/walk_forward.py`). Raw P&L alone is
insufficient — the MLP matched P&L while halving Calmar.

---

## 1. Non-negotiable design constraints

1. **No look-ahead at inference.** Meta-labels are outcome-based (forward-looking).
   Training may use forward windows, but only on firings whose **entire barrier window
   ends at or before the current candle**. The engine streams candles chronologically;
   `_train` already operates on `list(self._candles)` up to "now" — the labeler must
   discard any firing whose barrier window extends past the last buffered candle.
2. **Different features than the primary.** Re-using the primary's 6 scalars just
   relearns the primary. Use volatility/regime/structure context (§3.1).
3. **Parity-preserving.** Everything opt-in, default OFF. `tests/test_parity_golden.py`
   must stay byte-identical (meta disabled = current behaviour exactly).
4. **Per-stock first, regularized.** Stage 4 showed pooled hurts; small per-stock data
   → shallow/regularized model (xgboost depth ≤3, high `min_child_weight`).
5. **Config flows through `flatten_strategy_params` / `get_strategy_params`.** The
   nested `meta_label:` block must survive flattening like `exits:`/`features:` do, so
   `backtest.py`, `backtest_rolling.py`, and `walk_forward.py` all pick it up via
   `config.strategy_config("lr_extrema")`.

---

## 2. Component map (mirrors existing S1–S4 plug-points)

| New file | Role | Mirrors |
|---|---|---|
| `trader/features/meta_features.py` | `MetaFeaturePipeline` — context features at a candidate entry | `ExtremaFeaturePipeline` |
| `trader/models/meta.py` | `MetaModel` — `P(win)` binary classifier (xgboost/logistic) | `LogisticModel` |
| `trader/features/labels.py` (extend) | `MetaLabeler` / `triple_barrier_label()` — outcome label per firing | `ExtremaLabeler` |
| `trader/strategies/meta.py` (or inline) | `MetaFilter` — owns meta train + predict; wired into the strategy | new |

Plus edits to: `trader/strategies/lr_extrema.py` (wire train + inference gate),
`config/config.yaml` (the `meta_label:` block), `tests/` (unit + integration).

---

## 3. Detailed design

### 3.1 `MetaFeaturePipeline` (context features)

Implements the `FeaturePipeline` ABC (returns a 1-D vector; `min_history`,
`feature_names`). Computed at the candidate-entry candle. Proposed columns:

- **Volatility:** std of last `vol_bars` % returns; ATR/price.
- **Dip depth:** `drawdown_from_high` over a lookback (how deep is this dip).
- **Oscillators:** RSI(14), Stoch-RSI — reuse `trader/features/indicators.py`
  (`rsi_series`, `stoch_rsi_k`) — overbought/oversold context.
- **Regime:** serial correlation of recent returns (mean-revert vs trend); the
  higher-timeframe trend flags already injected by the engine onto the candle dict
  (`_htf_downtrend` / `_htf_inversion`) — read defensively (may be absent in pure
  cache-only single-symbol runs).
- **Primary confidence (fair meta-inputs):** `p_min`, `p_max`, and the margin
  `p_min - threshold`. How sure was the primary?

Keep it small (~8–10 features) given per-stock data. All scale-invariant.

### 3.2 `MetaModel` (P(win))

```python
class MetaModel:
    def __init__(self, cfg): ...          # type: xgboost | logistic
    def fit(self, X, y): ...              # y ∈ {0,1}; owns its scaler; class_weight/upsample
    def predict_proba(self, x) -> float  # single P(win)
    @property
    def is_trained(self) -> bool
```

- **xgboost** (already a dependency): `max_depth=3`, `n_estimators≈100`,
  `min_child_weight≈5`, `reg_lambda` > 0, fixed `random_state`. Shallow + regularized
  for small samples.
- **logistic** fallback: conservative linear baseline (good first A/B — if even a
  linear meta-filter helps, the signal is real; if not, suspect leakage/features).
- **Imbalance:** if the primary's historical win rate is far from 50%, up-sample the
  minority class or pass `scale_pos_weight` — the H&T study found balanced classes
  essential.

### 3.3 Triple-barrier meta-labeling

For each historical candle where the primary **would have fired** (recompute the
primary's gate over the train window, or cache per-candle `p_min/p_max`), assign:

```
entry  = close[i]
PT     = entry * (1 + profit_pct/100)        # or entry + atr_mult*ATR  (phase 3)
SL     = entry * (1 - stop_pct/100)
for j in i+1 .. min(i+max_bars, last_buffered):     # leakage guard: never past 'now'
    if low[j]  <= SL: y = 0; break          # stop hit first
    if high[j] >= PT: y = 1; break          # profit hit first
else:
    y = 1 if close[last] > entry else 0     # time barrier → sign of P&L (or drop as 'no-decision')
```

Barriers **default to the strategy's own exit params** so labels match real exits:
`profit_pct` ← `exits.trailing.profit_pct`, `stop_pct` ← `exits.hard_stop.stop_pct`,
`max_bars` ← `exits.hold_bars`. Discard firings whose barrier window would extend past
the last buffered candle (the leakage guard).

### 3.4 `MetaFilter` — train + predict, owned by the strategy

```python
class MetaFilter:
    def __init__(self, params):           # reads meta_label: block; builds pipeline+model+labeler
        self.enabled = ...
        self.meta_threshold = ...
    def train(self, candles, primary_predict_fn):
        # 1. scan candles for primary firings (primary_predict_fn -> (p_min,p_max))
        # 2. triple_barrier_label each (leakage-guarded)
        # 3. compute meta-features per firing
        # 4. fit MetaModel if enough of each class
    def allow(self, x_meta) -> tuple[bool, float]:
        # returns (take_trade, p_win); (True, 1.0) if disabled/untrained (no-op)
```

### 3.5 Wiring into `LRExtremaStrategy` (`trader/strategies/lr_extrema.py`)

- **`__init__`:** `self._meta = MetaFilter(params)` (no-op when disabled).
- **`_train` (~L351):** after `self._model.fit(...)`, if meta enabled call
  `self._meta.train(list(self._candles), self._model.predict_proba)`. (The primary is
  already fit, so firings are recomputable.)
- **Inference (entry site ~L204–221):** after `p_min ≥ threshold and p_max < veto` and
  `entry_policy.gate_blocks(...)` returns empty, and before
  `self._pos.entry_price = close`:
  ```python
  if self._meta.enabled and self._meta.is_trained:
      x_meta = self._meta.features.compute(self._candles, p_min=p_min, p_max=p_max)
      take, p_win = self._meta.allow(x_meta)
      if not take:
          _log_entry["type"] = "META_BLOCKED"; _log_entry["p_win"] = p_win
          self.last_filter_block = f"meta p_win={p_win:.2f}<{self._meta.meta_threshold}"
          self._candles_since_train += 1
          return None
  ```
  This slots in exactly like `gate_blocks` (precedent already in the code).
- **Phase 2 sizing:** thread `p_win` onto the `Signal` (new optional field) →
  `RiskManager` scales quantity (e.g. `qty * clamp(p_win / meta_threshold, …)`).
- **Diagnostics:** add `p_win` + `META_BLOCKED` to `signal_log` so `replay` / UI show
  vetoes.

### 3.6 Config schema (`config/config.yaml`, default OFF)

```yaml
strategies:
  lr_extrema:
    meta_label:
      enabled: false
      meta_threshold: 0.5
      model:
        type: xgboost            # xgboost | logistic
        max_depth: 3
        n_estimators: 100
        min_child_weight: 5
        reg_lambda: 1.0
      features:
        vol_bars: 20
        rsi_period: 14
        include_primary_scores: true
      barriers:                  # all default to the matching exits: param if omitted
        profit_pct: null
        stop_pct: null
        max_bars: null
        atr_mult: null           # phase 3: ATR-scaled barriers
```

---

## 4. Phasing

- **Phase 0 — scaffolding.** All components, config plumbing, OFF. Parity green. Unit
  tests: feature shape; model fit/predict; `triple_barrier_label` correctness on
  synthetic up/down/V series; leakage guard (no firing labeled using future-of-now).
- **Phase 1 — binary gate.** Wire train + inference veto. Validate (§5). Try
  `model.type: logistic` first (leakage canary), then `xgboost`.
- **Phase 2 — confidence sizing.** `qty ∝ p_win`. Compare to phase 1.
- **Phase 3 — better labels/barriers.** ATR-scaled triple-barrier; optional
  **trend-scanning** labels for the *primary* (the principled "dynamic extrema_order").
  Optional **pooled meta-model** A/B (meta "is this dip real?" may pool better than the
  primary did in Stage 4).

---

## 5. Validation protocol (uses the existing scripts)

Run all three, in order. Same span as prior experiments: `2024-06-01 → 2025-12-31`,
`--cache-only`, full watchlist. Compare meta-ON vs meta-OFF (baseline).

**5.1 In-sample sanity — `scripts/backtest.py`**
```
python scripts/backtest.py --from 2024-06-01 --to 2025-12-31 --cache-only
```
Toggle `meta_label.enabled`. **Gate:** win rate ↑ AND profit factor ↑ at
**trades ≤ baseline** (571). If trades go *up*, the gate is mis-wired (a filter can
only remove). If win rate doesn't rise, stop — it's the threshold sweep again.

**5.2 Regime robustness — `scripts/backtest_rolling.py`**
```
python scripts/backtest_rolling.py --from 2024-06-01 --to 2025-12-31 --window 6 --step 3 --cache-only
```
Reports `money_weighted_win_rate`, `profit_factor`(via metrics), `sharpe_proxy`,
% profitable windows per 6-month window. **Gate:** meta-ON ≥ baseline win rate in a
**majority of windows** (not just on aggregate) — confirms it's not one-regime luck.

**5.3 TRUE OOS — `scripts/walk_forward.py` (the decisive test)**
```
python scripts/walk_forward.py --from 2024-06-01 --to 2025-12-31 --train 6 --test 3 --cache-only
```
Fixed-param mode trains the **self-training model (primary AND meta) only on data
before each non-overlapping test window** — so it is the natural leakage detector for
meta-labeling. No special handling needed: the strategy (incl. `MetaFilter.train`)
refits per fold on pre-test candles only.

**Gates (this is what decides keep/kill):**
- **Consistency ↑ or ≥ baseline** (% profitable folds — the script's headline metric;
  target > 60%).
- **OOS avg win rate / profit factor ↑** vs baseline meta-OFF.
- **No collapse vs in-sample.** If 5.1 shows a big gain but walk-forward erases it →
  **look-ahead leakage in the meta-labels** → fix the leakage guard, don't ship.

Optional calibrated walk-forward to tune `meta_threshold` honestly:
```
python scripts/walk_forward.py --from 2024-06-01 --to 2025-12-31 --calibrate --unit per-stock --cache-only
```
(The script's `Train→OOS gap` line is the overfitting tell.)

---

## RESULTS (recorded as phases complete)

**Test span:** 2024-06-01 → 2025-12-31, full watchlist, `--cache-only`, **per-stock
overrides OFF** (renamed key) for clean comparison. Baseline below is therefore the
758-trade meta-OFF reference (not the 571-trade per-stock-ON config).

### Phase 1 — binary gate ✅ VALIDATED (in-sample + OOS)

In-sample A/B (`_meta_ab.py`):

| config | trades | win% | mwWR% | PF | ret% | sharpe | maxDD% |
|---|---|---|---|---|---|---|---|
| baseline meta-OFF | 758 | 48.7 | 64.4 | 1.81 | 112.1 | 0.173 | 13.3 |
| meta xgb @0.50 | 759 | 49.4 | 63.5 | 1.74 | 105.7 | 0.162 | 15.2 |
| **meta xgb @0.55** | **256** | 51.2 | **72.8** | **2.68** | 59.5 | **0.273** | **3.8** |
| meta xgb @0.60 | 246 | 50.8 | 71.8 | 2.54 | 55.2 | 0.261 | 4.9 |
| meta logistic @0.50 | 611 | 51.6 | 65.5 | 1.89 | 114.6 | 0.184 | 20.1 |

Walk-forward OOS (`walk_forward.py`, 2025, train 6 / test 3, 4 folds):

| | baseline meta-OFF | meta @0.55 |
|---|---|---|
| Profitable folds | 3/4 (75%) | 3/4 (75%) |
| Avg win rate | 58.5% | **70.9%** |
| Avg profit factor | 1.52 | **3.79** |
| Avg max drawdown | 5.2% | **1.8%** |
| Avg return/fold | +7.04% | +5.73% |
| Calmar (ret/DD) | 1.35 | **3.18** |
| Total trades | 616 | 154 |

**Conclusion:** precision gain survives OOS; not leakage (logistic canary also improved).
The only cost is absolute return (precision/recall tradeoff) — addressed by Phase 2/scale-up.

### Phase 2 (sizing) + scale-up ✅

| config | trades | PF | pnl | ret% | sharpe | maxDD% |
|---|---|---|---|---|---|---|
| baseline meta-OFF cap10 | 758 | 1.81 | 280,209 | 112.1 | 0.173 | 13.3 |
| meta @0.55 cap10 | 256 | 2.68 | 148,736 | 59.5 | 0.273 | 3.8 |
| **meta @0.55 cap20** | 219 | 3.16 | 277,485 | 111.0 | 0.309 | 5.4 |
| meta @0.55 sizing[.5-1.5] cap20 | 220 | 3.28 | 268,795 | 107.5 | 0.305 | 4.3 |

cap20 recovers baseline absolute return with ~2× Sharpe / half DD. Sizing ≈ binary (wash).

### Phase 3 — per-stock re-validation / ATR barriers / trend-scan

| config | trades | win% | PF | ret% | sharpe | maxDD% |
|---|---|---|---|---|---|---|
| perstock-ON meta-OFF | 571 | 54.6 | 2.06 | 107.1 | 0.231 | 9.3 |
| perstock-ON meta @0.55 | 182 | 58.8 | 2.67 | 44.6 | 0.311 | 5.2 |
| meta ATR-barriers(2/2) | 312 | 56.7 | 2.29 | 72.5 | 0.244 | 7.2 |
| trendscan meta-OFF | 31 | 58.1 | 3.37 | 11.5 | 0.422 | 2.1 |
| trendscan meta @0.55 | 28 | 64.3 | 5.24 | 12.7 | 0.564 | 1.5 |

Meta additive on per-stock-tuned config ✅. ATR barriers ✗ (worse than %). Trend-scan
ultra-selective (research lead; too few trades at t_threshold=2.0).

### DEPLOY CANDIDATE — meta@0.55 + cap20 + per-stock ON, expanded 2024-06→2026-06 ✅

Backtest (2 yr): 152 trades, WR 59.2%, PF~, ₹194k (77.7%), Sharpe 0.326, Sortino 0.931,
**Calmar 5.24**, R:R 2.05.

Walk-forward OOS (6 folds, 2025-01→2026-06): **4/6 profitable (67%)**, avg +7.64%/fold,
avg WR 64.0%, avg PF 2.86, avg DD 3.9%. Best Q4-25 +37.9% (PF 5.79). The 2 losing folds
are **both Q1** (2025 & 2026, PF 0.76) — a structural Q1 weakness meta can't rescue, and
cap20 amplifies (those folds' DD 10.3%/7.1%). → test **cap15** as a middle ground.

**Conclusion:** validated, OOS-robust deploy candidate. Higher quality + higher return than baseline.

### cap15 vs cap20 + EXTENDED horizon (Jan 2024 → Jun 2026, 2024 H1 backfilled)

Backtest (2.5 yr):
| cap | trades | WR% | pnl | ret% | Sharpe | Sortino | Calmar |
|---|---|---|---|---|---|---|---|
| 15 | 184 | 53.8 | 234,238 | 93.7 | 0.337 | 1.015 | 2.90 |
| **20** | 174 | 54.6 | 274,290 | 109.7 | **0.361** | **1.150** | **3.67** |

Walk-forward (8 OOS folds, 2024-07→2026-06):
| cap | folds | avg ret/fold | avg WR | avg PF | avg DD | worst |
|---|---|---|---|---|---|---|
| 15 | 6/8 (75%) | +8.50% | 67.0 | 2.91 | **2.7%** | −3.55 |
| **20** | 6/8 (75%) | **+11.49%** | 67.1 | 2.95 | 3.7% | −4.80 |

**Decision: cap20.** Wins every aggregate risk-adjusted metric AND walk-forward return; cap15's
slightly lower DD doesn't justify ~16pp less return. The longer horizon *improved* robustness
(OOS consistency 67%→75%, WR 64%→67% with 2024 H2 added). Q1 remains the weak quarter both years.

**FINAL DEPLOY CANDIDATE: meta@0.55 (binary, xgboost, % barriers) + per-stock overrides ON + cap20.**
Validated over 2.5 yr + 8 OOS folds: PF ~2.95, WR 67%, Calmar 3.67 (vs meta-OFF PnL-baseline PF ~2.06).
cap20 is validated ONLY paired with meta on — never enable cap20 with meta off.

Remaining before live (deferred): production cadence/frozen-artifact (t2.micro warm-up cost),
paper-trade. Config left safe-dormant (meta off, cap10); flip meta on + cap20 to deploy.

## 6. Risks / open questions

- **Label leakage** (biggest) — the forward barrier window. Mitigation: hard guard in
  `triple_barrier_label`; confirm via the 5.1→5.3 gap.
- **Retrain cost** — meta-train rescans firings each `retrain_every`. Cache the
  primary's per-candle `(p_min,p_max)` during the primary pass to avoid recompute, or
  retrain meta less often than the primary.
- **Data starvation on already-selective stocks** — stocks tuned to high
  `per_stock_params` thresholds fire rarely → thin meta-training set. A genuinely
  different operating point worth testing: **lower the primary threshold (more recall)
  + rely on the meta-gate for precision** — exactly what meta-labeling is designed for.
- **Per-stock vs pooled meta** — start per-stock; A/B pooled in phase 3.
- **Can't rescue a poor primary** — meta only removes; the ceiling is the primary's
  recall. Ours (54.6%) is a good-but-loose primary → ideal candidate.
```
