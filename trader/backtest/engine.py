"""
Backtest Engine — replays historical candles through strategy instances.

Reuses the exact same Strategy subclasses used in live trading.
The only difference is the data source (SQLite cache) and the order
executor (simulated fills at next candle open).

Usage
-----
    from trader.backtest.engine import Backtest
    from trader.strategies.rsi import RSIStrategy
    from trader.data.store import Store

    store = Store(config.db_path)
    strategy = RSIStrategy("NSE:RELIANCE", config.strategy_config("rsi"))
    bt = Backtest(store, strategy, capital=20000.0)
    report = bt.run("NSE:RELIANCE", "5minute",
                    from_dt=datetime(2024, 1, 1),
                    to_dt=datetime(2024, 3, 31))
    report.print_summary()
    report.save_trades("backtest_trades.csv")
"""

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from trader.core.config import config
from trader.core.logger import get_logger
from trader.data.store import Store
from trader.risk.manager import RiskManager
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)


@dataclass
class TradeRecord:
    instrument: str
    strategy: str
    direction: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime | None
    exit_price: float | None
    quantity: int
    pnl: float | None
    stop_loss: float


@dataclass
class BacktestReport:
    instrument: str
    strategy: str
    from_dt: datetime
    to_dt: datetime
    initial_capital: float
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Computed metrics                                                     #
    # ------------------------------------------------------------------ #

    def total_trades(self) -> int:
        return len([t for t in self.trades if t.pnl is not None])

    def winning_trades(self) -> int:
        return len([t for t in self.trades if t.pnl is not None and t.pnl > 0])

    def losing_trades(self) -> int:
        return len([t for t in self.trades if t.pnl is not None and t.pnl <= 0])

    def win_rate(self) -> float:
        total = self.total_trades()
        return self.winning_trades() / total if total > 0 else 0.0

    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades if t.pnl is not None)

    def max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for value in self.equity_curve:
            peak = max(peak, value)
            dd = (peak - value) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    def sharpe_ratio(self, risk_free_rate: float = 0.065) -> float:
        """Annualised Sharpe ratio using daily P&L from equity curve."""
        if len(self.equity_curve) < 2:
            return 0.0
        returns = pd.Series(self.equity_curve).pct_change().dropna()
        if returns.std() == 0:
            return 0.0
        daily_rf = risk_free_rate / 252
        excess = returns - daily_rf
        return float((excess.mean() / excess.std()) * (252 ** 0.5))

    def avg_pnl_per_trade(self) -> float:
        total = self.total_trades()
        return self.total_pnl() / total if total > 0 else 0.0

    def print_summary(self):
        print(f"\n{'='*55}")
        print(f"  Backtest Report — {self.strategy} on {self.instrument}")
        print(f"  Period : {self.from_dt.date()} → {self.to_dt.date()}")
        print(f"{'='*55}")
        print(f"  Initial capital  : ₹{self.initial_capital:,.0f}")
        print(f"  Final capital    : ₹{self.initial_capital + self.total_pnl():,.2f}")
        print(f"  Net P&L          : ₹{self.total_pnl():,.2f}")
        print(f"  Net P&L %        : {self.total_pnl() / self.initial_capital:.2%}")
        print(f"  Total trades     : {self.total_trades()}")
        print(f"  Win rate         : {self.win_rate():.1%}")
        print(f"  Avg P&L/trade    : ₹{self.avg_pnl_per_trade():,.2f}")
        print(f"  Max drawdown     : {self.max_drawdown():.1%}")
        print(f"  Sharpe ratio     : {self.sharpe_ratio():.2f}")
        print(f"{'='*55}\n")

    def save_trades(self, path: str):
        if not self.trades:
            logger.info("No trades to save.")
            return
        rows = [
            {
                "instrument": t.instrument,
                "strategy": t.strategy,
                "direction": t.direction,
                "entry_time": t.entry_time,
                "entry_price": t.entry_price,
                "exit_time": t.exit_time,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "pnl": t.pnl,
                "stop_loss": t.stop_loss,
            }
            for t in self.trades
        ]
        pd.DataFrame(rows).to_csv(path, index=False)
        logger.info("Trades saved to %s", path)


class Backtest:
    def __init__(self, store: Store, strategy: Strategy, capital: float | None = None,
                 reset_daily: bool = True):
        """
        Args:
            store       : Store with cached historical candles
            strategy    : Strategy instance (will be reset before each run)
            capital     : starting capital (defaults to config value)
            reset_daily : if True, reset daily P&L between calendar days (intraday).
                          Set False for interday backtests where positions carry overnight.
        """
        self._store = store
        self._strategy = strategy
        self._capital = capital or config.total_capital
        self._reset_daily = reset_daily

    def run(
        self,
        instrument: str,
        timeframe: str,
        from_dt: datetime,
        to_dt: datetime,
    ) -> BacktestReport:
        """
        Replay candles and return a BacktestReport.
        """
        df = self._store.read_candles(instrument, timeframe, from_dt, to_dt)
        if df.empty:
            logger.warning("No candles found for %s [%s] in range %s→%s",
                           instrument, timeframe, from_dt.date(), to_dt.date())
            return BacktestReport(
                instrument=instrument,
                strategy=self._strategy.name,
                from_dt=from_dt,
                to_dt=to_dt,
                initial_capital=self._capital,
            )

        logger.info("Backtest | %s [%s] | %d candles | %s → %s",
                    instrument, timeframe, len(df),
                    from_dt.date(), to_dt.date())

        risk = RiskManager()
        report = BacktestReport(
            instrument=instrument,
            strategy=self._strategy.name,
            from_dt=from_dt,
            to_dt=to_dt,
            initial_capital=self._capital,
        )

        # Pending signal waiting for next candle open to fill
        pending_signal: Signal | None = None
        open_trade: TradeRecord | None = None
        equity = self._capital
        current_date = None

        candles = df.to_dict("records")

        for i, row in enumerate(candles):
            candle = {
                "instrument_token": None,
                "timestamp": row["timestamp"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
            }

            # Reset daily P&L at the start of each new trading day (intraday only)
            candle_date = candle["timestamp"].date()
            if current_date != candle_date:
                current_date = candle_date
                if self._reset_daily:
                    risk.reset_day()

            # Fill pending order at this candle's open (next candle after signal)
            if pending_signal is not None:
                fill_price = candle["open"]
                order = risk.validate(pending_signal)

                if order is not None:
                    if pending_signal.signal_type == SignalType.ENTRY:
                        # Anchor SL to actual fill price (not signal price_hint)
                        sl_distance = abs(pending_signal.price_hint - order.stop_loss)
                        if pending_signal.direction == Direction.BUY:
                            anchored_sl = round(fill_price - sl_distance, 2)
                        else:
                            anchored_sl = round(fill_price + sl_distance, 2)

                        open_trade = TradeRecord(
                            instrument=instrument,
                            strategy=self._strategy.name,
                            direction=pending_signal.direction.value,
                            entry_time=candle["timestamp"],
                            entry_price=fill_price,
                            exit_time=None,
                            exit_price=None,
                            quantity=order.quantity,
                            pnl=None,
                            stop_loss=anchored_sl,
                        )
                        risk.on_order_filled(
                            instrument, pending_signal.direction,
                            order.quantity, fill_price, SignalType.ENTRY,
                        )
                        # Notify strategy of fill
                        self._strategy.on_order_update({
                            "status": "COMPLETE",
                            "direction": pending_signal.direction.value,
                            "signal_type": SignalType.ENTRY,
                        })

                    elif pending_signal.signal_type == SignalType.EXIT and open_trade:
                        pnl = self._calc_pnl(open_trade, fill_price)
                        open_trade.exit_time = candle["timestamp"]
                        open_trade.exit_price = fill_price
                        open_trade.pnl = pnl
                        equity += pnl
                        report.equity_curve.append(equity)
                        report.trades.append(open_trade)
                        risk.on_order_filled(
                            instrument, pending_signal.direction,
                            open_trade.quantity, fill_price, SignalType.EXIT,
                        )
                        self._strategy.on_order_update({
                            "status": "COMPLETE",
                            "direction": pending_signal.direction.value,
                            "signal_type": SignalType.EXIT,
                        })
                        open_trade = None

                pending_signal = None

            # Check SL hit during this candle (before calling strategy)
            if open_trade is not None:
                sl_hit_price = self._check_sl(open_trade, candle)
                if sl_hit_price is not None:
                    pnl = self._calc_pnl(open_trade, sl_hit_price)
                    open_trade.exit_time = candle["timestamp"]
                    open_trade.exit_price = sl_hit_price
                    open_trade.pnl = pnl
                    equity += pnl
                    report.equity_curve.append(equity)
                    report.trades.append(open_trade)
                    exit_dir = Direction.SELL if open_trade.direction == "BUY" else Direction.BUY
                    risk.on_order_filled(
                        instrument, exit_dir,
                        open_trade.quantity, sl_hit_price, SignalType.EXIT,
                    )
                    self._strategy.on_order_update({
                        "status": "COMPLETE",
                        "direction": exit_dir.value,
                        "signal_type": SignalType.EXIT,
                    })
                    open_trade = None
                    continue

            # Run strategy on this candle
            signal = self._strategy.on_candle(candle)
            if signal is not None:
                pending_signal = signal

        # Force-close any position still open at end of backtest
        if open_trade is not None and candles:
            last_close = float(candles[-1]["close"])
            pnl = self._calc_pnl(open_trade, last_close)
            open_trade.exit_time = candles[-1]["timestamp"]
            open_trade.exit_price = last_close
            open_trade.pnl = pnl
            equity += pnl
            report.equity_curve.append(equity)
            report.trades.append(open_trade)

        return report

    @staticmethod
    def _calc_pnl(trade: TradeRecord, exit_price: float) -> float:
        if trade.direction == "BUY":
            return (exit_price - trade.entry_price) * trade.quantity
        return (trade.entry_price - exit_price) * trade.quantity

    @staticmethod
    def _check_sl(trade: TradeRecord, candle: dict) -> float | None:
        """Return the SL trigger price if it was hit this candle, else None."""
        if trade.stop_loss <= 0:
            return None
        if trade.direction == "BUY" and candle["low"] <= trade.stop_loss:
            return trade.stop_loss
        if trade.direction == "SELL" and candle["high"] >= trade.stop_loss:
            return trade.stop_loss
        return None
