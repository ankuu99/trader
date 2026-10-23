#!/usr/bin/env bash
# Emergency kill switch — switches env to paper and stops the trader service.
# Usage:
#   From local machine:  bash scripts/kill_switch.sh
#   From remote (SSH'd): bash scripts/kill_switch.sh --local

set -e

EC2_HOST="trader"
CONFIG_PATH="/opt/trader/config/config.yaml"

_kill() {
    echo "=== Setting env: paper ==="
    if grep -q "^env: live" "$CONFIG_PATH"; then
        sed -i 's/^env: live/env: paper/' "$CONFIG_PATH"
        echo "    config.yaml updated: env -> paper"
    else
        echo "    env is already paper (or was never live) — skipping sed"
    fi

    echo "=== Stopping trader service ==="
    sudo systemctl stop trader
    echo "    Service stopped."

    echo ""
    echo "=== Kill switch activated ==="
    echo "    Trading is halted. Service will NOT restart (stopped, not failed)."
    echo "    To resume: edit config.yaml (env: live), then: sudo systemctl start trader"
}

if [ "${1}" == "--local" ]; then
    _kill
else
    echo "=== Sending kill switch to $EC2_HOST ==="
    ssh "$EC2_HOST" "$(declare -f _kill); CONFIG_PATH=$CONFIG_PATH _kill"
    echo "=== Done ==="
fi
