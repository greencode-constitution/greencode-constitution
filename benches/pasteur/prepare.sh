#!/bin/bash
set -euo pipefail

# Prepare Pasteur benchmark environment
# Creates venv, installs Pasteur, and ingests the mimic_core dataset

echo "==> Creating Python virtual environment..."
python3 -m venv venv

echo "==> Installing Pasteur in development mode..."
venv/bin/pip install -e ".[dev]"

echo "==> Ingesting mimic_core dataset..."
AGENT=1 venv/bin/pasteur iv mimic_core --all

echo "==> Preparation complete!"
echo "    - venv created at ./venv"
echo "    - mimic_core dataset ingested"
