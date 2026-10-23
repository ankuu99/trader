"""Walk-forward harness: naive-momentum benchmark, fold generation, summary gate."""

import pandas as pd

from trader.fvm import walkforward as wf


def _daily(closes, start="2018-01-01"):
    ts = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"timestamp": ts, "open": closes,
                         "high": [c * 1.005 for c in closes],
                         "low": [c * 0.995 for c in closes],
                         "close": closes, "volume": [10_000.0] * len(closes)})


def test_naive_momentum_picks_the_riser():
    # one steady riser, one flat, one decliner — momentum should hold the riser and profit.
    n = 600
    riser = _daily([100 * (1.0015) ** i for i in range(n)])
    flat = _daily([100.0] * n)
    faller = _daily([100 * (0.999) ** i for i in range(n)])
    price_data = {"UP": riser, "FLAT": flat, "DOWN": faller}

    weeks = wf.all_weeks(price_data)
    window = weeks[60:]                       # leave history for the 52w lookback
    res = wf.naive_momentum_backtest(price_data, 1_000_000, window,
                                     lookback_w=52, skip_w=4, top_n=1, rebal_every=4)
    held = {t["symbol"] for t in res["trades"]}
    assert "UP" in held                        # the riser was bought
    assert res["final_equity"] > 1_000_000     # momentum made money on a clean trend
    # equity is marked every week, not just on trade weeks
    assert len(res["equity_curve"]) == len(window)


def test_make_folds_rolls_out_of_sample():
    weeks = pd.to_datetime(pd.bdate_range("2018-01-05", periods=400, freq="W-FRI")).tolist()
    folds = wf.make_folds(weeks, test_len_w=78, step_w=39, warmup_w=52)
    assert len(folds) >= 2
    # each fold is the right length and they advance by the stride
    assert all(len(w) == 78 for _, w in folds)
    assert folds[1][1][0] > folds[0][1][0]
    # warmup is respected — first fold starts at/after the warmup index
    assert folds[0][1][0] == weeks[52]


def test_summarize_gate_majority():
    rows = [
        {"fvm_beats_bench": True, "fvm_profitable": True, "edge_pct": 5.0,
         "fvm_return_pct": 10.0, "bench_return_pct": 5.0, "fvm_maxdd_pct": 8.0},
        {"fvm_beats_bench": True, "fvm_profitable": True, "edge_pct": 3.0,
         "fvm_return_pct": 7.0, "bench_return_pct": 4.0, "fvm_maxdd_pct": 12.0},
        {"fvm_beats_bench": False, "fvm_profitable": False, "edge_pct": -2.0,
         "fvm_return_pct": -1.0, "bench_return_pct": 1.0, "fvm_maxdd_pct": 15.0},
    ]
    s = wf.summarize(rows)
    assert s["folds"] == 3
    assert s["fvm_beats_bench"] == 2 and s["fvm_profitable"] == 2
    assert s["gate_pass"] is True               # majority beat + majority profitable
    assert s["worst_fvm_maxdd_pct"] == 15.0
    assert abs(s["mean_edge_pct"] - 2.0) < 1e-9


def test_summarize_gate_fails_on_minority():
    rows = [
        {"fvm_beats_bench": False, "fvm_profitable": False, "edge_pct": -3.0,
         "fvm_return_pct": -2.0, "bench_return_pct": 1.0, "fvm_maxdd_pct": 20.0},
        {"fvm_beats_bench": True, "fvm_profitable": True, "edge_pct": 1.0,
         "fvm_return_pct": 3.0, "bench_return_pct": 2.0, "fvm_maxdd_pct": 10.0},
    ]
    s = wf.summarize(rows)
    assert s["gate_pass"] is False              # tie is not a majority
