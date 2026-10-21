"""A/B: scale-in add-on pool size (budget_pct). Usage: run.py OUT.json [--quick]"""
import json, logging, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
REPO = "/Users/abhisheksingh/Projects/trader-2"
sys.path.insert(0, REPO)

WINDOWS = [("2020-01→2026-10", "2020-01-01", "2026-10-17")] + \
    [(str(y), f"{y}-01-01", f"{y}-12-31") for y in range(2020, 2026)] + [("2026 YTD", "2026-01-01", "2026-10-17")]
BUDGETS = [10, 20, 40, 1000]

def peak_deployed(trades, addon_only=False):
    ev = []
    for t in trades:
        if addon_only and not t.get("addon_tier"):
            continue
        n = t["entry"] * t["qty"]
        ev.append((str(t["entry_date"]), 1, n)); ev.append((str(t["exit_date"]), 0, -n))
    cur = peak = 0.0
    for _, _, d in sorted(ev):   # exits (0) before entries (1) on the same timestamp
        cur += d; peak = max(peak, cur)
    return peak

def job(label, frm, to, budget):
    logging.disable(logging.CRITICAL)
    import os; os.chdir(REPO)
    from trader.core.config import config
    from trader.data.store import Store
    from trader.backtest.engine import run_backtest, compute_metrics
    config._data["scale_in"]["budget_pct"] = budget
    store = Store(config.db_path)
    wl = list(config.watchlist)
    params = config.strategy_config("lr_extrema")
    ov = config._data.get("per_stock_params") or {}
    psp = {s: config.get_strategy_params(s, "lr_extrema") for s in wl if ov.get(s, {}).get("lr_extrema")} or None
    t0 = time.time()
    tr = run_backtest(None, store, wl, {s: 0 for s in wl}, params,
                      datetime.strptime(frm, "%Y-%m-%d"),
                      datetime.strptime(to, "%Y-%m-%d").replace(hour=23, minute=59), per_symbol_params=psp)
    m = compute_metrics(tr, config.total_capital)
    return dict(window=label, budget=budget, secs=round(time.time() - t0), trades=m["total_trades"],
                addon_trades=sum(1 for t in tr if t.get("addon_tier")),
                addon_pnl=sum(t["pnl"] for t in tr if t.get("addon_tier")),
                pnl=m["total_pnl"], dd=m["max_drawdown"], dd_pct=m["max_drawdown_pct"], calmar=m["calmar_ratio"],
                mwwr=m["money_weighted_win_rate"], pf=m["profit_factor"],
                peak_all=peak_deployed(tr), peak_addon=peak_deployed(tr, True), capital=config.total_capital)

if __name__ == "__main__":
    out = sys.argv[1]
    jobs = [("2026 YTD", "2026-01-01", "2026-10-17", 10)] if "--quick" in sys.argv else \
        [(w, f, t, b) for (w, f, t) in WINDOWS for b in BUDGETS]
    res = []
    with ProcessPoolExecutor(max_workers=int(sys.argv[sys.argv.index("--workers")+1]) if "--workers" in sys.argv else 4) as ex:
        futs = {ex.submit(job, *j): j for j in jobs}
        for f in as_completed(futs):
            try: r = f.result()
            except Exception as e: r = dict(window=futs[f][0], budget=futs[f][3], error=repr(e))
            res.append(r); print(json.dumps(r), flush=True)
            json.dump(res, open(out, "w"), indent=1)
