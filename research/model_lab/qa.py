"""Per-symbol data QA: coverage and suspicious jumps (flags, never fixes)."""
import pandas as pd

from research.model_lab import store


def qa_report(interval: str) -> pd.DataFrame:
    rows = []
    for sym in store.list_symbols(interval):
        d = store.read_bars(sym, interval)
        if d.empty:
            continue
        jump = (d["open"] / d["close"].shift(1) - 1).abs() * 100
        jump = jump.dropna()
        if len(jump):
            i = jump.idxmax()
            mj, mts = float(jump.loc[i]), d["timestamp"].loc[i]
        else:
            mj, mts = 0.0, pd.NaT
        rows.append({
            "symbol": sym, "rows": len(d),
            "first": d["timestamp"].iloc[0], "last": d["timestamp"].iloc[-1],
            "dup_ts": int(d["timestamp"].duplicated().sum()),
            "max_jump_pct": mj, "max_jump_ts": mts,
            "n_jumps_30": int((jump > 30).sum()),
            "zero_vol_frac": float((d["volume"] == 0).mean()),
        })
    cols = ["symbol", "rows", "first", "last", "dup_ts", "max_jump_pct",
            "max_jump_ts", "n_jumps_30", "zero_vol_frac"]
    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values("max_jump_pct", ascending=False).reset_index(drop=True)
