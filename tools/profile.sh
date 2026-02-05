#!/bin/bash
# Energy profiling wrapper - fetches and runs energy-profile.py
# Usage: bash <(curl -sL https://greencode-constitution.org/profile.sh) [options] -- <command>
#
# Options:
#   --json          JSON output
#   --gpu-poll-ms N GPU polling interval (default: 100)
#   -o, --output F  Write results to file
#
# Examples:
#   bash <(curl -sL .../profile.sh) python train.py
#   bash <(curl -sL .../profile.sh) --json -- ./benchmark
#
# Enable RAPL access (once per boot): sudo sysctl kernel.perf_event_paranoid=-1

set -euo pipefail

BASE_URL="${GREENCODE_BASE_URL:-https://greencode-constitution.org}"
PROFILE_SCRIPT="$BASE_URL/energy-profile.py"

# Create temp directory and ensure cleanup
TMPDIR=$(mktemp -d -t greencode-profile.XXXXXX)
trap 'rm -rf "$TMPDIR"' EXIT

# Download the profiler
if ! curl -sfL "$PROFILE_SCRIPT" -o "$TMPDIR/energy-profile.py"; then
    echo "Error: Failed to download profiler from $PROFILE_SCRIPT" >&2
    exit 1
fi

# Verify it's actually Python (not an error page)
if ! head -1 "$TMPDIR/energy-profile.py" | grep -q '^#!.*python'; then
    echo "Error: Downloaded file is not a valid Python script" >&2
    exit 1
fi

chmod +x "$TMPDIR/energy-profile.py"

# Run with all arguments passed through
exec python3 "$TMPDIR/energy-profile.py" "$@"
