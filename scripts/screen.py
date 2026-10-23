"""
NSE stock screener — backtest LRExtremaStrategy against all NSE EQ instruments.

    python scripts/screen.py --from 2024-01-01
    python scripts/screen.py --from 2024-01-01 --to 2025-01-01 --min-trades 3 --output results.csv
    python scripts/screen.py --from 2024-01-01 --workers 8

Two-phase execution:
  Phase 1 (sequential, rate-limited): fetch & cache candles for all stocks via Kite API.
  Phase 2 (parallel):                 run backtests using ProcessPoolExecutor (kite=None).

Resumes from where it left off — already-processed symbols in the output CSV are skipped.
"""

import argparse
import csv
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.auth.session import create_kite
from trader.backtest.engine import compute_metrics, run_backtest
from trader.core.config import config
from trader.core.logger import get_logger, setup
from trader.data.historical import get_candles
from trader.data.store import Store
from trader.notifications import telegram
telegram.disable()

setup(log_dir=config.log_dir, level="WARNING")
logger = get_logger(__name__)

def _fetch_surveillance_symbols() -> set[str]:
    """Fetch current ASM + ESM stocks from NSE API. Returns set of ticker symbols to exclude."""
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        })
        session.get("https://www.nseindia.com", timeout=10)

        symbols: set[str] = set()

        r_asm = session.get("https://www.nseindia.com/api/reportASM", timeout=10)
        asm_data = r_asm.json()
        for section in ["longterm", "shortterm"]:
            section_data = asm_data.get(section, {})
            rows = section_data.get("data", []) if isinstance(section_data, dict) else section_data
            for row in rows:
                symbols.add(row["symbol"])

        r_esm = session.get("https://www.nseindia.com/api/reportESM", timeout=10)
        esm_rows = r_esm.json() if isinstance(r_esm.json(), list) else r_esm.json().get("data", [])
        for row in esm_rows:
            symbols.add(row.get("symbol") or row.get("SYMBOL", ""))

        symbols.discard("")
        return symbols
    except Exception as e:
        logger.warning("Could not fetch ASM/ESM list from NSE: %s — surveillance filter skipped", e)
        return set()


_CSV_FIELDS = [
    "instrument", "trades", "wins", "win_rate", "total_pnl",
    "return_pct", "sharpe_proxy", "period",
]


def _load_processed_symbols(path: str) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    with open(p) as f:
        reader = csv.DictReader(f)
        return {row["instrument"] for row in reader if "instrument" in row}


def _append_to_csv(path: str, symbol: str, metrics: dict, from_dt: datetime, to_dt: datetime):
    p = Path(path)
    write_header = not p.exists()
    with open(p, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "instrument": symbol,
            "trades": metrics["total_trades"],
            "wins": metrics["wins"],
            "win_rate": f"{metrics['money_weighted_win_rate']:.1f}",
            "total_pnl": f"{metrics['total_pnl']:.2f}",
            "return_pct": f"{metrics['return_pct']:.4f}",
            "sharpe_proxy": f"{metrics['sharpe_proxy']:.4f}",
            "period": f"{from_dt.date()} to {to_dt.date()}",
        })


def _print_final_table(results: list[dict], min_trades: int):
    filtered = [r for r in results if r["total_trades"] >= min_trades]
    filtered.sort(key=lambda r: r["return_pct"], reverse=True)

    print(f"\n{'='*75}")
    print(f"  Top performers (min {min_trades} trades) — sorted by Return%")
    print(f"{'='*75}")
    if not filtered:
        print("  No stocks met the minimum trades threshold.")
    else:
        print(f"  {'Instrument':<18}  {'Trades':>6}  {'Win%':>5}  {'P&L':>12}  {'Return%':>8}  {'Sharpe*':>8}")
        print(f"  {'-'*71}")
        for r in filtered:
            print(
                f"  {r['instrument']:<18}  {r['total_trades']:>6}  {r['money_weighted_win_rate']:>4.0f}%  "
                f"₹{r['total_pnl']:>11,.0f}  {r['return_pct']:>7.2f}%  {r['sharpe_proxy']:>8.3f}"
            )
    print(f"{'='*75}\n")


# ── Worker (top-level for multiprocessing pickling) ───────────────────────────

def _run_single(job: tuple) -> dict | None:
    logging.getLogger().setLevel(logging.CRITICAL)
    symbol, token, params, symbol_to_token, from_dt, to_dt, db_path, total_capital, timeframe = job
    if timeframe:
        config._data["candle_timeframe"] = timeframe
    # Screening evaluates raw per-stock fit — always un-levered (no scale-in).
    config._data.setdefault("scale_in", {})["enabled"] = False
    store = Store(db_path)
    try:
        trades = run_backtest(None, store, [symbol], symbol_to_token, params, from_dt, to_dt)
        metrics = compute_metrics(trades, total_capital)
        return {"symbol": symbol, **metrics}
    except Exception as e:
        logger.warning("Backtest failed for %s: %s", symbol, e)
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Screen all NSE EQ stocks with LRExtremaStrategy")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--min-trades", type=int, default=2,
                        help="Minimum trades to include in final table (default: 2)")
    parser.add_argument("--output", default="screen_results.csv",
                        help="Output CSV file path (default: screen_results.csv)")
    parser.add_argument("--timeframe", default=None,
                        choices=["5minute", "15minute", "30minute", "60minute", "day"],
                        help="Candle timeframe (default: from config)")
    parser.add_argument("--workers", type=int, default=None,
                        help="Parallel worker processes for backtest phase (default: CPU count)")
    args = parser.parse_args()
    if args.timeframe:
        config._data["candle_timeframe"] = args.timeframe

    from_dt = datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt = datetime.strptime(args.to_date, "%Y-%m-%d").replace(hour=23, minute=59)
    period_str = f"{from_dt.date()} to {to_dt.date()}"

    kite = create_kite()
    store = Store(config.db_path)
    params = config.strategy_config("lr_extrema")
    warmup_bars = params.get("warmup_bars", 200)

    print("Fetching ASM/ESM surveillance list from NSE...", flush=True)
    surveillance_symbols = _fetch_surveillance_symbols()
    print(f"Surveillance stocks to exclude: {len(surveillance_symbols)}\n", flush=True)

    all_instruments = kite.instruments("NSE")
    eq_instruments = [
        i for i in all_instruments
        if (
            i["instrument_type"] == "EQ"
            and i["segment"] == "NSE"      # excludes BE (trade-to-trade), BZ (Z-cat), SM (SME)
            and i["lot_size"] == 1
            and i["tradingsymbol"].replace("&", "").replace("-", "").isalpha()  # skip bonds/structured products
            and not i["tradingsymbol"].endswith(("-BE", "-BZ", "-SM"))  # skip T2T/Z-cat/SME suffix variants
            and i["tradingsymbol"] not in surveillance_symbols  # skip ASM/ESM stocks
        )
    ]
    symbol_to_token = {f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in eq_instruments}
    all_symbols = sorted(symbol_to_token.keys())

    already_done = _load_processed_symbols(args.output)
    remaining = [s for s in all_symbols if s not in already_done]
    total = len(all_symbols)
    width = len(str(total))

    print(f"\nNSE Screener | {period_str} | lr_extrema params from config")
    print(f"Total EQ instruments : {len(all_instruments)}")
    print(f"After quality filter : {total}  (excl. BE/BZ/SME, bonds, ASM/ESM)")
    print(f"Already processed    : {len(already_done)}")
    print(f"Remaining            : {len(remaining)}")
    print(f"Output file          : {args.output}")
    print(f"Workers              : {args.workers or 'CPU count'}\n")

    # ── Phase 1: fetch candles (sequential, rate-limited) ────────────────────
    print("=== Phase 1: Fetching candles ===")
    valid_symbols = []  # symbols with enough data for backtest
    idx_offset = len(already_done)

    for idx, symbol in enumerate(remaining, 1):
        token = symbol_to_token[symbol]
        display_idx = idx + idx_offset
        print(f"[{display_idx:{width}}/{total}] {symbol:<20}", end="  ", flush=True)

        try:
            df = get_candles(kite, store, token, symbol, config.candle_timeframe, from_dt, to_dt)
        except Exception as e:
            print(f"SKIP (data error: {e})")
            time.sleep(0.35)
            continue

        if df.empty or len(df) < warmup_bars:
            print(f"SKIP ({len(df)} candles, need {warmup_bars})")
            _append_to_csv(args.output, symbol,
                           {"total_trades": 0, "wins": 0, "money_weighted_win_rate": 0.0,
                            "total_pnl": 0.0, "return_pct": 0.0, "sharpe_proxy": 0.0},
                           from_dt, to_dt)
            time.sleep(0.35)
            continue

        # Quality gate 1: price >= ₹20 (filters out penny/micro-cap junk)
        last_close = df["close"].iloc[-1]
        if last_close < 20.0:
            print(f"SKIP (price ₹{last_close:.1f} < ₹20)")
            _append_to_csv(args.output, symbol,
                           {"total_trades": 0, "wins": 0, "money_weighted_win_rate": 0.0,
                            "total_pnl": 0.0, "return_pct": 0.0, "sharpe_proxy": 0.0},
                           from_dt, to_dt)
            time.sleep(0.35)
            continue

        # Quality gate 2: avg daily turnover >= ₹50L
        # 15-min candles: ~25 candles/day; turnover = volume × close
        avg_candle_turnover = (df["volume"] * df["close"]).mean()
        candles_per_day = {"5minute": 75, "15minute": 25, "30minute": 13, "60minute": 7, "day": 1}.get(
            config.candle_timeframe, 25
        )
        avg_daily_turnover = avg_candle_turnover * candles_per_day
        if avg_daily_turnover < 5_000_000:  # ₹50L
            print(f"SKIP (avg daily turnover ₹{avg_daily_turnover/1e5:.1f}L < ₹50L)")
            _append_to_csv(args.output, symbol,
                           {"total_trades": 0, "wins": 0, "money_weighted_win_rate": 0.0,
                            "total_pnl": 0.0, "return_pct": 0.0, "sharpe_proxy": 0.0},
                           from_dt, to_dt)
            time.sleep(0.35)
            continue

        print(f"OK ({len(df)} candles, ₹{avg_daily_turnover/1e5:.0f}L/day)")
        valid_symbols.append(symbol)
        time.sleep(0.35)

    print(f"\n=== Phase 1 done: {len(valid_symbols)} stocks ready for backtest ===\n")

    # ── Phase 2: run backtests in parallel ───────────────────────────────────
    print("=== Phase 2: Running backtests in parallel ===")
    jobs = [
        (sym, symbol_to_token[sym], params, symbol_to_token,
         from_dt, to_dt, config.db_path, config.total_capital, args.timeframe)
        for sym in valid_symbols
    ]

    in_session_results = []
    completed = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_run_single, job): job[0] for job in jobs}
        for future in as_completed(futures):
            symbol = futures[future]
            completed += 1
            result = future.result()
            if result is None:
                print(f"  [{completed}/{len(jobs)}] {symbol:<20}  ERROR")
                continue

            metrics = {k: v for k, v in result.items() if k != "symbol"}
            _append_to_csv(args.output, symbol, metrics, from_dt, to_dt)
            in_session_results.append({"instrument": symbol, **metrics})

            if metrics["total_trades"] == 0:
                print(f"  [{completed}/{len(jobs)}] {symbol:<20}  0 trades")
            else:
                print(
                    f"  [{completed}/{len(jobs)}] {symbol:<20}  "
                    f"Trades={metrics['total_trades']}  "
                    f"Wt.Win={metrics['money_weighted_win_rate']:.0f}%  "
                    f"Return={metrics['return_pct']:.2f}%"
                )

    print(f"\nDone. Results written to {args.output}")
    _print_final_table(in_session_results, args.min_trades)


if __name__ == "__main__":
    main()
