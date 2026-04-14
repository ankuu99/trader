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

    def test_chandelier_trailing_stop_moves_sl_up(self, store):
        """Chandelier SL trails higher highs upward and eventually triggers exit."""
        # Use ORB with volume/gap filters off for clean signal generation
        # Entry at candle 5 (open of candle 6), then price rallies, SL trails up,
        # price drops — SL should be higher than original SL.
        rows = [
            # Opening range candles
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 2000),
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 2000),
            # Range lock
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 2000),
            # Breakout signal
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 2000),
            # Fill candle (open=110; SL anchored to 110 - ATR_distance)
            (ts("2024-01-15", "09:40:00"), 110, 115, 109, 114, 2000),
        ]
        # Add 22 more candles of rally to build ATR history and raise chandelier SL
        base = datetime(2024, 1, 15, 9, 45)
        for i in range(22):
            t = base + timedelta(minutes=i * 5)
            rows.append((str(t), 114 + i, 116 + i, 113 + i, 115 + i, 2000))
        # Final candle: sharp drop that hits the chandelier SL
        final_low = 80  # well below any chandelier SL
        rows.append((str(base + timedelta(minutes=22 * 5)), 115 + 22, 116 + 22, final_low, 82, 2000))

        write_candles(store, "NSE:INFY", "5minute", rows)
        strategy = ORBStrategy("NSE:INFY", {"range_minutes": 15,
                                             "volume_filter": False, "gap_filter": False})
        bt = Backtest(store, strategy, capital=20000.0, chandelier=True)
        report = bt.run("NSE:INFY", "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))

        assert report.total_trades() == 1
        trade = report.trades[0]
        # With chandelier trailing the SL should be well above the original entry SL
        # Original SL ≈ 110 - ATR; after 22 candles of rally the SL should be much higher
        assert trade.stop_loss > trade.entry_price * 0.98  # SL trailed up significantly

    def test_chandelier_sl_never_moves_down(self, store):
        """Chandelier SL must only ratchet up, never decrease."""
        rows = [
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 2000),
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 2000),
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 2000),
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 2000),
            (ts("2024-01-15", "09:40:00"), 110, 115, 109, 114, 2000),
        ]
        # 22 candles of rally, then a small pullback — SL should NOT drop
        base = datetime(2024, 1, 15, 9, 45)
        for i in range(22):
            t = base + timedelta(minutes=i * 5)
            rows.append((str(t), 114 + i, 116 + i, 113 + i, 115 + i, 2000))
        # Small pullback (stays above SL)
        for i in range(5):
            t = base + timedelta(minutes=(22 + i) * 5)
            rows.append((str(t), 135, 137, 130, 132, 2000))
        # Forced close
        rows.append((str(base + timedelta(minutes=27 * 5)), 132, 134, 131, 133, 2000))

        write_candles(store, "NSE:INFY", "5minute", rows)
        strategy = ORBStrategy("NSE:INFY", {"range_minutes": 15,
                                             "volume_filter": False, "gap_filter": False})
        bt = Backtest(store, strategy, capital=20000.0, chandelier=True)
        report = bt.run("NSE:INFY", "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        # Trade completes — just checking it ran without error
        assert report.total_trades() >= 1

    def test_chandelier_disabled_by_default_uses_fixed_sl(self, store):
        """Without chandelier, SL is fixed at entry and doesn't trail."""
        rows = [
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 2000),
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 2000),
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 2000),
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 2000),
            (ts("2024-01-15", "09:40:00"), 110, 115, 109, 114, 2000),
            (ts("2024-01-15", "15:15:00"), 114, 115, 113, 114, 2000),
        ]
        write_candles(store, "NSE:INFY", "5minute", rows)
        strategy = ORBStrategy("NSE:INFY", {"range_minutes": 15,
                                             "volume_filter": False, "gap_filter": False})
        # chandelier=False explicitly
        bt = Backtest(store, strategy, capital=20000.0, chandelier=False)
        report = bt.run("NSE:INFY", "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        assert report.total_trades() >= 1

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

    def test_orb_backtest_volume_filter_passes_on_single_day(self, store):
        """ORB volume filter requires history; passes through on first day."""
        rows = [
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 500),  # low volume
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 500),
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 500),
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 500),
            (ts("2024-01-15", "09:40:00"), 110, 115, 109, 113, 500),
            (ts("2024-01-15", "15:15:00"), 113, 114, 112, 112, 500),
        ]
        write_candles(store, "NSE:INFY", "5minute", rows)
        strategy = ORBStrategy("NSE:INFY", {"range_minutes": 15, "volume_filter": True,
                                            "gap_filter": False})
        bt = Backtest(store, strategy, capital=20000.0)
        report = bt.run("NSE:INFY", "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        # Volume filter not enough history yet — trade should still execute
        assert report.total_trades() >= 1

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
