"""
NSE stock screener — backtest LRExtremaStrategy against all NSE EQ instruments.

    python scripts/screen.py --from 2024-01-01
    python scripts/screen.py --from 2024-01-01 --to 2025-01-01 --min-trades 2 --output results.csv

Processes stocks one at a time. Resumes from where it left off if interrupted —
already-processed symbols are read from the output CSV and skipped.

Rate-limited to ~3 req/sec to stay within Kite API limits (~12 min for 2000 stocks).
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.auth.session import create_kite
from trader.backtest.engine import compute_metrics, run_backtest
from trader.core.config import config
from trader.core.logger import get_logger, setup
from trader.data.historical import get_candles
from trader.data.store import Store

setup(log_dir=config.log_dir, level="WARNING")  # suppress info noise during scan
logger = get_logger(__name__)

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
            "win_rate": f"{metrics['win_rate']:.1f}",
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
                f"  {r['instrument']:<18}  {r['total_trades']:>6}  {r['win_rate']:>4.0f}%  "
                f"₹{r['total_pnl']:>11,.0f}  {r['return_pct']:>7.2f}%  {r['sharpe_proxy']:>8.3f}"
            )
    print(f"{'='*75}\n")


def main():
    parser = argparse.ArgumentParser(description="Screen all NSE EQ stocks with LRExtremaStrategy")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--min-trades", type=int, default=2,
                        help="Minimum trades to include in final table (default: 2)")
    parser.add_argument("--output", default="screen_results.csv",
                        help="Output CSV file path (default: screen_results.csv)")
    args = parser.parse_args()

    from_dt = datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt = datetime.strptime(args.to_date, "%Y-%m-%d").replace(hour=23, minute=59)
    period_str = f"{from_dt.date()} to {to_dt.date()}"

    kite = create_kite()
    store = Store(config.db_path)
    params = config.strategy_config("lr_extrema")
    warmup_bars = params.get("warmup_bars", 200)

    all_instruments = kite.instruments("NSE")
    # breakpoint()
    eq_instruments = [i for i in all_instruments if i["instrument_type"] == "EQ" and i["segment"] == "NSE" and i["lot_size"] == 1]
    symbol_to_token = {
        f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in eq_instruments
    }
    all_symbols = sorted(symbol_to_token.keys())

    already_done = _load_processed_symbols(args.output)
    remaining = [s for s in all_symbols if s not in already_done]
    total = len(all_symbols)

    print(f"\nNSE Screener | {period_str} | lr_extrema params from config")
    print(f"Total EQ instruments : {total}")
    print(f"Already processed    : {len(already_done)}")
    print(f"Remaining            : {len(remaining)}")
    print(f"Output file          : {args.output}\n")

    in_session_results = []
    idx_offset = len(already_done)

    for idx, symbol in enumerate(remaining, 1):
        token = symbol_to_token[symbol]
        display_idx = idx + idx_offset
        width = len(str(total))
        print(f"[{display_idx:{width}}/{total}] {symbol:<20}", end="  ", flush=True)

        # Fetch candles
        try:
            df = get_candles(kite, store, token, symbol, config.candle_timeframe, from_dt, to_dt)
        except Exception as e:
            print(f"SKIP (data error: {e})")
            logger.warning("Data fetch failed for %s: %s", symbol, e)
            time.sleep(0.35)
            continue

        if df.empty or len(df) < warmup_bars:
            print(f"SKIP (insufficient data: {len(df)} candles, need {warmup_bars})")
            # Write to CSV so we don't retry on resume
            _append_to_csv(args.output, symbol,
                           {"total_trades": 0, "wins": 0, "win_rate": 0.0,
                            "total_pnl": 0.0, "return_pct": 0.0, "sharpe_proxy": 0.0},
                           from_dt, to_dt)
            time.sleep(0.35)
            continue

        # Run backtest
        try:
            trades = run_backtest(kite, store, [symbol], symbol_to_token, params, from_dt, to_dt)
        except Exception as e:
            print(f"ERROR ({e})")
            logger.exception("Backtest failed for %s", symbol)
            time.sleep(0.35)
            continue  # not written to CSV — will be retried on next run

        metrics = compute_metrics(trades, config.total_capital)
        _append_to_csv(args.output, symbol, metrics, from_dt, to_dt)
        in_session_results.append({"instrument": symbol, **metrics})

        if metrics["total_trades"] == 0:
            print(f"0 trades")
        else:
            print(
                f"Trades={metrics['total_trades']}  Win={metrics['win_rate']:.0f}%  "
                f"Return={metrics['return_pct']:.2f}%"
            )

        time.sleep(0.35)

    print(f"\nDone. Results written to {args.output}")
    _print_final_table(in_session_results, args.min_trades)


if __name__ == "__main__":
    main()
