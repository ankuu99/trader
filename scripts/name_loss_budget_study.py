"""Per-instrument rolling loss-budget stratification (static, read-only).

Question (2026-09-07): should each stock carry a rolling loss budget (e.g. 20% of lot
notional over a trailing quarter) that (a) tightens the hard stop on a new lot to the
REMAINING budget and (b) blocks entry once the budget is exhausted?

Method — takes a finished backtest trade CSV, groups lot records into rounds
(instrument + entry_date), and for every round computes what the SAME instrument
realised over the trailing `--window-days` calendar days before that entry:

  * losses-only ledger  — consumed = sum of losing rounds' % loss in the window
  * drawdown ledger     — consumed = giveback from the rolling high-water-mark of the
                          instrument's cumulative %-P&L inside the window (wins restore)

Rounds are bucketed by remaining budget and their ACTUAL P&L is reported per bucket
(is the low-budget bucket negative-EV?). Then a static replay against the 15m candle
cache tightens each affected round's hard stop to entry × (1 − remaining%) and
blocks rounds whose remaining budget is below `--floor-pct`, to estimate the P&L
change. Static: freed capital is not redeployed and the ledger is not re-computed
with the tightened losses (second-order).

    python scripts/name_loss_budget_study.py backtest_results/portfolio_...csv \
        --window-days 90 --budget-pct 20 --floor-pct 3
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BUCKETS = [
    ("untouched (=budget)", lambda r, b: r >= b - 1e-9),
    ("75–100% left", lambda r, b: 0.75 * b <= r < b - 1e-9),
    ("50–75% left", lambda r, b: 0.50 * b <= r < 0.75 * b),
    ("25–50% left", lambda r, b: 0.25 * b <= r < 0.50 * b),
    ("0–25% left", lambda r, b: 0 < r < 0.25 * b),
    ("exhausted (<=0)", lambda r, b: r <= 0),
]


def load_rounds(csv: Path) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["entry_date", "exit_date"])
    df["notional"] = df["entry"] * df["qty"]
    g = df.groupby(["instrument", "entry_date"], as_index=False).agg(
        exit_date=("exit_date", "max"),
        entry=("entry", "first"),
        qty=("qty", "sum"),
        notional=("notional", "sum"),
        pnl=("pnl", "sum"),
        cost=("cost", "sum"),
        reasons=("reason", lambda s: "+".join(sorted(set(s)))),
    )
    g["pct"] = g["pnl"] / g["notional"] * 100.0
    return g.sort_values(["instrument", "entry_date"]).reset_index(drop=True)


def ledgers(rounds: pd.DataFrame, window_days: int, budget: float) -> pd.DataFrame:
    win = pd.Timedelta(days=window_days)
    out = []
    for inst, grp in rounds.groupby("instrument", sort=False):
        grp = grp.sort_values("entry_date")
        for _, r in grp.iterrows():
            prior = grp[(grp["exit_date"] <= r["entry_date"])
                        & (grp["exit_date"] >= r["entry_date"] - win)].sort_values("exit_date")
            loss_only = -prior.loc[prior["pct"] < 0, "pct"].sum()
            cum = prior["pct"].cumsum()
            hwm = max(0.0, cum.max()) if len(cum) else 0.0
            last = cum.iloc[-1] if len(cum) else 0.0
            giveback = max(0.0, hwm - last)
            out.append({
                **r.to_dict(),
                "prior_rounds": len(prior),
                "prior_loss_streak": int(prior["pct"].lt(0).iloc[-1]) if len(prior) else 0,
                "rem_loss_only": budget - loss_only,
                "rem_drawdown": budget - giveback,
            })
    return pd.DataFrame(out)


def bucket_table(df: pd.DataFrame, col: str, budget: float) -> pd.DataFrame:
    rows = []
    for name, pred in BUCKETS:
        sel = df[df[col].apply(lambda r: pred(r, budget))]
        if sel.empty:
            rows.append({"bucket": name, "rounds": 0})
            continue
        rows.append({
            "bucket": name,
            "rounds": len(sel),
            "pnl": round(sel["pnl"].sum()),
            "avg_pnl": round(sel["pnl"].mean()),
            "win_rate": round((sel["pnl"] > 0).mean() * 100, 1),
            "avg_pct": round(sel["pct"].mean(), 2),
            "instruments": sel["instrument"].nunique(),
        })
    return pd.DataFrame(rows)


def replay(df: pd.DataFrame, col: str, budget: float, floor: float, db: Path,
           timeframe: str = "15minute") -> pd.DataFrame:
    """Static replay: tightened stop / block for rounds with remaining < budget."""
    con = sqlite3.connect(db)
    cache: dict[str, pd.DataFrame] = {}

    def candles(inst: str) -> pd.DataFrame:
        if inst not in cache:
            c = pd.read_sql_query(
                "SELECT timestamp, open, low FROM candles WHERE instrument=? AND timeframe=? "
                "ORDER BY timestamp", con, params=(inst, timeframe), parse_dates=["timestamp"])
            cache[inst] = c
        return cache[inst]

    res = []
    for _, r in df.iterrows():
        rem = r[col]
        new_pnl, action, stop = r["pnl"], "unchanged", None
        if rem < budget - 1e-9:
            if rem <= floor:
                new_pnl, action = 0.0, "blocked"
            else:
                stop = r["entry"] * (1 - rem / 100.0)
                c = candles(r["instrument"])
                path = c[(c["timestamp"] >= r["entry_date"]) & (c["timestamp"] <= r["exit_date"])]
                hit = path[path["low"] <= stop]
                if not hit.empty:
                    h = hit.iloc[0]
                    px = min(stop, h["open"])
                    new_pnl = (px - r["entry"]) * r["qty"] - r["cost"]
                    action = "stopped_early"
        res.append({**r.to_dict(), "action": action, "tight_stop": stop, "new_pnl": new_pnl,
                    "delta": new_pnl - r["pnl"]})
    return pd.DataFrame(res)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--window-days", type=int, default=90)
    ap.add_argument("--budget-pct", type=float, default=20.0)
    ap.add_argument("--floor-pct", type=float, default=3.0)
    ap.add_argument("--db", type=Path, default=Path("data/market.db"))
    ap.add_argument("--dump", type=Path, default=None, help="write per-round table to CSV")
    a = ap.parse_args()

    rounds = load_rounds(a.csv)
    df = ledgers(rounds, a.window_days, a.budget_pct)
    print(f"rounds={len(df)}  lots={sum(1 for _ in open(a.csv)) - 1}  net P&L={df['pnl'].sum():,.0f}  "
          f"window={a.window_days}d budget={a.budget_pct}% floor={a.floor_pct}%\n")

    print("== Control: rounds whose immediately-prior round (in window) was a LOSS ==")
    ctl = df[df["prior_rounds"] > 0]
    for flag, name in ((1, "after a loss"), (0, "after a win")):
        s = ctl[ctl["prior_loss_streak"] == flag]
        print(f"  {name:12s} rounds={len(s):4d} pnl={s['pnl'].sum():>10,.0f} avg={s['pnl'].mean():>8,.0f} "
              f"win%={(s['pnl'] > 0).mean() * 100:5.1f}")
    s = df[df["prior_rounds"] == 0]
    print(f"  {'no history':12s} rounds={len(s):4d} pnl={s['pnl'].sum():>10,.0f} avg={s['pnl'].mean():>8,.0f} "
          f"win%={(s['pnl'] > 0).mean() * 100:5.1f}\n")

    for col, label in (("rem_loss_only", "LOSSES-ONLY ledger"), ("rem_drawdown", "DRAWDOWN ledger (wins restore)")):
        print(f"== {label}: actual P&L by remaining budget at entry ==")
        print(bucket_table(df, col, a.budget_pct).to_string(index=False))
        rp = replay(df, col, a.budget_pct, a.floor_pct, a.db)
        acts = rp["action"].value_counts().to_dict()
        print(f"\n   static replay: {acts}")
        print(f"   P&L {rp['pnl'].sum():,.0f} -> {rp['new_pnl'].sum():,.0f}  (delta {rp['delta'].sum():+,.0f})")
        for act in ("stopped_early", "blocked"):
            s = rp[rp["action"] == act]
            if s.empty:
                continue
            was_win = s[s["pnl"] > 0]
            print(f"   {act}: {len(s)} rounds, delta {s['delta'].sum():+,.0f}; "
                  f"{len(was_win)} of them were actual winners worth {was_win['pnl'].sum():,.0f}")
        worst = rp[rp["action"] != "unchanged"].nsmallest(5, "delta")[
            ["instrument", "entry_date", "pct", col, "action", "pnl", "new_pnl", "delta"]]
        best = rp[rp["action"] != "unchanged"].nlargest(5, "delta")[
            ["instrument", "entry_date", "pct", col, "action", "pnl", "new_pnl", "delta"]]
        print("   worst 5 rounds for the rule:\n" + worst.to_string(index=False))
        print("   best 5 rounds for the rule:\n" + best.to_string(index=False))
        print(f"   per-instrument delta (non-zero):")
        pi = rp.groupby("instrument")["delta"].sum()
        print("   " + pi[pi != 0].sort_values().round(0).to_string().replace("\n", "\n   "))
        print()
        if a.dump:
            rp.to_csv(a.dump.with_name(a.dump.stem + f"_{col}.csv"), index=False)


if __name__ == "__main__":
    main()
