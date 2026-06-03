---
name: feedback-run-commands-efficiently
description: Don't re-run expensive commands (backtests, long scripts) multiple times to grep different parts — write output to a file first, then grep the file
metadata:
  type: feedback
---

Don't run a backtest (or any long-running command) multiple times to extract different pieces of output. Write the output to a temp file first, then run all greps/analysis against that file.

**Why:** Backtests take significant time and resources. Re-running wastes both.

**How to apply:** For any command that takes >a few seconds, use `command > /tmp/output.txt 2>&1` first, then `grep`/`cat` the file for analysis.
