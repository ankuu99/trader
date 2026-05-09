# LR Extrema Strategy Refactor Roadmap

## Objective

Transform the current extrema-based prototype into a statistically robust, production-grade swing trading research system through incremental, testable upgrades.

The key requirement:
> Every change must be independently backtested and validated before moving to the next stage.

---

# Guiding Principles

## Core Rules

### 1. No future leakage
Any feature/label must only use information available at prediction time.

### 2. Every change must be measurable
Each feature addition must answer:

- Did Sharpe improve?
- Did CAGR improve?
- Did drawdown improve?
- Did stability improve?

### 3. One variable at a time
Never change:
- labels
- exits
- features
- models

all at once.

### 4. Walk-forward only
Use:
- train past
- predict future
- roll forward

Never random splits.

### 5. Preserve reproducibility
Every experiment must save:
- config snapshot
- git hash
- metrics
- trades
- feature list

---

# Target Architecture

```text
Market Data
    ↓
Feature Pipeline
    ↓
Label Generator
    ↓
Walk Forward Trainer
    ↓
Model
    ↓
Signal Engine
    ↓
Risk Engine
    ↓
Portfolio Manager
    ↓
Execution Simulator
    ↓
Analytics
```

---

# Phase 0 — Research Infrastructure

## Step 0.1 — Experiment Tracking

### Tasks
Create:

```text
research/
    experiments/
    reports/
    configs/
    results/
```

Each run should save:

```json
{
  "experiment_id": "...",
  "timestamp": "...",
  "git_commit": "...",
  "config": {...},
  "metrics": {...}
}
```

---

## Step 0.2 — Standard Metrics

### Return Metrics
- CAGR
- Total return
- Average trade return

### Risk Metrics
- Max drawdown
- Volatility
- Downside deviation

### Quality Metrics
- Sharpe ratio
- Sortino ratio
- Calmar ratio

### Trade Metrics
- Win rate
- Profit factor
- Avg winner
- Avg loser
- Expectancy

### Stability Metrics
- Rolling Sharpe
- Monthly returns
- Equity smoothness

---

## Step 0.3 — Slippage and Costs

Add:
- brokerage
- spread
- slippage
- overnight gap simulation

Recommended:
- 5–20bps liquid
- 20–100bps illiquid

---

## Step 0.4 — Walk Forward Backtesting

Required structure:

```text
Train Jan-Feb
Test  Mar

Train Jan-Mar
Test  Apr
```

No random splits.

---

## Step 0.5 — Save Predictions

Persist:
- timestamp
- features
- prediction
- probability
- actual outcome
- trade result

---

# Phase 1 — Replace Extrema Labels

## Step 1.1 — Remove Extrema Logic

Delete:
- `_find_local_extrema()`

Stop using:
- local minima
- local maxima

---

## Step 1.2 — Future Return Labels

New label:

```python
future_return = (
    future_close - current_close
) / current_close
```

---

## Step 1.3 — Multi Horizon Labels

Example:

```yaml
prediction_horizons:
  - 12
  - 24
  - 48
```

---

## Step 1.4 — Binary Classification

BUY class:

```text
future_return > +4%
```

NO BUY:
- everything else

---

## Step 1.5 — Triple Barrier Labels

Recommended institutional approach.

Barriers:
- +5% target
- -2% stop
- timeout

Labels:
- +1 target hit first
- -1 stop hit first
- 0 timeout

---

## Step 1.6 — Class Balancing

Add:
```python
class_weight="balanced"
```

Reject training if:
- minority class < 10%

---

# Phase 2 — Feature Engineering

## Step 2.1 — Modular Feature Pipeline

Refactor:

```python
_compute_features()
```

into:

```text
features/
    trend.py
    volatility.py
    momentum.py
    volume.py
    market.py
```

---

## Step 2.2 — Trend Features

Add:
- EMA20
- EMA50
- EMA spread
- distance from EMA

Example:

```text
(close - ema20) / ATR
```

---

## Step 2.3 — Volatility Features

Add:
- ATR
- realized volatility
- rolling stddev

Normalize all features by ATR.

---

## Step 2.4 — Mean Reversion Features

Add:
- RSI
- Bollinger z-score
- VWAP distance
- rolling percentile

---

## Step 2.5 — Volume Features

Add:
- relative volume
- OBV
- accumulation/distribution
- volume trend

---

## Step 2.6 — Candle Structure

Add:
- wick %
- body %
- engulfing patterns
- inside bars

---

## Step 2.7 — Market Regime

Add:
- NIFTY trend
- BANKNIFTY trend
- India VIX
- sector trend

---

## Step 2.8 — Cross Sectional Features

Examples:
- stock vs sector return
- momentum rank

---

# Phase 3 — Model Improvements

## Step 3.1 — Benchmark Strategies

Implement:
- EMA crossover
- RSI mean reversion
- Bollinger reversion

Compare ML vs simple systems.

---

## Step 3.2 — Proper ML Pipelines

Use sklearn Pipeline:

```python
Pipeline([
  scaler,
  model
])
```

---

## Step 3.3 — Probability Calibration

Use:
- isotonic calibration
- Platt scaling

---

## Step 3.4 — Tree Models

Test:
- RandomForest
- XGBoost
- LightGBM

Avoid deep learning initially.

---

## Step 3.5 — Feature Importance

Track:
- SHAP values
- feature importance
- coefficient drift

---

## Step 3.6 — Ensemble Models

Combine:
- trend
- mean reversion
- breakout

---

# Phase 4 — Risk Engine Rewrite

## Step 4.1 — ATR Stops

Replace:

```yaml
stop_pct: 20
```

with:

```text
stop = entry - 2 * ATR
```

---

## Step 4.2 — Volatility Position Sizing

Formula:

```text
position_size =
(account_risk)
/
(stop_distance)
```

---

## Step 4.3 — Portfolio Heat

Add:
```text
max_total_risk = 6%
```

---

## Step 4.4 — Correlation Controls

Avoid excessive sector concentration.

Examples:
- max 2 PSU banks
- max 2 chemical stocks

---

## Step 4.5 — Regime Shutdown

Disable trading during:
- crash conditions
- high VIX
- abnormal spreads

---

# Phase 5 — Execution Realism

## Step 5.1 — Liquidity Filters

Reject stocks with:
- low traded value
- poor liquidity

Suggested:
- minimum ₹10 crore/day traded value

---

## Step 5.2 — Gap Handling

Backtester must simulate:
- overnight gaps
- stop slippage
- open auction fills

---

## Step 5.3 — Partial Fills

Optional later enhancement.

---

## Step 5.4 — Market Impact

Estimate:

```text
slippage ∝ order_size / average_volume
```

---

# Phase 6 — Validation

## Step 6.1 — Parameter Sensitivity

Test:
- threshold
- ATR multiplier
- holding period
- prediction horizon

Look for:
- broad stable regions

Avoid:
- narrow optimized peaks

---

## Step 6.2 — Monte Carlo Resampling

Stress test:
- missing trades
- slippage changes
- random trade order

---

## Step 6.3 — Regime Analysis

Measure separately:
- bull markets
- bear markets
- sideways markets
- high volatility periods

---

## Step 6.4 — Feature Stability

Monitor:
- feature drift
- importance decay
- coefficient instability

---

## Step 6.5 — Paper Trading

Run:
- 1–2 months paper trading

Compare:
- expected vs actual slippage
- predicted vs realized outcomes

---

# Phase 7 — Productionization

## Step 7.1 — Model Registry

Store:
- model version
- feature schema
- training window

---

## Step 7.2 — Controlled Retraining

Prefer:
- daily retrain
or
- weekly retrain

Avoid:
- retraining every 25 candles

---

## Step 7.3 — Drift Detection

Monitor:
- feature distributions
- prediction distributions

Alert on abnormalities.

---

## Step 7.4 — Kill Switches

Disable trading automatically on:
- excessive drawdown
- abnormal slippage
- crash conditions

---

# Recommended Execution Order

## Stage A — Infrastructure
1. experiment tracking
2. metrics
3. slippage
4. walk-forward backtesting

---

## Stage B — Labels
5. remove extrema labels
6. future return labels
7. triple barrier labels

---

## Stage C — Features
8. ATR
9. RSI
10. EMA features
11. Bollinger z-score
12. market regime

---

## Stage D — Models
13. calibrated LR
14. RandomForest
15. XGBoost

---

## Stage E — Risk
16. ATR stops
17. volatility sizing
18. portfolio heat

---

## Stage F — Robustness
19. parameter stability
20. Monte Carlo testing
21. paper trading

---

# Success Criteria

| Metric | Target |
|---|---|
| Sharpe | > 1.5 |
| Max Drawdown | < 15% |
| Profit Factor | > 1.3 |
| Stability | Smooth |
| Regime Consistency | High |

---

# Most Important Insight

The single biggest improvement is:

> moving from hindsight extrema classification to forward-return prediction using proper walk-forward validation.

This matters more than:
- fancy ML
- more features
- deep learning
- hyperparameter tuning
