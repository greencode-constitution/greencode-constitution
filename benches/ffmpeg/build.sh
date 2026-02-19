#!/bin/bash
set -euo pipefail

# Build FFmpeg with optional NVIDIA CUDA/NVENC support
# Detects NVIDIA GPU and enables hardware acceleration if available

EXTRA_FLAGS=""

if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
    echo "==> NVIDIA GPU detected, enabling CUDA/NVENC..."

    # Find nvcc
    if [ -x /usr/local/cuda/bin/nvcc ]; then
        NVCC=/usr/local/cuda/bin/nvcc
    elif command -v nvcc &>/dev/null; then
        NVCC=$(command -v nvcc)
    else
        echo "    Warning: nvidia-smi found but nvcc not found, building without CUDA"
        NVCC=""
    fi

    if [ -n "$NVCC" ]; then
        EXTRA_FLAGS="--enable-nonfree --enable-cuda-nvcc --nvcc=$NVCC --enable-ffnvcodec --enable-nvenc --enable-nvdec --enable-cuvid"
        echo "    Using nvcc: $NVCC"
    fi
else
    echo "==> No NVIDIA GPU detected, building CPU-only"
fi

echo "==> Configuring FFmpeg..."
./configure \
    --enable-gpl \
    --enable-libx264 \
    --enable-libx265 \
    --enable-libfreetype \
    --enable-libfontconfig \
    --enable-libharfbuzz \
    --enable-libass \
    --disable-stripping \
    --extra-cflags="-g" \
    $EXTRA_FLAGS

echo "==> Building FFmpeg (parallel)..."
make -j$(nproc)

echo "==> Build complete!"
echo "    - Binaries: ./ffmpeg, ./ffprobe"
if [ -n "$EXTRA_FLAGS" ]; then
    echo "    - NVIDIA CUDA/NVENC: enabled"
else
    echo "    - NVIDIA CUDA/NVENC: disabled (CPU-only)"
fi
