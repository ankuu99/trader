from datetime import datetime, timedelta, time as dtime

import pytest

from trader.backtest.engine import Backtest, BacktestReport, TradeRecord
from trader.data.store import Store
from trader.strategies.orb import ORBStrategy
from trader.strategies.rsi import RSIStrategy

import pandas as pd


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


def write_candles(store, instrument, timeframe, rows):
    """rows: list of (timestamp_str, open, high, low, close, volume)"""
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    store.write_candles(instrument, timeframe, df)


def ts(date_str, time_str):
    return f"{date_str} {time_str}"


class TestBacktestEngine:

    def test_returns_empty_report_when_no_data(self, store):
        strategy = RSIStrategy("NSE:RELIANCE", {"period": 5})
        bt = Backtest(store, strategy, capital=20000.0)
        report = bt.run("NSE:RELIANCE", "5minute",
                        datetime(2024, 1, 1), datetime(2024, 1, 31))
        assert report.total_trades() == 0
        assert report.total_pnl() == 0.0

    def test_no_trades_without_signal(self, store):
        # Flat prices — RSI stays at 50, no signal
        base = datetime(2024, 1, 15, 9, 15)
        rows = [(str(base + timedelta(minutes=i * 5)), 100, 101, 99, 100, 1000)
                for i in range(20)]
        write_candles(store, "NSE:RELIANCE", "5minute", rows)
        strategy = RSIStrategy("NSE:RELIANCE", {"period": 5, "oversold": 30})
        bt = Backtest(store, strategy, capital=20000.0)
        report = bt.run("NSE:RELIANCE", "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        assert report.total_trades() == 0

    def test_orb_breakout_produces_trade(self, store):
        rows = [
            # Opening range candles (9:15, 9:20)
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 1000),
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 1000),
            # First candle after range — no breakout
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 1000),
            # Breakout candle (close > 106)
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 1000),
            # Fill candle (next open after signal)
            (ts("2024-01-15", "09:40:00"), 110, 115, 108, 113, 1000),
            # Exit candle
            (ts("2024-01-15", "15:15:00"), 113, 114, 112, 113, 1000),
            (ts("2024-01-15", "15:20:00"), 113, 114, 112, 112, 1000),
        ]
        write_candles(store, "NSE:INFY", "5minute", rows)
        strategy = ORBStrategy("NSE:INFY", {"range_minutes": 15})
        bt = Backtest(store, strategy, capital=20000.0)
        report = bt.run("NSE:INFY", "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        assert report.total_trades() >= 1
        trade = report.trades[0]
        assert trade.direction == "BUY"
        assert trade.entry_price == 110.0   # next candle open after signal

    def test_sl_hit_closes_trade(self, store):
        rows = [
            # Opening range
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 1000),
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 1000),
            # Range lock
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 1000),
            # Breakout
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 1000),
            # Fill at open=108
            (ts("2024-01-15", "09:40:00"), 108, 109, 107, 108, 1000),
            # SL hit (low drops below SL which is ~107)
            (ts("2024-01-15", "09:45:00"), 107, 108, 100, 101, 1000),
        ]
        write_candles(store, "NSE:INFY", "5minute", rows)
        strategy = ORBStrategy("NSE:INFY", {"range_minutes": 15})
        bt = Backtest(store, strategy, capital=20000.0)
        report = bt.run("NSE:INFY", "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        assert report.total_trades() == 1
        assert report.trades[0].pnl is not None
        assert report.trades[0].pnl < 0  # SL hit = loss

    def test_win_rate_calculation(self):
        report = BacktestReport(
            instrument="NSE:RELIANCE", strategy="test",
            from_dt=datetime(2024, 1, 1), to_dt=datetime(2024, 3, 31),
            initial_capital=20000.0,
        )
        report.trades = [
            TradeRecord("NSE:RELIANCE", "test", "BUY",
                        datetime(2024, 1, 2), 100, datetime(2024, 1, 3), 110, 10, 100.0, 95.0),
            TradeRecord("NSE:RELIANCE", "test", "BUY",
                        datetime(2024, 1, 4), 100, datetime(2024, 1, 5), 90, 10, -100.0, 95.0),
            TradeRecord("NSE:RELIANCE", "test", "BUY",
                        datetime(2024, 1, 6), 100, datetime(2024, 1, 7), 115, 10, 150.0, 95.0),
        ]
        assert report.win_rate() == pytest.approx(2 / 3)
        assert report.total_pnl() == pytest.approx(150.0)

    def test_max_drawdown_calculation(self):
        report = BacktestReport(
            instrument="NSE:RELIANCE", strategy="test",
            from_dt=datetime(2024, 1, 1), to_dt=datetime(2024, 3, 31),
            initial_capital=20000.0,
        )
        # Equity: 20000 → 22000 → 19000 → 21000
        report.equity_curve = [20000, 22000, 19000, 21000]
        # Max drawdown from peak 22000 to trough 19000 = 3000/22000
        assert report.max_drawdown() == pytest.approx(3000 / 22000, rel=1e-3)

    def test_open_position_force_closed_at_end(self, store):
        rows = [
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 1000),
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 1000),
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 1000),
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 1000),
            # Only one more candle — entry fill + forced close (low must stay above SL=108.9)
            (ts("2024-01-15", "09:40:00"), 110, 115, 109, 114, 1000),
        ]
        write_candles(store, "NSE:INFY", "5minute", rows)
        strategy = ORBStrategy("NSE:INFY", {"range_minutes": 15})
        bt = Backtest(store, strategy, capital=20000.0)
        report = bt.run("NSE:INFY", "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        # Position should be force-closed at last candle close
        assert report.total_trades() == 1
        assert report.trades[0].exit_price == 114.0
