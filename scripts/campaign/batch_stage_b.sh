#!/bin/zsh
# Usage: batch_stage_b.sh <worktree> <label:overlay-basename|label:-> ...   (2 runs at a time, 3 workers each)
MAIN=/Users/abhisheksingh/Projects/trader-2
WT=$1; shift
mkdir -p $MAIN/lab_data/campaign/logs
for spec in "$@"; do
  while (( $(jobs -r | wc -l) >= 2 )); do sleep 10; done
  (
    label=${spec%%:*}; ov=${spec#*:}
    cd $MAIN/../trader-2-wt/$WT
    args=(--label $label --workers 3 --out $MAIN/reviews/extrema_campaign/runs/stage_b_$label.json
          --compare $MAIN/reviews/extrema_campaign/runs/baseline_postfix_iss14.json)
    [[ $ov != "-" ]] && args+=(--overlay $MAIN/config/experiments/$ov.yaml)
    $MAIN/.venv/bin/python scripts/campaign/run_windows.py $args > $MAIN/lab_data/campaign/logs/stage_b_$label.log 2>&1
    echo "done $label rc=$?"
  ) &
done
wait
