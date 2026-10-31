"""
Backtest engine + per-stock aggregated timeframes.

Drives run_backtest with a recording stub strategy over synthetic 15m candles
pre-written to a Store (kite=None, cache-only), asserting:
  - a day-TF stock's strategy sees one composed bar per day (correct OHLCV,
    bucket-start timestamp), emitted on the 15:00 last-member candle
  - a base-TF stock sees every 15m candle untouched
  - an entry decided on the day bar fills at the SAME DAY's 15:15 base candle
    (next base candle open) — not the next morning
"""
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from trader.core.config import Config
from trader.data.store import Store
from trader.strategies.base import Direction, Signal, SignalType

_CONFIG_DATA = {
    "env": "paper",
    "candle_timeframe": "15minute",
    "capital": {"total": 1_000_000, "max_risk_per_trade_pct": 5.0, "daily_loss_limit_pct": 50.0},
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

RECORDERS: dict[str, "RecordingStrategy"] = {}


class RecordingStrategy:
    """Minimal strategy stub: records every bar it receives; optionally emits
    one BUY ENTRY on the params-configured bar index."""

    def __init__(self, instrument: str, params: dict):
        self.instrument = instrument
        self.params = params
        self.position = None
        self.bars: list[dict] = []
        self.fills: list[dict] = []
        self._signal_on = params.get("signal_on_bar")
        RECORDERS[instrument] = self

    @property
    def name(self) -> str:
        return "stub"

    def on_candle(self, bar: dict):
        self.bars.append(dict(bar))
        if (self._signal_on is not None and len(self.bars) - 1 == self._signal_on
                and self.position is None):
            self.position = Direction.BUY  # guard against re-entry pre-fill
            return Signal(
                instrument=self.instrument, direction=Direction.BUY,
                signal_type=SignalType.ENTRY, price_hint=bar["close"],
                strategy="stub", stop_loss_hint=bar["close"] * 0.50,
                timestamp=bar["timestamp"],
            )
        return None

    def on_tick(self, tick: dict):
        return None

    def on_order_update(self, update: dict):
        self.fills.append(dict(update))
        if update.get("direction") == "SELL" or update.get("status") == "CANCELLED":
            self.position = None


def _session_candles(day: datetime, base: float) -> list[dict]:
    """Full 15m session 09:15 … 15:15 (25 candles), gently rising."""
    rows = []
    for i in range(25):
        ts = day.replace(hour=9, minute=15) + timedelta(minutes=15 * i)
        px = base + i * 0.5
        rows.append({"timestamp": ts, "open": px, "high": px + 1.0,
                     "low": px - 1.0, "close": px + 0.25, "volume": 1000})
    return rows


@pytest.fixture
def env(tmp_path):
    RECORDERS.clear()
    cfg = Config(dict(_CONFIG_DATA))
    store = Store(tmp_path / "test.db")
    days = [datetime(2026, 6, d) for d in (1, 2, 3, 4)]  # Mon–Thu
    for sym, base in (("NSE:DAYSTOCK", 100.0), ("NSE:BASESTOCK", 200.0)):
        rows = [c for day in days for c in _session_candles(day, base)]
        store.write_candles(sym, "15minute", pd.DataFrame(rows))
    targets = [
        "trader.core.config.config",
        "trader.backtest.engine.config",
        "trader.risk.manager.config",
        "trader.orders.manager.config",
    ]
    patches = [patch(t, cfg) for t in targets]
    for p in patches:
        p.start()
    try:
        yield store, days
    finally:
        for p in patches:
            p.stop()


def _run(store, days, per_symbol_params):
    from trader.backtest.engine import run_backtest
    return run_backtest(
        kite=None, store=store,
        symbols=list(per_symbol_params),
        symbol_to_token={s: i + 1 for i, s in enumerate(per_symbol_params)},
        params={},
        from_dt=days[0], to_dt=days[-1] + timedelta(days=1),
        pre_warmup_days=0,
        per_symbol_params=per_symbol_params,
        strategy_cls=RecordingStrategy,
    )


def test_day_tf_strategy_sees_composed_daily_bars(env):
    store, days = env
    _run(store, days, {
        "NSE:DAYSTOCK": {"timeframe": "day"},
        "NSE:BASESTOCK": {},
    })

    day_bars = RECORDERS["NSE:DAYSTOCK"].bars
    assert [b["timestamp"] for b in day_bars] == [
        d.replace(hour=9, minute=15) for d in days
    ]
    bar = day_bars[0]  # members 09:15..15:00 of day 1 (base=100.0)
    assert bar["open"] == 100.0
    assert bar["close"] == 100.0 + 23 * 0.5 + 0.25   # 15:00 candle close
    assert bar["high"] == 100.0 + 23 * 0.5 + 1.0     # 15:00 candle high
    assert bar["low"] == 99.0
    assert bar["volume"] == 24 * 1000                 # tail candle excluded

    base_bars = RECORDERS["NSE:BASESTOCK"].bars
    assert len(base_bars) == 4 * 25                   # every 15m candle, untouched
    assert base_bars[0]["timestamp"] == days[0].replace(hour=9, minute=15)
    assert base_bars[1]["timestamp"] == days[0].replace(hour=9, minute=30)


def test_day_tf_entry_fills_same_day_at_1515(env):
    store, days = env
    trades = _run(store, days, {
        "NSE:DAYSTOCK": {"timeframe": "day", "signal_on_bar": 1},  # day-2 bar
    })

    strat = RECORDERS["NSE:DAYSTOCK"]
    buy_fills = [f for f in strat.fills if f.get("direction") == "BUY"
                 and f.get("status") == "COMPLETE"]
    assert len(buy_fills) == 1
    # Decision on day-2's bar (emitted on the 15:00 candle); paper MARKET order
    # fills at the next base candle's open — day 2, 15:15. Same day.
    day2_1515 = days[1].replace(hour=15, minute=15)
    fill_price = buy_fills[0].get("fill_price") or buy_fills[0].get("price")
    assert fill_price == 100.0 + 24 * 0.5             # 15:15 candle open, day 2
    open_at_end = [t for t in trades if t["reason"] == "OPEN@END"]
    assert len(open_at_end) == 1
    assert open_at_end[0]["entry_date"] == day2_1515


def test_4hour_tf_bar_cadence(env):
    store, days = env
    _run(store, days, {"NSE:DAYSTOCK": {"timeframe": "4hour"}})
    bars = RECORDERS["NSE:DAYSTOCK"].bars
    assert len(bars) == 8  # 2 per day × 4 days
    assert bars[0]["timestamp"] == days[0].replace(hour=9, minute=15)
    assert bars[1]["timestamp"] == days[0].replace(hour=13, minute=15)
