"""
Run this script once each trading day to refresh the Kite access token.

    python scripts/login.py

What it does:
  1. Opens the Kite login URL in your browser
  2. Starts a local server on port 8080 to capture the redirect
  3. Exchanges the request_token for an access_token
  4. Writes KITE_ACCESS_TOKEN to .env
"""

import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Allow running as a script without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect

ENV_FILE = Path(__file__).resolve().parents[1] / "config" / ".env"
CALLBACK_PORT = 8080
CALLBACK_PATH = "/callback"

load_dotenv(ENV_FILE)
API_KEY = os.environ.get("KITE_API_KEY")
API_SECRET = os.environ.get("KITE_API_SECRET")

if not API_KEY or not API_SECRET:
    print("ERROR: KITE_API_KEY and KITE_API_SECRET must be set in .env")
    sys.exit(1)

kite = KiteConnect(api_key=API_KEY)
_request_token: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _request_token
        parsed = urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        if "request_token" not in params:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing request_token")
            return

        _request_token = params["request_token"][0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Login successful. You can close this tab.</h2></body></html>"
        )

    def log_message(self, *_):  # suppress default server logs
        pass


def main():
    login_url = kite.login_url()
    print(f"\nOpening Kite login in your browser...")
    print(f"If the browser doesn't open, visit:\n  {login_url}\n")
    webbrowser.open(login_url)

    print(f"Waiting for Kite to redirect to http://127.0.0.1:{CALLBACK_PORT}{CALLBACK_PATH} ...")
    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), _CallbackHandler)
    server.handle_request()  # blocks until exactly one request is received

    if not _request_token:
        print("ERROR: Did not receive a request_token. Try again.")
        sys.exit(1)

    print("Received request_token. Exchanging for access_token...")
    try:
        session = kite.generate_session(_request_token, api_secret=API_SECRET)
    except Exception as e:
        print(f"ERROR: Could not generate session: {e}")
        sys.exit(1)

    access_token = session["access_token"]
    set_key(ENV_FILE, "KITE_ACCESS_TOKEN", access_token)
    print(f"Access token saved to .env")
    print(f"User: {session.get('user_name')} ({session.get('user_id')})")
    print("\nYou can now run: python main.py\n")


if __name__ == "__main__":
    main()
