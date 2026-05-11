Yes. There are several things in this strategy that are either:

* statistically weak
* redundant
* dangerous
* internally contradictory
* or classic “backtest patch” parameters.

Some should be removed immediately.
Others should be replaced later after infrastructure improves.

---

# REMOVE IMMEDIATELY

These are likely harming the strategy today.

---

# 1. REMOVE `min_hold_before_exit`

Current:

```yaml id="4rxm7k"
min_hold_before_exit: 150
```

Reason:

* arbitrary
* horizon mismatch
* redundant due to `sell_min_pct`
* suppresses alpha.

Action:

```yaml id="kzz1ws"
REMOVE
```

or reduce to:

```yaml id="trtmsp"
8–12
```

---

# 2. REMOVE `trail_pct: 0.25`

This is one of the biggest problems.

Current:

```yaml id="00spx2"
trail_pct: 0.25
```

This is:

* absurdly tight
* below normal noise
* guarantees premature exits.

On 15m timeframe:
0.25% is random fluctuation.

---

## What Happens

Trade reaches:

```text id="w2rl8g"
+20%
```

Trailing activates.

Then:

```text id="f1n1l5"
0.3% pullback
```

immediately exits trade.

This is not trailing.
This is noise harvesting.

---

## Action

Either:

### REMOVE trailing entirely initially

OR

Replace with:

```yaml id="5n7vce"
trail_pct: 2.5
```

or ATR-based trailing:

```text id="qkz0c0"
2 × ATR
```

ATR trailing is much better.

---

# 3. REMOVE `profit_pct: 20`

Current:

```yaml id="rvotj8"
profit_pct: 20
```

This means:

* trailing only activates after +20%.

For 15m swing strategy:

* too large
* unrealistic
* delays protection excessively.

This likely came from:

> trying to avoid premature trailing exits.

because:

```yaml id="nlk79o"
trail_pct = 0.25
```

was broken.

These two params are compensating for each other.

Classic sign of unstable optimization.

---

## Action

Remove both:

```yaml id="2c5mmt"
profit_pct
trail_pct
```

Replace later with:

* ATR trailing
* volatility-adjusted exits.

---

# 4. REMOVE `veto_threshold`

Current:

```yaml id="h5z6bp"
veto_threshold: 0.4
```

This is mathematically suspicious.

You are saying:

```text id="1v2trj"
Enter if:
P(min) high

BUT reject if:
P(max) moderately high
```

Problem:
Logistic regression probabilities here are NOT calibrated.

Also:

```text id="5x6zcs"
P(min) + P(max) = 1
```

in binary classification.

So this logic is partially redundant.

---

## Example

If:

```text id="nysv6h"
P(min)=0.85
```

then:

```text id="ttb5jf"
P(max)=0.15
```

naturally.

The veto adds little value.

---

## Action

REMOVE:

```yaml id="24c2p3"
veto_threshold
```

until probability calibration exists.

---

# 5. REMOVE `entry_min_volume_ratio: 2`

Current:

```yaml id="u0jzvg"
entry_min_volume_ratio: 2
```

This is probably filtering out:

* genuine exhaustion bottoms
* quiet accumulation
* low-volatility reversals.

You are biasing entries toward:

* panic spikes
* news candles
* high volatility events.

That may actually worsen mean-reversion quality.

---

## Action

REMOVE initially.

Later:
replace with:

* smarter liquidity filters
* relative-volume features
  NOT hard gates.

---

# 6. REMOVE `entry_require_prior_decline`

Currently:

```yaml id="q7f75h"
entry_require_prior_decline: false
```

Good that it's disabled.

Do not enable this.

Why?

Because:

```text id="tz2g4d"
20-bar slope < 0
```

is an extremely naive definition of decline.

This becomes:

* overconstrained
* fragile.

---

# THINGS TO REPLACE (NOT JUST REMOVE)

---

# 7. REPLACE Fixed Stop Loss

Current:

```yaml id="vyy1mb"
stop_pct: 20
```

This is dangerous.

Do NOT use fixed % stops across:

* all stocks
* all volatility regimes.

---

## Replace with

ATR stop:

```text id="6n6zfe"
stop = entry - (2 × ATR)
```

Much more robust.

---

# 8. REPLACE `hold_bars: 400`

Current:

```yaml id="78s9wi"
hold_bars: 400
```

~12–15 trading days.

Again:

* feature horizon mismatch.

---

## Replace With

Dynamic timeout based on:

* prediction horizon
* volatility
* trend strength.

Initially:

```yaml id="hdbksh"
48–96 bars
```

is far more reasonable.

---

# 9. REPLACE Logistic Regression Probabilities

Current:

```python id="xg47ry"
predict_proba()
```

These are NOT reliable confidence estimates.

---

## Replace with:

* calibrated probabilities
* isotonic regression
* Platt scaling.

Until then:

* do NOT overtrust thresholds.

---

# 10. REPLACE Binary Extrema Framing Entirely

This is the biggest future rewrite.

Remove conceptually:

```text id="9q7x7q"
local minima
local maxima
```

Replace with:

```text id="w6oc2h"
future return distribution
```

This changes the entire research quality.

---

# THINGS THAT ARE ACTUALLY GOOD

Do NOT remove these yet.

---

# Good #1 — Rolling Retraining Concept

Good idea.

But:

```yaml id="k9sh2x"
retrain_every: 25
```

is probably too frequent.

Later:

* retrain daily
  or
* weekly.

---

# Good #2 — Using Returns Instead of Raw Prices

Excellent decision.

This is actually quant-aware.

Good:

```python id="j4nj10"
returns
```

instead of:

```text id="2om5cb"
absolute prices
```

Keep this concept.

---

# Good #3 — Separate Tick/Candle Logic

Very good architecture.

Keep:

* entries on candles
* exits on tick.

Professional structure.

---

# Good #4 — Warmup + Rolling Window

Keep.

But later:
increase dataset size massively.

---

# PARAMETERS THAT SMELL LIKE OVERFITTING

These specifically look suspicious:

| Parameter                   | Why Suspicious         |
| --------------------------- | ---------------------- |
| `threshold: 0.85`           | likely tuned           |
| `sell_threshold: 0.80`      | likely tuned           |
| `profit_pct: 20`            | compensating parameter |
| `trail_pct: 0.25`           | unrealistic            |
| `min_hold_before_exit: 150` | patch parameter        |
| `stop_pct: 20`              | arbitrary              |
| `hold_bars: 400`            | arbitrary              |

These are likely:

* backtest artifacts
* not robust edges.

---

# SIMPLE IMMEDIATE CLEANUP VERSION

If I had to minimally clean current strategy TODAY:

---

# REMOVE

```yaml id="5j7u4r"
min_hold_before_exit
profit_pct
trail_pct
veto_threshold
entry_min_volume_ratio
```

---

# CHANGE

```yaml id="n2xg84"
stop_pct: 5
hold_bars: 72
sell_min_pct: 4
```

---

# KEEP TEMPORARILY

```yaml id="zy6e7u"
threshold
sell_threshold
warmup_bars
lookback_bars
```

until label redesign is complete.

---

# MOST IMPORTANT THING

Do NOT compensate for weak labels using:

* extra thresholds
* hold locks
* weird filters
* arbitrary delays.

That is how quant systems become:

```text id="jlwmvf"
fragile
complex
uninterpretable
overfit
```

A good quant strategy should become:

* simpler
* cleaner
* more explainable

as research improves.
