#!/bin/bash
set -euo pipefail

# List all valid scenarios from green-languages-scenarios

GREENCODE_BASE_URL="${GREENCODE_BASE_URL:-https://greencode-constitution.org}"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SCENARIOS_DIR="${SCENARIOS_DIR:-.}"

# Find run.py: local > cached > download
if [ -f "$SCRIPT_DIR/run.py" ]; then
    RUN_PY="$SCRIPT_DIR/run.py"
elif [ -f /tmp/scenarios-run.py ]; then
    RUN_PY="/tmp/scenarios-run.py"
else
    RUN_PY="/tmp/scenarios-run.py"
    curl -sfL "$GREENCODE_BASE_URL/benches/scenarios/run.py" -o "$RUN_PY"
fi

if [ ! -d "$SCENARIOS_DIR/clbg" ] && [ ! -d "$SCENARIOS_DIR/leetcode" ]; then
    echo "ERROR: Not in a green-languages-scenarios directory." >&2
    echo "Set SCENARIOS_DIR or run from the green-languages-scenarios repo root." >&2
    exit 1
fi

python3 "$RUN_PY" --dir "$SCENARIOS_DIR" list
