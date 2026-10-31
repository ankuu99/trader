"""
Export a real stock's cached candles as an Extrema Lab scenario so its dips/peaks
can be hand-labelled and the detection stack benchmarked against a human truth.

    python scripts/lab/export_stock.py NSE:ATHERENERG [--timeframe 15minute] [--from 2025-01-01]

Writes lab_data/<SYMBOL>_<tf>/candles.csv + meta.json (no `true_extrema` — real
data has no generator truth; the lab's pre-seed button is disabled for it).
Reads the local SQLite cache only (never fetches).
"""
import argparse, datetime, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "config" / ".env")

from trader.core.config import config
from trader.data.store import Store
from scripts.lab.generator import LAB_DATA_DIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--timeframe", default=None, help="default: config.candle_timeframe")
    ap.add_argument("--from", dest="from_date", default="2023-01-01")
    args = ap.parse_args()
    tf = args.timeframe or config.candle_timeframe
    store = Store(config.db_path)
    df = store.read_candles(args.symbol, tf, datetime.datetime.strptime(args.from_date, "%Y-%m-%d"),
                            datetime.datetime.now())
    if df.empty:
        sys.exit(f"no cached {tf} candles for {args.symbol}")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp")
    name = f"{args.symbol.split(':')[-1]}_{tf}"
    d = LAB_DATA_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    df.to_csv(d / "candles.csv", index=False)
    (d / "meta.json").write_text(json.dumps({
        "generator_version": 0, "real": True, "symbol": args.symbol, "timeframe": tf,
        "spec": {"name": name}, "bars": int(len(df)),
        "first": str(df.timestamp.iloc[0]), "last": str(df.timestamp.iloc[-1]),
        "exported": datetime.datetime.now().isoformat(timespec="seconds"),
    }, indent=2))
    print(f"wrote {d} — {len(df)} bars {df.timestamp.iloc[0]} → {df.timestamp.iloc[-1]}")


if __name__ == "__main__":
    main()
