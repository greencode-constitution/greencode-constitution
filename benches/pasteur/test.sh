#!/bin/bash
set -euo pipefail

# Run Pasteur data synthesis benchmark
# Executes the mimic_core.mare pipeline

echo "==> Running Pasteur mimic_core.mare pipeline..."
AGENT=1 venv/bin/pasteur p mimic_core.mare
