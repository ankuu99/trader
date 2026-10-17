"""
Pre-order risk rejects must clear the strategy's pending-entry guard.

lr_extrema arms its entry guard (_pos.entry_price) when it EMITS an ENTRY, and
clears it on the order's fill/REJECTED/CANCELLED update. When RiskManager refuses
the signal before any order exists (quantity_zero when capital is fully deployed,
max_positions, stock_paused, ...) no update ever arrives — so the strategy waited
for a fill forever and went silent: the rest of the run in a backtest (QUESS /
TVSMOTOR / SCHAEFFLER frozen Jan→Oct 2026 in the YTD run by a single quantity_zero),
until restart live. Strategy.on_pre_order_reject() routes those through the normal
REJECTED path; the backtest engine and both live decision paths call it.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from trader.core.config import Config
from trader.data.store import Store
from trader.strategies.base import Direction, Signal, SignalType, Strategy
from trader.strategies.lr_extrema import LRExtremaStrategy

_PARAMS = {"warmup_bars": 5, "threshold": 0.70, "profit_pct": 4.0, "stop_pct": 2.0,
           "hold_bars": 5, "retrain_every": 50, "extrema_order": 2}


def _signal(signal_type=SignalType.ENTRY):
    return Signal(instrument="NSE:TEST", direction=Direction.BUY, signal_type=signal_type,
                  price_hint=100.0, strategy="lr_extrema")


def _pending_strategy() -> LRExtremaStrategy:
    """Flat strategy whose ENTRY was just emitted — guard armed, awaiting a fill."""
    strat = LRExtremaStrategy("NSE:TEST", _PARAMS)
    strat._pos.entry_price = 100.0
    return strat


@pytest.mark.parametrize("reason", ["quantity_zero", "max_positions", "stock_paused",
                                    "daily_halt", "slow_tf_limit", None])
def test_pre_order_reject_clears_pending_entry_guard(reason):
    strat = _pending_strategy()
    strat.on_pre_order_reject(_signal(), reason)
    assert strat._pos.entry_price is None


@pytest.mark.parametrize("reason", ["already_in_position", "pending_order_exists"])
def test_guard_kept_when_an_order_or_position_really_exists(reason):
    strat = _pending_strategy()
    strat.on_pre_order_reject(_signal(), reason)
    assert strat._pos.entry_price == 100.0


def test_in_position_addon_reject_leaves_position_state_alone():
    strat = LRExtremaStrategy("NSE:TEST", _PARAMS)
    strat.position = Direction.BUY
    strat._pos.entry_price = 100.0
    strat._pos.held_bars = 37
    strat.on_pre_order_reject(_signal(), "addon_spacing")
    assert (strat._pos.entry_price, strat._pos.held_bars) == (100.0, 37)


def test_exit_reject_is_not_touched():
    strat = _pending_strategy()
    strat.on_pre_order_reject(_signal(SignalType.EXIT), "quantity_zero")
    assert strat._pos.entry_price == 100.0


# ── engine level: a capital-starved stock keeps re-signalling instead of freezing ──

_CONFIG_DATA = {
    "env": "paper",
    "candle_timeframe": "15minute",
    # ₹100 of capital vs a ₹200 stock → every entry sizes to quantity_zero
    "capital": {"total": 100, "max_risk_per_trade_pct": 5.0, "daily_loss_limit_pct": 50.0},
    "risk": {
        "max_open_positions": 5, "default_sl_pct": 2.0, "risk_reward": 2.0,
        "order_type": "MARKET", "gtt_enabled": False, "max_capital_per_stock_pct": 50.0,
        "trading_start": "09:15", "trading_end": "15:30",
    },
    "strategies": {"lr_extrema": {}},
    "watchlist": [],
    "data": {"db_path": "unused.db", "historical_cache_days": 5},
}
STUBS: dict[str, "GuardedStub"] = {}


class GuardedStub(Strategy):
    """Emits an ENTRY on every bar it is not awaiting a fill — the same
    arm-at-emission / clear-on-REJECTED guard contract as lr_extrema."""

    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self.pending = False
        self.emitted = 0
        STUBS[instrument] = self

    @property
    def name(self) -> str:
        return "stub"

    def on_candle(self, bar: dict):
        if self.pending or self.position is not None:
            return None
        self.pending = True
        self.emitted += 1
        return Signal(instrument=self.instrument, direction=Direction.BUY,
                      signal_type=SignalType.ENTRY, price_hint=bar["close"],
                      strategy="stub", stop_loss_hint=bar["close"] * 0.5,
                      timestamp=bar["timestamp"])

    def on_order_update(self, order: dict) -> None:
        super().on_order_update(order)
        if order.get("status") in ("REJECTED", "CANCELLED", "COMPLETE"):
            self.pending = False


def test_engine_keeps_resignalling_after_quantity_zero(tmp_path):
    STUBS.clear()
    cfg = Config(dict(_CONFIG_DATA))
    store = Store(tmp_path / "t.db")
    day = datetime(2026, 6, 1)
    rows = [{"timestamp": day.replace(hour=9, minute=15) + timedelta(minutes=15 * i),
             "open": 200.0, "high": 201.0, "low": 199.0, "close": 200.0, "volume": 1000}
            for i in range(25)]
    store.write_candles("NSE:POOR", "15minute", pd.DataFrame(rows))
    targets = ["trader.core.config.config", "trader.backtest.engine.config",
               "trader.risk.manager.config", "trader.orders.manager.config"]
    patches = [patch(t, cfg) for t in targets]
    for p in patches:
        p.start()
    try:
        from trader.backtest.engine import run_backtest
        trades = run_backtest(kite=None, store=store, symbols=["NSE:POOR"],
                              symbol_to_token={"NSE:POOR": 1}, params={},
                              from_dt=day, to_dt=day + timedelta(days=1), pre_warmup_days=0,
                              per_symbol_params={"NSE:POOR": {}}, strategy_cls=GuardedStub)
    finally:
        for p in patches:
            p.stop()
    assert trades == []
    # Every bar re-signals; before the fix the first quantity_zero froze it at 1.
    assert STUBS["NSE:POOR"].emitted > 20
