#!/bin/bash
set -euo pipefail

# Compile all scenarios, or a single one if specified.
#
# Usage:
#   ./build.sh                                    # compile all
#   ./build.sh leetcode/cpp/n-queens_english      # compile one

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SCENARIOS_DIR="${SCENARIOS_DIR:-$(cd "$SCRIPT_DIR/../../.." && pwd)/green-languages-scenarios}"
WORKDIR="${WORKDIR:-./scenarios-workspace}"

if [ ! -d "$WORKDIR" ]; then
    echo "ERROR: Workspace not found at $WORKDIR. Run prepare.sh first." >&2
    exit 1
fi

python3 "$SCRIPT_DIR/run.py" --dir "$SCENARIOS_DIR" compile --workdir "$WORKDIR" ${1:+"$1"}
