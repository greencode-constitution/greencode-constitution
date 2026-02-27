#!/bin/bash
set -euo pipefail

# Print the reference (original) source code for a scenario.
# Use this to see the unmodified code from the YAML file.
#
# Usage:
#   ./code.sh leetcode/cpp/n-queens_english

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

if [ -z "${1:-}" ]; then
    echo "Usage: $0 SCENARIO_ID" >&2
    echo "Run list.sh to see available scenarios." >&2
    exit 1
fi

python3 "$RUN_PY" --dir "$SCENARIOS_DIR" code "$1"
