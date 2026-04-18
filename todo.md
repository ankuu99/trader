# TODO

## Live Mode — Order Fill Tracking

Currently, live mode places market orders and GTT stop-losses correctly via the Kite API,
but has no way to detect when those orders are filled or when a GTT fires.

**Why:** Kite sends order status updates via a postback webhook (an HTTP POST to a URL you
configure in the Kite developer console). We don't have an HTTP server to receive these.

**Impact:**
- `RiskManager` and `PortfolioTracker` are never updated after a live fill
- Strategy position state (`strategy.position`) stays `None` after entry
- Risk manager blocks re-entry for the same instrument until restart

**What needs to be built:**
- A small HTTP server (e.g. Flask or FastAPI) to receive Kite's postback POSTs
- Parse the postback payload and call `orders.on_kite_order_update(update)`
- Wire that into `handle_order_update` in `main.py` so risk/portfolio/strategy state updates
- Configure the postback URL in Kite developer console settings
