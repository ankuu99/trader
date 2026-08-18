"""
LR Extrema Strategy — Logistic Regression on local price extrema.

Self-trains on accumulated candle history by labelling local minima as
buy candidates (class 0) and local maxima as sell candidates (class 1).
After warmup, emits a BUY ENTRY when the model is confident the current
bar is a local minimum.  Exits are managed within the strategy:
  - Profit target (profit_pct %)
  - Stop-loss     (stop_pct  %)
  - Max hold      (hold_bars candles)

Config keys (under strategies.lr_extrema in config.yaml):
    warmup_bars   : candles to collect before first training (default 200)
    lookback_bars : rolling training window size — deque maxlen (default 500)
                    must be >= warmup_bars; older candles beyond this are dropped
    threshold     : min P(local-min) to trigger BUY ENTRY   (default 0.70)
    profit_pct    : minimum profit % to activate trailing stop (default 3.0)
    trail_pct     : trailing stop distance % from peak       (default 1.5)
    stop_pct      : hard stop-loss in % from entry price     (default 3.0)
    hold_bars     : max candles to stay in a position        (default 150)
    retrain_every : retrain model every N new candles       (default 50)
    extrema_order : neighbourhood half-window for extrema   (default 5)
    sell_threshold      : min P(local-max) to trigger pattern-top EXIT   (default 0.65)
    veto_threshold      : max P(local-max) allowed at entry — blocks entry if model
                          thinks a top is forming simultaneously           (default 0.50)
    min_hold_before_exit: min held_bars before model-based exit can fire  (default 3)

Feature engineering lives in the nested `features:` block, handled by
trader/features/ExtremaFeaturePipeline (volume_ma_bars + optional depth/macd add-ons).

Based on: github.com/kaneelgit/Trading-strategy-
Features: volume, normalised price, 3/5/10/20-bar linear-regression slopes.
"""

from collections import deque
from datetime import  time

import numpy as np

from trader.core.config import config, flatten_strategy_params
from trader.core.logger import get_logger
from trader.features.registry import build_feature_pipeline
from trader.features.labels import MIN_SAMPLES_PER_CLASS, build_labeler
from trader.models.registry import build_model
from trader.policy.base import PositionState
from trader.policy.extrema_entry import ExtremaEntryPolicy
from trader.policy.extrema_exit import ExtremaExitPolicy
from trader.strategies.base import Direction, Signal, SignalType, Strategy
from trader.strategies.meta_filter import MetaFilter

logger = get_logger(__name__)


class LRExtremaStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        # Resolve nested entry_gates:/exits: config blocks into the flat keys the
        # policies read (Stage 3). Idempotent — config-sourced params arrive already
        # flattened; direct-dict callers (tests/calibrate) are flattened here.
        params = flatten_strategy_params(params)

        # --- Core model-decision params (strategy-level) ---
        self._warmup_bars: int = params.get("warmup_bars", 200)
        self._lookback_bars: int = params.get("lookback_bars", 600)
        self._threshold: float = params.get("threshold", 0.70)
        self._veto_threshold: float = params.get("veto_threshold", 0.50)
        # exposed for the UI; the exit policy owns its own pattern-top copy
        self._sell_threshold: float = params.get("sell_threshold", 0.65)
        # entry stop-loss hint; the exit policy owns the live hard-stop
        self._stop_pct: float = params.get("stop_pct", 3.0)
        self._retrain_every: int = params.get("retrain_every", 50)
        # When true, _train logs an out-of-sample (temporal-holdout) quality report
        # for both classes — precision/recall at the operating thresholds plus the
        # P(max)/P(min) separation. Off by default to keep backtest logs quiet.
        self._diag_enabled: bool = bool(params.get("training_diagnostics", False))
        # Pooled OOS (p_max, is_top) pairs across all retrains — used to emit a
        # precision/recall curve over a sell_threshold grid for recalibration.
        self._diag_pool_pmax: list[float] = []
        self._diag_pool_istop: list[int] = []

        # --- Pipeline (S1) / model (S2) / policies (S3) / labeler (S4) ---
        self._features = build_feature_pipeline(params.get("features", {}))
        self._model_cfg = params.get("model")  # kept for the diagnostic eval-model rebuild
        self._model = build_model(self._model_cfg)
        self._entry_policy = ExtremaEntryPolicy(params)
        self._exit_policy = ExtremaExitPolicy(params)
        self._labeler = build_labeler(instrument, params)

        # Meta-labeling precision gate (no-op unless meta_label.enabled). Barriers for
        # the meta triple-barrier labels default to the strategy's own exit params.
        self._meta = MetaFilter(instrument, params)
        self._meta_exit_defaults = {
            "profit_pct": params.get("profit_pct", 3.0),
            "stop_pct": params.get("stop_pct", 3.0),
            "max_bars": params.get("hold_bars", 150),
        }

        self._candles: deque = deque(maxlen=self._lookback_bars)
        self._candles_since_train: int = 0

        # Position-tracking state — single source of truth, mutated by the exit policy.
        self._pos = PositionState()

        # --- Display / diagnostic state ---
        # set to the block reason string when an entry is filtered; None otherwise
        self.last_filter_block: str | None = None
        # each entry: {timestamp, close, p_min, p_max, type} — type is
        # ENTRY | BLOCKED | VETOED | PATTERN_TOP; populated on every threshold crossing
        self.signal_log: list[dict] = []
        # Latest model scores — updated every candle once trained; exposed to UI
        self._last_p_min: float = 0.0
        self._last_p_max: float = 0.0
        # Latest feature vector fed to the model — retained for UI explainability
        self._last_features = None

    # ------------------------------------------------------------------
    # Backward-compatible position-state accessors
    # ------------------------------------------------------------------
    # Position state now lives in self._pos. These shims keep existing callers
    # working unchanged — engine.py / main.py (warmup-clear + persistence,
    # incl. getattr defaults), replay_strategy.py, and the flow tests.

    @property
    def _entry_price(self): return self._pos.entry_price
    @_entry_price.setter
    def _entry_price(self, v): self._pos.entry_price = v

    @property
    def _fill_price(self): return self._pos.fill_price
    @_fill_price.setter
    def _fill_price(self, v): self._pos.fill_price = v

    @property
    def _held_bars(self): return self._pos.held_bars
    @_held_bars.setter
    def _held_bars(self, v): self._pos.held_bars = v

    @property
    def _peak_close(self): return self._pos.peak_close
    @_peak_close.setter
    def _peak_close(self, v): self._pos.peak_close = v

    @property
    def _trailing_active(self): return self._pos.trailing_active
    @_trailing_active.setter
    def _trailing_active(self, v): self._pos.trailing_active = v

    @property
    def _max_gain_pct(self): return self._pos.max_gain_pct
    @_max_gain_pct.setter
    def _max_gain_pct(self, v): self._pos.max_gain_pct = v

    @property
    def _pattern_top_trailing(self): return self._pos.pattern_top_trailing
    @_pattern_top_trailing.setter
    def _pattern_top_trailing(self, v): self._pos.pattern_top_trailing = v

    @property
    def name(self) -> str:
        return f"LR-Extrema(w={self._warmup_bars},thr={self._threshold})"

    # ------------------------------------------------------------------
    # Core lifecycle
    # ------------------------------------------------------------------

    def on_candle(self, candle: dict) -> Signal | None:
        self._candles.append(candle)
        close = candle["close"]
        self.last_filter_block = None  # reset each candle

        # --- Hold-bars counter (always increment while in position) ---
        if not self.is_flat():
            self._pos.held_bars += 1

        # --- Warmup guard ---
        if len(self._candles) < self._warmup_bars:
            return None

        # --- Periodic retraining ---
        # Must run BEFORE the pending-fill guard below. A phantom warm-up entry
        # leaves _entry_price set with no fill; if the guard returned first it would
        # short-circuit every subsequent candle and freeze the model at its early,
        # undertrained fit (the 2026-06-17 RMDRIP P(min)=1.000 bug). Retraining must
        # never be gated by position state.
        if not self._model.is_trained or self._candles_since_train >= self._retrain_every:
            self._train()
            self._candles_since_train = 0

        # --- Pending fill guard (entry order sent, awaiting fill) ---
        if self._pos.entry_price is not None and self.is_flat():
            self._candles_since_train += 1  # keep retrain cadence advancing
            return None

        # --- Trading window gate (all signals, entry and exit) ---
        # The position survives outside the window; the SL / hold_bars exit will fire
        # on the next in-window candle.
        ts = candle.get("timestamp")
        _candle_time = ts.time() if (ts is not None and hasattr(ts, "time")) else None
        _outside_window = (
            _candle_time is not None
            and not (config.trading_start <= _candle_time <= config.trading_end)
        )
        if _outside_window:
            self._candles_since_train += 1
            return None

        # --- Candle-speed exits (hold_bars / stale / momentum / pattern-top) ---
        if not self.is_flat():
            decision = self._exit_policy.candle_exit(self, candle, close)
            if decision is not None:
                self._candles_since_train += 1
                return self._exit_signal(decision)

        # --- Entry prediction ---
        # Both gates must pass: P(local-min) >= threshold AND P(local-max) < veto_threshold.
        if self._model.is_trained and self.is_flat() and self._pos.entry_price is None:
            x = self._features.compute(self._candles)
            if x is not None:
                p_min, p_max = self._predict_proba(x)
                self._last_p_min = p_min
                self._last_p_max = p_max
                if p_min >= self._threshold:
                    _log_entry: dict = {
                        "timestamp": candle.get("timestamp"),
                        "close": close,
                        "p_min": p_min,
                        "p_max": p_max,
                        "type": "VETOED" if p_max >= self._veto_threshold else "ENTRY",
                    }
                    self.signal_log.append(_log_entry)
                if p_min >= self._threshold and p_max < self._veto_threshold:
                    blocks = self._entry_policy.gate_blocks(x, list(self._candles), close)
                    if blocks:
                        _log_entry["type"] = "BLOCKED"
                        self.last_filter_block = ", ".join(blocks)
                        logger.debug(
                            "LR-Extrema ENTRY BLOCKED | %s | %s | candle=%s",
                            self.instrument, self.last_filter_block, candle.get("timestamp"),
                        )
                        self._candles_since_train += 1
                        return None

                    # Meta-labeling precision gate — secondary model vetoes low-quality
                    # firings. No-op unless meta_label.enabled and trained.
                    size_weight = None
                    if self._meta.enabled and self._meta.is_trained:
                        x_meta = self._meta.features_for(self._candles, p_min, p_max, self._threshold)
                        take, p_win = self._meta.allow(x_meta)
                        if not take:
                            _log_entry["type"] = "META_BLOCKED"
                            _log_entry["p_win"] = p_win
                            self.last_filter_block = (
                                f"meta p_win={p_win:.2f}<{self._meta.meta_threshold:.2f}"
                            )
                            logger.debug(
                                "LR-Extrema META BLOCKED | %s | p_win=%.3f < %.2f | candle=%s",
                                self.instrument, p_win, self._meta.meta_threshold,
                                candle.get("timestamp"),
                            )
                            self._candles_since_train += 1
                            return None
                        # Phase 2: confidence sizing — scale qty by P(win). None = full size.
                        size_weight = self._meta.size_weight(p_win)

                    logger.info(
                        "LR-Extrema ENTRY | %s | P(min)=%.3f >= %.3f | P(max)=%.3f < %.3f | price=%.2f | candle=%s",
                        self.instrument, p_min, self._threshold, p_max, self._veto_threshold, close,
                        candle.get("timestamp"),
                    )
                    self._pos.entry_price = close  # guards re-entry; overridden by fill price in on_order_update
                    self._pos.held_bars = 0
                    self._candles_since_train += 1
                    sl_hint = round(close * (1 - self._stop_pct / 100), 2)
                    return Signal(
                        instrument=self.instrument,
                        direction=Direction.BUY,
                        signal_type=SignalType.ENTRY,
                        price_hint=close,
                        strategy=self.name,
                        stop_loss_hint=sl_hint,
                        target_price=None,  # trailing stop manages upside; no fixed target
                        timestamp=candle.get("timestamp"),
                        size_weight=size_weight,
                    )

        # In-position phantom signal — emitted when threshold crossed while already holding.
        # No state is changed; RiskManager rejects it with "already_in_position" and
        # main.py logs it so the chart can show where re-entries would have fired.
        if not self.is_flat() and self._model.is_trained:
            x = self._features.compute(self._candles)
            if x is not None:
                _p_min, _p_max = self._predict_proba(x)
                self._last_p_min = _p_min
                self._last_p_max = _p_max
                if _p_min >= self._threshold and _p_max < self._veto_threshold:
                    self._candles_since_train += 1
                    return Signal(
                        instrument=self.instrument,
                        direction=Direction.BUY,
                        signal_type=SignalType.ENTRY,
                        price_hint=close,
                        strategy=self.name,
                        stop_loss_hint=round(close * (1 - self._stop_pct / 100), 2),
                        target_price=None,
                        timestamp=candle.get("timestamp"),
                    )

        # Always refresh model scores for UI display (covers cases above that didn't compute).
        if self._model.is_trained:
            x = self._features.compute(self._candles)
            if x is not None:
                self._last_p_min, self._last_p_max = self._predict_proba(x)

        self._candles_since_train += 1
        return None

    def _predict_proba(self, x) -> tuple[float, float]:
        """Run the model and retain the feature vector so the UI can explain the
        most recent prediction. Side-effect only; output is identical to the
        model's own predict_proba (parity-golden safe)."""
        self._last_features = x
        return self._model.predict_proba(x)

    def score_current(self) -> tuple[float, float] | None:
        """Model (p_min, p_max) for the current candle buffer, computed directly
        and independent of position / pending-fill state. Returns None when the
        model is untrained or there isn't enough history.

        Used by the warm-up conviction backfill: reading the cached _last_p_min
        there is unreliable because a discarded phantom warm-up entry sets
        _pos.entry_price with no fill, after which on_candle's pending-fill guard
        returns early every candle and freezes _last_p_min at the entry-trigger
        value. This recomputes from the trained model so each candle gets its true
        score. Pure — no side effects on _last_p_min / _last_features."""
        if not self._model.is_trained:
            return None
        x = self._features.compute(self._candles)
        if x is None:
            return None
        return self._model.predict_proba(x)

    @property
    def feature_names(self) -> list[str]:
        """Column names for the active feature pipeline (UI explainability)."""
        return list(self._features.feature_names)

    def last_feature_drivers(self, top_n: int = 4) -> list[dict]:
        """Top drivers of the most recent prediction, largest magnitude first.

        Each item: {name, value, kind} where kind='contrib' is a signed push
        toward BUY (positive = bullish) and kind='raw' is the plain feature value
        used as a fallback when the model can't attribute linearly (e.g. MLP).
        Empty when nothing has been scored yet.
        """
        if self._last_features is None or not self._model.is_trained:
            return []
        contribs = self._model.feature_contributions(self._last_features, self.feature_names)
        if contribs:
            items = [{"name": n, "value": v, "kind": "contrib"} for n, v in contribs]
        else:
            items = [
                {"name": n, "value": float(v), "kind": "raw"}
                for n, v in zip(self.feature_names, self._last_features)
            ]
        items.sort(key=lambda it: abs(it["value"]), reverse=True)
        return items[:top_n]

    def _exit_signal(self, decision) -> Signal:
        """Build an EXIT Signal from an ExitDecision returned by the exit policy."""
        return Signal(
            instrument=self.instrument,
            direction=Direction.BUY,
            signal_type=SignalType.EXIT,
            price_hint=decision.price_hint,
            strategy=self.name,
            exit_reason=decision.exit_reason,
            timestamp=decision.timestamp,
            exit_fraction=getattr(decision, "exit_fraction", None),
        )

    def on_tick(self, tick: dict) -> Signal | None:
        """
        Called on every raw tick (live) or simulated tick (backtest).
        Hard stop / trailing / breakeven / EOD-close are handled by the exit policy.
        Entry logic stays in on_candle.
        """
        if self.is_flat() or self._pos.entry_price is None:
            return None

        # Trading window gate — no SL/trailing exits outside the window
        ts = tick.get("timestamp")
        tick_time = ts.time() if (ts is not None and hasattr(ts, "time")) else None
        if tick_time is not None and not (config.trading_start <= tick_time <= config.trading_end):
            return None

        last_price = tick.get("last_price")
        if last_price is None:
            return None

        decision = self._exit_policy.tick_exit(self, tick, last_price)
        if decision is not None:
            return self._exit_signal(decision)
        return None

    def seed_position_state(self, peak_close: float, max_gain_pct: float) -> None:
        """Restore in-memory position state after a restart.
        Called by main.py after on_order_update re-seeds entry price and held_bars.
        peak_close: 0.0 means not persisted (stock price can never be 0).
        max_gain_pct: always restored — 0.0 is valid (position never went positive)."""
        if peak_close > 0:
            self._pos.peak_close = peak_close
        self._pos.max_gain_pct = max_gain_pct

    def _reset_position_state(self) -> None:
        """Clear all position-tracking fields. Called on any exit path."""
        self._pos.reset()

    def on_order_update(self, order: dict) -> None:
        # Scale-in add-on fills change only quantity (tracked by RiskManager) — the
        # staleness clock (_held_bars), gain anchor (_entry_price) and trailing state
        # MUST stay frozen on the original entry. Re-anchoring to the blended (lower)
        # entry would restart the stale runway exactly on falling-knife positions,
        # turning the disaster brake into an enabler. Cancel/reject of an add-on is
        # equally a no-op: the parent position state is untouched.
        if order.get("addon"):
            return
        super().on_order_update(order)
        status = order.get("status", "")
        signal_type = order.get("signal_type", "")
        if status == "COMPLETE":
            if signal_type == SignalType.ENTRY:
                fill_price = order.get("price") or order.get("average_price")
                if fill_price:
                    self._pos.entry_price = float(fill_price)
                    self._pos.fill_price = float(fill_price)  # preserve confirmed fill for retrigger
                # Restore held_bars from synthetic fill on restart; normal fills pass 0
                held_bars = order.get("_held_bars")
                self._pos.held_bars = int(held_bars) if held_bars is not None else 0
                self._pos.clear_snapshot()  # new lifecycle — a stale exit snapshot must never restore into it
            elif signal_type == SignalType.EXIT:
                # Partial (scale-out) fill: position stays open with the remainder —
                # keep entry/trailing state intact (partial_taken already set).
                if not order.get("partial"):
                    self._pos.reset()
                    self._pos.clear_snapshot()  # exit confirmed — nothing left to restore
        elif status in ("REJECTED", "CANCELLED"):
            if signal_type == SignalType.ENTRY:
                logger.warning(
                    "LR-Extrema | %s | ENTRY order %s — clearing entry guard",
                    self.instrument, status,
                )
                self._pos.reset()
            elif signal_type == SignalType.EXIT:
                # EXIT order cancelled/rejected (e.g. last-candle exit dying in the
                # 15:30 Closing Auction Session) — restore the FULL pre-emission state
                # so the hold/stale clocks, trail anchor and scale-out guard survive,
                # not just the entry price (TVSMOTOR 2026-08-17: held_bars 200->0 lost
                # a timeout exit for ~8 sessions under the entry-price-only restore).
                if self._pos.restore_snapshot():
                    logger.warning(
                        "LR-Extrema | %s | EXIT order %s — position state restored for retrigger "
                        "(held_bars=%d trailing=%s)",
                        self.instrument, status, self._pos.held_bars, self._pos.trailing_active,
                    )
                elif self._pos.fill_price is not None:
                    # No snapshot (e.g. restart between emission and rejection) —
                    # legacy fallback: at least re-anchor the entry price.
                    logger.warning(
                        "LR-Extrema | %s | EXIT order %s — no snapshot, restoring entry price only",
                        self.instrument, status,
                    )
                    self._pos.entry_price = self._pos.fill_price

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def _train(self) -> None:
        # Snapshot the deque once — deque does not support slice notation and
        # a consistent list is needed for indexed access throughout training.
        candles = list(self._candles)

        # The labeler decides which candles are training samples and their class.
        indices, classes = self._labeler.label(candles)
        if not indices:
            return

        rows, labels, kept_idx = [], [], []
        for idx, cls in zip(indices, classes):
            feat = self._features.compute(candles[: idx + 1])
            if feat is not None:
                rows.append(feat)
                labels.append(cls)
                kept_idx.append(idx)

        if len(rows) < MIN_SAMPLES_PER_CLASS * 2:
            return

        X = np.array(rows, dtype=float)
        y = np.array(labels, dtype=int)

        # The model owns its own scaling and fits fresh each retrain.
        self._model.fit(X, y)
        logger.info(
            "LR-Extrema trained | %s | samples=%d (min=%d max=%d)",
            self.instrument, len(rows), labels.count(0), labels.count(1),
        )

        # Out-of-sample quality report (no-op unless training_diagnostics enabled).
        if self._diag_enabled:
            self._log_training_diagnostics(kept_idx, rows, labels)

        # Retrain the meta-labeling filter on the primary's historical firings.
        # No-op unless meta_label.enabled. Past-only buffer => no look-ahead.
        self._meta.train(
            candles, self._features, self._model.predict_proba,
            self._threshold, self._veto_threshold, self._meta_exit_defaults,
        )

    # ------------------------------------------------------------------
    # Training diagnostics (#8) — out-of-sample peak/dip detection quality
    # ------------------------------------------------------------------

    def _log_training_diagnostics(self, kept_idx, rows, labels) -> None:
        """Temporal-holdout evaluation of detection quality, logged per retrain.

        Splits the labelled samples chronologically (70/30), fits a throwaway model
        of the same config on the earlier 70%, and scores the held-out 30% at the
        live operating thresholds. Reports, per class:
          - precision = TP / (TP + FP)  → high precision means few FALSE POSITIVES
          - recall    = TP / (TP + FN)  → high recall means few FALSE NEGATIVES
        plus the mean P(max) on true tops vs non-tops (separation). The deployed
        model is unaffected — this fits its own eval model on a strict past slice.
        """
        order = sorted(range(len(kept_idx)), key=lambda i: kept_idx[i])
        X_all = np.array([rows[i] for i in order], dtype=float)
        y_all = np.array([labels[i] for i in order], dtype=int)
        n = len(y_all)
        split = int(n * 0.7)
        X_tr, y_tr = X_all[:split], y_all[:split]
        X_te, y_te = X_all[split:], y_all[split:]

        # Need both classes in train, and at least one of each in the holdout.
        if (y_tr.tolist().count(0) < MIN_SAMPLES_PER_CLASS
                or y_tr.tolist().count(1) < MIN_SAMPLES_PER_CLASS
                or 0 not in y_te.tolist() or 1 not in y_te.tolist()):
            logger.debug(
                "LR-Extrema diag | %s | holdout too small (n=%d) — skipping", self.instrument, n,
            )
            return

        eval_model = build_model(self._model_cfg)
        eval_model.fit(X_tr, y_tr)
        probs = [eval_model.predict_proba(x) for x in X_te]
        p_min = np.array([p[0] for p in probs])
        p_max = np.array([p[1] for p in probs])

        def _pr(pred: np.ndarray, actual: np.ndarray) -> tuple[float, float, int]:
            tp = int(np.sum(pred & actual))
            fp = int(np.sum(pred & ~actual))
            fn = int(np.sum(~pred & actual))
            prec = tp / (tp + fp) if (tp + fp) else float("nan")
            rec = tp / (tp + fn) if (tp + fn) else float("nan")
            return prec, rec, int(np.sum(actual))

        is_top = y_te == 1
        is_dip = y_te == 0
        top_prec, top_rec, n_top = _pr(p_max >= self._sell_threshold, is_top)
        dip_prec, dip_rec, n_dip = _pr(p_min >= self._threshold, is_dip)

        # Opt-in diagnostic — print so it survives backtest's ERROR log level.
        print(
            f"DIAG {self.instrument} | holdout n={len(y_te)} (dip={n_dip} top={n_top}) | "
            f"TOP@{self._sell_threshold:.2f} prec={top_prec:.2f} rec={top_rec:.2f} | "
            f"DIP@{self._threshold:.2f} prec={dip_prec:.2f} rec={dip_rec:.2f} | "
            f"P(max): tops={p_max[is_top].mean():.2f} non-tops={p_max[~is_top].mean():.2f} "
            f"sep={p_max[is_top].mean() - p_max[~is_top].mean():+.2f}"
        )

        # Pool this holdout into the running PR-curve buffer and re-emit the pooled
        # sweep. Holdouts overlap across retrains (sliding window), so this is a
        # relative recalibration aid, not an unbiased OOS estimate. The LAST SWEEP
        # line printed per symbol carries the full pooled curve.
        self._diag_pool_pmax.extend(p_max.tolist())
        self._diag_pool_istop.extend(is_top.astype(int).tolist())
        pm = np.array(self._diag_pool_pmax)
        it = np.array(self._diag_pool_istop, dtype=bool)
        n_pool_top = int(it.sum())
        if n_pool_top:
            grid = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
            cells = []
            for t in grid:
                pred = pm >= t
                tp = int(np.sum(pred & it))
                fp = int(np.sum(pred & ~it))
                prec = tp / (tp + fp) if (tp + fp) else float("nan")
                rec = tp / n_pool_top
                cells.append(f"{t:.2f}:p={prec:.2f},r={rec:.2f}")
            print(f"SWEEP {self.instrument} | pooled_n={len(pm)} tops={n_pool_top} | " + " ".join(cells))
