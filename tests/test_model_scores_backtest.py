"""
Per-candle model-score collection in the backtest engine.

run_backtest(model_scores=sink) must append one {timestamp, close, p_min, p_max}
row per strategy-TF decision bar per symbol, sourced from strategy.score_current()
(the exact model the run traded with). The sink is optional — omitting it must
change nothing — and strategies without score_current are skipped gracefully.
The SQLite model_scores table stays live-only (engine never writes it).
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from trader.core.config import Config
from trader.data.store import Store

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


class ScoringStub:
    """Never trades; reports a deterministic score per bar via score_current."""

    def __init__(self, instrument: str, params: dict):
        self.instrument = instrument
        self.params = params
        self.position = None
        self.n_bars = 0

    @property
    def name(self) -> str:
        return "scoring-stub"

    def on_candle(self, bar: dict):
        self.n_bars += 1
        return None

    def on_tick(self, tick: dict):
        return None

    def on_order_update(self, update: dict):
        pass

    def score_current(self):
        return (0.10 + 0.001 * self.n_bars, 0.90 - 0.001 * self.n_bars)


class NoScoreStub(ScoringStub):
    """Same but without score_current — engine must skip it gracefully."""
    score_current = None


def _session(day: datetime, price: float) -> list[dict]:
    return [
        {"timestamp": day.replace(hour=9, minute=15) + timedelta(minutes=15 * i),
         "open": price, "high": price + 0.5, "low": price - 0.5,
         "close": price, "volume": 1000}
        for i in range(25)
    ]


def _run(tmp_path, strategy_cls, sink):
    cfg = Config(dict(_CONFIG))
    store = Store(tmp_path / "t.db")
    days = [datetime(2026, 6, d) for d in (1, 2)]
    sym = "NSE:SCORED"
    rows = [c for day in days for c in _session(day, 100.0)]
    store.write_candles(sym, "15minute", pd.DataFrame(rows))

    targets = ["trader.core.config.config", "trader.backtest.engine.config",
               "trader.risk.manager.config", "trader.orders.manager.config"]
    patches = [patch(t, cfg) for t in targets]
    for p in patches:
        p.start()
    try:
        from trader.backtest.engine import run_backtest
        return run_backtest(
            kite=None, store=store, symbols=[sym], symbol_to_token={sym: 1},
            params={}, from_dt=days[0], to_dt=days[-1] + timedelta(days=1),
            pre_warmup_days=0, strategy_cls=strategy_cls,
            model_scores=sink,
        )
    finally:
        for p in patches:
            p.stop()


def test_engine_collects_score_per_decision_bar(tmp_path):
    sink: dict = {}
    _run(tmp_path, ScoringStub, sink)

    rows = sink.get("NSE:SCORED", [])
    assert len(rows) == 50  # one per 15m bar, both sessions
    first = rows[0]
    assert set(first) == {"timestamp", "close", "p_min", "p_max"}
    assert first["close"] == pytest.approx(100.0)
    # scores follow the stub's deterministic ramp — proves per-bar freshness
    assert rows[1]["p_min"] > rows[0]["p_min"]
    assert rows[1]["p_max"] < rows[0]["p_max"]


def test_engine_skips_strategy_without_score_current(tmp_path):
    sink: dict = {}
    _run(tmp_path, NoScoreStub, sink)
    assert sink == {}


def test_sink_omitted_is_noop(tmp_path):
    trades = _run(tmp_path, ScoringStub, None)
    assert trades == []
