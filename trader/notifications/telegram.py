"""
Telegram notifications — sends alerts via the Telegram Bot API.

All public functions are safe to call even if Telegram is not configured:
they log a warning and return silently rather than crashing the trading system.

Setup
-----
1. Create a bot via @BotFather on Telegram → get TELEGRAM_BOT_TOKEN
2. Send your bot a message, then visit:
   https://api.telegram.org/bot<TOKEN>/getUpdates
   Find "chat": {"id": <number>} → that is your TELEGRAM_CHAT_ID
3. Add both to config/.env

Events notified
---------------
- Order filled / rejected
- Daily P&L summary (post-market)
- Daily loss limit breached (halt)
- System errors / exceptions
"""

import os
from datetime import datetime

import requests

from trader.core.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT = 5  # seconds


def _token() -> str | None:
    return os.getenv("TELEGRAM_BOT_TOKEN")


def _chat_id() -> str | None:
    return os.getenv("TELEGRAM_CHAT_ID")


def _send(text: str) -> bool:
    """
    Send a message. Returns True on success, False on any failure.
    Never raises — the trading system must not crash due to a notification failure.
    """
    token = _token()
    chat_id = _chat_id()

    if not token or not chat_id:
        logger.debug("Telegram not configured — skipping notification")
        return False

    url = _BASE_URL.format(token=token)
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=_TIMEOUT,
        )
        if not resp.ok:
            logger.warning("Telegram send failed | status=%d | %s", resp.status_code, resp.text)
            return False
        return True
    except requests.RequestException as e:
        logger.warning("Telegram request error: %s", e)
        return False


# ------------------------------------------------------------------ #
# Public notification functions                                        #
# ------------------------------------------------------------------ #

def notify_order_filled(instrument: str, direction: str, quantity: int,
                        fill_price: float, strategy: str, mode: str):
    emoji = "🟢" if direction == "BUY" else "🔴"
    tag = "[PAPER]" if mode == "paper" else "[LIVE]"
    text = (
        f"{emoji} *Order Filled* {tag}\n"
        f"Instrument : `{instrument}`\n"
        f"Direction  : {direction}\n"
        f"Quantity   : {quantity}\n"
        f"Price      : ₹{fill_price:,.2f}\n"
        f"Strategy   : {strategy}\n"
        f"Time       : {datetime.now().strftime('%H:%M:%S')}"
    )
    _send(text)


def notify_order_rejected(instrument: str, direction: str, reason: str, mode: str):
    tag = "[PAPER]" if mode == "paper" else "[LIVE]"
    text = (
        f"⚠️ *Order Rejected* {tag}\n"
        f"Instrument : `{instrument}`\n"
        f"Direction  : {direction}\n"
        f"Reason     : {reason}\n"
        f"Time       : {datetime.now().strftime('%H:%M:%S')}"
    )
    _send(text)


def notify_daily_pnl(realised: float, unrealised: float, total_trades: int, mode: str,
                     capital: float = 0.0):
    net = realised + unrealised
    emoji = "📈" if net >= 0 else "📉"
    tag = "[PAPER]" if mode == "paper" else "[LIVE]"
    pct_line = f"Net %      : {net/capital:.2%}\n" if capital > 0 else ""
    text = (
        f"{emoji} *Daily P&L Summary* {tag}\n"
        f"Realised   : ₹{realised:,.2f}\n"
        f"Unrealised : ₹{unrealised:,.2f}\n"
        f"Net        : ₹{net:,.2f}\n"
        f"{pct_line}"
        f"Trades     : {total_trades}\n"
        f"Date       : {datetime.now().strftime('%d %b %Y')}"
    )
    _send(text)


def notify_halt(daily_pnl: float, limit: float, mode: str):
    tag = "[PAPER]" if mode == "paper" else "[LIVE]"
    text = (
        f"🚨 *Trading Halted* {tag}\n"
        f"Daily loss of ₹{abs(daily_pnl):,.2f} has breached the limit of ₹{limit:,.2f}.\n"
        f"No new entries will be placed today.\n"
        f"Time : {datetime.now().strftime('%H:%M:%S')}"
    )
    _send(text)


def notify_error(component: str, message: str):
    text = (
        f"❌ *System Error*\n"
        f"Component : {component}\n"
        f"Error     : {message}\n"
        f"Time      : {datetime.now().strftime('%H:%M:%S')}"
    )
    _send(text)


def notify_startup(mode: str, instruments: list[str], strategies: int):
    tag = "[PAPER]" if mode == "paper" else "[LIVE]"
    text = (
        f"🚀 *Trader Started* {tag}\n"
        f"Instruments : {', '.join(instruments)}\n"
        f"Strategies  : {strategies}\n"
        f"Time        : {datetime.now().strftime('%H:%M:%S IST')}"
    )
    _send(text)
