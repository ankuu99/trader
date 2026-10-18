"""Strategy S0 — offline lab portfolio simulator (scores in, rupee curve out).

Model-agnostic and causal: reads a lab run's out-of-sample scores (or a reference score on the same rows),
ranks eligible stocks at each decision time, fills equal-rupee slots, exits through a small exit library.
Offline lab simulation on a survivor-biased universe (TD-022) — not a production backtest.
Design: docs/04_Strategy_Framework_Proposal.md (S0). No imports from trader.strategies/features/policy/backtest;
trader.costs (pure function) is allowed.
"""
import argparse
import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from research.model_lab import bars as bars_mod
from research.model_lab import paths, references, store
from trader.costs import round_trip_cost

REPORT_DIR = paths.REPO_ROOT / "reviews" / "model_lab" / "portfolios"
HEADER = "Offline lab simulation — survivor-biased universe (TD-022); not a production backtest."


@dataclass(frozen=True)
class SimSpec:
    sim_id: str
    run_id: str
    hold_bars: int
    score_source: str = "run"            # "run" | "ref:<name>" | "pred:<col>"
    capital: float = 600_000
    slot: float = 40_000
    entry_mode: str = "rate"             # "rate" | "topk"
    rate: float = 0.01
    window_sessions: int = 60
    topk: int = 0
    stop_pct: float | None = None
    target_pct: float | None = None
    trail_pct: float | None = None
    trail_activate_pct: float = 0.0
    reentry_gap_bars: int = 0
    exclusions: tuple = ()               # (symbol, from_date, to_date|None)

    @property
    def n_slots(self) -> int:
        return int(self.capital // self.slot)


# ------------------------------------------------------------------ pure helpers

def causal_thresholds(dates, scores, rate: float, window: int) -> dict:
    """Per calendar date D: the (1-rate) quantile of all finite scores on the `window` distinct dates strictly
    before D. Dates with fewer than `window` prior distinct dates (warm-up) get no entry."""
    d = np.asarray(dates).astype("datetime64[D]")
    s = np.asarray(scores, float)
    ok = np.isfinite(s)
    d, s = d[ok], s[ok]
    if len(d) == 0:
        return {}
    order = np.argsort(d, kind="stable")
    d, s = d[order], s[order]
    uniq, start = np.unique(d, return_index=True)
    per = np.split(s, start[1:])
    out = {}
    for i in range(window, len(uniq)):
        pool = np.concatenate(per[i - window:i])
        out[uniq[i]] = float(np.quantile(pool, 1.0 - rate))
    return out


def _max_dd(eq: np.ndarray) -> tuple[float, float]:
    if len(eq) == 0:
        return 0.0, 0.0
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    pct = np.where(peak > 0, dd / peak * 100.0, 0.0)
    return float(dd.max()), float(pct.max())


def money_metrics(trades_net: np.ndarray, equity: pd.Series, capital: float, years: float) -> dict:
    net = np.asarray(trades_net, float)
    n = len(net)
    wins = net[net > 0].sum()
    losses = -net[net < 0].sum()
    if losses > 0:
        pf = float(wins / losses)
    else:
        pf = float("inf") if wins > 0 else float("nan")
    mwwp = 1.0 if pf == float("inf") else (pf / (1.0 + pf) if pf == pf else float("nan"))
    dd_abs, dd_pct = _max_dd(np.asarray(equity, float))
    total = float(net.sum())
    ann = total / capital / years * 100.0 if years > 0 else float("nan")
    return {"total_net": total, "trades": int(n),
            "win_rate": float((net > 0).mean()) if n else float("nan"),
            "profit_factor": pf, "mw_win_pct": mwwp,
            "avg_net": total / n if n else float("nan"),
            "max_dd_abs": dd_abs, "max_dd_pct": dd_pct,
            "ann_return_pct": ann,
            "calmar": ann / dd_pct if dd_pct > 0 else float("nan")}


# ------------------------------------------------------------------ data assembly

def _load_symbol(spec: SimSpec, tf: str, sym: str):
    sc_path = paths.RUNS_DIR / spec.run_id / "scores" / f"{paths.sym_file(sym)}.parquet"
    if not sc_path.exists():
        return None
    sc = pd.read_parquet(sc_path)
    b = bars_mod.load(sym, tf)
    if len(b) == 0 or len(sc) == 0:
        return None
    ts = b["timestamp"].to_numpy("datetime64[ns]")
    ix = pd.Index(ts).get_indexer(pd.DatetimeIndex(sc["timestamp"]))
    keep = ix >= 0
    sc, ix = sc[keep], ix[keep]
    if spec.score_source == "run":
        val = sc["score"].to_numpy(float)
    elif spec.score_source.startswith("pred:"):
        val = sc[spec.score_source[5:]].to_numpy(float)
    elif spec.score_source.startswith("ref:"):
        ref = references.read_ref(tf, spec.score_source[4:], sym)
        if ref is None:
            return None
        rs = pd.Series(ref["score"].to_numpy(float), index=pd.DatetimeIndex(ref["timestamp"]))
        val = rs.reindex(pd.DatetimeIndex(sc["timestamp"])).to_numpy(float)
    else:
        raise ValueError(f"bad score_source {spec.score_source!r}")
    n = len(ts)
    score = np.full(n, np.nan)
    fold = np.full(n, -1, dtype=np.int32)
    score[ix] = val
    fold[ix] = sc["fold_id"].to_numpy(np.int32)
    return {"ts": ts, "o": b["open"].to_numpy(float), "h": b["high"].to_numpy(float),
            "l": b["low"].to_numpy(float), "c": b["close"].to_numpy(float), "score": score, "fold": fold}


def _excluded_mask(spec: SimSpec, sym: str, ts: np.ndarray) -> np.ndarray:
    m = np.zeros(len(ts), bool)
    d = ts.astype("datetime64[D]")
    for s, f, t in spec.exclusions:
        if s != sym:
            continue
        lo = np.datetime64(pd.Timestamp(f).date(), "D")
        hi = np.datetime64(pd.Timestamp(t).date(), "D") if t is not None else None
        m |= (d >= lo) & ((d <= hi) if hi is not None else True)
    return m


# ------------------------------------------------------------------ simulation

def simulate(spec: SimSpec, data: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """data: {symbol: arrays from _load_symbol (+ 'excl')}. Returns (trades, equity, info)."""
    syms = sorted(data)
    sid = {s: i for i, s in enumerate(syms)}
    g_ts = np.concatenate([data[s]["ts"] for s in syms])
    g_sym = np.concatenate([np.full(len(data[s]["ts"]), sid[s], np.int32) for s in syms])
    g_idx = np.concatenate([np.arange(len(data[s]["ts"]), dtype=np.int64) for s in syms])
    g_score = np.concatenate([np.where(data[s]["excl"], np.nan, data[s]["score"]) for s in syms])
    g_close = np.concatenate([data[s]["c"] for s in syms])
    order = np.argsort(g_ts, kind="stable")           # within a timestamp: symbol ascending
    g_ts, g_sym, g_idx, g_score, g_close = g_ts[order], g_sym[order], g_idx[order], g_score[order], g_close[order]
    g_date = g_ts.astype("datetime64[D]")
    nrows = len(g_ts)
    cuts = np.flatnonzero(np.diff(g_ts.astype("int64"))) + 1 if nrows else np.array([], int)
    starts = np.concatenate([[0], cuts]) if nrows else np.array([], int)
    ends = np.concatenate([cuts, [nrows]]) if nrows else np.array([], int)

    thr = causal_thresholds(g_date, g_score, spec.rate, spec.window_sessions) if spec.entry_mode == "rate" else {}
    fin_dates = g_date[np.isfinite(g_score)]
    first_scored = fin_dates.min() if len(fin_dates) else (g_date.max() if nrows else np.datetime64("NaT"))

    open_pos: dict[int, dict] = {}
    pend_in: dict[int, dict] = {}
    pend_out: dict[int, str] = {}
    last_exit: dict[int, int] = {}
    last_close = np.full(len(syms), np.nan)
    trades: list[dict] = []
    eq_rows: list[dict] = []
    realised = 0.0
    qty_zero = 0

    def close(si, px, ts, idx, reason):
        nonlocal realised
        p = open_pos.pop(si)
        s = syms[si]
        et = pd.Timestamp(p["entry_ts"])
        xt = pd.Timestamp(ts)
        product = "MIS" if et.date() == xt.date() else "CNC"
        gross = (px - p["entry_px"]) * p["qty"]
        cost = round_trip_cost(product, p["qty"], p["entry_px"], px)
        net = gross - cost
        realised += net
        last_exit[si] = idx
        trades.append({"symbol": s, "signal_ts": p["signal_ts"], "entry_ts": p["entry_ts"], "entry_px": p["entry_px"],
                       "exit_ts": xt.to_datetime64(), "exit_px": px, "qty": p["qty"], "reason": reason,
                       "held_bars": p["held"], "gross": gross, "cost": cost, "net": net,
                       "ret_pct": net / (p["qty"] * p["entry_px"]), "fold_id": p["fold"], "score": p["score"]})

    for gi in range(len(starts)):
        a, b = int(starts[gi]), int(ends[gi])
        t = g_ts[a]
        bar = dict(zip(g_sym[a:b].tolist(), g_idx[a:b].tolist()))
        last_close[g_sym[a:b]] = g_close[a:b]

        # a. pending exits (marked TRAIL) fill at this bar's open
        for si in [k for k in pend_out if k in bar]:
            d = data[syms[si]]
            close(si, d["o"][bar[si]], t, bar[si], pend_out.pop(si))
        # b. pending entries fill at this bar's open
        fresh = set()
        for si in [k for k in pend_in if k in bar]:
            pe = pend_in.pop(si)
            d = data[syms[si]]
            px = d["o"][bar[si]]
            qty = int(spec.slot // px) if px > 0 else 0
            if qty <= 0:
                qty_zero += 1
                continue
            open_pos[si] = {"entry_px": px, "qty": qty, "entry_ts": t, "signal_ts": pe["signal_ts"], "held": 1,
                            "peak": px, "fold": pe["fold"], "score": pe["score"]}
            fresh.add(si)
        # c. exits on bar t
        for si in [k for k in open_pos if k in bar]:
            p = open_pos[si]
            d = data[syms[si]]
            i = bar[si]
            if si not in fresh:
                p["held"] += 1
            o, h, l, c = d["o"][i], d["h"][i], d["l"][i], d["c"][i]
            e = p["entry_px"]
            if spec.stop_pct is not None and l <= e * (1 - spec.stop_pct):
                close(si, min(o, e * (1 - spec.stop_pct)), t, i, "STOP")
                continue
            if spec.target_pct is not None and h >= e * (1 + spec.target_pct):
                close(si, max(o, e * (1 + spec.target_pct)), t, i, "TARGET")
                continue
            p["peak"] = max(p["peak"], c)
            if (spec.trail_pct is not None and p["peak"] >= e * (1 + spec.trail_activate_pct)
                    and c <= p["peak"] * (1 - spec.trail_pct)):
                pend_out[si] = "TRAIL"
                continue
            if p["held"] >= spec.hold_bars:
                close(si, c, t, i, "TIME")
        # d. entries
        sc = g_score[a:b]
        fin = np.isfinite(sc)
        if fin.any():
            if spec.entry_mode == "rate":
                th = thr.get(g_date[a])
                cand = np.flatnonzero(fin & (sc >= th)) if th is not None else np.array([], int)
            else:
                fi = np.flatnonzero(fin)
                srt = fi[np.lexsort((g_sym[a:b][fi], -sc[fi]))]
                cand = srt[:max(spec.topk, 0)]
            free = spec.n_slots - len(open_pos) - len(pend_in)
            if free > 0 and len(cand):
                cand = cand[np.lexsort((g_sym[a:b][cand], -sc[cand]))]
                for k in cand:
                    if free <= 0:
                        break
                    si = int(g_sym[a + k])
                    if si in open_pos or si in pend_in:
                        continue
                    i = int(g_idx[a + k])
                    if spec.reentry_gap_bars and si in last_exit and i - last_exit[si] < spec.reentry_gap_bars:
                        continue
                    pend_in[si] = {"signal_ts": t, "fold": int(data[syms[si]]["fold"][i]), "score": float(sc[k])}
                    free -= 1
        # e. end-of-date equity row (from the first date with any score: bars start years before the run's
        # first test fold, and counting those idle years would understate the annualised return)
        if g_date[a] < first_scored:
            continue
        if gi == len(starts) - 1 or g_date[int(starts[gi + 1])] != g_date[a]:
            mtm = sum(p["qty"] * (last_close[si] - p["entry_px"]) for si, p in open_pos.items())
            dep = sum(p["qty"] * p["entry_px"] for p in open_pos.values())
            eq_rows.append({"date": pd.Timestamp(g_date[a]), "realised": realised, "mtm": float(mtm),
                            "equity": spec.capital + realised + float(mtm), "deployed": float(dep),
                            "utilisation": float(dep) / spec.capital, "open_positions": len(open_pos)})

    # c. END
    for si in list(open_pos):
        d = data[syms[si]]
        j = len(d["c"]) - 1
        pend_out.pop(si, None)
        close(si, d["c"][j], d["ts"][j], j, "END")
    if eq_rows:
        eq_rows[-1]["realised"] = realised
        eq_rows[-1]["mtm"] = 0.0
        eq_rows[-1]["equity"] = spec.capital + realised
        eq_rows[-1]["deployed"] = 0.0
        eq_rows[-1]["utilisation"] = 0.0
        eq_rows[-1]["open_positions"] = 0
    cols = ["symbol", "signal_ts", "entry_ts", "entry_px", "exit_ts", "exit_px", "qty", "reason", "held_bars",
            "gross", "cost", "net", "ret_pct", "fold_id", "score"]
    tr = pd.DataFrame(trades, columns=cols)
    for c in ("signal_ts", "entry_ts", "exit_ts"):
        tr[c] = pd.to_datetime(tr[c]).astype("datetime64[ns]")
    return tr, pd.DataFrame(eq_rows), {"qty_zero": qty_zero, "n_slots": spec.n_slots}


# ------------------------------------------------------------------ run + report

def _headline(tr: pd.DataFrame, eq: pd.DataFrame, spec: SimSpec, drop2020: bool = False) -> dict:
    if drop2020:
        tr = tr[tr["exit_ts"].dt.year != 2020]
        keep = (eq["date"].dt.year != 2020).to_numpy()
        e = eq[keep]
        # daily changes taken on the FULL series, then 2020's dropped: diffing after the drop would carry all of
        # 2020's P&L into the first 2021 day
        chg = eq["equity"].diff().fillna(0.0)[keep]
        e_val = spec.capital + chg.cumsum() if len(e) else e["equity"]
        e_val = pd.Series(e_val.to_numpy(), index=e["date"].to_numpy())
        years = len(e) / 252.0
    else:
        e_val = pd.Series(eq["equity"].to_numpy(), index=eq["date"].to_numpy())
        years = (eq["date"].iloc[-1] - eq["date"].iloc[0]).days / 365.25 if len(eq) > 1 else 0.0
    m = money_metrics(tr["net"].to_numpy(), e_val, spec.capital, years)
    m["mean_utilisation"] = float(eq["utilisation"].mean()) if len(eq) else float("nan")
    m["avg_held_bars"] = float(tr["held_bars"].mean()) if len(tr) else float("nan")
    return m


def run(spec: SimSpec) -> dict:
    meta = json.loads((paths.RUNS_DIR / spec.run_id / "meta.json").read_text())
    tf = meta["tf"]
    data, skipped = {}, []
    for sym in meta["symbols"]:
        d = _load_symbol(spec, tf, sym)
        if d is None:
            skipped.append(sym)
            continue
        d["excl"] = _excluded_mask(spec, sym, d["ts"])
        data[sym] = d
    tr, eq, info = simulate(spec, data)
    out = paths.PORTFOLIOS_DIR / spec.sim_id
    paths.check_disk()
    out.mkdir(parents=True, exist_ok=True)
    store._atomic_write(out / "trades.parquet", lambda p: tr.to_parquet(p, compression="zstd", index=False))
    store._atomic_write(out / "equity.parquet", lambda p: eq.to_parquet(p, compression="zstd", index=False))
    summary = {"spec": asdict(spec), "tf": tf, "info": info, "skipped_symbols": skipped}
    if len(eq):
        summary["headline"] = _headline(tr, eq, spec)
        summary["headline_ex2020"] = _headline(tr, eq, spec, drop2020=True)
        by_reason = tr.groupby("reason")["net"].agg(["count", "sum"]) if len(tr) else pd.DataFrame()
        summary["exits_by_reason"] = {k: {"count": int(r["count"]), "net": float(r["sum"])}
                                      for k, r in by_reason.iterrows()}
        yrs = []
        for y in sorted(set(eq["date"].dt.year)):
            e = eq[eq["date"].dt.year == y]["equity"].to_numpy()
            t = tr[tr["exit_ts"].dt.year == y]
            yrs.append({"year": int(y), "trades": int(len(t)), "net": float(t["net"].sum()),
                        "max_dd_pct": _max_dd(e)[1]})
        summary["by_year"] = yrs
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    report_portfolio(summary)
    return summary


def _f(x, d=2):
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x:,.{d}f}"


def _line(m: dict) -> str:
    return (f"net ₹{_f(m['total_net'], 0)} · trades {m['trades']} · win rate {_f(m['win_rate'] * 100, 1)}% · "
            f"PF {_f(m['profit_factor'])} · money-weighted win % {_f(m['mw_win_pct'] * 100, 1)} · "
            f"avg ₹{_f(m['avg_net'], 0)}/trade · max DD ₹{_f(m['max_dd_abs'], 0)} ({_f(m['max_dd_pct'], 1)}%) · "
            f"ann. return {_f(m['ann_return_pct'], 1)}% · Calmar {_f(m['calmar'])} · "
            f"mean utilisation {_f(m['mean_utilisation'] * 100, 1)}% · avg held {_f(m['avg_held_bars'], 1)} bars")


def report_portfolio(summary: dict) -> str:
    spec = summary["spec"]
    L = [f"# Portfolio sim `{spec['sim_id']}` (run `{spec['run_id']}`, tf {summary['tf']})", "", HEADER, ""]
    if "headline" not in summary:
        L.append("No decision times / no data.")
    else:
        L += ["## Headline", "", _line(summary["headline"]), "", "## Excluding 2020", "",
              _line(summary["headline_ex2020"]), "", "## Exits by reason (counts and ₹ only)", "",
              "| reason | count | net ₹ |", "|---|---|---|"]
        for k, v in summary["exits_by_reason"].items():
            L.append(f"| {k} | {v['count']} | {_f(v['net'], 0)} |")
        L += ["", "## By calendar year", "", "| year | trades | net ₹ | max DD % |", "|---|---|---|---|"]
        for y in summary["by_year"]:
            L.append(f"| {y['year']} | {y['trades']} | {_f(y['net'], 0)} | {_f(y['max_dd_pct'], 1)} |")
    L += ["", "## Notes", "",
          "- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous "
          f"{spec['window_sessions']} distinct dates (strictly before); the window crosses fold boundaries, so a "
          "model refit that shifts the score scale shifts the threshold only gradually.",
          f"- Skipped symbols (no scores/bars/ref): {len(summary.get('skipped_symbols', []))}; "
          f"qty_zero skips: {summary['info']['qty_zero']}.",
          "", "## Spec", "", "```json", json.dumps(spec, indent=2, default=str), "```", ""]
    text = "\n".join(L)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"{spec['sim_id']}.md").write_text(text)
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--sim-id", required=True)
    ap.add_argument("--score-source", default="run")
    ap.add_argument("--rate", type=float, default=0.01)
    ap.add_argument("--hold-bars", type=int, required=True)
    ap.add_argument("--stop-pct", type=float, default=None)
    ap.add_argument("--target-pct", type=float, default=None)
    ap.add_argument("--trail-pct", type=float, default=None)
    ap.add_argument("--trail-activate-pct", type=float, default=0.0)
    ap.add_argument("--capital", type=float, default=600_000)
    ap.add_argument("--slot", type=float, default=40_000)
    ap.add_argument("--entry-mode", default="rate", choices=["rate", "topk"])
    ap.add_argument("--topk", type=int, default=0)
    a = ap.parse_args()
    spec = SimSpec(sim_id=a.sim_id, run_id=a.run, hold_bars=a.hold_bars, score_source=a.score_source,
                   capital=a.capital, slot=a.slot, entry_mode=a.entry_mode, rate=a.rate, topk=a.topk,
                   stop_pct=a.stop_pct, target_pct=a.target_pct, trail_pct=a.trail_pct,
                   trail_activate_pct=a.trail_activate_pct)
    s = run(spec)
    print(f"sim {a.sim_id}: {s.get('headline', {}).get('trades', 0)} trades -> {paths.PORTFOLIOS_DIR / a.sim_id}")


if __name__ == "__main__":
    main()
