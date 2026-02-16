#!/bin/bash
set -euo pipefail

# Prepare llama.cpp benchmark environment
# Creates venv, installs HF CLI, downloads model

echo "==> Creating Python virtual environment..."
python3 -m venv .venv

echo "==> Installing huggingface_hub CLI..."
./.venv/bin/pip install -q "huggingface_hub"

echo "==> Downloading Qwen3-8B-Q4_K_M model..."
./.venv/bin/hf download Qwen/Qwen3-8B-GGUF Qwen3-8B-Q4_K_M.gguf --local-dir models

echo "==> Preparation complete!"
echo "    - venv created at ./.venv"
echo "    - Model downloaded to ./models/Qwen3-8B-Q4_K_M.gguf"
