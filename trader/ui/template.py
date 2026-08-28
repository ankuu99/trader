"""
Dashboard HTML renderer — pure Python, no template files, no external dependencies.

render_page() returns a complete HTML string. All CSS is inlined.
render_chart_page() returns a full-page SVG chart for a single instrument.
SQLite is queried directly (read-only connection) so the Store write path is untouched.
"""

import html as _html
import sqlite3
import time as _time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from trader.costs import round_trip_cost

# Auto-refresh without a full navigation: re-fetch this URL every 30s and swap
# <body> in place, so scroll position (and any open <details>) survive — a meta
# refresh snaps a phone back to the top every 30s. Pauses while the tab is
# hidden (battery/data over Tailscale) and while a form input has focus, so a
# half-typed date range is never clobbered. <noscript> keeps the old meta
# refresh as the fallback. The "all columns" checkbox (mobile only) undoes the
# CSS column pruning and is remembered per browser in localStorage.
_JS = """
(function () {
  var INTERVAL = 30000, timer = null;
  function applyCols() {
    var on = false;
    try { on = localStorage.getItem('allcols') === '1'; } catch (e) {}
    document.body.classList.toggle('allcols', on);
    var cb = document.getElementById('allcols');
    if (cb) {
      cb.checked = on;
      cb.onchange = function () {
        try { localStorage.setItem('allcols', cb.checked ? '1' : '0'); } catch (e) {}
        applyCols();
      };
    }
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(refresh, INTERVAL); }
  function refresh() {
    if (document.visibilityState !== 'visible') { return; }  // resumes on visibilitychange
    var ae = document.activeElement;
    if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'SELECT')) { return schedule(); }
    fetch(location.href, { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) { throw new Error(r.status); } return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var open = {};
        document.querySelectorAll('details[id]').forEach(function (d) { open[d.id] = d.open; });
        document.body.innerHTML = doc.body.innerHTML;
        Object.keys(open).forEach(function (id) {
          var d = document.getElementById(id); if (d) { d.open = open[id]; }
        });
        applyCols();
      })
      .catch(function (err) {
        var n = document.getElementById('refresh-note');
        if (n) { n.textContent = 'refresh failed (' + (err && err.message || err) + ') — retrying'; }
      })
      .then(schedule);
  }
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') { refresh(); }
  });
  document.addEventListener('DOMContentLoaded', function () { applyCols(); schedule(); });
})();
"""


def _html_attr(text: str) -> str:
    """Escape a string for safe use inside a double-quoted HTML attribute."""
    return _html.escape(str(text), quote=True)


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
.toprow { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.toprow > * { flex: 1; min-width: 240px; }
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
.rangebar { display: inline-flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.rbtn {
    display: inline-block; padding: 2px 8px; border-radius: 3px;
    border: 1px solid #30363d; background: #21262d; color: #c9d1d9;
    font-size: 11px; text-decoration: none; cursor: pointer;
    font-family: inherit;
}
.rbtn:hover { border-color: #1f6feb; }
.rbtn.active { background: #1f6feb; color: #fff; border-color: #1f6feb; }
.rangebar input[type=date] {
    background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 3px; padding: 2px 4px; font-size: 11px; font-family: inherit;
}

.pane { flex: 1; min-width: 280px; }
.pane-wide { flex: 1.6; min-width: 380px; }
.pane-sm { min-width: 220px; }
.hdr { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.m-only { display: none; }
.retrow { display: flex; gap: 18px; flex-wrap: wrap; margin: 8px 0 6px; }
.retrow > div { flex: 1 1 140px; min-width: 0; }
.card svg { max-width: 100%; height: auto; }
.retrow .k { font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
.retrow .v { font-size: 15px; color: #e6edf3; }
.retrow .s { font-size: 11px; }
/* ── phone layout (Tailscale on mobile): single column, cards scroll their own
   wide tables, bigger tap targets, low-priority columns pruned unless the
   "all columns" toggle is on. Desktop is untouched. ── */
@media (max-width: 720px) {
  body { padding: 8px; font-size: 14px; }
  h1 { font-size: 17px; }
  .meta { font-size: 13px; margin-bottom: 10px; }
  .grid { grid-template-columns: 1fr; gap: 8px; }
  .toprow { gap: 8px; }
  .toprow > *, .pane, .pane-wide, .pane-sm { min-width: 0; flex-basis: 100%; }
  .card { padding: 10px; overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .card h2 { font-size: 12px; }
  th, td { padding: 6px 10px 6px 0; }
  th, .dim { font-size: 12px; }
  .badge { font-size: 12px; padding: 2px 7px; }
  .rbtn { padding: 6px 12px; font-size: 13px; }
  .rangebar { gap: 6px; }
  .rangebar input[type=date] { padding: 5px 6px; font-size: 13px; }
  .m-only { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }
  .m-only input { width: 18px; height: 18px; }
  .retrow { gap: 10px; }
  .retrow > div { flex: 1 1 42%; }
  .chart-scroll svg { min-width: 760px; }   /* scroll the big chart, don't shrink it to a thumbnail */
  body:not(.allcols) table.t-roll th:nth-child(2), body:not(.allcols) table.t-roll td:nth-child(2),
  body:not(.allcols) table.t-roll th:nth-child(3), body:not(.allcols) table.t-roll td:nth-child(3) { display: none; }
  body:not(.allcols) table.t-pos th:nth-child(3), body:not(.allcols) table.t-pos td:nth-child(3),
  body:not(.allcols) table.t-pos th:nth-child(4), body:not(.allcols) table.t-pos td:nth-child(4),
  body:not(.allcols) table.t-pos th:nth-child(7), body:not(.allcols) table.t-pos td:nth-child(7),
  body:not(.allcols) table.t-pos th:nth-child(8), body:not(.allcols) table.t-pos td:nth-child(8),
  body:not(.allcols) table.t-pos th:nth-child(10), body:not(.allcols) table.t-pos td:nth-child(10),
  body:not(.allcols) table.t-pos th:nth-child(13), body:not(.allcols) table.t-pos td:nth-child(13),
  body:not(.allcols) table.t-trades th:nth-child(1), body:not(.allcols) table.t-trades td:nth-child(1),
  body:not(.allcols) table.t-trades th:nth-child(5), body:not(.allcols) table.t-trades td:nth-child(5),
  body:not(.allcols) table.t-trades th:nth-child(6), body:not(.allcols) table.t-trades td:nth-child(6),
  body:not(.allcols) table.t-trades th:nth-child(7), body:not(.allcols) table.t-trades td:nth-child(7),
  body:not(.allcols) table.t-trades th:nth-child(9), body:not(.allcols) table.t-trades td:nth-child(9),
  body:not(.allcols) table.t-score th:nth-child(6), body:not(.allcols) table.t-score td:nth-child(6),
  body:not(.allcols) table.t-signals th:nth-child(5), body:not(.allcols) table.t-signals td:nth-child(5),
  body:not(.allcols) table.t-watch th:nth-child(3), body:not(.allcols) table.t-watch td:nth-child(3),
  body:not(.allcols) table.t-watch th:nth-child(4), body:not(.allcols) table.t-watch td:nth-child(4),
  body:not(.allcols) table.t-watch th:nth-child(9), body:not(.allcols) table.t-watch td:nth-child(9),
  body:not(.allcols) table.t-watch th:nth-child(10), body:not(.allcols) table.t-watch td:nth-child(10),
  body:not(.allcols) table.t-watch th:nth-child(11), body:not(.allcols) table.t-watch td:nth-child(11) { display: none; }
}
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


def _parse_ist_naive(ts) -> datetime | None:
    """Parse a stored timestamp (naive process-local, per store.py) into an
    IST-naive datetime — the same space _fmt_ist renders in. Date-range filtering
    is done in IST so the window the user picks lines up with the displayed dates."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        dt = ts
    else:
        try:
            dt = datetime.fromisoformat(str(ts))
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        return dt + _NAIVE_TO_IST_DELTA
    return dt.astimezone(_IST).replace(tzinfo=None)


_RANGE_DELTAS = {
    "1w": timedelta(days=7), "1m": timedelta(days=30),
    "1q": timedelta(days=90), "1y": timedelta(days=365),
}
_RANGE_LABELS = {
    "1w": "Last week", "1m": "Last month", "1q": "Last quarter",
    "1y": "Last year", "all": "All time",
}


def _resolve_range(params: dict | None):
    """Resolve URL params (range / from / to) into an IST-naive (lo, hi) window
    plus a human label and the active key. lo/hi are None for all-time. Explicit
    from/to dates take precedence over a quick-filter range key. Bad input falls
    back to all-time."""
    params = params or {}
    now = _now_ist().replace(tzinfo=None)
    hi_today = now.replace(hour=23, minute=59, second=59, microsecond=0)
    frm = (params.get("from") or "").strip()
    to = (params.get("to") or "").strip()

    def _day(s: str, end: bool = False):
        try:
            d = datetime.fromisoformat(s)
        except (ValueError, TypeError):
            return None
        return (d.replace(hour=23, minute=59, second=59, microsecond=0) if end
                else d.replace(hour=0, minute=0, second=0, microsecond=0))

    if frm or to:
        lo = _day(frm)
        hi = _day(to, end=True) or hi_today
        if lo or _day(to, end=True):  # at least one valid bound
            lbl = f"{lo:%d %b %Y}" if lo else "start"
            return lo, hi, f"{lbl} – {hi:%d %b %Y}", "custom"

    key = (params.get("range") or "").strip().lower()
    if key in _RANGE_DELTAS:
        lo = (now - _RANGE_DELTAS[key]).replace(hour=0, minute=0, second=0, microsecond=0)
        return lo, hi_today, _RANGE_LABELS[key], key
    return None, None, _RANGE_LABELS["all"], "all"


def _filter_trades(trades: list[dict], lo, hi) -> list[dict]:
    """Keep matched trades whose exit (IST) falls within [lo, hi]. Trades with no
    recorded exit are dropped from windowed views. lo/hi None ⇒ no filtering.
    NOTE: always run this AFTER FIFO match_trades on the full order set — never
    filter raw orders before matching, or BUY↔SELL pairing across the window
    boundary breaks."""
    if lo is None and hi is None:
        return trades
    out = []
    for t in trades:
        x = _parse_ist_naive(t.get("exit_time"))
        if x is None:
            continue
        if lo and x < lo:
            continue
        if hi and x > hi:
            continue
        out.append(t)
    return out


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


def _read_model_scores(db_path, instrument: str, limit: int = 80) -> list[dict]:
    """Recent persisted (p_min, p_max) scores for an instrument, oldest-first.
    Returns [] when the table is absent (old DBs) — caller renders a dash."""
    rows = _read_db(
        db_path,
        "SELECT timestamp, p_min, p_max FROM model_scores WHERE instrument = ? "
        "ORDER BY timestamp DESC LIMIT ?",
        (instrument, limit),
    )
    return list(reversed(rows))


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
    # Drop any NULL closes — an order/candle with a missing price would crash min/max.
    closes = [c for c in closes if c is not None]
    if len(closes) < 2:
        return "<span class='dim'>—</span>"
    # Markers can carry a NULL price (completed order with no recorded fill price); skip those.
    buy_markers = [(i, p) for i, p in buy_markers if p is not None]
    sell_markers = [(i, p) for i, p in sell_markers if p is not None]
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
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
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


def _render_prob_sparkline(
    scores: list[dict],
    threshold: float,
    veto_threshold: float,
    width: int = 180,
    height: int = 50,
) -> str:
    """Conviction trajectory — P(buy)=green and P(sell)=red over recent candles on
    a FIXED 0..1 axis (so a line pinned at the top reads as model saturation, not a
    strong signal). Dotted guides mark the entry threshold (green) and veto (red)."""
    if len(scores) < 2:
        return "<span class='dim'>—</span>"
    n = len(scores)
    pad = 4

    def sx(i: int) -> float:
        return pad + (i / (n - 1)) * (width - 2 * pad)

    def sy(p: float) -> float:
        p = 0.0 if p < 0 else (1.0 if p > 1 else p)
        return pad + (1 - p) * (height - 2 * pad)

    buy = " ".join(f"{sx(i):.1f},{sy(s['p_min']):.1f}" for i, s in enumerate(scores))
    sell = " ".join(f"{sx(i):.1f},{sy(s['p_max']):.1f}" for i, s in enumerate(scores))
    last = scores[-1]

    parts = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="vertical-align:middle;display:inline-block;background:#161b22;border-radius:3px">',
        # threshold / veto guides
        f'<line x1="{pad}" y1="{sy(threshold):.1f}" x2="{width - pad}" y2="{sy(threshold):.1f}" '
        f'stroke="#3fb950" stroke-width="0.7" stroke-dasharray="2,2" opacity="0.4"/>',
        f'<line x1="{pad}" y1="{sy(veto_threshold):.1f}" x2="{width - pad}" y2="{sy(veto_threshold):.1f}" '
        f'stroke="#f85149" stroke-width="0.7" stroke-dasharray="2,2" opacity="0.4"/>',
        f'<polyline points="{sell}" fill="none" stroke="#f85149" stroke-width="1.0" opacity="0.85"/>',
        f'<polyline points="{buy}" fill="none" stroke="#3fb950" stroke-width="1.2"/>',
        f'<circle cx="{sx(n - 1):.1f}" cy="{sy(last["p_min"]):.1f}" r="2" fill="#3fb950"/>',
        '</svg>',
    ]
    return "".join(parts)


def _render_equity_sparkline(values: list[float], net_values: list[float] | None = None,
                             width: int = 300, height: int = 70,
                             bench_values: list | None = None) -> str:
    """Line of a cumulative-P&L series with a dashed zero baseline. Green if the
    series ends positive, red otherwise. (Clone of _render_sparkline's polyline.)
    When `net_values` is given (same length), the gross series is drawn as a dim
    dashed line and the net-of-costs series becomes the prominent colored one.
    `bench_values` (same length, None gaps allowed) overlays the benchmark's
    full-capital buy-and-hold ₹ at each point as a thin blue line."""
    if len(values) < 2:
        return "<span class='dim'>—</span>"
    bench = [v for v in (bench_values or []) if v is not None]
    all_series = values + (net_values or []) + bench
    lo = min(min(all_series), 0.0)
    hi = max(max(all_series), 0.0)
    rng = (hi - lo) or 1.0
    pad = 4

    def sx(i: int) -> float:
        return pad + (i / (len(values) - 1)) * (width - 2 * pad)

    def sy(v: float) -> float:
        return pad + (1 - (v - lo) / rng) * (height - 2 * pad)

    zero_y = max(pad, min(height - pad, sy(0.0)))
    main = net_values if net_values else values
    pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(main))
    last = main[-1]
    color = "#3fb950" if last >= 0 else "#f85149"
    gross_line = ""
    if net_values:
        gross_pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(values))
        gross_line = (f'<polyline points="{gross_pts}" fill="none" stroke="#8b949e" '
                      f'stroke-width="1.2" stroke-dasharray="3,2" opacity="0.7"/>')
    bench_line = ""
    if bench_values and len(bench_values) == len(values) and len(bench) >= 2:
        bench_pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(bench_values)
                             if v is not None)
        bench_line = (f'<polyline points="{bench_pts}" fill="none" stroke="#58a6ff" '
                      f'stroke-width="1.1" opacity="0.85"/>')
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="vertical-align:middle;display:inline-block">'
        f'<line x1="{pad}" y1="{zero_y:.1f}" x2="{width - pad}" y2="{zero_y:.1f}" '
        f'stroke="#8b949e" stroke-width="0.8" stroke-dasharray="2,2" opacity="0.5"/>'
        f'{bench_line}'
        f'{gross_line}'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f'<circle cx="{sx(len(main) - 1):.1f}" cy="{sy(last):.1f}" r="2" fill="{color}"/>'
        f'</svg>'
    )


def _render_underwater_svg(underwater: list[float], width: int = 300, height: int = 70) -> str:
    """Filled area chart of the underwater (drawdown) series — all values <= 0,
    drawn as a red region hanging below a zero baseline at the top."""
    if len(underwater) < 2:
        return "<span class='dim'>—</span>"
    lo = min(min(underwater), 0.0)
    rng = (0.0 - lo) or 1.0
    pad = 4

    def sx(i: int) -> float:
        return pad + (i / (len(underwater) - 1)) * (width - 2 * pad)

    def sy(v: float) -> float:
        return pad + (-(v) / rng) * (height - 2 * pad)  # 0 at top, lo at bottom

    pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(underwater))
    zero_y = pad
    area = f"{sx(0):.1f},{zero_y:.1f} " + pts + f" {sx(len(underwater) - 1):.1f},{zero_y:.1f}"
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="vertical-align:middle;display:inline-block">'
        f'<line x1="{pad}" y1="{zero_y:.1f}" x2="{width - pad}" y2="{zero_y:.1f}" '
        f'stroke="#8b949e" stroke-width="0.8" stroke-dasharray="2,2" opacity="0.5"/>'
        f'<polygon points="{area}" fill="#f85149" fill-opacity="0.18"/>'
        f'<polyline points="{pts}" fill="none" stroke="#f85149" stroke-width="1.5"/>'
        f'</svg>'
    )


def _render_giveback_svg(equity: list[float], hwm: list[float], worst: dict | None = None,
                         width: int = 300, height: int = 70) -> str:
    """Net equity curve with its running high-water mark (dashed step) and the
    gap between them shaded — the giveback drawn ON the curve, so a dip reads as
    "we were at X, fell to Y, climbed back", not as a hole below zero. `worst`
    (an episode dict) puts a marker at the deepest trough."""
    if len(equity) < 2 or len(hwm) != len(equity):
        return "<span class='dim'>—</span>"
    lo = min(min(equity), 0.0)
    hi = max(max(hwm), 0.0)
    rng = (hi - lo) or 1.0
    pad = 4
    n = len(equity)

    def sx(i: int) -> float:
        return pad + (i / (n - 1)) * (width - 2 * pad)

    def sy(v: float) -> float:
        return pad + (1 - (v - lo) / rng) * (height - 2 * pad)

    zero_y = max(pad, min(height - pad, sy(0.0)))
    eq_pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(equity))
    # HWM as a step line: flat until a new peak, then a vertical rise.
    step = []
    for i, v in enumerate(hwm):
        if i and hwm[i - 1] != v:
            step.append(f"{sx(i):.1f},{sy(hwm[i - 1]):.1f}")
        step.append(f"{sx(i):.1f},{sy(v):.1f}")
    hwm_pts = " ".join(step)
    # Shade hwm -> equity (top edge along the HWM, back along the equity line).
    gap = (" ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(hwm)) + " "
           + " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in reversed(list(enumerate(equity)))))
    last = equity[-1]
    color = "#3fb950" if last >= 0 else "#f85149"
    marker = ""
    if worst and worst.get("depth", 0) > 0:
        # trough index = deepest point of that episode
        t_idx = max(range(n), key=lambda i: hwm[i] - equity[i])
        marker = (f'<circle cx="{sx(t_idx):.1f}" cy="{sy(equity[t_idx]):.1f}" r="2.5" '
                  f'fill="none" stroke="#f85149" stroke-width="1.2"/>')
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="vertical-align:middle;display:inline-block">'
        f'<line x1="{pad}" y1="{zero_y:.1f}" x2="{width - pad}" y2="{zero_y:.1f}" '
        f'stroke="#8b949e" stroke-width="0.8" stroke-dasharray="2,2" opacity="0.5"/>'
        f'<polygon points="{gap}" fill="#f85149" fill-opacity="0.18"/>'
        f'<polyline points="{hwm_pts}" fill="none" stroke="#d29922" stroke-width="1" '
        f'stroke-dasharray="3,2" opacity="0.9"/>'
        f'<polyline points="{eq_pts}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f'{marker}'
        f'<circle cx="{sx(n - 1):.1f}" cy="{sy(last):.1f}" r="2" fill="{color}"/>'
        f'</svg>'
    )


def _fmt_day(ts) -> str:
    """'2026-08-12T15:20' -> '12 Aug'."""
    try:
        return datetime.fromisoformat(str(ts)).strftime("%-d %b")
    except (TypeError, ValueError):
        return "—"


def _render_utilisation_svg(rows: list[dict], capital: float,
                            width: int = 300, height: int = 70) -> str:
    """Capital utilisation over trading days. Blue line = utilisation %
    (vs the compounding available capital, scaled to its own peak). Gold line =
    gross deployed ₹ scaled against *total capital* (0 = idle, top = fully
    deployed), with a dashed ceiling at the capital limit. Scaling deployed ₹ on
    the absolute capital axis — rather than its own range — keeps it from
    collapsing onto the utilisation line; the gap between the two shows the
    effect of compounding realised P&L on available capital."""
    if len(rows) < 2:
        return "<span class='dim'>—</span>"
    util_vals = [r["avg_util_pct"] for r in rows]
    dep_vals = [r["avg_deployed"] for r in rows]
    pad = 4
    n = len(rows)

    def sx(i: int) -> float:
        return pad + (i / (n - 1)) * (width - 2 * pad)

    u_hi = max(max(util_vals), 1.0)
    cap = capital or max(max(dep_vals), 1.0)

    def syu(v: float) -> float:
        return pad + (1 - v / u_hi) * (height - 2 * pad)

    def syd(v: float) -> float:
        return pad + (1 - min(v / cap, 1.0)) * (height - 2 * pad)

    upts = " ".join(f"{sx(i):.1f},{syu(v):.1f}" for i, v in enumerate(util_vals))
    dpts = " ".join(f"{sx(i):.1f},{syd(v):.1f}" for i, v in enumerate(dep_vals))
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="vertical-align:middle;display:inline-block">'
        f'<line x1="{pad}" y1="{pad}" x2="{width - pad}" y2="{pad}" '
        f'stroke="#d29922" stroke-width="0.8" stroke-dasharray="2,2" opacity="0.4"/>'
        f'<polyline points="{dpts}" fill="none" stroke="#d29922" stroke-width="1.5"/>'
        f'<polyline points="{upts}" fill="none" stroke="#58a6ff" stroke-width="1.5"/>'
        f'<circle cx="{sx(n - 1):.1f}" cy="{syd(dep_vals[-1]):.1f}" r="2" fill="#d29922"/>'
        f'<circle cx="{sx(n - 1):.1f}" cy="{syu(util_vals[-1]):.1f}" r="2" fill="#58a6ff"/>'
        f'</svg>'
    )


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
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
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

    # Markers can carry a NULL price (completed order with no recorded fill price); skip those.
    buy_markers = [(i, p) for i, p in (buy_markers or []) if p is not None]
    sell_markers = [(i, p) for i, p in (sell_markers or []) if p is not None]
    phantom_markers = [(i, p) for i, p in (phantom_markers or []) if p is not None]
    prices = [c for c in closes if c is not None]
    for ref in [entry_price, sl_price, sell_min_price, trail_price, trail_stop_price]:
        if ref:
            prices.append(ref)
    for _, p in buy_markers:
        prices.append(p)
    for _, p in sell_markers:
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


def _parse_ts(_s):
    try:
        return datetime.fromisoformat(_s)
    except (TypeError, ValueError):
        return None


def _load_matched_trades(db_path, instrument: str | None = None):
    """FIFO-match every COMPLETE order (optionally one instrument) into closed
    trades, tagging each SELL leg with its EXIT signal's reason by nearest
    timestamp. A positional queue join drifts whenever a SELL has no recorded
    reason (older exits predate exit_reason logging) or a non-fill EXIT signal
    has no SELL — nearest-time keeps every SELL anchored to the exact signal it
    came from; pre-logging exits correctly stay blank. Returns
    (matched_trades, orders_for_match). Always match on the FULL set, then
    window — never filter raw orders first."""
    from trader.analytics import match_trades
    inst_clause, args = ("", ()) if instrument is None else (" AND instrument = ?", (instrument,))
    raw_orders = _read_db(
        db_path,
        "SELECT instrument, direction, quantity, price, placed_at "
        "FROM orders WHERE status='COMPLETE'" + inst_clause + " ORDER BY placed_at",
        args,
    )
    exit_reasons = _read_db(
        db_path,
        "SELECT instrument, logged_at, exit_reason FROM signals "
        "WHERE signal_type='EXIT'" + inst_clause + " ORDER BY logged_at",
        args,
    )
    exit_sigs: dict[str, list] = defaultdict(list)
    for r in exit_reasons:
        dt = _parse_ts(r["logged_at"])
        if dt is not None:
            exit_sigs[r["instrument"]].append((dt, r["exit_reason"]))
    orders_for_match = []
    for o in raw_orders:
        rec = {"instrument": o["instrument"], "direction": o["direction"],
               "quantity": o["quantity"], "price": o["price"], "ts": o["placed_at"]}
        if o["direction"] == "SELL":
            sigs = exit_sigs.get(o["instrument"])
            odt = _parse_ts(o["placed_at"])
            if sigs and odt is not None:
                _dt, reason = min(sigs, key=lambda x: abs((x[0] - odt).total_seconds()))
                if reason is not None:
                    rec["exit_reason"] = reason
        orders_for_match.append(rec)
    return match_trades(orders_for_match), orders_for_match


def _render_return_row(ret: dict, bench: dict, capital: float, util_pct: float,
                       pnl_class, tm: dict | None = None) -> str:
    """Compact stat row under the Cumulative P&L headline: cum return,
    annualized (with on-deployed secondary), incl.-open MTM, Nifty 50 benchmark
    (buy-and-hold on full capital + the trade-matched counterfactual `tm`).
    Empty string when there is no return to show."""
    if ret.get("cum_pct") is None:
        return ""

    def _pct(v, suffix=""):
        return "—" if v is None else f"{v:+.1f}%{suffix}"

    min_days = int(ret["min_days"])
    days = ret["days"] or 0.0
    na_ann = (f'<span class="dim" title="annualized only once the window spans '
              f'{min_days}+ days">— p.a. (&lt;{min_days} d)</span>')

    def _ann(v):
        return (f'<span class="{pnl_class(v)}">{_pct(v, " p.a.")}</span>'
                if v is not None else na_ann)

    cum_tile = (f'<div><div class="dim k">Cum return</div>'
                f'<div class="v {pnl_class(ret["cum_pct"])}">{_pct(ret["cum_pct"])}</div>'
                f'<div class="dim s">on &#8377;{capital:,.0f} · {days:.0f} d</div></div>')
    if ret.get("deployed_cum_pct") is not None:
        dep_s = (f'on deployed ({util_pct:.0f}%): {_pct(ret["deployed_cum_pct"])}'
                 f' · {_pct(ret["deployed_ann_pct"], " p.a.") if ret["deployed_ann_pct"] is not None else "—"}')
    else:
        dep_s = "on deployed: —"
    ann_tile = (f'<div><div class="dim k">Annualized</div>'
                f'<div class="v">{_ann(ret["ann_pct"])}</div>'
                f'<div class="dim s">{dep_s}</div></div>')
    if ret.get("mtm_cum_pct") is not None:
        mtm_tile = (f'<div><div class="dim k">Incl. open</div>'
                    f'<div class="v {pnl_class(ret["mtm_cum_pct"])}">{_pct(ret["mtm_cum_pct"])}</div>'
                    f'<div class="dim s">{_ann(ret["mtm_ann_pct"])} · realised + unrealised</div></div>')
    else:
        mtm_tile = ""
    tm = tm or {}
    if tm.get("pnl") is not None:
        tm_diff = tm["our_gross_pct"] - tm["pct"]
        tm_line = (f'<div class="dim s">trade-matched: '
                   f'<span class="{pnl_class(tm["pnl"])}">&#8377;{tm["pnl"]:+,.0f} ({tm["pct"]:+.1f}%)</span>'
                   f' on &#8377;{tm["notional"]:,.0f} · ours gross {tm["our_gross_pct"]:+.1f}% → '
                   f'<span class="{pnl_class(tm_diff)}">{tm_diff:+.1f} pp</span>'
                   f'{" · " + str(tm["skipped"]) + " unpriced" if tm.get("skipped") else ""}</div>')
    else:
        tm_line = ""
    if bench.get("cum_pct") is not None:
        if ret["ann_pct"] is not None and bench["ann_pct"] is not None:
            diff = ret["ann_pct"] - bench["ann_pct"]
            diff_s = f"ours {diff:+.1f} pp p.a."
        else:
            diff = ret["cum_pct"] - bench["cum_pct"]
            diff_s = f"ours {diff:+.1f} pp cum"
        bench_tile = (f'<div><div class="dim k">Nifty 50 (buy &amp; hold)</div>'
                      f'<div class="v {pnl_class(bench["cum_pct"])}">{_pct(bench["cum_pct"])}</div>'
                      f'<div class="dim s">{_ann(bench["ann_pct"])} · '
                      f'<span class="{pnl_class(diff)}">{diff_s}</span></div>{tm_line}</div>')
    else:
        bench_tile = ('<div><div class="dim k">Nifty 50 (buy &amp; hold)</div>'
                      '<div class="v dim">—</div>'
                      f'<div class="dim s">no daily candles cached for the window yet</div>{tm_line}</div>')
    return f'<div class="retrow">{cum_tile}{ann_tile}{mtm_tile}{bench_tile}</div>'


def _render_rolling_row(rows: list[dict], pnl_class) -> str:
    """Mini table of rolling windows (1M / 3M / Inception): trades, net ₹,
    return, annualized (blank under the guard), Nifty buy-and-hold, and the
    delta. Independent of the range filter. Empty when nothing has traded."""
    if not any(r["ret"].get("cum_pct") is not None for r in rows):
        return ""

    def _pct(v, suffix=""):
        return "—" if v is None else f"{v:+.1f}%{suffix}"

    body = ""
    for r in rows:
        ret, b = r["ret"], r["bench"]
        cum, ann = ret.get("cum_pct"), ret.get("ann_pct")
        days = ret.get("days")
        lbl = r["label"] + (f' <span class="dim">({days:.0f} d)</span>' if days and r["label"] == "Inception" else "")
        if cum is None:
            body += (f"<tr><td>{lbl}</td><td class='dim'>0</td><td class='dim'>—</td>"
                     f"<td class='dim'>—</td><td class='dim'>—</td><td class='dim'>—</td><td class='dim'>—</td></tr>")
            continue
        ann_s = (f"<span class='{pnl_class(ann)}'>{_pct(ann)}</span>" if ann is not None
                 else f"<span class='dim' title='under the {int(ret['min_days'])}-day guard'>—</span>")
        if b.get("cum_pct") is not None:
            nifty_s = f"<span class='{pnl_class(b['cum_pct'])}'>{_pct(b['cum_pct'])}</span>"
            d = cum - b["cum_pct"]
            delta_s = f"<span class='{pnl_class(d)}'>{d:+.1f} pp</span>"
        else:
            nifty_s = delta_s = "<span class='dim'>—</span>"
        body += (f"<tr><td>{lbl}</td><td class='dim'>{r['n']}</td>"
                 f"<td class='{pnl_class(r['net'])}'>&#8377;{r['net']:+,.0f}</td>"
                 f"<td class='{pnl_class(cum)}'>{_pct(cum)}</td><td>{ann_s}</td>"
                 f"<td>{nifty_s}</td><td>{delta_s}</td></tr>")
    return f"""<table class="t-roll" style="margin:4px 0 8px">
        <tr><th>Rolling</th><th>Trades</th><th>Net</th><th>Return</th><th>p.a.</th>
            <th>Nifty B&amp;H</th><th>&Delta;</th></tr>{body}</table>"""


def _build_chart(instrument: str, config, width: int = 1100, height: int = 480):
    """Price chart (closes since 3 days before entry, or full cached history)
    with fill markers, in-position phantom signals and the strategy's levels.
    Returns (chart_svg, meta_parts, n_candles); chart_svg is None when there is
    not enough candle data. Shared by /chart/<sym> and /stock/<sym>."""
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
        return None, [], len(candle_rows)

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
        width=width, height=height,
    )

    last_close = closes[-1]
    meta_parts = []
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
    return chart_svg, meta_parts, len(candle_rows)


def render_chart_page(instrument: str, store, config) -> str:
    sym = instrument.split(":")[-1]
    chart_svg, meta_parts, _n = _build_chart(instrument, config)
    if chart_svg is None:
        return (
            f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{sym}</title>"
            f"<style>{_CSS}</style></head><body>"
            f"<p class='dim'>Not enough candle data for {instrument}.</p>"
            f"<a href='/' class='chart-link'>← Dashboard</a></body></html>"
        )
    meta_parts = ['<a href="/" class="chart-link">← Dashboard</a>',
                  f'<a href="/stock/{sym}" class="chart-link">{sym} drilldown</a>'] + meta_parts
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


def render_page(bot_state, risk, store, config, range_params=None) -> str:
    now = _now_ist()
    market = _market_status(now)

    # ── date range (URL params; persists across the meta-refresh for free) ─────
    _lo, _hi, _range_label, _range_key = _resolve_range(range_params)
    # SQL queries hit naive process-local timestamps; convert the IST window back.
    _lo_local = (_lo - _NAIVE_TO_IST_DELTA) if _lo else None
    _hi_local = (_hi - _NAIVE_TO_IST_DELTA) if _hi else None

    _tok = getattr(bot_state, "token_status", None) or {}

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
        "pattern_top_trailing, addon_lots "
        "FROM open_positions ORDER BY entry_time ASC",
    )
    import json as _json
    for _p in positions:
        _p["addon_lots"] = _json.loads(_p["addon_lots"]) if _p.get("addon_lots") else []
    pending_orders = list(risk._pending_orders.keys())

    # ── orders in range (defaults to most-recent 20 when all-time) ─────────────
    if _lo_local or _hi_local:
        orders = _read_db(
            config.db_path,
            "SELECT instrument, direction, quantity, price, status, placed_at "
            "FROM orders WHERE placed_at >= ? AND placed_at <= ? "
            "ORDER BY placed_at DESC LIMIT 100",
            ((_lo_local or datetime.min).isoformat(), (_hi_local or datetime.max).isoformat()),
        )
    else:
        orders = _read_db(
            config.db_path,
            "SELECT instrument, direction, quantity, price, status, placed_at "
            "FROM orders ORDER BY placed_at DESC LIMIT 20",
        )

    # ── closed trade history (FIFO-matched so scale-out partials split correctly) ──
    # A 7-share entry exited as 4 + 3 must show as two trades (4 and 3) with their
    # own P&L — the old row-number BUY↔SELL join reported the entry qty (7) and
    # dropped the remainder leg. match_trades does proper FIFO lot accounting.
    from trader.analytics import (match_trades, compute_utilisation,
                                  exit_reason_breakdown, per_stock_scorecard,
                                  drawdown_stats, position_exit_legs,
                                  position_entry_legs)

    _matched, _orders_for_match = _load_matched_trades(config.db_path)
    # FIFO matched on the FULL order set above; NOW restrict to the date window.
    # Everything below derived from closed trades uses the windowed set; only
    # capital utilisation keeps the full set (overlap handled inside its from/to).
    _windowed = _filter_trades(_matched, _lo, _hi)

    closed_trades = sorted(
        _windowed, key=lambda t: str(t.get("exit_time") or ""), reverse=True
    )[:30]

    # ── recent signals (date-bounded server-side; logged_at is process-local) ──
    _sig_clause, _sig_args = "", ()
    if _lo_local or _hi_local:
        _sig_clause = " AND logged_at >= ? AND logged_at <= ?"
        _sig_args = ((_lo_local or datetime.min).isoformat(), (_hi_local or datetime.max).isoformat())
    signals = _read_db(
        config.db_path,
        "SELECT logged_at, instrument, direction, signal_type, price_hint, accepted, reject_reason, exit_reason "
        "FROM signals WHERE (reject_reason IS NULL OR reject_reason NOT LIKE 'FILTER:%')"
        + _sig_clause + " ORDER BY id DESC LIMIT 20",
        _sig_args,
    )
    filtered_signals = _read_db(
        config.db_path,
        "SELECT logged_at, instrument, direction, signal_type, price_hint, reject_reason "
        "FROM signals WHERE reject_reason LIKE 'FILTER:%'"
        + _sig_clause + " ORDER BY id DESC LIMIT 30",
        _sig_args,
    )

    # ── capital utilisation (over time) ──────────────────────────────────────
    # Built from the FULL matched set + open positions; the window is applied
    # *inside* compute_utilisation (from/to) so a position opened before the
    # window but still open during it correctly counts as deployed capital.
    _all_for_util = sorted(_matched, key=lambda t: str(t.get("entry_time") or ""))
    util_trades = []
    for t in _all_for_util:
        ed, xd = _parse_ist_naive(t["entry_time"]), _parse_ist_naive(t["exit_time"])
        # Skip rows with a NULL fill price / qty — some completed orders carry no
        # recorded price; None * qty would crash compute_utilisation.
        if ed and xd and t["entry_price"] is not None and t["quantity"] is not None:
            util_trades.append({
                "entry": t["entry_price"], "exit": t["exit_price"], "qty": t["quantity"],
                "pnl": t["gross_pnl"] or 0.0, "entry_date": ed, "exit_date": xd,
            })
    # Currently-open positions still tie up capital → count as deployed through "now".
    _now_naive = _now_ist().replace(tzinfo=None)
    for p in positions:
        ed = _parse_ist_naive(p["entry_time"])
        if ed and p["entry_price"] is not None and p["quantity"] is not None:
            util_trades.append({
                "entry": p["entry_price"], "exit": p["entry_price"], "qty": p["quantity"],
                "pnl": 0.0, "entry_date": ed, "exit_date": _now_naive,
            })
    util = compute_utilisation(util_trades, total, from_dt=_lo, to_dt=_hi, bucket="day")

    # Equity curve: cumulative gross P&L over the WINDOWED closed trades, ordered
    # by exit time. Baseline resets to 0 at the window start — this is "P&L in
    # range", distinct from the lifetime cumulative_pnl on the Persistent State card.
    _closed_sorted = sorted(
        (t for t in _windowed if _parse_ist_naive(t["exit_time"])),
        key=lambda t: _parse_ist_naive(t["exit_time"]),
    )
    equity_vals, net_equity_vals, _cum, _cum_net = [], [], 0.0, 0.0
    for t in _closed_sorted:
        _gross = t["gross_pnl"] or 0.0
        _ep = t.get("entry_price") or 0.0
        _xp = t.get("exit_price") or 0.0
        _q = t.get("quantity") or 0
        _tc = round_trip_cost(config.product, _q, _ep, _xp) if (_ep and _xp and _q) else 0.0
        _cum += _gross
        _cum_net += _gross - _tc
        t["net_pnl"] = _gross - _tc      # consumed by drawdown_stats(pnl_key="net_pnl")
        equity_vals.append(_cum)
        net_equity_vals.append(_cum_net)
    equity_total = _cum
    net_equity_total = _cum_net

    # ── strategy config ───────────────────────────────────────────────────────
    lr = config.strategy_config("lr_extrema")

    # ── build sections ────────────────────────────────────────────────────────

    # ── date-range control (quick filters + custom picker) ─────────────────────
    _from_val = _lo.strftime("%Y-%m-%d") if _lo else ""
    _to_val = (_hi or now.replace(tzinfo=None)).strftime("%Y-%m-%d")

    def _rbtn(key, label):
        cls = "rbtn active" if key == _range_key else "rbtn"
        return f'<a href="/?range={key}" class="{cls}">{label}</a>'

    range_controls = f"""
        <span class="rangebar">
            <span class="dim" style="font-size:11px">Range:</span>
            {_rbtn("1w", "1W")}{_rbtn("1m", "1M")}{_rbtn("1q", "1Q")}{_rbtn("1y", "1Y")}{_rbtn("all", "All")}
            <form method="GET" action="/" style="display:inline-flex;gap:4px;margin-left:6px;align-items:center">
                <input type="date" name="from" value="{_from_val}">
                <input type="date" name="to" value="{_to_val}">
                <button type="submit" class="rbtn{' active' if _range_key == 'custom' else ''}">Apply</button>
            </form>
        </span>"""

    # ── health strip: "is something wrong?" in one line ───────────────────────
    # Red only when non-zero. Sources: today's REJECTED orders (broker), today's
    # ACCEPTED signals that never produced an order row (placement failures —
    # Kite refused before assigning an id, e.g. CAS / network), model saturation
    # (P(buy) pinned at 1.0 = stale-model failure mode), stale tick, token, halt.
    _today_local = (now.replace(tzinfo=None) - _NAIVE_TO_IST_DELTA).replace(hour=0, minute=0, second=0, microsecond=0)
    _rej_today = _read_db(
        config.db_path,
        "SELECT instrument FROM orders WHERE status = 'REJECTED' AND placed_at >= ?",
        (_today_local.isoformat(),),
    )
    _acc_today = _read_db(
        config.db_path,
        "SELECT instrument, logged_at FROM signals WHERE accepted = 1 AND logged_at >= ?",
        (_today_local.isoformat(),),
    )
    _ord_today = _read_db(
        config.db_path,
        "SELECT instrument, placed_at FROM orders WHERE placed_at >= ?",
        (_today_local.isoformat(),),
    )
    _ord_ts: dict[str, list] = defaultdict(list)
    for _o in _ord_today:
        _d = _parse_ts(_o["placed_at"])
        if _d is not None:
            _ord_ts[_o["instrument"]].append(_d)
    _unplaced = []
    for _a in _acc_today:
        _d = _parse_ts(_a["logged_at"])
        if _d is None:
            continue
        if not any(abs((_x - _d).total_seconds()) <= 120 for _x in _ord_ts.get(_a["instrument"], [])):
            _unplaced.append(_a["instrument"].split(":")[-1])
    _saturated = [
        _sym.split(":")[-1] for _sym, _ms in (getattr(bot_state, "model_scores", {}) or {}).items()
        if (_ms.get("p_min") or 0.0) >= 0.999
    ]
    _health = []   # (label, kind, href)
    if halted:
        _health.append(("HALTED — daily loss limit", "red", "#pnl"))
    if _tok and not _tok.get("valid"):
        _health.append(("Kite token INVALID", "red", "#state"))
    if tick_stale and market == "OPEN":
        _health.append(("no ticks > 10 min", "red", None))
    if _rej_today:
        _health.append((f"{len(_rej_today)} broker reject{'s' if len(_rej_today) > 1 else ''} today "
                        f"({', '.join(sorted({r['instrument'].split(':')[-1] for r in _rej_today}))})",
                        "red", "#orders"))
    if _unplaced:
        _health.append((f"{len(_unplaced)} accepted signal{'s' if len(_unplaced) > 1 else ''} never placed "
                        f"({', '.join(sorted(set(_unplaced)))}) — CAS / placement failure", "red", "#signals"))
    if _saturated:
        _health.append((f"model saturated P(buy)=1.0: {', '.join(sorted(_saturated))}", "orange", "#watchlist"))
    if pending_orders:
        _health.append((f"{len(pending_orders)} pending order{'s' if len(pending_orders) > 1 else ''}", "dim", "#positions"))
    if _health:
        _items = "".join(
            (f'<a href="{href}" style="text-decoration:none">{_badge(lbl, kind)}</a>' if href else _badge(lbl, kind))
            for lbl, kind, href in _health
        )
        health_strip = f'<div class="meta" style="margin-bottom:10px;line-height:2">Health: {_items}</div>'
    else:
        health_strip = (f'<div class="meta" style="margin-bottom:10px">Health: {_badge("ALL CLEAR", "green")}'
                        f' <span class="dim" style="font-size:11px">no rejects, no unplaced signals, '
                        f'model sane, ticks fresh</span></div>')

    header = f"""
    <h1>Trader Dashboard</h1>
    <div class="meta">
        {mode_badge} {market_badge} {status_badge}
        &nbsp;·&nbsp; {now.strftime("%d %b %Y, %H:%M:%S IST")}
        &nbsp;·&nbsp; uptime {uptime_str}
        &nbsp;·&nbsp; last tick: {'<span class="red">'+tick_str+'</span>' if tick_stale else tick_str}
        &nbsp;·&nbsp; <span id="refresh-note" style="font-size:11px">auto-refresh 30s</span>
    </div>
    <div class="meta hdr">
        <span style="font-size:11px">Showing <span class="val">{len(_windowed)}</span> closed trades
            &nbsp;·&nbsp; <span class="orange">{_range_label}</span></span>
        {range_controls}
        <label class="m-only"><input type="checkbox" id="allcols"> all columns</label>
    </div>
    {health_strip}"""

    # Scale-in pool row — shown only when the feature is on (or money is still parked)
    _si_deployed = getattr(risk, "scale_in_deployed", 0.0)
    _si_budget = config.scale_in_budget if getattr(config, "scale_in_enabled", False) else 0.0
    if _si_budget or _si_deployed:
        _si_pct = (_si_deployed / _si_budget * 100) if _si_budget else 100.0
        scale_in_row = (
            f'<tr><td class="dim">Scale-in pool</td><td class="val">&#8377; {_si_deployed:,.0f}'
            f' <span class="dim">/ &#8377;{_si_budget:,.0f} ({_si_pct:.0f}%)</span></td></tr>'
        )
    else:
        scale_in_row = ""

    capital_card = f"""
    <div class="card">
        <h2>Capital</h2>
        <table>
            <tr><td class="dim">Total</td><td class="val">&#8377; {total:,.0f}</td></tr>
            <tr><td class="dim">Deployed</td><td class="val">&#8377; {deployed:,.0f}
                <span class="dim">({deploy_pct:.0f}%)</span></td></tr>
            <tr><td class="dim">Pending lock</td><td class="val">&#8377; {pending_amt:,.0f}</td></tr>
            <tr><td class="dim">Available</td><td class="val green">&#8377; {available:,.0f}</td></tr>
            {scale_in_row}
        </table>
        <div class="bar-bg"><div class="bar-fill {bar_danger}" style="width:{bar_w}%"></div></div>
    </div>"""

    total_unrealised = sum((p.get("unrealised_pnl") or 0.0) for p in positions)
    unreal_sign = "+" if total_unrealised >= 0 else ""

    pnl_sign = "+" if realised >= 0 else ""
    pnl_card = f"""
    <div class="card">
        <h2 id="pnl">P&amp;L Today</h2>
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

    # ── capital utilisation panel (over time) ──
    _o = util["overall"]
    _u_rows = util["monthly"]   # full daily series for the chart
    if len(_u_rows) >= 2:
        util_section = f"""
    <div class="card">
        <h2>Capital Utilisation (gross, daily)</h2>
        <div class="dim" style="margin-bottom:6px;font-size:11px">
            time-avg {_o['time_avg_util_pct']:.0f}% &nbsp;·&nbsp; peak {_o['peak_util_pct']:.0f}%
            &nbsp;·&nbsp; peak deployed &#8377;{_o['peak_deployed']:,.0f}
            &nbsp;·&nbsp; peak pos {_o['peak_positions']}/{config.max_open_positions}
        </div>
        {_render_utilisation_svg(_u_rows, total)}
        <div class="dim" style="font-size:11px;margin-top:4px">
            <span style="color:#58a6ff">&#9632;</span> utilisation %
            &nbsp;·&nbsp; <span style="color:#d29922">&#9632;</span> deployed &#8377; (vs &#8377;{total:,.0f} cap)
        </div>
    </div>"""
    else:
        util_section = ""

    # ── return stats (cumulative + annualized) + Nifty 50 benchmark ───────────
    # Span anchors: start = later of the window start and the FIRST fill (idle
    # time before the bot's first trade must not dilute the figure); end = now
    # while the window is live (capital stays at risk), else the window end.
    # Headline is realised net on config capital; "on deployed" uses the
    # window's time-avg utilisation; "incl. open" adds today's unrealised P&L
    # (only meaningful for a window that reaches now). Annualized figures blank
    # below ANNUALIZE_MIN_DAYS — see trader/analytics.py::return_stats.
    from trader.analytics import (return_stats, benchmark_return, trade_matched_benchmark,
                                  benchmark_equity, BENCHMARK_INSTRUMENT)
    _now_n = now.replace(tzinfo=None)
    _fill_times = [_parse_ist_naive(t["entry_time"]) for t in _matched if t.get("entry_time")]
    _fill_times += [_parse_ist_naive(p["entry_time"]) for p in positions if p.get("entry_time")]
    _fill_times = [d for d in _fill_times if d]
    _first_fill = min(_fill_times) if _fill_times else None
    if _lo and _first_fill:
        _ret_start = max(_lo, _first_fill)
    else:
        _ret_start = _lo or _first_fill
    _window_live = _hi is None or _hi >= _now_n
    _ret_end = _now_n if _window_live else _hi
    _open_unreal = sum((p.get("unrealised_pnl") or 0.0) for p in positions)
    _ret = return_stats(
        net_equity_total, total, _ret_start, _ret_end,
        time_avg_util_pct=_o["time_avg_util_pct"],
        unrealised_pnl=_open_unreal if _window_live else None,
    )
    _bench = benchmark_return([])
    _bench_rows: list[dict] = []
    if _ret_start and _ret_end:
        _bench_rows = _read_db(
            config.db_path,
            "SELECT timestamp, close FROM candles WHERE instrument = ? AND timeframe = 'day' "
            "AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC",
            (BENCHMARK_INSTRUMENT,
             _ret_start.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
             _ret_end.isoformat()),
        )
        _bench = benchmark_return(_bench_rows)
    # Trade-matched counterfactual: same notional, same entry/exit days, in
    # Nifty. Windowed trades are filtered by EXIT time, so an entry can predate
    # the window — pull closes from the earliest entry, not the window start.
    _tm = trade_matched_benchmark([], [])
    _tm_rows: list[dict] = []
    _tm_entries = [_parse_ist_naive(t["entry_time"]) for t in _windowed if t.get("entry_time")]
    _tm_entries = [d for d in _tm_entries if d]
    if _tm_entries:
        _tm_rows = _read_db(
            config.db_path,
            "SELECT timestamp, close FROM candles WHERE instrument = ? AND timeframe = 'day' "
            "AND timestamp >= ? ORDER BY timestamp ASC",
            (BENCHMARK_INSTRUMENT,
             (min(_tm_entries) - timedelta(days=7)).replace(hour=0, minute=0, second=0).isoformat()),
        )
        _tm = trade_matched_benchmark(_windowed, _tm_rows)
    ret_row = _render_return_row(_ret, _bench, total, _o["time_avg_util_pct"], _pnl_class, _tm)
    # Nifty B&H ₹ on full capital, marked at each closed trade's exit → same
    # trade-indexed x-axis as the equity curve (rebased to 0 at the window start).
    _bench_eq = benchmark_equity(
        _bench_rows, [_parse_ist_naive(t["exit_time"]) for t in _closed_sorted], total,
    ) if _bench_rows else []

    # ── rolling windows, INDEPENDENT of the range filter ────────────────────
    # "Is the edge holding recently?" without touching the range buttons: 1M /
    # 3M / since-inception, each with realised-net return, annualized (blank
    # under the 90-day guard), and Nifty buy-and-hold over the same span.
    _roll_bench_rows: list[dict] = []
    if _first_fill:
        _roll_bench_rows = _read_db(
            config.db_path,
            "SELECT timestamp, close FROM candles WHERE instrument = ? AND timeframe = 'day' "
            "AND timestamp >= ? ORDER BY timestamp ASC",
            (BENCHMARK_INSTRUMENT,
             _first_fill.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()),
        )
    _roll_rows = []
    for _label, _days in (("1M", 30), ("3M", 90), ("Inception", None)):
        _rlo = ((_now_n - timedelta(days=_days)).replace(hour=0, minute=0, second=0, microsecond=0)
                if _days else None)
        _rtrades = _filter_trades(_matched, _rlo, None)
        _rnet = 0.0
        for t in _rtrades:
            _ep, _xp, _q = t.get("entry_price") or 0.0, t.get("exit_price") or 0.0, t.get("quantity") or 0
            _rnet += (t.get("gross_pnl") or 0.0) - (
                round_trip_cost(config.product, _q, _ep, _xp) if (_ep and _xp and _q) else 0.0)
        if _rlo and _first_fill:
            _rstart = max(_rlo, _first_fill)
        else:
            _rstart = _rlo or _first_fill
        _rutil = 0.0
        if _rstart and util_trades:
            _rutil = compute_utilisation(util_trades, total, from_dt=_rstart, to_dt=_now_n,
                                         bucket="day")["overall"]["time_avg_util_pct"]
        _rret = return_stats(_rnet, total, _rstart, _now_n, time_avg_util_pct=_rutil)
        _rb = benchmark_return([])
        if _rstart:
            _rs_iso = _rstart.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            _rb = benchmark_return([r for r in _roll_bench_rows if str(r["timestamp"]) >= _rs_iso])
        _roll_rows.append({"label": _label, "n": len(_rtrades), "net": _rnet,
                           "ret": _rret, "bench": _rb})
    roll_row = _render_rolling_row(_roll_rows, _pnl_class)

    # ── cumulative P&L + drawdown panel (merged, #7) ──
    _dd = drawdown_stats(_windowed, config.total_capital, now=_now_n, pnl_key="net_pnl")
    _eq_left = ""
    if equity_vals:
        _eq_sign = "+" if equity_total >= 0 else ""
        _net_sign = "+" if net_equity_total >= 0 else ""
        _eq_costs = equity_total - net_equity_total
        _eq_left = f"""
            <h3 style="font-size:13px;margin:4px 0">Cumulative P&amp;L</h3>
            <div class="val {_pnl_class(net_equity_total)}" style="font-size:18px">
                &#8377; {_net_sign}{net_equity_total:,.0f}
                <span class="dim" style="font-size:11px;font-weight:normal">net of costs</span></div>
            <div class="dim" style="font-size:11px;margin-bottom:6px">
                gross {_eq_sign}&#8377;{equity_total:,.0f} &minus; costs &#8377;{_eq_costs:,.0f}
                &nbsp;·&nbsp; {len(equity_vals)} closed trades</div>
            {ret_row}
            {roll_row}
            {_render_equity_sparkline(equity_vals, net_equity_vals, bench_values=_bench_eq)}
            <div class="dim" style="font-size:11px;margin-top:2px">
                <span style="color:#58a6ff">&#9644;</span> Nifty B&amp;H on &#8377;{total:,.0f}, at our exit dates
                &nbsp;·&nbsp; <span style="color:#8b949e">&#9476;</span> gross
                &nbsp;·&nbsp; <span style="color:{'#3fb950' if net_equity_total >= 0 else '#f85149'}">&#9644;</span> net</div>"""
    _dd_right = ""
    if _dd["underwater"]:
        _cap_n = config.total_capital or 0.0
        _ep = _dd["last_episode"]
        _worst = _dd["episodes"][0] if _dd["episodes"] else None
        if _dd["state"] == "underwater" and _ep:
            _dd_kind = "red"
            _sentence = (f"Still <b>&#8377;{_dd['current_dd']:,.0f}</b> "
                         f"({_dd['current_dd_pct']:.1f}% of capital) below the "
                         f"&#8377;{_dd['peak']:,.0f} peak of {_fmt_day(_ep['peak_time'])} "
                         f"&mdash; {_dd['days_in_drawdown']} days and counting"
                         + (f"; deepest so far &#8377;{_ep['depth']:,.0f} on "
                            f"{_fmt_day(_ep['trough_time'])}." if _ep['depth'] > _dd['current_dd'] + 0.5 else "."))
        elif _ep:
            _dd_kind = "green"
            _sentence = (f"<b>At a new high</b> (&#8377;{_dd['peak']:,.0f}). The last giveback "
                         f"&mdash; &#8377;{_ep['depth']:,.0f} ({_ep['depth_pct']:.1f}%), "
                         f"{_fmt_day(_ep['peak_time'])} &rarr; {_fmt_day(_ep['trough_time'])} &mdash; "
                         f"was recovered on {_fmt_day(_ep['recovery_time'])} after "
                         f"{_ep['days_underwater']} days.")
        else:
            _dd_kind = "green"
            _sentence = (f"<b>At a new high</b> (&#8377;{_dd['peak']:,.0f}) and never below it "
                         f"&mdash; nothing given back yet.")
        _ep_rows = ""
        for e in _dd["episodes"][:3]:
            _rec = ("<span class='red'>ongoing</span>" if e["ongoing"]
                    else _fmt_day(e["recovery_time"]))
            _ep_rows += (f"<tr><td>{_fmt_day(e['peak_time'])} &rarr; {_fmt_day(e['trough_time'])}"
                         f" &rarr; {_rec}</td>"
                         f"<td class='val red'>&#8377;{e['depth']:,.0f} "
                         f"<span class='dim'>({e['depth_pct']:.1f}%)</span></td>"
                         f"<td class='val'>{e['days_underwater']}</td></tr>")
        _open_line = ""
        if _window_live and positions:
            _mtm_below = _dd["current_dd"] - _open_unreal
            _mtm_txt = (f"&#8377;{_mtm_below:,.0f} below the peak" if _mtm_below > 0
                        else f"&#8377;{-_mtm_below:,.0f} above it")
            _open_line = (f"<div class='dim' style='font-size:11px;margin-top:4px'>"
                          f"Incl. open positions ({'+' if _open_unreal >= 0 else ''}&#8377;{_open_unreal:,.0f} "
                          f"unrealised, not yet banked): {_mtm_txt} if closed now.</div>")
        _dd_right = f"""
            <h3 style="font-size:13px;margin:4px 0">Giveback from peak
                <span class="dim" style="font-weight:normal">(drawdown)</span></h3>
            <div class="{_dd_kind}" style="font-size:12px;line-height:1.5;margin-bottom:4px">{_sentence}</div>
            {_render_giveback_svg(_dd['equity'], _dd['hwm'], _worst)}
            <div class="dim" style="font-size:11px;margin:2px 0 6px">
                <span style="color:#d29922">&#9476;</span> best-so-far (high-water mark)
                &nbsp;·&nbsp; <span style="color:#f85149">&#9644;</span> shaded = banked profit handed back
                &nbsp;·&nbsp; &#9675; deepest point</div>
            <table class="t-giveback">
                <tr><th>peak &rarr; trough &rarr; recovered</th><th>given back</th><th>days under</th></tr>
                {_ep_rows}
            </table>
            {_open_line}
            <div class="dim" style="font-size:11px;margin-top:6px">
                Net of costs, closed trades only. Giveback measures realised profit handed back since
                its best point &mdash; it is not a loss against starting capital unless the curve is
                below the dotted zero line. Worst ever: &#8377;{_dd['max_dd']:,.0f}
                ({_dd['max_dd_pct']:.1f}% of &#8377;{_cap_n:,.0f}).</div>"""
    if _eq_left or _dd_right:
        equity_section = f"""
    <div class="card full">
        <h2>Cumulative P&amp;L &amp; Giveback <span class="dim"
            style="font-weight:normal;text-transform:none">· net of costs</span></h2>
        <div style="display:flex;gap:24px;flex-wrap:wrap">
            <div class="pane">{_eq_left}</div>
            <div class="pane">{_dd_right}</div>
        </div>
    </div>"""
    else:
        equity_section = ""

    # ── graph row: capital utilisation + merged P&L/drawdown side by side ──
    _graph_panes = ""
    if util_section:
        _graph_panes += f'<div class="pane">{util_section}</div>'
    if equity_section:
        _graph_panes += f'<div class="pane pane-wide">{equity_section}</div>'
    graph_row = f'<div class="toprow">{_graph_panes}</div>' if _graph_panes else ""

    # ── persistent state panel (day-to-day continuity) ────────────────────────
    _cum_pnl = risk.cumulative_pnl
    _eff_cap = config.total_capital          # runtime effective (post-cap)
    _open_now = {p["instrument"] for p in positions}
    _state_rows = store.read_state()

    _pos_rows, _ctrl_rows = [], []
    for _r in _state_rows:
        _k, _v = _r["key"], _r["value"]
        if _k == "cumulative_pnl":
            continue  # shown live from risk, below
        if _k.endswith((".peak_close", ".max_gain_pct")):
            _inst = _k.rsplit(".", 1)[0]
            _is_stale = _inst not in _open_now
            _tag = " <span class='dim' style='font-size:10px'>(stale)</span>" if _is_stale else ""
            _pos_rows.append(
                f"<tr><td class='dim'>{_k}{_tag}</td><td class='val'>{_v:g}</td></tr>"
            )
        elif _k.endswith(".paused"):
            if _v > 0.5:
                _ctrl_rows.append(
                    f"<tr><td class='dim'>{_k.rsplit('.',1)[0]}</td>"
                    f"<td class='val'>{_badge('PAUSED','orange')}</td></tr>"
                )

    _pos_body = "".join(_pos_rows) or "<tr><td class='dim' colspan='2'>—</td></tr>"
    _ctrl_body = "".join(_ctrl_rows) or "<tr><td class='dim' colspan='2'>none paused</td></tr>"

    # Kite token status (published by main.py: startup / heartbeat / hot-reload)
    if _tok:
        _tok_badge = _badge("VALID", "green") if _tok.get("valid") else _badge("INVALID", "red")
        _tok_checked = _tok.get("checked_at")
        _tok_when = _tok_checked.strftime("%H:%M:%S") if _tok_checked else "—"
        _tok_detail = (f"{_tok.get('user_id') or '—'} · checked {_tok_when}"
                       f" · {_tok.get('source', '')}")
    else:
        _tok_badge, _tok_detail = _badge("UNKNOWN", "orange"), "no check recorded yet"
    token_block = f"""
            <div class="pane-sm">
                <h3 style="font-size:13px;margin:4px 0">Kite token</h3>
                <table>
                    <tr><td class="dim">status</td><td class="val">{_tok_badge}</td></tr>
                    <tr><td class="dim" colspan="2" style="font-size:11px">{_tok_detail}</td></tr>
                </table>
                <form method="POST" action="/token/reload" style="margin-top:6px">
                    <button type="submit" style="font-size:11px;padding:3px 9px;border-radius:3px;
                            border:1px solid #58a6ff;background:#21262d;color:#58a6ff;cursor:pointer">
                        Reload token from .env</button>
                </form>
            </div>"""
    state_section = f"""
    <div class="card full">
        <h2 id="state">Persistent State (carried day-to-day)</h2>
        <div style="display:flex;gap:24px;flex-wrap:wrap">
            <div class="pane-sm">
                <h3 style="font-size:13px;margin:4px 0">Cumulative (lifetime)</h3>
                <table>
                    <tr><td class="dim">cumulative_pnl</td>
                        <td class="val {_pnl_class(_cum_pnl)}">&#8377; {_cum_pnl:,.2f}</td></tr>
                    <tr><td class="dim">effective_capital</td><td class="val">&#8377; {_eff_cap:,.0f}</td></tr>
                    <tr><td class="dim">capital_deployed</td><td class="val">&#8377; {risk.capital_deployed:,.0f}</td></tr>
                    <tr><td class="dim">capital_available</td><td class="val green">&#8377; {risk.capital_available:,.0f}</td></tr>
                </table>
                <form method="POST" action="/reset_pnl" style="margin-top:6px"
                      onsubmit="return confirm('Override lifetime cumulative_pnl?')">
                    <input type="number" step="0.01" name="value" value="0"
                           style="width:110px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:3px;padding:3px">
                    <button type="submit" style="font-size:11px;padding:3px 9px;border-radius:3px;
                            border:1px solid #d29922;background:#21262d;color:#d29922;cursor:pointer">
                        Reset P&amp;L</button>
                </form>
            </div>
            <div class="pane-sm">
                <h3 style="font-size:13px;margin:4px 0">Position state</h3>
                <table>{_pos_body}</table>
            </div>
            <div class="pane-sm">
                <h3 style="font-size:13px;margin:4px 0">Controls</h3>
                <table>{_ctrl_body}</table>
            </div>
            {token_block}
        </div>
    </div>"""

    # Open positions
    _lr_cfg = config.strategy_config("lr_extrema") or {}
    _stop_pct = float(_lr_cfg.get("stop_pct", 3.0))
    _trail_pct = float(_lr_cfg.get("trail_pct", 1.5))
    _hold_bars_max = int(_lr_cfg.get("hold_bars", 200))
    _pos_legs = position_exit_legs(_orders_for_match, positions)  # #14 scale-out lifecycle
    _entry_legs = position_entry_legs(positions)  # scale-in lot ladder

    if positions or pending_orders:
        rows_html = ""
        # Portfolio stop-risk: ₹ given back if every position's EFFECTIVE stop
        # (trail trigger when trailing, else hard stop) hits from the current
        # price. Positive = at risk; negative = already locked in above price.
        _risk_at_risk = 0.0     # sum of positive exposures
        _risk_locked = 0.0      # sum of locked-in gains (stops above price)
        for p in positions:
            sym = p["instrument"].split(":")[-1]
            # Per-stock params: stop/trail/hold limits AND the strategy TF —
            # held_bars counts strategy-TF bars (days for a day-TF stock).
            _pos_cfg = config.get_strategy_params(p["instrument"], "lr_extrema") or {}
            _pos_stop_pct = float(_pos_cfg.get("stop_pct", _stop_pct))
            _pos_trail_pct = float(_pos_cfg.get("trail_pct", _trail_pct))
            _pos_hold_max = int(_pos_cfg.get("hold_bars", _hold_bars_max))
            _pos_tf = config.strategy_timeframe(p["instrument"])
            _pos_aggregated = _pos_tf != config.candle_timeframe
            _tf_badge = (
                f' <span class="badge badge-dim" title="decisions update once per '
                f'{_pos_tf} bar">{_pos_tf.upper()}</span>'
                if _pos_aggregated else ""
            )
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
            sl_price = p["entry_price"] * (1 - _pos_stop_pct / 100)
            trail_trigger = peak * (1 - _pos_trail_pct / 100) if trailing and peak > 0 else None
            # Trail distance: how far current price is above trigger (cushion before stop fires)
            trail_cushion_str = ""
            if trail_trigger and cur > 0:
                cushion_pct = (cur - trail_trigger) / cur * 100
                cushion_color = "orange" if cushion_pct < 1.0 else "dim"
                trail_cushion_str = (
                    f"<br><span class='{cushion_color}' style='font-size:11px'>"
                    f"cushion {cushion_pct:+.2f}%</span>"
                )
            # ₹ to the effective stop × remaining qty → the evening number.
            _eff_stop = trail_trigger if trail_trigger else sl_price
            _risk_rs = (cur - _eff_stop) * (p["quantity"] or 0) if cur > 0 else 0.0
            _risk_pct = _risk_rs / total * 100 if total else 0.0
            if _risk_rs >= 0:
                _risk_at_risk += _risk_rs
                risk_str = (f"<br><span class='red' style='font-size:11px'>at risk &#8377;{_risk_rs:,.0f}"
                            f" <span class='dim'>({_risk_pct:.1f}% cap)</span></span>")
            else:
                _risk_locked += -_risk_rs
                risk_str = (f"<br><span class='green' style='font-size:11px'>locked &#8377;{-_risk_rs:,.0f}"
                            f" <span class='dim'>({-_risk_pct:.1f}% cap)</span></span>")
            stop_cell = (
                f"<span class='red'>&#8377; {sl_price:.2f}</span>"
                + (f"<br><span class='orange' style='font-size:11px'>trail &#8377; {trail_trigger:.2f}</span>"
                   if trail_trigger else "")
                + trail_cushion_str
                + risk_str
            )
            # Hold bars progress bar (strategy-TF units — days for a day-TF stock)
            hold_pct = min(100, int(held / _pos_hold_max * 100)) if _pos_hold_max else 0
            hold_bar_danger = "danger" if hold_pct >= 80 else ""
            _hold_units = (
                f" <span class='dim' style='font-size:10px'>{_pos_tf} bars</span>"
                if _pos_aggregated else ""
            )
            hold_cell = (
                f"{held}/{_pos_hold_max}{_hold_units}"
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

            # Conviction sparkline over the SAME window (entry → now). Reuses the
            # persisted model_scores; per-stock thresholds drive the guide lines.
            # Coverage degrades gracefully — if the position predates the recorded
            # scores the line just starts later (or shows a dash under 2 points).
            conviction_html = "<span class='dim'>—</span>"
            if p.get("entry_time"):
                _pscores = _read_db(
                    config.db_path,
                    "SELECT timestamp, p_min, p_max FROM model_scores "
                    "WHERE instrument = ? AND timestamp >= ? ORDER BY timestamp ASC",
                    (p["instrument"], p["entry_time"]),
                )
                if len(_pscores) >= 2:
                    _pcfg = config.get_strategy_params(p["instrument"], "lr_extrema") or {}
                    conviction_html = _render_prob_sparkline(
                        _pscores,
                        float(_pcfg.get("threshold", 0.70)),
                        float(_pcfg.get("veto_threshold", 0.50)),
                        width=160, height=45,
                    )

            # #14 — scale-out lifecycle sub-line (entry → sold legs → holding remainder)
            legs_html = ""
            _li = _pos_legs.get(p["instrument"])
            if _li:
                _leg_strs = " · ".join(
                    f"sold {l['qty']} @ &#8377;{l['price']:.2f}"
                    f"{' (' + l['reason'] + ')' if l['reason'] else ''}"
                    for l in _li["legs"] if l["price"] is not None
                )
                legs_html = (
                    f"<br><span class='dim' style='font-size:10px'>"
                    f"entry {_li['original_qty']} → {_leg_strs} · holding {_li['open_qty']}</span>"
                )

            # Scale-in lot ladder sub-line + qty badge (parent + add-on lots)
            addon_badge = ""
            ladder_html = ""
            _el = _entry_legs.get(p["instrument"])
            if _el:
                _n_addons = len(_el["legs"]) - 1
                addon_badge = (
                    f" <span class='badge badge-dim' title='scale-in add-on lots'>"
                    f"+{_n_addons} addon</span>"
                )
                _lot_strs = " · ".join(
                    f"T{l['tier']}: {l['qty']} @ &#8377;{(l['price'] or 0):.2f}"
                    for l in _el["legs"]
                )
                ladder_html = (
                    f"<br><span class='dim' style='font-size:10px'>"
                    f"{_lot_strs} · avg &#8377;{_el['avg_cost']:.2f}</span>"
                )

            # Deployed capital: blended avg cost (scale-in aware) × remaining qty
            _avg_cost = _el["avg_cost"] if _el else (p["entry_price"] or 0.0)
            _deployed_val = (_avg_cost or 0.0) * (p["quantity"] or 0)
            _deployed_pct = _deployed_val / total * 100 if total else 0.0
            deployed_cell = (
                f"&#8377; {_deployed_val:,.0f}"
                f"<br><span class='dim' style='font-size:11px'>{_deployed_pct:.0f}% of cap</span>"
            )

            rows_html += (
                f"<tr>"
                f"<td><a href='/stock/{sym}' class='chart-link'>{sym}</a>{_tf_badge}"
                f"<br><span class='dim' style='font-size:11px'>{entry_ist}</span>{legs_html}{ladder_html}</td>"
                f"<td>{p['quantity']}{addon_badge}</td>"
                f"<td>{deployed_cell}</td>"
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
                f"<td>{conviction_html}</td>"
                f"</tr>"
            )
        for inst in pending_orders:
            sym = inst.split(":")[-1]
            rows_html += (
                f"<tr>"
                f"<td>{sym}</td><td>—</td><td>—</td><td>—</td><td>—</td><td class='dim'>—</td>"
                f"<td>—</td><td>—</td><td>—</td><td>—</td>"
                f"<td>{_badge('PENDING', 'orange')}</td><td></td><td></td>"
                f"</tr>"
            )
        _risk_net = _risk_locked - _risk_at_risk
        _risk_line = ""
        if positions:
            _risk_line = (
                f'<div class="dim" style="font-size:11px;margin:-4px 0 8px">'
                f'If every stop hits: <span class="red">&#8377;{_risk_at_risk:,.0f} at risk</span>'
                f' <span class="dim">({_risk_at_risk / total * 100 if total else 0:.1f}% of capital)</span>'
                f' &nbsp;·&nbsp; <span class="green">&#8377;{_risk_locked:,.0f} locked in</span>'
                f' &nbsp;·&nbsp; net <span class="{_pnl_class(_risk_net)}">&#8377;{_risk_net:+,.0f}</span>'
                f' <span class="dim">· effective stop = trail trigger when trailing, else hard stop</span></div>'
            )
        pos_section = f"""
        <div class="card full">
            <h2 id="positions">Open Positions ({len(positions)}) + Pending ({len(pending_orders)})</h2>
            {_risk_line}
            <table class="t-pos">
                <tr>
                    <th>Symbol / Entry time</th><th>Qty</th><th>Deployed</th><th>Entry</th>
                    <th>Current (chg%)</th><th>Unreal. P&amp;L</th>
                    <th>Peak &#9650;</th><th>Low &#9660;</th><th>SL / Trail trigger</th>
                    <th>Held</th><th>Status</th><th>Price (since entry)</th>
                    <th>Model (since entry)</th>
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
            <h2 id="orders">Orders ({len(orders)}) <span class="dim" style="font-weight:normal;text-transform:none">· {_range_label}</span></h2>
            <table>
                <tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Qty</th><th>Price</th><th>Status</th></tr>
                {rows_html}
            </table>
        </div>"""
    else:
        orders_section = f"""
        <div class="card full">
            <h2>Orders <span class="dim" style="font-weight:normal;text-transform:none">· {_range_label}</span></h2>
            <span class="dim">No orders in range</span>
        </div>"""

    # Closed trade history
    if closed_trades:
        _product = config.product
        _EXIT_REASON_KIND = {
            "SL": "red", "TRAILING": "orange", "PATTERN_TOP": "orange",
            "STALE": "dim", "STRATEGY": "dim", "OPEN@END": "dim",
        }
        total_pnl = 0.0   # gross
        total_cost = 0.0
        wins = losses = 0
        rows_html = ""
        for t in closed_trades:
            sym = t["instrument"].split(":")[-1]
            entry_p = t.get("entry_price") or 0.0
            exit_p = t.get("exit_price") or 0.0
            qty = t.get("quantity") or 0
            pnl = t.get("gross_pnl") or 0.0
            cost = round_trip_cost(_product, qty, entry_p, exit_p) if (entry_p and exit_p and qty) else 0.0
            net = pnl - cost
            total_pnl += pnl
            total_cost += cost
            if net > 0:
                wins += 1
            elif net < 0:
                losses += 1
            pnl_sign = "+" if pnl >= 0 else ""
            net_sign = "+" if net >= 0 else ""
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
                f"<td class='dim'>&#8377; {cost:,.2f}</td>"
                f"<td class='{_pnl_class(net)}'>{net_sign}&#8377; {net:,.2f}</td>"
                f"<td class='dim'>{dur}</td>"
                f"<td>{reason_badge}</td>"
                f"<td class='dim'>{exit_fmt}</td>"
                f"</tr>"
            )
        total_net = total_pnl - total_cost
        total_sign = "+" if total_pnl >= 0 else ""
        net_total_sign = "+" if total_net >= 0 else ""
        trades_section = f"""
        <div class="card full">
            <h2>Trade History — {len(closed_trades)} closed trades
                &nbsp;<span class="dim" style="font-weight:normal;text-transform:none">
                {wins}W / {losses}L &nbsp;·&nbsp; gross
                <span class="{_pnl_class(total_pnl)}">{total_sign}&#8377; {total_pnl:,.2f}</span>
                &nbsp;&minus;&nbsp; costs &#8377; {total_cost:,.2f}
                &nbsp;=&nbsp; net
                <span class="{_pnl_class(total_net)}">{net_total_sign}&#8377; {total_net:,.2f}</span>
                </span>
            </h2>
            <table class="t-trades">
                <tr><th>Entry time</th><th>Symbol</th><th>Entry &#8377;</th><th>Exit &#8377;</th>
                    <th>Qty</th><th>Gross P&amp;L</th><th>Cost</th><th>Net P&amp;L</th>
                    <th>Hold</th><th>Exit reason</th><th>Exit time</th></tr>
                {rows_html}
            </table>
        </div>"""
    else:
        trades_section = ""

    # ── exit-reason breakdown (#3) — counts + P&L + hold, NO win-rate-per-reason ──
    _reason_rows = exit_reason_breakdown(_windowed)
    if _reason_rows:
        _rr_kind = {
            "SL": "red", "TRAILING": "orange", "PATTERN_TOP": "orange",
            "PATTERN_TOP_PARTIAL": "orange", "TRAILING_EOD_CLOSE": "orange",
            "STALE": "dim", "STRATEGY": "dim", "MOMENTUM_DECAY": "dim",
            "MANUAL/EXTERNAL": "dim",
        }
        _rr_body = "".join(
            f"<tr><td>{_badge(r['reason'], _rr_kind.get(r['reason'], 'dim'))}</td>"
            f"<td class='dim'>{r['count']}</td>"
            f"<td class='{_pnl_class(r['total_pnl'])}'>&#8377; {r['total_pnl']:+,.0f}</td>"
            f"<td class='dim'>{r['pnl_share_pct']:+.0f}%</td>"
            f"<td class='dim'>{r['avg_hold_hours']:.1f}h</td></tr>"
            if r["avg_hold_hours"] is not None else
            f"<tr><td>{_badge(r['reason'], _rr_kind.get(r['reason'], 'dim'))}</td>"
            f"<td class='dim'>{r['count']}</td>"
            f"<td class='{_pnl_class(r['total_pnl'])}'>&#8377; {r['total_pnl']:+,.0f}</td>"
            f"<td class='dim'>{r['pnl_share_pct']:+.0f}%</td><td class='dim'>—</td></tr>"
            for r in _reason_rows
        )
        reason_section = f"""
        <div class="card">
            <h2>Exit Reasons</h2>
            <table>
                <tr><th>Reason</th><th>Trades</th><th>Gross P&amp;L</th><th>% P&amp;L</th><th>Avg hold</th></tr>
                {_rr_body}
            </table>
        </div>"""
    else:
        reason_section = ""

    # ── per-stock scorecard (#6) — gross from FIFO trades; net adds round-trip costs ──
    _scorecard = per_stock_scorecard(_windowed, positions)
    if _scorecard:
        _sc_product = config.product
        _cost_by_inst: dict[str, float] = {}
        for t in _windowed:
            _ep, _xp, _q = t.get("entry_price"), t.get("exit_price"), t.get("quantity")
            if _ep and _xp and _q:
                _cost_by_inst[t["instrument"]] = _cost_by_inst.get(t["instrument"], 0.0) + \
                    round_trip_cost(_sc_product, _q, _ep, _xp)
        _sc_body = ""
        for c in _scorecard:
            sym = c["instrument"].split(":")[-1]
            net = c["gross_pnl"] - _cost_by_inst.get(c["instrument"], 0.0)
            hold = f"{c['avg_hold_hours']:.1f}h" if c["avg_hold_hours"] is not None else "—"
            last_reason = c["last_exit_reason"] or "—"
            open_badge = f" {_badge('OPEN ' + str(c['open_qty']), 'green')}" if c["open_qty"] else ""
            # Trade-matched Nifty on THIS stock's capital-days: same notional, same
            # entry/exit days, in the index. Gross vs gross (index side is frictionless).
            _tm_i = trade_matched_benchmark(
                [t for t in _windowed if t["instrument"] == c["instrument"]], _tm_rows)
            if _tm_i["pnl"] is not None:
                _edge = _tm_i["our_gross_pct"] - _tm_i["pct"]
                vs_nifty = (f"<span class='{_pnl_class(_edge)}' title='ours {_tm_i['our_gross_pct']:+.1f}% vs "
                            f"Nifty {_tm_i['pct']:+.1f}% on &#8377;{_tm_i['notional']:,.0f} deployed'>"
                            f"{_edge:+.1f} pp</span>"
                            f"<br><span class='dim' style='font-size:10px'>Nifty &#8377;{_tm_i['pnl']:+,.0f}</span>")
            else:
                vs_nifty = "<span class='dim'>—</span>"
            _sc_body += (
                f"<tr><td><a href='/stock/{sym}' class='chart-link'>{sym}</a>{open_badge}</td>"
                f"<td class='dim'>{c['n_trades']}</td>"
                f"<td class='{_pnl_class(c['gross_pnl'])}'>&#8377; {c['gross_pnl']:+,.0f}</td>"
                f"<td class='{_pnl_class(net)}'>&#8377; {net:+,.0f}</td>"
                f"<td>{vs_nifty}</td>"
                f"<td class='dim'>{hold}</td>"
                f"<td class='dim'>{last_reason}</td></tr>"
            )
        scorecard_section = f"""
        <div class="card full">
            <h2>Per-Stock Performance (live)</h2>
            <table class="t-score">
                <tr><th>Symbol</th><th>Trades</th><th>Gross P&amp;L</th><th>Net P&amp;L</th>
                    <th>vs Nifty <span class="dim" style="font-weight:normal">trade-matched</span></th>
                    <th>Avg hold</th><th>Last exit</th></tr>
                {_sc_body}
            </table>
        </div>"""
    else:
        scorecard_section = ""

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
            <h2 id="signals">Recent Signals (last 20)</h2>
            <table class="t-signals">
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
    _open_set = {p["instrument"] for p in positions}
    _pending_set = set(risk._pending_orders.keys())
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

        # Explainability tooltip — top drivers of the latest prediction. For a
        # linear model (kind='contrib') the arrow shows the push direction:
        # ▲ toward BUY, ▼ against. MLP falls back to raw feature values (kind='raw').
        _drivers = scores.get("drivers", []) if scores else []
        if _drivers:
            _parts = []
            for d in _drivers:
                if d.get("kind") == "contrib":
                    _arrow = "▲" if d["value"] >= 0 else "▼"
                    _parts.append(f"{_arrow} {d['name']} {d['value']:+.2f}")
                else:
                    _parts.append(f"{d['name']} {d['value']:.2f}")
            _drv_title = "why P(buy): " + "  ·  ".join(_parts)
            _p_min_cell = f'<td title="{_html_attr(_drv_title)}" style="cursor:help">{p_min_html}</td>'
        else:
            _p_min_cell = f"<td>{p_min_html}</td>"

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

        # Conviction trajectory — recent P(buy)/P(sell) history (persisted per candle).
        _prob_hist = _read_model_scores(config.db_path, sym, limit=80)
        conviction_html = _render_prob_sparkline(_prob_hist, _threshold, _veto_threshold)

        # ── per-stock decision status (priority order) ──
        if risk.is_paused(sym):
            status_html = _badge("PAUSED", "red")
        elif st != "TRAINED":
            status_html = _badge("WARMING", "orange")
        elif sym in _open_set:
            status_html = _badge("IN POSITION", "green")
        elif sym in _pending_set:
            status_html = _badge("PENDING", "orange")
        elif scores and p_min >= _threshold and p_max >= _veto_threshold:
            status_html = _badge("VETOED", "dim")
        elif scores and p_min >= _threshold:
            status_html = _badge("ENTRY-READY", "green")
        elif scores:
            status_html = _badge("WAITING", "dim")
        else:
            status_html = "<span class='dim'>—</span>"

        # ── pause / resume control (form POST → /pause → redirect) ──
        _paused = risk.is_paused(sym)
        _act = "resume" if _paused else "pause"
        _btn_label = "Resume" if _paused else "Pause"
        _btn_col = "#3fb950" if _paused else "#f85149"
        action_html = (
            f'<form method="POST" action="/pause" style="margin:0">'
            f'<input type="hidden" name="instrument" value="{sym}">'
            f'<input type="hidden" name="action" value="{_act}">'
            f'<button type="submit" style="font-size:10px;padding:2px 7px;border-radius:3px;'
            f'border:1px solid {_btn_col};background:#21262d;color:{_btn_col};cursor:pointer">'
            f'{_btn_label}</button></form>'
        )

        ticker = sym.split(":")[-1]
        # Aggregated-TF badge: P(buy)/P(sell), Status and Conviction update once
        # per strategy-TF bar (~15:15 IST for a day bar) — label it so a slow
        # cadence isn't misread as a stale/frozen model.
        _ws_tf = config.strategy_timeframe(sym)
        _ws_aggregated = _ws_tf != config.candle_timeframe
        _ws_tf_badge = (
            f' <span class="badge badge-dim" title="model scores update once per '
            f'{_ws_tf} bar, not per 15m candle">{_ws_tf.upper()}</span>'
            if _ws_aggregated else ""
        )
        _bars_label = f"{candles} {_ws_tf} bars" if _ws_aggregated else f"{candles} candles"
        ws_rows += (
            f"<tr>"
            f"<td><a href='/stock/{ticker}' class='chart-link'>{ticker}</a>{_ws_tf_badge}</td>"
            f"<td class='val'>{price_html}</td>"
            f"<td class='dim'>{tick_time}</td>"
            f"<td class='dim'>{vol_html}</td>"
            f"{_p_min_cell}"
            f"<td>{p_max_html}</td>"
            f"<td>{conviction_html}</td>"
            f"<td>{status_html}</td>"
            f"<td>{_badge(st, kind)}</td>"
            f"<td class='dim'>{_bars_label}</td>"
            f"<td>{sparkline_html}</td>"
            f"<td>{action_html}</td>"
            f"</tr>"
        )
    watchlist_section = f"""
    <div class="card full">
        <h2 id="watchlist">Watchlist ({len(config.watchlist)} symbols)</h2>
        <table class="t-watch">
            <tr><th>Symbol</th><th>Last price</th><th>Candle time (IST)</th>
                <th>Volume</th>
                <th>P(buy) <span class="dim" style="font-weight:normal">thr={int(_threshold*100)}%</span></th>
                <th>P(sell) <span class="dim" style="font-weight:normal">veto={int(_veto_threshold*100)}%</span></th>
                <th>Conviction <span class="dim" style="font-weight:normal">buy/sell</span></th>
                <th>Status</th>
                <th>Warm-up</th><th>Candles</th><th>Trend (last 80)</th><th>Action</th></tr>
            {ws_rows}
        </table>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<noscript><meta http-equiv="refresh" content="30"></noscript>
<title>Trader</title>
<style>{_CSS}</style>
<script>{_JS}</script>
</head>
<body>
{header}
<div class="toprow">
    {capital_card}
    {pnl_card}
    {reason_section}
</div>
{graph_row}
<div class="grid">
    {pos_section}
    {scorecard_section}
    {orders_section}
    {trades_section}
    {signals_section}
    {filtered_section}
    {strategy_section}
    {watchlist_section}
    {state_section}
</div>
</body>
</html>"""


def render_stock_page(instrument: str, bot_state, risk, store, config) -> str:
    """Per-stock drilldown (/stock/<sym>): everything about one name in one
    place — status + model reading, price chart with fills/levels, conviction
    history, open-position detail with stop-risk, this stock's closed trades
    (with the trade-matched Nifty counterfactual), its signals incl. gate
    filters, and the effective per-stock params. Same shell as the dashboard
    (mobile CSS + scroll-preserving refresh). Read-only."""
    from trader.analytics import trade_matched_benchmark, BENCHMARK_INSTRUMENT
    sym = instrument.split(":")[-1]
    now = _now_ist()
    params = config.get_strategy_params(instrument, "lr_extrema") or {}
    tf = config.strategy_timeframe(instrument)
    threshold = float(params.get("threshold", 0.70))
    veto = float(params.get("veto_threshold", 0.50))
    sell_thr = float(params.get("sell_threshold", 0.65))
    stop_pct = float(params.get("stop_pct", 3.0))
    trail_pct = float(params.get("trail_pct", 1.5))
    hold_max = int(params.get("hold_bars", 200))
    total = config.total_capital

    # ── status / latest model reading ───────────────────────────────────────
    ws = ((getattr(bot_state, "warmup_status", None) or {}).get(instrument)) if bot_state else None
    scores = ((getattr(bot_state, "model_scores", None) or {}).get(instrument)) if bot_state else None
    try:
        paused = store.get_state(f"{instrument}.paused", 0.0) > 0.5
    except Exception:
        paused = False
    pos_rows = _read_db(
        config.db_path,
        "SELECT entry_price, quantity, held_bars, entry_time, current_price, pct_change, "
        "unrealised_pnl, peak_close, trailing_active, low_since_entry, pattern_top_trailing "
        "FROM open_positions WHERE instrument = ?", (instrument,),
    )
    pos = pos_rows[0] if pos_rows else None
    pending = instrument in (getattr(risk, "_pending_orders", None) or {})
    p_min = float(scores.get("p_min", 0.0)) if scores else None
    p_max = float(scores.get("p_max", 0.0)) if scores else None
    if paused:
        status = _badge("PAUSED", "red")
    elif ws and ws.get("status") == "WARMING_UP":
        status = _badge("WARMING", "orange")
    elif pos:
        status = _badge("IN POSITION", "green")
    elif pending:
        status = _badge("PENDING", "orange")
    elif p_min is not None and p_min >= threshold and (p_max or 0) >= veto:
        status = _badge("VETOED", "dim")
    elif p_min is not None and p_min >= threshold:
        status = _badge("ENTRY-READY", "green")
    elif p_min is not None:
        status = _badge("WAITING", "dim")
    else:
        status = _badge("NO SCORE", "dim")
    if p_min is not None:
        _pmc = "green" if p_min >= threshold else "dim"
        _pxc = "red" if (p_max or 0) >= sell_thr else ("orange" if (p_max or 0) >= veto else "dim")
        model_now = (f'P(buy) <span class="{_pmc}">{p_min * 100:.0f}%</span>'
                     f' <span class="dim">thr {threshold * 100:.0f}%</span>'
                     f' &nbsp;·&nbsp; P(sell) <span class="{_pxc}">{(p_max or 0) * 100:.0f}%</span>'
                     f' <span class="dim">veto {veto * 100:.0f}% · sell {sell_thr * 100:.0f}%</span>')
        drivers = scores.get("drivers") or []
        if drivers:
            _d = " · ".join(
                f"{'▲' if (d.get('value') or 0) >= 0 else '▼'} {d.get('name')} {d.get('value'):+.2f}"
                for d in drivers[:5] if d.get("value") is not None
            )
            model_now += f'<div class="dim" style="font-size:11px;margin-top:2px">drivers: {_d}</div>'
    else:
        model_now = '<span class="dim">no model reading yet</span>'
    _tf_badge = (f' <span class="badge badge-dim" title="strategy timeframe">{tf}</span>'
                 if config.is_aggregated_tf(instrument) else "")

    # ── price chart + conviction history ────────────────────────────────────
    chart_svg, meta_parts, n_candles = _build_chart(instrument, config, width=1100, height=420)
    chart_block = chart_svg if chart_svg else (
        f'<span class="dim">Not enough {config.candle_timeframe} candles cached for {sym} '
        f'({n_candles} found).</span>')
    hist = _read_model_scores(config.db_path, instrument, limit=200)
    conviction = (_render_prob_sparkline(hist, threshold, veto, width=600, height=90)
                  if len(hist) >= 2 else '<span class="dim">no persisted scores yet</span>')
    _hist_from = hist[0]["timestamp"][:16] if hist else "—"

    # ── open position detail ────────────────────────────────────────────────
    pos_block = ""
    if pos:
        ep = pos.get("entry_price") or 0.0
        q = pos.get("quantity") or 0
        cur = pos.get("current_price") or 0.0
        pct = pos.get("pct_change") or 0.0
        upnl = pos.get("unrealised_pnl") or 0.0
        peak = pos.get("peak_close") or 0.0
        low = pos.get("low_since_entry") or 0.0
        trailing = bool(pos.get("trailing_active", 0))
        held = pos.get("held_bars") or 0
        sl = ep * (1 - stop_pct / 100)
        trail_trigger = peak * (1 - trail_pct / 100) if trailing and peak > 0 else None
        eff = trail_trigger if trail_trigger else sl
        risk_rs = (cur - eff) * q if cur > 0 else 0.0
        risk_html = (f'<span class="red">at risk &#8377;{risk_rs:,.0f}</span>' if risk_rs >= 0
                     else f'<span class="green">locked &#8377;{-risk_rs:,.0f}</span>')
        _tk = "TRAIL(TOP)" if pos.get("pattern_top_trailing") else "TRAIL(PCT)"
        pos_block = f"""
    <div class="card">
        <h2>Open Position</h2>
        <table>
            <tr><td class="dim">Entry</td><td class="val">&#8377; {ep:.2f} × {q}
                <span class="dim">= &#8377;{ep * q:,.0f} ({ep * q / total * 100 if total else 0:.0f}% cap)</span></td></tr>
            <tr><td class="dim">Since</td><td class="val">{_fmt_ist(_parse_ist_naive(pos.get("entry_time")))}</td></tr>
            <tr><td class="dim">Current</td><td class="val">&#8377; {cur:.2f}
                <span class="{_pnl_class(pct)}">({pct:+.2f}%)</span>
                &nbsp;·&nbsp; unrealised <span class="{_pnl_class(upnl)}">&#8377; {upnl:+,.2f}</span></td></tr>
            <tr><td class="dim">Peak / Low</td><td class="val"><span class="green">&#8377; {peak:.2f}</span>
                <span class="dim">({(peak - ep) / ep * 100 if ep and peak else 0:+.2f}%)</span>
                &nbsp;/&nbsp; {(f'<span class="red">&#8377; {low:.2f}</span> <span class="dim">({(low - ep) / ep * 100:+.2f}%)</span>'
                               if (low and ep) else '<span class="dim">—</span>')}</td></tr>
            <tr><td class="dim">Hard stop</td><td class="val red">&#8377; {sl:.2f} <span class="dim">(−{stop_pct:g}%)</span></td></tr>
            <tr><td class="dim">Trail</td><td class="val">{(f'<span class="orange">&#8377; {trail_trigger:.2f}</span> {_badge(_tk, "orange")}'
                                                              if trail_trigger else '<span class="dim">not active</span>')}</td></tr>
            <tr><td class="dim">Stop risk</td><td class="val">{risk_html}
                <span class="dim">({abs(risk_rs) / total * 100 if total else 0:.1f}% cap · to {'trail' if trail_trigger else 'hard stop'})</span></td></tr>
            <tr><td class="dim">Held</td><td class="val">{held}/{hold_max} {tf} bars</td></tr>
        </table>
    </div>"""

    # ── closed trades for this stock ────────────────────────────────────────
    matched, _ = _load_matched_trades(config.db_path, instrument)
    trades = sorted((t for t in matched if t.get("exit_time")),
                    key=lambda t: str(t["exit_time"]), reverse=True)
    trades_block = ""
    if trades:
        _ER = {"SL": "red", "TRAILING": "orange", "PATTERN_TOP": "orange",
               "PATTERN_TOP_PARTIAL": "orange", "STALE": "dim", "STALE_REARM": "dim",
               "STRATEGY": "dim"}
        tg = tc = 0.0
        rows = ""
        for t in trades:
            ep, xp, q = t.get("entry_price") or 0.0, t.get("exit_price") or 0.0, t.get("quantity") or 0
            g = t.get("gross_pnl") or 0.0
            c = round_trip_cost(config.product, q, ep, xp) if (ep and xp and q) else 0.0
            n = g - c
            tg += g; tc += c
            pctp = (xp - ep) / ep * 100 if ep else 0.0
            r = t.get("exit_reason") or ""
            rows += (f"<tr><td class='dim'>{_fmt_ist(_parse_ist_naive(t.get('entry_time')))}</td>"
                     f"<td>&#8377; {ep:.2f}</td><td>&#8377; {xp:.2f}</td><td class='dim'>{q}</td>"
                     f"<td class='{_pnl_class(g)}'>&#8377; {g:+,.0f} <span class='dim'>({pctp:+.1f}%)</span></td>"
                     f"<td class='{_pnl_class(n)}'>&#8377; {n:+,.0f}</td>"
                     f"<td class='dim'>{_hold_duration(t.get('entry_time', ''), t.get('exit_time', ''))}</td>"
                     f"<td>{_badge(r, _ER.get(r, 'dim')) if r else '<span class=dim>—</span>'}</td>"
                     f"<td class='dim'>{_fmt_ist(_parse_ist_naive(t.get('exit_time')))}</td></tr>")
        first_entry = min((_parse_ist_naive(t["entry_time"]) for t in trades if t.get("entry_time")),
                          default=None)
        tm_line = ""
        if first_entry:
            closes = _read_db(
                config.db_path,
                "SELECT timestamp, close FROM candles WHERE instrument = ? AND timeframe = 'day' "
                "AND timestamp >= ? ORDER BY timestamp ASC",
                (BENCHMARK_INSTRUMENT, (first_entry - timedelta(days=7)).isoformat()),
            )
            tm = trade_matched_benchmark(trades, closes)
            if tm["pnl"] is not None:
                edge = tm["our_gross_pct"] - tm["pct"]
                tm_line = (f' &nbsp;·&nbsp; vs Nifty trade-matched: <span class="{_pnl_class(tm["pnl"])}">'
                           f'&#8377;{tm["pnl"]:+,.0f} ({tm["pct"]:+.1f}%)</span> on &#8377;{tm["notional"]:,.0f}'
                           f' → ours <span class="{_pnl_class(edge)}">{edge:+.1f} pp</span>')
        trades_block = f"""
    <div class="card full">
        <h2 id="trades">Closed Trades ({len(trades)})
            <span class="dim" style="font-weight:normal;text-transform:none">
            gross <span class="{_pnl_class(tg)}">&#8377; {tg:+,.0f}</span> − costs &#8377;{tc:,.0f}
            = net <span class="{_pnl_class(tg - tc)}">&#8377; {tg - tc:+,.0f}</span>{tm_line}</span></h2>
        <table class="t-trades-s">
            <tr><th>Entry time</th><th>Entry</th><th>Exit</th><th>Qty</th><th>Gross</th>
                <th>Net</th><th>Hold</th><th>Reason</th><th>Exit time</th></tr>{rows}
        </table>
    </div>"""
    else:
        trades_block = '<div class="card full"><h2>Closed Trades</h2><span class="dim">none yet</span></div>'

    # ── signals for this stock (incl. gate filters) ──────────────────────────
    sigs = _read_db(
        config.db_path,
        "SELECT logged_at, direction, signal_type, price_hint, accepted, reject_reason, exit_reason "
        "FROM signals WHERE instrument = ? ORDER BY id DESC LIMIT 40", (instrument,),
    )
    if sigs:
        srows = ""
        for sg in sigs:
            acc = bool(sg.get("accepted"))
            rr = sg.get("reject_reason") or ""
            kind = "green" if acc else ("dim" if rr.startswith("FILTER:") else "red")
            reason = (sg.get("exit_reason") or "") if sg.get("signal_type") == "EXIT" else rr
            ph = sg.get("price_hint")
            srows += (f"<tr><td class='dim'>{_fmt_ist(_parse_ist_naive(sg.get('logged_at')))}</td>"
                      f"<td class='{'green' if sg.get('direction') == 'BUY' else 'red'}'>{sg.get('direction')}</td>"
                      f"<td>{sg.get('signal_type')}</td>"
                      f"<td>{'&#8377; %.2f' % ph if ph else '—'}</td>"
                      f"<td>{_badge('✓' if acc else '✗', kind)}</td>"
                      f"<td class='dim'>{reason or '—'}</td></tr>")
        signals_block = f"""
    <div class="card full">
        <h2 id="signals">Signals (last {len(sigs)}, incl. gate filters)</h2>
        <table><tr><th>Time</th><th>Dir</th><th>Type</th><th>Price</th><th></th><th>Reason</th></tr>{srows}</table>
    </div>"""
    else:
        signals_block = '<div class="card full"><h2>Signals</h2><span class="dim">none logged</span></div>'

    # ── effective params ─────────────────────────────────────────────────────
    _ptags = "".join(f'<span class="tag">{k} = {v}</span>' for k, v in sorted(params.items())
                     if not isinstance(v, (dict, list)))
    params_block = f"""
    <div class="card full">
        <h2>Effective Params <span class="dim" style="font-weight:normal;text-transform:none">· timeframe {tf}
            · global ∪ per_stock_params</span></h2>
        <div>{_ptags or '<span class="dim">—</span>'}</div>
    </div>"""

    meta = " &nbsp;·&nbsp; ".join(
        ['<a href="/" class="chart-link">← Dashboard</a>',
         f'<a href="/chart/{sym}" class="chart-link">full-size chart</a>'] + meta_parts
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<noscript><meta http-equiv="refresh" content="60"></noscript>
<title>{sym} — Trader</title>
<style>{_CSS}</style>
<script>{_JS}</script>
</head>
<body>
<h1>{sym}{_tf_badge} &nbsp;{status}</h1>
<div class="meta">{meta} &nbsp;·&nbsp; {now.strftime("%d %b %Y, %H:%M:%S IST")}
    &nbsp;·&nbsp; <span id="refresh-note" style="font-size:11px">auto-refresh 30s</span></div>
<div class="toprow">
    <div class="card"><h2>Model now</h2><div class="val">{model_now}</div></div>
    {pos_block}
</div>
<div class="card full" style="margin-bottom:12px">
    <h2>Price · {config.candle_timeframe} candles · fills, levels, in-position signals</h2>
    <div class="chart-scroll" style="overflow-x:auto">{chart_block}</div>
</div>
<div class="card full" style="margin-bottom:12px">
    <h2>Conviction history <span class="dim" style="font-weight:normal;text-transform:none">· P(buy) green / P(sell) red
        · last {len(hist)} scores from {_hist_from}</span></h2>
    <div style="overflow-x:auto">{conviction}</div>
</div>
<div class="grid">
    {trades_block}
    {signals_block}
    {params_block}
</div>
</body>
</html>"""
