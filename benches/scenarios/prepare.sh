#!/bin/bash
set -euo pipefail

# Prepare scenario workspace: install deps and extract all code

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SCENARIOS_DIR="${SCENARIOS_DIR:-$(cd "$SCRIPT_DIR/../../.." && pwd)/green-languages-scenarios}"
WORKDIR="${WORKDIR:-./scenarios-workspace}"

if [ ! -d "$SCENARIOS_DIR" ]; then
    echo "ERROR: Scenarios directory not found: $SCENARIOS_DIR" >&2
    echo "Set SCENARIOS_DIR or clone green-languages-scenarios next to this repo." >&2
    exit 1
fi

echo "==> Checking dependencies..."
MISSING=""
for cmd in gcc g++ javac python3 ruby cargo rustc; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING="$MISSING $cmd"
    fi
done
if [ -n "$MISSING" ]; then
    echo "    Missing:$MISSING"
    echo "    Install with: sudo apt-get install -y default-jdk cargo rustc ruby libboost-dev libtbb-dev"
fi

echo "==> Extracting scenarios to $WORKDIR..."
python3 "$SCRIPT_DIR/run.py" --dir "$SCENARIOS_DIR" prepare --workdir "$WORKDIR"

echo ""
echo "==> Workspace ready at: $WORKDIR"
echo "    Edit source files, then run build.sh and test.sh"
