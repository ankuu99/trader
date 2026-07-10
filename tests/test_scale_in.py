"""
Scale-in (geometric add-on) tests.

Covers the full contract of the portfolio-level scale-in feature:
  1. RiskManager — geometric sizing off the previous lot, tier limit, daily
     spacing, separate budget pool (on top of base capital), reject reasons,
     pool accounting across fill → close, and exemption from max_open_positions.
  2. Strategy — an add-on fill/cancel NEVER touches position state: the
     staleness clock (_held_bars) and gain anchor (_entry_price) stay frozen on
     the original entry (the disaster-brake regression test).
  3. OrderManager — the `addon` flag threads through the paper fill dispatch
     and the clear_pending CANCELLED dispatch.
  4. Store — addon_lots persistence + blended quantity, and restart seeding
     (seed_position + seed_scale_in) rebuilding pool/tier/spacing state.
  5. Engine — end-to-end multi-lot backtest: per-lot trade records with
     addon_tier, shared exit, and lot-level costs.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch, PropertyMock

import pandas as pd
import pytest

from trader.core.config import Config, config
from trader.data.store import Store
from trader.orders.manager import OrderManager
from trader.risk.manager import Order, RiskManager
from trader.strategies.base import Direction, Signal, SignalType

INSTRUMENT = "NSE:TEST"
DAY1 = datetime(2026, 6, 1, 10, 0)
DAY2 = datetime(2026, 6, 2, 10, 0)
DAY3 = datetime(2026, 6, 3, 10, 0)
DAY4 = datetime(2026, 6, 4, 10, 0)
DAY5 = datetime(2026, 6, 5, 10, 0)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

@contextmanager
def _scale_in_config(enabled=True, fraction_pct=25.0, max_addons=3,
                     min_spacing_days=1, budget=100_000.0):
    with patch.object(type(config), "scale_in_enabled",
                      new_callable=PropertyMock, return_value=enabled), \
         patch.object(type(config), "scale_in_fraction_pct",
                      new_callable=PropertyMock, return_value=fraction_pct), \
         patch.object(type(config), "scale_in_max_addons",
                      new_callable=PropertyMock, return_value=max_addons), \
         patch.object(type(config), "scale_in_min_spacing_days",
                      new_callable=PropertyMock, return_value=min_spacing_days), \
         patch.object(type(config), "scale_in_budget",
                      new_callable=PropertyMock, return_value=budget):
        yield


def _entry(instrument=INSTRUMENT, price=100.0, sl=90.0, ts=DAY1) -> Signal:
    return Signal(
        instrument=instrument, direction=Direction.BUY,
        signal_type=SignalType.ENTRY, price_hint=price,
        strategy="test", stop_loss_hint=sl, timestamp=ts,
    )


def _exit(instrument=INSTRUMENT, price=104.0, ts=DAY3) -> Signal:
    return Signal(
        instrument=instrument, direction=Direction.BUY,
        signal_type=SignalType.EXIT, price_hint=price,
        strategy="test", timestamp=ts,
    )


def _open_parent(risk: RiskManager, qty=100, price=100.0, ts=DAY1):
    """Approve + fill a parent entry of qty @ price on day ts."""
    order = risk.validate(_entry(price=price, sl=price * 0.9, ts=ts))
    assert order is not None and not order.addon
    risk.on_order_filled(INSTRUMENT, price, qty, fill_ts=ts)


# --------------------------------------------------------------------------- #
# 1. RiskManager — add-on validation and pool accounting
# --------------------------------------------------------------------------- #

def test_addon_geometric_sizing_and_tier_limit():
    """Each add-on is fraction_pct of the PREVIOUS lot's notional; tier capped."""
    with _scale_in_config():
        risk = RiskManager()
        _open_parent(risk, qty=100, price=100.0, ts=DAY1)  # parent lot 10,000

        # Tier 1: 25% of 10,000 = 2,500 → 25 shares @100
        o1 = risk.validate(_entry(ts=DAY2))
        assert o1 is not None and o1.addon and o1.quantity == 25
        risk.on_order_filled(INSTRUMENT, 100.0, 25, addon=True, fill_ts=DAY2)

        # Tier 2: 25% of 2,500 = 625 → 6 shares
        o2 = risk.validate(_entry(ts=DAY3))
        assert o2 is not None and o2.quantity == 6
        risk.on_order_filled(INSTRUMENT, 100.0, 6, addon=True, fill_ts=DAY3)

        # Tier 3: 25% of 600 = 150 → 1 share
        o3 = risk.validate(_entry(ts=DAY4))
        assert o3 is not None and o3.quantity == 1
        risk.on_order_filled(INSTRUMENT, 100.0, 1, addon=True, fill_ts=DAY4)

        # Tier 4: rejected — max_addons=3
        o4 = risk.validate(_entry(ts=DAY5))
        assert o4 is None
        assert risk._last_reject_reason == "addon_limit_reached"

        # Blended quantity accumulates for the eventual full exit
        assert risk._open_positions[INSTRUMENT] == 132


def test_addon_spacing_same_day_rejected():
    with _scale_in_config():
        risk = RiskManager()
        _open_parent(risk, ts=DAY1)
        same_day = risk.validate(_entry(ts=DAY1.replace(hour=14)))
        assert same_day is None
        assert risk._last_reject_reason == "addon_spacing"
        # Next calendar day passes
        assert risk.validate(_entry(ts=DAY2)) is not None


def test_addon_budget_exhausted():
    with _scale_in_config(budget=2_000.0):  # tier-1 lot needs 2,500
        risk = RiskManager()
        _open_parent(risk, ts=DAY1)
        blocked = risk.validate(_entry(ts=DAY2))
        assert blocked is None
        assert risk._last_reject_reason == "addon_budget_exhausted"


def test_addon_qty_zero_rejected():
    """Lot too small to buy one share → addon_qty_zero."""
    with _scale_in_config():
        risk = RiskManager()
        _open_parent(risk, qty=1, price=300.0, ts=DAY1)  # lot 300 → 25% = 75 < price
        blocked = risk.validate(_entry(price=300.0, sl=270.0, ts=DAY2))
        assert blocked is None
        assert risk._last_reject_reason == "addon_qty_zero"


def test_disabled_scale_in_keeps_already_in_position():
    with _scale_in_config(enabled=False):
        risk = RiskManager()
        _open_parent(risk, ts=DAY1)
        blocked = risk.validate(_entry(ts=DAY2))
        assert blocked is None
        assert risk._last_reject_reason == "already_in_position"


def test_addon_exempt_from_max_positions():
    """An add-on is not a NEW position — approved even at the portfolio cap."""
    with _scale_in_config(), \
         patch.object(type(config), "max_open_positions",
                      new_callable=PropertyMock, return_value=1):
        risk = RiskManager()
        _open_parent(risk, ts=DAY1)
        addon = risk.validate(_entry(ts=DAY2))
        assert addon is not None and addon.addon


def test_addon_pool_on_top_of_base_capital():
    """Add-on deployment must not reduce base capital_available; close frees both."""
    with _scale_in_config():
        risk = RiskManager()
        _open_parent(risk, qty=100, price=100.0, ts=DAY1)
        base_available = risk.capital_available

        o = risk.validate(_entry(ts=DAY2))
        risk.on_order_filled(INSTRUMENT, 100.0, o.quantity, addon=True, fill_ts=DAY2)

        assert risk.capital_available == pytest.approx(base_available)
        assert risk.scale_in_deployed == pytest.approx(2_500.0)
        assert risk._capital_deployed == pytest.approx(10_000.0)  # parent only

        # Full close frees the pool and base capital, P&L uses blended avg entry
        risk.close_position(INSTRUMENT, exit_price=110.0)
        assert risk.scale_in_deployed == 0.0
        assert risk._capital_deployed == 0.0
        # blended: 125 sh, cost 12,500 → avg 100; pnl = 10 * 125
        assert risk.cumulative_pnl == pytest.approx(1_250.0)


def test_exit_sells_blended_quantity():
    with _scale_in_config():
        risk = RiskManager()
        _open_parent(risk, qty=100, price=100.0, ts=DAY1)
        o = risk.validate(_entry(ts=DAY2))
        risk.on_order_filled(INSTRUMENT, 100.0, o.quantity, addon=True, fill_ts=DAY2)

        sell = risk.validate(_exit())
        assert sell is not None
        assert sell.quantity == 125


def test_addon_pending_lock_blocks_duplicate_and_releases_on_cancel():
    with _scale_in_config():
        risk = RiskManager()
        _open_parent(risk, ts=DAY1)
        o = risk.validate(_entry(ts=DAY2))
        assert o is not None
        # Second add-on while first pending → blocked
        assert risk.validate(_entry(ts=DAY2)) is None
        assert risk._last_reject_reason == "pending_order_exists"
        # Cancel releases the lock and the addon marker
        risk.on_order_cancelled(INSTRUMENT)
        assert INSTRUMENT not in risk._pending_orders
        assert INSTRUMENT not in risk._pending_addons


def test_seed_scale_in_restores_state():
    """Restart path: seed_position(parent) + seed_scale_in(addons) rebuilds the
    blended qty, pool usage, tier count and spacing date."""
    with _scale_in_config():
        risk = RiskManager()
        risk.seed_position(INSTRUMENT, 100, 100.0, entry_ts=DAY1)
        risk.seed_scale_in(INSTRUMENT, [
            {"price": 95.0, "qty": 26, "date": DAY2.isoformat()},
        ])
        assert risk._open_positions[INSTRUMENT] == 126
        assert risk.scale_in_deployed == pytest.approx(95.0 * 26)
        state = risk._scale_in[INSTRUMENT]
        assert state["addon_count"] == 1
        assert state["last_invest_date"] == DAY2.date()

        # Same-day add-on blocked (spacing anchored to restored date)
        assert risk.validate(_entry(ts=DAY2.replace(hour=14))) is None
        assert risk._last_reject_reason == "addon_spacing"
        # Next tier sizes off the restored last lot (25% of 2,470 = 617.5 → 6 @ 100)
        o = risk.validate(_entry(ts=DAY3))
        assert o is not None and o.quantity == 6


# --------------------------------------------------------------------------- #
# 2. Strategy — add-on updates never touch position state (stale anchor)
# --------------------------------------------------------------------------- #

def test_strategy_ignores_addon_fill_and_cancel():
    from trader.strategies.lr_extrema import LRExtremaStrategy
    strat = LRExtremaStrategy(INSTRUMENT, {"warmup_bars": 5})
    # Simulate an established position: parent entry @100, 42 bars held, trailing on
    strat.position = Direction.BUY
    strat._pos.entry_price = 100.0
    strat._pos.fill_price = 100.0
    strat._pos.held_bars = 42
    strat._pos.peak_close = 108.0
    strat._pos.trailing_active = True

    addon_fill = {"status": "COMPLETE", "signal_type": SignalType.ENTRY,
                  "direction": "BUY", "price": 92.0, "quantity": 25, "addon": True}
    strat.on_order_update(addon_fill)

    assert strat._pos.entry_price == 100.0      # gain anchor unchanged
    assert strat._pos.held_bars == 42           # staleness clock unchanged
    assert strat._pos.peak_close == 108.0
    assert strat._pos.trailing_active is True
    assert strat.position == Direction.BUY

    # A cancelled/rejected add-on is equally a no-op (must NOT reset the parent)
    for status in ("CANCELLED", "REJECTED"):
        strat.on_order_update({"status": status, "signal_type": SignalType.ENTRY,
                               "direction": "BUY", "addon": True})
        assert strat._pos.entry_price == 100.0
        assert strat.position == Direction.BUY


# --------------------------------------------------------------------------- #
# 3. OrderManager — addon flag threading (paper)
# --------------------------------------------------------------------------- #

def _paper_order(addon: bool) -> Order:
    return Order(
        instrument=INSTRUMENT, direction=Direction.BUY, quantity=10,
        price_hint=100.0, stop_loss=90.0, target_price=0.0,
        strategy="test", mode="paper", signal_type=SignalType.ENTRY, addon=addon,
    )


def test_paper_fill_dispatch_carries_addon_flag(tmp_path):
    store = Store(tmp_path / "t.db")
    om = OrderManager(kite=None, store=store, mode="paper")
    seen: list[dict] = []
    om.register_update_callback(seen.append)

    om.place(_paper_order(addon=True))
    om.on_candle({"_symbol": INSTRUMENT, "open": 100.0, "high": 101.0,
                  "low": 99.0, "close": 100.5, "timestamp": DAY2})

    assert len(seen) == 1
    assert seen[0]["status"] == "COMPLETE"
    assert seen[0]["addon"] is True


def test_clear_pending_cancel_carries_addon_flag(tmp_path):
    store = Store(tmp_path / "t.db")
    om = OrderManager(kite=None, store=store, mode="paper")
    seen: list[dict] = []
    om.register_update_callback(seen.append)

    om.place(_paper_order(addon=True))
    om.clear_pending()

    assert len(seen) == 1
    assert seen[0]["status"] == "CANCELLED"
    assert seen[0]["addon"] is True


# --------------------------------------------------------------------------- #
# 4. Store — addon_lots persistence
# --------------------------------------------------------------------------- #

def test_add_position_lot_appends_and_bumps_quantity(tmp_path):
    store = Store(tmp_path / "t.db")
    store.upsert_open_position(INSTRUMENT, 100.0, 100, 0, DAY1)
    store.add_position_lot(INSTRUMENT, 95.0, 26, DAY2)
    store.add_position_lot(INSTRUMENT, 93.0, 6, DAY3)

    pos = store.read_open_positions()[0]
    assert pos["quantity"] == 132
    assert pos["entry_price"] == 100.0          # parent untouched
    assert len(pos["addon_lots"]) == 2
    assert pos["addon_lots"][0]["price"] == 95.0
    assert pos["addon_lots"][1]["qty"] == 6


def test_consume_position_lots_fifo_parent_first(tmp_path):
    """Partial exit on a scaled-in position consumes parent shares first, then
    add-on lots in fill order — quantity and addon_lots stay consistent so
    restart seeding (parent = quantity − Σ lots) can never go negative."""
    store = Store(tmp_path / "t.db")
    store.upsert_open_position(INSTRUMENT, 100.0, 100, 0, DAY1)  # parent 100
    store.add_position_lot(INSTRUMENT, 95.0, 26, DAY2)           # blended 126
    store.add_position_lot(INSTRUMENT, 93.0, 6, DAY3)            # blended 132

    # Scale-out sells 110: parent 100 fully consumed + 10 of the first add-on
    store.consume_position_lots(INSTRUMENT, 110)

    pos = store.read_open_positions()[0]
    assert pos["quantity"] == 22
    lots = pos["addon_lots"]
    assert [l["qty"] for l in lots] == [16, 6]
    # restart parent = 22 - 22 = 0 (non-negative) — seeding stays valid
    assert pos["quantity"] - sum(l["qty"] for l in lots) == 0

    # A small scale-out that only touches the parent leaves lots untouched
    store2 = Store(tmp_path / "t2.db")
    store2.upsert_open_position(INSTRUMENT, 100.0, 100, 0, DAY1)
    store2.add_position_lot(INSTRUMENT, 95.0, 26, DAY2)
    store2.consume_position_lots(INSTRUMENT, 50)
    pos2 = store2.read_open_positions()[0]
    assert pos2["quantity"] == 76
    assert [l["qty"] for l in pos2["addon_lots"]] == [26]


def test_restart_seed_after_partial_scale_out(tmp_path):
    """End-to-end restart consistency: scale-in add-on, then partial scale-out,
    then reseed from DB — blended qty matches and the pool reflects surviving
    add-on shares only."""
    with _scale_in_config():
        store = Store(tmp_path / "t.db")
        store.upsert_open_position(INSTRUMENT, 100.0, 100, 0, DAY1)
        store.add_position_lot(INSTRUMENT, 95.0, 26, DAY2)
        store.consume_position_lots(INSTRUMENT, 110)  # parent gone + 10 of add-on

        pos = store.read_open_positions()[0]
        lots = pos["addon_lots"]
        parent_qty = pos["quantity"] - sum(l["qty"] for l in lots)
        assert parent_qty >= 0

        risk = RiskManager()
        risk.seed_position(INSTRUMENT, parent_qty, pos["entry_price"], entry_ts=DAY1)
        risk.seed_scale_in(INSTRUMENT, lots)
        # blended 126 (parent 100 + addon 26), sold 110 → 16 addon shares survive
        assert risk._open_positions[INSTRUMENT] == 16
        assert risk.scale_in_deployed == pytest.approx(95.0 * 16)


def test_add_position_lot_missing_position_is_noop(tmp_path):
    store = Store(tmp_path / "t.db")
    store.add_position_lot("NSE:GHOST", 95.0, 26, DAY2)  # must not raise
    assert store.read_open_positions() == []


# --------------------------------------------------------------------------- #
# 5. Engine — end-to-end multi-lot backtest with per-lot trade records
# --------------------------------------------------------------------------- #

_ENGINE_CONFIG = {
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
    "scale_in": {"enabled": True, "fraction_pct": 25, "max_addons": 3,
                 "min_spacing_days": 1, "budget_pct": 20},
    "strategies": {"lr_extrema": {}},
    "watchlist": [],
    "data": {"db_path": "unused.db", "historical_cache_days": 5},
}


class ScriptedScaleInStrategy:
    """Emits: parent ENTRY on bar entry_on; in-position ENTRY (add-on candidate)
    on every bar in addon_on; EXIT on bar exit_on. Tracks fills like a real
    strategy (position set by parent fill only; addon updates ignored)."""

    def __init__(self, instrument: str, params: dict):
        self.instrument = instrument
        self.params = params
        self.position = None
        self.bars: list[dict] = []
        self.fills: list[dict] = []
        self._entry_on = params.get("entry_on", 0)
        self._addon_on = set(params.get("addon_on", ()))
        self._exit_on = params.get("exit_on")

    @property
    def name(self) -> str:
        return "scripted"

    def _signal(self, bar, signal_type):
        return Signal(
            instrument=self.instrument, direction=Direction.BUY,
            signal_type=signal_type, price_hint=bar["close"], strategy="scripted",
            stop_loss_hint=bar["close"] * 0.5 if signal_type == SignalType.ENTRY else None,
            timestamp=bar["timestamp"],
            exit_reason="STRATEGY" if signal_type == SignalType.EXIT else None,
        )

    def on_candle(self, bar: dict):
        self.bars.append(dict(bar))
        i = len(self.bars) - 1
        if i == self._entry_on and self.position is None:
            return self._signal(bar, SignalType.ENTRY)
        if i in self._addon_on and self.position is not None:
            return self._signal(bar, SignalType.ENTRY)  # add-on candidate
        if self._exit_on is not None and i == self._exit_on and self.position is not None:
            return self._signal(bar, SignalType.EXIT)
        return None

    def on_tick(self, tick: dict):
        return None

    def on_order_update(self, update: dict):
        self.fills.append(dict(update))
        if update.get("addon"):
            return  # add-on fills never touch position state
        status = update.get("status")
        if status == "COMPLETE":
            if update.get("direction") == "BUY":
                self.position = Direction.BUY
            else:
                self.position = None
        elif status in ("CANCELLED", "REJECTED"):
            self.position = None


def _flat_session(day: datetime, price: float) -> list[dict]:
    """25 flat 15m candles so fills happen at a known price."""
    rows = []
    for i in range(25):
        ts = day.replace(hour=9, minute=15) + timedelta(minutes=15 * i)
        rows.append({"timestamp": ts, "open": price, "high": price + 0.5,
                     "low": price - 0.5, "close": price, "volume": 1000})
    return rows


def test_engine_multilot_per_lot_records(tmp_path):
    cfg = Config(dict(_ENGINE_CONFIG))
    store = Store(tmp_path / "t.db")
    days = [datetime(2026, 6, d) for d in (1, 2, 3, 4)]  # Mon–Thu
    sym = "NSE:SCALE"
    prices = {days[0]: 100.0, days[1]: 96.0, days[2]: 94.0, days[3]: 105.0}
    rows = [c for day in days for c in _flat_session(day, prices[day])]
    store.write_candles(sym, "15minute", pd.DataFrame(rows))

    targets = ["trader.core.config.config", "trader.backtest.engine.config",
               "trader.risk.manager.config", "trader.orders.manager.config"]
    patches = [patch(t, cfg) for t in targets]
    for p in patches:
        p.start()
    try:
        from trader.backtest.engine import run_backtest
        trades = run_backtest(
            kite=None, store=store, symbols=[sym], symbol_to_token={sym: 1},
            params={"entry_on": 0,            # parent entry on day-1 first bar
                    "addon_on": [25, 50],     # add-on signals on day-2/day-3 first bars
                    "exit_on": 80},           # exit on day-4
            from_dt=days[0], to_dt=days[-1] + timedelta(days=1),
            pre_warmup_days=0,
            strategy_cls=ScriptedScaleInStrategy,
        )
    finally:
        for p in patches:
            p.stop()

    # One record per lot, shared exit
    assert len(trades) == 3
    tiers = sorted(t["addon_tier"] for t in trades)
    assert tiers == [0, 1, 2]
    by_tier = {t["addon_tier"]: t for t in trades}

    # Parent: filled at day-1 open (100); add-ons at day-2 (96) / day-3 (94) opens
    assert by_tier[0]["entry"] == pytest.approx(100.0)
    assert by_tier[1]["entry"] == pytest.approx(96.0)
    assert by_tier[2]["entry"] == pytest.approx(94.0)

    # Geometric sizing: parent notional N; tier1 ≈ 25% of N; tier2 ≈ 25% of tier1
    n0 = by_tier[0]["entry"] * by_tier[0]["qty"]
    n1 = by_tier[1]["entry"] * by_tier[1]["qty"]
    n2 = by_tier[2]["entry"] * by_tier[2]["qty"]
    assert n1 == pytest.approx(n0 * 0.25, rel=0.05)
    assert n2 == pytest.approx(n1 * 0.25, rel=0.10)

    # All lots exit together at the same price/date with the strategy reason
    exits = {t["exit"] for t in trades}
    assert len(exits) == 1
    assert {t["reason"] for t in trades} == {"STRATEGY"}
    assert len({str(t["exit_date"]) for t in trades}) == 1

    # Add-on lots bought lower and exited at the shared exit → profitable
    assert by_tier[1]["pnl"] > 0 and by_tier[2]["pnl"] > 0
    # held_candles is per-lot (parent held longest)
    assert by_tier[0]["held_candles"] > by_tier[1]["held_candles"] > by_tier[2]["held_candles"]


def test_engine_scale_in_disabled_single_record(tmp_path):
    """With scale_in disabled the same script produces exactly one parent trade
    (in-position ENTRYs rejected as before) — the zero-diff guarantee."""
    cfg_data = dict(_ENGINE_CONFIG)
    cfg_data["scale_in"] = {"enabled": False}
    cfg = Config(cfg_data)
    store = Store(tmp_path / "t.db")
    days = [datetime(2026, 6, d) for d in (1, 2, 3, 4)]
    sym = "NSE:SCALE"
    rows = [c for day in days for c in _flat_session(day, 100.0)]
    store.write_candles(sym, "15minute", pd.DataFrame(rows))

    targets = ["trader.core.config.config", "trader.backtest.engine.config",
               "trader.risk.manager.config", "trader.orders.manager.config"]
    patches = [patch(t, cfg) for t in targets]
    for p in patches:
        p.start()
    try:
        from trader.backtest.engine import run_backtest
        trades = run_backtest(
            kite=None, store=store, symbols=[sym], symbol_to_token={sym: 1},
            params={"entry_on": 0, "addon_on": [25, 50], "exit_on": 80},
            from_dt=days[0], to_dt=days[-1] + timedelta(days=1),
            pre_warmup_days=0,
            strategy_cls=ScriptedScaleInStrategy,
        )
    finally:
        for p in patches:
            p.stop()

    assert len(trades) == 1
    assert trades[0]["addon_tier"] == 0
