"""Run one campaign window (optionally with an overlay) and pickle its trade list for offline stratification.

    .venv/bin/python scripts/campaign/save_trades.py --window HORIZON --label baseline
"""
import argparse
import pickle
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.campaign.run_windows import WINDOWS, _apply_overlay  # noqa: E402

OUT = ROOT / "lab_data" / "campaign" / "trades"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--overlay", default=None)
    a = ap.parse_args()
    import logging
    logging.disable(logging.CRITICAL)
    _apply_overlay(a.overlay)
    from trader.backtest.engine import run_backtest
    from trader.core.config import config
    from trader.data.store import Store
    f, t = WINDOWS[a.window]
    wl = list(config.watchlist)
    ov = config._data.get("per_stock_params") or {}
    per = {s: config.get_strategy_params(s, "lr_extrema") for s in wl if ov.get(s, {}).get("lr_extrema")} or None
    trades = run_backtest(None, Store(config.db_path), wl, {**{s: 0 for s in wl}, "NSE:NIFTY 50": 256265, "NSE:INDIA VIX": 264969}, config.strategy_config("lr_extrema"),
                          datetime.strptime(f, "%Y-%m-%d"), datetime.strptime(t, "%Y-%m-%d").replace(hour=23, minute=59),
                          per_symbol_params=per)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{a.label}_{a.window}.pkl"
    path.write_bytes(pickle.dumps(trades))
    print(f"{len(trades)} trades → {path}")


if __name__ == "__main__":
    main()
