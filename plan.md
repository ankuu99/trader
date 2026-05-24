# Comprehensive Strategy Evaluation Report

## Part 1 — Diagnostic Framework

Before listing branches, fix the measurement problem. Many of the "things tried" likely failed not because they were wrong but because we couldn't tell.

### Metrics every branch must report (not just total P&L)

| Metric | Why it matters here |
|---|---|
| Avg holding period (in bars) | The "stuck capital" symptom is literally this number being too high |
| % of trades exited via `hold_bars` timeout | If >25%, exits aren't pulling weight |
| Avg gain at peak vs. avg gain at exit | The "give-back ratio" — directly measures missed mini movements |
| Median R-multiple (gain / risk taken) | Replaces win rate as the truth metric |
| Capital turnover per month | If capital is recycled twice as fast, edge can be half as large for same P&L |
| Time spent in "dead trades" (held with \|gain\| < 1 ATR for >40 bars) | Quantifies the user's complaint precisely |
| Distribution of P&L per stock | Reveals if 1-2 stocks are carrying everything |

Without this, every branch below is a coin flip.

---

## Part 2 — The Branch Space

Branches organized by **what they change**. They are largely independent and can be evaluated in parallel by different walk-forward backtests.

### Axis A — Exit logic (highest expected return on time)

**A1. ATR-scaled trailing ladder**
- *Hypothesis:* Fixed-pct trailing (15% activation, 1.5% give-back) is wrong because volatility varies 5-10x across watchlist. ATR-scaled exits capture mini moves on quiet stocks while letting volatile ones breathe.
- *Mechanism:* `trail_activate_atr=1.0` activates trailing when gain ≥ 1 ATR; `trail_give_back_atr=0.7` exits when peak − 0.7 ATR.
- *Effort:* Small (~30 lines in `on_tick`).
- *Risk:* On extremely choppy stocks, may exit too fast. Mitigate with `min_hold_bars_before_trailing`.

**A2. Stagnation exit (volatility-aware)**
- *Hypothesis:* The biggest cost is capital sitting in flat trades. Exit if no movement of N ATR within M bars.
- *Mechanism:* Track `bars_since_last_atr_move`. Exit if it exceeds threshold AND gain < +1 ATR.
- *Effort:* Small.
- *Risk:* Cuts winners that were about to break out. Mitigate by combining with peak_gain — only exit if peak never reached +0.5 ATR.

**A3. Peak-gain give-back exit**
- *Hypothesis:* The single biggest leak is "trade went +5%, came back to +0.5%, exited flat." Track peak-gain; exit when current drops below some fraction.
- *Mechanism:* `if peak_gain >= 2% and current_gain < peak_gain * 0.4: EXIT`.
- *Effort:* Small.
- *Risk:* Triggers on noise during sideways drift. Combine with min `peak_gain` threshold.

**A4. Model-as-exit (continuous regression)**
- *Hypothesis:* The model is the best information we have. Exit on every candle whose forward-return prediction goes negative or below threshold. No fixed pct gates.
- *Mechanism:* Switch to `forward_return` mode; exit when `predicted_return < -ATR_ratio`.
- *Effort:* Medium (mode already exists, but exit policy needs rework).
- *Risk:* Already tried forward_return; if it didn't work it may have been the *exit threshold*, not the model. Worth testing exit decoupled from entry.

**A5. Multi-tier profit-taking**
- *Hypothesis:* Compound mini-movements by exiting partial size at +X ATR, +Y ATR, leaving a runner with trailing.
- *Mechanism:* Split entry into 3 logical positions; exit each at scaled targets.
- *Effort:* Medium (position model needs to track quantities separately). Possibly conflicts with CNC settlement.
- *Risk:* CNC settlement and brokerage cost may erase the gain. Need cost model.

**A6. Multi-timeframe exit**
- *Hypothesis:* Enter on 15min, but exit on 5min for tighter reactivity.
- *Mechanism:* Subscribe to 5min stream; run mini-exit logic (peak-give-back, RSI > 70, EMA cross) at 5min cadence.
- *Effort:* Large (new data pipeline, second feature set).
- *Risk:* Complexity. Two timeframes = two failure modes.

**A7. Time-decay exit pressure**
- *Hypothesis:* Required gain to keep holding should rise with time held.
- *Mechanism:* `required_gain(bars_held) = base_target * decay_factor^bars_held`. After N bars, even small gains trigger exit.
- *Effort:* Small.
- *Risk:* Hand-tuned curve; may exit just before payoff.

---

### Axis B — Entry logic (second highest impact)

**B1. Trend filter (no entries below 50-bar EMA)**
- *Hypothesis:* Catching falling knives is the dominant loss source. EMA50 filter cuts these.
- *Mechanism:* `if close < ema50: skip entry`.
- *Effort:* Tiny (~5 lines).
- *Risk:* Misses reversal trades at true bottoms. Worth measuring tradeoff.

**B2. Bounce confirmation**
- *Hypothesis:* Wait for one confirmation bar before entering. `close > prev_close` filter.
- *Effort:* Tiny.
- *Risk:* Always slips entry by 1 bar — measure cost vs. avoided losses.

**B3. RSI gate**
- *Hypothesis:* Combine ML signal with classical mean-reversion confirmation. Require `RSI < 35` for entry.
- *Effort:* Tiny (RSI already computed).
- *Risk:* Reduces trade count.

**B4. Volume confirmation**
- *Hypothesis:* Local minima with high volume are more reliable. `entry_min_volume_ratio` already exists.
- *Effort:* Tiny (just configure).
- *Risk:* Reduces trade count.

**B5. Multi-bar pattern confirmation**
- *Hypothesis:* Require N consecutive bars in a configuration (e.g. 3 down then 1 up) before entering.
- *Mechanism:* Hard-coded sequence detector before consulting model.
- *Effort:* Small.
- *Risk:* Over-fits to recent regime.

**B6. Meta-labeling (model-of-model)**
- *Hypothesis:* The primary model finds candidates; a secondary model predicts whether to take each. Trained on past primary signals labeled by their outcome.
- *Mechanism:* Two-stage pipeline. Stage 1 = current model. Stage 2 = XGB classifier on `[stage1_proba, regime features, recent vol]` predicting `was_profitable`.
- *Effort:* Medium-large.
- *Risk:* Adds complexity. But this is a research-validated technique (de Prado).

**B7. Regime-conditional entry**
- *Hypothesis:* The model works in trending markets but fails in chop. Gate entries by realized vol regime.
- *Mechanism:* Compute 60-bar return autocorrelation; if mean-reverting regime, block trend-following entries (or vice versa).
- *Effort:* Medium.
- *Risk:* Regime detection is itself noisy.

---

### Axis C — Model / labeling

**C1. Triple-barrier labeling (de Prado)**
- *Hypothesis:* Forward-return labels conflate fast wins with slow ones. Triple-barrier (upper, lower, time barriers) labels each bar with what *would* have happened to a hypothetical trade — directly answering "was this a good entry?"
- *Mechanism:* Each candle gets label ∈ {hit_target, hit_stop, hit_time} based on simulation of next N bars.
- *Effort:* Medium (need to scan future bars during training, careful not to leak).
- *Risk:* Compute-heavy on retrain.

**C2. Per-stock model**
- *Hypothesis:* ABFRL and ATHERENERG don't behave the same way. One global model is biased toward the most-traded names.
- *Mechanism:* Already on `todo_perstockparams.md`. Train one model per instrument.
- *Effort:* Small (model dict already exists; just train per-key).
- *Risk:* Need enough per-stock history (warmup_bars × N stocks of data).

**C3. Walk-forward validation harness**
- *Hypothesis:* All current backtest numbers are suspect because in-sample tuning may overfit. A WF harness with strict purging and embargoes is the gating layer for every other branch.
- *Mechanism:* Already exists (`scripts/walk_forward.py`) — verify it's run for every branch decision.
- *Effort:* Verify, not build.
- *Risk:* May reveal the strategy has no edge.

**C4. Ensemble (rules + ML)**
- *Hypothesis:* Take a signal only when ML and a simple rule (RSI<30 + bounce) agree.
- *Mechanism:* Logical AND on both signals.
- *Effort:* Small.
- *Risk:* Cuts trade count significantly.

**C5. Online learning**
- *Hypothesis:* Full retrain every 25 bars discards recent observations. Incremental updates (SGD classifier) react faster to regime change.
- *Effort:* Medium (replace LR/XGB with `SGDClassifier(partial_fit)`).
- *Risk:* Drifts on noisy days.

**C6. Feature pruning**
- *Hypothesis:* 11 features with 25-50 training samples per retrain = overfitting risk. Pare to 3-4 highest-importance features.
- *Mechanism:* Use feature importance from XGB runs; drop the bottom 7.
- *Effort:* Tiny (config change).
- *Risk:* Loses signal in dropped features.

**C7. Lagged features**
- *Hypothesis:* Current features are all "spot" — they encode the current bar. Adding lagged values (RSI_t-3, slope_t-5) lets the model see trajectories without explicit sequence modeling.
- *Effort:* Small (~15 lines).
- *Risk:* Doubles feature count, worsens overfitting risk.

---

### Axis D — Position sizing & risk

**D1. ATR-scaled position sizing**
- *Hypothesis:* Current sizing uses fixed `max_risk_per_trade` / SL_distance. If SL is ATR-based, sizing automatically scales with volatility — high-vol stocks get smaller positions.
- *Mechanism:* Set `atr_stop_mult: 2.0`. Risk module already uses `sl_distance` for sizing.
- *Effort:* Tiny (config change).
- *Risk:* Smaller positions in high-vol period; may reduce gross P&L.

**D2. Volatility-targeted sizing**
- *Hypothesis:* Each position should contribute roughly equal portfolio variance.
- *Mechanism:* `position_size = target_vol / instrument_vol`.
- *Effort:* Small.
- *Risk:* Vol estimation is noisy.

**D3. Correlation-aware portfolio limit**
- *Hypothesis:* Holding 5 banking stocks is one position with 5 tickets. Limit by sector or correlation.
- *Mechanism:* Reject entries when correlation to existing positions > 0.7.
- *Effort:* Medium (need rolling correlation matrix).
- *Risk:* Reduces diversification of strategy itself.

**D4. Kelly-fraction sizing on edge estimate**
- *Hypothesis:* Use the model's predicted return as edge estimate; size proportionally.
- *Mechanism:* `size_pct = clip(predicted_return / variance, 0, max_pct)`.
- *Effort:* Medium (requires regression mode).
- *Risk:* Kelly is famously aggressive; cap at 0.5x Kelly.

---

### Axis E — Time horizon / regime

**E1. Switch to 5min timeframe**
- *Hypothesis:* On 15min you get ~25 bars/day; mini-movements are by definition sub-bar. Going to 5min triples the resolution.
- *Mechanism:* `candle_timeframe: 5minute`. Adjust hold_bars proportionally.
- *Effort:* Small (config), but full rebacktest required.
- *Risk:* Brokerage costs may dominate. Need cost model.

**E2. Pure intraday strategy**
- *Hypothesis:* Overnight risk is uncompensated. Close all positions by 15:25.
- *Mechanism:* Hard exit at session end.
- *Effort:* Small.
- *Risk:* Cuts off multi-day moves; need MIS product instead of CNC.

**E3. Hold-period bucketing**
- *Hypothesis:* Define separate "fast trade" and "swing trade" sub-strategies with different exit logic, decided at entry by model confidence.
- *Mechanism:* If `predicted_return > 5%`: swing rules. Else: fast rules with tight exits.
- *Effort:* Medium.
- *Risk:* Adds branching complexity.

**E4. Regime-switching strategy**
- *Hypothesis:* Mean-reversion in chop, momentum in trends. Use VIX or NIFTY-slope to switch entry logic.
- *Mechanism:* Two strategy classes, one router.
- *Effort:* Large.
- *Risk:* Regime detection lag.

---

### Axis F — Infrastructure (un-glamorous but high-leverage) --> USER MARKED AS NOT PRIORITY AS REMOTE SERVER ALREADY PROVIDES GOOD ENOUGH METRICS AND COVERAGE, IF YOU ARE LLM IGNORE AXIS F

**F1. Enable GTT broker-side stops**
- *Hypothesis:* `gtt_enabled: false` means a process crash = no stop. The catch-up logic only helps on restart.
- *Effort:* Tiny (config flip + verify OCO logic).
- *Risk:* GTT rate-limits; ensure clean cancel-on-exit.

**F2. Process supervisor + dead-man's switch**
- *Hypothesis:* Single-process crash = silent failure. Add systemd + Telegram alert if no candle received in 30 min during market hours.
- *Effort:* Small (systemd unit + heartbeat check).
- *Risk:* None.

**F3. Cost model in backtest**
- *Hypothesis:* Current backtest underestimates cost. Real edge after Zerodha brokerage + STT + slippage may be negative on mini-movement strategies.
- *Mechanism:* `trader/costs.py` exists; verify it's applied in `backtest.py`.
- *Effort:* Verify, not build.
- *Risk:* May reveal mini-movement branches are uneconomic — actually critical to know early.

**F4. Token refresh fail-loud**
- *Hypothesis:* TOTP refresh fail at night = bot starts dead next morning. Add pre-market token validation that alerts.
- *Effort:* Small.
- *Risk:* None.

---

### Axis G — Strategy alternatives (parallel tracks)

**G1. Pure rule-based baseline (no ML)**
- *Hypothesis:* The ML model may not be adding edge over a rule (`RSI<30 + close>prev_close + above EMA50`). Build this as a baseline. If ML doesn't beat it on equal cost basis, drop ML.
- *Effort:* Small (~150 lines new strategy class).
- *Risk:* May discover the ML model is worthless. Or may discover it's gold and you didn't know.

**G2. Pairs / sector-relative strategy**
- *Hypothesis:* Long when stock is oversold vs. its sector index. Reduces directional market exposure.
- *Effort:* Large (need sector data, peer mapping).
- *Risk:* New data dependency.

**G3. Opening-range breakout (intraday)**
- *Hypothesis:* First 30 min defines a range; breakout in either direction with stop on opposite side.
- *Effort:* Medium.
- *Risk:* Different beast — own strategy class.

**G4. Cap-and-collect (mean-reversion to VWAP)**
- *Hypothesis:* Buy when price > 2σ below intraday VWAP, exit on VWAP touch.
- *Effort:* Medium.
- *Risk:* Falling-knife risk; needs trend filter overlay.

---

## Part 3 — Prioritization Matrix

| Branch | Effort | Expected ROI | Independence | Suggested order |
|---|---|---|---|---|
| C3 (WF harness verify) | Tiny | Gating for all | Standalone | **Do first** |
| A1 + A2 + A3 combined | Small | High | Together = "new exit ladder" | **Do second** |
| B1 (trend filter) | Tiny | Medium-high | Standalone | **Do second** |
| D1 (ATR sizing) | Tiny | Medium | Standalone | **Do second** |
| C6 (feature pruning) | Tiny | Medium | Standalone | Third |
| C2 (per-stock model) | Small | Medium-high | Standalone | Third |
| A4 (model-as-exit) | Medium | Unknown | Needs regression mode | Fourth |
| G1 (rule-based baseline) | Small | High info value | Standalone | Fourth |
| C1 (triple-barrier) | Medium | High | Independent | Fifth |
| B6 (meta-labeling) | Large | High | Standalone | Later |
| E1 (5min timeframe) | Small effort, large rebacktest | Unknown | Standalone | Later |
| E4 (regime-switching) | Large | High | Architectural | Later |
| A6 (multi-timeframe exit) | Large | Medium | Architectural | Later |

---

## Part 4 — What to Avoid Doing Again

Based on the git history, these have been tried and didn't stick. Don't re-attempt without a new angle:

- **Plain `forward_return` regression as both entry and exit** (already in code, currently inactive). The mode itself is fine; what to try differently is **A4: decouple exit policy from the prediction sign** (e.g. require persistent negative prediction for N bars before exiting).
- **Naive XGBoost classifier replacement of LR** — the win comes from labeling (C1) and meta-labeling (B6), not the classifier choice.
- **Generic flat/stagnant exit on bar count** (reverted on release_branch). The reason it doesn't work is it's not volatility-aware. A2 fixes by scaling with ATR.

---

## Part 5 — Suggested First Sprint

Three independent tasks, each shippable in a session:

1. **Sprint task 1 — Gating fixes** (measurement harness in Part 1). Unblocks honest evaluation of everything else.

2. **Sprint task 2 — New exit ladder** (A1 + A2 + A3 as one coherent rework of `on_tick` + new candle-based exits in `on_candle`). Directly targets the stated "stuck capital" complaint. Pair with D1 (ATR sizing) since both want ATR everywhere.

3. **Sprint task 3 — Rule-based baseline** (G1). Until we know whether the ML adds edge over `RSI<30 + bounce + trend filter`, all branches in axis C are noise.

After sprint 1 finishes, the data tells you which axis to deepen: if cost model reveals fees dominate, drop mini-movement axis entirely; if the new exit ladder fixes hold-time, go to B1+B6; if baseline beats ML, kill the ML and tune the rules.
