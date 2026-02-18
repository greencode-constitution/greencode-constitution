#!/bin/bash
set -euo pipefail

# Prepare FFmpeg benchmark environment
# Installs build dependencies needed for compilation

echo "==> Installing build dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    nasm yasm \
    libx264-dev libx265-dev \
    libfreetype-dev libfontconfig-dev \
    libass-dev \
    pkg-config

echo "==> Preparation complete!"
echo "    - Build dependencies installed"
