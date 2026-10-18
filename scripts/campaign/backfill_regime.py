"""One-off: backfill NIFTY 50 + INDIA VIX 15m candles into the local cache for the campaign's
market-context arm (EXP-07). The cache held only 2023-11-28 → 2026-08-31; the campaign windows
need 2019-06 → 2026-10-16 (HORIZON warm-up included).

    .venv/bin/python scripts/campaign/backfill_regime.py
"""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from trader.auth.session import create_kite
from trader.core.config import config
from trader.data.historical import _fetch_and_cache, get_candles
from trader.data.store import Store

START, END = datetime(2019, 6, 1), datetime(2026, 10, 16, 23, 59)


def main():
    kite = create_kite()
    toks = {f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in kite.instruments("NSE")
            if i["tradingsymbol"] in ("NIFTY 50", "INDIA VIX")}
    store = Store(config.db_path)
    for sym, tok in toks.items():
        print(sym, tok)
        _fetch_and_cache(kite, store, tok, sym, "15minute", START, datetime(2023, 11, 28, 9, 0))
        df = get_candles(kite, store, tok, sym, "15minute", START, END)
        print(f"  {len(df)} rows {df['timestamp'].min()} → {df['timestamp'].max()}")


if __name__ == "__main__":
    main()
