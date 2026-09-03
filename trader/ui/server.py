"""
Dashboard HTTP server — runs in a daemon thread inside the bot process.

Binds to 127.0.0.1 only (loopback). Never reachable from the internet.
Access via SSH tunnel: ssh -fN -L <port>:localhost:<port> trader
Then open: http://localhost:<port>
"""

import logging
import threading

from flask import Flask, Response, redirect, request

from trader.ui.template import render_page, render_chart_page, render_stock_page

# Suppress Flask/Werkzeug access logs — we don't want dashboard hits polluting bot logs
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)


def build_app(bot_state, risk, store, config) -> Flask:
    """Construct the dashboard Flask app (routes wired to the live objects).
    Separated from start_dashboard so it can be exercised with a test client."""
    app = Flask(__name__)
    app.logger.setLevel(logging.ERROR)

    @app.route("/")
    def index():
        html = render_page(bot_state, risk, store, config,
                           range_params=request.args.to_dict())
        return Response(html, mimetype="text/html")

    @app.route("/chart/<symbol>")
    def chart(symbol):
        html = render_chart_page(f"NSE:{symbol}", store, config)
        return Response(html, mimetype="text/html")

    @app.route("/stock/<symbol>")
    def stock(symbol):
        html = render_stock_page(f"NSE:{symbol}", bot_state, risk, store, config,
                                 bench=request.args.get("bench"))
        return Response(html, mimetype="text/html")

    @app.route("/pause", methods=["POST"])
    def pause():
        # Form fields (not URL path) so symbols like "M&MFIN" / "NIFTY 50" need no encoding.
        instrument = (request.form.get("instrument") or "").strip()
        action = request.form.get("action")
        if instrument:
            if action == "pause":
                risk.pause(instrument)
                store.set_state(f"{instrument}.paused", 1.0)
            elif action == "resume":
                risk.unpause(instrument)
                store.set_state(f"{instrument}.paused", 0.0)
        # Back to the referring view so the active date range survives the action.
        return redirect(request.referrer or "/", code=303)

    @app.route("/reset_pnl", methods=["POST"])
    def reset_pnl():
        # Operator override for a corrupted lifetime P&L. Updates the live risk object
        # AND persists, atomically, so the next close doesn't clobber it.
        raw = (request.form.get("value") or "0").strip()
        try:
            value = float(raw)
        except ValueError:
            return redirect("/", code=303)
        risk.reset_cumulative_pnl(value)
        store.set_state("cumulative_pnl", value)
        return redirect(request.referrer or "/", code=303)

    @app.route("/token/reload", methods=["POST"])
    def token_reload():
        # Re-read config/.env and hot-swap the Kite token (weekly-restart ops).
        # The heavy lifting lives in main.py's _reload_kite_token closure.
        fn = getattr(bot_state, "reload_token", None)
        if callable(fn):
            try:
                fn("ui-reload")
            except Exception:
                logging.getLogger(__name__).exception("UI token reload failed")
        return redirect(request.referrer or "/", code=303)

    @app.route("/healthz")
    def healthz():
        return "ok"

    return app


def start_dashboard(bot_state, risk, store, config) -> threading.Thread:
    """
    Start the read-only dashboard in a daemon thread. Returns immediately.
    If the thread crashes, the bot is unaffected — daemon threads are silently reaped.
    """
    port = config.ui_port
    app = build_app(bot_state, risk, store, config)

    def _run():
        # host="127.0.0.1": loopback only — not reachable from outside EC2.
        # use_reloader=False is critical — the reloader spawns a child process
        # which would duplicate the bot's threads and break order handling.
        # threaded=False: one request at a time is intentional; no thread-pool overhead.
        app.run(host="127.0.0.1", port=port, use_reloader=False, threaded=False)

    t = threading.Thread(target=_run, name="dashboard", daemon=True)
    t.start()
    return t
