#!/bin/bash
# PreToolUse hook: calls local approve server. If server is down, outputs nothing
# and Claude Code falls through to the normal permission prompt.
INPUT=$(cat)
RESPONSE=$(echo "$INPUT" | curl -s --max-time 2 -X POST http://localhost:8765/approve \
  -H "Content-Type: application/json" \
  -d @- 2>/dev/null)

if [ $? -eq 0 ] && [ -n "$RESPONSE" ]; then
    echo "$RESPONSE"
fi
exit 0
