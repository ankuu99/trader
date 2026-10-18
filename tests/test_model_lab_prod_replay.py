"""Production P(min)/P(max) replay (scripts/model_lab/prod_pmin.py)."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from research.model_lab import synth

_SPEC = importlib.util.spec_from_file_location(
    "prod_pmin", Path(__file__).resolve().parents[1] / "scripts" / "model_lab" / "prod_pmin.py")
prod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(prod)


def _params():
    from trader.core.config import config
    p = dict(config.strategy_config("lr_extrema"))
    p.update(warmup_bars=100, lookback_bars=300, retrain_every=25)
    return p


def test_prod_replay_matches_score_current():
    from trader.strategies.lr_extrema import LRExtremaStrategy
    b = synth.synthetic_15m(40, seed=7)
    p = _params()
    r1 = prod.replay_symbol(b, "NSE:SYN", p)
    r2 = prod.replay_symbol(b, "NSE:SYN", p)
    assert list(r1.columns) == ["timestamp", "score", "p_max"]
    pm = r1["score"].to_numpy()
    assert np.isnan(pm[:50]).all()                 # untrained early on
    assert np.isfinite(pm[-100:]).all()            # trained later
    assert np.array_equal(pm, r2["score"].to_numpy(), equal_nan=True)
    checks = [len(b) - 1, len(b) - 40, len(b) - 90]
    strat = LRExtremaStrategy("NSE:SYN", dict(p))
    for i, row in enumerate(b.itertuples()):
        strat.on_candle({"timestamp": row.timestamp.to_pydatetime(), "open": row.open, "high": row.high,
                         "low": row.low, "close": row.close, "volume": row.volume})
        if i in checks:
            s = strat.score_current()
            assert s is not None
            assert abs(s[0] - pm[i]) < 1e-6 and abs(s[1] - r1["p_max"].to_numpy()[i]) < 1e-6
