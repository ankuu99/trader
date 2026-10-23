#!/usr/bin/env bash
# Start / stop / status of the trader EC2 box from the Mac.
# Usage: ./scripts/ec2.sh start|stop|status|ensure-running
#   ensure-running — start only if stopped, then wait until SSH answers.
# The box powers itself off at 16:00 IST Mon–Fri and 23:55 daily
# (scripts/trader-poweroff.timer), so a box started for an evening release
# needs no manual stop. Uses the default AWS CLI profile (IAM user abhishek).
set -euo pipefail

REGION="ap-south-1"
INSTANCE_ID="i-04c3a635ebb6455e2"
EC2_HOST="trader"

state() {
  aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].State.Name' --output text
}

wait_ssh() {
  local i
  for i in $(seq 1 36); do   # up to ~3 min
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "$EC2_HOST" true 2>/dev/null; then
      echo "ssh: up"; return 0
    fi
    sleep 5
  done
  echo "ERROR: instance running but SSH not answering after 3 min" >&2
  return 1
}

case "${1:-status}" in
  status)
    echo "state: $(state)"
    ;;
  start)
    aws ec2 start-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null
    aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
    echo "state: $(state)"; wait_ssh
    ;;
  stop)
    aws ec2 stop-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null
    aws ec2 wait instance-stopped --region "$REGION" --instance-ids "$INSTANCE_ID"
    echo "state: $(state)"
    ;;
  ensure-running)
    s="$(state)"
    case "$s" in
      running) wait_ssh ;;
      stopped|stopping)
        echo "box is $s — starting it for this session (it will power off at 23:55 IST / 16:00 next trading day)"
        [[ "$s" == stopping ]] && aws ec2 wait instance-stopped --region "$REGION" --instance-ids "$INSTANCE_ID"
        "$0" start ;;
      *) echo "box is $s — waiting"; aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"; wait_ssh ;;
    esac
    ;;
  *) echo "usage: $0 start|stop|status|ensure-running" >&2; exit 1 ;;
esac
