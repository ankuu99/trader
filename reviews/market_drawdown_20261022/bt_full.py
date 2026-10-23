import logging, sys, os, pickle
from datetime import datetime
REPO = "/Users/abhisheksingh/Projects/trader-2"; sys.path.insert(0, REPO); os.chdir(REPO)
logging.disable(logging.CRITICAL)
from trader.core.config import config
from trader.data.store import Store
from trader.backtest.engine import run_backtest, compute_metrics
store = Store(config.db_path)
wl = list(config.watchlist)
params = config.strategy_config("lr_extrema")
ov = config._data.get("per_stock_params") or {}
psp = {s: config.get_strategy_params(s, "lr_extrema") for s in wl if ov.get(s, {}).get("lr_extrema")} or None
tr = run_backtest(None, store, wl, {s: 0 for s in wl}, params, datetime(2020,1,1), datetime(2026,10,23,23,59), per_symbol_params=psp)
m = compute_metrics(tr, config.total_capital)
print(len(tr), round(m["total_pnl"]), round(m["max_drawdown"]), m["max_drawdown_pct"], config.total_capital, len(wl))
pickle.dump(tr, open(sys.argv[1], "wb"))
