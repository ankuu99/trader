"""
Dashboard HTML renderer — pure Python, no template files, no external dependencies.

render_page() returns a complete HTML string. All CSS is inlined.
render_chart_page() returns a full-page SVG chart for a single instrument.
SQLite is queried directly (read-only connection) so the Store write path is untouched.
"""

import sqlite3
import time as _time
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))

_LOCAL_UTC_OFFSET_HRS = -_time.timezone / 3600
_IST_HRS = 5.5
_NAIVE_TO_IST_DELTA = timedelta(hours=_IST_HRS - _LOCAL_UTC_OFFSET_HRS)

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    background: #0d1117; color: #c9d1d9;
    font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
    font-size: 13px; padding: 16px;
}
h1 { font-size: 15px; color: #58a6ff; margin-bottom: 4px; }
.meta { color: #8b949e; font-size: 12px; margin-bottom: 16px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.card {
    background: #161b22; border: 1px solid #30363d;
    border-radius: 6px; padding: 12px;
}
.card h2 { font-size: 12px; color: #8b949e; text-transform: uppercase;
           letter-spacing: 0.05em; margin-bottom: 8px; }
.val { font-size: 14px; color: #e6edf3; }
.green { color: #3fb950; }
.red { color: #f85149; }
.orange { color: #d29922; }
.dim { color: #8b949e; }
.full { grid-column: 1 / -1; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; color: #8b949e; font-weight: normal;
     font-size: 11px; padding: 3px 8px 3px 0; border-bottom: 1px solid #21262d; }
td { padding: 4px 8px 4px 0; border-bottom: 1px solid #161b22; vertical-align: middle; }
tr:last-child td { border-bottom: none; }
.badge {
    display: inline-block; padding: 1px 6px; border-radius: 3px;
    font-size: 11px; font-weight: bold;
}
.badge-green { background: #0d2116; color: #3fb950; border: 1px solid #1a4a2a; }
.badge-red   { background: #2d0f0f; color: #f85149; border: 1px solid #5a1a1a; }
.badge-orange{ background: #2d1f00; color: #d29922; border: 1px solid #5a3d00; }
.badge-dim   { background: #1c2128; color: #8b949e; border: 1px solid #30363d; }
.tag { display: inline-block; background: #1c2128; border: 1px solid #30363d;
       border-radius: 3px; padding: 1px 5px; margin: 2px; font-size: 11px; }
.bar-bg { background: #21262d; border-radius: 3px; height: 6px; margin-top: 4px; }
.bar-fill { background: #1f6feb; border-radius: 3px; height: 6px; }
.bar-fill.danger { background: #f85149; }
a.chart-link { color: #58a6ff; text-decoration: none; font-size: 11px; }
a.chart-link:hover { text-decoration: underline; }
"""


def _now_ist() -> datetime:
    return datetime.now(_IST)


def _fmt_ist(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt + _NAIVE_TO_IST_DELTA
    else:
        dt = dt.astimezone(_IST)
    return dt.strftime("%d %b %H:%M:%S")


def _market_status(now: datetime) -> str:
    t = now.time()
    from datetime import time as dtime
    if dtime(9, 15) <= t <= dtime(15, 30):
        return "OPEN"
    return "CLOSED"


def _pnl_class(val: float) -> str:
    if val > 0:
        return "green"
    if val < 0:
        return "red"
    return "dim"


def _badge(text: str, kind: str) -> str:
    return f'<span class="badge badge-{kind}">{text}</span>'


def _read_db(db_path, query: str, params: tuple = ()) -> list[dict]:
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _hold_duration(entry_time_str: str, exit_time_str: str) -> str:
    try:
        entry_dt = datetime.fromisoformat(entry_time_str)
        exit_dt = datetime.fromisoformat(exit_time_str)
        total_hours = int((exit_dt - entry_dt).total_seconds() / 3600)
        days, hours = divmod(total_hours, 24)
        return f"{days}d {hours}h" if days > 0 else f"{hours}h"
    except Exception:
        return "—"


def _find_candle_idx(order_ts: str, timestamps: list[str]) -> int:
    """Last candle index whose start time is <= order_ts (the candle that owns this moment)."""
    target = order_ts[:16]
    result = 0
    for i, ts in enumerate(timestamps):
        if ts[:16] <= target:
            result = i
        else:
            break
    return result


def _render_watchlist_sparkline(
    closes: list[float],
    buy_markers: list,
    sell_markers: list,
    open_entry: float | None = None,
    width: int = 180,
    height: int = 50,
) -> str:
    if len(closes) < 2:
        return "<span class='dim'>—</span>"
    n = len(closes)
    pad = 4
    all_prices = list(closes)
    if open_entry:
        all_prices.append(open_entry)
    for _, p in buy_markers:
        all_prices.append(p)
    for _, p in sell_markers:
        all_prices.append(p)
    lo = min(all_prices) * 0.997
    hi = max(all_prices) * 1.003
    rng = hi - lo or 1.0

    def sx(i: int) -> float:
        return pad + (i / (n - 1)) * (width - 2 * pad)

    def sy(price: float) -> float:
        return pad + (1 - (price - lo) / rng) * (height - 2 * pad)

    last = closes[-1]
    color = "#3fb950" if (open_entry is None or last >= open_entry) else "#f85149"
    pts = " ".join(f"{sx(i):.1f},{sy(c):.1f}" for i, c in enumerate(closes))

    parts = [
        f'<svg width="{width}" height="{height}" '
        f'style="vertical-align:middle;display:inline-block;background:#161b22;border-radius:3px">',
    ]
    if open_entry:
        ey = max(pad, min(height - pad, sy(open_entry)))
        parts.append(
            f'<line x1="{pad}" y1="{ey:.1f}" x2="{width - pad}" y2="{ey:.1f}" '
            f'stroke="#3fb950" stroke-width="0.8" stroke-dasharray="2,2" opacity="0.5"/>'
        )
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.2"/>')
    for idx, price in buy_markers:
        if 0 <= idx < n:
            x, y = sx(idx), min(height - 6, sy(price) + 9)
            parts.append(
                f'<polygon points="{x:.1f},{y - 5:.1f} {x - 4:.1f},{y:.1f} {x + 4:.1f},{y:.1f}" '
                f'fill="#3fb950" opacity="0.9"/>'
            )
    for idx, price in sell_markers:
        if 0 <= idx < n:
            x, y = sx(idx), max(6, sy(price) - 9)
            parts.append(
                f'<polygon points="{x:.1f},{y + 5:.1f} {x - 4:.1f},{y:.1f} {x + 4:.1f},{y:.1f}" '
                f'fill="#f85149" opacity="0.9"/>'
            )
    parts.append(f'<circle cx="{sx(n - 1):.1f}" cy="{sy(last):.1f}" r="2" fill="{color}"/>')
    parts.append('</svg>')
    return "".join(parts)


def _render_sparkline(closes: list[float], entry_price: float,
                      width: int = 160, height: int = 45) -> str:
    if len(closes) < 2:
        return "<span class='dim'>—</span>"
    lo = min(min(closes), entry_price) * 0.998
    hi = max(max(closes), entry_price) * 1.002
    rng = hi - lo or 1.0
    pad = 4

    def sx(i: int) -> float:
        return pad + (i / (len(closes) - 1)) * (width - 2 * pad)

    def sy(price: float) -> float:
        return pad + (1 - (price - lo) / rng) * (height - 2 * pad)

    pts = " ".join(f"{sx(i):.1f},{sy(c):.1f}" for i, c in enumerate(closes))
    entry_y = max(pad, min(height - pad, sy(entry_price)))
    last = closes[-1]
    color = "#3fb950" if last >= entry_price else "#f85149"

    return (
        f'<svg width="{width}" height="{height}" '
        f'style="vertical-align:middle;display:inline-block">'
        f'<line x1="{pad}" y1="{entry_y:.1f}" x2="{width - pad}" y2="{entry_y:.1f}" '
        f'stroke="#3fb950" stroke-width="0.8" stroke-dasharray="2,2" opacity="0.6"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f'<circle cx="{sx(len(closes) - 1):.1f}" cy="{sy(last):.1f}" r="2" fill="{color}"/>'
        f'</svg>'
    )


def _render_chart_svg(closes: list[float], timestamps: list[str], entry_idx: int,
                      entry_price: float | None = None, sl_price: float | None = None,
                      sell_min_price: float | None = None,
                      trail_price: float | None = None,
                      trail_stop_price: float | None = None,
                      buy_markers: list | None = None,
                      sell_markers: list | None = None,
                      phantom_markers: list | None = None,
                      width: int = 820, height: int = 320) -> str:
    if len(closes) < 2:
        return "<p class='dim'>Not enough candle data to render chart.</p>"

    pl, pr, pt, pb = 70, 20, 20, 35
    cw = width - pl - pr
    ch = height - pt - pb
    n = len(closes)

    prices = list(closes)
    for ref in [entry_price, sl_price, sell_min_price, trail_price, trail_stop_price]:
        if ref:
            prices.append(ref)
    for _, p in (buy_markers or []):
        prices.append(p)
    for _, p in (sell_markers or []):
        prices.append(p)
    lo = min(prices) * 0.997
    hi = max(prices) * 1.003
    rng = hi - lo or 1.0

    def px(price: float) -> float:
        return pt + ch * (1 - (price - lo) / rng)

    def tx(i: int) -> float:
        return pl + cw * i / (n - 1)

    parts: list[str] = [
        f'<svg width="100%" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="{width}" height="{height}" fill="#0d1117"/>',
    ]

    # Horizontal grid lines with price labels
    for i in range(5):
        y = pt + ch * i / 4
        price = hi - (rng * i / 4)
        parts.append(
            f'<line x1="{pl}" x2="{width - pr}" y1="{y:.0f}" y2="{y:.0f}" '
            f'stroke="#21262d" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pl - 5}" y="{y + 4:.0f}" fill="#8b949e" font-size="10" '
            f'text-anchor="end" font-family="monospace">&#8377;{price:.1f}</text>'
        )

    def hline(price: float, color: str, label: str, dash: str = "4,2") -> None:
        y = px(price)
        parts.append(
            f'<line x1="{pl}" x2="{width - pr}" y1="{y:.1f}" y2="{y:.1f}" '
            f'stroke="{color}" stroke-dasharray="{dash}" opacity="0.85" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pl - 5}" y="{y + 4:.1f}" fill="{color}" font-size="10" '
            f'text-anchor="end" font-family="monospace">{label}</text>'
        )

    if sl_price:
        hline(sl_price, "#f85149", "SL")
    if trail_stop_price:
        hline(trail_stop_price, "#d29922", "T.Stop", dash="3,3")
    elif trail_price and (not sell_min_price or abs(trail_price - sell_min_price) > 0.5):
        hline(trail_price, "#d29922", "Trail")
    if sell_min_price:
        hline(sell_min_price, "#58a6ff", "PTop")
    if entry_price:
        hline(entry_price, "#3fb950", "Entry")

    # Entry vertical line (open position only)
    if entry_price and 0 <= entry_idx < n:
        ex = tx(entry_idx)
        parts.append(
            f'<line x1="{ex:.1f}" x2="{ex:.1f}" y1="{pt}" y2="{pt + ch}" '
            f'stroke="#58a6ff" stroke-dasharray="4,2" opacity="0.6" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ex + 4:.1f}" y="{pt + 12}" fill="#58a6ff" '
            f'font-size="10" font-family="monospace">Entry</text>'
        )

    # Price line
    last = closes[-1]
    ref = entry_price or closes[0]
    line_color = "#3fb950" if last >= ref else "#f85149"
    pts_str = " ".join(f"{tx(i):.1f},{px(c):.1f}" for i, c in enumerate(closes))
    parts.append(
        f'<polyline points="{pts_str}" fill="none" stroke="{line_color}" stroke-width="1.5"/>'
    )

    # Trade markers — rendered on top of price line
    for idx, price in (buy_markers or []):
        if 0 <= idx < n:
            x, y = tx(idx), px(price)
            tip_y = min(pt + ch - 2, y + 8)
            parts.append(
                f'<polygon points="{x:.1f},{tip_y - 7:.1f} {x - 6:.1f},{tip_y:.1f} {x + 6:.1f},{tip_y:.1f}" '
                f'fill="#3fb950" opacity="0.9"/>'
            )
            parts.append(
                f'<text x="{x:.1f}" y="{tip_y + 11:.1f}" fill="#3fb950" font-size="9" '
                f'text-anchor="middle" font-family="monospace">&#8377;{price:.0f}</text>'
            )
    for idx, price in (sell_markers or []):
        if 0 <= idx < n:
            x, y = tx(idx), px(price)
            tip_y = max(pt + 2, y - 8)
            parts.append(
                f'<polygon points="{x:.1f},{tip_y + 7:.1f} {x - 6:.1f},{tip_y:.1f} {x + 6:.1f},{tip_y:.1f}" '
                f'fill="#f85149" opacity="0.9"/>'
            )
            parts.append(
                f'<text x="{x:.1f}" y="{tip_y - 4:.1f}" fill="#f85149" font-size="9" '
                f'text-anchor="middle" font-family="monospace">&#8377;{price:.0f}</text>'
            )

    # Phantom markers — in-position threshold crossings (hollow orange circles)
    for idx, price in (phantom_markers or []):
        if 0 <= idx < n:
            x, y = tx(idx), px(price)
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" '
                f'fill="none" stroke="#d29922" stroke-width="1.2" opacity="0.75"/>'
            )

    # Current price dot + label
    last_x = tx(n - 1)
    last_y = px(last)
    parts.append(f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3" fill="{line_color}"/>')
    parts.append(
        f'<text x="{last_x - 5:.1f}" y="{last_y - 6:.1f}" fill="{line_color}" font-size="10" '
        f'text-anchor="end" font-family="monospace">&#8377;{last:.2f}</text>'
    )

    # X-axis date labels (~6 evenly spaced)
    step = max(1, n // 6)
    for i in range(0, n, step):
        ts_label = timestamps[i][:10] if timestamps[i] else ""
        parts.append(
            f'<text x="{tx(i):.0f}" y="{pt + ch + 25}" fill="#8b949e" font-size="10" '
            f'text-anchor="middle" font-family="monospace">{ts_label}</text>'
        )

    parts.append('</svg>')
    return "".join(parts)


def render_chart_page(instrument: str, store, config) -> str:
    sym = instrument.split(":")[-1]
    tf = config.candle_timeframe
    tf_minutes = {"5minute": 5, "15minute": 15, "30minute": 30, "60minute": 60, "day": 1440}.get(tf, 60)

    # Open position (may not exist)
    pos_rows = _read_db(
        config.db_path,
        "SELECT entry_price, entry_time, peak_close, trailing_active FROM open_positions WHERE instrument = ?",
        (instrument,),
    )
    pos = pos_rows[0] if pos_rows else None

    # All completed orders for this instrument (full history)
    order_rows = _read_db(
        config.db_path,
        "SELECT direction, price, placed_at, updated_at FROM orders "
        "WHERE instrument = ? AND status = 'COMPLETE' ORDER BY placed_at ASC",
        (instrument,),
    )

    # Open position: show 3 days before entry for context.
    # Watchlist / history view: full cached history so all trades are visible.
    if pos and pos.get("entry_time"):
        from_dt = datetime.fromisoformat(pos["entry_time"]) - timedelta(days=3)
    else:
        from_dt = datetime(2000, 1, 1)

    candle_rows = _read_db(
        config.db_path,
        "SELECT timestamp, close FROM candles "
        "WHERE instrument = ? AND timeframe = ? AND timestamp >= ? "
        "ORDER BY timestamp ASC",
        (instrument, config.candle_timeframe, from_dt.isoformat()),
    )

    if len(candle_rows) < 2:
        return (
            f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{sym}</title>"
            f"<style>{_CSS}</style></head><body>"
            f"<p class='dim'>Not enough candle data for {instrument}.</p>"
            f"<a href='/' class='chart-link'>← Dashboard</a></body></html>"
        )

    closes = [r["close"] for r in candle_rows]
    timestamps = [r["timestamp"] for r in candle_rows]

    # Match order fill timestamps to candle indices (use updated_at = fill time, not placed_at)
    buy_markers, sell_markers = [], []
    for o in order_rows:
        fill_ts = o.get("updated_at") or o["placed_at"]
        idx = _find_candle_idx(fill_ts, timestamps)
        (buy_markers if o["direction"] == "BUY" else sell_markers).append((idx, o["price"]))

    # In-position phantom signals (threshold crossed while already holding)
    phantom_rows = _read_db(
        config.db_path,
        "SELECT price_hint, logged_at FROM signals "
        "WHERE instrument = ? AND direction = 'BUY' AND signal_type = 'ENTRY' "
        "  AND accepted = 0 AND reject_reason = 'already_in_position' "
        "ORDER BY logged_at ASC",
        (instrument,),
    )
    phantom_markers = []
    for r in phantom_rows:
        idx = _find_candle_idx(r["logged_at"], timestamps)
        phantom_markers.append((idx, r["price_hint"]))

    # Open position details
    entry_price = pos["entry_price"] if pos else None
    entry_time_str = pos.get("entry_time") if pos else None
    peak_close = (pos.get("peak_close") or 0.0) if pos else 0.0
    trailing_active = bool(pos.get("trailing_active", 0)) if pos else False
    entry_idx = 0
    if entry_time_str:
        target_et = entry_time_str[:16]
        for i, ts in enumerate(timestamps):
            if ts[:16] <= target_et:
                entry_idx = i
            else:
                break

    sl_price = sell_min_price = trail_price = trail_stop_price = None
    if entry_price:
        lr = config.strategy_config("lr_extrema") or {}
        stop_pct = float(lr.get("stop_pct", 3.0))
        profit_pct = float(lr.get("profit_pct", 3.0))
        sell_min_pct = float(lr.get("sell_min_pct", 3.0))
        trail_pct = float(lr.get("trail_pct", 1.5))
        sl_price = round(entry_price * (1 - stop_pct / 100), 2)
        sell_min_price = round(entry_price * (1 + sell_min_pct / 100), 2)
        trail_price = round(entry_price * (1 + profit_pct / 100), 2)
        if trailing_active and peak_close > 0:
            trail_stop_price = round(peak_close * (1 - trail_pct / 100), 2)

    chart_svg = _render_chart_svg(
        closes, timestamps, entry_idx,
        entry_price=entry_price,
        sl_price=sl_price,
        sell_min_price=sell_min_price,
        trail_price=trail_price if not trail_stop_price else None,
        trail_stop_price=trail_stop_price,
        buy_markers=buy_markers,
        sell_markers=sell_markers,
        phantom_markers=phantom_markers,
        width=1100, height=480,
    )

    last_close = closes[-1]
    meta_parts = ['<a href="/" class="chart-link">← Dashboard</a>']
    if entry_price:
        chg = (last_close - entry_price) / entry_price * 100
        chg_sign = "+" if chg >= 0 else ""
        chg_class = "green" if chg >= 0 else "red"
        meta_parts += [
            f"Entry &#8377;{entry_price:.2f}",
            f'Current &#8377;{last_close:.2f} <span class="{chg_class}">({chg_sign}{chg:.2f}%)</span>',
            f"SL &#8377;{sl_price:.2f}",
            f"PTop &#8377;{sell_min_price:.2f}",
        ]
        if trail_stop_price:
            meta_parts.append(f"Trail stop &#8377;{trail_stop_price:.2f} (peak &#8377;{peak_close:.2f})")
        else:
            meta_parts.append(f"Trail &#8377;{trail_price:.2f}")
    else:
        meta_parts.append(f"&#8377;{last_close:.2f} (last close)")
    if phantom_markers:
        meta_parts.append(f'<span class="orange">{len(phantom_markers)} in-pos &#9711;</span>')
    if order_rows:
        n_trades = len([o for o in order_rows if o["direction"] == "BUY"])
        meta_parts.append(f"{n_trades} trade(s)")
    meta_parts.append('<span style="color:#8b949e">auto-refresh 60s</span>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="60">
<title>{sym} — Chart</title>
<style>{_CSS}
body {{ max-width: 1160px; margin: 0 auto; }}
</style>
</head>
<body>
<h1>{sym}</h1>
<div class="meta">{"&nbsp;·&nbsp;".join(meta_parts)}</div>
<div style="margin-top:16px;overflow-x:auto">
{chart_svg}
</div>
</body>
</html>"""


def render_page(bot_state, risk, store, config) -> str:
    now = _now_ist()
    market = _market_status(now)

    # ── heartbeat staleness ──────────────────────────────────────────────────
    last_tick = bot_state.last_candle_at
    if last_tick:
        age = (datetime.now() - last_tick).total_seconds()
        tick_str = f"{_fmt_ist(last_tick)} ({int(age)}s ago)"
        tick_stale = age > 600
    else:
        tick_str = "—"
        tick_stale = True

    # ── status badges ────────────────────────────────────────────────────────
    halted = bot_state.halted
    status_badge = _badge("HALTED", "red") if halted else _badge("RUNNING", "green")
    market_badge = _badge(market, "green" if market == "OPEN" else "dim")
    mode_badge = _badge(config.env.upper(), "orange" if config.env == "live" else "dim")

    uptime_secs = int((datetime.now() - bot_state.started_at).total_seconds())
    h, rem = divmod(uptime_secs, 3600)
    m, s = divmod(rem, 60)
    uptime_str = f"{h}h {m}m {s}s"

    # ── capital ──────────────────────────────────────────────────────────────
    total = config.total_capital
    deployed = risk._capital_deployed
    available = risk.capital_available
    pending_amt = sum(risk._pending_orders.values())
    deploy_pct = (deployed / total * 100) if total else 0
    bar_danger = "danger" if deploy_pct > 85 else ""
    bar_w = min(100, int(deploy_pct))

    # ── P&L ──────────────────────────────────────────────────────────────────
    realised = risk._realised_pnl
    limit = config.daily_loss_limit
    pnl_used_pct = (abs(realised) / limit * 100) if limit and realised < 0 else 0
    pnl_bar_w = min(100, int(pnl_used_pct))
    pnl_bar_danger = "danger" if pnl_used_pct > 75 else ""

    # ── open positions from DB ────────────────────────────────────────────────
    positions = _read_db(
        config.db_path,
        "SELECT instrument, entry_price, quantity, held_bars, entry_time, "
        "current_price, pct_change, unrealised_pnl, peak_close, trailing_active, low_since_entry, "
        "pattern_top_trailing "
        "FROM open_positions ORDER BY entry_time ASC",
    )
    pending_orders = list(risk._pending_orders.keys())

    # ── today's orders ────────────────────────────────────────────────────────
    orders = _read_db(
        config.db_path,
        "SELECT instrument, direction, quantity, price, status, placed_at "
        "FROM orders "
        "WHERE date(placed_at) = date('now', 'localtime') "
        "ORDER BY placed_at DESC LIMIT 20",
    )

    # ── closed trade history ──────────────────────────────────────────────────
    closed_trades = _read_db(
        config.db_path,
        """
        WITH buy_q AS (
          SELECT instrument, price AS entry_price, quantity,
                 placed_at AS entry_time,
                 ROW_NUMBER() OVER (PARTITION BY instrument ORDER BY placed_at) rn
          FROM orders WHERE direction='BUY' AND status='COMPLETE'
        ),
        sell_q AS (
          SELECT instrument, price AS exit_price,
                 placed_at AS exit_time,
                 ROW_NUMBER() OVER (PARTITION BY instrument ORDER BY placed_at) rn
          FROM orders WHERE direction='SELL' AND status='COMPLETE'
        ),
        exit_sig AS (
          SELECT instrument, exit_reason,
                 ROW_NUMBER() OVER (PARTITION BY instrument ORDER BY logged_at) rn
          FROM signals WHERE signal_type = 'EXIT' AND exit_reason IS NOT NULL
        )
        SELECT b.instrument, b.entry_price, s.exit_price, b.quantity,
               (s.exit_price - b.entry_price) * b.quantity AS gross_pnl,
               b.entry_time, s.exit_time, e.exit_reason
        FROM buy_q b
        JOIN sell_q s ON b.instrument = s.instrument AND b.rn = s.rn
        LEFT JOIN exit_sig e ON b.instrument = e.instrument AND e.rn = s.rn
        ORDER BY b.entry_time DESC
        LIMIT 30
        """,
    )

    # ── recent signals ────────────────────────────────────────────────────────
    signals = _read_db(
        config.db_path,
        "SELECT logged_at, instrument, direction, signal_type, price_hint, accepted, reject_reason, exit_reason "
        "FROM signals WHERE reject_reason IS NULL OR reject_reason NOT LIKE 'FILTER:%' "
        "ORDER BY id DESC LIMIT 20",
    )
    filtered_signals = _read_db(
        config.db_path,
        "SELECT logged_at, instrument, direction, signal_type, price_hint, reject_reason "
        "FROM signals WHERE reject_reason LIKE 'FILTER:%' "
        "ORDER BY id DESC LIMIT 30",
    )

    # ── strategy config ───────────────────────────────────────────────────────
    lr = config.strategy_config("lr_extrema")

    # ── build sections ────────────────────────────────────────────────────────

    header = f"""
    <h1>Trader Dashboard</h1>
    <div class="meta">
        {mode_badge} {market_badge} {status_badge}
        &nbsp;·&nbsp; {now.strftime("%d %b %Y, %H:%M:%S IST")}
        &nbsp;·&nbsp; uptime {uptime_str}
        &nbsp;·&nbsp; last tick: {'<span class="red">'+tick_str+'</span>' if tick_stale else tick_str}
        <span style="float:right;font-size:11px">auto-refresh 30s</span>
    </div>"""

    capital_card = f"""
    <div class="card">
        <h2>Capital</h2>
        <table>
            <tr><td class="dim">Total</td><td class="val">&#8377; {total:,.0f}</td></tr>
            <tr><td class="dim">Deployed</td><td class="val">&#8377; {deployed:,.0f}
                <span class="dim">({deploy_pct:.0f}%)</span></td></tr>
            <tr><td class="dim">Pending lock</td><td class="val">&#8377; {pending_amt:,.0f}</td></tr>
            <tr><td class="dim">Available</td><td class="val green">&#8377; {available:,.0f}</td></tr>
        </table>
        <div class="bar-bg"><div class="bar-fill {bar_danger}" style="width:{bar_w}%"></div></div>
    </div>"""

    total_unrealised = sum((p.get("unrealised_pnl") or 0.0) for p in positions)
    unreal_sign = "+" if total_unrealised >= 0 else ""

    pnl_sign = "+" if realised >= 0 else ""
    pnl_card = f"""
    <div class="card">
        <h2>P&amp;L Today</h2>
        <table>
            <tr><td class="dim">Realised</td>
                <td class="val {_pnl_class(realised)}">&#8377; {pnl_sign}{realised:,.2f}</td></tr>
            <tr><td class="dim">Unrealised</td>
                <td class="val {_pnl_class(total_unrealised)}">{unreal_sign}&#8377; {total_unrealised:,.2f}</td></tr>
            <tr><td class="dim">Daily limit</td><td class="val">&#8377; {limit:,.0f}</td></tr>
            <tr><td class="dim">Limit used</td>
                <td class="val {'red' if pnl_used_pct > 75 else 'dim'}">{pnl_used_pct:.0f}%</td></tr>
        </table>
        <div class="bar-bg"><div class="bar-fill {pnl_bar_danger}" style="width:{pnl_bar_w}%"></div></div>
    </div>"""

    # Open positions
    _lr_cfg = config.strategy_config("lr_extrema") or {}
    _stop_pct = float(_lr_cfg.get("stop_pct", 3.0))
    _trail_pct = float(_lr_cfg.get("trail_pct", 1.5))
    _hold_bars_max = int(_lr_cfg.get("hold_bars", 200))

    if positions or pending_orders:
        rows_html = ""
        for p in positions:
            sym = p["instrument"].split(":")[-1]
            entry_ist = _fmt_ist(
                datetime.fromisoformat(p["entry_time"]) if p.get("entry_time") else None
            )
            pct = p.get("pct_change") or 0.0
            upnl = p.get("unrealised_pnl") or 0.0
            cur = p.get("current_price") or 0.0
            peak = p.get("peak_close") or 0.0
            low = p.get("low_since_entry") or 0.0
            trailing = bool(p.get("trailing_active", 0))
            ptt = bool(p.get("pattern_top_trailing", 0))
            held = p.get("held_bars") or 0
            pct_sign = "+" if pct >= 0 else ""
            pct_class = "green" if pct >= 0 else "red"
            upnl_sign = "+" if upnl >= 0 else ""
            # Trailing badge: distinguish TRAIL(TOP) vs TRAIL(PCT)
            if trailing:
                trail_label = "TRAIL(TOP)" if ptt else "TRAIL(PCT)"
                trailing_badge = f" {_badge(trail_label, 'orange')}"
            else:
                trailing_badge = ""
            peak_pct = (peak - p["entry_price"]) / p["entry_price"] * 100 if peak > 0 and p["entry_price"] else 0.0
            low_pct = (low - p["entry_price"]) / p["entry_price"] * 100 if low > 0 and p["entry_price"] else 0.0
            low_str = (
                f"&#8377; {low:.2f} <span class='red' style='font-size:11px'>({low_pct:+.2f}%)</span>"
                if low > 0 else "<span class='dim'>—</span>"
            )
            sl_price = p["entry_price"] * (1 - _stop_pct / 100)
            trail_trigger = peak * (1 - _trail_pct / 100) if trailing and peak > 0 else None
            # Trail distance: how far current price is above trigger (cushion before stop fires)
            trail_cushion_str = ""
            if trail_trigger and cur > 0:
                cushion_pct = (cur - trail_trigger) / cur * 100
                cushion_color = "orange" if cushion_pct < 1.0 else "dim"
                trail_cushion_str = (
                    f"<br><span class='{cushion_color}' style='font-size:11px'>"
                    f"cushion {cushion_pct:+.2f}%</span>"
                )
            stop_cell = (
                f"<span class='red'>&#8377; {sl_price:.2f}</span>"
                + (f"<br><span class='orange' style='font-size:11px'>trail &#8377; {trail_trigger:.2f}</span>"
                   if trail_trigger else "")
                + trail_cushion_str
            )
            # Hold bars progress bar
            hold_pct = min(100, int(held / _hold_bars_max * 100)) if _hold_bars_max else 0
            hold_bar_danger = "danger" if hold_pct >= 80 else ""
            hold_cell = (
                f"{held}/{_hold_bars_max}"
                f'<div class="bar-bg"><div class="bar-fill {hold_bar_danger}" style="width:{hold_pct}%"></div></div>'
            )

            # Sparkline: query candles since entry
            sparkline_html = "<span class='dim'>—</span>"
            if p.get("entry_time"):
                candle_rows = _read_db(
                    config.db_path,
                    "SELECT close FROM candles WHERE instrument = ? AND timeframe = ? "
                    "AND timestamp >= ? ORDER BY timestamp ASC",
                    (p["instrument"], config.candle_timeframe, p["entry_time"]),
                )
                if candle_rows:
                    closes = [r["close"] for r in candle_rows]
                    sparkline_html = _render_sparkline(closes, p["entry_price"])

            rows_html += (
                f"<tr>"
                f"<td><a href='/chart/{sym}' class='chart-link'>{sym}</a>"
                f"<br><span class='dim' style='font-size:11px'>{entry_ist}</span></td>"
                f"<td>{p['quantity']}</td>"
                f"<td>&#8377; {p['entry_price']:.2f}</td>"
                f"<td>&#8377; {cur:.2f} <span class='{pct_class}'>({pct_sign}{pct:.2f}%)</span></td>"
                f"<td class='{pct_class}'>&#8377; {upnl_sign}{upnl:,.2f}</td>"
                f"<td class='green' style='font-size:12px'>&#8377; {peak:.2f}"
                f"<br><span style='font-size:11px'>({peak_pct:+.2f}%)</span></td>"
                f"<td class='red' style='font-size:12px'>{low_str}</td>"
                f"<td>{stop_cell}</td>"
                f"<td>{hold_cell}</td>"
                f"<td>{_badge('OPEN', 'green')}{trailing_badge}</td>"
                f"<td>{sparkline_html}</td>"
                f"</tr>"
            )
        for inst in pending_orders:
            sym = inst.split(":")[-1]
            rows_html += (
                f"<tr>"
                f"<td>{sym}</td><td>—</td><td>—</td><td>—</td><td class='dim'>—</td>"
                f"<td>—</td><td>—</td><td>—</td><td>—</td>"
                f"<td>{_badge('PENDING', 'orange')}</td><td></td>"
                f"</tr>"
            )
        pos_section = f"""
        <div class="card full">
            <h2>Open Positions ({len(positions)}) + Pending ({len(pending_orders)})</h2>
            <table>
                <tr>
                    <th>Symbol / Entry time</th><th>Qty</th><th>Entry</th>
                    <th>Current (chg%)</th><th>Unreal. P&amp;L</th>
                    <th>Peak &#9650;</th><th>Low &#9660;</th><th>SL / Trail trigger</th>
                    <th>Held</th><th>Status</th><th>Since entry</th>
                </tr>
                {rows_html}
            </table>
        </div>"""
    else:
        pos_section = """
        <div class="card full">
            <h2>Open Positions</h2>
            <span class="dim">No open positions</span>
        </div>"""

    # Today's orders
    if orders:
        rows_html = ""
        for o in orders:
            sym = o["instrument"].split(":")[-1]
            price_str = f"&#8377; {o['price']:.2f}" if o.get("price") else o.get("order_type", "—")
            status = o.get("status", "")
            status_kind = {"COMPLETE": "green", "REJECTED": "red", "CANCELLED": "red"}.get(status, "dim")
            dir_class = "green" if o["direction"] == "BUY" else "red"
            placed = o.get("placed_at", "")[:16]
            rows_html += (
                f"<tr>"
                f"<td class='dim'>{placed}</td>"
                f"<td>{sym}</td>"
                f"<td class='{dir_class}'>{o['direction']}</td>"
                f"<td>{o['quantity']}</td>"
                f"<td>{price_str}</td>"
                f"<td>{_badge(status, status_kind)}</td>"
                f"</tr>"
            )
        orders_section = f"""
        <div class="card full">
            <h2>Today's Orders ({len(orders)})</h2>
            <table>
                <tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Qty</th><th>Price</th><th>Status</th></tr>
                {rows_html}
            </table>
        </div>"""
    else:
        orders_section = """
        <div class="card full">
            <h2>Today's Orders</h2>
            <span class="dim">No orders today</span>
        </div>"""

    # Closed trade history
    if closed_trades:
        total_pnl = sum((t.get("gross_pnl") or 0) for t in closed_trades)
        wins = sum(1 for t in closed_trades if (t.get("gross_pnl") or 0) > 0)
        losses = sum(1 for t in closed_trades if (t.get("gross_pnl") or 0) < 0)
        total_sign = "+" if total_pnl >= 0 else ""
        _EXIT_REASON_KIND = {
            "SL": "red", "TRAILING": "orange", "PATTERN_TOP": "orange",
            "STALE": "dim", "STRATEGY": "dim", "OPEN@END": "dim",
        }
        rows_html = ""
        for t in closed_trades:
            sym = t["instrument"].split(":")[-1]
            entry_p = t.get("entry_price") or 0.0
            exit_p = t.get("exit_price") or 0.0
            qty = t.get("quantity") or 0
            pnl = t.get("gross_pnl") or 0.0
            pnl_sign = "+" if pnl >= 0 else ""
            pct_pnl = (exit_p - entry_p) / entry_p * 100 if entry_p else 0.0
            pct_sign = "+" if pct_pnl >= 0 else ""
            entry_fmt = _fmt_ist(datetime.fromisoformat(t["entry_time"])) if t.get("entry_time") else "—"
            exit_fmt = _fmt_ist(datetime.fromisoformat(t["exit_time"])) if t.get("exit_time") else "—"
            dur = _hold_duration(t.get("entry_time", ""), t.get("exit_time", ""))
            exit_reason = t.get("exit_reason") or ""
            reason_badge = (
                _badge(exit_reason, _EXIT_REASON_KIND.get(exit_reason, "dim"))
                if exit_reason else "<span class='dim'>—</span>"
            )
            rows_html += (
                f"<tr>"
                f"<td class='dim'>{entry_fmt}</td>"
                f"<td>{sym}</td>"
                f"<td>&#8377; {entry_p:.2f}</td>"
                f"<td>&#8377; {exit_p:.2f}</td>"
                f"<td class='dim'>{qty}</td>"
                f"<td class='{_pnl_class(pnl)}'>{pnl_sign}&#8377; {pnl:,.2f} ({pct_sign}{pct_pnl:.2f}%)</td>"
                f"<td class='dim'>{dur}</td>"
                f"<td>{reason_badge}</td>"
                f"<td class='dim'>{exit_fmt}</td>"
                f"</tr>"
            )
        trades_section = f"""
        <div class="card full">
            <h2>Trade History — {len(closed_trades)} closed trades
                &nbsp;<span class="dim" style="font-weight:normal;text-transform:none">
                {wins}W / {losses}L &nbsp;·&nbsp; gross P&L
                <span class="{_pnl_class(total_pnl)}">{total_sign}&#8377; {total_pnl:,.2f}</span>
                <span style="font-size:10px">(before costs)</span>
                </span>
            </h2>
            <table>
                <tr><th>Entry time</th><th>Symbol</th><th>Entry &#8377;</th><th>Exit &#8377;</th>
                    <th>Qty</th><th>Gross P&amp;L</th><th>Hold</th><th>Exit reason</th><th>Exit time</th></tr>
                {rows_html}
            </table>
        </div>"""
    else:
        trades_section = ""

    # Recent signals
    if signals:
        rows_html = ""
        for s in signals:
            sym = s["instrument"].split(":")[-1]
            accepted = bool(s.get("accepted"))
            acc_badge = _badge("✓", "green") if accepted else _badge("✗", "red")
            reject_reason = s.get("reject_reason") or ""
            exit_reason = s.get("exit_reason") or ""
            reason_display = exit_reason if s.get("signal_type") == "EXIT" else reject_reason
            display_dir = "SELL" if s.get("signal_type") == "EXIT" else s["direction"]
            dir_class = "green" if display_dir == "BUY" else "red"
            logged = s.get("logged_at", "")[:16]
            rows_html += (
                f"<tr>"
                f"<td class='dim'>{logged}</td>"
                f"<td>{sym}</td>"
                f"<td class='{dir_class}'>{display_dir}</td>"
                f"<td class='dim'>{s['signal_type']}</td>"
                f"<td>&#8377; {s['price_hint']:.2f}</td>"
                f"<td>{acc_badge}</td>"
                f"<td class='dim'>{reason_display}</td>"
                f"</tr>"
            )
        signals_section = f"""
        <div class="card full">
            <h2>Recent Signals (last 20)</h2>
            <table>
                <tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Type</th>
                    <th>Price hint</th><th></th><th>Reason</th></tr>
                {rows_html}
            </table>
        </div>"""
    else:
        signals_section = """
        <div class="card full">
            <h2>Recent Signals</h2>
            <span class="dim">No signals logged yet</span>
        </div>"""

    # Filtered signals
    if filtered_signals:
        rows_html = ""
        for s in filtered_signals:
            sym = s["instrument"].split(":")[-1]
            logged = s.get("logged_at", "")[:16]
            reason = (s.get("reject_reason") or "").removeprefix("FILTER: ")
            rows_html += (
                f"<tr>"
                f"<td class='dim'>{logged}</td>"
                f"<td>{sym}</td>"
                f"<td>&#8377; {s['price_hint']:.2f}</td>"
                f"<td class='dim'>{reason}</td>"
                f"</tr>"
            )
        filtered_section = f"""
        <div class="card full">
            <h2>Filtered Signals — blocked by strategy gates (last 10)</h2>
            <table>
                <tr><th>Time</th><th>Symbol</th><th>Price</th><th>Reason</th></tr>
                {rows_html}
            </table>
        </div>"""
    else:
        filtered_section = ""

    # Strategy config
    if lr:
        params_html = " &nbsp; ".join(
            f"<span class='tag'>{k} = {v}</span>"
            for k, v in lr.items()
            if k != "enabled"
        )
        strategy_section = f"""
        <div class="card full">
            <h2>Strategy Config — lr_extrema</h2>
            <div style="margin-top:4px">{params_html}</div>
        </div>"""
    else:
        strategy_section = ""

    # Watchlist + warm-up status + last tick from DB
    placeholders = ",".join("?" * len(config.watchlist))
    last_ticks = {}
    if config.watchlist:
        rows = _read_db(
            config.db_path,
            f"""
            SELECT c.instrument, c.timestamp, c.close, c.volume
            FROM candles c
            INNER JOIN (
                SELECT instrument, MAX(timestamp) AS max_ts
                FROM candles
                WHERE timeframe = ? AND instrument IN ({placeholders})
                GROUP BY instrument
            ) latest ON c.instrument = latest.instrument AND c.timestamp = latest.max_ts
            """,
            (config.candle_timeframe, *config.watchlist),
        )
        last_ticks = {r["instrument"]: r for r in rows}

    _threshold = float(_lr_cfg.get("threshold", 0.70))
    _veto_threshold = float(_lr_cfg.get("veto_threshold", 0.50))
    _sell_threshold = float(_lr_cfg.get("sell_threshold", 0.65))

    ws_rows = ""
    for sym in config.watchlist:
        ws = bot_state.warmup_status.get(sym, {})
        st = ws.get("status", "—")
        candles = ws.get("candles", "—")
        kind = "green" if st == "TRAINED" else ("orange" if st == "WARMING_UP" else "dim")
        tick = last_ticks.get(sym)
        if tick:
            close = tick["close"]
            vol = tick["volume"]
            tick_time = _fmt_ist(datetime.fromisoformat(tick["timestamp"]))
            price_html = f"&#8377; {close:.2f}"
            vol_html = f"{vol:,}"
        else:
            price_html = "<span class='dim'>—</span>"
            vol_html = "<span class='dim'>—</span>"
            tick_time = "<span class='dim'>—</span>"

        scores = bot_state.model_scores.get(sym, {})
        p_min = scores.get("p_min", 0.0)
        p_max = scores.get("p_max", 0.0)
        if scores:
            p_min_pct = int(p_min * 100)
            p_max_pct = int(p_max * 100)
            # P(buy): green when near/above entry threshold
            p_min_color = "#3fb950" if p_min >= _threshold else ("#d29922" if p_min >= _threshold * 0.8 else "#8b949e")
            # P(sell): red when near/above sell or veto threshold
            p_max_color = "#f85149" if p_max >= _sell_threshold else ("#d29922" if p_max >= _veto_threshold else "#8b949e")
            p_min_html = (
                f'<span style="color:{p_min_color};font-variant-numeric:tabular-nums">{p_min_pct}%</span>'
                f'<div style="background:#21262d;border-radius:2px;height:3px;margin-top:2px;width:48px">'
                f'<div style="background:{p_min_color};border-radius:2px;height:3px;width:{min(48,int(p_min*48))}px"></div></div>'
            )
            p_max_html = (
                f'<span style="color:{p_max_color};font-variant-numeric:tabular-nums">{p_max_pct}%</span>'
                f'<div style="background:#21262d;border-radius:2px;height:3px;margin-top:2px;width:48px">'
                f'<div style="background:{p_max_color};border-radius:2px;height:3px;width:{min(48,int(p_max*48))}px"></div></div>'
            )
        else:
            p_min_html = "<span class='dim'>—</span>"
            p_max_html = "<span class='dim'>—</span>"

        # Mini sparkline with trade markers (last 80 candles)
        ws_candles = _read_db(
            config.db_path,
            "SELECT timestamp, close FROM candles WHERE instrument = ? AND timeframe = ? "
            "ORDER BY timestamp DESC LIMIT 80",
            (sym, config.candle_timeframe),
        )
        ws_candles = list(reversed(ws_candles))
        ws_closes = [r["close"] for r in ws_candles]
        ws_ts = [r["timestamp"] for r in ws_candles]
        ws_orders = _read_db(
            config.db_path,
            "SELECT direction, price, placed_at, updated_at FROM orders "
            "WHERE instrument = ? AND status = 'COMPLETE' ORDER BY placed_at ASC",
            (sym,),
        )
        ws_buys, ws_sells = [], []
        for o in ws_orders:
            fill_ts = o.get("updated_at") or o["placed_at"]
            idx = _find_candle_idx(fill_ts, ws_ts)
            (ws_buys if o["direction"] == "BUY" else ws_sells).append((idx, o["price"]))
        open_entry_for_sym = next(
            (p["entry_price"] for p in positions if p["instrument"] == sym), None
        )
        sparkline_html = _render_watchlist_sparkline(
            ws_closes, ws_buys, ws_sells, open_entry=open_entry_for_sym
        )

        ticker = sym.split(":")[-1]
        ws_rows += (
            f"<tr>"
            f"<td><a href='/chart/{ticker}' class='chart-link'>{ticker}</a></td>"
            f"<td class='val'>{price_html}</td>"
            f"<td class='dim'>{tick_time}</td>"
            f"<td class='dim'>{vol_html}</td>"
            f"<td>{p_min_html}</td>"
            f"<td>{p_max_html}</td>"
            f"<td>{_badge(st, kind)}</td>"
            f"<td class='dim'>{candles} candles</td>"
            f"<td>{sparkline_html}</td>"
            f"</tr>"
        )
    watchlist_section = f"""
    <div class="card full">
        <h2>Watchlist ({len(config.watchlist)} symbols)</h2>
        <table>
            <tr><th>Symbol</th><th>Last price</th><th>Candle time (IST)</th>
                <th>Volume</th>
                <th>P(buy) <span class="dim" style="font-weight:normal">thr={int(_threshold*100)}%</span></th>
                <th>P(sell) <span class="dim" style="font-weight:normal">veto={int(_veto_threshold*100)}%</span></th>
                <th>Warm-up</th><th>Candles</th><th>Trend (last 80)</th></tr>
            {ws_rows}
        </table>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trader</title>
<style>{_CSS}</style>
</head>
<body>
{header}
<div class="grid">
    {capital_card}
    {pnl_card}
    {pos_section}
    {orders_section}
    {trades_section}
    {signals_section}
    {filtered_section}
    {strategy_section}
    {watchlist_section}
</div>
</body>
</html>"""
