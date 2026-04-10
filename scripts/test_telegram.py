"""
Quick smoke test for Telegram notifications.
Run after setting TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in config/.env

    python scripts/test_telegram.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

import trader.notifications.telegram as tg

print("Sending test notifications to Telegram...")

results = {
    "startup":          tg.notify_startup("paper", ["NSE:RELIANCE", "NSE:INFY"], 4),
    "order_filled":     tg.notify_order_filled("NSE:RELIANCE", "BUY", 12, 2500.0, "RSI(14)", "paper"),
    "order_rejected":   tg.notify_order_rejected("NSE:INFY", "BUY", "max positions reached", "paper"),
    "daily_pnl_profit": tg.notify_daily_pnl(420.0, 80.0, 3, "paper"),
    "daily_pnl_loss":   tg.notify_daily_pnl(-320.0, -50.0, 2, "paper"),
    "halt":             tg.notify_halt(-620.0, 600.0, "paper"),
    "error":            tg.notify_error("data/live.py", "KiteTicker disconnected unexpectedly"),
}

print()
all_ok = True
for name, ok in results.items():
    status = "✓" if ok else "✗"
    print(f"  {status}  {name}")
    if not ok:
        all_ok = False

print()
if all_ok:
    print("All notifications sent successfully.")
else:
    print("Some notifications failed — check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in config/.env")
    sys.exit(1)
