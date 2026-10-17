# Trough/peak model research — inventory & starting point (2026-10-18)

Owner's question (2026-10-18): *"we are actually missing really good troughs as entries"* — revisit the
trough/peak detection model. This note records (1) how swappable the model is today, (2) what our own past
research already established, (3) every detection idea built or designed on other branches, (4) the external
reading list, and (5) a backtest-realism gap found on the way (ISS-14). It is the baseline document for the
evaluation campaign that follows — every path taken from here gets appended to it or to a linked review.

---

## 1. Can we just swap the model? (coupling assessment)

**Yes, if the replacement fits the contract.** Three plug points, each an interface + registry + nested config
block; `trader/strategies/lr_extrema.py` touches them only through the builders:

| Plug point | Interface | Config key | Registered today |
|---|---|---|---|
| Model | `ExtremaModel` (`trader/models/base.py`): `fit(X,y)`, `predict_proba(x) → (p_min, p_max)`, `is_trained` | `model.type` | logistic, gbdt, mlp |
| Features | `FeaturePipeline` (`trader/features/base.py`): `compute(candles) → vector`, `min_history`, `feature_names` | `features.type` | extrema, extrema_regime, swing, window |
| Labels | `Labeler` (`trader/features/labels.py`): `label(candles) → (indices, classes)` | `labels.type` | extrema, trend_scan, zigzag, avg_trend (+ neutral) |

A new per-stock classifier / feature set / labeler = one new file + one registry line + a config value.

**Coupling that remains:**
1. **Calibration (the real cost).** Global `threshold: 0.90` and every per-stock `threshold` / `sell_threshold` /
   `veto_threshold` are tuned to the logistic probability scale. A new model ⇒ re-sweep all of them.
2. **The model drives exits too.** `trader/policy/extrema_exit.py:269-291` reads P(max) for pattern-top + scale-out
   and P(min) for momentum_decay. Swapping the model changes exits, not just entries.
3. **Private-attribute reach-ins** (work, but brittle): `extrema_exit.py` calls `strat._model` / `strat._features`;
   `scripts/ui.py:220-246` re-implements the train loop; `scripts/replay_strategy.py`.
4. **Positional entry gates** — `ExtremaEntryPolicy` reads `x[0]`, `x[1]`, `x[5]` assuming the extrema layout.
   All disabled in config (latent).
5. Meta filter consumes p_min/p_max as features (disabled).

**Outside the contract (needs a refactor spec first):** pooled / cross-stock or offline-pretrained models (no
save/load hook; every boot retrains from scratch); outputs other than (p_min, p_max) (regression, EV, ranking,
explicit neutral — the neutral class is silently dropped today); heavy models on the t2.micro (`_train()`
recomputes features per labelled index in a Python loop — unmeasured cost for dense labels × long windows);
a model that decides entry timing itself (threshold/veto lives in the strategy).

---

## 2. What our own research already established

Read before proposing anything:

- **`reviews/ather_minima_diagnosis_20260927.md`** — the key document.
  - P(min) is a "bar closed at its low" detector: `norm_price` corr −0.82 with P(min) but AUC 0.49 alone for dip
    proximity. Against 191 hand-labelled ATHERENERG dips: AUC 0.54, recall 27 % / precision 38 % at 0.90.
  - Univariate swing measures beat the model: RSI14 0.69, % above 20-bar low 0.68, 20-bar return 0.68, depth 0.65.
  - Mechanism: min-vs-max labels are trivially separable by "did the bar fall" → the model learns bar direction,
    not swing position. P(min) peaks ON the dip bar (0.77) then 0.38 on the reversal bar — the missed population.
  - None of collapse_ties / neutral / extrema_order / lookback 3000 / retrain 5 / regime feats / zigzag / gbdt
    moved the ranking.
  - **The twist:** `features.type: swing` lifted detection (38/27 → 48/42 %) and LOST money (portfolio
    ₹498k/Calmar 5.50 → ₹391k/3.46). Extra catches were shallow 2–3 % dips that tier-1 stale kills before the +7 %
    trail. Earlier trail arming (+3 %) also falsified.
- **`/missed-opportunities` 2026-08-16** (memory: missed-opportunities-skill) — 187/210 dips "missed", but:
  no_score 85 (500-row model_scores trim artifact), in_position 49, blocked 10, **below_threshold only 43**.
- `reviews/dayw_candidate_proposal_20260713.md` — regime-campaign winner (zigzag vol-scaled + neutral +
  extrema_regime + gbdt on day TF, Calmar 2.11, 6/7 windows). Not deployed.
- `avg_trend_paper_plan.md` — dense regime labels flip ~window/2 bars past the turn (structural lag).
- `meta_labeling_learnings.md` / `neutral_class_learnings.md` — secondary veto and neutral class didn't pay.
- Knife-regime entry gate NULL (knife-state entries are the best bucket); per-name loss budget FALSIFIED.

**Working conclusion:** the target is not "a trough" but *"a trough that bounces ≥ profit_pct before our
stale/stop exits fire"*. Nothing trains on that today: `triple_barrier_label` (`labels.py:402`) exists but only
the meta filter uses it; `forward_label` (closest) is disabled.

---

## 3. Detection ideas on other branches

Inventory of 2026-10-18. `better_ui` (916b624) is fully contained in HEAD; `main` differs only by two EC2-schedule
commits; `release_candidate` (06f6573) is risk-only (`sl_cooldown_bars`, author noted "still not working").
**No branch result is trustworthy as-is** — all pre-date per-stock params, the reject-freeze engine fix
(2026-10-16), and `simple_trader`'s gates were mis-indexed under `feature_indices`.

### 3a. Built in code, not in HEAD

| Idea | Branch @ ref | Mechanism | Recorded result |
|---|---|---|---|
| Triple-barrier **primary** labels | simple_trader_buy_low_strategy @ d5928b5 (`label_mode: triple_barrier`, `barrier_target_pct/stop_pct/window`) | label = 1 if +target before −stop within window | never enabled |
| Lag stacking | same, 3af0607 (`feature_lag_periods: [1,2]`) | append t-1, t-2 feature vectors | active on branch, no number |
| `ema20_dist` | same, 023897c | (close − EMA20) / ATR | survived XGB-importance pruning (top 4); used ATR(250) |
| Nifty slope20 / VIX/30 features | same | market context per candle | pruned. HEAD engine injects `_nifty_close`/`_vix_close` (`engine.py:385`) — unread; no live wiring |
| `atr_ratio`, Wilder RSI features | same; also release_branch 71fdcf9 (reverted 7ff6184, no reason recorded) | ATR/close; RSI | pruned. HEAD has SMA-RSI in `swing_features.py` |
| Feature pruning by index | same (`feature_indices: [1,3,4,8]`) | subset selection | active |
| Forward-return regression | same, 1d4ceea → reverted d634c84 (58 min later) | XGBRegressor on 96-bar return, enter if ≥ min | **untested, not falsified** |
| xgboost / sgd primary model | same, d634c84 → 471b9c1 back to lr | — | reverted, no number |
| Rules baseline | same (`model_type: rules`) | RSI14<35 + bounce + close>EMA50, no ML | never run |
| Bounce gate / EMA50 gate / autocorr regime gate | same (`entry_require_bounce`, `entry_ema_filter_period`, `regime_autocorr_*`) | confirmation / trend / regime filters | EMA50 active, others off |
| Exits: stagnation (ATR), peak give-back, ATR trail, time decay, model exit, hold bucketing | same | — | mixed, no numbers |
| DD circuit breaker | same (`dd_circuit_breaker_pct` 20/15) | portfolio halt | active, no number |
| EMA-above-and-rising gate | handle_trailing @ 52a5d93 (`ema_gate_*`) | close > EMA(25), rising 20 bars | kept on in the branch's 150 %/65.7 % WR baseline |
| 60-min calibration | handle_trailing a445c33 (`config_60min_calibrated.yaml`) | extrema_order 5, thr 0.80, profit 15, stop 20, hold 600 | walk-forward 6/9 folds, ~+5 %/2-month OOS |
| Intrabar trailing-floor check (engine) | handle_trailing | exit at floor if candle low breaks prior trail | → **ISS-14** (not in HEAD) |

### 3b. Designed only (no code anywhere)

| Idea | Where | Note |
|---|---|---|
| Touch-counted support/resistance levels | handle_trailing `todo_sr_logic.md` | Phase 4 = S/R distance + touch count as **features**; the planned entry *gate* would block more troughs |
| Tighten trail near resistance | same | exit-side |
| 2-state GaussianHMM on Nifty returns (+ Bollinger squeeze filter) | release_branch 9b4351a `trader/strategies/regime_hmm.py`, `todo_hmm.md` | entry veto, never wired, no results |
| Nifty slope gate, VIX gate, ATR SL, ATR×√hold target, volume-divergence exit, anchor tiers, gap SL buffer, LLM macro bias | ai_assisted_trader 6380e16 `docs/todo_improvements.md` | gates/exits, none on detection |

### 3c. Rejected with evidence (do not re-test blind)

From handle_trailing `AUTONOMOUS_MAINTENANCE.md`: ATR stops/trail on 15m (SL exits 83 → 106); model early stop
on P(max) while underwater (TRAILING 154 → 114); EMA200 / dual-EMA gate (blocked winners: GOKEX halved,
IDFCFIRSTB +10.7k → +1.1k).

---

## 4. External reading list

Cited from memory 2026-10-18 — verify editions/venues during the literature phase.

**Labelling & evaluation (where the bottleneck is)**
- López de Prado, *Advances in Financial Machine Learning* (2018) — ch 3 triple-barrier & meta-labelling, ch 4
  sample uniqueness (overlapping labels), ch 7 purged k-fold + embargo.
- López de Prado, *Machine Learning for Asset Managers* (2020) ch 5 — trend-scanning labels.
- Saito & Rehmsmeier (2015), PR vs ROC on imbalanced data, *PLoS ONE*.
- Niculescu-Mizil & Caruana (2005), "Predicting good probabilities with supervised learning", *ICML*.

**Why some troughs reverse (economics)**
- Chan, W.S. (2003), "Stock price reaction to news and no-news: drift and reversal after headlines", *JFE*.
- Da, Liu & Schaumburg (2014), "A closer look at the short-term return reversal", *Management Science*.
- Nagel (2012), "Evaporating liquidity", *RFS*.
- Avellaneda & Lee (2010), "Statistical arbitrage in the U.S. equities market", *Quantitative Finance* (OU s-score).

**Defining turning points**
- Lo, Mamaysky & Wang (2000), "Foundations of Technical Analysis", *J. Finance* (kernel-smoothed extrema).
- Directional change: Glattfelder, Dupuis & Olsen (2011), *Quantitative Finance*; Chen & Tsang, *Detecting Regime
  Change in Computational Finance* (2020).
- Change-point (lower priority — after-the-fact lag): Adams & MacKay (2007) Bayesian online changepoint detection.

---

## 5. Side finding — ISS-14

HEAD's backtest feeds the trailing/breakeven tick checks only the candle **high then close**
(`trader/backtest/engine.py:661`); a candle whose low pierces the trail floor but closes above it never exits in
backtest, while live (tick-level) would. Every exit A/B so far carries this optimism. Filed as
`ISSUES/ISS-14-backtest-trailing-ignores-candle-low/`.

---

## 6. Next

Evaluation campaign plan proposed to the owner 2026-10-18 (pending review). Results get appended here as dated
addenda with links to the per-experiment reviews.
