"""Model Lab L1a — walk-forward runner (synthetic only; RUNS_DIR redirected to tmp)."""
import json

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from research.model_lab import paths, runner, splits
from research.model_lab.source import SynthSource, symbol_frames

FEATS = ["plant_signal", "ret_4", "rsi_14"]
KW = {"step": "1M", "min_train": "3W"}


@pytest.fixture(autouse=True)
def _tmp_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "RUNS_DIR", tmp_path / "runs")
    runner._last_fit_rows = None
    yield
    runner._last_fit_rows = None


def _spec(run_id="r", **kw):
    base = dict(run_id=run_id, tf="15m", scheme="expanding", target="t1w_min_w4", model="logistic",
                features=FEATS, universe_top_n=None, scheme_kw=KW)
    base.update(kw)
    return runner.RunSpec(**base)


def _src(**kw):
    return SynthSource(n_symbols=6, n_sessions=120, seed=1, plant="ret_4", **kw)


def test_runner_end_to_end_synthetic():
    src = _src()
    d = runner.run(_spec(), src)
    meta = json.loads((d / "meta.json").read_text())
    for k in ("run_id", "tf", "scheme", "target", "model", "model_params", "features", "universe_top_n",
              "symbols", "train_rows_per_fold", "seed", "created", "elapsed_s"):
        assert k in meta
    fo = pd.read_parquet(d / "folds.parquet")
    assert len(fo) >= 2
    assert fo["fold_id"].dtype == np.int32 and fo["holdout_group"].dtype == np.int32
    for c in ("train_start", "train_end", "test_start", "test_end"):
        assert str(fo[c].dtype) == "datetime64[ns]"
    assert (fo["holdout_group"] == -1).all()
    frames = []
    for sym in meta["symbols"]:
        sc = pd.read_parquet(d / "scores" / f"{paths.sym_file(sym)}.parquet")
        assert sc["fold_id"].dtype == np.int32 and sc["score"].dtype == np.float32
        assert str(sc["timestamp"].dtype) == "datetime64[ns]"
        f, t = symbol_frames(src, sym, "15m")
        merged = sc.merge(pd.DataFrame({"timestamp": f["timestamp"], "avail_ts": f["avail_ts"],
                                        "y": t["t1w_min_w4"]}), on="timestamp")
        assert len(merged) == len(sc)
        m = merged.merge(fo, on="fold_id")
        assert ((m["avail_ts"] >= m["test_start"]) & (m["avail_ts"] < m["test_end"])).all()
        frames.append(merged.dropna(subset=["y"]))
    al = pd.concat(frames)
    assert roc_auc_score(al["y"], al["score"]) > 0.75


def test_runner_never_trains_on_test_window():
    runner._last_fit_rows = []
    runner.run(_spec(), _src())
    log = runner._last_fit_rows
    assert len(log) >= 2
    emb = pd.Timedelta(splits.EMBARGO["15m"])
    for e in log:
        ts = e["fold"].test_start
        assert pd.Timestamp(e["label_end_max"]) < ts - emb
        assert pd.Timestamp(e["avail_max"]) < ts


class _Excl(SynthSource):
    def __init__(self, *a, excl_year, **k):
        super().__init__(*a, **k)
        self.excl_year = excl_year

    def membership(self, years, top_n, tf="15m"):
        m = super().membership(years, top_n, tf)
        m[self.excl_year] = m[self.excl_year] - {"NSE:SYN0"}
        return m


def test_runner_pit_membership():
    S = "NSE:SYN0"
    # excluded in 2019: no training rows of S with avail in 2019
    src = _Excl(6, 200, 1, plant="ret_4", start="2019-10-01", excl_year=2019)
    runner._last_fit_rows = []
    runner.run(_spec("a", scheme_kw={"step": "1M", "min_train": "3W"}), src)
    seen = False
    for e in runner._last_fit_rows:
        s_rows = e["symbols"] == S
        yrs = pd.DatetimeIndex(e["avail"][s_rows]).year
        seen |= bool(s_rows.any())
        assert (yrs != 2019).all()
    assert seen
    # excluded in 2020: S is scored in 2019 test windows only, never in 2020
    src2 = _Excl(6, 200, 1, plant="ret_4", start="2019-10-01", excl_year=2020)
    d = runner.run(_spec("b"), src2)
    sc = pd.read_parquet(d / "scores" / f"{paths.sym_file(S)}.parquet")
    assert len(sc) and (sc["timestamp"].dt.year == 2019).all()
    other = pd.read_parquet(d / "scores" / f"{paths.sym_file('NSE:SYN1')}.parquet")
    assert (other["timestamp"].dt.year == 2020).any()


def test_runner_holdout_groups():
    d = runner.run(_spec(n_groups=3), _src())
    fo = pd.read_parquet(d / "folds.parquet").set_index("fold_id")
    assert set(fo["holdout_group"]) == {0, 1, 2}
    n = 0
    for f in (d / "scores").glob("*.parquet"):
        sym = paths.file_sym(f.stem)
        sc = pd.read_parquet(f)
        g = sc["fold_id"].map(fo["holdout_group"])
        assert (g == splits.stock_group(sym, 3)).all()
        n += 1
    assert n >= 1


class _ZeroEarly(SynthSource):
    def postprocess(self, symbol, factors, targets):
        factors, targets = super().postprocess(symbol, factors, targets)
        targets = targets.copy()
        targets.loc[targets["timestamp"] < pd.Timestamp("2020-02-20"), "t1w_min_w4"] = 0.0
        return factors, targets


def test_one_class_fold_skipped():
    d = runner.run(_spec(), _ZeroEarly(6, 120, 1, plant="ret_4"))
    meta = json.loads((d / "meta.json").read_text())
    sk = [i["skipped"] for i in meta["folds"]]
    assert sk[0] and "one-class" in sk[0]
    assert any(s is None for s in sk[1:])
    fo = pd.read_parquet(d / "folds.parquet")
    sc = pd.read_parquet(next((d / "scores").glob("*.parquet")))
    assert 0 not in set(sc["fold_id"])
