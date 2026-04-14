"""
Tests for PortfolioBacktest — shared-capital multi-symbol backtest engine.
"""

from datetime import datetime, timedelta

import pytest

from trader.backtest.portfolio import PortfolioBacktest, PortfolioBacktestReport
from trader.data.store import Store
from trader.strategies.orb import ORBStrategy

import pandas as pd

# Simple ORB-only factory used by all tests that rely on orb_breakout_rows()
def _orb_factory(symbol, cfg):
    return [ORBStrategy(symbol, {"range_minutes": 15, "volume_filter": False, "gap_filter": False})]


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


def write_candles(store, instrument, timeframe, rows):
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    store.write_candles(instrument, timeframe, df)


def ts(date_str, time_str):
    return f"{date_str} {time_str}"


def orb_breakout_rows(date="2024-01-15"):
    """Standard ORB breakout sequence: signal at 09:35, fill at 09:40."""
    return [
        (ts(date, "09:15:00"), 100, 105, 99,  102, 2000),
        (ts(date, "09:20:00"), 102, 106, 101, 104, 2000),
        (ts(date, "09:30:00"), 104, 107, 103, 104, 2000),
        (ts(date, "09:35:00"), 104, 112, 104, 110, 2000),  # breakout signal
        (ts(date, "09:40:00"), 110, 115, 109, 113, 2000),  # fill candle
        (ts(date, "15:15:00"), 113, 114, 112, 112, 2000),  # EOD exit
    ]


class TestBasicPortfolioRun:
    def test_empty_when_no_data(self, store):
        bt = PortfolioBacktest(store, capital=20000.0)
        report = bt.run(["NSE:MISSING"], "5minute",
                        datetime(2024, 1, 1), datetime(2024, 1, 31))
        assert report.total_trades() == 0
        assert report.equity_curve == []
        assert report.total_pnl() == 0.0

    def test_single_symbol_produces_trade(self, store):
        write_candles(store, "NSE:INFY", "5minute", orb_breakout_rows())
        bt = PortfolioBacktest(store, capital=20000.0, strategies_factory=_orb_factory)
        report = bt.run(["NSE:INFY"], "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        assert report.total_trades() >= 1
        assert report.trades[0].direction == "BUY"

    def test_equity_curve_has_entry_per_closed_trade(self, store):
        write_candles(store, "NSE:INFY", "5minute", orb_breakout_rows())
        bt = PortfolioBacktest(store, capital=20000.0, strategies_factory=_orb_factory)
        report = bt.run(["NSE:INFY"], "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        assert len(report.equity_curve) == report.total_trades()


class TestSharedCapital:
    def test_max_positions_enforced_portfolio_wide(self, store):
        """With max_open_positions=1, two simultaneous signals → only 1 trade."""
        rows_a = orb_breakout_rows("2024-01-15")
        rows_b = orb_breakout_rows("2024-01-15")
        write_candles(store, "NSE:INFY",     "5minute", rows_a)
        write_candles(store, "NSE:RELIANCE", "5minute", rows_b)

        # Patch config max_open_positions to 1 for this test
        import trader.core.config as cfg_mod
        orig = cfg_mod.config._data["risk"]["max_open_positions"]
        cfg_mod.config._data["risk"]["max_open_positions"] = 1
        try:
            bt = PortfolioBacktest(store, capital=20000.0, strategies_factory=_orb_factory)
            report = bt.run(
                ["NSE:INFY", "NSE:RELIANCE"], "5minute",
                datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59),
            )
            assert report.total_trades() == 1
        finally:
            cfg_mod.config._data["risk"]["max_open_positions"] = orig

    def test_equity_reflects_all_symbols(self, store):
        """Two profitable trades (different symbols, different days) → equity increases for each."""
        # INFY trades on Jan 15 with a 15:25 square-off candle so cash is freed before Jan 16
        infy_rows = orb_breakout_rows("2024-01-15") + [
            (ts("2024-01-15", "15:25:00"), 112, 113, 111, 112, 500),
        ]
        write_candles(store, "NSE:INFY",     "5minute", infy_rows)
        write_candles(store, "NSE:RELIANCE", "5minute", orb_breakout_rows("2024-01-16"))

        import trader.core.config as cfg_mod
        orig = cfg_mod.config._data["risk"]["max_open_positions"]
        cfg_mod.config._data["risk"]["max_open_positions"] = 6
        try:
            bt = PortfolioBacktest(store, capital=20000.0, strategies_factory=_orb_factory)
            report = bt.run(
                ["NSE:INFY", "NSE:RELIANCE"], "5minute",
                datetime(2024, 1, 15), datetime(2024, 1, 16, 23, 59),
            )
            assert report.total_trades() == 2
            # Each closed trade appends to equity_curve
            assert len(report.equity_curve) == 2
        finally:
            cfg_mod.config._data["risk"]["max_open_positions"] = orig

    def test_per_symbol_pnl_adds_up_to_total(self, store):
        infy_rows = orb_breakout_rows("2024-01-15") + [
            (ts("2024-01-15", "15:25:00"), 112, 113, 111, 112, 500),
        ]
        write_candles(store, "NSE:INFY",     "5minute", infy_rows)
        write_candles(store, "NSE:RELIANCE", "5minute", orb_breakout_rows("2024-01-16"))

        import trader.core.config as cfg_mod
        orig = cfg_mod.config._data["risk"]["max_open_positions"]
        cfg_mod.config._data["risk"]["max_open_positions"] = 6
        try:
            bt = PortfolioBacktest(store, capital=20000.0, strategies_factory=_orb_factory)
            report = bt.run(
                ["NSE:INFY", "NSE:RELIANCE"], "5minute",
                datetime(2024, 1, 15), datetime(2024, 1, 16, 23, 59),
            )
            sym_total = sum(s.total_pnl() for s in report.symbol_summaries.values())
            assert abs(sym_total - report.total_pnl()) < 0.01
        finally:
            cfg_mod.config._data["risk"]["max_open_positions"] = orig


class TestDailyHalt:
    def test_daily_halt_blocks_second_symbol_same_day(self, store):
        """Loss on SYMB_A triggers daily halt → SYMB_B entry blocked."""
        # SYMB_A: breakout, then sharp SL hit (loss big enough to trip daily limit)
        rows_a = [
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 2000),
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 2000),
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 2000),
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 2000),  # signal
            (ts("2024-01-15", "09:40:00"), 110, 111, 109, 110, 2000),  # fill at 110
            # Crash far below SL — large loss
            (ts("2024-01-15", "09:45:00"), 109,  111,  50,  50, 2000),
        ]
        # SYMB_B: breakout signal comes AFTER the halt
        rows_b = [
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 2000),
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 2000),
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 2000),
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 2000),
            (ts("2024-01-15", "09:50:00"), 110, 115, 109, 113, 2000),  # fill candle (blocked)
        ]
        write_candles(store, "NSE:INFY",     "5minute", rows_a)
        write_candles(store, "NSE:RELIANCE", "5minute", rows_b)

        import trader.core.config as cfg_mod
        # Set daily limit low enough to trip on SYMB_A's loss
        orig = cfg_mod.config._data["capital"]["daily_loss_limit_pct"]
        cfg_mod.config._data["capital"]["daily_loss_limit_pct"] = 0.1  # 0.1% = ₹20
        try:
            bt = PortfolioBacktest(store, capital=20000.0, strategies_factory=_orb_factory)
            report = bt.run(
                ["NSE:INFY", "NSE:RELIANCE"], "5minute",
                datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59),
            )
            reliance_trades = [t for t in report.trades if t.instrument == "NSE:RELIANCE"]
            assert len(reliance_trades) == 0
        finally:
            cfg_mod.config._data["capital"]["daily_loss_limit_pct"] = orig


class TestForceClose:
    def test_open_position_force_closed_at_end(self, store):
        rows = [
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 2000),
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 2000),
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 2000),
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 2000),
            # Only one more candle — fill + no further candles → force-close
            (ts("2024-01-15", "09:40:00"), 110, 115, 109, 114, 2000),
        ]
        write_candles(store, "NSE:INFY", "5minute", rows)
        bt = PortfolioBacktest(store, capital=20000.0, strategies_factory=_orb_factory)
        report = bt.run(["NSE:INFY"], "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        assert report.total_trades() == 1
        assert report.trades[0].pnl is not None
        assert report.trades[0].exit_price == 114.0


class TestPerSymbolSummary:
    def test_symbol_summary_populated(self, store):
        write_candles(store, "NSE:INFY", "5minute", orb_breakout_rows())
        bt = PortfolioBacktest(store, capital=20000.0, strategies_factory=_orb_factory)
        report = bt.run(["NSE:INFY"], "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        assert "NSE:INFY" in report.symbol_summaries
        s = report.symbol_summaries["NSE:INFY"]
        assert s.total_trades() == report.total_trades()

    def test_symbol_summary_pnl_matches_filtered_trades(self, store):
        write_candles(store, "NSE:INFY", "5minute", orb_breakout_rows())
        bt = PortfolioBacktest(store, capital=20000.0, strategies_factory=_orb_factory)
        report = bt.run(["NSE:INFY"], "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        s = report.symbol_summaries["NSE:INFY"]
        expected = sum(t.pnl for t in report.trades
                       if t.instrument == "NSE:INFY" and t.pnl is not None)
        assert abs(s.total_pnl() - expected) < 0.01


class TestIntradaySquareOff:
    def test_position_closed_at_square_off_time(self, store):
        """Open MIS position should be force-closed at the configured square_off_time."""
        rows = [
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 2000),
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 2000),
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 2000),
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 2000),  # signal
            (ts("2024-01-15", "09:40:00"), 110, 115, 109, 113, 2000),  # fill
            (ts("2024-01-15", "15:25:00"), 113, 114, 112, 113, 500),   # square-off candle
        ]
        write_candles(store, "NSE:INFY", "5minute", rows)
        bt = PortfolioBacktest(store, capital=20000.0, strategies_factory=_orb_factory)
        report = bt.run(["NSE:INFY"], "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        assert report.total_trades() == 1
        trade = report.trades[0]
        assert trade.pnl is not None
        assert trade.exit_time == pd.Timestamp("2024-01-15 15:25:00")

    def test_no_multi_day_positions_in_mis_mode(self, store):
        """A position opened on day 1 must not carry over to day 2 in MIS mode."""
        rows = [
            (ts("2024-01-15", "09:15:00"), 100, 105, 99,  102, 2000),
            (ts("2024-01-15", "09:20:00"), 102, 106, 101, 104, 2000),
            (ts("2024-01-15", "09:30:00"), 104, 107, 103, 104, 2000),
            (ts("2024-01-15", "09:35:00"), 104, 112, 104, 110, 2000),  # signal
            (ts("2024-01-15", "09:40:00"), 110, 115, 109, 113, 2000),  # fill
            (ts("2024-01-15", "15:25:00"), 113, 114, 112, 113, 500),   # square-off
            (ts("2024-01-16", "09:15:00"), 113, 116, 112, 114, 2000),  # next day — must not see open position
        ]
        write_candles(store, "NSE:INFY", "5minute", rows)
        bt = PortfolioBacktest(store, capital=20000.0, strategies_factory=_orb_factory)
        report = bt.run(["NSE:INFY"], "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 16, 23, 59))
        for t in report.trades:
            if t.pnl is not None:
                assert t.entry_time.date() == t.exit_time.date(), (
                    f"Trade {t.instrument} crossed midnight: "
                    f"{t.entry_time} → {t.exit_time}"
                )


class TestChandelierPortfolio:
    def test_chandelier_enabled_produces_trade(self, store):
        """Chandelier mode runs without error in portfolio engine."""
        rows = orb_breakout_rows()
        base = datetime(2024, 1, 15, 9, 45)
        for i in range(10):
            t = base + timedelta(minutes=i * 5)
            rows.append((str(t), 113 + i, 115 + i, 112 + i, 114 + i, 2000))
        rows.append((str(base + timedelta(minutes=10 * 5)), 123, 124, 50, 52, 2000))
        write_candles(store, "NSE:INFY", "5minute", rows)
        bt = PortfolioBacktest(store, capital=20000.0, chandelier=True,
                               strategies_factory=_orb_factory)
        report = bt.run(["NSE:INFY"], "5minute",
                        datetime(2024, 1, 15), datetime(2024, 1, 15, 23, 59))
        assert report.total_trades() >= 1
