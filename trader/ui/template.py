"""
Dashboard HTML renderer — pure Python, no template files, no external dependencies.

render_page() returns a complete HTML string. All CSS is inlined.
SQLite is queried directly (read-only connection) so the Store write path is untouched.
"""

import sqlite3
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))

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
td { padding: 4px 8px 4px 0; border-bottom: 1px solid #161b22; }
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
"""


def _now_ist() -> datetime:
    return datetime.now(_IST)


def _fmt_ist(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(_IST)
    else:
        dt = dt.astimezone(_IST)
    return dt.strftime("%H:%M:%S")


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
        "SELECT instrument, entry_price, quantity, held_bars, entry_time "
        "FROM open_positions ORDER BY entry_time ASC",
    )
    # pending orders from risk manager memory
    pending_orders = list(risk._pending_orders.keys())

    # ── today's orders ────────────────────────────────────────────────────────
    orders = _read_db(
        config.db_path,
        "SELECT instrument, direction, quantity, price, status, placed_at "
        "FROM orders "
        "WHERE date(placed_at) = date('now', 'localtime') "
        "ORDER BY placed_at DESC LIMIT 20",
    )

    # ── recent signals ────────────────────────────────────────────────────────
    signals = _read_db(
        config.db_path,
        "SELECT logged_at, instrument, direction, signal_type, price_hint, accepted, reject_reason "
        "FROM signals ORDER BY id DESC LIMIT 20",
    )

    # ── strategy config ───────────────────────────────────────────────────────
    lr = config.strategy_config("lr_extrema")

    # ── build sections ────────────────────────────────────────────────────────

    # Header
    header = f"""
    <h1>Trader Dashboard</h1>
    <div class="meta">
        {mode_badge} {market_badge} {status_badge}
        &nbsp;·&nbsp; {now.strftime("%d %b %Y, %H:%M:%S IST")}
        &nbsp;·&nbsp; uptime {uptime_str}
        &nbsp;·&nbsp; last tick: {'<span class="red">'+tick_str+'</span>' if tick_stale else tick_str}
        <span style="float:right;font-size:11px">auto-refresh 30s</span>
    </div>"""

    # Capital card
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

    # P&L card
    pnl_sign = "+" if realised >= 0 else ""
    pnl_card = f"""
    <div class="card">
        <h2>P&amp;L Today</h2>
        <table>
            <tr><td class="dim">Realised</td>
                <td class="val {_pnl_class(realised)}">&#8377; {pnl_sign}{realised:,.2f}</td></tr>
            <tr><td class="dim">Daily limit</td><td class="val">&#8377; {limit:,.0f}</td></tr>
            <tr><td class="dim">Limit used</td>
                <td class="val {'red' if pnl_used_pct > 75 else 'dim'}">{pnl_used_pct:.0f}%</td></tr>
        </table>
        <div class="bar-bg"><div class="bar-fill {pnl_bar_danger}" style="width:{pnl_bar_w}%"></div></div>
    </div>"""

    # Open positions
    if positions or pending_orders:
        rows_html = ""
        for p in positions:
            sym = p["instrument"].split(":")[-1]
            entry_ist = _fmt_ist(
                datetime.fromisoformat(p["entry_time"]) if p.get("entry_time") else None
            )
            rows_html += (
                f"<tr>"
                f"<td>{sym}</td>"
                f"<td>{p['quantity']}</td>"
                f"<td>&#8377; {p['entry_price']:.2f}</td>"
                f"<td>{p['held_bars']} bars</td>"
                f"<td class='dim'>{entry_ist}</td>"
                f"<td>{_badge('OPEN', 'green')}</td>"
                f"</tr>"
            )
        for inst in pending_orders:
            sym = inst.split(":")[-1]
            rows_html += (
                f"<tr>"
                f"<td>{sym}</td><td>—</td><td>—</td><td>—</td><td class='dim'>—</td>"
                f"<td>{_badge('PENDING', 'orange')}</td>"
                f"</tr>"
            )
        pos_section = f"""
        <div class="card full">
            <h2>Open Positions ({len(positions)}) + Pending ({len(pending_orders)})</h2>
            <table>
                <tr>
                    <th>Symbol</th><th>Qty</th><th>Entry</th>
                    <th>Held</th><th>Entry time (IST)</th><th>Status</th>
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
            price_str = f"&#8377; {o['price']:.2f}" if o.get("price") else "—"
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

    # Recent signals
    if signals:
        rows_html = ""
        for s in signals:
            sym = s["instrument"].split(":")[-1]
            accepted = bool(s.get("accepted"))
            acc_badge = _badge("✓", "green") if accepted else _badge("✗", "red")
            reason = s.get("reject_reason") or ""
            dir_class = "green" if s["direction"] == "BUY" else "red"
            logged = s.get("logged_at", "")[:16]
            rows_html += (
                f"<tr>"
                f"<td class='dim'>{logged}</td>"
                f"<td>{sym}</td>"
                f"<td class='{dir_class}'>{s['direction']}</td>"
                f"<td class='dim'>{s['signal_type']}</td>"
                f"<td>&#8377; {s['price_hint']:.2f}</td>"
                f"<td>{acc_badge}</td>"
                f"<td class='dim'>{reason}</td>"
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

    # Watchlist + warm-up status
    ws_rows = ""
    for sym in config.watchlist:
        ws = bot_state.warmup_status.get(sym, {})
        st = ws.get("status", "—")
        candles = ws.get("candles", "—")
        kind = "green" if st == "TRAINED" else ("orange" if st == "WARMING_UP" else "dim")
        ws_rows += (
            f"<tr>"
            f"<td>{sym.split(':')[-1]}</td>"
            f"<td>{_badge(st, kind)}</td>"
            f"<td class='dim'>{candles} candles</td>"
            f"</tr>"
        )
    watchlist_section = f"""
    <div class="card full">
        <h2>Watchlist ({len(config.watchlist)} symbols)</h2>
        <table>
            <tr><th>Symbol</th><th>Warm-up</th><th>Candles</th></tr>
            {ws_rows}
        </table>
    </div>"""

    # Full page
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
    {signals_section}
    {strategy_section}
    {watchlist_section}
</div>
</body>
</html>"""
