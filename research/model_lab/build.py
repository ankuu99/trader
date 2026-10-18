"""Build factor + target parquet tables per (timeframe, symbol).

    .venv/bin/python -m research.model_lab.build --tf 15m [--symbols NSE:A NSE:B …] [--what factors targets] [--no-xs]
"""
import argparse
import logging
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd

from research.model_lab import bars as bars_mod
from research.model_lab import factors as fx
from research.model_lab import targets as tg
from research.model_lab.paths import FACTORS_DIR, LOGS_DIR, TARGETS_DIR, check_disk, sym_file

log = logging.getLogger("model_lab.build")
NIFTY, VIX = "NSE:NIFTY 50", "NSE:INDIA VIX"
XS_COLS = ["xs_n", "xs_rank_ret16", "xs_rank_ret64", "xs_breadth_100"]
MIN_BARS = 300


def _write(df: pd.DataFrame, path) -> int:
    """float32 (timestamp/avail_ts stay datetime64[ns]), zstd, atomic."""
    df = df.copy()
    for c in df.columns:
        if c in ("timestamp", "avail_ts"):
            df[c] = df[c].astype("datetime64[ns]")
        else:
            df[c] = df[c].astype("float32")
    check_disk()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, compression="zstd", index=False)
    os.replace(tmp, path)
    return path.stat().st_size


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", required=True, choices=bars_mod.TFS)
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--what", nargs="*", default=["factors", "targets"], choices=["factors", "targets"])
    ap.add_argument("--no-xs", action="store_true")
    a = ap.parse_args(argv)
    from research.model_lab import store             # lazy: built by the L0a guide

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(LOGS_DIR / f"build_{a.tf}_{stamp}.log")])
    t0 = time.time()
    tf = a.tf
    syms = a.symbols or [s for s in store.list_symbols(bars_mod.SOURCE[tf]) if s not in (NIFTY, VIX)]

    nifty = vix = None
    if "factors" in a.what:
        try:
            nifty = bars_mod.load(NIFTY, tf)
        except Exception as e:
            log.warning("no NIFTY bars for %s (%s) — nifty columns will be NaN", tf, e)
        try:
            vix = store.read_bars(VIX, "day")
        except Exception as e:
            log.warning("no INDIA VIX bars (%s) — vix columns will be NaN", e)

    nfiles = nbytes = 0
    xs_in: dict[str, pd.DataFrame] = {}
    for sym in syms:
        ts0 = time.time()
        try:
            b = bars_mod.load(sym, tf)
        except Exception as e:
            log.warning("%s: load failed (%s) — skipped", sym, e)
            continue
        if len(b) < MIN_BARS:
            log.info("%s: only %d bars (< %d) — skipped", sym, len(b), MIN_BARS)
            continue
        if "factors" in a.what:
            higher = {}
            for htf in fx.HIGHER_TF[tf]:
                try:
                    higher[htf] = bars_mod.load(sym, htf)
                except Exception as e:
                    log.warning("%s: higher %s missing (%s)", sym, htf, e)
            f = fx.compute_factors(b, tf, nifty=nifty, vix_day=vix, higher=higher)
            xs_in[sym] = pd.DataFrame({"timestamp": b["timestamp"].values, "ret_16": f["ret_16"].values,
                                       "ret_64": f["ret_64"].values, "close": b["close"].values})
            for c in XS_COLS:
                f[c] = np.nan
            nbytes += _write(f, FACTORS_DIR / tf / f"{sym_file(sym)}.parquet"); nfiles += 1
        if "targets" in a.what:
            t = tg.build_targets(b, tf)
            nbytes += _write(t, TARGETS_DIR / tf / f"{sym_file(sym)}.parquet"); nfiles += 1
        log.info("%s: %d rows %.1fs", sym, len(b), time.time() - ts0)

    if "factors" in a.what and not a.no_xs and xs_in:
        xs = fx.cross_section(xs_in)
        for sym, x in xs.items():
            p = FACTORS_DIR / tf / f"{sym_file(sym)}.parquet"
            f = pd.read_parquet(p)
            for c in XS_COLS:
                f[c] = x[c].values
            nbytes += _write(f, p)
        log.info("cross-section pass: %d symbols", len(xs))

    log.info("done: %d files written, %.1f MB, %.1fs", nfiles, nbytes / 1e6, time.time() - t0)


if __name__ == "__main__":
    main()
