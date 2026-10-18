"""Model Lab S0 portfolio simulator (synthetic only; lab dirs redirected to tmp)."""
import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.model_lab import bars as bars_mod
from research.model_lab import paths, portfolio, references, synth, targets
from trader.costs import round_trip_cost

DAYS = pd.bdate_range("2021-03-01", periods=7).values.astype("datetime64[ns]")


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(paths, "PORTFOLIOS_DIR", tmp_path / "portfolios")
    monkeypatch.setattr(paths, "REFS_DIR", tmp_path / "refs")
    monkeypatch.setattr(portfolio, "REPORT_DIR", tmp_path / "reports")
    store = {}
    monkeypatch.setattr(bars_mod, "load", lambda sym, tf, start=None, end=None: store[(sym, tf)])

    class Lab:
        bars = store

        @staticmethod
        def make(run_id, tf, bars, scores, extra=None):
            """bars: {sym: DataFrame}; scores: {sym: array aligned to bars (NaN = no score row)}."""
            d = paths.RUNS_DIR / run_id
            (d / "scores").mkdir(parents=True)
            (d / "meta.json").write_text(json.dumps({"tf": tf, "symbols": sorted(bars)}))
            for s, df in bars.items():
                store[(s, tf)] = df
                sc = np.asarray(scores[s], float)
                m = np.isfinite(sc)
                out = pd.DataFrame({"timestamp": df["timestamp"].values[m], "fold_id": np.zeros(m.sum(), np.int32),
                                    "score": sc[m].astype(np.float32)})
                for k, v in (extra or {}).get(s, {}).items():
                    out[k] = np.asarray(v, np.float32)[m]
                out.to_parquet(d / "scores" / f"{paths.sym_file(s)}.parquet", index=False)
    return Lab


def _bars(rows, ts=DAYS):
    a = np.array(rows, float)
    return pd.DataFrame({"timestamp": ts[:len(a)], "open": a[:, 0], "high": a[:, 1], "low": a[:, 2],
                         "close": a[:, 3], "volume": 1000})


def _spec(**kw):
    base = dict(sim_id="s", run_id="r", hold_bars=50, capital=10_000, slot=10_000, entry_mode="topk", topk=1)
    base.update(kw)
    return portfolio.SimSpec(**base)


NAN = np.nan


def _toy1():
    A = _bars([(100, 101, 99, 100), (100, 101, 99, 100), (90, 92, 88, 91), (91, 92, 90, 91), (91, 92, 90, 91),
               (100, 112, 94, 100), (100, 101, 99, 100)])
    B = _bars([(50, 51, 49, 50), (50, 51, 49, 50), (50, 51, 49, 50), (50, 51, 49.5, 50), (58, 60, 57, 59),
               (59, 60, 58, 59), (59, 60, 58, 59)])
    sa = [0.9, NAN, NAN, NAN, 0.6, NAN, NAN]
    sb = [0.5, NAN, 0.7, NAN, NAN, NAN, NAN]
    return {"A": A, "B": B}, {"A": sa, "B": sb}


def _cnc(q, e, x):
    return round_trip_cost("CNC", q, e, x)


# ------------------------------------------------------------------ tests

def test_time_exit_reproduces_t5_ret(lab):
    H = 25
    b = synth.synthetic_15m(30, seed=3)
    rng = np.random.default_rng(0)
    lab.make("r", "15m", {"A": b}, {"A": rng.random(len(b))})
    tr, eq, _ = portfolio.simulate(_spec(capital=1e7, slot=1e5, hold_bars=H, topk=1), _data(lab, "r"))
    t5 = targets.build_targets(b, "15m", hold_h=[H])[f"t5_ret_H{H}"].to_numpy()
    ix = pd.Index(b["timestamp"])
    tt = tr[tr["reason"] == "TIME"]
    assert len(tt) > 5
    for _, r in tt.iterrows():
        s = ix.get_loc(r["signal_ts"])
        np.testing.assert_allclose(r["exit_px"] / r["entry_px"] - 1, t5[s], rtol=1e-12)
        assert r["held_bars"] == H


def _data(lab, run_id, spec=None):
    spec = spec or _spec(run_id=run_id)
    meta = json.loads((paths.RUNS_DIR / run_id / "meta.json").read_text())
    out = {}
    for s in meta["symbols"]:
        d = portfolio._load_symbol(spec, meta["tf"], s)
        d["excl"] = portfolio._excluded_mask(spec, s, d["ts"])
        out[s] = d
    return out


def _sim(lab, run_id="r", **kw):
    spec = _spec(run_id=run_id, **kw)
    return portfolio.simulate(spec, _data(lab, run_id, spec))


def test_hand_toy_portfolio(lab):
    bars, sc = _toy1()
    lab.make("r", "day", bars, sc)
    tr, eq, info = _sim(lab, stop_pct=0.05, target_pct=0.10)
    assert list(tr["symbol"]) == ["A", "B", "A"]
    assert list(tr["reason"]) == ["STOP", "TARGET", "STOP"]
    # A: signal d0 (higher score than B), entry d1 open 100 qty 100, gap-down d2 open 90 -> fill at the open
    assert (tr.loc[0, "entry_px"], tr.loc[0, "exit_px"], tr.loc[0, "qty"]) == (100, 90, 100)
    assert tr.loc[0, "gross"] == pytest.approx(-1000)
    assert tr.loc[0, "net"] == pytest.approx(-1000 - _cnc(100, 100, 90))
    # B enters the freed slot: signal d2, entry d3 open 50 qty 200, gap-up d4 open 58 > target 55 -> fill at open
    assert pd.Timestamp(tr.loc[1, "signal_ts"]) == pd.Timestamp(DAYS[2])
    assert pd.Timestamp(tr.loc[1, "entry_ts"]) == pd.Timestamp(DAYS[3])
    assert (tr.loc[1, "entry_px"], tr.loc[1, "exit_px"], tr.loc[1, "qty"]) == (50, 58, 200)
    assert tr.loc[1, "gross"] == pytest.approx(1600)
    # A again: entry d5 open 100; bar hits both stop (95) and target (110) -> STOP at 95
    assert (tr.loc[2, "entry_px"], tr.loc[2, "exit_px"]) == (100, 95)
    assert tr.loc[2, "gross"] == pytest.approx(-500)
    mis = round_trip_cost("MIS", 100, 100, 95)               # entered and stopped out on the same date
    assert tr.loc[2, "net"] == pytest.approx(-500 - mis)
    assert tr["cost"].sum() == pytest.approx(_cnc(100, 100, 90) + _cnc(200, 50, 58) + mis)
    assert eq["realised"].iloc[-1] == pytest.approx(tr["net"].sum())
    assert eq["equity"].iloc[-1] == pytest.approx(10_000 + tr["net"].sum())
    # d1: A open (qty 100 @100), mark at close 100 -> deployed 10000, utilisation 1.0
    assert eq.loc[1, "deployed"] == pytest.approx(10_000) and eq.loc[1, "utilisation"] == pytest.approx(1.0)


def test_toy_trailing_exit_fills_next_open_and_slot_reused(lab):
    A = _bars([(100, 101, 99, 100), (100, 111, 100, 110), (110, 110, 102, 103), (102, 103, 101, 102),
               (102, 103, 101, 102), (102, 103, 101, 102), (102, 103, 101, 102)])
    B = _bars([(50, 51, 49, 50)] * 4 + [(50, 51, 49, 50), (50, 52, 49, 51), (51, 52, 50, 51)])
    sc = {"A": [0.9, NAN, NAN, NAN, NAN, NAN, NAN], "B": [NAN, NAN, 0.8, 0.8, NAN, NAN, NAN]}
    lab.make("r", "day", {"A": A, "B": B}, sc)
    tr, _, _ = _sim(lab, trail_pct=0.05, hold_bars=2)
    # A: entry d1 open 100; d1 peak 110; d2 close 103 <= 104.5 -> TRAIL (wins over time stop at held=2), fill d3 open 102
    assert list(tr["reason"]) == ["TRAIL", "TIME"]
    assert (tr.loc[0, "entry_px"], tr.loc[0, "exit_px"]) == (100, 102)
    assert pd.Timestamp(tr.loc[0, "exit_ts"]) == pd.Timestamp(DAYS[3])
    assert tr.loc[0, "gross"] == pytest.approx(200)
    # slot still occupied at d2 (pending exit) -> B signal d2 impossible; freed at d3 -> signal d3, entry d4
    assert pd.Timestamp(tr.loc[1, "signal_ts"]) == pd.Timestamp(DAYS[3])
    assert pd.Timestamp(tr.loc[1, "entry_ts"]) == pd.Timestamp(DAYS[4])
    assert (tr.loc[1, "entry_px"], tr.loc[1, "exit_px"], tr.loc[1, "held_bars"]) == (50, 51, 2)


def test_threshold_is_causal():
    dates = np.repeat(pd.bdate_range("2021-01-04", periods=12).values.astype("datetime64[D]"), 5)
    rng = np.random.default_rng(1)
    s = rng.random(len(dates))
    base = portfolio.causal_thresholds(dates, s, 0.2, window=4)
    D = dates[8 * 5]
    s2 = s.copy()
    s2[dates >= D] = rng.random((dates >= D).sum()) + 5
    new = portfolio.causal_thresholds(dates, s2, 0.2, window=4)
    for d in sorted(set(dates)):
        if d <= D:
            assert base.get(d) == new.get(d)
    uniq = sorted(set(dates))
    assert all(d not in base for d in uniq[:4])           # warm-up: fewer than 4 prior dates
    assert uniq[4] in base
    expect = np.quantile(s[np.isin(dates, uniq[0:4])], 0.8)
    assert base[uniq[4]] == pytest.approx(expect)


def test_no_lookahead_in_trades(lab):
    bars, sc = _toy1()
    lab.make("r", "day", bars, sc)
    t1, _, _ = _sim(lab, stop_pct=0.05, target_pct=0.10)
    bars2 = {k: v.copy() for k, v in bars.items()}
    for v in bars2.values():
        v.loc[3:, ["open", "high", "low", "close"]] *= 1.37       # strictly after the first trade's exit (d2)
    lab.make("r2", "day", bars2, sc)
    t2, _, _ = _sim(lab, run_id="r2", stop_pct=0.05, target_pct=0.10)
    pd.testing.assert_series_equal(t1.iloc[0], t2.iloc[0], check_names=False)


def test_costs_mis_vs_cnc(lab):
    b = synth.synthetic_15m(3, seed=5)
    s1 = np.full(len(b), np.nan); s1[3] = 0.9
    lab.make("r", "15m", {"A": b}, {"A": s1})
    tr, _, _ = _sim(lab, capital=1e6, slot=1e5, hold_bars=2)
    r = tr.iloc[0]
    assert pd.Timestamp(r["entry_ts"]).date() == pd.Timestamp(r["exit_ts"]).date()
    assert r["cost"] == pytest.approx(round_trip_cost("MIS", int(r["qty"]), r["entry_px"], r["exit_px"]))
    s2 = np.full(len(b), np.nan); s2[24] = 0.9
    lab.make("r2", "15m", {"A": b}, {"A": s2})
    tr, _, _ = _sim(lab, run_id="r2", capital=1e6, slot=1e5, hold_bars=26)
    r = tr.iloc[0]
    assert pd.Timestamp(r["entry_ts"]).date() != pd.Timestamp(r["exit_ts"]).date()
    assert r["reason"] == "TIME"
    assert r["cost"] == pytest.approx(round_trip_cost("CNC", int(r["qty"]), r["entry_px"], r["exit_px"]))


def test_exclusion_point_in_time(lab):
    b = synth.synthetic_day(10, seed=2)
    lab.make("r", "day", {"A": b}, {"A": np.linspace(0.1, 0.9, 10)})
    d = b["timestamp"]
    ex = (("A", d[4], d[6]),)
    tr, _, _ = _sim(lab, hold_bars=1, exclusions=ex)
    sig = [pd.Timestamp(x) for x in tr["signal_ts"]]
    assert sig == [pd.Timestamp(d[i]) for i in (0, 1, 2, 3, 7, 8)]
    # an open position is not force-closed by a later exclusion
    tr, _, _ = _sim(lab, hold_bars=5, exclusions=(("A", d[2], d[4]),))
    r = tr.iloc[0]
    assert r["reason"] == "TIME" and pd.Timestamp(r["entry_ts"]) == pd.Timestamp(d[1])
    assert pd.Timestamp(r["exit_ts"]) == pd.Timestamp(d[5])


def test_score_source_ref_and_pred(lab, monkeypatch):
    bars = {"A": synth.synthetic_day(10, seed=1), "B": synth.synthetic_day(10, seed=2)}
    rng = np.random.default_rng(4)
    sc = {s: np.where(np.arange(10) % 3 == 0, np.nan, rng.random(10)) for s in bars}
    pred = {s: {"pred_x": np.arange(10) * 0.1 + (1 if s == "B" else 0)} for s in bars}
    lab.make("r", "day", bars, sc, extra=pred)
    references.write_refs("day", ["A", "B"], ["coin"])
    for s in bars:
        run = portfolio._load_symbol(_spec(), "day", s)
        ref = portfolio._load_symbol(_spec(score_source="ref:coin"), "day", s)
        pr = portfolio._load_symbol(_spec(score_source="pred:pred_x"), "day", s)
        m = np.isfinite(run["score"])
        assert (np.isfinite(ref["score"]) == m).all()
        assert not np.allclose(ref["score"][m], run["score"][m])
        coin = references.read_ref("day", "coin", s)["score"].to_numpy(float)
        np.testing.assert_allclose(ref["score"][m], coin[m])
        np.testing.assert_allclose(pr["score"][m], pred[s]["pred_x"][m], rtol=1e-6)


def test_money_metrics_hand_case():
    net = np.array([300.0, -100.0, 200.0, -200.0])
    eq = pd.Series([1000.0, 1300.0, 1200.0, 1400.0, 1200.0])
    m = portfolio.money_metrics(net, eq, capital=1000.0, years=0.5)
    assert m["total_net"] == 200 and m["trades"] == 4 and m["win_rate"] == 0.5
    assert m["profit_factor"] == pytest.approx(500 / 300)
    assert m["mw_win_pct"] == pytest.approx((500 / 300) / (1 + 500 / 300))
    assert m["avg_net"] == 50
    assert m["max_dd_abs"] == 200
    assert m["max_dd_pct"] == pytest.approx(200 / 1400 * 100)
    assert m["ann_return_pct"] == pytest.approx(40.0)
    assert m["calmar"] == pytest.approx(40.0 / (200 / 1400 * 100))


def test_run_writes_outputs_and_report(lab):
    bars, sc = _toy1()
    lab.make("r", "day", bars, sc)
    s = portfolio.run(_spec(stop_pct=0.05, target_pct=0.10))
    out = paths.PORTFOLIOS_DIR / "s"
    for f in ("trades.parquet", "equity.parquet", "summary.json"):
        assert (out / f).exists()
    text = (portfolio.REPORT_DIR / "s.md").read_text()
    assert "survivor-biased" in text and "money-weighted win %" in text and "Excluding 2020" in text
    assert s["headline"]["trades"] == 3


def test_no_forbidden_imports():
    src = Path(portfolio.__file__).read_text()
    for node in ast.walk(ast.parse(src)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for n in names:
            assert not n.startswith(("trader.strategies", "trader.features", "trader.policy", "trader.backtest")), n


def test_ex2020_headline_excludes_2020_equity_change():
    """Main session 2026-10-18: ex-2020 equity must not carry 2020's P&L into the first 2021 day."""
    dates = pd.to_datetime(["2019-12-30", "2019-12-31", "2020-06-01", "2020-12-31", "2021-01-01", "2021-01-04"])
    eq = pd.DataFrame({"date": dates, "equity": [600_000, 600_000, 300_000, 300_000, 310_000, 320_000],
                       "utilisation": 0.0})
    tr = pd.DataFrame({"exit_ts": pd.to_datetime(["2020-06-01", "2021-01-04"]), "net": [-300_000.0, 20_000.0],
                       "held_bars": [1, 1]})
    m = portfolio._headline(tr, eq, _spec(), drop2020=True)
    assert m["total_net"] == 20_000.0
    assert m["max_dd_abs"] == 0.0        # the 2020 crash is not in the ex-2020 curve
