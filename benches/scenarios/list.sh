#!/bin/bash
set -euo pipefail

# List all valid scenarios from green-languages-scenarios

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SCENARIOS_DIR="${SCENARIOS_DIR:-$(cd "$SCRIPT_DIR/../../.." && pwd)/green-languages-scenarios}"

if [ ! -d "$SCENARIOS_DIR" ]; then
    echo "ERROR: Scenarios directory not found: $SCENARIOS_DIR" >&2
    echo "Set SCENARIOS_DIR or clone green-languages-scenarios next to this repo." >&2
    exit 1
fi

python3 "$SCRIPT_DIR/run.py" --dir "$SCENARIOS_DIR" list
