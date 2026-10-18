"""Walk-forward split engine: dynamic schemes, purge + embargo by each row's label end time.

All windows are half-open [start, end) on avail_ts. `train_mask` is the leakage gate.
"""
import hashlib
import re
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

EMBARGO = {"15m": "1D", "30m": "1D", "60m": "1D", "4h": "1D", "dayagg": "1D", "day": "5D", "week": "21D",
          "dayn": "5D", "weekn": "21D"}


@dataclass(frozen=True)
class Fold:
    fold_id: int
    scheme: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    holdout_group: int = -1


def _offset(s: str) -> pd.DateOffset:
    m = re.fullmatch(r"(\d+)([YMWD])", s)
    if not m:
        raise ValueError(f"bad duration {s!r} (use e.g. 2Y, 6M, 3W, 5D)")
    n, u = int(m.group(1)), m.group(2)
    return pd.DateOffset(**{{"Y": "years", "M": "months", "W": "weeks", "D": "days"}[u]: n})


def _step_months(step: str) -> int:
    m = re.fullmatch(r"(\d+)M", step)
    if not m or 12 % int(m.group(1)):
        raise ValueError(f"step must be a divisor of 12 months, e.g. 1M/2M/3M/6M/12M, got {step!r}")
    return int(m.group(1))


def test_windows(data_start, data_end, step: str = "6M", min_train: str = "2Y"):
    data_start, data_end = pd.Timestamp(data_start), pd.Timestamp(data_end)
    k = _step_months(step)
    first = data_start + _offset(min_train)
    s = pd.Timestamp(first.year, ((first.month - 1) // k) * k + 1, 1)
    if s < first:
        s = s + pd.DateOffset(months=k)
    out = []
    while s < data_end:
        e = s + pd.DateOffset(months=k)
        if e > data_end:
            e = data_end
            if (e - s) < pd.Timedelta(days=30):
                break
        out.append((s, e))
        s = s + pd.DateOffset(months=k)
    return out


def expanding(data_start, data_end, step="6M", min_train="2Y", scheme="expanding") -> list[Fold]:
    ds = pd.Timestamp(data_start)
    return [Fold(i, scheme, ds, s, s, e)
            for i, (s, e) in enumerate(test_windows(ds, data_end, step, min_train))]


def rolling(data_start, data_end, train_len: str, step="6M", min_train="2Y") -> list[Fold]:
    ds = pd.Timestamp(data_start)
    off = _offset(train_len)
    return [Fold(i, f"rolling_{train_len}", max(ds, s - off), s, s, e)
            for i, (s, e) in enumerate(test_windows(ds, data_end, step, min_train))]


def anchor_sweep(data_start, data_end, anchors: list[str], step="6M", min_train="2Y") -> list[Fold]:
    rows = []
    for a in anchors:
        A = pd.Timestamp(a)
        for s, e in test_windows(A, data_end, step, min_train):
            rows.append((s, A, e))
    rows.sort(key=lambda r: (r[0], r[1]))
    return [Fold(i, f"anchor_{A.year}", A, s, s, e) for i, (s, A, e) in enumerate(rows)]


def leave_one_year_out(data_start, data_end) -> list[Fold]:
    ds, de = pd.Timestamp(data_start), pd.Timestamp(data_end)
    out = []
    for y in range(ds.year, de.year + 1):
        s, e = pd.Timestamp(y, 1, 1), pd.Timestamp(y + 1, 1, 1)
        if e <= ds or s >= de:
            continue
        out.append(Fold(len(out), "loyo", ds, de, s, e))
    return out


def stock_group(symbol: str, n_groups: int) -> int:
    return int(hashlib.md5(symbol.encode()).hexdigest(), 16) % n_groups


def with_stock_groups(folds: list[Fold], n_groups: int) -> list[Fold]:
    out = []
    for f in folds:
        for g in range(n_groups):
            out.append(replace(f, fold_id=len(out), holdout_group=g))
    return out


def _groups(symbols, n_groups) -> np.ndarray:
    if n_groups is None:
        raise ValueError("n_groups required when a fold holds out a stock group")
    syms = np.asarray(symbols)
    uniq, inv = np.unique(syms, return_inverse=True)
    return np.array([stock_group(str(u), n_groups) for u in uniq], dtype=np.int64)[inv]


def train_mask(fold: Fold, avail_ts, label_end_ts, symbols, tf: str, n_groups: int | None = None) -> np.ndarray:
    av = np.asarray(avail_ts, dtype="datetime64[ns]")
    le = np.asarray(label_end_ts, dtype="datetime64[ns]")
    emb = np.timedelta64(pd.Timedelta(EMBARGO[tf]).value, "ns")
    ts, te = fold.train_start.to_datetime64(), fold.train_end.to_datetime64()
    t0, t1 = fold.test_start.to_datetime64(), fold.test_end.to_datetime64()
    ok = (av >= ts) & (av < te) & ~np.isnat(le)
    before = av < t0
    # rows before the test window: the label must be fully resolved a full embargo before it opens
    ok &= ~before | (le < t0 - emb)
    if fold.scheme == "loyo":
        ok &= before | (av >= t1 + emb)
    else:
        ok &= before
    ok &= ~((av >= t0 - emb) & (av < t1 + emb))
    if fold.holdout_group >= 0:
        ok &= _groups(symbols, n_groups) != fold.holdout_group
    return ok


def test_mask(fold: Fold, avail_ts, symbols, n_groups: int | None = None) -> np.ndarray:
    av = np.asarray(avail_ts, dtype="datetime64[ns]")
    ok = (av >= fold.test_start.to_datetime64()) & (av < fold.test_end.to_datetime64())
    if fold.holdout_group >= 0:
        ok &= _groups(symbols, n_groups) == fold.holdout_group
    return ok


def make_folds(scheme: str, data_start, data_end, **kw) -> list[Fold]:
    n_groups = kw.pop("n_groups", None)
    step, min_train = kw.get("step", "6M"), kw.get("min_train", "2Y")
    if scheme == "expanding":
        folds = expanding(data_start, data_end, step, min_train)
    elif re.fullmatch(r"rolling_\d+[YM]", scheme):
        folds = rolling(data_start, data_end, scheme.split("_", 1)[1], step, min_train)
    elif scheme == "anchor":
        folds = anchor_sweep(data_start, data_end, kw["anchors"], step, min_train)
    elif scheme == "loyo":
        folds = leave_one_year_out(data_start, data_end)
    else:
        raise ValueError(f"unknown scheme {scheme!r}")
    return with_stock_groups(folds, n_groups) if n_groups else folds
