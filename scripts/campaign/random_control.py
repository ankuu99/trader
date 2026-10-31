"""Coin-flip control (owner question 2026-10-18: "if we flip a coin and wait, do we still make money?").
Same watchlist, per-stock params, exits, risk, scale-in and capital as the baseline — but the model is replaced by
random draws: each strategy-TF bar "fires" an entry with the stock's own baseline firing rate (share of bars with
P(min) ≥ threshold, 2023–26 score cache) and a top signal with its own P(max) ≥ sell_threshold rate. No information,
same activity level. Deterministic per (seed, stock, bar timestamp). Research-only subclass; no production code.

    .venv/bin/python scripts/campaign/random_control.py --window FULL --seeds 1 2 3 4 5
"""
import argparse
import hashlib
import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.campaign.run_windows import WINDOWS  # noqa: E402

SCORES = ROOT / "lab_data/campaign/scores/baseline.pkl"


def baseline_rates() -> dict:
    run = pickle.loads(SCORES.read_bytes())
    out = {}
    for s, p in run["params"].items():
        rows = run["scores"].get(s) or []
        pmin = np.array([r["p_min"] for r in rows]); pmax = np.array([r["p_max"] for r in rows])
        out[s] = (float(((pmin >= p["threshold"]) & (pmax < p.get("veto_threshold", 1.0))).mean()),
                  float((pmax >= p["sell_threshold"]).mean()))
    return out


def _u(seed, sym, ts, k) -> float:
    h = hashlib.blake2b(f"{seed}|{sym}|{ts}|{k}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2 ** 64


def make_cls(seed: int, rates: dict, mode: str = "coin"):
    from trader.strategies.lr_extrema import LRExtremaStrategy

    class _CoinModel:
        def __init__(self, strat):
            self.s = strat; self.trained = False
        @property
        def is_trained(self):
            return self.trained
        def fit(self, X, y):
            self.trained = True
        def predict_proba(self, x):
            ts = self.s._candles[-1].get("timestamp") if self.s._candles else None
            re, rt = rates.get(self.s.instrument, (0.0, 0.0))
            p_min = 1.0 if _u(seed, self.s.instrument, ts, 0) < re else 0.0
            p_max = 0.9 if _u(seed, self.s.instrument, ts, 1) < rt else 0.0  # ≥ sell_threshold, < veto 1.0
            return p_min, p_max
        def feature_contributions(self, x, names=None):
            return None

    class _HybridModel:
        """Real model for one side, coin for the other (attribution of the edge)."""
        def __init__(self, strat, real):
            self.s, self.real, self.coin = strat, real, _CoinModel(strat)
        @property
        def is_trained(self):
            return self.real.is_trained
        def fit(self, X, y):
            self.real.fit(X, y)
        def predict_proba(self, x):
            rmin, rmax = self.real.predict_proba(x)
            cmin, cmax = self.coin.predict_proba(x)
            if mode == "model_entry":
                return rmin, cmax
            return cmin, max(rmax, 0.0) if rmax < 1.0 else 0.99  # model_top: keep real P(max) below veto 1.0
        def feature_contributions(self, x, names=None):
            return None

    class CoinFlipLR(LRExtremaStrategy):
        def __init__(self, instrument, params):
            super().__init__(instrument, params)
            self._model = _CoinModel(self) if mode == "coin" else _HybridModel(self, self._model)
        def _train(self):
            if mode == "coin":
                self._model.trained = True  # no fitting — the coin needs no training
            else:
                super()._train()

    return CoinFlipLR


def run_one(args):
    window, seed, mode = args
    import logging
    logging.disable(logging.CRITICAL)
    from trader.analytics import compute_utilisation
    from trader.backtest.engine import compute_metrics, run_backtest
    from trader.core.config import config
    from trader.data.store import Store
    f, t = WINDOWS[window]
    fd, td = datetime.strptime(f, "%Y-%m-%d"), datetime.strptime(t, "%Y-%m-%d").replace(hour=23, minute=59)
    wl = list(config.watchlist)
    ov = config._data.get("per_stock_params") or {}
    per = {s: config.get_strategy_params(s, "lr_extrema") for s in wl if ov.get(s, {}).get("lr_extrema")} or None
    trades = run_backtest(None, Store(config.db_path), wl, {s: 0 for s in wl}, config.strategy_config("lr_extrema"),
                          fd, td, per_symbol_params=per, strategy_cls=make_cls(seed, baseline_rates(), mode))
    m = compute_metrics(trades, config.total_capital)
    u = compute_utilisation(trades, config.total_capital, fd, td)["overall"]
    return {"window": window, "seed": seed, "mode": mode, "trades": m["total_trades"], "pnl": round(m["total_pnl"], 1),
            "max_dd_pct": round(m["max_drawdown_pct"], 2), "calmar": round(m["calmar_ratio"], 2),
            "weighted_win_pct": round(m["money_weighted_win_rate"], 1), "win_rate": round(m["win_rate"], 1),
            "util_pct": round(u.get("time_avg_util_pct", 0.0), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", nargs="+", default=["FULL", "HORIZON"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3, 4, 5])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--modes", nargs="+", default=["coin"], help="coin | model_entry | model_top")
    ap.add_argument("--out", default=str(ROOT / "reviews/extrema_campaign/runs/random_control.json"))
    a = ap.parse_args()
    jobs = [(w, s, m) for m in a.modes for w in a.windows for s in a.seeds]
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        res = list(ex.map(run_one, jobs))
    for r in res:
        print(r)
    Path(a.out).write_text(json.dumps({"run_at": datetime.now().isoformat(timespec="seconds"), "results": res}, indent=1))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
