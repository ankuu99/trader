#!/usr/bin/env bash
# Full token refresh flow — run this from your Mac each morning before 9:15.
#   1. Opens Kite login in browser, captures the new access token
#   2. Copies the updated .env to EC2
#   3. Restarts the trader service
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EC2_HOST="trader"
ENV_FILE="$SCRIPT_DIR/../config/.env"

echo "=== Step 1: Refreshing Kite access token ==="
python "$SCRIPT_DIR/login.py"

echo "=== Step 2: Copying updated .env to EC2 ==="
scp "$ENV_FILE" "$EC2_HOST:/tmp/.trader.env"
ssh "$EC2_HOST" "sudo -u trader cp /tmp/.trader.env /opt/trader/config/.env && rm /tmp/.trader.env"

echo "=== Step 3: Restarting service ==="
ssh "$EC2_HOST" "sudo systemctl restart trader && sleep 5 && sudo systemctl status trader --no-pager -l"

echo "=== Done. ==="
