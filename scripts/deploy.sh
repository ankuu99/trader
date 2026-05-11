#!/usr/bin/env bash
# Deploy a specific release tag to EC2 and restart the trader service.
# Usage: ./scripts/deploy.sh release-YYYY-MM-DD
set -e

EC2_HOST="trader"
RELEASE_TAG="${1:-}"

if [[ -z "$RELEASE_TAG" ]]; then
  echo "ERROR: release tag required."
  echo "Usage: ./scripts/deploy.sh release-YYYY-MM-DD"
  echo ""
  echo "To create and push a tag:"
  echo "  git tag release-$(date +%Y-%m-%d) <commit-sha>"
  echo "  git push origin release-$(date +%Y-%m-%d)"
  exit 1
fi

echo "=== Deploying $RELEASE_TAG ==="
ssh "$EC2_HOST" "sudo -u trader git -C /opt/trader fetch --tags && sudo -u trader git -C /opt/trader checkout tags/$RELEASE_TAG"

echo "=== Checking for requirements changes ==="
ssh "$EC2_HOST" "sudo -u trader /opt/trader/.venv/bin/pip install --no-cache-dir -r /opt/trader/requirements.txt 2>&1 | grep -E 'Installing|already satisfied|Successfully' | tail -5"

echo "=== Restarting service ==="
ssh "$EC2_HOST" "sudo systemctl restart trader && sleep 5 && sudo systemctl status trader --no-pager -l"

echo "=== Done. Running: $RELEASE_TAG ==="
