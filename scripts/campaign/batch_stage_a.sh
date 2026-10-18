#!/bin/zsh
# Usage: batch_stage_a.sh "<worktree> <label> <overlay-basename>" ...   (runs 5 at a time)
MAIN=/Users/abhisheksingh/Projects/trader-2
run_one() {
  set -- ${=1}
  cd $MAIN/../trader-2-wt/$1 || exit 1
  $MAIN/.venv/bin/python scripts/campaign/stage_a.py --label $2 --overlay $MAIN/config/experiments/$3.yaml \
    --baseline baseline --out $MAIN/reviews/extrema_campaign/runs/stage_a_$2.json \
    --emit-overlay $MAIN/config/experiments/$2_matched.yaml > $MAIN/lab_data/campaign/logs/stage_a_$2.log 2>&1
  echo "done $2 rc=$?"
}
mkdir -p $MAIN/lab_data/campaign/logs
for a in "$@"; do echo "$a"; done | while read -r line; do
  while (( $(jobs -r | wc -l) >= 5 )); do sleep 5; done
  run_one "$line" &
done
wait
