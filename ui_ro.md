# Read-Only Dashboard — Implementation Plan

## Overview

A minimal read-only HTTP dashboard that shows live bot state. Runs inside the same process
as the trading bot (background daemon thread), reads from the in-memory objects that already
exist (`RiskManager`, `config`) and from the SQLite DB (`Store`). No writes, no auth, no JS
frameworks.

**Guiding constraints:**
- Zero new heavyweight dependencies (no Streamlit, no Grafana, no React)
- Memory budget: < 30 MB additional RAM on t2.micro
- Bot thread must never be blocked or affected by the UI
- Read-only — no endpoint mutates any state
- Served via a daemon thread; if the thread crashes, the bot keeps running

---

## Architecture

```
main.py (main thread)
│
├── RiskManager         ← in-memory: halt flag, capital, P&L, positions
├── Store (SQLite WAL)  ← DB: orders, signals, open_positions, candles
├── config              ← yaml: strategy params, risk limits, watchlist
│
└── [daemon thread] DashboardServer (port 8080)
        │
        └── GET /  → reads BotState + SQLite + config → renders HTML
```

SQLite is opened in WAL mode (`PRAGMA journal_mode=WAL`) already, which allows unlimited
concurrent readers alongside the writer. The UI opens its own read-only connection per
request — no locking contention with the bot.

The `BotState` object is a plain Python dataclass shared between the main thread and the
dashboard thread. The main thread updates it (heartbeat timestamp, restart count). The UI
thread only reads it. No locks needed for the fields we use (datetime and bool are
atomically readable on CPython due to the GIL).

---

## Data panels and sources

| Panel | Source | Update rate |
|-------|--------|-------------|
| Bot status (running / halted) | `BotState.halted` (mirror of `risk._halted`) | Real-time via shared ref |
| Market status (open / closed) | Computed from IST wall clock | Per request |
| Last heartbeat | `BotState.last_candle_at` | Updated each candle in `handle_candle()` |
| Mode (paper / live) | `config.env` | Static |
| Capital: total / deployed / available | `risk._capital_deployed`, `risk.capital_available` | Shared ref |
| Realised P&L today | `risk._realised_pnl` | Shared ref |
| Daily loss limit | `config.daily_loss_limit` | Static |
| Open positions | SQLite `open_positions` | Per-request read |
| Pending orders | `risk._pending_orders` | Shared ref |
| Today's orders (fills + rejects) | SQLite `orders` WHERE date=today | Per-request read |
| Recent signals (last 20) | SQLite `signals` ORDER BY id DESC LIMIT 20 | Per-request read |
| Watchlist + strategy params | `config.watchlist`, `config.strategy_config()` | Static |
| Strategy warm-up status | `BotState.warmup_status` dict | Set once at startup |

---

## File structure

```
trader/
└── ui/
    ├── __init__.py          (empty)
    ├── server.py            (HTTP server — daemon thread entry point)
    ├── state.py             (BotState dataclass — shared between main and UI)
    └── template.py          (HTML template — pure Python f-string, no files to deploy)
```

No template files on disk. The HTML is a single f-string in `template.py` so there are no
static file serving concerns and deployment is just `git pull`.

---

## Dependencies

| Package | Already used? | Purpose |
|---------|--------------|---------|
| `flask` | No | HTTP server. ~4 MB. Alternative: stdlib `http.server` (~0 MB but painful) |
| Nothing else | — | HTML rendered as plain string; CSS inlined |

Flask is chosen over FastAPI/uvicorn for lower overhead (~4 MB vs ~15 MB for uvicorn),
simpler threading model (Flask's dev server runs in a thread trivially), and no async
complexity. The dashboard has no concurrency requirement — one request at a time is fine.

Add to `requirements.txt`:
```
flask>=3.0
```

---

## Implementation steps

### Step 1 — `trader/ui/state.py`

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class BotState:
    """
    Lightweight object shared between the main bot thread and the dashboard thread.
    The main thread writes; the dashboard thread reads only.
    All field types are atomically readable under CPython's GIL.
    """
    started_at: datetime = field(default_factory=datetime.now)
    last_candle_at: datetime | None = None   # updated by handle_candle()
    halted: bool = False                     # mirror of risk._halted — updated on halt
    warmup_done: bool = False                # set True after strategy warm-up loop
    warmup_status: dict = field(default_factory=dict)
    # { "NSE:SYMBOL": {"status": "TRAINED"|"WARMING_UP", "candles": int} }
```

`BotState` mirrors a few in-memory fields from `RiskManager` so the UI never has to read
`_` private attributes directly. The main thread sets `bot_state.halted = True` wherever
it currently calls `risk.notify_halt`.

### Step 2 — `trader/ui/template.py`

Single function `render_page(bot_state, risk, store, config) -> str` that returns a
complete HTML page. Key sections:

```
┌─────────────────────────────────────────────────┐
│  Trader Dashboard          [LIVE | 09:32 IST]   │
│  Status: RUNNING ✓   Last tick: 09:32:15        │
├────────────┬────────────────────────────────────┤
│ Capital    │ P&L Today                          │
│ Total 1000 │ Realised  ₹ +42.50                 │
│ Deployed 329│ Limit    ₹ 100.00                 │
│ Available 671│ Utilised 42.5%                   │
├────────────┴────────────────────────────────────┤
│ Open Positions (3)                              │
│ GICL      4 @ 41.70   held 38 bars             │
│ VISASTEEL 4 @ 40.90   held 15 bars             │
│ INFOMEDIA 34 @ 5.88   held  1 bar              │
├─────────────────────────────────────────────────┤
│ Today's Orders (last 10)                        │
│ 09:18  GICL    BUY  4  COMPLETE  @ 41.70       │
│ ...                                             │
├─────────────────────────────────────────────────┤
│ Recent Signals (last 20)                        │
│ 09:32  TATASTEEL  ENTRY  BUY  ✗ max positions  │
│ ...                                             │
├─────────────────────────────────────────────────┤
│ Strategy Config (lr_extrema)                    │
│ threshold 0.70  profit_pct 3.0  stop_pct 3.0   │
│ hold_bars 150   retrain 50     extrema_order 5  │
├─────────────────────────────────────────────────┤
│ Watchlist (N symbols)                           │
│ NSE:GICL  NSE:VISASTEEL  NSE:INFOMEDIA  ...    │
└─────────────────────────────────────────────────┘
```

CSS: inline `<style>` block, monospace font, dark background, <5 KB total.
Auto-refresh: `<meta http-equiv="refresh" content="30">` — zero JS, zero websockets.
No external CDN calls (no fonts, no bootstrap).

### Step 3 — `trader/ui/server.py`

```python
import threading
from flask import Flask, Response
from trader.ui.template import render_page

def start_dashboard(bot_state, risk, store, config, port=8080):
    """
    Start the dashboard in a daemon thread. Returns immediately.
    If Flask crashes, the bot is unaffected (daemon threads are silently reaped).
    Binds to 127.0.0.1 only — never exposed to the internet.
    Access via SSH tunnel: ssh -fN -L 8080:localhost:8080 trader
    """
    app = Flask(__name__)

    @app.route("/")
    def index():
        html = render_page(bot_state, risk, store, config)
        return Response(html, mimetype="text/html")

    @app.route("/healthz")
    def healthz():
        return "ok"

    def _run():
        # host="127.0.0.1": loopback only — not reachable from outside EC2.
        # use_reloader=False is critical — reloader forks and breaks the bot.
        app.run(host="127.0.0.1", port=port, use_reloader=False, threaded=False)

    t = threading.Thread(target=_run, name="dashboard", daemon=True)
    t.start()
    return t
```

`threaded=False` means one request at a time. This is intentional — the dashboard is
one person looking at one page. It eliminates any thread-pool overhead.

### Step 4 — Integration into `main.py`

Four small touch points:

**a) Import and create `BotState` at the top of `main()`:**
```python
from trader.ui.state import BotState
bot_state = BotState()
```

**b) After strategy warm-up loop, populate warm-up status and set `warmup_done`:**
```python
for strat in strategies:
    bot_state.warmup_status[strat.instrument] = {
        "status": "TRAINED" if getattr(strat, "_trained", False) else "WARMING_UP",
        "candles": len(getattr(strat, "_candles", [])),
    }
bot_state.warmup_done = True
```

**c) Start dashboard after all components are wired (after reconciliation):**
```python
if config.ui_enabled:   # see config section below
    from trader.ui.server import start_dashboard
    start_dashboard(bot_state, risk, store, config, port=config.ui_port)
    logger.info("Dashboard started on port %d", config.ui_port)
```

**d) In `handle_candle()`, update heartbeat and halt mirror:**
```python
bot_state.last_candle_at = datetime.now()
bot_state.halted = risk.is_halted()
```

### Step 5 — Config additions (`config.yaml` + `Config` class)

In `config.yaml`:
```yaml
ui:
  enabled: true
  port: 8080
```

In `trader/core/config.py`:
```python
@property
def ui_enabled(self) -> bool:
    return bool(self._data.get("ui", {}).get("enabled", False))

@property
def ui_port(self) -> int:
    return int(self._data.get("ui", {}).get("port", 8080))
```

Defaults to `enabled: false` so existing deployments are unaffected until explicitly turned on.

---

## SQLite queries used by the UI

All queries use a fresh read-only connection per request (no connection pooling needed at
this request rate). WAL mode means no write blocking.

```sql
-- Open positions
SELECT instrument, entry_price, quantity, held_bars, entry_time
FROM open_positions
ORDER BY entry_time ASC;

-- Today's orders
SELECT order_id, instrument, direction, quantity, price, status, placed_at
FROM orders
WHERE date(placed_at) = date('now', 'localtime')
ORDER BY placed_at DESC
LIMIT 20;

-- Recent signals
SELECT logged_at, instrument, direction, signal_type, price_hint, accepted, reject_reason
FROM signals
ORDER BY id DESC
LIMIT 20;
```

---

## Resource budget

| Item | Estimate |
|------|----------|
| Flask + Werkzeug import | ~8 MB RAM (one-time) |
| Per-request memory | < 1 MB (single HTML page) |
| SQLite read connection per request | < 1 ms, 0 MB retained |
| Dashboard thread stack | < 1 MB |
| CPU at idle (no requests) | ~0% |
| CPU per page load | < 5 ms (simple queries + string render) |
| **Total added overhead** | **~10 MB RAM, negligible CPU** |

t2.micro has 1 GB RAM. The bot typically uses ~150–200 MB. This leaves ~800 MB headroom;
10 MB for the UI is well within budget.

---

## Access — SSH tunnel (no static IP required)

The dashboard binds to `127.0.0.1` (loopback) only. **Port 8080 is never opened in the
EC2 security group.** Access is exclusively via an SSH tunnel, which works from any IP,
any network (home, office, phone hotspot).

### Open the tunnel

```bash
# Foreground (closes when you Ctrl-C)
ssh -L 8080:localhost:8080 trader -N

# Background (persists until you kill it or close the terminal session)
ssh -fN -L 8080:localhost:8080 trader
```

Then open: **`http://localhost:8080`** in any browser on your Mac.

### Close the background tunnel

```bash
pkill -f "ssh -fN -L 8080"
```

### Why this is secure

- The SSH connection uses your existing `~/.ssh/trader_ec2` key (key-only auth, no password).
- Traffic between your Mac and EC2 is encrypted by SSH — HTTP inside the tunnel is effectively HTTPS.
- The Flask server is never reachable from any IP other than the EC2 instance itself.
- No auth credentials to manage, no TLS certificates, no security group rules to change.

### No nginx proxy needed

Flask's dev server is adequate for 1 user hitting 1 page every 30 seconds.

---

## Systemd / restart behaviour

The dashboard starts inside the bot process. If the bot is restarted via `systemctl restart trader`,
the dashboard also restarts automatically. No separate service unit needed.

If the dashboard thread crashes (e.g. Flask encounters an unhandled exception), the daemon
thread is silently reaped and the bot keeps running. The bot logs will not show any error
unless we add a watchdog — not worth adding for v1.

---

## What is NOT in scope

- Authentication / login (handled by SSH key — no credentials needed)
- HTTPS / TLS (SSH tunnel encrypts the traffic)
- Opening any new port in the EC2 security group
- WebSockets / push updates (polling via meta-refresh is sufficient)
- Charts or graphs (just numbers in tables)
- Unrealised P&L per position (requires live LTP from Kite — adds a Kite API call per page load; not worth it)
- Write operations of any kind
- Mobile-responsive design (internal tool, laptop browser only)
- Multi-strategy display (only LRExtrema is in use; strategy config section shows its params)

---

## Implementation order

1. `trader/ui/state.py` — BotState dataclass
2. `trader/ui/__init__.py` — empty
3. Config additions — `ui_enabled`, `ui_port` properties
4. `trader/ui/template.py` — HTML render function (biggest chunk of work)
5. `trader/ui/server.py` — Flask wrapper + daemon thread launcher
6. `main.py` integration — 4 touch points listed above
7. Test locally (paper mode): `python main.py`, open `http://localhost:8080/` directly (no tunnel needed on localhost)
8. Deploy to EC2: set `ui.enabled: true` in config, push + restart service — no security group change needed
9. Access on EC2: `ssh -fN -L 8080:localhost:8080 trader` then open `http://localhost:8080`
