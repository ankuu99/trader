#!/usr/bin/env bash
# clear-db.sh — stop trader, delete SQLite DB on EC2, restart trader
set -euo pipefail

DB_PATH="/opt/trader/data/market.db"
SSH_OPTS="-p 9654"
HOST="trader"

echo "Stopping trader service..."
ssh $SSH_OPTS $HOST "sudo systemctl stop trader"

echo "Deleting DB at $DB_PATH (including WAL/SHM files)..."
ssh $SSH_OPTS $HOST "sudo rm -f $DB_PATH ${DB_PATH}-wal ${DB_PATH}-shm"

echo "Starting trader service..."
ssh $SSH_OPTS $HOST "sudo systemctl start trader"

echo "Done. DB will be rebuilt from Kite on next warm-up."
