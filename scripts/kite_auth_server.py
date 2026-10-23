"""
Kite OAuth token refresh — runs on EC2, works from any SSH client (Mac or iPhone).

    python scripts/kite_auth_server.py

What it does:
  1. Prints the Kite login URL — open it in any browser
  2. After you log in, Kite redirects to http://127.0.0.1:8080/callback?request_token=xxx
     The page will fail to load (no local server) — that's expected.
  3. Copy the full URL from your browser's address bar and paste it here
  4. Script parses the request_token, exchanges it for an access_token
  5. Writes KITE_ACCESS_TOKEN to config/.env
  6. Restarts the trader service

No port changes or SSL setup needed — redirect URL stays as http://127.0.0.1:8080/callback.
"""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect

ENV_FILE = Path(__file__).resolve().parents[1] / "config" / ".env"

load_dotenv(ENV_FILE)
API_KEY = os.environ.get("KITE_API_KEY")
API_SECRET = os.environ.get("KITE_API_SECRET")

if not API_KEY or not API_SECRET:
    print("ERROR: KITE_API_KEY and KITE_API_SECRET must be set in config/.env")
    sys.exit(1)

kite = KiteConnect(api_key=API_KEY)


def main():
    login_url = kite.login_url()

    print("\n" + "=" * 60)
    print("  Kite Token Refresh")
    print("=" * 60)
    print(f"\nStep 1 — Open this URL in your browser:\n\n  {login_url}\n")
    print("Step 2 — Log in with your Zerodha credentials.")
    print("Step 3 — The browser will redirect to localhost and show an error.")
    print("         Copy the full URL from the address bar.\n")

    raw = input("Paste the redirect URL here: ").strip()

    parsed = urlparse(raw)
    params = parse_qs(parsed.query)
    request_token = params.get("request_token", [None])[0]

    if not request_token:
        print("\nERROR: Could not find request_token in the URL. Make sure you copied the full URL.")
        sys.exit(1)

    print("\nExchanging request_token for access_token...")
    try:
        session = kite.generate_session(request_token, api_secret=API_SECRET)
    except Exception as e:
        print(f"ERROR: Could not generate session: {e}")
        sys.exit(1)

    access_token = session["access_token"]
    set_key(ENV_FILE, "KITE_ACCESS_TOKEN", access_token)
    print(f"Token saved  : {ENV_FILE}")
    print(f"User         : {session.get('user_name')} ({session.get('user_id')})")

    print("\nRestarting trader service...")
    try:
        subprocess.run(["sudo", "systemctl", "restart", "trader"], check=True)
        print("Trader restarted successfully.")
    except subprocess.CalledProcessError as e:
        print(f"WARNING: Could not restart trader: {e}")
        print("Run manually: sudo systemctl restart trader")

    print("\nDone. Token is valid until midnight IST.\n")


if __name__ == "__main__":
    main()
