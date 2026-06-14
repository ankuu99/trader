"""
ExtremaEntryPolicy — the entry filter gates.

Moved verbatim from LRExtremaStrategy.on_candle's gate block (Stage 3). Given the
feature vector + candle history of a would-be entry, returns the list of gate-failure
strings ("blocks"). Empty list = all gates pass. The strategy still owns the model
prediction, threshold/veto decision, signal_log, and Signal construction; this class
owns only the hard filter gates.

All gates are disabled by default (0 / False / absent block). The parity golden
enforces byte-identical behaviour.
"""

from trader.features.indicators import macd_state, rsi_series, stoch_rsi_k


class ExtremaEntryPolicy:
    def __init__(self, params: dict):
        self._entry_min_volume_ratio: float = params.get("entry_min_volume_ratio", 0.0)
        self._entry_min_norm_price: float = params.get("entry_min_norm_price", 0.0)
        self._entry_require_prior_decline: bool = bool(params.get("entry_require_prior_decline", False))

        self._trend_gate_enabled: bool = bool(params.get("trend_gate_enabled", False))
        self._trend_gate_lookback: int = int(params.get("trend_gate_lookback", 100))
        self._trend_gate_min_return: float = float(params.get("trend_gate_min_return", -10.0))

        self._rsi_gate_enabled: bool = bool(params.get("rsi_gate_enabled", False))
        self._rsi_period: int = int(params.get("rsi_period", 14))
        self._rsi_gate_max: float = float(params.get("rsi_gate_max", 50.0))

        self._stoch_rsi_gate_enabled: bool = bool(params.get("stoch_rsi_gate_enabled", False))
        self._stoch_rsi_period: int = int(params.get("stoch_rsi_period", 14))
        self._stoch_rsi_smooth_k: int = int(params.get("stoch_rsi_smooth_k", 3))
        self._stoch_rsi_gate_max: float = float(params.get("stoch_rsi_gate_max", 20.0))

        self._macd_gate_enabled: bool = bool(params.get("macd_gate_enabled", False))
        self._macd_fast: int = int(params.get("macd_fast", 12))
        self._macd_slow: int = int(params.get("macd_slow", 26))
        self._macd_signal_period: int = int(params.get("macd_signal_period", 9))
        self._macd_slope_ma_period: int = int(params.get("macd_slope_ma_period", 3))
        self._macd_slope_threshold: float = float(params.get("macd_slope_threshold", 0.0))

        # Higher-timeframe (4h) trend-context gate. The regime classification
        # (_htf_downtrend / _htf_inversion) is precomputed by main.py / the backtest
        # engine and injected onto each candle dict — this gate only consumes it.
        self._ht_trend_gate_enabled: bool = bool(params.get("ht_trend_gate_enabled", False))
        self._ht_trend_rsi_downtrend_max: float = float(params.get("ht_trend_rsi_downtrend_max", 50.0))
        self._ht_trend_rsi_oversold: float = float(params.get("ht_trend_rsi_oversold", 30.0))

    def gate_blocks(self, x, candles: list[dict], close: float) -> list[str]:
        """Return the list of gate-failure reason strings for a would-be entry.
        *x* is the feature vector for the current candle; *candles* is the candle
        history (list); *close* the current close."""
        blocks: list[str] = []

        if self._entry_min_volume_ratio > 0 and x[0] < self._entry_min_volume_ratio:
            blocks.append(f"vol_ratio={x[0]:.2f}<{self._entry_min_volume_ratio}")
        if self._entry_min_norm_price > 0 and x[1] < self._entry_min_norm_price:
            blocks.append(f"norm_price={x[1]:.2f}<{self._entry_min_norm_price}")
        if self._entry_require_prior_decline and x[5] >= 0:
            blocks.append(f"slope20={x[5]:.4f}>=0 (no prior decline)")

        if self._trend_gate_enabled and len(candles) >= self._trend_gate_lookback:
            close_ref = candles[-self._trend_gate_lookback]["close"]
            trend_ret = (close - close_ref) / close_ref * 100.0 if close_ref > 0 else 0.0
            if trend_ret < self._trend_gate_min_return:
                blocks.append(
                    f"trend_ret={trend_ret:.1f}%<{self._trend_gate_min_return}% ({self._trend_gate_lookback}b)"
                )

        if self._rsi_gate_enabled:
            rsi_vals = rsi_series([c["close"] for c in candles], self._rsi_period)
            if not rsi_vals:
                blocks.append("rsi=N/A(insufficient data)")
            else:
                rsi_val = rsi_vals[-1]
                if rsi_val > self._rsi_gate_max:
                    blocks.append(f"rsi={rsi_val:.1f}>{self._rsi_gate_max}")

        if self._stoch_rsi_gate_enabled:
            stoch_k = stoch_rsi_k(
                [c["close"] for c in candles],
                self._stoch_rsi_period, self._stoch_rsi_smooth_k,
            )
            if stoch_k is None:
                blocks.append("stoch_rsi=N/A(insufficient data)")
            elif stoch_k > self._stoch_rsi_gate_max:
                blocks.append(f"stoch_rsi_k={stoch_k:.1f}>{self._stoch_rsi_gate_max}")

        if self._macd_gate_enabled:
            macd_st = macd_state(
                [c["close"] for c in candles],
                self._macd_fast,
                self._macd_slow,
                self._macd_signal_period,
                self._macd_slope_ma_period,
            )
            if macd_st is None:
                blocks.append("macd=N/A(insufficient data)")
            else:
                hist, avg_slope = macd_st
                if hist >= 0:
                    blocks.append(f"macd_hist={hist:.4f}>=0(not in negative zone)")
                elif avg_slope <= self._macd_slope_threshold:
                    blocks.append(
                        f"macd_avg_slope={avg_slope:.5f}<={self._macd_slope_threshold}(not converging)"
                    )

        if self._ht_trend_gate_enabled:
            cur = candles[-1] if candles else {}
            htf_rsi = cur.get("_htf_rsi")
            htf_macd_hist = cur.get("_htf_macd_hist")
            if htf_rsi is None or htf_macd_hist is None:
                pass  # insufficient HTF data — neutral, do not block
            elif cur.get("_htf_inversion"):
                pass  # inversion suspected — explicitly allow, overrides downtrend
            elif cur.get("_htf_downtrend"):
                blocks.append(
                    f"htf_downtrend: htf_rsi={htf_rsi:.1f}<{self._ht_trend_rsi_downtrend_max} "
                    f"& htf_macd_hist={htf_macd_hist:.4f}<0 (no inversion)"
                )

        return blocks
