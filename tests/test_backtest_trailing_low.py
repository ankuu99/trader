"""
ISS-14: the backtest engine tests the candle LOW against the highest tick-exit
level (trail / trailing floor / breakeven) armed BEFORE the candle, filling at
min(level, open). Levels armed by the candle's own high never fire on its low.
"""
import dataclasses
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from trader.core.config import Config
from trader.data.store import Store
from trader.strategies.base import Direction, Signal, SignalType
from trader.strategies.lr_extrema import LRExtremaStrategy

SYM = "NSE:TRL"
DAY1 = datetime(2026, 6, 1)
DAY2 = datetime(2026, 6, 2)

_CFG = {
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
    "scale_in": {"enabled": False},
    "strategies": {"lr_extrema": {}},
    "watchlist": [],
    "data": {"db_path": "unused.db", "historical_cache_days": 5},
}

_PARAMS = {"trail_pct": 2.0, "profit_pct": 3.0, "sell_min_pct": 2.0, "stop_pct": 50.0}


def _strat(**over):
    return LRExtremaStrategy(SYM, {**_PARAMS, **over})


def _arm(strat, **fields):
    strat.position = Direction.BUY
    strat._pos.entry_price = 100.0
    strat._pos.fill_price = 100.0
    for k, v in fields.items():
        setattr(strat._pos, k, v)


# --------------------------------------------------------------------------- #
# Policy-level
# --------------------------------------------------------------------------- #

def test_policy_level_pure():
    s = _strat(breakeven_stop_enabled=True, breakeven_buffer_pct=0.5)
    _arm(s, trailing_active=True, peak_close=110.0, breakeven_active=True)
    before = dataclasses.asdict(s._pos)
    lvl = s.tick_exit_level()
    # candidates: BE 100.5, trail 107.8, floor 103.0 -> max is the trail
    assert lvl == (pytest.approx(107.8), "TRAILING")
    assert dataclasses.asdict(s._pos) == before


def test_policy_level_none_when_unarmed():
    s = _strat()
    _arm(s, trailing_active=False, peak_close=105.0)
    assert s.tick_exit_level() is None
    s2 = _strat(breakeven_stop_enabled=False)
    _arm(s2, breakeven_active=True)
    assert s2.tick_exit_level() is None


# --------------------------------------------------------------------------- #
# Engine-level
# --------------------------------------------------------------------------- #

class ScriptedLR(LRExtremaStrategy):
    """Real exit policy; entry on bar 0, position state armed directly after the
    last bar of day 1 (so the state is 'pre-candle' for day 2's first candle)."""

    def __init__(self, instrument, params):
        super().__init__(instrument, params)
        self._n = 0
        self._arm_fields = params.get("arm", {})

    def on_candle(self, bar):
        i = self._n
        self._n += 1
        if i == 0 and self.is_flat():
            return Signal(instrument=self.instrument, direction=Direction.BUY,
                          signal_type=SignalType.ENTRY, price_hint=bar["close"],
                          strategy="scripted", stop_loss_hint=bar["close"] * 0.5,
                          timestamp=bar["timestamp"])
        if i == 24 and not self.is_flat():
            for k, v in self._arm_fields.items():
                setattr(self._pos, k, v)
        return None


def _session(day, rows_override=None, price=100.0, spread=0.1):
    rows = []
    for i in range(25):
        ts = day.replace(hour=9, minute=15) + timedelta(minutes=15 * i)
        rows.append({"timestamp": ts, "open": price, "high": price + spread,
                     "low": price - spread, "close": price, "volume": 1000})
    if rows_override:
        rows[0].update(rows_override)
    return rows


def _run(tmp_path, day2_rows, params, strategy_cls=ScriptedLR):
    cfg = Config(dict(_CFG))
    store = Store(tmp_path / "t.db")
    rows = _session(DAY1) + day2_rows
    store.write_candles(SYM, "15minute", pd.DataFrame(rows))
    targets = ["trader.core.config.config", "trader.backtest.engine.config",
               "trader.risk.manager.config", "trader.orders.manager.config",
               "trader.strategies.lr_extrema.config"]
    patches = [patch(t, cfg) for t in targets]
    for p in patches:
        p.start()
    try:
        from trader.backtest.engine import run_backtest
        return run_backtest(
            kite=None, store=store, symbols=[SYM], symbol_to_token={SYM: 1},
            params=params, from_dt=DAY1, to_dt=DAY2 + timedelta(days=1),
            pre_warmup_days=0, strategy_cls=strategy_cls,
        )
    finally:
        for p in patches:
            p.stop()


def test_low_pierce_exits_at_level(tmp_path):
    day2 = _session(DAY2, {"open": 109.0, "high": 110.0, "low": 107.0, "close": 109.0},
                    price=109.0)
    trades = _run(tmp_path, day2, {**_PARAMS, "arm": {"trailing_active": True, "peak_close": 110.0}})
    assert len(trades) == 1
    assert trades[0]["reason"] == "TRAILING"
    assert trades[0]["exit"] == pytest.approx(110.0 * 0.98)
    assert trades[0]["exit_date"].date() == DAY2.date()


def test_gap_through_level_fills_at_open(tmp_path):
    day2 = _session(DAY2, {"open": 105.0, "high": 106.0, "low": 104.0, "close": 105.5},
                    price=105.5)
    trades = _run(tmp_path, day2, {**_PARAMS, "arm": {"trailing_active": True, "peak_close": 110.0}})
    assert len(trades) == 1
    assert trades[0]["reason"] == "TRAILING"
    assert trades[0]["exit"] == pytest.approx(105.0)


def test_level_armed_by_same_candle_does_not_fire(tmp_path):
    # Not armed before day 2. First candle: high arms the trail (>=3%), low is
    # below the would-be trail (104*0.98=101.92) but close recovers above it.
    day2 = _session(DAY2, {"open": 100.0, "high": 104.0, "low": 101.0, "close": 103.5},
                    price=103.5, spread=0.05)
    trades = _run(tmp_path, day2, {**_PARAMS, "arm": {}})
    assert len(trades) == 1
    assert trades[0]["reason"] == "OPEN@END"


def test_breakeven_level_low_pierce(tmp_path):
    day2 = _session(DAY2, {"open": 102.0, "high": 102.5, "low": 100.0, "close": 102.0},
                    price=102.0, spread=0.1)
    params = {**_PARAMS, "breakeven_stop_enabled": True, "breakeven_buffer_pct": 0.5,
              "arm": {"breakeven_active": True}}
    trades = _run(tmp_path, day2, params)
    assert len(trades) == 1
    assert trades[0]["reason"] == "BREAKEVEN"
    assert trades[0]["exit"] == pytest.approx(100.5)


class _NoHookStrategy:
    """Stub with no tick_exit_level; enters bar 0, exits bar 30."""

    def __init__(self, instrument, params):
        self.instrument = instrument
        self.position = None
        self._n = 0

    @property
    def name(self):
        return "nohook"

    def on_candle(self, bar):
        i = self._n
        self._n += 1
        if i == 0 and self.position is None:
            return Signal(instrument=self.instrument, direction=Direction.BUY,
                          signal_type=SignalType.ENTRY, price_hint=bar["close"],
                          strategy="nohook", stop_loss_hint=bar["close"] * 0.5,
                          timestamp=bar["timestamp"])
        if i == 30 and self.position is not None:
            return Signal(instrument=self.instrument, direction=Direction.BUY,
                          signal_type=SignalType.EXIT, price_hint=bar["close"],
                          strategy="nohook", timestamp=bar["timestamp"],
                          exit_reason="STRATEGY")
        return None

    def on_tick(self, tick):
        return None

    def on_order_update(self, update):
        if update.get("status") == "COMPLETE":
            self.position = Direction.BUY if update.get("direction") == "BUY" else None
        elif update.get("status") in ("CANCELLED", "REJECTED"):
            self.position = None


def test_strategy_without_hook_unchanged(tmp_path):
    assert not hasattr(_NoHookStrategy, "tick_exit_level")
    day2 = _session(DAY2, price=101.0)
    trades = _run(tmp_path, day2, {}, strategy_cls=_NoHookStrategy)
    assert len(trades) == 1
    assert trades[0]["reason"] == "STRATEGY"
