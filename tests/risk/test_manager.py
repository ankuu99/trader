import pytest

from trader.strategies.base import Direction, Signal, SignalType
from trader.risk.manager import RiskManager, should_square_off
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
        # max_risk = 20000 * 2% = 400, atr = 25 → qty = 400 // 25 = 16
        order = self.rm.validate(make_signal(price=2500.0), atr=25.0)
        assert order.quantity == 16

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
        # Fill up to max (3 from config)
        for i in range(3):
            sig = make_signal(instrument=f"NSE:STOCK{i}", price=100.0)
            order = self.rm.validate(sig, atr=1.0)
            fill(self.rm, f"NSE:STOCK{i}", Direction.BUY, order.quantity, 100.0, SignalType.ENTRY)
        # 4th entry should be rejected
        order = self.rm.validate(make_signal(instrument="NSE:STOCK4", price=100.0), atr=1.0)
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
        assert self.rm.realised_pnl() == 16 * 50  # qty(16) * price_diff(50)

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
        assert should_square_off(datetime(2024, 1, 15, 15, 15)) is True
        assert should_square_off(datetime(2024, 1, 15, 15, 20)) is True

    def test_should_square_off_false_before_time(self):
        assert should_square_off(datetime(2024, 1, 15, 15, 14)) is False
