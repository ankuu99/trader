"""
FVM positional backtest engine (Phase 4) — separate from the intraday LRExtrema engine.

Weekly rebalance over a date range:
  1. mark open positions; update high-water tracking; apply the EXIT stack (full + trim)
  2. (regime-permitting) score the universe -> gate -> time -> rank -> size -> enter
  3. record equity

PIT-correct: fundamentals are read as-of the rebalance week (FVMStore PIT reads); technical
is computed from price up to that week only. Reuses costs.py. Sleeve sizing is risk-based off
the WIDE catastrophe stop (R4), with per-stock and per-sector caps.

Scoring / veto / regime are INJECTABLE (default to the real modules) so the simulation loop
is unit-testable without the full live dataset.
"""

import pandas as pd

from trader.costs import round_trip_cost
from trader.fvm import exits as exitmod
from trader.fvm import handoff
from trader.fvm import scoring as scoringmod
from trader.fvm import technical
from trader.fvm import vetoes as vetomod

RISK_PCT = 0.01          # risk per trade = 1% of sleeve capital
MAX_PER_STOCK = 0.20     # ≤20% of sleeve in one name
MAX_PER_SECTOR = 0.40    # ≤40% in one sector
MAX_POSITIONS = 12


class _Pos:
    __slots__ = ("symbol", "qty", "entry_price", "entry_date", "stop", "sector", "state")

    def __init__(self, symbol, qty, entry_price, entry_date, stop, sector):
        self.symbol, self.qty, self.entry_price = symbol, qty, entry_price
        self.entry_date, self.stop, self.sector = entry_date, stop, sector
        self.state = {"entry_price": entry_price, "peak_close": entry_price,
                      "weeks_since_new_high": 0, "trimmed": False}


def _slice_daily(df, wk):
    return df[pd.to_datetime(df["timestamp"]) <= wk]


def _last_close(df):
    return float(df["close"].iloc[-1]) if len(df) else None


def run_backtest(store, price_data: dict, sectors: dict, sleeve_capital: float,
                 rebalance_weeks=None, score_fn=None, veto_fn=None, regime_fn=None,
                 peg_fn=None, select_kwargs=None):
    """
    price_data : {symbol: daily OHLCV DataFrame}
    sectors    : {symbol: sector}
    score_fn(store, universe, asof) -> {sym: {"composite",...}}   (default scoring.compute_scores)
    veto_fn(store, sym, asof)       -> (passed, reasons)          (default vetoes.check_vetoes)
    regime_fn(asof)                 -> bool                       (default risk-on)
    peg_fn(sym, asof)               -> float|None                 (valuation-exhaustion exit input)
    Returns {"trades": [...], "equity_curve": [(date, equity)], "final_equity": float}.
    """
    score_fn = score_fn or scoringmod.compute_scores
    veto_fn = veto_fn or (lambda st, s, a: vetomod.check_vetoes(st, s, a))
    regime_fn = regime_fn or (lambda a: True)
    peg_fn = peg_fn or (lambda s, a: None)
    select_kwargs = select_kwargs or {}        # handoff gate thresholds (tunable/calibration)

    weekly = {s: technical.resample_weekly(df) for s, df in price_data.items()}
    if rebalance_weeks is None:
        allw = sorted(set().union(*[set(pd.to_datetime(w["timestamp"])) for w in weekly.values()]))
        rebalance_weeks = allw

    cash = float(sleeve_capital)
    positions: dict[str, _Pos] = {}
    trades, equity_curve = [], []

    def sector_exposure(sec, prices):
        return sum(p.qty * prices.get(p.symbol, p.entry_price)
                   for p in positions.values() if p.sector == sec)

    for wk in rebalance_weeks:
        daily_upto = {s: _slice_daily(df, wk) for s, df in price_data.items()}
        prices = {s: _last_close(d) for s, d in daily_upto.items() if len(d)}

        # 1. exits on open positions
        for sym in list(positions):
            pos = positions[sym]
            wdf = weekly[sym][pd.to_datetime(weekly[sym]["timestamp"]) <= wk]
            if len(wdf) == 0:
                continue
            exitmod.update_tracking(pos.state, float(wdf["close"].iloc[-1]))
            passed, _ = veto_fn(store, sym, wk.date().isoformat())
            action, reason = exitmod.decide_exit(wdf, pos.state, passed, peg_fn(sym, wk))
            px = prices.get(sym, pos.entry_price)
            if action == exitmod.EXIT:
                cost = round_trip_cost("CNC", pos.qty, pos.entry_price, px)
                cash += pos.qty * px
                trades.append({"symbol": sym, "entry": pos.entry_price, "exit": px,
                               "qty": pos.qty, "pnl": pos.qty * (px - pos.entry_price) - cost,
                               "cost": cost, "reason": reason,
                               "entry_date": pos.entry_date, "exit_date": wk.date().isoformat()})
                del positions[sym]
            elif action == exitmod.TRIM and not pos.state["trimmed"]:
                trim_qty = int(pos.qty * exitmod.TRIM_FRACTION)
                if trim_qty > 0:
                    cost = round_trip_cost("CNC", trim_qty, pos.entry_price, px)
                    cash += trim_qty * px
                    pos.qty -= trim_qty
                    pos.state["trimmed"] = True
                    trades.append({"symbol": sym, "entry": pos.entry_price, "exit": px,
                                   "qty": trim_qty, "pnl": trim_qty * (px - pos.entry_price) - cost,
                                   "cost": cost, "reason": "valuation_exhaustion_trim",
                                   "entry_date": pos.entry_date, "exit_date": wk.date().isoformat()})

        # 2. entries
        if regime_fn(wk) and len(positions) < MAX_POSITIONS:
            universe = [s for s, d in daily_upto.items() if len(d) >= 60]
            asof = wk.date().isoformat()
            scores = score_fn(store, universe, asof)
            vmap = {s: veto_fn(store, s, asof) for s in universe}
            tmap = {s: technical.evaluate(daily_upto[s]) for s in universe}
            cands, _ = handoff.select_candidates(scores, vmap, tmap, regime_ok=True, **select_kwargs)
            for c in cands:
                sym = c["symbol"]
                if sym in positions or len(positions) >= MAX_POSITIONS:
                    continue
                entry = prices.get(sym)
                stop = tmap[sym]["initial_stop"]
                if not entry or not stop or entry <= stop:
                    continue
                qty = int((RISK_PCT * sleeve_capital) / (entry - stop))
                qty = min(qty, int(MAX_PER_STOCK * sleeve_capital / entry), int(cash / entry))
                sec = sectors.get(sym, "Unknown")
                if qty <= 0 or sector_exposure(sec, prices) + qty * entry > MAX_PER_SECTOR * sleeve_capital:
                    continue
                cash -= qty * entry
                positions[sym] = _Pos(sym, qty, entry, asof, stop, sec)

        equity = cash + sum(p.qty * prices.get(p.symbol, p.entry_price) for p in positions.values())
        equity_curve.append((wk, equity))

    # close residual positions at the last price
    last = rebalance_weeks[-1]
    final_prices = {s: _last_close(_slice_daily(df, last)) for s, df in price_data.items()}
    for sym, pos in list(positions.items()):
        px = final_prices.get(sym, pos.entry_price)
        cost = round_trip_cost("CNC", pos.qty, pos.entry_price, px)
        cash += pos.qty * px
        trades.append({"symbol": sym, "entry": pos.entry_price, "exit": px, "qty": pos.qty,
                       "pnl": pos.qty * (px - pos.entry_price) - cost, "cost": cost,
                       "reason": "end", "entry_date": pos.entry_date,
                       "exit_date": last.date().isoformat()})

    return {"trades": trades, "equity_curve": equity_curve, "final_equity": cash}


def compute_metrics(trades, sleeve_capital):
    if not trades:
        return {"trades": 0, "total_pnl": 0.0, "return_pct": 0.0, "win_rate": 0.0}
    pnl = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    return {
        "trades": len(trades),
        "total_pnl": pnl,
        "return_pct": 100.0 * pnl / sleeve_capital,
        "win_rate": 100.0 * wins / len(trades),
    }
