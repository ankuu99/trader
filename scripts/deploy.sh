#!/usr/bin/env bash
# Deploy latest code from simple_trader branch and restart the trader service
set -e

EC2_HOST="trader"

echo "=== Pulling latest code ==="
ssh "$EC2_HOST" "sudo -u trader git -C /opt/trader pull origin simple_trader"

echo "=== Checking for requirements changes ==="
ssh "$EC2_HOST" "sudo -u trader /opt/trader/.venv/bin/pip install --no-cache-dir -r /opt/trader/requirements.txt 2>&1 | grep -E 'Installing|already satisfied|Successfully' | tail -5"

echo "=== Restarting service ==="
ssh "$EC2_HOST" "sudo systemctl restart trader && sleep 5 && sudo systemctl status trader --no-pager -l"

echo "=== Done. ==="
