"""SwingFeaturePipeline (`features.type: swing`) + the `turn` entry gate."""

import numpy as np

from trader.core.config import flatten_strategy_params
from trader.features.registry import build_feature_pipeline
from trader.policy.extrema_entry import ExtremaEntryPolicy


def _candles(closes, volume=1000):
    out = []
    for i, c in enumerate(closes):
        out.append({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": volume})
    return out


def test_swing_pipeline_names_and_values():
    fp = build_feature_pipeline({"type": "swing", "swing": {
        "low_lookbacks": [5], "high_lookbacks": [5], "return_bars": [2], "rsi_period": 3}})
    assert fp.feature_names == ["volume_ratio", "above_low_5", "depth_5", "ret_2", "rsi_3"]
    assert fp.min_history == 20  # volume_ma_bars default dominates
    # 21 bars: falling then flat; last close 100, 5-bar window [104,103,102,101,100]
    closes = [120 - i for i in range(21)]
    x = fp.compute(_candles(closes))
    assert x is not None and len(x) == 5
    assert x[0] == 1.0                              # flat volume
    assert np.isclose(x[1], 0.0)                     # close IS the 5-bar low
    assert np.isclose(x[2], (100 - 104) / 104)       # depth from 5-bar high
    assert np.isclose(x[3], 100 / 102 - 1)           # 2-bar return
    assert np.isclose(x[4], 0.0)                     # RSI 0 on a straight decline
    assert fp.compute(_candles(closes[:10])) is None


def test_swing_pipeline_optional_norm_price():
    fp = build_feature_pipeline({"type": "swing", "swing": {"include_norm_price": True}})
    assert fp.feature_names[1] == "norm_price"


def test_default_pipeline_unchanged():
    assert build_feature_pipeline({}).feature_names[:2] == ["volume_ratio", "norm_price"]


def test_turn_gate_flatten_and_blocks():
    flat = flatten_strategy_params({"entry_gates": {"turn": {"lowest_of": 5}}})
    assert flat["turn_gate_enabled"] is True and flat["turn_gate_lowest_of"] == 5
    pol = ExtremaEntryPolicy(flat)
    x = np.zeros(7)
    # prev bar (99) is the lowest of the 5 before it; current closes up (100) -> pass
    c = _candles([105, 104, 103, 102, 101, 99, 100])
    assert pol.gate_blocks(x, c, 100) == []
    # current bar closes down -> blocked
    c = _candles([105, 104, 103, 102, 101, 99, 98])
    assert any("no up-close" in b for b in pol.gate_blocks(x, c, 98))
    # prev bar not the lowest of the window -> blocked
    c = _candles([105, 104, 90, 102, 101, 99, 100])
    assert any("not lowest" in b for b in pol.gate_blocks(x, c, 100))
    # too little history -> blocked (never silently passes)
    assert pol.gate_blocks(x, _candles([99, 100]), 100) == ["turn=N/A(insufficient data)"]


def test_turn_gate_off_by_default():
    pol = ExtremaEntryPolicy(flatten_strategy_params({}))
    assert pol.gate_blocks(np.zeros(7), _candles([105, 104, 103, 102, 101, 99, 98]), 98) == []
