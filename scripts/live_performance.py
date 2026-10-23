"""
live_performance.py — Compare live (EC2) trade performance vs backtest expectations.

Fetches the live SQLite DB from EC2 via SSH, reconstructs matched trade pairs from
the orders table, then runs a backtest on the same period to produce a side-by-side
comparison per stock.

Usage:
    python scripts/live_performance.py [--skip-refresh] [--days N]

Flags:
    --skip-refresh   Skip kite_totp_refresh (use existing token)
    --days N         Restrict live trades to the last N calendar days (default: all)

Output: JSON to stdout with per-stock live vs backtest metrics and divergence flags.
"""

import argparse
import datetime
import json
import sqlite3
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.backtest.engine import compute_metrics, run_backtest
from trader.core.config import config
from trader.costs import round_trip_cost
from trader.data.store import Store
from trader.notifications import telegram
telegram.disable()

_SSH_ALIAS   = "trader"
_REMOTE_DB   = "/opt/trader/data/market.db"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _refresh_token():
    print("Refreshing Kite token...", file=sys.stderr)
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "kite_totp_refresh.py")],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Token refresh failed:\n{result.stderr}")
    print("Token refreshed.", file=sys.stderr)


def _fetch_remote_db() -> Path:
    """Stream the remote DB to a local temp file via SSH and return its path."""
    print("Fetching live DB from EC2...", file=sys.stderr)
    tmp = Path(tempfile.mktemp(suffix=".db"))
    result = subprocess.run(
        ["ssh", _SSH_ALIAS, f"sudo cat {_REMOTE_DB}"],
        capture_output=True, timeout=300,
    )
    if result.returncode != 0:
        err = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"SSH fetch failed: {err}")
    tmp.write_bytes(result.stdout)
    print(f"DB fetched ({len(result.stdout) // 1024} KB).", file=sys.stderr)
    return tmp


def _parse_live_trades(db_path: Path, since: datetime.datetime | None) -> list[dict]:
    """
    Read COMPLETE live orders, reconstruct FIFO entry/exit pairs, apply costs.
    Returns a list of trade dicts compatible with backtest trade records.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = conn.execute(
        """
        SELECT instrument, direction, quantity, price, updated_at
        FROM   orders
        WHERE  status = 'COMPLETE' AND mode = 'live'
          AND  price IS NOT NULL AND price > 0
        ORDER  BY updated_at ASC
        """
    ).fetchall()
    conn.close()

    open_buys: dict[str, list[dict]] = defaultdict(list)
    pairs: list[dict] = []

    for inst, direction, qty, price, ts in rows:
        ts_dt = datetime.datetime.fromisoformat(ts)
        if direction == "BUY":
            open_buys[inst].append({
                "instrument": inst,
                "entry":      price,
                "qty":        qty,
                "entry_date": ts_dt,
            })
        elif direction == "SELL" and open_buys[inst]:
            buy = open_buys[inst].pop(0)
            exit_date = ts_dt
            gross = (price - buy["entry"]) * buy["qty"]
            # Detect same-day (MIS) vs multi-day (CNC) for cost calc
            product = (
                "MIS" if buy["entry_date"].date() == exit_date.date() else "CNC"
            )
            cost = round_trip_cost(
                product=product,
                quantity=buy["qty"],
                entry_price=buy["entry"],
                exit_price=price,
            )
            net = gross - cost
            pairs.append({
                "instrument": inst,
                "entry":      buy["entry"],
                "exit":       price,
                "qty":        buy["qty"],
                "pnl":        round(net, 2),
                "cost":       round(cost, 2),
                "product":    product,
                "entry_date": buy["entry_date"],
                "exit_date":  exit_date,
            })

    # Optionally restrict to recent window
    if since:
        pairs = [p for p in pairs if p["exit_date"] >= since]

    return pairs


def _stock_metrics(trades: list) -> dict:
    if not trades:
        return {"pnl": 0.0, "trades": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0}
    wins   = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    return {
        "pnl":      round(sum(t["pnl"] for t in trades), 2),
        "trades":   len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "avg_win":  round(sum(wins)   / len(wins),   2) if wins   else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
    }


def _divergence_flag(live: dict, bt: dict) -> str:
    """
    Return a severity flag based on how far live performance diverges from backtest.
      RED    — critically underperforming (likely remove/calibrate)
      AMBER  — noticeably underperforming (watch)
      GREEN  — in line with or beating backtest
      SPARSE — fewer than 5 live trades (insufficient data)
    """
    if live["trades"] < 5:
        return "SPARSE"
    wr_gap = bt["win_rate"] - live["win_rate"]  # positive = live worse
    if live["pnl"] < -3000 or (wr_gap > 20 and live["pnl"] < 0):
        return "RED"
    if wr_gap > 12 or live["pnl"] < -500:
        return "AMBER"
    return "GREEN"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--days", type=int, default=None,
                        help="Restrict live trades to last N calendar days")
    args = parser.parse_args()

    if not args.skip_refresh:
        _refresh_token()

    # 1. Fetch and parse live trades
    db_path = _fetch_remote_db()
    since = (
        datetime.datetime.now() - datetime.timedelta(days=args.days)
        if args.days else None
    )
    live_trades = _parse_live_trades(db_path, since)
    db_path.unlink(missing_ok=True)

    if not live_trades:
        print(json.dumps({"error": "No completed live trades found.", "stocks": {}}))
        return

    # Determine date range of live trades for the backtest window
    bt_from = min(t["entry_date"] for t in live_trades).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    bt_to = datetime.datetime.now()

    # Symbols with live trades
    live_symbols = sorted({t["instrument"] for t in live_trades})
    live_by_sym: dict[str, list] = defaultdict(list)
    for t in live_trades:
        live_by_sym[t["instrument"]].append(t)

    # 2. Run backtest over same window (cache-only — candles already present)
    from trader.auth.session import create_kite
    kite  = create_kite()
    store = Store(config.db_path)

    # Clear stale test data without touching candles
    with store._conn() as conn:
        conn.executescript("DELETE FROM orders; DELETE FROM trades; DELETE FROM signals;")

    instruments   = kite.instruments("NSE")
    sym_to_tok    = {f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments}
    valid_symbols = [s for s in live_symbols if s in sym_to_tok]

    print(f"Running backtest for {len(valid_symbols)} symbols ({bt_from.date()} → {bt_to.date()})…",
          file=sys.stderr)

    _overrides = config._data.get("per_stock_params") or {}
    per_symbol_params = {
        sym: config.get_strategy_params(sym, "lr_extrema")
        for sym in valid_symbols if _overrides.get(sym, {}).get("lr_extrema")
    } or None

    bt_trades = run_backtest(
        None, store, valid_symbols, sym_to_tok,
        config.strategy_config("lr_extrema"),
        bt_from, bt_to,
        per_symbol_params=per_symbol_params,
    )
    bt_by_sym: dict[str, list] = defaultdict(list)
    for t in bt_trades:
        bt_by_sym[t["instrument"]].append(t)

    # 3. Build per-stock comparison
    stocks = {}
    for sym in live_symbols:
        live_m = _stock_metrics(live_by_sym[sym])
        bt_m   = _stock_metrics(bt_by_sym.get(sym, []))
        flag   = _divergence_flag(live_m, bt_m)

        # Expected P&L: backtest avg P&L per trade × number of live trades taken
        expected_pnl = (
            round(bt_m["pnl"] / bt_m["trades"] * live_m["trades"], 2)
            if bt_m["trades"] > 0 and live_m["trades"] > 0
            else 0.0
        )

        stocks[sym] = {
            "live":         live_m,
            "backtest":     bt_m,
            "expected_pnl": expected_pnl,
            "pnl_gap":      round(live_m["pnl"] - expected_pnl, 2),
            "wr_gap":       round(bt_m["win_rate"] - live_m["win_rate"], 1),
            "flag":         flag,
        }

    # Portfolio-level live summary
    total_live_pnl    = sum(m["live"]["pnl"]    for m in stocks.values())
    total_live_trades = sum(m["live"]["trades"]  for m in stocks.values())
    live_wins = sum(
        1 for trades in live_by_sym.values() for t in trades if t["pnl"] > 0
    )
    portfolio_live_wr = (
        round(live_wins / total_live_trades * 100, 1) if total_live_trades else 0.0
    )

    result = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "live_from":    min(t["entry_date"] for t in live_trades).date().isoformat(),
        "live_to":      max(t["exit_date"]  for t in live_trades).date().isoformat(),
        "backtest_window": f"{bt_from.date()} → {bt_to.date()}",
        "portfolio": {
            "live_pnl":    round(total_live_pnl, 2),
            "live_trades": total_live_trades,
            "live_wr":     portfolio_live_wr,
        },
        "stocks": stocks,
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
