"""
Dashboard HTTP server — runs in a daemon thread inside the bot process.

Binds to 127.0.0.1 only (loopback). Never reachable from the internet.
Access via SSH tunnel: ssh -fN -L <port>:localhost:<port> trader
Then open: http://localhost:<port>
"""

import logging
import threading

from flask import Flask, Response

from trader.ui.template import render_page, render_chart_page

# Suppress Flask/Werkzeug access logs — we don't want dashboard hits polluting bot logs
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)


def start_dashboard(bot_state, risk, store, config) -> threading.Thread:
    """
    Start the read-only dashboard in a daemon thread. Returns immediately.
    If the thread crashes, the bot is unaffected — daemon threads are silently reaped.
    """
    port = config.ui_port
    app = Flask(__name__)
    app.logger.setLevel(logging.ERROR)

    @app.route("/")
    def index():
        html = render_page(bot_state, risk, store, config)
        return Response(html, mimetype="text/html")

    @app.route("/chart/<symbol>")
    def chart(symbol):
        html = render_chart_page(f"NSE:{symbol}", store, config)
        return Response(html, mimetype="text/html")

    @app.route("/healthz")
    def healthz():
        return "ok"

    def _run():
        # host="127.0.0.1": loopback only — not reachable from outside EC2.
        # use_reloader=False is critical — the reloader spawns a child process
        # which would duplicate the bot's threads and break order handling.
        # threaded=False: one request at a time is intentional; no thread-pool overhead.
        app.run(host="127.0.0.1", port=port, use_reloader=False, threaded=False)

    t = threading.Thread(target=_run, name="dashboard", daemon=True)
    t.start()
    return t
