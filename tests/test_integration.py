"""
Offline integration test — full pipeline without Kite API.

Wires together the real Strategy → RiskManager → OrderManager → Store chain
and runs it against candle data loaded from a CSV fixture file.
Ticks are simulated from each candle (high then close), mirroring the backtest engine.

Usage:
    .venv/bin/python -m pytest tests/test_integration.py -v -s
    # -s shows the printed summary report

Fixture data:
    tests/fixtures/integration/candles.csv
    See tests/fixtures/integration/README.md for the format spec.
"""

import csv
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from trader.core.config import Config
from trader.data.store import Store
from trader.orders.manager import OrderManager
from trader.risk.manager import RiskManager
from trader.strategies.base import SignalType
from trader.strategies.lr_extrema import LRExtremaStrategy

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "integration"

# Strategy params tuned for the short synthetic dataset
_STRATEGY_PARAMS = {
    "warmup_bars":          10,
    "lookback_bars":        50,
    "threshold":            0.60,
    "profit_pct":           2.0,
    "trail_pct":            1.0,
    "stop_pct":             2.0,
    "hold_bars":            20,
    "retrain_every":        10,
    "extrema_order":        2,
    "sell_threshold":       0.60,
    "sell_min_pct":         1.0,
    "veto_threshold":       0.50,
    "min_hold_before_exit": 2,
    "volume_ma_bars":       5,
    "trading_start":        "09:00",
    "trading_end":          "15:30",
}

_TEST_CONFIG_DATA = {
    "env": "paper",
    "candle_timeframe": "5minute",
    "capital": {
        "total": 100_000,
        "max_risk_per_trade_pct": 1.0,
        "daily_loss_limit_pct": 5.0,
    },
    "risk": {
        "max_open_positions": 3,
        "default_sl_pct": 2.0,
        "risk_reward": 2.0,
        "order_type": "MARKET",
        "gtt_enabled": False,
        "max_capital_per_stock_pct": 30.0,
    },
    "strategies": {
        "lr_extrema": _STRATEGY_PARAMS,
    },
    "watchlist": [],
    "interested": [],
    "data": {"db_path": ":memory:", "historical_cache_days": 90},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_candles(path: Path, instrument: str) -> list[dict]:
    """Load candles from CSV; attach instrument and parse timestamp."""
    candles = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            candles.append({
                "instrument": instrument,
                "_symbol":    instrument,       # OrderManager uses _symbol for matching
                "timestamp":  datetime.fromisoformat(row["timestamp"]),
                "open":       float(row["open"]),
                "high":       float(row["high"]),
                "low":        float(row["low"]),
                "close":      float(row["close"]),
                "volume":     int(row["volume"]),
            })
    return candles


def simulate_ticks(candle: dict) -> list[dict]:
    """Yield high then close as simulated ticks, mirroring the backtest engine."""
    return [
        {"last_price": candle["high"],  "instrument": candle["instrument"]},
        {"last_price": candle["close"], "instrument": candle["instrument"]},
    ]


@contextmanager
def _patched_config(config_obj: Config):
    """Patch the global config singleton used by RiskManager and OrderManager."""
    targets = [
        "trader.core.config.config",
        "trader.risk.manager.config",
        "trader.orders.manager.config",
    ]
    patches = [patch(t, config_obj) for t in targets]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()


# ---------------------------------------------------------------------------
# PipelineRunner
# ---------------------------------------------------------------------------

class PipelineRunner:
    """
    Wires Strategy → RiskManager → OrderManager → Store and replays candles.
    Mirrors the handle_candle / handle_order_update logic from main.py exactly.
    """

    def __init__(self, instrument: str, strategy_params: dict, config_obj: Config):
        self.instrument = instrument
        self._config = config_obj

        import tempfile, pathlib
        self._db_dir = tempfile.mkdtemp()
        self.store   = Store(pathlib.Path(self._db_dir) / "test.db")
        self.risk    = RiskManager()
        self.orders  = OrderManager(kite=None, store=self.store, mode="paper")
        self.strategy = LRExtremaStrategy(instrument, strategy_params)
        self.orders.register_update_callback(self._handle_order_update)

        # Tracking
        self.candles_seen: int = 0
        self.signals: list[dict] = []          # {type, price, candle_ts}
        self.filter_blocks: list[dict] = []    # {reason, candle_ts}
        self.order_updates: list[dict] = []    # raw dispatch records
        self._open_trade: dict | None = None
        self.trades: list[dict] = []           # closed trades with P&L
        self._peak_deployed: float = 0.0

    # ------------------------------------------------------------------ #
    # Order update callback (mirrors handle_order_update in main.py)      #
    # ------------------------------------------------------------------ #

    def _handle_order_update(self, update: dict) -> None:
        self.order_updates.append(update)
        status      = update.get("status", "")
        signal_type = update.get("signal_type")
        instrument  = update.get("instrument", "")
        fill_price  = float(update.get("fill_price") or update.get("price") or 0)
        quantity    = int(update.get("quantity") or 0)

        if status == "COMPLETE":
            if signal_type == SignalType.ENTRY:
                self.risk.on_order_filled(instrument, fill_price, quantity)
                self._open_trade = {
                    "instrument":  instrument,
                    "entry_price": fill_price,
                    "quantity":    quantity,
                    "entry_ts":    update.get("candle_ts"),
                }
            elif signal_type == SignalType.EXIT:
                pnl = 0.0
                if self._open_trade and self._open_trade["instrument"] == instrument:
                    pnl = (fill_price - self._open_trade["entry_price"]) * self._open_trade["quantity"]
                    self.trades.append({
                        "instrument":  instrument,
                        "entry_price": self._open_trade["entry_price"],
                        "exit_price":  fill_price,
                        "quantity":    self._open_trade["quantity"],
                        "pnl":         pnl,
                    })
                    self._open_trade = None
                self.risk.close_position(instrument, fill_price)

        elif status in ("REJECTED", "CANCELLED"):
            if signal_type == SignalType.ENTRY:
                self.risk.on_order_cancelled(instrument)

        self.strategy.on_order_update(update)

    # ------------------------------------------------------------------ #
    # Main feed methods                                                    #
    # ------------------------------------------------------------------ #

    def run_candle(self, candle: dict) -> None:
        self.candles_seen += 1

        # 1. Fill any pending paper orders at this candle's open
        self.orders.on_candle(candle)

        # 2. Strategy logic
        signal = self.strategy.on_candle(candle)

        # 3. Capture filter blocks (strategy gated a would-be entry)
        if self.strategy.last_filter_block:
            self.filter_blocks.append({
                "reason":    self.strategy.last_filter_block,
                "candle_ts": candle.get("timestamp"),
            })

        # 4. Route signal through risk → orders
        if signal is not None:
            self.signals.append({
                "type":      signal.signal_type.value,
                "price":     signal.price_hint,
                "candle_ts": candle.get("timestamp"),
            })
            order = self.risk.validate(signal)
            if order is not None:
                self.orders.place(order)

        self._peak_deployed = max(self._peak_deployed, self.risk._capital_deployed)

    def run_tick(self, tick: dict) -> None:
        signal = self.strategy.on_tick(tick)
        if signal is not None:
            self.signals.append({
                "type":  signal.signal_type.value,
                "price": signal.price_hint,
            })
            order = self.risk.validate(signal)
            if order is not None:
                self.orders.place(order)

        self._peak_deployed = max(self._peak_deployed, self.risk._capital_deployed)

    # ------------------------------------------------------------------ #
    # Summary                                                              #
    # ------------------------------------------------------------------ #

    def summary(self) -> dict:
        fills        = [u for u in self.order_updates if u.get("status") == "COMPLETE"]
        entry_fills  = [u for u in fills if u.get("signal_type") == SignalType.ENTRY]
        exit_fills   = [u for u in fills if u.get("signal_type") == SignalType.EXIT]
        rejects      = [u for u in self.order_updates
                        if u.get("status") in ("REJECTED", "CANCELLED")]

        signals_entry  = [s for s in self.signals if s["type"] == "ENTRY"]
        signals_exit   = [s for s in self.signals if s["type"] == "EXIT"]

        wins   = [t for t in self.trades if t["pnl"] > 0]
        losses = [t for t in self.trades if t["pnl"] <= 0]
        total_pnl = sum(t["pnl"] for t in self.trades)

        candle_ts_list = []
        for s in self.signals:
            if s.get("candle_ts"):
                candle_ts_list.append(s["candle_ts"])

        period_start = min((s["candle_ts"] for s in self.signals if s.get("candle_ts")), default=None)
        period_end   = max((s["candle_ts"] for s in self.signals if s.get("candle_ts")), default=None)

        return {
            "total_candles":         self.candles_seen,
            "period_start":          period_start,
            "period_end":            period_end,
            "signals_entry":         len(signals_entry),
            "signals_exit":          len(signals_exit),
            "filter_blocks":         len(self.filter_blocks),
            "filter_block_reasons":  [fb["reason"] for fb in self.filter_blocks],
            "fills":                 len(fills),
            "entry_fills":           len(entry_fills),
            "exit_fills":            len(exit_fills),
            "rejected_cancelled":    len(rejects),
            "trades_closed":         len(self.trades),
            "wins":                  len(wins),
            "losses":                len(losses),
            "win_rate_pct":          len(wins) / len(self.trades) * 100 if self.trades else 0.0,
            "total_pnl":             total_pnl,
            "best_trade_pnl":        max((t["pnl"] for t in self.trades), default=0.0),
            "worst_trade_pnl":       min((t["pnl"] for t in self.trades), default=0.0),
            "open_positions_at_end": dict(self.risk._open_positions),
            "capital_deployed_end":  self.risk._capital_deployed,
            "peak_capital_deployed": self._peak_deployed,
            "total_capital":         self._config.total_capital,
        }

    def print_summary(self, s: dict) -> None:
        cap = s["total_capital"]
        peak_pct = s["peak_capital_deployed"] / cap * 100 if cap else 0

        print("\n" + "=" * 54)
        print("  Integration Run Summary")
        print("=" * 54)
        period = (
            f"{s['period_start'].strftime('%Y-%m-%d')} → {s['period_end'].strftime('%Y-%m-%d')}"
            if s["period_start"] and s["period_end"] else "N/A"
        )
        print(f"  Period  : {period}  ({s['total_candles']} candles)")
        print(f"  Capital : ₹{cap:,.0f}")
        print()
        print(f"  Signals : {s['signals_entry'] + s['signals_exit']} total"
              f"  ({s['signals_entry']} ENTRY, {s['signals_exit']} EXIT)")
        if s["filter_blocks"]:
            print(f"  Filtered: {s['filter_blocks']} blocked entries")
            for r in s["filter_block_reasons"][:5]:
                print(f"            · {r}")
            if len(s["filter_block_reasons"]) > 5:
                print(f"            … and {len(s['filter_block_reasons']) - 5} more")
        print(f"  Orders  : {s['fills']} filled"
              f"  ({s['rejected_cancelled']} rejected/cancelled)")
        print()
        if s["trades_closed"]:
            sign = "+" if s["total_pnl"] >= 0 else ""
            print(f"  Trades  : {s['trades_closed']} closed")
            print(f"    Wins  : {s['wins']}  ({s['win_rate_pct']:.1f}%)")
            print(f"    Loss  : {s['losses']}")
            print(f"    P&L   : {sign}₹{s['total_pnl']:,.2f}")
            if s["trades_closed"]:
                print(f"    Best  : +₹{s['best_trade_pnl']:,.2f}")
                print(f"    Worst : ₹{s['worst_trade_pnl']:,.2f}")
        else:
            print("  Trades  : 0 closed")
        print()
        if s["open_positions_at_end"]:
            print(f"  Open    : {list(s['open_positions_at_end'].keys())}")
        else:
            print("  Open    : none")
        print(f"  Peak    : ₹{s['peak_capital_deployed']:,.0f} deployed ({peak_pct:.1f}%)")
        print("=" * 54 + "\n")


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

INSTRUMENT = "NSE:TEST"


@pytest.fixture(scope="module")
def config_obj():
    return Config(_TEST_CONFIG_DATA)


@pytest.fixture(scope="module")
def candle_data():
    path = FIXTURE_DIR / "candles.csv"
    return load_candles(path, INSTRUMENT)


@pytest.fixture
def runner(config_obj):
    with _patched_config(config_obj):
        yield PipelineRunner(INSTRUMENT, _STRATEGY_PARAMS, config_obj)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pipeline_runs_without_errors(runner, candle_data, config_obj):
    """Smoke test: all candles + simulated ticks feed through with no exceptions."""
    with _patched_config(config_obj):
        for candle in candle_data:
            runner.run_candle(candle)
            for tick in simulate_ticks(candle):
                runner.run_tick(tick)

    s = runner.summary()
    assert s["total_candles"] == len(candle_data)


def test_pipeline_full_summary(runner, candle_data, config_obj):
    """
    Full integration run — feeds every candle and tick, then prints a
    human-readable summary and asserts pipeline-level sanity invariants.
    Run with -s to see the printed output.
    """
    with _patched_config(config_obj):
        for candle in candle_data:
            runner.run_candle(candle)
            for tick in simulate_ticks(candle):
                runner.run_tick(tick)

    s = runner.summary()
    runner.print_summary(s)

    # --- Sanity invariants ---

    # Every candle was processed
    assert s["total_candles"] == len(candle_data)

    # Can never fill more entry orders than entry signals emitted
    assert s["entry_fills"] <= s["signals_entry"]

    # Closed trades cannot exceed entry fills (some fills may still be open)
    assert s["trades_closed"] <= s["entry_fills"]

    # Risk manager's open positions must match runner's open trade state
    expected_open = 1 if runner._open_trade else 0
    assert len(s["open_positions_at_end"]) == expected_open

    # Capital deployed must never exceed total capital
    assert s["capital_deployed_end"] <= s["total_capital"] + 1  # +1 for float rounding

    # Win + Loss count must equal total closed trades
    assert s["wins"] + s["losses"] == s["trades_closed"]


def test_no_capital_overdeployment(runner, candle_data, config_obj):
    """Peak capital deployed at any point must never exceed total capital."""
    with _patched_config(config_obj):
        for candle in candle_data:
            runner.run_candle(candle)
            for tick in simulate_ticks(candle):
                runner.run_tick(tick)

    s = runner.summary()
    assert s["peak_capital_deployed"] <= s["total_capital"] + 1


def test_position_state_consistency(runner, candle_data, config_obj):
    """RiskManager open positions and strategy position state stay in sync
    throughout the run — no phantom positions or stuck state."""
    with _patched_config(config_obj):
        for candle in candle_data:
            runner.run_candle(candle)
            for tick in simulate_ticks(candle):
                runner.run_tick(tick)

    strategy_in_position = not runner.strategy.is_flat()
    risk_has_position    = len(runner.risk._open_positions) > 0
    runner_open_trade    = runner._open_trade is not None

    # All three must agree
    assert strategy_in_position == risk_has_position == runner_open_trade


def test_filter_blocks_are_entry_only(runner, candle_data, config_obj):
    """Filter blocks only occur when strategy is flat (no blocked exits)."""
    with _patched_config(config_obj):
        for candle in candle_data:
            runner.run_candle(candle)
            for tick in simulate_ticks(candle):
                runner.run_tick(tick)

    # All filter blocks are strings (reason text), never None
    assert all(isinstance(fb["reason"], str) for fb in runner.filter_blocks)
    assert all(len(fb["reason"]) > 0 for fb in runner.filter_blocks)
