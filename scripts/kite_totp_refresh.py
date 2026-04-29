"""
Kite access token auto-refresh using TOTP — fully unattended.

    python scripts/kite_totp_refresh.py

Requires three additional env vars in config/.env:
    KITE_USER_ID      — Zerodha user ID (e.g. AB1234)
    KITE_PASSWORD     — Zerodha login password
    KITE_TOTP_SECRET  — base32 TOTP secret from Zerodha 2FA setup

Flow:
  1. POST credentials to Zerodha login API → get request_id
  2. Generate live TOTP code from secret → POST to 2FA endpoint
  3. Parse request_token from redirect Location header
  4. Exchange request_token for access_token via KiteConnect
  5. Write KITE_ACCESS_TOKEN to config/.env
  6. Restart trader systemd service (EC2 only — skipped if not found)
  7. Send Telegram notification on success or failure

EC2 cron (run as trader user, weekdays at 08:15 IST = 02:45 UTC):
    45 2 * * 1-5 /home/trader/.venv/bin/python /home/trader/trader/scripts/kite_totp_refresh.py >> /home/trader/logs/totp_refresh.log 2>&1

Keep scripts/kite_auth_server.py as a manual fallback for when this fails.
"""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyotp
import requests
from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect

from trader.core.logger import get_logger

ENV_FILE = Path(__file__).resolve().parents[1] / "config" / ".env"

load_dotenv(ENV_FILE)

API_KEY    = os.environ.get("KITE_API_KEY", "")
API_SECRET = os.environ.get("KITE_API_SECRET", "")
USER_ID    = os.environ.get("KITE_USER_ID", "")
PASSWORD   = os.environ.get("KITE_PASSWORD", "")
TOTP_SECRET = os.environ.get("KITE_TOTP_SECRET", "")

logger = get_logger(__name__)

_LOGIN_URL  = "https://kite.zerodha.com/api/login"
_TWOFA_URL  = "https://kite.zerodha.com/api/twofa"


def _check_env():
    missing = [k for k, v in {
        "KITE_API_KEY": API_KEY,
        "KITE_API_SECRET": API_SECRET,
        "KITE_USER_ID": USER_ID,
        "KITE_PASSWORD": PASSWORD,
        "KITE_TOTP_SECRET": TOTP_SECRET,
    }.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing env vars: {', '.join(missing)}")


def _get_request_token(session: requests.Session) -> str:
    """
    Full headless login flow using a persistent session (cookies preserved).

    Step 1 — POST credentials → request_id
    Step 2 — POST TOTP       → Zerodha sets auth cookie (returns profile JSON)
    Step 3 — GET OAuth URL   → Zerodha redirects to our callback with request_token
    """
    # Step 1: credentials
    resp = session.post(_LOGIN_URL, data={"user_id": USER_ID, "password": PASSWORD}, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") != "success":
        raise RuntimeError(f"Login failed: {body.get('message', body)}")
    request_id = body["data"]["request_id"]
    logger.info("Login OK | request_id=%s", request_id)

    # Step 2: TOTP 2FA — sets session cookie on Zerodha's domain
    totp_code = pyotp.TOTP(TOTP_SECRET).now()
    resp = session.post(
        _TWOFA_URL,
        data={
            "user_id":     USER_ID,
            "request_id":  request_id,
            "twofa_value": totp_code,
            "twofa_type":  "totp",
        },
        timeout=15,
    )
    body = resp.json()
    logger.debug("2FA response: %s", body)
    if body.get("status") != "success":
        message = body.get("message") or body.get("error_type") or repr(body)
        raise RuntimeError(f"2FA failed: {message}")

    # Step 3: GET the KiteConnect OAuth URL using the authenticated session.
    # Zerodha redirects (possibly multiple hops) to our registered redirect URL
    # e.g. http://127.0.0.1:8080/callback?request_token=xxx
    # The final redirect will fail to connect (no local server) — catch it and
    # extract the URL from the exception, or read it from the redirect history.
    kite = KiteConnect(api_key=API_KEY)
    oauth_url = kite.login_url()
    try:
        resp = session.get(oauth_url, allow_redirects=True, timeout=10)
        # If we got here, check the final URL in the redirect chain
        final_url = resp.url
    except requests.exceptions.ConnectionError as e:
        # Expected: final redirect to 127.0.0.1 fails — URL is in the exception
        final_url = str(e.request.url) if e.request else ""
        if not final_url:
            raise RuntimeError(f"Could not capture redirect URL: {e}") from e

    params = parse_qs(urlparse(final_url).query)
    token = params.get("request_token", [None])[0]
    if not token:
        raise RuntimeError(
            f"request_token not found in final redirect URL: {final_url!r}. "
            "Ensure the Kite app redirect URL is set to http://127.0.0.1:8080/callback"
        )
    return token


def _exchange(request_token: str) -> dict:
    """Exchange request_token for access_token via KiteConnect."""
    kite = KiteConnect(api_key=API_KEY)
    session = kite.generate_session(request_token, api_secret=API_SECRET)
    return session


def _save_token(access_token: str):
    set_key(str(ENV_FILE), "KITE_ACCESS_TOKEN", access_token)
    logger.info("KITE_ACCESS_TOKEN written to %s", ENV_FILE)


def _restart_service():
    """Restart the trader systemd service. Skips silently if not on a systemd host."""
    import shutil
    if not shutil.which("systemctl"):
        logger.info("systemctl not available — skipping service restart (not on EC2).")
        return
    try:
        subprocess.run(
            ["sudo", "systemctl", "restart", "trader"],
            check=True, capture_output=True, timeout=30,
        )
        logger.info("Trader service restarted.")
    except subprocess.CalledProcessError as e:
        logger.warning("Could not restart trader service: %s", e.stderr.decode().strip())


def _notify(success: bool, user_id: str = "", detail: str = ""):
    """Send Telegram alert. Import lazily so missing Telegram config doesn't crash."""
    try:
        from trader.notifications import telegram
        if success:
            telegram.notify_token_refreshed(user_id)
        else:
            telegram.notify_error("kite_totp_refresh", f"Token refresh FAILED: {detail}")
    except Exception:
        pass  # Telegram failure must never block the script


def main():
    print("Kite TOTP auto-refresh starting...")
    try:
        _check_env()

        print("Steps 1-3/4 — Logging in with TOTP and obtaining request token...")
        session = requests.Session()
        request_token = _get_request_token(session)
        logger.info("Auth OK | request_token obtained")

        print("Step 4/4 — Exchanging for access token...")
        kite_session = _exchange(request_token)
        access_token = kite_session["access_token"]
        user_name = kite_session.get("user_name", "")
        user_id = kite_session.get("user_id", "")
        logger.info("Session OK | user=%s (%s)", user_name, user_id)

        print("Saving token and restarting service...")
        _save_token(access_token)
        _restart_service()

        print(f"\nDone. Token valid until midnight IST.")
        print(f"User: {user_name} ({user_id})")
        _notify(success=True, user_id=user_id)

    except Exception as exc:
        logger.error("TOTP refresh failed: %s", exc)
        print(f"\nERROR: {exc}", file=sys.stderr)
        _notify(success=False, detail=str(exc))

        sys.exit(1)


if __name__ == "__main__":
    main()
