#!/bin/bash
set -euo pipefail

# Compile all scenarios, or a single one if specified.
#
# Usage:
#   ./build.sh                                    # compile all
#   ./build.sh leetcode/cpp/n-queens_english      # compile one

GREENCODE_BASE_URL="${GREENCODE_BASE_URL:-https://greencode-constitution.org}"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SCENARIOS_DIR="${SCENARIOS_DIR:-.}"
WORKDIR="${WORKDIR:-./scenarios-workspace}"

# Find run.py: local > cached > download
if [ -f "$SCRIPT_DIR/run.py" ]; then
    RUN_PY="$SCRIPT_DIR/run.py"
elif [ -f /tmp/scenarios-run.py ]; then
    RUN_PY="/tmp/scenarios-run.py"
else
    RUN_PY="/tmp/scenarios-run.py"
    curl -sfL "$GREENCODE_BASE_URL/benches/scenarios/run.py" -o "$RUN_PY"
fi

if [ ! -d "$WORKDIR" ]; then
    echo "ERROR: Workspace not found at $WORKDIR. Run prepare.sh first." >&2
    exit 1
fi

python3 "$RUN_PY" --dir "$SCENARIOS_DIR" compile --workdir "$WORKDIR" ${1:+"$1"}
