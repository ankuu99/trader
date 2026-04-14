import pytest

from trader.strategies.base import Direction, Signal, SignalType
from trader.risk.manager import RiskManager
from trader.core.config import config
from datetime import datetime


def make_signal(instrument="NSE:RELIANCE", direction=Direction.BUY,
                signal_type=SignalType.ENTRY, price=2500.0):
    return Signal(instrument, direction, signal_type, price_hint=price, strategy="test")


def fill(rm, instrument, direction, qty, price, signal_type):
    rm.on_order_filled(instrument, direction, qty, price, signal_type)


class TestRiskManager:
    def setup_method(self):
        self.rm = RiskManager()

    def test_valid_entry_produces_order(self):
        signal = make_signal()
        order = self.rm.validate(signal, atr=25.0)
        assert order is not None
        assert order.quantity > 0
        assert order.stop_loss == 2475.0  # 2500 - 25

    def test_quantity_bounded_by_max_risk(self):
        # max_risk = 20000 * 1% = 200, sl_distance = 25 → qty = 200 // 25 = 8
        order = self.rm.validate(make_signal(price=2500.0), atr=25.0)
        assert order.quantity == 8

    def test_sl_fallback_to_pct_when_no_atr(self):
        order = self.rm.validate(make_signal(price=1000.0), atr=None)
        assert order is not None
        # 1% of 1000 = 10 → SL = 990
        assert order.stop_loss == 990.0

    def test_entry_rejected_when_halted(self):
        self.rm._halted = True
        order = self.rm.validate(make_signal())
        assert order is None

    def test_entry_rejected_when_max_positions_reached(self):
        max_pos = config.max_open_positions
        for i in range(max_pos):
            sig = make_signal(instrument=f"NSE:STOCK{i}", price=100.0)
            order = self.rm.validate(sig, atr=1.0)
            fill(self.rm, f"NSE:STOCK{i}", Direction.BUY, order.quantity, 100.0, SignalType.ENTRY)
        # One more entry should be rejected
        order = self.rm.validate(make_signal(instrument=f"NSE:STOCK{max_pos}", price=100.0), atr=1.0)
        assert order is None

    def test_entry_rejected_for_duplicate_position(self):
        order = self.rm.validate(make_signal(), atr=25.0)
        fill(self.rm, "NSE:RELIANCE", Direction.BUY, order.quantity, 2500.0, SignalType.ENTRY)
        # Second entry for same instrument
        order2 = self.rm.validate(make_signal(), atr=25.0)
        assert order2 is None

    def test_exit_order_produced_for_open_position(self):
        order = self.rm.validate(make_signal(), atr=25.0)
        fill(self.rm, "NSE:RELIANCE", Direction.BUY, order.quantity, 2500.0, SignalType.ENTRY)
        exit_sig = make_signal(direction=Direction.SELL, signal_type=SignalType.EXIT, price=2520.0)
        exit_order = self.rm.validate(exit_sig)
        assert exit_order is not None
        assert exit_order.signal_type == SignalType.EXIT

    def test_exit_ignored_when_no_position(self):
        exit_sig = make_signal(direction=Direction.SELL, signal_type=SignalType.EXIT)
        order = self.rm.validate(exit_sig)
        assert order is None

    def test_pnl_tracked_after_close(self):
        order = self.rm.validate(make_signal(price=2500.0), atr=25.0)
        fill(self.rm, "NSE:RELIANCE", Direction.BUY, order.quantity, 2500.0, SignalType.ENTRY)
        exit_sig = make_signal(direction=Direction.SELL, signal_type=SignalType.EXIT, price=2550.0)
        exit_order = self.rm.validate(exit_sig)
        fill(self.rm, "NSE:RELIANCE", Direction.BUY, exit_order.quantity, 2550.0, SignalType.EXIT)
        assert self.rm.realised_pnl() == 8 * 50   # qty(8) * price_diff(50)

    def test_halt_triggered_on_daily_loss_breach(self):
        # Create a large loss to breach the 600 daily limit
        order = self.rm.validate(make_signal(price=1000.0), atr=1.0)
        fill(self.rm, "NSE:RELIANCE", Direction.BUY, order.quantity, 1000.0, SignalType.ENTRY)
        exit_sig = make_signal(direction=Direction.SELL, signal_type=SignalType.EXIT, price=900.0)
        exit_order = self.rm.validate(exit_sig)
        fill(self.rm, "NSE:RELIANCE", Direction.BUY, exit_order.quantity, 900.0, SignalType.EXIT)
        assert self.rm.is_halted()

    def test_square_off_generates_exit_orders(self):
        order = self.rm.validate(make_signal(price=2500.0), atr=25.0)
        fill(self.rm, "NSE:RELIANCE", Direction.BUY, order.quantity, 2500.0, SignalType.ENTRY)
        orders = self.rm.square_off_all()
        assert len(orders) == 1
        assert orders[0].signal_type == SignalType.EXIT
        assert orders[0].instrument == "NSE:RELIANCE"

    def test_reset_day_clears_pnl_but_keeps_positions(self):
        order = self.rm.validate(make_signal(), atr=25.0)
        fill(self.rm, "NSE:RELIANCE", Direction.BUY, order.quantity, 2500.0, SignalType.ENTRY)
        self.rm.reset_day()
        # Positions are preserved across days (interday behaviour)
        assert self.rm.open_position_count() == 1
        assert self.rm.realised_pnl() == 0.0
        assert not self.rm.is_halted()

    def test_reset_positions_clears_all_state(self):
        order = self.rm.validate(make_signal(), atr=25.0)
        fill(self.rm, "NSE:RELIANCE", Direction.BUY, order.quantity, 2500.0, SignalType.ENTRY)
        self.rm.reset_day()
        self.rm.reset_positions()
        assert self.rm.open_position_count() == 0
        assert self.rm.realised_pnl() == 0.0
        assert not self.rm.is_halted()

    def test_should_square_off_true_at_or_after_time(self):
        assert should_square_off(datetime(2024, 1, 15, 15, 20)) is True
        assert should_square_off(datetime(2024, 1, 15, 15, 30)) is True

    def test_should_square_off_false_before_time(self):
        assert should_square_off(datetime(2024, 1, 15, 15, 19)) is False


class TestWeeklyCircuitBreaker:
    def setup_method(self):
        self.rm = RiskManager()

    def _big_loss(self, instrument="NSE:A", price=1000.0, atr=1.0, exit_price=500.0):
        """Open and close a position with a large loss."""
        order = self.rm.validate(make_signal(instrument=instrument, price=price), atr=atr)
        fill(self.rm, instrument, Direction.BUY, order.quantity, price, SignalType.ENTRY)
        exit_sig = make_signal(instrument=instrument, direction=Direction.SELL,
                               signal_type=SignalType.EXIT, price=exit_price)
        exit_order = self.rm.validate(exit_sig)
        fill(self.rm, instrument, Direction.BUY, exit_order.quantity, exit_price, SignalType.EXIT)

    def test_weekly_pnl_accumulates_across_days(self):
        self._big_loss(instrument="NSE:A", exit_price=990.0)
        self.rm.reset_day()  # new day, not Monday
        assert self.rm.weekly_realised_pnl() < 0

    def test_weekly_halt_triggered_on_breach(self):
        # Pre-seed weekly P&L just below the limit, then add a small loss to push it over
        weekly_limit = config.weekly_loss_limit   # rupees
        pre_seed = -(weekly_limit - 1.0)          # ₹1 below the limit; any loss trips the breaker
        self.rm._weekly_realised_pnl = pre_seed
        order = self.rm.validate(make_signal(price=1000.0), atr=25.0)
        fill(self.rm, "NSE:RELIANCE", Direction.BUY, order.quantity, 1000.0, SignalType.ENTRY)
        exit_sig = make_signal(direction=Direction.SELL, signal_type=SignalType.EXIT, price=995.0)
        exit_order = self.rm.validate(exit_sig)
        fill(self.rm, "NSE:RELIANCE", Direction.BUY, exit_order.quantity, 995.0, SignalType.EXIT)
        assert self.rm.is_weekly_halted()

    def test_weekly_halt_blocks_entries(self):
        self.rm._weekly_halted = True
        order = self.rm.validate(make_signal())
        assert order is None

    def test_monday_reset_clears_weekly_state(self):
        self.rm._weekly_halted = True
        self.rm._weekly_realised_pnl = -1000.0
        self.rm.reset_day(is_monday=True)
        assert not self.rm.is_weekly_halted()
        assert self.rm.weekly_realised_pnl() == 0.0

    def test_non_monday_reset_preserves_weekly_state(self):
        self.rm._weekly_realised_pnl = -300.0
        self.rm.reset_day(is_monday=False)
        assert self.rm.weekly_realised_pnl() == -300.0


class TestRegimeOverlay:
    def setup_method(self):
        self.rm = RiskManager()

    def test_entry_passes_when_regime_allowed(self):
        self.rm.update_regime(True)
        order = self.rm.validate(make_signal(), atr=25.0)
        assert order is not None

    def test_entry_blocked_when_regime_disabled_and_config_enabled(self, monkeypatch):
        from trader.core import config as cfg_module
        monkeypatch.setattr(cfg_module.config, "_data", {
            **cfg_module.config._data,
            "risk": {
                **cfg_module.config._data["risk"],
                "regime_filter": {"enabled": True},
            },
        })
        self.rm.update_regime(False)
        order = self.rm.validate(make_signal(), atr=25.0)
        assert order is None

    def test_regime_flag_ignored_when_filter_disabled(self):
        # regime_filter.enabled is false in test config — update_regime(False) should have no effect
        self.rm.update_regime(False)
        order = self.rm.validate(make_signal(), atr=25.0)
        assert order is not None  # filter disabled in config, so blocked flag is irrelevant


class TestATRSizing:
    def setup_method(self):
        self.rm = RiskManager()

    def test_default_sizing_uses_sl_distance(self, monkeypatch):
        from trader.core import config as cfg_module
        monkeypatch.setattr(cfg_module.config, "_data", {
            **cfg_module.config._data,
            "risk": {
                **cfg_module.config._data["risk"],
                "position_sizing": {"atr_based": False, "atr_multiplier": 2.0, "max_position_pct": 0},
            },
        })
        # non-ATR formula: max_risk=200, sl_distance=25 → 200//25 = 8
        order = self.rm.validate(make_signal(price=2500.0), atr=25.0)
        assert order.quantity == 8

    def test_sl_distance_sizing_capped_by_max_position_pct(self, monkeypatch):
        from trader.core import config as cfg_module
        monkeypatch.setattr(cfg_module.config, "_data", {
            **cfg_module.config._data,
            "risk": {
                **cfg_module.config._data["risk"],
                "position_sizing": {"atr_based": False, "atr_multiplier": 2.0, "max_position_pct": 8.0},
            },
        })
        # sl_dist_qty = 200 // 1 = 200; cap_qty = 20000*8%/100 = 16 → qty = 16
        order = self.rm.validate(make_signal(price=100.0), atr=None)
        assert order.quantity == 16

    def test_atr_sizing_when_enabled(self, monkeypatch):
        from trader.core import config as cfg_module
        monkeypatch.setattr(cfg_module.config, "_data", {
            **cfg_module.config._data,
            "risk": {
                **cfg_module.config._data["risk"],
                "position_sizing": {"atr_based": True, "atr_multiplier": 2.0, "max_position_pct": 0},
            },
        })
        order = self.rm.validate(make_signal(price=2500.0), atr=25.0)
        # risk_amount=200 (1% of 20000), qty = 200 / (2 * 25) = 4
        assert order.quantity == 4

    def test_atr_sizing_capped_by_max_position_pct(self, monkeypatch):
        from trader.core import config as cfg_module
        monkeypatch.setattr(cfg_module.config, "_data", {
            **cfg_module.config._data,
            "risk": {
                **cfg_module.config._data["risk"],
                "position_sizing": {"atr_based": True, "atr_multiplier": 2.0, "max_position_pct": 8.0},
            },
        })
        # capital=20000, max_pos=8% → cap=1600/2500=0 shares (very low price relative to cap)
        # Let's use a more realistic price
        order = self.rm.validate(make_signal(price=100.0), atr=1.0)
        # risk_amount=400, atr_qty = 400/(2*1) = 200
        # cap_qty = 20000*8%/100 = 16
        assert order.quantity == 16


class TestSignalLogger:
    def test_signal_logger_called_on_acceptance(self):
        logged = []
        def mock_logger(**kwargs):
            logged.append(kwargs)

        rm = RiskManager(signal_logger=mock_logger)
        rm.validate(make_signal(), atr=25.0)
        assert len(logged) == 1
        assert logged[0]["accepted"] is True
        assert logged[0]["instrument"] == "NSE:RELIANCE"

    def test_signal_logger_called_on_rejection(self):
        logged = []
        def mock_logger(**kwargs):
            logged.append(kwargs)

        rm = RiskManager(signal_logger=mock_logger)
        rm._halted = True
        rm.validate(make_signal())
        assert len(logged) == 1
        assert logged[0]["accepted"] is False

    def test_no_signal_logger_works_fine(self):
        rm = RiskManager()  # no logger
        order = rm.validate(make_signal(), atr=25.0)
        assert order is not None
