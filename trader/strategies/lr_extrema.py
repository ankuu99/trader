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
    volume_ma_bars      : rolling window for volume normalisation          (default 20)

Based on: github.com/kaneelgit/Trading-strategy-
Features: volume, normalised price, 3/5/10/20-bar linear-regression slopes.
"""

from collections import deque
from datetime import  time

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import MinMaxScaler

from trader.core.config import config
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
        self._sell_threshold: float = params.get("sell_threshold", 0.65)
        self._sell_min_pct: float = params.get("sell_min_pct", 2.0)
        self._veto_threshold: float = params.get("veto_threshold", 0.50)
        self._min_hold_before_exit: int = params.get("min_hold_before_exit", 3)
        self._volume_ma_bars: int = params.get("volume_ma_bars", 20)

        # --- Entry filter gates (disabled by default — 0/False means off) ---
        self._entry_min_volume_ratio: float = params.get("entry_min_volume_ratio", 0.0)
        self._entry_min_norm_price: float = params.get("entry_min_norm_price", 0.0)
        self._entry_require_prior_decline: bool = bool(params.get("entry_require_prior_decline", False))

        # RSI gate — RSI must be <= rsi_gate_max (oversold confirmation)
        self._rsi_gate_enabled: bool = bool(params.get("rsi_gate_enabled", False))
        self._rsi_period: int = int(params.get("rsi_period", 14))
        self._rsi_gate_max: float = float(params.get("rsi_gate_max", 50.0))

        # Stochastic RSI gate — K line must be <= stoch_rsi_gate_max (deeply oversold)
        self._stoch_rsi_gate_enabled: bool = bool(params.get("stoch_rsi_gate_enabled", False))
        self._stoch_rsi_period: int = int(params.get("stoch_rsi_period", 14))
        self._stoch_rsi_smooth_k: int = int(params.get("stoch_rsi_smooth_k", 3))
        self._stoch_rsi_gate_max: float = float(params.get("stoch_rsi_gate_max", 20.0))

        # MACD gate — histogram must be negative but slope converging toward 0
        self._macd_gate_enabled: bool = bool(params.get("macd_gate_enabled", False))
        self._macd_fast: int = int(params.get("macd_fast", 12))
        self._macd_slow: int = int(params.get("macd_slow", 26))
        self._macd_signal_period: int = int(params.get("macd_signal_period", 9))
        self._macd_slope_ma_period: int = int(params.get("macd_slope_ma_period", 3))
        self._macd_slope_threshold: float = float(params.get("macd_slope_threshold", 0.0))

        # --- NEW EXIT FEATURES (all disabled by default) ---

        # Feature 1: Progress gate — exit if trade hasn't shown meaningful gain after N bars.
        # Tracks _max_gain_pct (best gain since entry). If after stale_check_bars bars the
        # best gain never exceeded stale_min_gain_pct%, the thesis is dead — exit.
        self._stale_exit_enabled: bool = bool(params.get("stale_exit_enabled", False))
        self._stale_check_bars: int = int(params.get("stale_check_bars", 20))
        self._stale_min_gain_pct: float = float(params.get("stale_min_gain_pct", 0.5))

        # Feature 2: Breakeven stop — once position gains breakeven_trigger_pct, move the
        # effective hard stop to entry_price * (1 + breakeven_buffer_pct/100).
        # Prevents a profitable trade from turning into a loss. Checked on every tick.
        self._breakeven_stop_enabled: bool = bool(params.get("breakeven_stop_enabled", False))
        self._breakeven_trigger_pct: float = float(params.get("breakeven_trigger_pct", 1.0))
        self._breakeven_buffer_pct: float = float(params.get("breakeven_buffer_pct", 0.0))
        self._breakeven_active: bool = False  # True once trigger_pct has been reached

        # Feature 3: Momentum decay exit — if P(local-min) drops below momentum_exit_p_min_floor
        # while the position is flat/slightly positive (below sell_min_pct), exit early.
        # Interpretation: model no longer believes this was a bottom; get out before the stop.
        self._momentum_exit_enabled: bool = bool(params.get("momentum_exit_enabled", False))
        self._momentum_exit_p_min_floor: float = float(params.get("momentum_exit_p_min_floor", 0.35))
        self._momentum_exit_min_bars: int = int(params.get("momentum_exit_min_bars", 5))

        def _parse_time(val: str | None, default: time) -> time:
            if val is None:
                return default
            h, m = val.split(":")
            return time(int(h), int(m))
        
        # E4: Force close trailing positions before market end (None = disabled)
        _ftic = params.get("force_trailing_close_time")
        self._force_trailing_close = _parse_time(_ftic, time(15, 25)) if _ftic else None

        self._candles: deque = deque(maxlen=self._lookback_bars)
        self._model: LogisticRegression | None = None
        self._scaler: MinMaxScaler | None = None
        self._trained: bool = False
        self._candles_since_train: int = 0

        # exit tracking
        self._entry_price: float | None = None
        self._fill_price: float | None = None   # confirmed fill price; survives _reset_position_state()
        self._held_bars: int = 0
        self._peak_close: float | None = None   # highest close since entry
        self._trailing_active: bool = False     # True once profit_pct floor is hit
        self._pattern_top_trailing: bool = False  # True when trailing activated by pattern-top detection
        self._max_gain_pct: float = 0.0         # best % gain seen since entry (feature 1: progress gate)
        self._breakeven_active: bool = False    # True once breakeven stop has been armed (feature 2)

        # set to the block reason string when an entry is filtered; None otherwise
        self.last_filter_block: str | None = None
        # each entry: {timestamp, close, p_min, p_max, type} — type is
        # ENTRY | BLOCKED | VETOED | PATTERN_TOP; populated on every threshold crossing
        self.signal_log: list[dict] = []

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

        # --- Trading window gate (all signals, entry and exit) ---
        # Checked once here so all exit paths (hold_bars, pattern_top) and entry
        # are gated in a single place.  Does NOT modify state — the position survives
        # outside the window; the SL / hold_bars exit will fire on the next in-window candle.
        ts = candle.get("timestamp")
        _candle_time = ts.time() if (ts is not None and hasattr(ts, "time")) else None
        _outside_window = (
            _candle_time is not None
            and not (config.trading_start <= _candle_time <= config.trading_end)
        )
        if _outside_window:
            self._candles_since_train += 1
            return None

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
                timestamp=candle.get("timestamp"),
            )

        # --- Feature 1: Progress gate (stale trade exit) ---
        # Tracks the best gain ever seen since entry. If after stale_check_bars the best
        # gain has never exceeded stale_min_gain_pct, the trade is going nowhere — exit.
        _pct_gain = (
            (close - self._entry_price) / self._entry_price * 100.0
            if self._entry_price else 0.0
        )
        if not self.is_flat() and self._entry_price is not None:
            if _pct_gain > self._max_gain_pct:
                self._max_gain_pct = _pct_gain
        if (self._stale_exit_enabled
                and not self.is_flat()
                and self._entry_price is not None
                and self._held_bars >= self._stale_check_bars
                and self._max_gain_pct < self._stale_min_gain_pct):
            logger.info(
                "LR-Extrema EXIT (stale) | %s | held=%d bars, best_gain=%.2f%% < %.2f%% | entry=%.2f close=%.2f | candle=%s",
                self.instrument, self._held_bars, self._max_gain_pct, self._stale_min_gain_pct,
                self._entry_price, close, candle.get("timestamp"),
            )
            self._reset_position_state()
            self._candles_since_train += 1
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.EXIT,
                price_hint=close,
                strategy=self.name,
                exit_reason="STALE",
                timestamp=candle.get("timestamp"),
            )

        # --- Feature 3: Momentum decay exit (on-candle) ---
        # If model's P(local-min) drops below momentum_exit_p_min_floor while the position
        # is flat/slightly positive (below sell_min_pct), the bottom thesis has failed — exit.
        if (self._momentum_exit_enabled
                and not self.is_flat()
                and self._trained
                and self._entry_price is not None
                and self._held_bars >= self._momentum_exit_min_bars
                and _pct_gain < self._sell_min_pct):
            x = self._compute_features(self._candles)
            if x is not None:
                x_scaled = self._scaler.transform(x.reshape(1, -1))
                classes = list(self._model.classes_)
                proba = self._model.predict_proba(x_scaled)[0]
                p_min = proba[classes.index(0)] if 0 in classes else 1.0
                if p_min < self._momentum_exit_p_min_floor:
                    logger.info(
                        "LR-Extrema EXIT (momentum-decay) | %s | P(min)=%.3f < %.3f | gain=%.2f%% | held=%d | candle=%s",
                        self.instrument, p_min, self._momentum_exit_p_min_floor,
                        _pct_gain, self._held_bars, candle.get("timestamp"),
                    )
                    self._reset_position_state()
                    self._candles_since_train += 1
                    return Signal(
                        instrument=self.instrument,
                        direction=Direction.BUY,
                        signal_type=SignalType.EXIT,
                        price_hint=close,
                        strategy=self.name,
                        exit_reason="MOMENTUM_DECAY",
                        timestamp=candle.get("timestamp"),
                    )

        # --- Model-based exit (pattern top detection, on-candle) ---
        # Fires when P(local-max) >= sell_threshold after min_hold_before_exit bars,
        # but only when gain >= sell_min_pct — stop_pct handles underwater/small exits.
        if (not self.is_flat() and self._trained
                and self._held_bars >= self._min_hold_before_exit
                and _pct_gain >= self._sell_min_pct):
            x = self._compute_features(self._candles)
            if x is not None:
                x_scaled = self._scaler.transform(x.reshape(1, -1))
                classes = list(self._model.classes_)
                proba = self._model.predict_proba(x_scaled)[0]
                if 1 in classes:
                    p_max = proba[classes.index(1)]
                    if p_max >= self._sell_threshold:
                        self.signal_log.append({
                            "timestamp": candle.get("timestamp"),
                            "close": close,
                            "p_min": proba[classes.index(0)] if 0 in classes else 0.0,
                            "p_max": p_max,
                            "type": "PATTERN_TOP",
                        })
                        if not self._pattern_top_trailing:
                            if not self._trailing_active:
                                self._trailing_active = True
                                if self._peak_close is None:
                                    self._peak_close = close
                            self._pattern_top_trailing = True
                            logger.info(
                                "LR-Extrema PATTERN-TOP TRAILING | %s | P(max)=%.3f >= %.3f | price=%.2f | candle=%s",
                                self.instrument, p_max, self._sell_threshold, close,
                                candle.get("timestamp"),
                            )

        # --- Entry prediction ---
        # Both gates must pass: P(local-min) >= threshold AND P(local-max) < veto_threshold.
        # The veto prevents entering when the model simultaneously thinks a top is forming.
        if self._trained and self.is_flat() and self._entry_price is None:
            x = self._compute_features(self._candles)
            if x is not None:
                x_scaled = self._scaler.transform(x.reshape(1, -1))
                classes = list(self._model.classes_)
                proba = self._model.predict_proba(x_scaled)[0]
                p_min = proba[classes.index(0)] if 0 in classes else 0.0
                p_max = proba[classes.index(1)] if 1 in classes else 1.0
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
                    # Hard filter gates — collected so all failures are logged together
                    blocks: list[str] = []
                    if self._entry_min_volume_ratio > 0 and x[0] < self._entry_min_volume_ratio:
                        blocks.append(f"vol_ratio={x[0]:.2f}<{self._entry_min_volume_ratio}")
                    if self._entry_min_norm_price > 0 and x[1] < self._entry_min_norm_price:
                        blocks.append(f"norm_price={x[1]:.2f}<{self._entry_min_norm_price}")
                    if self._entry_require_prior_decline and x[5] >= 0:
                        blocks.append(f"slope20={x[5]:.4f}>=0 (no prior decline)")

                    if self._rsi_gate_enabled:
                        rsi_series = self._rsi_series(
                            [c["close"] for c in self._candles], self._rsi_period
                        )
                        if not rsi_series:
                            blocks.append("rsi=N/A(insufficient data)")
                        else:
                            rsi_val = rsi_series[-1]
                            if rsi_val > self._rsi_gate_max:
                                blocks.append(f"rsi={rsi_val:.1f}>{self._rsi_gate_max}")

                    if self._stoch_rsi_gate_enabled:
                        stoch_k = self._compute_stoch_rsi_k(
                            self._candles, self._stoch_rsi_period, self._stoch_rsi_smooth_k
                        )
                        if stoch_k is None:
                            blocks.append("stoch_rsi=N/A(insufficient data)")
                        elif stoch_k > self._stoch_rsi_gate_max:
                            blocks.append(f"stoch_rsi_k={stoch_k:.1f}>{self._stoch_rsi_gate_max}")

                    if self._macd_gate_enabled:
                        macd_state = self._compute_macd_state(
                            self._candles,
                            self._macd_fast,
                            self._macd_slow,
                            self._macd_signal_period,
                            self._macd_slope_ma_period,
                        )
                        if macd_state is None:
                            blocks.append("macd=N/A(insufficient data)")
                        else:
                            hist, avg_slope = macd_state
                            if hist >= 0:
                                blocks.append(f"macd_hist={hist:.4f}>=0(not in negative zone)")
                            elif avg_slope <= self._macd_slope_threshold:
                                blocks.append(
                                    f"macd_avg_slope={avg_slope:.5f}<={self._macd_slope_threshold}(not converging)"
                                )

                    if blocks:
                        _log_entry["type"] = "BLOCKED"
                        self.last_filter_block = ", ".join(blocks)
                        logger.debug(
                            "LR-Extrema ENTRY BLOCKED | %s | %s | candle=%s",
                            self.instrument, self.last_filter_block, candle.get("timestamp"),
                        )
                        self._candles_since_train += 1
                        return None

                    logger.info(
                        "LR-Extrema ENTRY | %s | P(min)=%.3f >= %.3f | P(max)=%.3f < %.3f | price=%.2f | candle=%s",
                        self.instrument, p_min, self._threshold, p_max, self._veto_threshold, close,
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
                        timestamp=candle.get("timestamp"),
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

        # Trading window gate — no SL/trailing exits outside the window
        ts = tick.get("timestamp")
        tick_time = ts.time() if (ts is not None and hasattr(ts, "time")) else None
        if tick_time is not None and not (config.trading_start <= tick_time <= config.trading_end):
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
        # E4: Force close trailing positions before overnight gap risk (tick-level precision)
        if self._trailing_active and self._force_trailing_close is not None:
            _tick_ts = tick.get("timestamp")
            _tick_time = _tick_ts.time() if hasattr(_tick_ts, "time") else None
            if _tick_time is not None and _tick_time >= self._force_trailing_close:
                logger.info(
                    "LR-Extrema TRAILING EOD CLOSE | %s | price=%.2f",
                    self.instrument, last_price,
                )
                self._reset_position_state()
                return Signal(
                    instrument=self.instrument,
                    direction=Direction.BUY,
                    signal_type=SignalType.EXIT,
                    price_hint=last_price,
                    strategy=self.name,
                    exit_reason="TRAILING_EOD_CLOSE",
                )

        # Feature 2: Breakeven stop — arm once trigger_pct gain is reached; then hard stop
        # moves up to entry + buffer. Checked before the normal stop so it fires first.
        if self._breakeven_stop_enabled and not self._breakeven_active and pct >= self._breakeven_trigger_pct:
            self._breakeven_active = True
            logger.info(
                "LR-Extrema BREAKEVEN armed | %s | pct=+%.2f%% >= trigger=%.2f%% | floor=entry+%.2f%%",
                self.instrument, pct, self._breakeven_trigger_pct, self._breakeven_buffer_pct,
            )

        reason: str | None = None
        if self._breakeven_stop_enabled and self._breakeven_active:
            be_floor = self._entry_price * (1.0 + self._breakeven_buffer_pct / 100.0)
            if last_price <= be_floor:
                reason = f"breakeven stop price={last_price:.2f} <= floor={be_floor:.2f}"
        if reason is None and pct <= -self._stop_pct:
            reason = f"stop-loss {pct:.2f}%"
        elif reason is None and self._trailing_active:
            drawdown = (last_price - self._peak_close) / self._peak_close * 100.0
            if drawdown <= -self._trail_pct:
                reason = f"trailing stop {drawdown:.2f}% from peak {self._peak_close:.2f}"
        # Trailing floor — pattern-top trailing uses sell_min_pct as floor (the minimum gain
        # that triggered detection); regular trailing uses profit_pct.
        # Strict < avoids firing on the same tick trailing activates.
        _floor_pct = self._sell_min_pct if self._pattern_top_trailing else self._profit_pct
        if reason is None and self._trailing_active and pct < _floor_pct:
            reason = f"trailing floor pct={pct:.2f}% < {_floor_pct:.2f}%"

        if reason:
            logger.info(
                "LR-Extrema EXIT (tick) | %s | %s | entry=%.2f price=%.2f",
                self.instrument, reason, self._entry_price, last_price,
            )
            self._reset_position_state()
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.EXIT,
                price_hint=last_price,
                strategy=self.name,
                timestamp=tick.get("timestamp"),
            )

        return None

    def _reset_position_state(self) -> None:
        """Clear all position-tracking fields. Called on any exit path."""
        self._entry_price = None
        self._held_bars = 0
        self._peak_close = None
        self._trailing_active = False
        self._pattern_top_trailing = False
        self._max_gain_pct = 0.0
        self._breakeven_active = False

    def on_order_update(self, order: dict) -> None:
        super().on_order_update(order)
        status = order.get("status", "")
        signal_type = order.get("signal_type", "")
        if status == "COMPLETE":
            if signal_type == SignalType.ENTRY:
                fill_price = order.get("price") or order.get("average_price")
                if fill_price:
                    self._entry_price = float(fill_price)
                    self._fill_price = float(fill_price)  # preserve confirmed fill for retrigger
                # Restore held_bars from synthetic fill on restart; normal fills pass 0
                held_bars = order.get("_held_bars")
                self._held_bars = int(held_bars) if held_bars is not None else 0
            elif signal_type == SignalType.EXIT:
                self._reset_position_state()
        elif status in ("REJECTED", "CANCELLED"):
            if signal_type == SignalType.ENTRY:
                logger.warning(
                    "LR-Extrema | %s | ENTRY order %s — clearing entry guard",
                    self.instrument, status,
                )
                self._reset_position_state()
            elif signal_type == SignalType.EXIT:
                # EXIT order cancelled/rejected — restore entry state so SL/trailing can retrigger
                logger.warning(
                    "LR-Extrema | %s | EXIT order %s — restoring entry state for retrigger",
                    self.instrument, status,
                )
                if self._fill_price is not None:
                    self._entry_price = self._fill_price

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
        """Return feature vector [volume_ratio, norm_price, slope3, slope5, slope10, slope20]
        for the last candle in *candles*, or None if not enough history.

        Slopes are computed over % returns (first-order differences) rather than
        absolute prices, making features stationary and scale-invariant across
        different price levels and time periods.  Volume is normalised as a ratio
        to the rolling mean over volume_ma_bars candles for the same reason.
        """
        if len(candles) < 21:
            return None
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
        slope20 = self._linreg_slope(returns[-20:])

        return np.array([volume_ratio, norm_price, slope3, slope5, slope10, slope20], dtype=float)

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

    # ------------------------------------------------------------------
    # Indicator helpers (used by entry gate checks)
    # ------------------------------------------------------------------

    @staticmethod
    def _rsi_series(closes: list[float], period: int) -> list[float]:
        """SMA-based RSI series. Each value uses the preceding `period` deltas."""
        if len(closes) < period + 1:
            return []
        result = []
        for i in range(period, len(closes)):
            deltas = [closes[j] - closes[j - 1] for j in range(i - period + 1, i + 1)]
            avg_gain = sum(max(d, 0.0) for d in deltas) / period
            avg_loss = sum(abs(min(d, 0.0)) for d in deltas) / period
            if avg_loss == 0:
                result.append(100.0)
            else:
                result.append(100.0 - 100.0 / (1.0 + avg_gain / avg_loss))
        return result

    def _compute_stoch_rsi_k(
        self,
        candles,
        period: int,
        smooth_k: int,
    ) -> float | None:
        """Stochastic RSI K line. Uses `period` for both RSI and stochastic lookback.
        Returns None if there is insufficient data."""
        closes = [c["close"] for c in candles]
        rsi_vals = self._rsi_series(closes, period)
        if len(rsi_vals) < period + smooth_k - 1:
            return None
        stoch_vals = []
        for i in range(period - 1, len(rsi_vals)):
            window = rsi_vals[i - period + 1: i + 1]
            lo, hi = min(window), max(window)
            if hi == lo:
                stoch_vals.append(0.0)
            else:
                stoch_vals.append((window[-1] - lo) / (hi - lo) * 100.0)
        if len(stoch_vals) < smooth_k:
            return None
        return sum(stoch_vals[-smooth_k:]) / smooth_k

    @staticmethod
    def _ema_series(values: list[float], period: int) -> list[float]:
        """Standard EMA series seeded with the first-period SMA."""
        if len(values) < period:
            return []
        k = 2.0 / (period + 1)
        result = [sum(values[:period]) / period]
        for v in values[period:]:
            result.append(v * k + result[-1] * (1 - k))
        return result

    def _compute_macd_state(
        self,
        candles,
        fast: int,
        slow: int,
        signal_period: int,
        slope_ma_period: int,
    ) -> tuple[float, float] | None:
        """Returns (current_histogram, avg_slope) or None if insufficient data.

        avg_slope is the mean of the last `slope_ma_period` bar-to-bar histogram
        differences (y2-y1 with x spacing=1). A positive avg_slope means the
        histogram is consistently rising (converging toward 0 from negative).
        """
        closes = [c["close"] for c in candles]
        if len(closes) < slow + signal_period + slope_ma_period:
            return None
        ema_fast = self._ema_series(closes, fast)
        ema_slow = self._ema_series(closes, slow)
        if not ema_fast or not ema_slow:
            return None
        # Align fast EMA to match slow EMA length
        macd_vals = [ef - es for ef, es in zip(ema_fast[slow - fast:], ema_slow)]
        signal_ema = self._ema_series(macd_vals, signal_period)
        # signal_ema[i] corresponds to macd_vals[signal_period - 1 + i]
        sig_offset = signal_period - 1
        hist_series = [
            macd_vals[sig_offset + i] - signal_ema[i]
            for i in range(len(signal_ema))
        ]
        if len(hist_series) < slope_ma_period + 1:
            return None
        current_hist = hist_series[-1]
        slopes = [hist_series[i] - hist_series[i - 1] for i in range(-slope_ma_period, 0)]
        avg_slope = sum(slopes) / slope_ma_period
        return current_hist, avg_slope
