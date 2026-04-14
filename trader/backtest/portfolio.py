"""
Portfolio Backtest — replays all symbols simultaneously with shared capital.

Unlike the per-symbol Backtest, this engine:
  - Shares one RiskManager across all symbols and strategies
  - Enforces max_open_positions portfolio-wide
  - Tracks a single equity curve updated by all trades
  - Processes candles in time-sorted order across all symbols

Usage
-----
    from trader.backtest.portfolio import PortfolioBacktest

    bt = PortfolioBacktest(store, capital=20000.0)
    report = bt.run(
        symbols=["NSE:INDHOTEL", "NSE:MARKSANS"],
        timeframe="5minute",
        from_dt=datetime(2024, 1, 1),
        to_dt=datetime(2024, 3, 31),
    )
    report.print_summary()
    report.save_trades("portfolio_trades.csv")
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from trader.backtest.engine import (
    TradeRecord,
    _CandleState,
    _ChandelierCfg,
    _SharedState,
    _calc_pnl,
    _check_sl,
    _make_candle_dict,
    _process_candle,
    _warm_up_strategies,
)
from trader.core.config import config
from trader.core.logger import get_logger
from trader.data.store import Store
from trader.risk.manager import RiskManager
from trader.strategies.registry import build_strategies

logger = get_logger(__name__)


# ------------------------------------------------------------------ #
# Report dataclasses                                                   #
# ------------------------------------------------------------------ #

@dataclass
class SymbolSummary:
    symbol: str
    trades: list  # list[TradeRecord]

    def total_trades(self) -> int:
        return len([t for t in self.trades if t.pnl is not None])

    def winning_trades(self) -> int:
        return len([t for t in self.trades if t.pnl is not None and t.pnl > 0])

    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades if t.pnl is not None)

    def win_rate(self) -> float:
        total = self.total_trades()
        return self.winning_trades() / total if total > 0 else 0.0

    def total_costs(self) -> float:
        return sum(t.costs for t in self.trades if t.pnl is not None)


@dataclass
class PortfolioBacktestReport:
    symbols: list             # list[str]
    from_dt: datetime
    to_dt: datetime
    initial_capital: float
    trades: list = field(default_factory=list)        # list[TradeRecord]
    equity_curve: list = field(default_factory=list)  # list[float]
    symbol_summaries: dict = field(default_factory=dict)  # str → SymbolSummary

    # ------------------------------------------------------------------ #
    # Metrics (same logic as BacktestReport)                              #
    # ------------------------------------------------------------------ #

    def total_trades(self) -> int:
        return len([t for t in self.trades if t.pnl is not None])

    def winning_trades(self) -> int:
        return len([t for t in self.trades if t.pnl is not None and t.pnl > 0])

    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades if t.pnl is not None)

    def win_rate(self) -> float:
        total = self.total_trades()
        return self.winning_trades() / total if total > 0 else 0.0

    def avg_pnl_per_trade(self) -> float:
        total = self.total_trades()
        return self.total_pnl() / total if total > 0 else 0.0

    def total_costs(self) -> float:
        return sum(t.costs for t in self.trades if t.pnl is not None)

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
        if len(self.equity_curve) < 2:
            return 0.0
        returns = pd.Series(self.equity_curve).pct_change().dropna()
        if returns.std() == 0:
            return 0.0
        daily_rf = risk_free_rate / 252
        excess = returns - daily_rf
        return float((excess.mean() / excess.std()) * (252 ** 0.5))

    def print_summary(self):
        gross = self.total_pnl() + self.total_costs()
        sym_str = ", ".join(s.split(":")[-1] for s in self.symbols)
        print(f"\n{'='*57}")
        print(f"  Portfolio Backtest — {self.from_dt.date()} → {self.to_dt.date()}")
        print(f"  Symbols  : {sym_str} ({len(self.symbols)})")
        print(f"  Capital  : ₹{self.initial_capital:,.0f}")
        print(f"{'='*57}")
        print(f"  Gross P&L        : ₹{gross:,.2f}")
        print(f"  Transaction costs: ₹{self.total_costs():,.2f}")
        print(f"  Net P&L          : ₹{self.total_pnl():,.2f}"
              f"  ({self.total_pnl() / self.initial_capital:.2%})")
        print(f"  Total trades     : {self.total_trades()}")
        print(f"  Win rate         : {self.win_rate():.1%}")
        print(f"  Avg P&L/trade    : ₹{self.avg_pnl_per_trade():,.2f}")
        print(f"  Max drawdown     : {self.max_drawdown():.1%}")
        print(f"  Sharpe ratio     : {self.sharpe_ratio():.2f}")
        print(f"{'='*57}")

        if self.symbol_summaries:
            print(f"\n  {'Symbol':<25}  {'Trades':>6}  {'Win%':>6}  {'Net P&L':>12}")
            print(f"  {'-'*25}  {'-'*6}  {'-'*6}  {'-'*12}")
            for sym, s in self.symbol_summaries.items():
                label = sym.split(":")[-1]
                win = f"{s.win_rate():.1%}" if s.total_trades() > 0 else "  —"
                print(f"  {label:<25}  {s.total_trades():>6}  {win:>6}  "
                      f"₹{s.total_pnl():>10,.2f}")
            print()

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
        logger.info("Portfolio trades saved to %s", path)


# ------------------------------------------------------------------ #
# PortfolioBacktest engine                                             #
# ------------------------------------------------------------------ #

class PortfolioBacktest:
    def __init__(
        self,
        store: Store,
        capital: float | None = None,
        chandelier: bool | None = None,
        strategies_factory=None,
    ):
        """
        Args:
            store              : Store with cached historical candles
            capital            : starting capital (defaults to config value)
            chandelier         : enable Chandelier trailing stop. None reads from config.
            strategies_factory : callable(symbol, config) -> list[Strategy].
                                 Defaults to build_strategies. Override in tests to inject
                                 explicit strategy instances instead of using live config.
        """
        self._store = store
        self._capital = capital or config.total_capital
        self._chandelier = config.trailing_stop_enabled if chandelier is None else chandelier
        self._chandelier_period = config.chandelier_period
        self._chandelier_multiplier = config.chandelier_multiplier
        self._strategies_factory = strategies_factory or build_strategies

    def run(
        self,
        symbols: list,
        timeframe: str,
        from_dt: datetime,
        to_dt: datetime,
    ) -> PortfolioBacktestReport:
        """
        Replay candles for all symbols in time-synchronised order and return
        a PortfolioBacktestReport with shared-capital results.
        """
        ch = _ChandelierCfg(
            enabled=self._chandelier,
            period=self._chandelier_period,
            multiplier=self._chandelier_multiplier,
        )

        # Pre-load candles and build per-symbol state
        symbol_states: list[_CandleState] = []
        for symbol in symbols:
            df = self._store.read_candles(symbol, timeframe, from_dt, to_dt)
            if df.empty:
                logger.warning("No candles for %s [%s] — skipping", symbol, timeframe)
                continue
            candles = [_make_candle_dict(row) for row in df.to_dict("records")]
            strategies = self._strategies_factory(symbol, config)
            state = _CandleState(
                instrument=symbol,
                strategies=strategies,
                tr_window=deque(maxlen=self._chandelier_period),
            )
            # Attach pre-loaded candles and cursor as extra attributes
            state._candles = candles   # type: ignore[attr-defined]
            state._cursor = 0          # type: ignore[attr-defined]
            symbol_states.append(state)

        if not symbol_states:
            logger.warning("No candle data found for any symbol in range %s→%s",
                           from_dt.date(), to_dt.date())
            return PortfolioBacktestReport(
                symbols=symbols, from_dt=from_dt, to_dt=to_dt,
                initial_capital=self._capital,
            )

        logger.info("PortfolioBacktest | %d symbols | %s → %s",
                    len(symbol_states), from_dt.date(), to_dt.date())

        # Warm up strategy indicators with pre-period candles (signals discarded)
        for state in symbol_states:
            _warm_up_strategies(self._store, state.strategies, state.instrument,
                                timeframe, from_dt)

        # Merged timeline: all unique timestamps across all symbols, sorted
        all_ts = sorted({
            c["timestamp"]
            for state in symbol_states
            for c in state._candles  # type: ignore[attr-defined]
        })

        # Shared portfolio state — trades/equity_curve populated in-place
        report = PortfolioBacktestReport(
            symbols=[s.instrument for s in symbol_states],
            from_dt=from_dt,
            to_dt=to_dt,
            initial_capital=self._capital,
        )
        shared = _SharedState(
            equity=self._capital,
            trades=report.trades,
            equity_curve=report.equity_curve,
        )
        risk = RiskManager()
        current_date = None

        for ts in all_ts:
            # Daily reset at calendar day boundary (resets loss-limit counters; positions persist)
            ts_date = ts.date() if hasattr(ts, "date") else ts
            if current_date != ts_date:
                current_date = ts_date
                is_monday = ts.weekday() == 0 if hasattr(ts, "weekday") else False
                risk.reset_day(is_monday=is_monday)
                # CNC: pending entry signal carries to next morning's open — do not discard

            for state in symbol_states:
                candles = state._candles      # type: ignore[attr-defined]
                cursor = state._cursor        # type: ignore[attr-defined]
                if cursor >= len(candles):
                    continue
                if candles[cursor]["timestamp"] != ts:
                    continue
                candle = candles[cursor]
                state._cursor += 1            # type: ignore[attr-defined]
                _process_candle(state, candle, risk, shared, ch)

        # Force-close any positions still open at end
        for state in symbol_states:
            if state.open_trade is not None:
                candles = state._candles      # type: ignore[attr-defined]
                if not candles:
                    continue
                last_close = candles[-1]["close"]
                pnl, costs = _calc_pnl(state.open_trade, last_close)
                state.open_trade.exit_time = candles[-1]["timestamp"]
                state.open_trade.exit_price = last_close
                state.open_trade.pnl = pnl
                state.open_trade.costs = costs
                shared.equity += pnl
                shared.deployed_cash = max(
                    0.0, shared.deployed_cash
                    - state.open_trade.quantity * state.open_trade.entry_price
                )
                shared.equity_curve.append(shared.equity)
                shared.trades.append(state.open_trade)

        # Build per-symbol summaries
        for sym in report.symbols:
            sym_trades = [t for t in report.trades if t.instrument == sym]
            report.symbol_summaries[sym] = SymbolSummary(symbol=sym, trades=sym_trades)

        return report
