# Trough/peak detection — experiment ledger

One row per path ever taken on dip/peak detection (labels, features, models, entry gates, thresholds), plus the
exit-side results that constrain them. **Append-only:** a re-test gets a new row that points at the old one; old
rows are never edited except to add a "superseded by" pointer. Protocol: `docs/01_Extrema_Model_Campaign.md`.
Baseline inventory: `reviews/extrema_model_research_inventory_20261018.md`.

**Status vocabulary:** VALIDATED (passed a multi-window test, in config) · FALSIFIED (negative on the metric that
matters) · NULL (no effect beyond noise) · PARTIAL (mixed / one regime) · UNTESTED (built or designed, never
judged) · SUSPECT (judged on the pre-2026-10-16 engine with the reject-freeze bug, or pre-ISS-14 — re-test before
trusting) · LIVE (running in production).

Evidence column: memory-file slug (`~/.claude/projects/.../memory/<slug>.md`), review path, or branch@commit.

## R — retrospective (before 2026-10-18)

### Labels
| ID | Path | Result | Status | Evidence |
|---|---|---|---|---|
| R-01 | Geometric extrema labels (±extrema_order) — production | P(min) learns "bar closed at its low"; AUC 0.54 vs ATHER hand dips | LIVE | `reviews/ather_minima_diagnosis_20260927.md` |
| R-02 | `forward_label` (keep minima only if +min_return within forward_bars) | global threshold hurt per-stock consistency (2026-06-05) | FALSIFIED · SUSPECT | project_stale2_analysis |
| R-03 | `labels.collapse_ties` | fixes plateau double-labels (synthetic s1 P 0.5→1.0); ATHER AUC unmoved | NULL on real | project_regime_detection; ATHER review |
| R-04 | `labels.type: zigzag` (fixed %; then vol-scaled k·σ) | label quality ≫ geometric on synthetic; starves the model at lookback 1200; fixed % fragile, vol-scaled k 2–2.5 plateau | PARTIAL | project_regime_detection |
| R-05 | `labels.type: trend_scan` | labels every trend bar (~12k samples) — NULL for point detection (synthetic) | NULL (synthetic only) | project_regime_detection |
| R-06 | `labels.neutral` (class-2 samples) | fixes dip calibration (precision 0.54→0.79 @0.90) but P&L par, Calmar 9.9→8.3 | NULL · SUSPECT | project_neutral_class_result; `neutral_class_learnings.md` |
| R-07 | `labels.type: avg_trend` (Bruni 2026) | perfect labels; flip fires window/2 late (1.1–2.3 % above trough) — structural | FALSIFIED | project_avg_trend_paper_null; `avg_trend_paper_plan.md` |
| R-08 | Triple-barrier labels for the meta filter | meta filter made outcomes worse (owner-corrected 2026-06-27) | FALSIFIED | project_meta_labeling |

### Features
| ID | Path | Result | Status | Evidence |
|---|---|---|---|---|
| R-10 | Base 6 scalars (vol ratio, norm_price, return slopes 3/5/10/20) | norm_price dominates (corr −0.82) yet AUC 0.49 alone for dips | LIVE | ATHER review |
| R-11 | `features.depth` (drawdown_from_high) | in production since 2026-06; strongest single swing signal (AUC 0.65–0.78) | VALIDATED · LIVE | project_stale2_analysis; ATHER review |
| R-12 | Drawdown-curvature feature | worse at every lookback, logistic and MLP | FALSIFIED (not committed) | project_drawdown_curvature_null |
| R-13 | `features.type: extrema_regime` (ER/VR/slope-t per horizon) | key part of the synthetic winner; ATHER real AUC unmoved | PARTIAL | project_regime_detection |
| R-14 | `features.smoothing` (causal Gaussian) | parity with winner recipe | NULL | project_avg_trend_paper_null |
| R-15 | `features.type: swing` (above_low/depth/ret/RSI) | detection ↑ (P/R 38/27→48/42 %); portfolio ₹498k/5.50 → ₹391k/3.46 — shallow dips killed by stale | FALSIFIED on P&L | project_ather_minima_diagnosis |
| R-16 | Detrended inputs (OHLC ÷ SMA1000) | score distributions unchanged | NULL (synthetic) | project_extrema_lab |
| R-17 | `features.type: window` + MLP (raw window morphology) | built (`tests/test_window_mlp.py`); lab MLP on scalars saturated; real P&L verdict not located | UNTESTED on P&L | shape_features_plan.md Plan 5; project_drawdown_curvature_null |

### Models
| ID | Path | Result | Status | Evidence |
|---|---|---|---|---|
| R-20 | Logistic regression — production | — | LIVE | — |
| R-21 | MLP on scalar features | fires 3.5–6.5k×, precision = base rate (synthetic) | FALSIFIED (synthetic) | project_extrema_lab |
| R-22 | RSI as a detector | at/near random (synthetic) | FALSIFIED (synthetic) | project_extrema_lab |
| R-23 | `winner_gbdt` (zigzag + lookback 6000 + regime + neutral + gbdt @0.65/0.60), 15m global | synthetic 7/7; real: more P&L, worse Calmar (exposure-driven); hold400 variant ₹253.8k/Calmar 2.16 vs base ₹170.9k/1.72; ~2–2.5 h per 18-month run | PARTIAL · SUSPECT | project_regime_detection |
| R-24 | Same recipe on DAY timeframe for all names | Calmar 2.11, DD 10.8 %, 6/7 rolling windows | UNTESTED for deploy · SUSPECT | `reviews/dayw_candidate_proposal_20260713.md` |
| R-25 | Meta-labeling secondary veto | worsened outcomes | FALSIFIED | project_meta_labeling |

### Thresholds / gates
| ID | Path | Result | Status | Evidence |
|---|---|---|---|---|
| R-30 | Regime-conditioned threshold | worse than regime features | FALSIFIED (synthetic) | project_regime_detection |
| R-31 | Adaptive (rolling-quantile) threshold | restores firing in trends at ~chance precision | PARTIAL (synthetic; real untested) | project_extrema_lab |
| R-32 | sell_threshold recalibration (peak recall 0.25 → 0.6–0.9) | P&L ₹424k → ₹420k | NULL | project_peak_detection_vs_pnl |
| R-33 | Per-stock day/4h timeframes | the real separator (4h/day ~⅔ profitable vs 15m ~⅓–½) | VALIDATED · LIVE | project_per_stock_params; project_property_study_20261015 |
| R-34 | Day-TF in-block threshold calibration | dormant names revived (0.90 → 0.88) | VALIDATED · LIVE | project_daytf_threshold_calibration_20260901 |
| R-35 | Knife-regime (zero-cross daily slope) entry gate | knife entries are the BEST bucket | FALSIFIED | project_knife_regime_gate_null |
| R-36 | `entry_gates.turn` (lowest-of-N then up-close) | standalone ATHER ₹44.1k → ₹37.8k | FALSIFIED | project_ather_minima_diagnosis |
| R-37 | RSI / stoch-RSI / MACD / HTF-trend entry gates | built, default-off; stoch_rsi<30 −₹156k in one A/B | FALSIFIED (stoch) / UNTESTED (others) | `exit_mechanism_learnings.md` |
| R-38 | Pattern-top trend guard (per-stock) | ATHER +32 %; global net-negative | VALIDATED per-stock · LIVE (ATHER) | project_pattern_top_trend_guard |
| R-39 | Momentum-decay (P(min) floor) exit | robust null even calibrated | FALSIFIED | project_neutral_class_result |

### Exit-side constraints (why detection gains don't reach P&L)
| ID | Path | Result | Status | Evidence |
|---|---|---|---|---|
| R-40 | Stale runway ×2 (40/200 15m, 10/30 day) | beats baseline 4/4 half-years | VALIDATED · LIVE | project_stale_runway_finding |
| R-41 | Stale re-arm (rolling, cur_floor −2 %) | +₹67k, 4/4 windows | VALIDATED · LIVE | project_stale_rearm_validation |
| R-42 | Tighter hard stop (10/15 %) | doubles losses in corrections | FALSIFIED | project_strategy_exit_model |
| R-43 | Earlier trail arm (+3 %) | ₹498k → ₹397–424k | FALSIFIED | project_ather_minima_diagnosis |
| R-44 | Peak-based stop / breakeven lock (STYLAMIND) | ₹26.9k → ₹8.6–22k | FALSIFIED (single stock) | project_peak_based_stop_styl |
| R-45 | Regime-widened trail at 15m | EOD force-close binds first | FALSIFIED | CLAUDE.md alternative stack |
| R-46 | ISS-14 — backtest trailing ignored candle low | fixed 2026-10-18; every earlier exit A/B is optimistic by an unmeasured amount | FIXED | `ISSUES/ISS-14-*` |

### Selection (not detection, but constrains the watchlist the detector sees)
| ID | Path | Result | Status | Evidence |
|---|---|---|---|---|
| R-50 | Fundamental fingerprint of winners | collapses under PIT (look-ahead) | NULL | project_fingerprint_discovery_null |
| R-51 | Price-behaviour property scorer | ρ +0.06 out of sample | NULL | project_property_study_20261015 |

## B — other branches (inventory 2026-10-18; none judged on the current engine)

| ID | Path | Branch @ ref | Result | Status |
|---|---|---|---|---|
| B-01 | Triple-barrier labels for the PRIMARY model | simple_trader_buy_low_strategy @ d5928b5 | never enabled | UNTESTED |
| B-02 | Lag stacking (t-1, t-2 vectors) | same @ 3af0607 | active, no number | UNTESTED |
| B-03 | `ema20_dist` = (close−EMA20)/ATR | same @ 023897c | top-4 XGB importance | UNTESTED |
| B-04 | Nifty slope20 / VIX features | same | pruned | UNTESTED |
| B-05 | `atr_ratio`, Wilder RSI features | same; release_branch 71fdcf9 → reverted 7ff6184 | pruned / revert reason unrecorded | UNTESTED |
| B-06 | Forward-return regression (XGBRegressor, 96 bars) | same 1d4ceea → d634c84 | reverted after 58 min | UNTESTED |
| B-07 | xgboost / sgd primary | same d634c84 → 471b9c1 | reverted, no number | UNTESTED |
| B-08 | Rules baseline (RSI14<35 + bounce + >EMA50) | same | never run | UNTESTED |
| B-09 | Bounce / EMA50 / autocorr-regime gates | same | EMA50 active, no number | UNTESTED |
| B-10 | EMA-above-and-rising gate | handle_trailing @ 52a5d93 | kept in branch baseline | UNTESTED |
| B-11 | 60-min timeframe calibration | handle_trailing a445c33 | WF 6/9 folds (old engine) | SUSPECT |
| B-12 | Touch-counted S/R levels (features / gate / exit) | handle_trailing `todo_sr_logic.md` | design only | UNTESTED |
| B-13 | 2-state HMM on Nifty (veto) + BB squeeze | release_branch 9b4351a | never wired | UNTESTED |
| B-14 | Nifty slope / VIX gates, ATR SL/targets, volume-divergence exit | ai_assisted_trader 6380e16 | todo only | UNTESTED |
| B-15 | ATR stops/trail at 15m | handle_trailing AUTONOMOUS_MAINTENANCE.md | SL exits 83 → 106 | FALSIFIED |
| B-16 | Early exit on P(max) while underwater | same | TRAILING 154 → 114 | FALSIFIED |
| B-17 | EMA200 / dual-EMA gate | same | blocked winners | FALSIFIED |

## EXP — campaign 2026-10 (protocol: `docs/01_Extrema_Model_Campaign.md`)

| ID | Worktree | Arm | Stage A | Stage B | Status | Review |
|---|---|---|---|---|---|---|
| EXP-00 | — | Baseline (config @ 5970eb5, post-ISS-14) | reference | reference | — | `runs/baseline_postfix_iss14.json`, `runs/stage_a_baseline.json` |
| EXP-00a | — | ISS-14 impact on the baseline (pre-fix 1dd827c vs post-fix 5970eb5) | — | FULL ₹465.4k→₹439.2k (−₹26.2k), Calmar 6.60→6.18, DD 5.7→5.8 %; H1-26 −₹23.9k; HORIZON ₹1,918k→₹2,019k (floor exits help in crashes) | MEASURED | `runs/baseline_prefix_iss14.json` vs `runs/baseline_postfix_iss14.json` |
| EXP-00b | — | Headroom probe: univariate swing measures vs tradeable-trough truth (test 2025-01→) | p_min median AUC 0.511; −depth50 0.534; −ret20 0.515; −RSI14 0.513; −above_low20 0.496; −ret5 0.508 | — | MEASURED — the production model does not rank troughs that pay; neither do single price-position measures. Expect small ΔAUC; EV@matched is the more sensitive gate | `scripts/campaign/headroom_probe.py` |

| EXP-03 | cfg @ 1409e9b | `forward_label` re-test on the fixed engine (150 bars, +1.5 %) — supersedes R-02 | median ΔAUC −0.000, worse on 62 %; median ΔEV@matched 0.00 (15m names −0.12…−0.31, CUPID +1.03); day/4h names unchanged (almost every minimum bounces 1.5 % within 150 bars) | not run (gate) | FAILED Stage A | `runs/stage_a_exp03.json` |

| EXP-12 | — | Market-state stratification of the Stage-A truth (prior-day India VIX tercile; Nifty drawdown from 50-day high) — literature arm (Nagel 2012) | dip bars P(good) 0.26/0.32/0.37 by VIX low/mid/high, EV 0.70/0.81/1.45 %; Nifty dd >8 % → P 0.49 / EV 2.67 % vs <3 % 0.30 / 0.97 %; stress bucket wins in 71–90 % of stocks | — (probe) | PASSED its pre-registered rule (≥20 % rel. base-rate gap, ≥⅔ sign consistency) — deviation: run on 2023–26, not calibration-only; stress episodes cluster in time (few independent episodes) | `scripts/campaign/exp12_context_split.py`; `docs/02_Extrema_Literature_Review.md` §7 |
| EXP-01 | labels @ b99bfce | Tradeable-trough labels, candidates = geometric minima, failed → neutral | median ΔAUC -0.013 (worse 76 %); median ΔEV@matched -0.63 pp (worse 70 %); tuning-free: ΔAP −0.020 (w 67 %), ΔEV@top3 % −0.57 | not run (gate) | FAILED Stage A | `runs/stage_a_exp01.json` |
| EXP-02 | labels @ b99bfce | Tradeable-trough labels, candidates = every 5th bar | median ΔAUC -0.072 (worse 67 %); median ΔEV@matched -1.10 pp (worse 76 %); tuning-free: ΔAP −0.021 (w 76 %), ΔEV@top3 % −0.47 | not run (gate) | FAILED Stage A | `runs/stage_a_exp02.json` |
| EXP-04 | main @ c3fb3a3 | Lag stacking t-1, t-2 (scaffold) — supersedes B-02 | median ΔAUC −0.000 (worse 52 %); median ΔEV@matched −0.62 pp (worse 76 %) | not run (gate) | FAILED Stage A | `runs/stage_a_exp04.json` |
| EXP-05 | features @ d54a0c0 | Reversal bar-shape add-on | median ΔAUC -0.002 (worse 67 %); median ΔEV@matched -0.62 pp (worse 71 %); tuning-free: ΔAP −0.007 (w 67 %), ΔEV@top3 % −0.36 | not run (gate) | FAILED Stage A | `runs/stage_a_exp05.json` |
| EXP-06 | features @ d54a0c0 | ATR-scaled EMA distance add-on | median ΔAUC -0.003 (worse 67 %); median ΔEV@matched -0.28 pp (worse 71 %); tuning-free: ΔAP −0.002 (w 67 %), ΔEV@top3 % +0.11 | not run (gate) | FAILED Stage A | `runs/stage_a_exp06.json` |
| EXP-07 | features @ d54a0c0 | Market add-on (15m Nifty/VIX: rel. strength, Nifty dd, VIX level/chg); Nifty/VIX 15m backfilled 2019-06→2026-10-16 | median ΔAUC +0.010 (worse 29 %); median ΔEV@matched -0.18 pp (worse 62 %); tuning-free: ΔAP +0.006 (w 29 %), ΔEV@top3 % +0.00 — only arm with consistent positive ranking change; gain larger on 4h/day (+0.012–0.014) than 15m (+0.006) | not run (gate) | FAILED Stage A | `runs/stage_a_exp07.json` |
| EXP-08 | features @ d54a0c0 | Touch-counted S/R add-on | median ΔAUC -0.002 (worse 67 %); median ΔEV@matched -0.57 pp (worse 67 %); tuning-free: ΔAP −0.006 (w 67 %), ΔEV@top3 % −0.27 | not run (gate) | FAILED Stage A | `runs/stage_a_exp08.json` |
| EXP-09a | rules @ abd3233 | No-ML rule RSI14<35 + up-close + >EMA50 | median ΔAUC -0.007 (worse 67 %); median ΔEV@matched -1.80 pp (worse 85 %); tuning-free: ΔAP −0.022 (w 81 %), ΔEV@top3 % −0.48 | not run (gate) | FAILED Stage A | `runs/stage_a_exp09a.json` |
| EXP-09b | rules @ abd3233 | No-ML rule lowest-of-20 + up-close | median ΔAUC -0.006 (worse 62 %); median ΔEV@matched -0.68 pp (worse 81 %); tuning-free: ΔAP −0.017 (w 81 %), ΔEV@top3 % −0.86 | not run (gate) | FAILED Stage A | `runs/stage_a_exp09b.json` |
| EXP-10a | rules @ abd3233 | No-ML rule: raw-price OU s-score (graded) | median ΔAUC -0.006 (worse 52 %); median ΔEV@matched -0.73 pp (worse 71 %); tuning-free: ΔAP −0.009 (w 57 %), ΔEV@top3 % −0.15 | not run (gate) | FAILED Stage A | `runs/stage_a_exp10a.json` |
| EXP-10b | rules @ abd3233 | OU s-score + half-life as model features | median ΔAUC +0.000 (worse 48 %); median ΔEV@matched -0.16 pp (worse 67 %); tuning-free: ΔAP −0.001 (w 52 %), ΔEV@top3 % −0.03 | not run (gate) | FAILED Stage A | `runs/stage_a_exp10b.json` |
| EXP-11 | — | EXP-02 + average-uniqueness sample weights (AFML ch 4) | — | — | PROPOSED (literature) | docs/02 arm 4 |
| EXP-13 | — | Residual-vs-Nifty OU s-score (A&L 2010) vs raw-price control (EXP-10a) | — | — | superseded by the pre-check row below | docs/02 arm 5 |
| EXP-14 | — | Volume-conditioned decline probe (15m names; 5-bar/50-bar volume ratio tercile on dip bars) | P(good) low/mid/high 0.303/0.328/0.327, EV 0.72/1.10/1.12 %; high > low in 5/7 stocks | — (probe) | FAILED its pre-registered rule (8 % relative < 20 %) — mild capitulation lean, not built | `scripts/campaign/exp14_volume_split.py` |
| EXP-15 | — | News/no-news decline flag (Chan 2003) — blocked on point-in-time event data | — | — | PROPOSED · BLOCKED | docs/02 arm 3 |
| EXP-16 | — | EXP-08 + double-bottom retest feature (Lo–Mamaysky–Wang 2000) | — | — | PROPOSED (literature) | docs/02 arm 7 |
| EXP-17 | — | Directional-change overshoot features (Glattfelder 2011) — skip if own-path W2 arms all fail | — | — | PROPOSED (literature) | docs/02 arm 8 |

**Protocol note 2026-10-18 (after the first Stage-A batch):** EV@matched is biased toward the baseline — its
per-stock thresholds were calibrated on backtests overlapping the 2025+ test window, every arm is out-of-sample. The
tuning-free cross-check (`scripts/campaign/tail_compare.py`: same top-q tail of each arm's own test-window scores,
plus average precision) removes most of the negative-EV pattern, but **no arm passes under either metric**, so no
verdict changes. AUC (threshold-free) is unaffected. DECISIONS row 2026-10-18.

| EXP-13 | — | Residual-vs-Nifty OU s-score — pre-check (`market_headroom_probe.py`) | −resid_ou_s median AUC 0.511 (57 % > 0.5); −resid_ret20 0.506 | — | FAILED pre-check — not built (supersedes the PROPOSED row) | `scripts/campaign/market_headroom_probe.py` |
| EXP-12b | — | Market-information headroom: prior-day VIX level / z250, Nifty dd20/dd60/ret5 vs truth (test window) | VIX level median AUC **0.638** (86 % of stocks > 0.5); VIX z250 0.611; Nifty dd60 0.582 (81 %); dd20 0.578; ret5 0.535 | — | MEASURED — strongest signal in the campaign; a market-TIMING signal, not which-dip | same |
| EXP-12c | — | Stability by calendar year 2020–26 (truth rebuilt from prices, `vix_by_year.py`) | within-year VIX AUC 0.571/0.557/0.657/0.476/0.549/0.550/0.622 (2020→2026); hi-VIX P(good) > lo in 6/7 years (2020 = tercile artefact) | — | ROBUST 6/7 years | `scripts/campaign/vix_by_year.py` |
| EXP-12d | — | Baseline trades stratified by entry-time VIX percentile tercile (`trades_by_market.py`) | FULL: stress ₹332.7k of ₹419k (avg +2.78 %/pos, win 68 %), calm ₹26.8k (avg +0.17 %); HORIZON: stress avg +1.34 % vs calm +0.66 % (calm still ₹415k); stress ≥ calm avg in 7/7 years; Nifty-dd split NOT consistent (dd>8 % worst over HORIZON) | — | MEASURED — motivates EXP-18 (lean into stress, don't block calm) | `scripts/campaign/trades_by_market.py` |
| EXP-18 | regime (to build) | Market-regime entry modulation (VIX trailing-250 percentile; variants 18a–18f per DECISIONS 2026-10-18) | n/a (decision layer) | pending | QUEUED | `to_develop/2026-10-18_TD-018_W6-market-regime-entry.md` |

(rows appended as arms are defined and run)
