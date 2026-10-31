"""Technical layer: trend / timing / extension-veto / stop over synthetic OHLCV."""

import pandas as pd
import pytest

from trader.fvm import technical as tech


def make_daily(closes, highs=None, lows=None, vols=None, opens=None):
    n = len(closes)
    ts = pd.bdate_range("2024-01-01", periods=n)
    highs = highs or [c * 1.005 for c in closes]
    lows = lows or [c * 0.995 for c in closes]
    opens = opens or ([closes[0]] + closes[:-1])
    vols = vols or [1000.0] * n
    return pd.DataFrame({"timestamp": ts, "open": opens, "high": highs,
                         "low": lows, "close": closes, "volume": vols})


def test_smoothstep_monotonic_bounded():
    assert tech.smoothstep(-1, 0, 1) == 0.0
    assert tech.smoothstep(2, 0, 1) == 1.0
    assert 0 < tech.smoothstep(0.5, 0, 1) < 1
    assert tech.smoothstep(0.3, 0, 1) < tech.smoothstep(0.7, 0, 1)


def test_resample_weekly_aggregates():
    df = make_daily([100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
                    vols=[10] * 10)
    w = tech.resample_weekly(df)
    assert len(w) >= 2
    assert w.iloc[0]["volume"] > 0 and w.iloc[0]["high"] >= w.iloc[0]["low"]


def test_atr_positive():
    df = make_daily([100 + i for i in range(30)])
    assert tech.atr(df) > 0


def test_trend_score_high_for_uptrend_zero_for_downtrend():
    up = [100 * (1.003 ** i) for i in range(320)]
    down = [200 * (0.997 ** i) for i in range(320)]
    up_w = tech.resample_weekly(make_daily(up))
    down_w = tech.resample_weekly(make_daily(down))
    assert tech.trend_score(up_w) > 0.8
    assert tech.trend_score(down_w) < 0.05


def test_breakout_score_fires_on_base_breakout_with_volume():
    base = [100.0] * 25
    closes = base + [102.0]                  # clears the ~100.5 base high
    vols = [1000.0] * 25 + [2600.0]          # 2.6× volume expansion
    df = make_daily(closes, vols=vols)
    assert tech.breakout_score(df) > 0.5
    # same breakout WITHOUT volume -> no score
    flat_vol = make_daily(closes, vols=[1000.0] * 26)
    assert tech.breakout_score(flat_vol) < 0.2


def test_extension_veto_blocks_parabolic():
    closes = [100 + i * 0.3 for i in range(60)]
    a = tech.atr(make_daily(closes))
    ma50 = sum(closes[-50:]) / 50
    closes_spike = closes + [ma50 + 6 * a]   # far above the 50-day -> parabolic
    df = make_daily(closes_spike)
    assert tech.extension_vetoed(df) is True
    assert tech.timing_score(df) == 0.0


def test_initial_stop_is_min_weekly_low():
    df = make_daily([100 + i for i in range(80)])
    w = tech.resample_weekly(df)
    stop = tech.initial_stop(w)
    assert stop == pytest.approx(min(w["low"].tolist()[-tech.SWING_LOW_W:]))


def test_evaluate_combines_trend_times_timing():
    up = [100 * (1.003 ** i) for i in range(320)]
    res = tech.evaluate(make_daily(up))
    assert set(res) >= {"trend_score", "timing_score", "technical_score",
                        "extension_vetoed", "initial_stop"}
    assert res["technical_score"] == pytest.approx(res["trend_score"] * res["timing_score"])
