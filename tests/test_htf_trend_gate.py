"""
Tests for the 4h trend-context entry gate:
  - trader.features.indicators.htf_trend_regime()
  - ExtremaEntryPolicy's ht_trend gate_blocks branch
"""
import math

from trader.features.indicators import htf_trend_regime
from trader.policy.extrema_entry import ExtremaEntryPolicy


# ---------------------------------------------------------------------------
# Synthetic close series
# ---------------------------------------------------------------------------

def _downtrend_then_inversion_closes():
    """Up-move followed by an accelerating decline. Early truncations land in
    a continuous-downtrend regime (macd_hist<0, slope<=0); later truncations
    land in a macd-turning-up inversion (macd_hist still <0, slope>0)."""
    closes = [100.0]
    for _ in range(30):
        closes.append(closes[-1] * 1.01)
    for i in range(40):
        rate = 0.005 + i * 0.001
        closes.append(closes[-1] * (1 - rate))
    return closes


def _oversold_recovery_closes():
    """Oscillating series whose RSI dips below 30 and then rises — drives the
    'was oversold and is now rising' inversion path independent of MACD."""
    closes = [100.0]
    for i in range(80):
        closes.append(closes[-1] + math.sin(i / 5.0) * 1.5 - 0.3)
    return closes


_KWARGS = dict(
    rsi_period=14,
    macd_fast=12, macd_slow=26, macd_signal_period=9, macd_slope_ma_period=3,
    rsi_downtrend_max=50.0, rsi_oversold=30.0, oversold_lookback=6,
)


# ---------------------------------------------------------------------------
# htf_trend_regime()
# ---------------------------------------------------------------------------

def test_htf_trend_regime_insufficient_data_returns_none():
    assert htf_trend_regime([100.0, 101.0, 99.0], **_KWARGS) is None


def test_htf_trend_regime_downtrend():
    closes = _downtrend_then_inversion_closes()[:45]
    regime = htf_trend_regime(closes, **_KWARGS)
    assert regime is not None
    assert regime["macd_hist"] < 0
    assert regime["macd_slope"] <= 0
    assert regime["rsi"] < 50.0
    assert regime["downtrend"] is True
    assert regime["inversion"] is False


def test_htf_trend_regime_macd_turning_up_inversion():
    closes = _downtrend_then_inversion_closes()[:53]
    regime = htf_trend_regime(closes, **_KWARGS)
    assert regime is not None
    assert regime["macd_hist"] < 0
    assert regime["macd_slope"] > 0
    assert regime["downtrend"] is False
    assert regime["inversion"] is True


def test_htf_trend_regime_oversold_recovery_inversion():
    closes = _oversold_recovery_closes()[:40]
    regime = htf_trend_regime(closes, **_KWARGS)
    assert regime is not None
    assert regime["downtrend"] is False
    assert regime["inversion"] is True


# ---------------------------------------------------------------------------
# ExtremaEntryPolicy ht_trend gate
# ---------------------------------------------------------------------------

# Feature vector / close value are irrelevant to the ht_trend gate; use
# placeholders that don't trip the other (disabled) gates.
_X = [1.0, 0.5, 0.0, 0.0, 0.0, -0.1]
_CLOSE = 100.0


def _candle(**htf_fields):
    base = {"close": _CLOSE}
    base.update(htf_fields)
    return base


def test_ht_trend_gate_disabled_is_noop():
    policy = ExtremaEntryPolicy({"ht_trend_gate_enabled": False})
    candles = [_candle(_htf_rsi=40.0, _htf_macd_hist=-1.0, _htf_macd_slope=-0.1,
                        _htf_downtrend=True, _htf_inversion=False)]
    assert policy.gate_blocks(_X, candles, _CLOSE) == []


def test_ht_trend_gate_blocks_on_downtrend():
    policy = ExtremaEntryPolicy({"ht_trend_gate_enabled": True})
    candles = [_candle(_htf_rsi=40.0, _htf_macd_hist=-1.0, _htf_macd_slope=-0.1,
                        _htf_downtrend=True, _htf_inversion=False)]
    blocks = policy.gate_blocks(_X, candles, _CLOSE)
    assert any("htf_downtrend" in b for b in blocks)


def test_ht_trend_gate_inversion_overrides_downtrend():
    policy = ExtremaEntryPolicy({"ht_trend_gate_enabled": True})
    candles = [_candle(_htf_rsi=25.0, _htf_macd_hist=-1.0, _htf_macd_slope=0.2,
                        _htf_downtrend=True, _htf_inversion=True)]
    assert policy.gate_blocks(_X, candles, _CLOSE) == []


def test_ht_trend_gate_neutral_when_not_downtrend():
    policy = ExtremaEntryPolicy({"ht_trend_gate_enabled": True})
    candles = [_candle(_htf_rsi=60.0, _htf_macd_hist=0.5, _htf_macd_slope=0.1,
                        _htf_downtrend=False, _htf_inversion=False)]
    assert policy.gate_blocks(_X, candles, _CLOSE) == []


def test_ht_trend_gate_missing_htf_data_is_neutral():
    policy = ExtremaEntryPolicy({"ht_trend_gate_enabled": True})
    candles = [_candle(_htf_rsi=None, _htf_macd_hist=None,
                        _htf_macd_slope=None, _htf_downtrend=None, _htf_inversion=None)]
    assert policy.gate_blocks(_X, candles, _CLOSE) == []


def test_ht_trend_gate_block_reason_uses_configured_thresholds():
    policy = ExtremaEntryPolicy({
        "ht_trend_gate_enabled": True,
        "ht_trend_rsi_downtrend_max": 45.0,
        "ht_trend_rsi_oversold": 25.0,
    })
    candles = [_candle(_htf_rsi=40.0, _htf_macd_hist=-2.0, _htf_macd_slope=-0.05,
                        _htf_downtrend=True, _htf_inversion=False)]
    blocks = policy.gate_blocks(_X, candles, _CLOSE)
    assert len(blocks) == 1
    assert "45.0" in blocks[0]
    assert "htf_rsi=40.0" in blocks[0]
    assert "htf_macd_hist=-2.0000" in blocks[0]
