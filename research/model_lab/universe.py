"""Point-in-time universe for the Model Lab.

Known limitation: SURVIVORSHIP. The instrument snapshot only lists names trading
on the snapshot date; delisted / merged names are absent, so every universe built
from it is biased toward survivors. The liquidity panel itself is point-in-time
(value at date D uses only sessions before D).
"""
from datetime import date, datetime

import pandas as pd

from research.model_lab import paths, store

_INDEX = {"NSE:NIFTY 50", "NSE:INDIA VIX"}


def _is_etf(name: str, ts: str) -> bool:
    return ("ETF" in name.upper() or ts.endswith(("BEES", "ETF", "IETF")) or "BEES" in ts)


def snapshot_instruments(kite) -> pd.DataFrame:
    rows = []
    for r in kite.instruments("NSE"):
        ts = r.get("tradingsymbol") or ""
        name = r.get("name") or ""
        if r.get("segment") != "NSE" or r.get("instrument_type") != "EQ" or "-" in ts:
            continue
        if _is_etf(name, ts):
            continue
        rows.append({
            "symbol": "NSE:" + ts, "tradingsymbol": ts,
            "instrument_token": r.get("instrument_token"), "name": name,
            "lot_size": r.get("lot_size"), "tick_size": r.get("tick_size"),
        })
    df = pd.DataFrame(rows, columns=["symbol", "tradingsymbol", "instrument_token",
                                     "name", "lot_size", "tick_size"])
    paths.UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(paths.UNIVERSE_DIR / f"nse_eq_{datetime.now():%Y%m%d}.csv", index=False)
    return df


def latest_snapshot() -> pd.DataFrame:
    files = sorted(paths.UNIVERSE_DIR.glob("nse_eq_*.csv")) if paths.UNIVERSE_DIR.exists() else []
    if not files:
        raise FileNotFoundError("no instrument snapshot — run fetch daily --snapshot")
    return pd.read_csv(files[-1])


def _panel_name(interval: str) -> str:
    return "liquidity_daily.parquet" if interval == "day" else f"liquidity_{interval}.parquet"


def build_liquidity_panel(symbols: list[str] | None = None, interval: str = "day") -> pd.DataFrame:
    paths.check_disk()
    out = []
    for sym in symbols or store.list_symbols(interval):
        d = store.read_bars(sym, interval)
        if d.empty:
            continue
        tv = d["close"] * d["volume"]
        prior = tv.shift(1)
        out.append(pd.DataFrame({
            "date": d["timestamp"],
            "symbol": sym,
            "med_tv_252": prior.rolling(252, min_periods=200).median(),
            "n_sessions": prior.notna().cumsum().astype("int64"),
        }))
    panel = (pd.concat(out, ignore_index=True) if out else
             pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "symbol": pd.Series(dtype=str),
                           "med_tv_252": pd.Series(dtype="float64"),
                           "n_sessions": pd.Series(dtype="int64")}))
    paths.UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    store._atomic_write(paths.UNIVERSE_DIR / _panel_name(interval),
                        lambda t: panel.to_parquet(t, engine="pyarrow", compression="zstd", index=False))
    return panel


def _load_panel(interval: str = "day") -> pd.DataFrame:
    return pd.read_parquet(paths.UNIVERSE_DIR / _panel_name(interval))


def liquid_universe(asof, top_n: int, panel: pd.DataFrame | None = None,
                    min_sessions: int = 200) -> list[str]:
    panel = _load_panel() if panel is None else panel
    asof = pd.Timestamp(asof)
    p = panel[(panel["date"] < asof) & ~panel["symbol"].isin(_INDEX)]
    p = p.dropna(subset=["med_tv_252"])
    if p.empty:
        return []
    last = p.sort_values("date").groupby("symbol", as_index=False).tail(1)
    last = last[(last["n_sessions"] >= min_sessions)
                & (last["date"] >= asof - pd.Timedelta(days=10))]
    last = last.sort_values(["med_tv_252", "symbol"], ascending=[False, True])
    return last["symbol"].head(top_n).tolist()


def intraday_fetch_list(years: list[int], top_n: int, panel: pd.DataFrame | None = None) -> list[str]:
    panel = _load_panel() if panel is None else panel
    syms: set[str] = set()
    for y in years:
        syms.update(liquid_universe(date(y, 1, 1), top_n, panel))
    return sorted(syms)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="research.model_lab.universe")
    ap.add_argument("stage", choices=["build"])
    ap.add_argument("--interval", default="day", choices=["day", "day_nse"])
    args = ap.parse_args(argv)
    panel = build_liquidity_panel(interval=args.interval)
    print(f"liquidity panel ({args.interval}): {len(panel)} rows, {panel['symbol'].nunique()} symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
