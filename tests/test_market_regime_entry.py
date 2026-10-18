"""
W6 market-regime entry modulation (TD-018 arm EXP-18): default-off decision-layer
tweak keyed on the prior-session India VIX percentile injected by the backtest engine.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from trader.core.config import Config
from trader.data.store import Store
from trader.strategies.base import SignalType
from trader.strategies.lr_extrema import LRExtremaStrategy


class _StubModel:
    is_trained = True

    def __init__(self, p_min=0.86, p_max=0.1):
        self.p = (p_min, p_max)

    def predict_proba(self, x):
        return self.p


class _StubFeatures:
    def compute(self, candles):
        return np.zeros(3)


def _mr(**over) -> dict:
    blk = {"enabled": True, "calm": {}, "mid": {}, "stress": {}}
    blk.update(over)
    return blk


def _strat(market_regime=None, p_min=0.86, threshold=0.85) -> LRExtremaStrategy:
    params = {"warmup_bars": 2, "threshold": threshold, "veto_threshold": 0.5,
              "stop_pct": 2.0, "retrain_every": 1000}
    if market_regime is not None:
        params["market_regime"] = market_regime
    s = LRExtremaStrategy("NSE:TEST", params)
    s._model = _StubModel(p_min)
    s._features = _StubFeatures()
    s._entry_policy.gate_blocks = lambda x, c, close: []
    return s


def _candle(i: int, vix_pct="absent") -> dict:
    c = {"timestamp": datetime(2026, 3, 2, 10, 0) + timedelta(minutes=15 * i),
         "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1000}
    if vix_pct != "absent":
        c["_mkt_vix_pct"] = vix_pct
        c["_mkt_nifty_dd60"] = -0.02
    return c


def _feed(s, vix_pct="absent", n=4):
    """Feed n candles; return the list of signals."""
    return [s.on_candle(_candle(i, vix_pct)) for i in range(n)]


def test_disabled_is_identity():
    a, b = _strat(), _strat(market_regime={"enabled": False, "calm": {"block": True}})
    c = _strat()
    sa = _feed(a)
    sb = _feed(b, vix_pct=0.1)
    sc = _feed(c, vix_pct=0.9)
    key = lambda sigs: [(x.signal_type, x.price_hint, x.size_weight) if x else None for x in sigs]
    assert key(sa) == key(sb) == key(sc)
    assert any(sa)  # the stub really does fire an entry
    assert b.last_market_state is None


@pytest.mark.parametrize("v,exp", [(0.1, "calm"), (0.5, "mid"), (0.9, "stress"), (None, "unknown")])
def test_state_classification(v, exp):
    s = _strat(_mr())
    assert s._market_state(_candle(0, v)) == exp
    assert s._market_state(_candle(0)) == "unknown"


def test_threshold_delta():
    mr = _mr(calm={"threshold_delta": 0.05})
    calm = _strat(mr)
    assert not any(_feed(calm, vix_pct=0.1))
    assert calm.last_market_state == "calm"
    stress = _strat(mr)
    sigs = [x for x in _feed(stress, vix_pct=0.9) if x]
    assert len(sigs) == 1 and sigs[0].signal_type == SignalType.ENTRY
    assert stress.last_market_state == "stress"


def test_block_calm():
    s = _strat(_mr(calm={"block": True}))
    sigs = _feed(s, vix_pct=0.1)
    assert not any(sigs)
    assert s.last_filter_block == "market_regime=calm"
    assert s._pos.entry_price is None  # entry guard not armed
    assert s.signal_log[-1]["type"] == "BLOCKED"


def test_size_mult():
    s = _strat(_mr(stress={"size_mult": 0.5}))
    sig = [x for x in _feed(s, vix_pct=0.9) if x][0]
    assert sig.size_weight == pytest.approx(0.5)

    s2 = _strat(_mr(stress={"size_mult": 0.5}))
    s2._meta = type("M", (), {
        "enabled": True, "is_trained": True, "meta_threshold": 0.0,
        "features_for": lambda self, *a: None,
        "allow": lambda self, x: (True, 0.8),
        "size_weight": lambda self, p: 0.8,
    })()
    sig2 = [x for x in _feed(s2, vix_pct=0.9) if x][0]
    assert sig2.size_weight == pytest.approx(0.4)


# ---------------------------------------------------------------- engine --

_CONFIG = {
    "env": "paper",
    "candle_timeframe": "15minute",
    "capital": {"total": 1_000_000, "max_risk_per_trade_pct": 5.0,
                "daily_loss_limit_pct": 50.0},
    "risk": {
        "max_open_positions": 5, "default_sl_pct": 2.0, "risk_reward": 2.0,
        "order_type": "MARKET", "gtt_enabled": False,
        "max_capital_per_stock_pct": 50.0,
        "trading_start": "09:15", "trading_end": "15:30",
    },
    "strategies": {"lr_extrema": {}},
    "watchlist": [],
    "data": {"db_path": "unused.db", "historical_cache_days": 5},
}

_N_DAYS = 80
_START = datetime(2026, 1, 1)


class _CaptureStub:
    seen: list = []

    def __init__(self, instrument, params):
        self.instrument = instrument
        self.params = params
        self.position = None

    @property
    def name(self):
        return "capture-stub"

    def on_candle(self, bar):
        _CaptureStub.seen.append(bar)
        return None

    def on_tick(self, tick):
        return None

    def on_order_update(self, update):
        pass


def _bars(day: datetime, close: float) -> list[dict]:
    return [{"timestamp": day.replace(hour=9, minute=15) + timedelta(minutes=15 * i),
             "open": close, "high": close + 0.5, "low": close - 0.5,
             "close": close, "volume": 1000} for i in range(25)]


def _run_engine(tmp_path, enabled: bool, vix_overrides: dict | None = None):
    _CaptureStub.seen = []
    cfg = Config(dict(_CONFIG))
    store = Store(tmp_path / "t.db")
    days = [_START + timedelta(days=k) for k in range(_N_DAYS)]
    vix_close = {k: float(k) for k in range(_N_DAYS)}
    vix_close[_N_DAYS - 2] = 39.5
    vix_close.update(vix_overrides or {})
    vix_rows = [b for k, d in enumerate(days) for b in _bars(d, vix_close[k])]
    nifty_rows = [b for k, d in enumerate(days) for b in _bars(d, 1000.0 + k)]
    store.write_candles("NSE:INDIA VIX", "15minute", pd.DataFrame(vix_rows))
    store.write_candles("NSE:NIFTY 50", "15minute", pd.DataFrame(nifty_rows))
    sym = "NSE:CAP"
    store.write_candles(sym, "15minute", pd.DataFrame(_bars(days[-1], 100.0)))

    targets = ["trader.core.config.config", "trader.backtest.engine.config",
               "trader.risk.manager.config", "trader.orders.manager.config"]
    patches = [patch(t, cfg) for t in targets]
    for p in patches:
        p.start()
    try:
        from trader.backtest.engine import run_backtest
        params = {"market_regime": {"enabled": enabled, "vix_lookback_days": 250}}
        run_backtest(
            kite=None, store=store, symbols=[sym],
            symbol_to_token={sym: 1, "NSE:NIFTY 50": 2, "NSE:INDIA VIX": 3},
            params=params, from_dt=days[-1], to_dt=days[-1] + timedelta(days=1),
            pre_warmup_days=_N_DAYS + 5, strategy_cls=_CaptureStub,
        )
    finally:
        for p in patches:
            p.stop()
    return [b for b in _CaptureStub.seen if b["timestamp"].date() == days[-1].date()]


def test_engine_injects_context(tmp_path):
    bars = _run_engine(tmp_path, enabled=True)
    assert bars
    # prior session (index 78) closes 39.5; 78 reference sessions 0..77, 40 of them below
    assert bars[0]["_mkt_vix_pct"] == pytest.approx(40 / 78)
    assert 0.0 <= bars[0]["_mkt_vix_pct"] <= 1.0
    # NIFTY prior close 1078 is its own 60-session high
    assert bars[0]["_mkt_nifty_dd60"] == pytest.approx(0.0)


def test_engine_disabled_keys_none(tmp_path):
    bars = _run_engine(tmp_path, enabled=False)
    assert bars
    assert all(b["_mkt_vix_pct"] is None and b["_mkt_nifty_dd60"] is None for b in bars)


def test_no_lookahead(tmp_path):
    base = _run_engine(tmp_path / "a", enabled=True)[0]["_mkt_vix_pct"]
    # change the VIX close of the stock's own session (index 79): must not move the value
    (tmp_path / "b").mkdir()
    moved = _run_engine(tmp_path / "b", enabled=True, vix_overrides={_N_DAYS - 1: 500.0})[0]["_mkt_vix_pct"]
    assert moved == base
