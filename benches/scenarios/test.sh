#!/bin/bash
set -euo pipefail

# Test all scenarios, or a single one if specified.
# Wrap with energy-profile.py for energy measurement.
#
# Usage:
#   ./test.sh                                     # test all
#   ./test.sh leetcode/cpp/n-queens_english        # test one
#
# Energy measurement:
#   energy-profile.py -- ./test.sh leetcode/cpp/n-queens_english

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SCENARIOS_DIR="${SCENARIOS_DIR:-$(cd "$SCRIPT_DIR/../../.." && pwd)/green-languages-scenarios}"
WORKDIR="${WORKDIR:-./scenarios-workspace}"

if [ ! -d "$WORKDIR" ]; then
    echo "ERROR: Workspace not found at $WORKDIR. Run prepare.sh first." >&2
    exit 1
fi

python3 "$SCRIPT_DIR/run.py" --dir "$SCENARIOS_DIR" test --workdir "$WORKDIR" ${1:+"$1"}
