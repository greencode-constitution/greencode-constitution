#!/bin/bash
set -euo pipefail

# Print the reference (original) source code for a scenario.
# Use this to see the unmodified code from the YAML file.
#
# Usage:
#   ./code.sh leetcode/cpp/n-queens_english

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SCENARIOS_DIR="${SCENARIOS_DIR:-$(cd "$SCRIPT_DIR/../../.." && pwd)/green-languages-scenarios}"

if [ -z "${1:-}" ]; then
    echo "Usage: $0 SCENARIO_ID" >&2
    echo "Run list.sh to see available scenarios." >&2
    exit 1
fi

python3 "$SCRIPT_DIR/run.py" --dir "$SCENARIOS_DIR" code "$1"
