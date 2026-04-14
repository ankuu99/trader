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

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from trader.core.config import config
from trader.core.logger import get_logger
from trader.costs import round_trip_cost
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
    pnl: float | None           # net P&L after transaction costs
    stop_loss: float
    costs: float = 0.0          # total round-trip transaction costs


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

    def total_costs(self) -> float:
        return sum(t.costs for t in self.trades if t.pnl is not None)

    def print_summary(self):
        gross = self.total_pnl() + self.total_costs()
        print(f"\n{'='*55}")
        print(f"  Backtest Report — {self.strategy} on {self.instrument}")
        print(f"  Period : {self.from_dt.date()} → {self.to_dt.date()}")
        print(f"{'='*55}")
        print(f"  Initial capital  : ₹{self.initial_capital:,.0f}")
        print(f"  Final capital    : ₹{self.initial_capital + self.total_pnl():,.2f}")
        print(f"  Gross P&L        : ₹{gross:,.2f}")
        print(f"  Transaction costs: ₹{self.total_costs():,.2f}")
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
                "gross_pnl": round((t.pnl or 0.0) + t.costs, 2),
                "costs": round(t.costs, 2),
                "net_pnl": t.pnl,
                "stop_loss": t.stop_loss,
            }
            for t in self.trades
        ]
        pd.DataFrame(rows).to_csv(path, index=False)
        logger.info("Trades saved to %s", path)


# ------------------------------------------------------------------ #
# Shared candle-processing primitives                                  #
# (used by both Backtest and PortfolioBacktest)                        #
# ------------------------------------------------------------------ #

@dataclass
class _CandleState:
    """Mutable per-symbol state threaded through the candle loop."""
    instrument: str
    strategies: list              # list[Strategy]
    pending_signal: object = None  # Signal | None
    open_trade: object = None      # TradeRecord | None
    prev_close: float | None = None
    chandelier_highest_high: float | None = None
    tr_window: object = field(default_factory=deque)
    target_price: float | None = None  # intra-candle profit target; checked against candle HIGH


@dataclass
class _SharedState:
    """Portfolio-level accumulator shared across all symbols."""
    equity: float
    trades: list        # list[TradeRecord] — shared by reference with report
    equity_curve: list  # list[float]       — shared by reference with report
    deployed_cash: float = 0.0  # entry_price × qty for all open trades; bounds new entries


@dataclass
class _ChandelierCfg:
    enabled: bool
    period: int
    multiplier: float


def _calc_pnl(trade: TradeRecord, exit_price: float) -> tuple[float, float]:
    """Returns (net_pnl, costs) for a completed trade."""
    gross = (
        (exit_price - trade.entry_price) * trade.quantity
        if trade.direction == "BUY"
        else (trade.entry_price - exit_price) * trade.quantity
    )
    costs = round_trip_cost(
        product=config.product,
        quantity=trade.quantity,
        entry_price=trade.entry_price,
        exit_price=exit_price,
        entry_side=trade.direction,
    )
    return gross - costs, costs


def _check_sl(trade: TradeRecord, candle: dict) -> float | None:
    """Return the SL trigger price if it was hit this candle, else None."""
    if trade.stop_loss <= 0:
        return None
    if trade.direction == "BUY" and candle["low"] <= trade.stop_loss:
        return trade.stop_loss
    if trade.direction == "SELL" and candle["high"] >= trade.stop_loss:
        return trade.stop_loss
    return None


_WARMUP_DAYS = 45  # calendar days of pre-period candles fed to strategies to build indicator state


def _make_candle_dict(row: dict) -> dict:
    return {
        "instrument_token": None,
        "timestamp": row["timestamp"],
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": int(row["volume"]),
    }


def _warm_up_strategies(store, strategies: list, instrument: str,
                        timeframe: str, from_dt: datetime) -> None:
    """
    Feed pre-period candles into strategies so their indicators are primed
    before the actual backtest period starts.  Signals are discarded.

    This makes sub-period results consistent: a backtest starting on April 1
    will have the same indicator state as a continuous run that passes through
    April 1 from an earlier start date.
    """
    warmup_df = store.read_candles(instrument, timeframe,
                                   from_dt - timedelta(days=_WARMUP_DAYS), from_dt)
    if warmup_df.empty:
        return
    for row in warmup_df.to_dict("records"):
        candle = _make_candle_dict(row)
        for strategy in strategies:
            strategy.on_candle(candle)


def _process_candle(
    state: _CandleState,
    candle: dict,
    risk: RiskManager,
    shared: _SharedState,
    ch: _ChandelierCfg,
) -> bool:
    """
    Process one candle for one symbol. Mutates state and shared in-place.

    Returns True if the candle was fully processed (strategy was called),
    False if processing stopped early (SL hit — strategy skipped this bar).
    This mirrors the original 'continue' behaviour in Backtest.run().
    """
    # A. Accumulate True Range for chandelier ATR
    if ch.enabled and state.prev_close is not None:
        tr = max(
            candle["high"] - candle["low"],
            abs(candle["high"] - state.prev_close),
            abs(candle["low"] - state.prev_close),
        )
        state.tr_window.append(tr)

    # B. Fill pending signal at this candle's open
    if state.pending_signal is not None:
        fill_price = candle["open"]
        order = risk.validate(state.pending_signal, atr=state.pending_signal.atr)

        if order is not None:
            if state.pending_signal.signal_type == SignalType.ENTRY:
                # Cap quantity to available cash (shared capital enforcement)
                available_cash = shared.equity - shared.deployed_cash
                actual_qty = (
                    min(order.quantity, int(available_cash / fill_price))
                    if fill_price > 0 else 0
                )
                if actual_qty > 0:
                    sl_distance = abs(state.pending_signal.price_hint - order.stop_loss)
                    if state.pending_signal.direction == Direction.BUY:
                        anchored_sl = round(fill_price - sl_distance, 2)
                    else:
                        anchored_sl = round(fill_price + sl_distance, 2)

                    state.open_trade = TradeRecord(
                        instrument=state.instrument,
                        strategy=state.pending_signal.strategy,
                        direction=state.pending_signal.direction.value,
                        entry_time=candle["timestamp"],
                        entry_price=fill_price,
                        exit_time=None,
                        exit_price=None,
                        quantity=actual_qty,
                        pnl=None,
                        stop_loss=anchored_sl,
                    )
                    shared.deployed_cash += actual_qty * fill_price
                    state.target_price = state.pending_signal.target_price
                    if ch.enabled:
                        state.chandelier_highest_high = fill_price
                    risk.on_order_filled(
                        state.instrument, state.pending_signal.direction,
                        actual_qty, fill_price, SignalType.ENTRY,
                    )
                    for strategy in state.strategies:
                        strategy.on_order_update({
                            "status": "COMPLETE",
                            "direction": state.pending_signal.direction.value,
                            "signal_type": SignalType.ENTRY,
                        })

            elif state.pending_signal.signal_type == SignalType.EXIT and state.open_trade:
                pnl, costs = _calc_pnl(state.open_trade, fill_price)
                state.open_trade.exit_time = candle["timestamp"]
                state.open_trade.exit_price = fill_price
                state.open_trade.pnl = pnl
                state.open_trade.costs = costs
                shared.equity += pnl
                shared.deployed_cash = max(
                    0.0, shared.deployed_cash
                    - state.open_trade.quantity * state.open_trade.entry_price
                )
                shared.equity_curve.append(shared.equity)
                shared.trades.append(state.open_trade)
                risk.on_order_filled(
                    state.instrument, state.pending_signal.direction,
                    state.open_trade.quantity, fill_price, SignalType.EXIT,
                )
                for strategy in state.strategies:
                    strategy.on_order_update({
                        "status": "COMPLETE",
                        "direction": state.pending_signal.direction.value,
                        "signal_type": SignalType.EXIT,
                    })
                state.open_trade = None
                state.chandelier_highest_high = None
                state.target_price = None

        state.pending_signal = None

    # C. Update chandelier trailing stop before SL check
    if ch.enabled and state.open_trade is not None and state.open_trade.direction == "BUY":
        if state.chandelier_highest_high is None or candle["high"] > state.chandelier_highest_high:
            state.chandelier_highest_high = candle["high"]
        if len(state.tr_window) >= ch.period and state.chandelier_highest_high:
            atr = sum(state.tr_window) / len(state.tr_window)
            chandelier_sl = round(
                state.chandelier_highest_high - ch.multiplier * atr, 2
            )
            if chandelier_sl > state.open_trade.stop_loss:
                state.open_trade.stop_loss = chandelier_sl

    # D. Check SL hit (before calling strategy)
    if state.open_trade is not None:
        sl_hit_price = _check_sl(state.open_trade, candle)
        if sl_hit_price is not None:
            pnl, costs = _calc_pnl(state.open_trade, sl_hit_price)
            state.open_trade.exit_time = candle["timestamp"]
            state.open_trade.exit_price = sl_hit_price
            state.open_trade.pnl = pnl
            state.open_trade.costs = costs
            shared.equity += pnl
            shared.deployed_cash = max(
                0.0, shared.deployed_cash
                - state.open_trade.quantity * state.open_trade.entry_price
            )
            shared.equity_curve.append(shared.equity)
            shared.trades.append(state.open_trade)
            exit_dir = Direction.SELL if state.open_trade.direction == "BUY" else Direction.BUY
            risk.on_order_filled(
                state.instrument, exit_dir,
                state.open_trade.quantity, sl_hit_price, SignalType.EXIT,
            )
            for strategy in state.strategies:
                strategy.on_order_update({
                    "status": "COMPLETE",
                    "direction": exit_dir.value,
                    "signal_type": SignalType.EXIT,
                })
            state.open_trade = None
            state.chandelier_highest_high = None
            state.target_price = None
            # Do NOT update prev_close here — matches original 'continue' behaviour
            return False

    # D''. Profit target check — candle HIGH (mirrors SL using candle LOW in section D)
    # Exit price is exactly target_price; timestamp is the candle (approximation within candle period)
    if (state.target_price is not None
            and state.open_trade is not None
            and state.open_trade.direction == "BUY"
            and candle["high"] >= state.target_price):
        exit_price = state.target_price
        pnl, costs = _calc_pnl(state.open_trade, exit_price)
        state.open_trade.exit_time = candle["timestamp"]
        state.open_trade.exit_price = exit_price
        state.open_trade.pnl = pnl
        state.open_trade.costs = costs
        shared.equity += pnl
        shared.deployed_cash = max(
            0.0, shared.deployed_cash
            - state.open_trade.quantity * state.open_trade.entry_price
        )
        shared.equity_curve.append(shared.equity)
        shared.trades.append(state.open_trade)
        exit_dir = Direction.SELL
        risk.on_order_filled(
            state.instrument, exit_dir,
            state.open_trade.quantity, exit_price, SignalType.EXIT,
        )
        for strategy in state.strategies:
            strategy.on_order_update({
                "status": "COMPLETE",
                "direction": exit_dir.value,
                "signal_type": SignalType.EXIT,
            })
        state.open_trade = None
        state.chandelier_highest_high = None
        state.target_price = None
        return False  # skip strategy this bar — mirrors SL hit behaviour

    # E. Run strategies, collect first non-None signal
    for strategy in state.strategies:
        sig = strategy.on_candle(candle)
        if sig is not None and state.pending_signal is None:
            state.pending_signal = sig

    state.prev_close = candle["close"]
    return True


# ------------------------------------------------------------------ #
# Backtest — per-symbol isolated engine                                #
# ------------------------------------------------------------------ #

class Backtest:
    def __init__(
        self,
        store: Store,
        strategy: Strategy,
        capital: float | None = None,
        chandelier: bool | None = None,
    ):
        """
        Args:
            store      : Store with cached historical candles
            strategy   : Strategy instance (will be reset before each run)
            capital    : starting capital (defaults to config value)
            chandelier : enable Chandelier trailing stop on open BUY positions.
                         None (default) reads from config.trailing_stop_enabled.
                         Period and multiplier always read from config.
        """
        self._store = store
        self._strategy = strategy
        self._capital = capital or config.total_capital
        self._chandelier = config.trailing_stop_enabled if chandelier is None else chandelier
        self._chandelier_period = config.chandelier_period
        self._chandelier_multiplier = config.chandelier_multiplier

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

        # Warm up strategy indicators with pre-period candles (signals discarded)
        _warm_up_strategies(self._store, [self._strategy], instrument, timeframe, from_dt)

        risk = RiskManager()
        report = BacktestReport(
            instrument=instrument,
            strategy=self._strategy.name,
            from_dt=from_dt,
            to_dt=to_dt,
            initial_capital=self._capital,
        )

        ch = _ChandelierCfg(
            enabled=self._chandelier,
            period=self._chandelier_period,
            multiplier=self._chandelier_multiplier,
        )
        state = _CandleState(
            instrument=instrument,
            strategies=[self._strategy],
            tr_window=deque(maxlen=self._chandelier_period),
        )
        # shared.trades and shared.equity_curve reference report's lists directly
        shared = _SharedState(
            equity=self._capital,
            trades=report.trades,
            equity_curve=report.equity_curve,
        )

        current_date = None
        candles = df.to_dict("records")

        for row in candles:
            candle = _make_candle_dict(row)

            candle_date = candle["timestamp"].date()
            if current_date != candle_date:
                is_monday = candle["timestamp"].weekday() == 0
                current_date = candle_date
                risk.reset_day(is_monday=is_monday)
                # CNC: pending entry signal carries to next morning's open — do not discard

            _process_candle(state, candle, risk, shared, ch)

        # Force-close any position still open at end of backtest
        if state.open_trade is not None and candles:
            last_close = float(candles[-1]["close"])
            pnl, costs = _calc_pnl(state.open_trade, last_close)
            state.open_trade.exit_time = candles[-1]["timestamp"]
            state.open_trade.exit_price = last_close
            state.open_trade.pnl = pnl
            state.open_trade.costs = costs
            shared.equity += pnl
            shared.equity_curve.append(shared.equity)
            shared.trades.append(state.open_trade)
            state.target_price = None

        return report
