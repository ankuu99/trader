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

Based on: github.com/kaneelgit/Trading-strategy-
Features: volume, normalised price, 3/5/10/20-bar linear-regression slopes.
"""

from collections import deque
from datetime import time

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import MinMaxScaler

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)

_MIN_SAMPLES_PER_CLASS = 2   # need at least this many of each class to train


class LRExtremaStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._warmup_bars: int = params.get("warmup_bars", 200)
        self._lookback_bars: int = params.get("lookback_bars", 600)
        self._threshold: float = params.get("threshold", 0.70)
        self._profit_pct: float = params.get("profit_pct", 3.0)
        self._trail_pct: float = params.get("trail_pct", 1.5)
        self._stop_pct: float = params.get("stop_pct", 3.0)
        self._hold_bars: int = params.get("hold_bars", 150)
        self._retrain_every: int = params.get("retrain_every", 50)
        self._extrema_order: int = params.get("extrema_order", 5)

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
        self._held_bars: int = 0
        self._peak_close: float | None = None   # highest close since entry
        self._trailing_active: bool = False     # True once profit_pct floor is hit

    @property
    def name(self) -> str:
        return f"LR-Extrema(w={self._warmup_bars},thr={self._threshold})"

    # ------------------------------------------------------------------
    # Core lifecycle
    # ------------------------------------------------------------------

    def on_candle(self, candle: dict) -> Signal | None:
        self._candles.append(candle)
        close = candle["close"]

        # --- Pending fill guard (entry order sent, awaiting fill) ---
        if self._entry_price is not None and self.is_flat():
            return None

        # --- Hold-bars timeout (candle-granularity is appropriate for a time cap) ---
        # Hard stop and trailing stop fire tick-by-tick via on_tick; hold_bars is
        # intentionally candle-based (a time limit, not a price level).
        if not self.is_flat():
            self._held_bars += 1
            if self._held_bars >= self._hold_bars:
                logger.info(
                    "LR-Extrema EXIT | %s | max hold (%d bars) | entry=%.2f close=%.2f | candle=%s",
                    self.instrument, self._held_bars, self._entry_price or 0, close,
                    candle.get("timestamp"),
                )
                self._entry_price = None
                self._held_bars = 0
                self._peak_close = None
                self._trailing_active = False
                return Signal(
                    instrument=self.instrument,
                    direction=Direction.BUY,
                    signal_type=SignalType.EXIT,
                    price_hint=close,
                    strategy=self.name,
                )

        # --- Warmup guard ---
        if len(self._candles) < self._warmup_bars:
            return None

        # --- Periodic retraining ---
        if not self._trained or self._candles_since_train >= self._retrain_every:
            self._train()
            self._candles_since_train = 0

        # --- Trading window gate (entry only) ---
        ts = candle.get("timestamp")
        if ts is not None:
            candle_time = ts.time() if hasattr(ts, "time") else None
            if candle_time is not None and not (self._trading_start <= candle_time <= self._trading_end):
                self._candles_since_train += 1
                return None

        # --- Entry prediction ---
        if self._trained and self.is_flat() and self._entry_price is None:
            x = self._compute_features(self._candles)
            if x is not None:
                x_scaled = self._scaler.transform(x.reshape(1, -1))
                classes = list(self._model.classes_)
                proba = self._model.predict_proba(x_scaled)[0]
                # class 0 = local minimum = buy candidate
                if 0 in classes:
                    p_min = proba[classes.index(0)]
                    if p_min >= self._threshold:
                        logger.info(
                            "LR-Extrema ENTRY | %s | P(min)=%.3f >= %.3f | price=%.2f | candle=%s",
                            self.instrument, p_min, self._threshold, close,
                            candle.get("timestamp"),
                        )
                        self._entry_price = close  # guards against re-entry; overridden by fill price in on_order_update
                        self._held_bars = 0
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
        if pct <= -self._stop_pct:
            reason = f"stop-loss {pct:.2f}%"
        elif self._trailing_active:
            drawdown = (last_price - self._peak_close) / self._peak_close * 100.0
            if drawdown <= -self._trail_pct:
                reason = f"trailing stop {drawdown:.2f}% from peak {self._peak_close:.2f}"

        if reason:
            logger.info(
                "LR-Extrema EXIT (tick) | %s | %s | entry=%.2f price=%.2f",
                self.instrument, reason, self._entry_price, last_price,
            )
            self._entry_price = None
            self._held_bars = 0
            self._peak_close = None
            self._trailing_active = False
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.EXIT,
                price_hint=last_price,
                strategy=self.name,
            )

        return None

    def on_order_update(self, order: dict) -> None:
        super().on_order_update(order)
        status = order.get("status", "")
        signal_type = order.get("signal_type", "")
        if status == "COMPLETE":
            if signal_type == SignalType.ENTRY:
                fill_price = order.get("price") or order.get("average_price")
                if fill_price:
                    self._entry_price = float(fill_price)
                held_bars = order.get("_held_bars")
                self._held_bars = int(held_bars) if held_bars is not None else 0
            elif signal_type == SignalType.EXIT:
                self._entry_price = None
                self._peak_close = None
                self._trailing_active = False
        elif status in ("REJECTED", "CANCELLED"):
            if signal_type == SignalType.ENTRY:
                logger.warning(
                    "LR-Extrema | %s | ENTRY order %s — clearing entry guard",
                    self.instrument, status,
                )
                self._entry_price = None
                self._held_bars = 0
                self._peak_close = None
                self._trailing_active = False

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def _train(self) -> None:
        # Snapshot the deque once — deque does not support slice notation and
        # a consistent list is needed for indexed access throughout training.
        candles = list(self._candles)
        closes = [c["close"] for c in candles]
        minima, maxima = self._find_local_extrema(closes, self._extrema_order)

        if len(minima) < _MIN_SAMPLES_PER_CLASS or len(maxima) < _MIN_SAMPLES_PER_CLASS:
            logger.warning(
                "LR-Extrema | %s | not enough extrema to train (min=%d max=%d)",
                self.instrument, len(minima), len(maxima),
            )
            return

        rows, labels = [], []
        for idx in minima:
            feat = self._compute_features(candles[: idx + 1])
            if feat is not None:
                rows.append(feat)
                labels.append(0)
        for idx in maxima:
            feat = self._compute_features(candles[: idx + 1])
            if feat is not None:
                rows.append(feat)
                labels.append(1)

        if len(rows) < _MIN_SAMPLES_PER_CLASS * 2:
            return

        X = np.array(rows, dtype=float)
        y = np.array(labels, dtype=int)

        scaler = MinMaxScaler()
        X_scaled = scaler.fit_transform(X)

        model = LogisticRegression(max_iter=1000, solver="lbfgs")
        model.fit(X_scaled, y)

        self._scaler = scaler
        self._model = model
        self._trained = True
        logger.info(
            "LR-Extrema trained | %s | samples=%d (min=%d max=%d)",
            self.instrument, len(rows), labels.count(0), labels.count(1),
        )

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def _compute_features(self, candles: list[dict]) -> np.ndarray | None:
        """Return feature vector [volume, norm_price, slope3, slope5, slope10, slope20]
        for the last candle in *candles*, or None if not enough history."""
        if len(candles) < 20:
            return None
        last = candles[-1]
        closes = [c["close"] for c in candles]
        high, low, close = last["high"], last["low"], last["close"]

        norm_price = (close - low) / (high - low) if high != low else 0.5
        volume = float(last.get("volume", 0))

        slope3  = self._linreg_slope(closes[-3:])
        slope5  = self._linreg_slope(closes[-5:])
        slope10 = self._linreg_slope(closes[-10:])
        slope20 = self._linreg_slope(closes[-20:])

        return np.array([volume, norm_price, slope3, slope5, slope10, slope20], dtype=float)

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
