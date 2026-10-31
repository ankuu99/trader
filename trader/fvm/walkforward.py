"""
Milestone-A walk-forward harness (design §12b/§12c).

The validation gate: the rules-only FVM strategy must **beat a naive-momentum benchmark**
on the SAME universe + cost model, and be **profitable in the majority of walk-forward folds**
(consistency, not one lucky window), within a max-drawdown ceiling.

This module is pure orchestration over `engine.run_backtest` (FVM) and `naive_momentum_backtest`
(the benchmark). FVM is rules-only (nothing is fit), so "walk-forward" here means evaluating both
strategies over a sequence of rolling out-of-sample windows and checking that the edge is
consistent across them — not a train/test split.

Benchmark = "hold while in the top-N by 12–1 momentum": each rebalance, rank names by trailing
return (lookback minus a recent skip), hold the top N equal-weight, sell on exit from the set.
Same `round_trip_cost`, same sleeve capital, same weekly grid as FVM — apples to apples.
"""

import pandas as pd

from trader.costs import round_trip_cost
from trader.fvm import engine as enginemod
from trader.fvm import technical


# ------------------------------------------------------------------ #
# Naive-momentum benchmark                                            #
# ------------------------------------------------------------------ #

def _weekly_closes(price_data):
    """{symbol: weekly DataFrame[timestamp, close]} from daily OHLCV."""
    return {s: technical.resample_weekly(df) for s, df in price_data.items()}


def _trailing_return(wk_df, asof, lookback_w, skip_w):
    """12–1 style momentum: return from (lookback+skip) weeks ago to `skip` weeks ago."""
    w = wk_df[pd.to_datetime(wk_df["timestamp"]) <= asof]
    closes = w["close"].astype(float).tolist()
    need = lookback_w + skip_w + 1
    if len(closes) < need:
        return None
    recent = closes[-1 - skip_w]
    past = closes[-1 - skip_w - lookback_w]
    return (recent / past - 1.0) if past > 0 else None


def naive_momentum_backtest(price_data, sleeve_capital, rebalance_weeks,
                            lookback_w=52, skip_w=4, top_n=enginemod.MAX_POSITIONS,
                            rebal_every=4):
    """Top-N trailing-momentum portfolio; hold while in the set. Equity marked every week.

    rebal_every : trade only every Nth week (1 = weekly). Equity is still marked weekly.
    Returns the same shape as engine.run_backtest: {trades, equity_curve, final_equity}.
    """
    weekly = _weekly_closes(price_data)
    cash = float(sleeve_capital)
    holdings = {}            # symbol -> {"qty", "entry_price", "entry_date"}
    trades, equity_curve = [], []

    def price_asof(sym, wk):
        d = price_data[sym]
        d = d[pd.to_datetime(d["timestamp"]) <= wk]
        return float(d["close"].iloc[-1]) if len(d) else None

    for i, wk in enumerate(rebalance_weeks):
        prices = {s: price_asof(s, wk) for s in price_data}
        prices = {s: p for s, p in prices.items() if p}

        if i % rebal_every == 0:
            ranked = sorted(
                ((s, r) for s in price_data
                 if (r := _trailing_return(weekly[s], wk, lookback_w, skip_w)) is not None
                 and s in prices),
                key=lambda kv: kv[1], reverse=True)
            desired = {s for s, _ in ranked[:top_n]}

            # sell holds that fell out of the set
            for sym in list(holdings):
                if sym not in desired:
                    h = holdings.pop(sym)
                    px = prices.get(sym, h["entry_price"])
                    cost = round_trip_cost("CNC", h["qty"], h["entry_price"], px)
                    cash += h["qty"] * px
                    trades.append({"symbol": sym, "entry": h["entry_price"], "exit": px,
                                   "qty": h["qty"], "pnl": h["qty"] * (px - h["entry_price"]) - cost,
                                   "cost": cost, "reason": "momentum_exit",
                                   "entry_date": h["entry_date"],
                                   "exit_date": wk.date().isoformat()})

            # buy new names into the set, equal-weight on free cash across open slots
            new = [s for s in desired if s not in holdings]
            slots = top_n - len(holdings)
            if new and slots > 0:
                budget = cash / slots
                for sym in new[:slots]:
                    px = prices[sym]
                    qty = int(budget / px)
                    if qty > 0:
                        cash -= qty * px
                        holdings[sym] = {"qty": qty, "entry_price": px,
                                         "entry_date": wk.date().isoformat()}

        equity = cash + sum(h["qty"] * prices.get(s, h["entry_price"])
                            for s, h in holdings.items())
        equity_curve.append((wk, equity))

    # liquidate residual at the last week
    last = rebalance_weeks[-1]
    for sym, h in list(holdings.items()):
        px = price_asof(sym, last) or h["entry_price"]
        cost = round_trip_cost("CNC", h["qty"], h["entry_price"], px)
        cash += h["qty"] * px
        trades.append({"symbol": sym, "entry": h["entry_price"], "exit": px, "qty": h["qty"],
                       "pnl": h["qty"] * (px - h["entry_price"]) - cost, "cost": cost,
                       "reason": "end", "entry_date": h["entry_date"],
                       "exit_date": last.date().isoformat()})
    return {"trades": trades, "equity_curve": equity_curve, "final_equity": cash}


# ------------------------------------------------------------------ #
# Folds + metrics                                                     #
# ------------------------------------------------------------------ #

def all_weeks(price_data):
    """Sorted union of weekly rebalance timestamps across the universe."""
    weekly = _weekly_closes(price_data)
    return sorted(set().union(*[set(pd.to_datetime(w["timestamp"])) for w in weekly.values()]))


def first_scoreable_week(store, weeks, universe, veto_fn, min_names=5, probe_every=4):
    """Earliest week where >= min_names of the universe pass vetoes (i.e. have enough PIT
    fundamentals to be scoreable). Folds before this are vacuous (everything `insufficient_data`)
    and would make the gate an artifact of data depth, not strategy behaviour.

    Returns the index into `weeks`, or None if never reached. Probes every `probe_every` weeks.
    """
    for i in range(0, len(weeks), probe_every):
        asof = weeks[i].date().isoformat()
        n = sum(1 for s in universe if veto_fn(store, s, asof)[0])
        if n >= min_names:
            return i
    return None


def make_folds(weeks, test_len_w=78, step_w=39, warmup_w=52, start_idx=None):
    """Rolling out-of-sample windows over the weekly grid.

    warmup_w : weeks reserved at the front so momentum/MA history exists before the first fold.
    test_len_w / step_w : fold length and stride (defaults ≈ 18-month folds stepped 9 months).
    Returns [(label, [weeks...]), ...].
    """
    folds = []
    start = warmup_w if start_idx is None else max(warmup_w, start_idx)
    n = len(weeks)
    while start + test_len_w <= n:
        window = weeks[start:start + test_len_w]
        label = f"{window[0].date()}..{window[-1].date()}"
        folds.append((label, window))
        start += step_w
    return folds


def equity_drawdown_pct(equity_curve, sleeve_capital):
    """Max peak-to-trough decline on the equity curve, as % of sleeve capital."""
    peak = -float("inf")
    mdd = 0.0
    for _, eq in equity_curve:
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    return 100.0 * mdd / sleeve_capital if sleeve_capital else 0.0


def _fold_metrics(result, sleeve_capital):
    m = enginemod.compute_metrics(result["trades"], sleeve_capital)
    m["max_drawdown_pct"] = equity_drawdown_pct(result["equity_curve"], sleeve_capital)
    return m


def run_walk_forward(store, price_data, sectors, sleeve_capital, folds,
                     score_fn=None, veto_fn=None, regime_fn=None, peg_fn=None,
                     select_kwargs=None, benchmark_kwargs=None):
    """Run FVM and the naive-momentum benchmark over each fold. Returns per-fold + summary."""
    benchmark_kwargs = benchmark_kwargs or {}
    rows = []
    for label, window in folds:
        fvm = enginemod.run_backtest(
            store, price_data, sectors, sleeve_capital, rebalance_weeks=window,
            score_fn=score_fn, veto_fn=veto_fn, regime_fn=regime_fn, peg_fn=peg_fn,
            select_kwargs=select_kwargs)
        bench = naive_momentum_backtest(
            price_data, sleeve_capital, rebalance_weeks=window, **benchmark_kwargs)
        fm = _fold_metrics(fvm, sleeve_capital)
        bm = _fold_metrics(bench, sleeve_capital)
        rows.append({
            "fold": label,
            "fvm_return_pct": fm["return_pct"], "fvm_trades": fm["trades"],
            "fvm_win_rate": fm["win_rate"], "fvm_maxdd_pct": fm["max_drawdown_pct"],
            "bench_return_pct": bm["return_pct"], "bench_trades": bm["trades"],
            "edge_pct": fm["return_pct"] - bm["return_pct"],
            "fvm_beats_bench": fm["return_pct"] > bm["return_pct"],
            "fvm_profitable": fm["return_pct"] > 0,
        })
    return {"folds": rows, "summary": summarize(rows)}


def summarize(rows):
    n = len(rows)
    if n == 0:
        return {"folds": 0}
    beats = sum(r["fvm_beats_bench"] for r in rows)
    profit = sum(r["fvm_profitable"] for r in rows)
    return {
        "folds": n,
        "fvm_beats_bench": beats,
        "fvm_beats_bench_pct": 100.0 * beats / n,
        "fvm_profitable": profit,
        "fvm_profitable_pct": 100.0 * profit / n,
        "mean_edge_pct": sum(r["edge_pct"] for r in rows) / n,
        "mean_fvm_return_pct": sum(r["fvm_return_pct"] for r in rows) / n,
        "mean_bench_return_pct": sum(r["bench_return_pct"] for r in rows) / n,
        "worst_fvm_maxdd_pct": max(r["fvm_maxdd_pct"] for r in rows),
        # Milestone-A gate (§12c): beat the benchmark AND be profitable in the majority of folds.
        "gate_pass": beats > n / 2 and profit > n / 2,
    }
