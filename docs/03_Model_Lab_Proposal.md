# Model Lab — a vanilla turning-point framework outside LR-Extrema (proposal, 2026-10-18)

**Status: BRAINSTORM, owner review pending (TD-021).** Nothing is built until the owner signs off on the open
questions at the end.

## Why

Round 1 of the detection campaign (TD-018, `reviews/extrema_campaign/CAMPAIGN_ROUND1_20261018.md`) tested 12 ideas, and
none beat the production entry model. The owner's critique (2026-10-18), recorded here because it is correct: every
one of those ideas lived **inside LR-Extrema's construct**:

- one model per stock;
- a ~1,200-bar rolling training window (≈ 7 weeks of 15m bars);
- labels that mark only the extreme bars of a fixed-order window;
- a probability threshold tuned to the logistic scale;
- features computed by the strategy's own pipeline.

Round 1 therefore shows that *tweaks to that construct* don't help. It does not show that no model can find turning
points better. The coin-flip controls (EXP-20/22) also do NOT say the model is a coin. Its **entry** signal beats
random entries clearly (₹439k vs ₹158–389k, drawdown 5.8 % vs 8–13 %, weighted win 63.9 % vs 55–61 %). Only its
**pattern-top** signal is no better than a coin at the same rate.

## Nomenclature (owner, 2026-10-18)

- **Model** — the mathematical / ML tool that looks at the data up to candle *t* and says whether *t* is a good entry
  (local min) or exit (local max) point, and how big the coming move is.
- **Strategy** — everything around it: stop loss, target, trailing, stale/early exits, minimum hold, scale-in/out,
  risk sizing, capital limits.

The lab evaluates **models only**, with the strategy held fixed. A model graduates to the strategy only after it wins
in the lab.

## The framework

### 1. Data (read-only reuse of the current stack)

Use the existing candle cache and fetchers only, never the strategy code.

| Series | Depth in `data/market.db` today |
|---|---|
| 15m OHLCV, 105 NSE stocks | 22 stocks from 2017–19, 5 from 2021, 50 from 2023, 28 from 2024+ |
| Daily OHLCV, 532 stocks | from 2023-06 |
| Nifty 50 + India VIX 15m | 2019-06 → 2026-10-16 (backfilled in TD-018) |

Daily history can be fetched further back from Kite (pre-authorised) if the owner wants a longer daily panel.

### 2. Factor library: every candle property is its own time series

All factors are strictly causal (computed from bars ≤ *t*) and live in one table: `(stock, timestamp) → factor
columns`.

- **Raw:** open, high, low, close, volume; gap from the previous close.
- **Shape:** body, upper and lower wick, close location in the range, range / ATR.
- **Returns:** many horizons (1, 4, 16, 64, 256 bars), plus log-return z-scores.
- **Position:** distance to the rolling min/max over many windows (20 … 1,000 bars); drawdown from high; days since the
  last N-bar low; RSI / stochastic-type oscillators.
- **Volatility:** realised volatility at several horizons; vol-of-vol; ATR.
- **Volume:** relative volume, volume z-score, up-volume vs down-volume, volume at the low.
- **Multi-timeframe:** the same factors on 1h / day bars, broadcast to each 15m bar (only completed bars).
- **Calendar:** time of day, day of week, days to month-end / expiry.
- **Market:** Nifty and VIX returns, drawdown and percentile; the stock's beta and residual vs Nifty.
- **Cross-section:** the stock's return rank among the panel at that bar; sector/peer moves where available.
- **Sequences:** raw windows of the last *L* bars, for sequence models.

### 3. Targets (hindsight labels, used only for training and scoring)

The owner's three questions, each as its own target:

| Question | Target(s) |
|---|---|
| Is candle *t* a potential min (or max)? | **T1** — *t* is the lowest low within ±*w* bars (several *w*), or a zigzag pivot with a ≥ *k*·σ reversal; same for max |
| Will the direction change? | **T2** — sign of the trend after *t* vs before *t* over *h* bars (with a dead-band) |
| By how much? | **T3** — maximum favourable excursion (largest rise from close[*t*] over the next *H* bars) and maximum adverse excursion before it; also the size of the move to the next opposite pivot |

T3 matters most for money. Round 1 showed that a dip which turns but first falls another 5 % is killed by the
strategy's exits, so T3 includes the adverse excursion, not just the rise.

### 4. Protocol: train on the past, predict the future point by point

- **Chronological split:**
  - train on the first part of history;
  - validate on the next part;
  - keep a final test period **untouched** until a model is frozen (e.g. train ≤ 2022, validate 2023, test
    2024-01 → 2026-10).
- **Walk-forward:**
  - at each test bar, the model sees only bars ≤ *t*;
  - retrain on a schedule (e.g. monthly), with an embargo equal to the label horizon, because a label at *t* needs bars
    up to *t*+*w* (López de Prado, purged walk-forward).
- **Pooled across stocks** by default (one model learns from all names, with time-aligned splits so no stock leaks
  the future of another), plus per-stock variants for comparison.
- **Held-out stocks:** also score on names never seen in training, to test generality and reduce the watchlist's
  hindsight bias.

### 5. Model ladder (cheap to expensive)

1. **Naive baselines:**
   - a coin at the same firing rate;
   - lowest-of-N;
   - RSI;
   - **the production LR-Extrema P(min) scores** (cached by TD-018), the bar to beat.
2. Pooled logistic regression on the factor library.
3. Gradient-boosted trees (sklearn HistGradientBoosting and xgboost are installed). Multi-task: classifier for
   T1/T2, quantile regressors for T3.
4. Sequence models (1D-CNN / TCN / LSTM / small transformer) on raw windows. These need `torch`, which is not
   installed.
5. Optional later: pretrained time-series foundation models used as feature extractors.

### 6. Scoring: model-only but money-aware

Round 1's lesson: a ranking metric (AUC) did not track money. So the lab scores what a fired candle would have been
worth, across a **grid** of exit rules rather than the current one:

- **Detection:**
  - precision / recall at a fixed firing rate (matched to production);
  - PR-AUC;
  - how far the signal is from the true trough (in bars and in %);
  - lateness.
- **Magnitude:**
  - rank correlation of predicted vs realised MFE/MAE;
  - calibration of the predicted move.
- **Payoff of fired candles:**
  - forward return at 1d / 3d / 5d / 10d;
  - P(+X % before −Y %) on a grid of X and Y;
  - mean MFE/MAE.

  Each is measured vs the production model's fired candles and vs a coin at the same rate.

**Gate to the strategy:** a model must beat the production P(min) on the payoff of its top-k fired candles in the
untouched test period, on most stocks. Then it goes through the existing Stage B (full backtest, pass rule + crash
guard, weighted win % reported).

### 7. Integration path (only for a winner)

A pooled, pretrained model is outside today's per-stock `ExtremaModel` contract (inventory §1: no save/load, every boot
retrains). A winner needs:

- an adapter model type that loads a pretrained artefact and computes the lab's factors live;
- an offline (re)training job;
- a t2.micro inference budget check;
- re-calibration of the thresholds.

That is a spec-first build (`to_develop/`), only after a lab win.

### 8. Traps to design out from day one

- **Look-ahead:**
  - centred smoothing;
  - normalising with full-sample statistics;
  - labels leaking into features;
  - cross-stock same-timestamp leakage in pooled splits.
- **Overlapping labels:** neighbouring bars share outcomes, so use sample weights and an embargo.
- **Multiple testing:** register the arms and the test window before looking; the test set is opened once per frozen
  model.
- **Survivorship and hindsight:** the 21 watchlist names were chosen knowing 2023–26 outcomes, so use the 105-stock
  panel for training and scoring.
- **Realism:** the decision is made at bar close and filled at the next open; costs are ~0.22 % per round trip.

## Proposed phases

| Phase | Deliverable | Rough size |
|---|---|---|
| L0 | Data loader + factor library + target builders + leakage tests | 1–2 days |
| L1 | Walk-forward harness + scoring report; baselines incl. production P(min) | 1–2 days |
| L2 | Pooled logistic + GBDT (multi-target) on 15m and day | 1 day + compute |
| L3 | Sequence models (needs torch) | 2–3 days + compute |
| L4 | Winner → adapter spec → Stage B → paper | only on a lab win |

## Open questions for the owner

1. **Universe:** all 105 stocks with 15m data (recommended), or the 21 watchlist names?
2. **Timeframe first:** 15m (most live names), daily, or both from L1?
3. **Definition of a min/max:** a ±*w*-bar window, a %-reversal zigzag, or both (recommended: both, scored
   separately)?
4. **Split dates:** train ≤ 2022 / validate 2023 / test 2024-01 → 2026-10?
5. **Install `torch`** (and optionally `lightgbm`) into `.venv` for L3?
