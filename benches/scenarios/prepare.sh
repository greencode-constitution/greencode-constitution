#!/bin/bash
set -euo pipefail

# Prepare scenario workspace: install deps and extract all code

GREENCODE_BASE_URL="${GREENCODE_BASE_URL:-https://greencode-constitution.org}"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SCENARIOS_DIR="${SCENARIOS_DIR:-.}"
WORKDIR="${WORKDIR:-./scenarios-workspace}"

# Find or download run.py
if [ -f "$SCRIPT_DIR/run.py" ]; then
    RUN_PY="$SCRIPT_DIR/run.py"
else
    RUN_PY="/tmp/scenarios-run.py"
    curl -sfL "$GREENCODE_BASE_URL/benches/scenarios/run.py" -o "$RUN_PY"
fi

if [ ! -d "$SCENARIOS_DIR/clbg" ] && [ ! -d "$SCENARIOS_DIR/leetcode" ]; then
    echo "ERROR: Not in a green-languages-scenarios directory." >&2
    echo "Set SCENARIOS_DIR or run from the green-languages-scenarios repo root." >&2
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
python3 "$RUN_PY" --dir "$SCENARIOS_DIR" prepare --workdir "$WORKDIR"

echo ""
echo "==> Workspace ready at: $WORKDIR"
echo "    Edit source files, then run build.sh and test.sh"
