"""
Backtest runner — replays historical candles through the same pipeline as main.py.

    python scripts/backtest.py --from 2025-01-01
    python scripts/backtest.py --from 2025-01-01 --to 2025-12-31

Uses the same RiskManager, OrderManager (paper mode), and Strategy instances as live.
The only backtest-specific addition is SL simulation: checks candle low against the
stop-loss price placed with each order.
"""

import argparse
import bisect
import csv
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.auth.session import create_kite
from trader.backtest.engine import compute_metrics, run_backtest
from trader.core.config import config
from trader.core.logger import get_logger, setup
from trader.data.store import Store
from trader.notifications import telegram
telegram.disable()

setup(log_dir=config.log_dir, level="ERROR")
logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Backtest strategies on historical data")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--timeframe", default=None,
                        choices=["minute", "5minute", "15minute", "30minute", "60minute", "day"],
                        help="Candle timeframe (default: from config)")
    parser.add_argument("--cache-only", action="store_true",
                        help="Skip Kite authentication and use only locally cached candle data")
    parser.add_argument("--config", dest="config_path", default=None,
                        help="Path to alternate config.yaml (default: config/config.yaml)")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Override watchlist e.g. NSE:RELIANCE NSE:TCS")
    args = parser.parse_args()

    if args.config_path:
        config.reload(Path(__file__).resolve().parents[1] / args.config_path)

    if args.timeframe:
        config._data["candle_timeframe"] = args.timeframe

    from_dt = datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt = datetime.strptime(args.to_date, "%Y-%m-%d").replace(hour=23, minute=59)

    store = Store(config.db_path)
    if not args.cache_only:
        store.clear_backtest_data()

    if args.cache_only:
        kite = None
        valid_watchlist = args.symbols or list(config.watchlist)
        symbol_to_token = {s: 0 for s in valid_watchlist}
        logger.info("Cache-only mode — skipping Kite authentication")
    else:
        kite = create_kite()
        instruments = kite.instruments("NSE")
        symbol_to_token = {
            f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments
        }
        watchlist = args.symbols or list(config.watchlist)
        valid_watchlist = [s for s in watchlist if s in symbol_to_token]

    if not valid_watchlist:
        print("No valid instruments in watchlist.")
        return

    logger.info("Backtest | %s to %s | instruments=%s", args.from_date, args.to_date, valid_watchlist)

    params = config.strategy_config("lr_extrema")
    _stock_overrides = (config._data.get("per_stock_params") or {})
    per_symbol_params = {
        sym: config.get_strategy_params(sym, "lr_extrema")
        for sym in valid_watchlist
        if _stock_overrides.get(sym, {}).get("lr_extrema")
    } or None

    def _progress(date, pct):
        print(f"\r  Progress: {date}  [{pct*100:5.1f}%]", end="", flush=True)

    t0 = time.perf_counter()
    trades = run_backtest(kite, store, valid_watchlist, symbol_to_token, params, from_dt, to_dt,
                          progress_callback=_progress, per_symbol_params=per_symbol_params)
    print()  # newline after progress line
    elapsed = time.perf_counter() - t0
    _print_summary(trades, args.from_date, args.to_date)
    _dump_csv(trades, args.from_date, args.to_date)
    print(f"  Elapsed    : {elapsed:.2f}s")
    print(f"  Params     : {', '.join(f'{k}={v}' for k, v in params.items())}")


def _print_summary(trades: list[dict], from_date: str, to_date: str):
    W = 62
    print(f"\n{'='*W}")
    print(f"  Backtest: {from_date}  →  {to_date}")
    print(f"{'='*W}")

    if not trades:
        print("  No trades executed.")
        print(f"{'='*W}\n")
        return

    m = compute_metrics(trades, config.total_capital)
    total_costs = sum(t.get("cost", 0.0) for t in trades)

    # Effective capital at entry of each trade
    sorted_for_capital = sorted(trades, key=lambda t: t.get("entry_date") or "")
    running_pnl = 0.0
    capital_at_entry: dict[int, float] = {}
    for t in sorted_for_capital:
        capital_at_entry[id(t)] = config.total_capital + running_pnl
        running_pnl += t["pnl"]

    print(f"\n  {'Entry Date':<19} {'Exit Date':<19} {'Days':>4} {'Bars':>5} {'Instrument':<15} {'Entry':>8} {'Exit':>8} {'Qty':>5} {'Cost':>8} {'Net P&L':>10} {'P&L%':>7} {'Capital':>10}  Prod  Reason")
    print(f"  {'-'*19} {'-'*19} {'-'*4} {'-'*5} {'-'*15} {'-'*8} {'-'*8} {'-'*5} {'-'*8} {'-'*10} {'-'*7} {'-'*10}  ----  ------")
    for t in trades:
        entry_date_str = str(t["entry_date"])[:19] if t["entry_date"] else "—"
        exit_date_str  = str(t["exit_date"])[:19]
        if t["entry_date"] and t["exit_date"]:
            entry_dt = t["entry_date"] if isinstance(t["entry_date"], datetime) else datetime.fromisoformat(str(t["entry_date"])[:19])
            exit_dt  = t["exit_date"]  if isinstance(t["exit_date"],  datetime) else datetime.fromisoformat(str(t["exit_date"])[:19])
            hold_str = str((exit_dt - entry_dt).days)
        else:
            hold_str = "—"
        bars_str = str(t.get("held_candles", "—"))
        invested = t["entry"] * t["qty"]
        pnl_pct_str = f"{t['pnl'] / invested * 100:+.2f}%" if invested else "—"
        cap_str = f"₹{capital_at_entry[id(t)]:,.0f}"
        print(
            f"  {entry_date_str:<19} {exit_date_str:<19} {hold_str:>4} {bars_str:>5} {t['instrument']:<15} "
            f"{t['entry']:>8.2f} {t['exit']:>8.2f} {t['qty']:>5} "
            f"₹{t.get('cost', 0.0):>7,.2f} ₹{t['pnl']:>9,.2f} {pnl_pct_str:>7} {cap_str:>10}  "
            f"{t.get('product','CNC'):<4}  {t['reason']}"
        )

    # ANSI style definitions
    _G = "\033[92m"       # bright green
    _R = "\033[91m"       # bright red
    _RESET = "\033[0m"    # reset color

    mr = m.get("monthly_returns", {})
    if mr:
        from collections import defaultdict
        yr_stats = defaultdict(lambda: {"pnl": 0.0, "trades": 0})
        for month_str, data in mr.items():
            yr = month_str.split("-")[0] if "-" in month_str else "Total"
            yr_stats[yr]["pnl"] += data["pnl"]
            yr_stats[yr]["trades"] += data["trades"]

        print(f"  {'─'*115}")
        print(f"  {'Monthly P&L Distribution':<54} │  Yearly Breakdown")
        print(f"  {'─'*54} ┼ {'─'*58}")
        
        m_keys = sorted(mr.keys())
        y_keys = sorted(yr_stats.keys())
        max_lines = max(len(m_keys), len(y_keys))
        
        max_m_pnl = max(abs(v['pnl']) for v in mr.values()) if mr else 1
        max_y_pnl = max(abs(v['pnl']) for v in yr_stats.values()) if yr_stats else 1

        for i in range(max_lines):
            # 1. Process Monthly (Left side)
            if i < len(m_keys):
                m_key = m_keys[i]
                m_data = mr[m_key]
                m_color = _G if m_data['pnl'] >= 0 else _R
                m_sign = "+" if m_data['pnl'] >= 0 else "-"
                m_bar_char = "█" if m_data['pnl'] >= 0 else "░"
                m_bar_width = int(abs(m_data['pnl']) / max_m_pnl * 15)
                m_bar = m_bar_char * m_bar_width
                
                # Construct data string segment without color escape noise for proper padding width math
                text_part = f"    {m_key}  {m_sign}₹{abs(m_data['pnl']):>8,.0f}  ({m_data['return_pct']:+.2f}%)"
                colored_text = f"    {m_key}  {m_color}{m_sign}₹{abs(m_data['pnl']):>8,.0f}  ({m_data['return_pct']:+.2f}%){_RESET}"
                
                # Fill space out evenly between metric values text and visual bars
                space_fill = " " * (35 - len(text_part))
                bar_part = f"{m_color}{m_bar:<15}{_RESET}  [{m_data['trades']:>2}t]"
                left_side = f"{colored_text}{space_fill}{bar_part}"
            else:
                left_side = f"{'':<54}"

            # 2. Process Yearly (Right side)
            if i < len(y_keys):
                y_key = y_keys[i]
                y_data = yr_stats[y_key]
                y_color = _G if y_data['pnl'] >= 0 else _R
                y_sign = "+" if y_data['pnl'] >= 0 else "-"
                y_bar_char = "█" if y_data['pnl'] >= 0 else "░"
                y_bar_width = int(abs(y_data['pnl']) / max_y_pnl * 12)
                y_bar = y_bar_char * y_bar_width
                y_ret_pct = (y_data['pnl'] / config.total_capital) * 100
                
                y_text_part = f"  {y_key}: {y_sign}₹{abs(y_data['pnl']):>9,.0f} ({y_ret_pct:+.2f}%)"
                y_colored_text = f"  {y_key}: {y_color}{y_sign}₹{abs(y_data['pnl']):>9,.0f}{_RESET} ({y_color}{y_ret_pct:+.2f}%{_RESET})"
                
                y_space_fill = " " * (34 - len(y_text_part))
                y_bar_part = f"{y_color}{y_bar:<12}{_RESET} [{y_data['trades']:>3}t]"
                right_side = f" │{y_colored_text}{y_space_fill}{y_bar_part}"
            else:
                right_side = ""

            print(f"{left_side}{right_side}")
        print(f"  {'─'*115}")

    C = 28  # width of each column (excluding separator)
    col1 = [
        f"{'Trades':<12}: {m['total_trades']}",
        f"{'W / L':<12}: {m['wins']} / {m['losses']}",
        f"{'Win Rate':<12}: {m['win_rate']:.1f}%",
        f"{'Wt. Win%':<12}: {m['money_weighted_win_rate']:.1f}%",
        f"{'Avg Win':<12}: ₹{m['avg_win']:,.2f}",
        f"{'Avg Loss':<12}: ₹{m['avg_loss']:,.2f}",
        f"{'Prof.Factor':<12}: {m['profit_factor']:.2f}",
    ]
    col2 = [
        f"{'Total costs':<12}: ₹{total_costs:,.2f}",
        f"{'Total P&L':<12}: ₹{m['total_pnl']:,.2f}",
        f"{'Return':<12}: {m['return_pct']:.2f}%",
        # f"{'Ann. Return':<12}: {m['annualized_return_pct']:.2f}%",
        f"{'Max DD':<12}: ₹{m['max_drawdown']:,.0f}  ({m['max_drawdown_pct']:.1f}%)",
    ]
    col3 = [
        f"{'Sharpe*':<8}: {m['sharpe_proxy']:.3f}",
        f"{'Sortino':<8}: {m['sortino_ratio']:.3f}",
        f"{'Calmar':<8}: {m['calmar_ratio']:.3f}",
    ]
    n = max(len(col1), len(col2), len(col3))
    col1 += [""] * (n - len(col1))
    col2 += [""] * (n - len(col2))
    col3 += [""] * (n - len(col3))

    print(f"\n  {'─'*(C*3+6)}")
    for a, b, c in zip(col1, col2, col3):
        print(f"  {a:<{C}}  │  {b:<{C}}  │  {c}")

    from collections import defaultdict
    reason_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "pnl": 0.0, "wins": 0, "held": 0})
    for t in trades:
        r = t.get("reason", "UNKNOWN")
        reason_stats[r]["count"] += 1
        reason_stats[r]["pnl"] += t["pnl"]
        reason_stats[r]["held"] += t.get("held_candles", 0)
        if t["pnl"] > 0:
            reason_stats[r]["wins"] += 1
    print(f"  {'─'*W}")
    print(f"  Exit reasons:                              avg_bars")
    max_count = max(s["count"] for s in reason_stats.values()) if reason_stats else 1
    for reason in ["SL", "TRAILING", "STALE", "STAGNATION", "MODEL_EXIT", "PATTERN_TOP", "TARGET", "STRATEGY", "OPEN@END"]:
        if reason not in reason_stats:
            continue
        s = reason_stats[reason]
        bar = "█" * int(s["count"] / max_count * 20)
        wr = s["wins"] / s["count"] * 100
        avg_bars = s["held"] / s["count"]
        print(f"    {reason:<12} {s['count']:>3}t  wr:{wr:4.0f}%  ₹{s['pnl']:>9,.0f}  {bar:<20}  {avg_bars:>5.0f}b")

    # Per-stock exit breakdown — one line per instrument
    _REASON_ABBREV = {
        "SL": "SL", "TRAILING": "TRL", "TRAILING_EOD_CLOSE": "EOD",
        "PATTERN_TOP": "PAT", "STRATEGY": "STR", "TARGET": "TGT",
        "OPEN@END": "END", "STAGNATION": "STG", "MODEL_EXIT": "MOD",
        "TIME_DECAY": "DCY", "INTRADAY_CLOSE": "IDC", "STALE": "STL",
    }
    _REASON_COLOUR = {
        "SL":                "\033[91m",   # bright red
        "TRAILING":          "\033[93m",   # yellow
        "TRAILING_EOD_CLOSE":"\033[92m",   # green
        "PATTERN_TOP":       "\033[96m",   # cyan
        "MODEL_EXIT":        "\033[94m",   # blue
        "TARGET":            "\033[92m",   # green
        "STAGNATION":        "\033[33m",   # dark yellow
        "STALE":             "\033[33m",   # dark yellow
        "TIME_DECAY":        "\033[35m",   # magenta
        "INTRADAY_CLOSE":    "\033[95m",   # bright magenta
        "STRATEGY":          "\033[37m",   # white
        "OPEN@END":          "\033[90m",   # grey
    }

    def _fmt_pnl(v: float) -> str:
        colour = "\033[92m" if v >= 0 else "\033[91m"
        sign = "+" if v >= 0 else "-"
        amt = f"₹{abs(v)/1000:.1f}k" if abs(v) >= 1000 else f"₹{abs(v):.0f}"
        return f"{colour}{sign}{amt}{_RESET}"

    per_stock: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: {"count": 0, "pnl": 0.0}))
    for t in trades:
        per_stock[t["instrument"]][t.get("reason", "UNKNOWN")]["count"] += 1
        per_stock[t["instrument"]][t.get("reason", "UNKNOWN")]["pnl"] += t["pnl"]

    _REASON_ORDER = ["SL", "TRAILING", "TRAILING_EOD_CLOSE", "STALE", "STAGNATION", "TIME_DECAY",
                     "MODEL_EXIT", "PATTERN_TOP", "TARGET", "INTRADAY_CLOSE", "STRATEGY", "OPEN@END"]
    BAR_W = 24

    def _stacked_bar(reasons: dict, total: int) -> str:
        ordered = [r for r in _REASON_ORDER if r in reasons]
        ordered += sorted(set(reasons) - set(_REASON_ORDER))
        segments = []
        filled = 0
        for i, reason in enumerate(ordered):
            cnt = reasons[reason]["count"]
            width = (BAR_W - filled) if i == len(ordered) - 1 else int(cnt / total * BAR_W)
            if width > 0:
                colour = _REASON_COLOUR.get(reason, "")
                segments.append(f"{colour}{'█' * width}{_RESET}")
            filled += width
        return "".join(segments)

    print(f"  {'─'*W}")
    print(f"  Per-stock exits:")
    legend_parts = [f"{_REASON_COLOUR.get(r, '')}{_REASON_ABBREV.get(r, r[:3])}{'█'}{_RESET}" for r in _REASON_ORDER]
    print(f"    {'  '.join(legend_parts)}")
    print()
    for sym, reasons in sorted(per_stock.items()):
        total_t = sum(r["count"] for r in reasons.values())
        sym_short = sym.replace("NSE:", "")
        bar = _stacked_bar(reasons, total_t)
        stock_pnl = sum(r["pnl"] for r in reasons.values())
        pnl_str = _fmt_pnl(stock_pnl)
        print(f"    {sym_short:<16} {total_t:>3}t  {bar}  {pnl_str}")

    print(f"  {'='*W}\n")
    _print_utilisation_table(trades, config.total_capital)
    _print_capital_chart(trades, config.total_capital)


def _print_utilisation_table(trades: list[dict], total_capital: float):
    """Monthly capital-utilisation and open-position table — tells you whether
    capital/position caps are under-used (room to raise max_capital_per_stock_pct)."""
    from trader.backtest.engine import compute_utilisation
    u = compute_utilisation(trades, total_capital)
    rows = u["monthly"]
    if not rows:
        return
    o = u["overall"]
    max_pos = config.max_open_positions
    pct_cap = config._data.get("risk", {}).get("max_capital_per_stock_pct", "?")
    print(f"  Capital Utilisation & Open Positions  (capital ₹{total_capital:,.0f} · "
          f"max_capital_per_stock {pct_cap}% · max_open_positions {max_pos})")
    print(f"  {'month':<8} {'entries':>7} {'avgDep':>11} {'peakDep':>11} {'avgUtil':>8} {'peakUtil':>9} {'avgPos':>7} {'peakPos':>8}")
    print(f"  {'-'*8} {'-'*7} {'-'*11} {'-'*11} {'-'*8} {'-'*9} {'-'*7} {'-'*8}")
    for r in rows:
        print(f"  {r['month']:<8} {r['entries']:>7} {r['avg_deployed']:>11,.0f} "
              f"{r['peak_deployed']:>11,.0f} {r['avg_util_pct']:>7.1f}% {r['peak_util_pct']:>8.1f}% "
              f"{r['avg_positions']:>7.1f} {r['peak_positions']:>8d}")
    print(f"  {'─'*72}")
    print(f"  OVERALL  time-avg util {o['time_avg_util_pct']:.1f}%  ·  peak util {o['peak_util_pct']:.1f}%  ·  "
          f"peak deployed ₹{o['peak_deployed']:,.0f}  ·  avg pos {o['avg_positions']:.1f}  ·  "
          f"peak pos {o['peak_positions']}/{max_pos}")
    print()


def _build_step_series(trades: list[dict], value_fn, count_fn=None):
    """
    Build (xs, ys) step-function time series from trades.

    value_fn(trade) -> +delta on entry, will be negated on exit.
    If count_fn is provided, returns a second series for position count.
    """
    cap_events: list[tuple] = []
    cnt_events: list[tuple] = []
    for t in trades:
        if not t.get("entry_date") or not t.get("exit_date"):
            continue
        v = value_fn(t)
        cap_events.append((t["entry_date"],  v))
        cap_events.append((t["exit_date"],  -v))
        cnt_events.append((t["entry_date"],  1))
        cnt_events.append((t["exit_date"],  -1))

    def _collapse(events):
        events.sort(key=lambda e: e[0])
        xs, ys = [], []
        cur = 0.0
        for ts, delta in events:
            cur = max(0.0, cur + delta)
            if xs and xs[-1] == ts:
                ys[-1] = cur
            else:
                xs.append(ts)
                ys.append(cur)
        return xs, ys

    cap_xs, cap_ys = _collapse(cap_events)
    cnt_xs, cnt_ys = _collapse(cnt_events)
    return cap_xs, cap_ys, cnt_xs, cnt_ys


def _sample_step(xs: list, ys: list[float], span_sec: float, n: int) -> list[float]:
    """Sample a step-function series into n evenly-spaced columns."""
    result = []
    for col in range(n):
        frac = col / (n - 1)
        target = xs[0] + timedelta(seconds=span_sec * frac)
        idx = bisect.bisect_right(xs, target) - 1
        result.append(ys[idx] if idx >= 0 else 0.0)
    return result


def _draw_line_chart(col_vals: list[float], max_y: float,
                     chart_h: int, chart_w: int, char: str = '█', connector: str = '╎') -> list[list[str]]:
    grid = [[' '] * chart_w for _ in range(chart_h)]

    def _row(v):
        return chart_h - 1 - round(v / max_y * (chart_h - 1))

    rows = [_row(v) for v in col_vals]
    for col in range(chart_w):
        r = rows[col]
        if col > 0:
            r1, r2 = min(rows[col - 1], r), max(rows[col - 1], r)
            for rr in range(r1, r2 + 1):
                if grid[rr][col] == ' ':
                    grid[rr][col] = connector
        grid[r][col] = char
    return grid


def _print_capital_chart(trades: list[dict], total_capital: float):
    """ASCII line charts: capital deployed + open positions count, shared x-axis."""
    cap_xs, cap_ys, cnt_xs, cnt_ys = _build_step_series(
        trades, value_fn=lambda t: t["entry"] * t["qty"]
    )
    if not cap_xs:
        return

    CHART_W = 72
    CAP_H   = 10
    CNT_H   =  5
    Y_W     = 13

    span_sec = (cap_xs[-1] - cap_xs[0]).total_seconds()
    max_cap  = max(cap_ys)
    max_cnt  = max(cnt_ys) if cnt_ys else 1
    if max_cap == 0 or span_sec == 0:
        return

    cap_cols = _sample_step(cap_xs, cap_ys, span_sec, CHART_W)
    cnt_cols = _sample_step(cnt_xs, cnt_ys, span_sec, CHART_W) if cnt_xs else [0.0] * CHART_W

    cap_grid = _draw_line_chart(cap_cols, max_cap, CAP_H, CHART_W)
    cnt_grid = _draw_line_chart(cnt_cols, max_cnt, CNT_H, CHART_W, char='▪', connector='┊')

    # --- Capital chart ---
    print(f"  Capital Deployed Over Time")
    print(f"  (peak ₹{max_cap:,.0f}  ·  total capital ₹{total_capital:,.0f})")
    print()
    for r in range(CAP_H):
        row_val = max_cap * (CAP_H - 1 - r) / (CAP_H - 1)
        y_label = f"  ₹{row_val:>10,.0f} │" if r % 3 == 0 else f"{'':>{Y_W+2}} │"
        print(y_label + ''.join(cap_grid[r]))

    # --- Position count chart (shared x-axis separator) ---
    print(f"  {'':>{Y_W}} ├{'─' * CHART_W}")
    for r in range(CNT_H):
        row_val = max_cnt * (CNT_H - 1 - r) / (CNT_H - 1)
        if r == 0:
            y_label = f"  {'pos':>6} {int(row_val):>3}   │"
        elif r == CNT_H - 1:
            y_label = f"  {'pos':>6} {0:>3}   │"
        else:
            y_label = f"{'':>{Y_W+2}} │"
        print(y_label + ''.join(cnt_grid[r]))

    # --- Shared x-axis ---
    print(f"  {'':>{Y_W}} └{'─' * CHART_W}")
    n_labels = 6
    date_line = f"  {'':>{Y_W+1}}"
    prev_end = 0
    for i in range(n_labels):
        frac = i / (n_labels - 1)
        col  = int(frac * (CHART_W - 1))
        lbl  = (cap_xs[0] + timedelta(seconds=span_sec * frac)).strftime("%b'%y")
        spaces = max(1, col - prev_end)
        date_line += " " * spaces + lbl
        prev_end = col + len(lbl)
    print(date_line)
    print()


def _dump_csv(trades: list[dict], from_date: str, to_date: str):
    if not trades:
        return
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    from_str = from_date.replace("-", "")
    to_str = to_date.replace("-", "")
    timeframe = config.candle_timeframe.replace("minute", "m").replace("day", "1d")
    filename = f"portfolio_{from_str}_{to_str}_{timeframe}_{now}.csv"
    out_path = Path(__file__).resolve().parents[1] / "backtest_results" / filename
    fields = ["instrument", "entry_date", "exit_date", "entry", "exit", "qty",
              "cost", "pnl", "product", "reason", "held_candles", "sl", "peak_high"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    print(f"  CSV saved : {out_path}")


if __name__ == "__main__":
    main()