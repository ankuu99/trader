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
    trading_start : earliest candle time for ENTRY signals  (default "09:45")
    trading_end   : latest candle time for ENTRY signals    (default "15:15")
    sell_threshold      : min P(local-max) to trigger pattern-top EXIT   (default 0.65)
    volume_ma_bars      : rolling window for volume normalisation          (default 20)
    label_mode          : "extrema" (default) uses ±order neighbourhood — has look-ahead
                          in training labels; "forward_return" uses future N-bar return
                          to label each candle with no look-ahead contamination
    label_horizon       : bars ahead to measure return for forward_return labels (default 24)
    model_type          : "lr" (default LogisticRegression) or "xgboost"
    n_estimators        : XGBoost trees (default 100, ignored for lr)
    max_depth           : XGBoost tree depth (default 3)
    learning_rate       : XGBoost learning rate (default 0.1)
    atr_stop_mult       : stop = entry - mult * ATR14; 0 (default) uses stop_pct fallback
    regime_nifty_symbol : injected by backtest engine, no config needed (default "NSE:NIFTY 50")
    regime_vix_symbol   : injected by backtest engine, no config needed (default "NSE:INDIA VIX")

Based on: github.com/kaneelgit/Trading-strategy-
Features (11): volume_ratio, norm_price, slope3/5/10/20, ATR-ratio, RSI14, EMA20-dist,
               NIFTY-slope20, VIX-norm
"""

from collections import deque
from datetime import datetime, time, timedelta

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import MinMaxScaler

try:
    from xgboost import XGBClassifier as _XGBClassifier, XGBRegressor as _XGBRegressor
    _XGBOOST_AVAILABLE = True
except Exception:
    _XGBOOST_AVAILABLE = False

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)

_MIN_SAMPLES_PER_CLASS = 2   # need at least this many of each class to train
_MIN_REGRESSION_SAMPLES = 50  # minimum samples for regression training (tail quantiles need more data)


class LRExtremaStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._warmup_bars: int = params.get("warmup_bars", 200)
        self._lookback_bars: int = params.get("lookback_bars", 600)
        self._threshold: float = params.get("threshold", 0.70)
        self._profit_pct: float = params.get("profit_pct", 3.0)
        self._trail_pct: float = params.get("trail_pct", 1.5)
        self._stop_pct: float = params.get("stop_pct", 3.0)
        self._retrain_every: int = params.get("retrain_every", 50)
        self._extrema_order: int = params.get("extrema_order", 5)
        self._sell_threshold: float = params.get("sell_threshold", 0.65)
        self._sell_min_pct: float = params.get("sell_min_pct", 2.0)
        self._volume_ma_bars: int = params.get("volume_ma_bars", 20)
        self._label_mode: str = params.get("label_mode", "extrema")
        self._label_horizon: int = params.get("label_horizon", 24)
        self._model_type: str = params.get("model_type", "lr")
        # Regression mode: forward_return labels are continuous, model is XGBRegressor
        self._is_regression: bool = (self._label_mode == "forward_return")
        self._min_entry_return: float = params.get("min_entry_return", 0.03)
        self._exit_return_floor: float = params.get("exit_return_floor", 0.0)
        if self._is_regression:
            # Regression: ATR window and hold backstop both derived from label_horizon
            self._atr_period: int = self._label_horizon
            self._hold_bars: int = int(self._label_horizon * 1.5)
        else:
            # Extrema/classification: independent params — label_horizon is irrelevant
            self._atr_period = params.get("atr_period", 14)
            self._hold_bars  = params.get("hold_bars", 150)
        self._xgb_n_estimators: int = params.get("n_estimators", 100)
        self._xgb_max_depth: int = params.get("max_depth", 3)
        self._xgb_learning_rate: float = params.get("learning_rate", 0.1)
        self._atr_stop_mult: float = params.get("atr_stop_mult", 0.0)

        # --- Entry filter gates (disabled by default — 0/False means off) ---
        self._entry_min_volume_ratio: float = params.get("entry_min_volume_ratio", 0.0)
        self._entry_min_norm_price: float = params.get("entry_min_norm_price", 0.0)
        self._entry_require_prior_decline: bool = bool(params.get("entry_require_prior_decline", False))

        def _parse_time(val: str | None, default: time) -> time:
            if val is None:
                return default
            h, m = val.split(":")
            return time(int(h), int(m))

        self._trading_start: time = _parse_time(params.get("trading_start"), time(9, 30))
        self._trading_end: time   = _parse_time(params.get("trading_end"),   time(15, 30))

        self._candles: deque = deque(maxlen=self._lookback_bars)
        self._model: LogisticRegression | None = None
        self._scaler: MinMaxScaler | None = None
        self._trained: bool = False
        self._candles_since_train: int = 0

        # exit tracking
        self._entry_price: float | None = None
        self._entry_stop: float | None = None   # actual stop price at entry (ATR or pct-based)
        self._held_bars: int = 0
        self._peak_close: float | None = None   # highest close since entry
        self._trailing_active: bool = False     # True once profit_pct floor is hit

        # SL cooldown — block re-entry for sl_cooldown_bars × candle_minutes after a hard SL hit
        # Default 0 = disabled; set explicitly in config to activate (e.g. sl_cooldown_bars: 96)
        # In regression mode defaults to label_horizon (the natural prediction window)
        _default_cooldown = self._label_horizon if self._is_regression else 0
        self._sl_cooldown_bars: int = params.get("sl_cooldown_bars", _default_cooldown)
        self._sl_cooldown_until: datetime | None = None
        self._last_candle_ts: datetime | None = None  # tracks last seen candle timestamp
        self._candle_minutes: int = 0                  # auto-detected from first candle pair

        # set to the block reason string when an entry is filtered; None otherwise
        self.last_filter_block: str | None = None

    @property
    def name(self) -> str:
        if self._is_regression:
            return f"LR-Extrema(w={self._warmup_bars},ret>={self._min_entry_return:.2f})"
        return f"LR-Extrema(w={self._warmup_bars},thr={self._threshold})"

    # ------------------------------------------------------------------
    # Core lifecycle
    # ------------------------------------------------------------------

    def on_candle(self, candle: dict) -> Signal | None:
        self._candles.append(candle)
        close = candle["close"]
        self.last_filter_block = None  # reset each candle

        # Auto-detect candle duration from the first consecutive candle pair seen
        candle_ts = candle.get("timestamp")
        if candle_ts is not None:
            if self._candle_minutes == 0 and self._last_candle_ts is not None:
                delta_min = (candle_ts - self._last_candle_ts).total_seconds() / 60
                if 1 <= delta_min <= 1500:
                    self._candle_minutes = int(round(delta_min))
            self._last_candle_ts = candle_ts

        # --- Pending fill guard (entry order sent, awaiting fill) ---
        if self._entry_price is not None and self.is_flat():
            return None

        # --- Hold-bars counter (always increment while in position) ---
        if not self.is_flat():
            self._held_bars += 1

        # --- Warmup guard ---
        if len(self._candles) < self._warmup_bars:
            return None

        # --- Periodic retraining ---
        if not self._trained or self._candles_since_train >= self._retrain_every:
            self._train()
            self._candles_since_train = 0

        # --- Hold-bars timeout (candle-granularity time cap) ---
        # Hard stop and trailing stop fire tick-by-tick via on_tick; hold_bars is
        # intentionally candle-based (a time limit, not a price level).
        if not self.is_flat() and self._held_bars >= self._hold_bars:
            logger.info(
                "LR-Extrema EXIT | %s | max hold (%d bars) | entry=%.2f close=%.2f | candle=%s",
                self.instrument, self._held_bars, self._entry_price or 0, close,
                candle.get("timestamp"),
            )
            self._reset_position_state()
            self._candles_since_train += 1
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.EXIT,
                price_hint=close,
                strategy=self.name,
            )

        # --- Model-based exit (pattern top detection, on-candle) ---
        # Fires when P(local-max) >= sell_threshold after min_hold_before_exit bars,
        # but only when gain >= sell_min_pct — stop_pct handles underwater/small exits.
        _pct_gain = (
            (close - self._entry_price) / self._entry_price * 100.0
            if self._entry_price else 0.0
        )
        if (not self.is_flat() and self._trained
                and _pct_gain >= self._sell_min_pct):
            x = self._compute_features(self._candles)
            if x is not None:
                should_exit = False
                if self._is_regression:
                    expected_return = self._predict_return(x)
                    should_exit = expected_return < self._exit_return_floor
                    if should_exit:
                        logger.info(
                            "LR-Extrema PATTERN-TOP EXIT | %s | expected_return=%.4f < floor=%.4f | price=%.2f | candle=%s",
                            self.instrument, expected_return, self._exit_return_floor, close,
                            candle.get("timestamp"),
                        )
                else:
                    proba = self._predict_proba(x)
                    classes = list(self._model.classes_)
                    if 1 in classes:
                        p_max = proba[classes.index(1)]
                        should_exit = p_max >= self._sell_threshold
                        if should_exit:
                            logger.info(
                                "LR-Extrema PATTERN-TOP EXIT | %s | P(max)=%.3f >= %.3f | price=%.2f | candle=%s",
                                self.instrument, p_max, self._sell_threshold, close,
                                candle.get("timestamp"),
                            )
                if should_exit:
                    self._reset_position_state()
                    self._candles_since_train += 1
                    return Signal(
                        instrument=self.instrument,
                        direction=Direction.BUY,
                        signal_type=SignalType.EXIT,
                        price_hint=close,
                        strategy=self.name,
                        exit_reason="PATTERN_TOP",
                    )

        # --- Trading window gate (entry only) ---
        ts = candle.get("timestamp")
        if ts is not None:
            candle_time = ts.time() if hasattr(ts, "time") else None
            if candle_time is not None and not (self._trading_start <= candle_time <= self._trading_end):
                self._candles_since_train += 1
                return None

        # --- Entry prediction ---
        if self._sl_cooldown_until is not None and candle_ts is not None:
            if candle_ts < self._sl_cooldown_until:
                self.last_filter_block = f"sl_cooldown_until={self._sl_cooldown_until.strftime('%Y-%m-%d %H:%M')}"
                self._candles_since_train += 1
                return None
            else:
                self._sl_cooldown_until = None  # expired — clear it

        if self._trained and self.is_flat() and self._entry_price is None:
            x = self._compute_features(self._candles)
            if x is not None:
                signal_entry = False
                if self._is_regression:
                    expected_return = self._predict_return(x)
                    signal_entry = expected_return >= self._min_entry_return
                else:
                    # Classification path (extrema mode)
                    proba = self._predict_proba(x)
                    classes = list(self._model.classes_)
                    p_min = proba[classes.index(0)] if 0 in classes else 0.0
                    p_max = proba[classes.index(1)] if 1 in classes else 1.0
                    signal_entry = p_min >= self._threshold

                if signal_entry:
                    # Hard filter gates — shared across both paths
                    blocks: list[str] = []
                    if self._entry_min_volume_ratio > 0 and x[0] < self._entry_min_volume_ratio:
                        blocks.append(f"vol_ratio={x[0]:.2f}<{self._entry_min_volume_ratio}")
                    if self._entry_min_norm_price > 0 and x[1] < self._entry_min_norm_price:
                        blocks.append(f"norm_price={x[1]:.2f}<{self._entry_min_norm_price}")
                    if self._entry_require_prior_decline and x[5] >= 0:
                        blocks.append(f"slope20={x[5]:.4f}>=0 (no prior decline)")
                    if blocks:
                        self.last_filter_block = ", ".join(blocks)
                        logger.debug(
                            "LR-Extrema ENTRY BLOCKED | %s | %s | candle=%s",
                            self.instrument, self.last_filter_block, candle.get("timestamp"),
                        )
                        self._candles_since_train += 1
                        return None

                    if self._is_regression:
                        logger.info(
                            "LR-Extrema ENTRY | %s | expected_return=%.4f >= %.4f | price=%.2f | candle=%s",
                            self.instrument, expected_return, self._min_entry_return, close,
                            candle.get("timestamp"),
                        )
                    else:
                        logger.info(
                            "LR-Extrema ENTRY | %s | P(min)=%.3f >= %.3f | price=%.2f | candle=%s",
                            self.instrument, p_min, self._threshold, close,
                            candle.get("timestamp"),
                        )
                    self._entry_price = close  # guards against re-entry; overridden by fill price in on_order_update
                    self._held_bars = 0
                    self._candles_since_train += 1
                    atr_stop = self._compute_atr(list(self._candles), period=self._atr_period)
                    if self._atr_stop_mult > 0 and atr_stop > 0:
                        sl_hint = round(close - self._atr_stop_mult * atr_stop, 2)
                    else:
                        sl_hint = round(close * (1 - self._stop_pct / 100), 2)
                    self._entry_stop = sl_hint
                    return Signal(
                        instrument=self.instrument,
                        direction=Direction.BUY,
                        signal_type=SignalType.ENTRY,
                        price_hint=close,
                        strategy=self.name,
                        atr=atr_stop,
                        stop_loss_hint=sl_hint,
                        target_price=None,  # trailing stop manages upside; no fixed target
                    )

        self._candles_since_train += 1
        return None

    def on_tick(self, tick: dict) -> Signal | None:
        """
        Called on every raw tick (live) or simulated tick (backtest).
        Handles hard stop and trailing stop at tick speed.
        Entry logic stays in on_candle.
        """
        if self.is_flat() or self._entry_price is None:
            return None

        last_price = tick.get("last_price")
        if last_price is None:
            return None

        # Update high-water mark
        if self._peak_close is None or last_price > self._peak_close:
            self._peak_close = last_price

        # Activate trailing once minimum profit floor is reached
        pct = (last_price - self._entry_price) / self._entry_price * 100.0
        if not self._trailing_active and pct >= self._profit_pct:
            self._trailing_active = True
            logger.info(
                "LR-Extrema TRAILING activated | %s | pct=+%.2f%% >= floor=%.2f%% | peak=%.2f",
                self.instrument, pct, self._profit_pct, self._peak_close,
            )

        reason: str | None = None
        if self._entry_stop is not None:
            if last_price <= self._entry_stop:
                reason = f"stop-loss @ {self._entry_stop:.2f}"
        elif pct <= -self._stop_pct:
            reason = f"stop-loss {pct:.2f}%"
        if reason is None and self._trailing_active:
            drawdown = (last_price - self._peak_close) / self._peak_close * 100.0
            if drawdown <= -self._trail_pct:
                reason = f"trailing stop {drawdown:.2f}% from peak {self._peak_close:.2f}"

        if reason:
            logger.info(
                "LR-Extrema EXIT (tick) | %s | %s | entry=%.2f price=%.2f",
                self.instrument, reason, self._entry_price, last_price,
            )
            if "stop-loss" in reason:
                until = self._compute_sl_cooldown_until()
                if until is not None:
                    self._sl_cooldown_until = until
                    logger.info(
                        "LR-Extrema SL COOLDOWN | %s | blocking re-entry until %s",
                        self.instrument, self._sl_cooldown_until,
                    )
            self._reset_position_state()
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.EXIT,
                price_hint=last_price,
                strategy=self.name,
            )

        return None

    @property
    def sl_cooldown_until(self) -> datetime | None:
        return self._sl_cooldown_until

    def seed_sl_cooldown(self, expiry_ts: float) -> None:
        """Restore SL cooldown from SQLite on restart. expiry_ts is a Unix timestamp; 0.0 means none.
        Honors current config: if sl_cooldown_bars=0 (disabled), stored value is ignored.
        If the stored expiry has already passed, it is silently discarded."""
        if self._sl_cooldown_bars == 0 or expiry_ts <= 0:
            return
        until = datetime.fromtimestamp(expiry_ts)
        if until > datetime.now():
            self._sl_cooldown_until = until
            logger.info(
                "LR-Extrema SL cooldown restored | %s | until=%s",
                self.instrument, until,
            )

    def _compute_sl_cooldown_until(self) -> datetime | None:
        """Return the datetime until which re-entry should be blocked after an SL hit.

        Converts sl_cooldown_bars (market bars) to calendar time so the cooldown
        remains correct across overnight gaps and weekends.

        Formula: calendar_days = (bars / bars_per_trading_day) × (7/5)
        The 7/5 factor converts trading days to calendar days (5 trading days per week).
        For 96 bars on 15min: (96/25) × 1.4 = 5.38 calendar days.
        """
        if self._sl_cooldown_bars <= 0 or self._last_candle_ts is None or self._candle_minutes <= 0:
            return None
        _MARKET_MINUTES_PER_DAY = 375  # 9:15–15:30
        bars_per_day = _MARKET_MINUTES_PER_DAY / self._candle_minutes
        trading_days = self._sl_cooldown_bars / bars_per_day
        calendar_days = trading_days * 7 / 5
        return self._last_candle_ts + timedelta(days=calendar_days)

    def _reset_position_state(self) -> None:
        """Clear all position-tracking fields. Called on any exit path."""
        self._entry_price = None
        self._entry_stop = None
        self._held_bars = 0
        self._peak_close = None
        self._trailing_active = False

    def on_order_update(self, order: dict) -> None:
        super().on_order_update(order)
        status = order.get("status", "")
        signal_type = order.get("signal_type", "")
        if status == "COMPLETE":
            if signal_type == SignalType.ENTRY:
                fill_price = order.get("price") or order.get("average_price")
                if fill_price:
                    self._entry_price = float(fill_price)
                # Restore held_bars from synthetic fill on restart; normal fills pass 0 
                held_bars = order.get("_held_bars")   
                self._held_bars = int(held_bars) if held_bars is not None else 0 
            elif signal_type == SignalType.EXIT:
                # Set SL cooldown if not already set by on_tick (covers backtest intrabar path)
                exit_reason = order.get("exit_reason", "")
                if exit_reason == "SL" and self._sl_cooldown_until is None:
                    until = self._compute_sl_cooldown_until()
                    if until is not None:
                        self._sl_cooldown_until = until
                        logger.info(
                            "LR-Extrema SL COOLDOWN | %s | blocking re-entry until %s",
                            self.instrument, self._sl_cooldown_until,
                        )
                self._reset_position_state()
        elif status in ("REJECTED", "CANCELLED"):
            if signal_type == SignalType.ENTRY:
                logger.warning(
                    "LR-Extrema | %s | ENTRY order %s — clearing entry guard",
                    self.instrument, status,
                )
                self._reset_position_state()

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def _train(self) -> None:
        candles = list(self._candles)

        if self._is_regression:
            # Regression path: continuous forward-return labels → XGBRegressor
            rows, labels = self._build_forward_return_labels(candles)
            if len(rows) < _MIN_REGRESSION_SAMPLES:
                return
            if not _XGBOOST_AVAILABLE:
                logger.warning("LR-Extrema | %s | XGBoost not available — regression requires XGBoost, skipping train", self.instrument)
                return
            X = np.array(rows, dtype=float)
            y = np.array(labels, dtype=float)
            model = _XGBRegressor(
                n_estimators=self._xgb_n_estimators,
                max_depth=self._xgb_max_depth,
                learning_rate=self._xgb_learning_rate,
                objective="reg:squarederror",
                verbosity=0,
                random_state=42,
            )
            model.fit(X, y)
            self._scaler = None
            fi = model.feature_importances_
            top3 = sorted(enumerate(fi), key=lambda kv: kv[1], reverse=True)[:3]
            logger.info(
                "XGB Regressor trained | %s | samples=%d | top features: %s",
                self.instrument, len(rows), [(i, f"{v:.3f}") for i, v in top3],
            )
        else:
            # Classification path: extrema binary labels → XGBClassifier or LR
            rows, labels = self._build_extrema_labels(candles)
            if len(rows) < _MIN_SAMPLES_PER_CLASS * 2:
                return
            n_pos = sum(1 for l in labels if l == 1)
            n_neg = sum(1 for l in labels if l == 0)
            if n_pos < _MIN_SAMPLES_PER_CLASS or n_neg < _MIN_SAMPLES_PER_CLASS:
                logger.warning(
                    "LR-Extrema | %s | not enough samples per class (buy=%d nobuy=%d)",
                    self.instrument, n_pos, n_neg,
                )
                return
            X = np.array(rows, dtype=float)
            y = np.array(labels, dtype=int)
            if self._model_type == "xgboost" and _XGBOOST_AVAILABLE:
                model = _XGBClassifier(
                    n_estimators=self._xgb_n_estimators,
                    max_depth=self._xgb_max_depth,
                    learning_rate=self._xgb_learning_rate,
                    eval_metric="logloss",
                    verbosity=0,
                    random_state=42,
                )
                model.fit(X, y)
                self._scaler = None
                fi = model.feature_importances_
                top3 = sorted(enumerate(fi), key=lambda kv: kv[1], reverse=True)[:3]
                logger.info(
                    "XGB Classifier trained | %s | mode=%s samples=%d (buy=%d nobuy=%d) | top features: %s",
                    self.instrument, self._label_mode, len(rows), n_pos, n_neg,
                    [(i, f"{v:.3f}") for i, v in top3],
                )
            else:
                if self._model_type == "xgboost":
                    logger.warning("XGBoost not available — falling back to LogisticRegression")
                scaler = MinMaxScaler()
                X_scaled = scaler.fit_transform(X)
                model = LogisticRegression(max_iter=1000, solver="lbfgs", class_weight="balanced")
                model.fit(X_scaled, y)
                self._scaler = scaler
                logger.info(
                    "LR trained | %s | mode=%s samples=%d (buy=%d nobuy=%d)",
                    self.instrument, self._label_mode, len(rows), n_pos, n_neg,
                )

        self._model = model
        self._trained = True

    def _predict_proba(self, x: np.ndarray) -> np.ndarray:
        """Run classifier inference. Scales for LR; passes raw features for XGBoost."""
        x_in = self._scaler.transform(x.reshape(1, -1)) if self._scaler is not None else x.reshape(1, -1)
        return self._model.predict_proba(x_in)[0]

    def _predict_return(self, x: np.ndarray) -> float:
        """Run regressor inference. Returns expected forward return as a float."""
        return float(self._model.predict(x.reshape(1, -1))[0])

    def _build_extrema_labels(
        self, candles: list[dict]
    ) -> tuple[list[np.ndarray], list[int]]:
        """Original label method — local minima (0) and maxima (1) by neighbourhood window.
        Has look-ahead contamination in training labels: a candle is confirmed as a minimum
        only after observing extrema_order future candles."""
        closes = [c["close"] for c in candles]
        minima, maxima = self._find_local_extrema(closes, self._extrema_order)
        rows, labels = [], []
        for label, indices in ((0, minima), (1, maxima)):
            for idx in indices:
                feat = self._compute_features(candles[: idx + 1])
                if feat is not None:
                    rows.append(feat)
                    labels.append(label)
        return rows, labels

    def _build_forward_return_labels(
        self, candles: list[dict]
    ) -> tuple[list[np.ndarray], list[float]]:
        """Continuous return label method.
        Label = close[t+horizon] / close[t] - 1 (raw forward return, not binarised).
        The model learns to predict the magnitude of future return, not just direction.
        Only candles with at least horizon future candles available are labelled, so
        the last label_horizon candles are excluded from training."""
        horizon = self._label_horizon
        rows, labels = [], []
        n = len(candles) - horizon
        for idx in range(n):
            feat = self._compute_features(candles[: idx + 1])
            if feat is None:
                continue
            fwd_return = (
                candles[idx + horizon]["close"] - candles[idx]["close"]
            ) / candles[idx]["close"]
            rows.append(feat)
            labels.append(fwd_return)
        return rows, labels

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def _compute_features(self, candles: list[dict]) -> np.ndarray | None:
        """Return feature vector for the last candle in *candles*, or None if not enough history.

        Features (11 total):
          0  volume_ratio    — current vol / rolling mean (scale-invariant)
          1  norm_price      — (close - low) / (high - low) within the bar
          2  slope3          — LR slope over last 3 % returns
          3  slope5          — LR slope over last 5 % returns
          4  slope10         — LR slope over last 10 % returns
          5  slope20         — LR slope over last 20 % returns
          6  atr_ratio       — ATR(atr_period) / close (normalised volatility)
          7  rsi             — RSI(atr_period) (0-100)
          8  ema20_dist      — (close - EMA20) / ATR(atr_period) (price position vs trend)
          9  nifty_slope20   — NIFTY 50 LR slope over last 20 returns (0.0 if unavailable)
          10 vix_norm        — India VIX / 30.0, capped at 2.0 (0.5 neutral if unavailable)
        """
        min_candles = max(21, self._atr_period + 1)
        if len(candles) < min_candles:
            return None
        if not isinstance(candles, list):
            candles = list(candles)
        last = candles[-1]
        closes = [c["close"] for c in candles]
        high, low, close = last["high"], last["low"], last["close"]

        norm_price = (close - low) / (high - low) if high != low else 0.5

        # Volume ratio: current candle volume vs rolling mean
        volumes = [c.get("volume", 0) for c in candles]
        vol_window = volumes[-self._volume_ma_bars:]
        vol_mean = sum(vol_window) / len(vol_window)
        volume_ratio = float(last.get("volume", 0)) / vol_mean if vol_mean > 0 else 1.0

        # % returns over last 21 closes → 20 return values
        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(len(closes) - 20, len(closes))
        ]
        slope3  = self._linreg_slope(returns[-3:])
        slope5  = self._linreg_slope(returns[-5:])
        slope10 = self._linreg_slope(returns[-10:])
        slope20 = self._linreg_slope(returns)

        # ATR and RSI both use atr_period for consistency with the stop-loss calculation
        atr = self._compute_atr(candles, period=self._atr_period)
        atr_ratio = atr / close if close > 0 else 0.0

        rsi = self._compute_rsi(closes, period=self._atr_period)

        # EMA-20 distance normalised by ATR
        ema20 = self._compute_ema(closes, period=20)
        ema20_dist = (close - ema20) / atr if atr > 0 else 0.0

        # Feature 9: NIFTY slope-20 — broad market momentum context
        nifty_vals = [c["_nifty_close"] for c in candles[-21:] if c.get("_nifty_close") is not None]
        if len(nifty_vals) >= 2:
            nifty_rets = [(nifty_vals[i] - nifty_vals[i - 1]) / nifty_vals[i - 1]
                          for i in range(1, len(nifty_vals))]
            nifty_slope20 = self._linreg_slope(nifty_rets[-20:])
        else:
            nifty_slope20 = 0.0  # neutral when regime data not available

        # Feature 10: India VIX normalised — fear/volatility regime
        # Scan from end to find most recent valid value — avoids full-list scan
        vix_last = next((c["_vix_close"] for c in reversed(candles) if c.get("_vix_close") is not None), None)
        vix_norm = min(vix_last / 30.0, 2.0) if vix_last is not None else 0.5

        return np.array(
            [volume_ratio, norm_price, slope3, slope5, slope10, slope20,
             atr_ratio, rsi, ema20_dist, nifty_slope20, vix_norm],
            dtype=float,
        )

    @staticmethod
    def _linreg_slope(prices: list[float]) -> float:
        """Ordinary least-squares slope of prices vs index."""
        n = len(prices)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2.0
        y_mean = sum(prices) / n
        num = sum((i - x_mean) * (prices[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        return num / den if den != 0.0 else 0.0

    @staticmethod
    def _compute_atr(candles: list[dict], period: int = 14) -> float:
        """Average True Range over the last *period* candles."""
        if len(candles) < period + 1:
            # Fall back to a simpler high-low average if not enough history
            highs = [c["high"] for c in candles[-period:]]
            lows  = [c["low"]  for c in candles[-period:]]
            return sum(h - l for h, l in zip(highs, lows)) / len(highs) if highs else 0.0
        trs = []
        for i in range(len(candles) - period, len(candles)):
            h, l, prev_c = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
            trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
        return sum(trs) / len(trs)

    @staticmethod
    def _compute_rsi(closes: list[float], period: int = 14) -> float:
        """RSI using Wilder's smoothed method. Returns value in [0, 100]."""
        if len(closes) < period + 1:
            return 50.0  # neutral when insufficient history
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains  = [max(d, 0.0) for d in deltas[-(period):]]
        losses = [abs(min(d, 0.0)) for d in deltas[-(period):]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _compute_ema(closes: list[float], period: int = 20) -> float:
        """Exponential moving average over *closes*, returning the last value."""
        if len(closes) < period:
            return closes[-1] if closes else 0.0
        k = 2.0 / (period + 1)
        ema = sum(closes[:period]) / period  # seed with SMA
        for price in closes[period:]:
            ema = price * k + ema * (1 - k)
        return ema

    @staticmethod
    def _find_local_extrema(
        closes: list[float], order: int
    ) -> tuple[list[int], list[int]]:
        """Return (minima_indices, maxima_indices) without scipy."""
        minima, maxima = [], []
        n = len(closes)
        for i in range(order, n - order):
            window = closes[i - order: i + order + 1]
            if closes[i] == min(window):
                minima.append(i)
            if closes[i] == max(window):
                maxima.append(i)
        return minima, maxima
