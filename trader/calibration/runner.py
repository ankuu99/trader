"""
Calibration runner — searches for optimal strategy parameters via backtest.

Usage
-----
    from trader.calibration.runner import CalibrationRunner, print_ranked_table, print_best_params

    runner = CalibrationRunner(
        strategy_name="rsi",
        symbols=["NSE:INDHOTEL", "NSE:MARKSANS"],
        from_dt=datetime(2026, 3, 1),
        to_dt=datetime(2026, 4, 10),
        timeframe="5minute",
        capital=200000.0,
        store=Store(config.db_path),
    )
    results = runner.run(iterations=20, metric="sharpe", mode="random")
    print_ranked_table(results, metric="sharpe")
    print_best_params(results[0], "rsi", symbols)
"""

import itertools
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

import yaml

from trader.backtest.engine import Backtest, BacktestReport
from trader.calibration.param_space import (
    GROUP_COMPOSITIONS,
    PARAM_SPACES,
    ALL_STRATEGIES,
)
from trader.data.store import Store
from trader.strategies.base import Strategy
from trader.strategies.bollinger import BollingerBandStrategy
from trader.strategies.ema_pullback import EMAPullbackStrategy
from trader.strategies.group import StrategyGroup
from trader.strategies.orb import ORBStrategy
from trader.strategies.rsi import RSIStrategy
from trader.strategies.supertrend import SupertrendStrategy
from trader.strategies.vwap import VWAPReversionStrategy

STRATEGY_CLASSES: dict[str, type[Strategy]] = {
    "rsi":          RSIStrategy,
    "orb":          ORBStrategy,
    "vwap":         VWAPReversionStrategy,
    "supertrend":   SupertrendStrategy,
    "bollinger":    BollingerBandStrategy,
    "ema_pullback": EMAPullbackStrategy,
}


# ------------------------------------------------------------------ #
# Result dataclass                                                     #
# ------------------------------------------------------------------ #

@dataclass
class CalibrationResult:
    params: dict
    metric_value: float             # aggregated score (mean across symbols)
    per_symbol_metrics: dict[str, float] = field(default_factory=dict)
    per_symbol_trades: dict[str, int]   = field(default_factory=dict)
    per_symbol_pnl: dict[str, float]    = field(default_factory=dict)
    avg_sharpe: float = 0.0
    avg_total_pnl: float = 0.0
    avg_win_rate: float = 0.0
    avg_max_drawdown: float = 0.0
    avg_trades: float = 0.0


# ------------------------------------------------------------------ #
# ParameterSampler                                                     #
# ------------------------------------------------------------------ #

class ParameterSampler:
    """Generates parameter combinations for a strategy or group."""

    def __init__(self, strategy_name: str):
        if strategy_name not in ALL_STRATEGIES:
            raise ValueError(
                f"Unknown strategy '{strategy_name}'. "
                f"Valid options: {sorted(ALL_STRATEGIES)}"
            )
        self._name = strategy_name
        self._is_group = strategy_name in GROUP_COMPOSITIONS
        self._flat_space = self._build_flat_space()

    def _build_flat_space(self) -> dict[str, list]:
        if not self._is_group:
            return dict(PARAM_SPACES[self._name])

        primary_name, filter_names = GROUP_COMPOSITIONS[self._name]
        merged: dict[str, list] = {}
        primary_space = PARAM_SPACES[primary_name]
        all_filter_keys: set[str] = set()
        for fn in filter_names:
            all_filter_keys |= set(PARAM_SPACES[fn])

        for k, v in primary_space.items():
            # If a key collides between primary and any filter, prefix it
            key = f"{primary_name}__{k}" if k in all_filter_keys else k
            merged[key] = v

        for fn in filter_names:
            for k, v in PARAM_SPACES[fn].items():
                key = f"{fn}__{k}" if k in primary_space else k
                merged[key] = v

        return merged

    @property
    def flat_space(self) -> dict[str, list]:
        return self._flat_space

    @property
    def total_combinations(self) -> int:
        result = 1
        for values in self._flat_space.values():
            result *= len(values)
        return result

    def _is_valid(self, combo: dict) -> bool:
        """Filter out parameter combinations that are logically invalid."""
        # ema_pullback: fast must be strictly less than slow
        fast = combo.get("fast")
        slow = combo.get("slow")
        if fast is not None and slow is not None and fast >= slow:
            return False
        return True

    def grid(self) -> Iterator[dict]:
        """Yield all valid parameter combinations (cartesian product)."""
        keys = list(self._flat_space.keys())
        for values in itertools.product(*self._flat_space.values()):
            combo = dict(zip(keys, values))
            if self._is_valid(combo):
                yield combo

    def random_sample(self, n: int, seed: int | None = None) -> list[dict]:
        """
        Return up to n unique valid parameter combinations chosen at random.
        Falls back to all valid combos if n exceeds what is available.
        """
        rng = random.Random(seed)
        all_combos = list(self.grid())
        rng.shuffle(all_combos)
        return all_combos[:n]


# ------------------------------------------------------------------ #
# CalibrationRunner                                                    #
# ------------------------------------------------------------------ #

class CalibrationRunner:
    def __init__(
        self,
        strategy_name: str,
        symbols: list[str],
        from_dt: datetime,
        to_dt: datetime,
        timeframe: str,
        capital: float,
        store: Store,
    ):
        self._strategy_name = strategy_name
        self._symbols = symbols
        self._from_dt = from_dt
        self._to_dt = to_dt
        self._timeframe = timeframe
        self._capital = capital
        self._store = store
        self._sampler = ParameterSampler(strategy_name)
        self._is_group = strategy_name in GROUP_COMPOSITIONS

    def run(
        self,
        iterations: int,
        metric: str,
        mode: str = "random",
        seed: int | None = None,
    ) -> list[CalibrationResult]:
        """
        Run calibration. Returns results sorted best→worst by metric.
        Prints progress to stdout as iterations complete.
        """
        _validate_metric(metric)

        if mode == "grid":
            combos = list(self._sampler.grid())
            print(f"  Mode: grid | Total combinations: {len(combos)}")
        else:
            combos = self._sampler.random_sample(iterations, seed=seed)
            print(
                f"  Mode: random | Sampling {len(combos)} of "
                f"{self._sampler.total_combinations} combinations"
            )

        results: list[CalibrationResult] = []
        total = len(combos)

        for i, params in enumerate(combos, 1):
            result = self._run_single(params, metric)
            results.append(result)

            param_str = "  ".join(f"{k}={v}" for k, v in params.items())
            metric_display = _display_metric(metric, result.metric_value)
            print(f"  [{i:3d}/{total}]  {param_str}  →  {metric}={metric_display}")

        results.sort(key=lambda r: r.metric_value, reverse=True)
        return results

    def _run_single(self, params: dict, metric: str) -> CalibrationResult:
        per_symbol_metrics: dict[str, float] = {}
        per_symbol_trades: dict[str, int] = {}
        per_symbol_pnl: dict[str, float] = {}
        sharpes: list[float] = []
        pnls: list[float] = []
        win_rates: list[float] = []
        drawdowns: list[float] = []
        trades_list: list[int] = []

        for symbol in self._symbols:
            strategy = self._build_strategy(symbol, params)
            bt = Backtest(
                self._store, strategy,
                capital=self._capital,
                reset_daily=True,
            )
            report = bt.run(symbol, self._timeframe, self._from_dt, self._to_dt)

            m = self._extract_metric(report, metric)
            per_symbol_metrics[symbol] = m
            per_symbol_trades[symbol] = report.total_trades()
            per_symbol_pnl[symbol] = report.total_pnl()

            sharpes.append(report.sharpe_ratio())
            pnls.append(report.total_pnl())
            win_rates.append(report.win_rate())
            drawdowns.append(report.max_drawdown())
            trades_list.append(report.total_trades())

        agg = sum(per_symbol_metrics.values()) / len(per_symbol_metrics)

        return CalibrationResult(
            params=params,
            metric_value=agg,
            per_symbol_metrics=per_symbol_metrics,
            per_symbol_trades=per_symbol_trades,
            per_symbol_pnl=per_symbol_pnl,
            avg_sharpe=_mean(sharpes),
            avg_total_pnl=_mean(pnls),
            avg_win_rate=_mean(win_rates),
            avg_max_drawdown=_mean(drawdowns),
            avg_trades=_mean([float(t) for t in trades_list]),
        )

    def _build_strategy(self, symbol: str, params: dict) -> Strategy:
        if not self._is_group:
            return STRATEGY_CLASSES[self._strategy_name](symbol, params)

        primary_name, filter_names = GROUP_COMPOSITIONS[self._strategy_name]
        primary_space_keys = set(PARAM_SPACES[primary_name])
        filter_space_keys = {fn: set(PARAM_SPACES[fn]) for fn in filter_names}

        # Reverse the name-collision prefixing done by ParameterSampler
        all_filter_keys: set[str] = set()
        for fn in filter_names:
            all_filter_keys |= filter_space_keys[fn]

        primary_params: dict = {}
        filter_params: dict[str, dict] = {fn: {} for fn in filter_names}

        for k, v in params.items():
            # Un-prefix primary keys
            if k.startswith(f"{primary_name}__"):
                primary_params[k[len(primary_name) + 2:]] = v
            elif k in primary_space_keys:
                primary_params[k] = v
            else:
                # Assign to the correct filter
                for fn in filter_names:
                    raw_key = k[len(fn) + 2:] if k.startswith(f"{fn}__") else k
                    if raw_key in filter_space_keys[fn]:
                        filter_params[fn][raw_key] = v
                        break

        filters = [
            STRATEGY_CLASSES[fn](symbol, filter_params[fn])
            for fn in filter_names
        ]
        primary = STRATEGY_CLASSES[primary_name](symbol, primary_params)
        return StrategyGroup(primary=primary, filters=filters)

    def _extract_metric(self, report: BacktestReport, metric: str) -> float:
        if metric == "sharpe":
            return report.sharpe_ratio()
        if metric == "total_pnl":
            return report.total_pnl()
        if metric == "win_rate":
            return report.win_rate()
        if metric == "max_drawdown":
            # Negate so that sort descending = smallest drawdown first
            return -report.max_drawdown()
        raise ValueError(f"Unknown metric: {metric}")


# ------------------------------------------------------------------ #
# Display helpers                                                      #
# ------------------------------------------------------------------ #

def print_ranked_table(
    results: list[CalibrationResult],
    strategy_name: str,
    metric: str,
    top_n: int = 10,
) -> None:
    top = results[:top_n]
    if not top:
        print("  No results to display.")
        return

    # Collect all param keys across results (in order of first occurrence)
    param_keys = list(top[0].params.keys())

    header_metric = metric if metric != "max_drawdown" else "drawdown"

    print(f"\n{'=' * 90}")
    print(f"  TOP {min(top_n, len(top))} RESULTS — {strategy_name.upper()} | ranked by: {metric}")
    print(f"{'=' * 90}")

    # Build column widths
    col_widths = {k: max(len(k), 6) for k in param_keys}
    for r in top:
        for k, v in r.params.items():
            col_widths[k] = max(col_widths[k], len(str(v)))

    param_header = "  ".join(f"{k:>{col_widths[k]}}" for k in param_keys)
    print(f"  {'Rank':>4}  {param_header}  |  {'sharpe':>7}  {'pnl':>10}  "
          f"{'win%':>6}  {'drawdown':>8}  {'trades':>6}")
    print(f"  {'-' * 4}  {'-' * (sum(col_widths.values()) + 2 * (len(param_keys) - 1))}  "
          f"|  {'-' * 7}  {'-' * 10}  {'-' * 6}  {'-' * 8}  {'-' * 6}")

    for rank, r in enumerate(top, 1):
        param_str = "  ".join(f"{str(r.params[k]):>{col_widths[k]}}" for k in param_keys)
        dd = r.avg_max_drawdown * 100
        mark = " *" if rank == 1 else "  "
        print(
            f"{mark}{rank:>4}  {param_str}  |  "
            f"{r.avg_sharpe:>7.2f}  "
            f"₹{r.avg_total_pnl:>9,.0f}  "
            f"{r.avg_win_rate:>6.1%}  "
            f"{dd:>7.1f}%  "
            f"{r.avg_trades:>6.0f}"
        )

    print(f"{'=' * 90}")
    print("  * = best result  |  metrics are means across all symbols")
    print(f"  max_drawdown shown as positive % (lower is better)\n")


def print_best_params(
    result: CalibrationResult,
    strategy_name: str,
    symbols: list[str],
    metric: str,
) -> None:
    print(f"\n{'=' * 60}")
    print(f"  BEST PARAMS — {strategy_name.upper()}")
    print(f"{'=' * 60}")
    for k, v in result.params.items():
        print(f"  {k:<20}: {v}")
    print(f"  {'---'}")
    print(f"  {'sharpe':<20}: {result.avg_sharpe:.2f}")
    print(f"  {'total_pnl':<20}: ₹{result.avg_total_pnl:,.0f}  (mean across symbols)")
    print(f"  {'win_rate':<20}: {result.avg_win_rate:.1%}")
    print(f"  {'max_drawdown':<20}: {result.avg_max_drawdown:.1%}")
    print(f"  {'trades':<20}: {result.avg_trades:.0f}  (mean)")
    print(f"  {'---'}")
    print("  Per-symbol breakdown:")
    for sym in symbols:
        m = result.per_symbol_metrics.get(sym, 0.0)
        pnl = result.per_symbol_pnl.get(sym, 0.0)
        trades = result.per_symbol_trades.get(sym, 0)
        metric_display = _display_metric(metric, m)
        print(f"    {sym:<25}  {metric}={metric_display}  pnl=₹{pnl:,.0f}  trades={trades}")
    print(f"{'=' * 60}\n")


def write_best_params(
    strategy_name: str,
    best_params: dict,
    config_path: Path,
) -> None:
    """
    Write best params back to config.yaml.
    Uses PyYAML round-trip — YAML comments will be lost on rewrite.
    """
    with open(config_path) as f:
        data = yaml.safe_load(f)

    if strategy_name in PARAM_SPACES:
        existing = data["strategies"].setdefault(strategy_name, {})
        existing.update(best_params)
    elif strategy_name in GROUP_COMPOSITIONS:
        primary_name, filter_names = GROUP_COMPOSITIONS[strategy_name]
        primary_keys = set(PARAM_SPACES[primary_name])
        filter_keys = {fn: set(PARAM_SPACES[fn]) for fn in filter_names}
        all_filter_keys: set[str] = set()
        for fn in filter_names:
            all_filter_keys |= filter_keys[fn]

        for k, v in best_params.items():
            if k.startswith(f"{primary_name}__"):
                raw = k[len(primary_name) + 2:]
                data["strategies"].setdefault(primary_name, {})[raw] = v
            elif k in primary_keys:
                data["strategies"].setdefault(primary_name, {})[k] = v
            else:
                for fn in filter_names:
                    raw = k[len(fn) + 2:] if k.startswith(f"{fn}__") else k
                    if raw in filter_keys[fn]:
                        data["strategies"].setdefault(fn, {})[raw] = v
                        break

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"  config updated → {config_path}")


# ------------------------------------------------------------------ #
# Internal utilities                                                   #
# ------------------------------------------------------------------ #

def _validate_metric(metric: str) -> None:
    valid = {"sharpe", "total_pnl", "win_rate", "max_drawdown"}
    if metric not in valid:
        raise ValueError(f"Unknown metric '{metric}'. Choose from: {sorted(valid)}")


def _display_metric(metric: str, value: float) -> str:
    if metric == "max_drawdown":
        # Un-negate the internal negation
        return f"{-value:.1%}"
    if metric == "total_pnl":
        return f"₹{value:,.0f}"
    if metric == "win_rate":
        return f"{value:.1%}"
    return f"{value:.2f}"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
