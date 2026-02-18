#!/bin/bash
set -euo pipefail

# Build llama.cpp with CUDA support

echo "==> Configuring llama.cpp with CUDA..."
CUDACXX=/usr/local/cuda/bin/nvcc cmake -B build -DGGML_CUDA=ON

echo "==> Building llama.cpp (parallel)..."
cmake --build build --config Release -j$(nproc)

echo "==> Build complete!"
echo "    - Binaries: ./build/bin/llama-{batched-bench,bench,cli}"
