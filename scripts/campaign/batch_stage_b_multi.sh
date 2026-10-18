#!/bin/zsh
# Usage: batch_stage_b_multi.sh <worktree:label:overlay-basename> ...   (3 runs at a time, 3 workers each)
# worktree "main" = the main checkout (symlinked at ../trader-2-wt/main).
MAIN=/Users/abhisheksingh/Projects/trader-2
mkdir -p $MAIN/lab_data/campaign/logs
for spec in "$@"; do
  while (( $(jobs -r | wc -l) >= 3 )); do sleep 10; done
  (
    wt=${spec%%:*}; rest=${spec#*:}; label=${rest%%:*}; ov=${rest#*:}
    cd $MAIN/../trader-2-wt/$wt
    $MAIN/.venv/bin/python scripts/campaign/run_windows.py --label $label --workers 3 \
      --overlay $MAIN/config/experiments/$ov.yaml \
      --out $MAIN/reviews/extrema_campaign/runs/stage_b_$label.json \
      --compare $MAIN/reviews/extrema_campaign/runs/baseline_postfix_iss14.json \
      > $MAIN/lab_data/campaign/logs/stage_b_$label.log 2>&1
    echo "done $label rc=$?"
  ) &
done
wait
