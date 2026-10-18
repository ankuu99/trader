"""W2 feature add-ons: bar_shape, atr_dist, sr, market (TD-018 EXP-05..08)."""

import math
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from trader.features.addon_atr_dist import AtrDistAddon
from trader.features.addon_bar_shape import BarShapeAddon
from trader.features.addon_market import MarketContextAddon
from trader.features.addon_sr import SupportResistanceAddon


def _c(o, h, l, c, v=1000, **extra):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v, **extra}


def test_registered():
    import trader.features.registry  # noqa: F401
    from trader.features.addons import ADDONS
    assert list(ADDONS) == ["bar_shape", "atr_dist", "sr", "market"]


def test_bar_shape_values():
    a = BarShapeAddon({"vol_bars": 20})
    cs = [_c(100, 101, 99, 100) for _ in range(19)]
    cs.append(_c(100, 101, 95, 100.5, v=3000))  # hammer, prev low = 99
    lw, uw, body, cxv, cpl = a.compute(cs)
    assert lw == pytest.approx(5 / 6)
    assert uw == pytest.approx(0.5 / 6)
    assert body == pytest.approx(0.5 / 6)
    vr = 3000 / ((19 * 1000 + 3000) / 20)
    assert cxv == pytest.approx((5 / 6) * vr)
    assert cpl == pytest.approx((100.5 - 99) / 99)
    # zero-range candle
    z = cs[:-1] + [_c(100, 100, 100, 100)]
    assert a.compute(z)[:4] == [0.0, 0.0, 0.0, 0.0]
    assert a.min_history == 20


def test_atr_dist_values():
    a = AtrDistAddon({})
    cs = [_c(100 + i, 100 + i + 0.5, 100 + i - 0.5, 100.0 + i) for i in range(100)]
    dist, ratio = a.compute(cs)
    # slope 1/bar: EMA(20) lags by (20-1)/2 = 9.5; TR = max(1, 1.5, 0.5) = 1.5
    assert dist == pytest.approx(9.5 / 1.5, rel=1e-6)
    assert dist > 0
    assert ratio == pytest.approx(1.5 / 199.0)
    assert a.min_history == 100


def _sr_series():
    path = [103, 102, 101, 100]
    for _ in range(2):
        path += [102, 104, 106, 108, 110, 108, 106, 104, 102, 100]
    path += [102, 104, 106]  # confirms the third 100
    return path


def _sr_candles(cur):
    cs = [_c(p, p, p, float(p)) for p in _sr_series()]
    cs.append(_c(cur, cur, cur, float(cur)))
    return cs


def test_sr_levels():
    cs = _sr_candles(104)
    a = SupportResistanceAddon({"lookback": len(cs) - 1})
    sd, st, rd, rt = a.compute(cs)
    assert sd == pytest.approx(0.04, abs=0.002)  # (104-100)/104
    assert st == 3.0
    assert rd == pytest.approx(0.0577, abs=0.0005)
    assert rt == 2.0
    flat = [_c(p, p, p, float(p)) for p in range(100, 160)]
    assert SupportResistanceAddon({"lookback": 50}).compute(flat) == [0.25, 0.0, 0.25, 0.0]


def test_sr_no_lookahead():
    a = SupportResistanceAddon({"lookback": len(_sr_candles(104)) - 1})
    x1 = a.compute(_sr_candles(104))
    x2 = a.compute(_sr_candles(105))
    assert (x1[1], x1[3]) == (x2[1], x2[3]) == (3.0, 2.0)
    assert x1[0] != x2[0] and x1[2] != x2[2]
    assert x2[0] == pytest.approx(5 / 105)
    assert x2[2] == pytest.approx(5 / 105)


def test_market_values_and_missing():
    a = MarketContextAddon({})
    cs = [_c(100, 100, 100, 100.0 + i, _nifty_close=1000.0 + 10 * i, _vix_close=15.0 + 0.1 * i)
          for i in range(60)]
    rel, dd, vl, vc = a.compute(cs)
    n, c, v = cs[-1], cs[-1]["close"], cs[-1]["_vix_close"]
    c0, n0, v0 = cs[-21]["close"], cs[-21]["_nifty_close"], cs[-21]["_vix_close"]
    assert rel == pytest.approx((c / c0 - 1) - (n["_nifty_close"] / n0 - 1))
    assert dd == pytest.approx(0.0)  # nifty at its 50-bar high
    assert vl == pytest.approx(v / 20 - 1)
    assert vc == pytest.approx(v / v0 - 1)
    bare = [_c(100, 100, 100, 100.0) for _ in range(60)]
    assert a.compute(bare) == [0.0, 0.0, 0.0, 0.0]
    # drawdown from a prior high
    cs[-1]["_nifty_close"] = 1000.0
    assert a.compute(cs)[1] == pytest.approx(1000.0 / max(c["_nifty_close"] for c in cs[-50:]) - 1)


def test_pipeline_append_order():
    from trader.features.registry import build_feature_pipeline
    cfg = {k: {"enabled": True} for k in ("bar_shape", "atr_dist", "sr", "market")}
    pipe = build_feature_pipeline(cfg)
    base = build_feature_pipeline({})
    rng = np.random.default_rng(1)
    px = 100 + np.cumsum(rng.normal(0, 1, 400))
    cs = [_c(p, p + 1, p - 1, float(p), 1000, _nifty_close=1000.0 + i, _vix_close=15.0)
          for i, p in enumerate(px)]
    x, xb = pipe.compute(cs), base.compute(cs)
    assert len(pipe.feature_names) == len(x) == 21
    assert np.array_equal(x[:6], xb)
    assert all(math.isfinite(v) for v in x)


def test_addons_finite_on_flat_zero_volume():
    cs = [_c(100, 100, 100, 100.0, 0) for _ in range(30)]
    for a in (BarShapeAddon({}), AtrDistAddon({}), SupportResistanceAddon({"lookback": 20}),
              MarketContextAddon({})):
        vals = a.compute(cs)
        assert len(vals) == len(a.feature_names)
        assert all(math.isfinite(v) for v in vals)


def test_runner_regime_symbols(tmp_path):
    from trader.backtest.engine import run_backtest
    from trader.core.config import Config
    from trader.data.store import Store
    from tests.test_engine_aggregated_tf import _CONFIG_DATA, RECORDERS, RecordingStrategy, _session_candles

    RECORDERS.clear()
    cfg = Config(dict(_CONFIG_DATA))
    store = Store(tmp_path / "t.db")
    days = [datetime(2026, 6, d) for d in (1, 2)]
    for sym, base in (("NSE:AAA", 100.0), ("NSE:NIFTY 50", 20000.0), ("NSE:INDIA VIX", 14.0)):
        rows = [c for d in days for c in _session_candles(d, base)]
        store.write_candles(sym, "15minute", pd.DataFrame(rows))
    tokens = {**{"NSE:AAA": 0}, "NSE:NIFTY 50": 256265, "NSE:INDIA VIX": 264969}
    targets = ["trader.core.config.config", "trader.backtest.engine.config",
               "trader.risk.manager.config", "trader.orders.manager.config"]
    ps = [patch(t, cfg) for t in targets]
    for p in ps:
        p.start()
    try:
        run_backtest(kite=None, store=store, symbols=["NSE:AAA"], symbol_to_token=tokens,
                     params={}, from_dt=days[0], to_dt=days[-1] + timedelta(days=1),
                     pre_warmup_days=0, per_symbol_params={"NSE:AAA": {}},
                     strategy_cls=RecordingStrategy)
    finally:
        for p in ps:
            p.stop()
    bars = RECORDERS["NSE:AAA"].bars
    assert bars and all(b["_nifty_close"] is not None and b["_vix_close"] is not None for b in bars)
