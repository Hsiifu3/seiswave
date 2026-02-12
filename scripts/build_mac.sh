#!/bin/bash
# SeisWave macOS Build Script
# Usage: bash scripts/build_mac.sh

set -e

echo "============================================"
echo " SeisWave macOS Build"
echo "============================================"

cd "$(dirname "$0")/.."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found. Please install Python 3.9+."
    exit 1
fi

echo "Python: $(python3 --version)"

# Install/upgrade PyInstaller
echo "[1/3] Installing PyInstaller..."
pip3 install --upgrade pyinstaller

# Install project dependencies
echo "[2/3] Installing dependencies..."
pip3 install -r requirements.txt
pip3 install -e .

# Build
echo "[3/3] Building SeisWave..."
python3 -m PyInstaller build.spec --noconfirm --clean

echo "============================================"
echo " Build complete!"
echo " Output: dist/SeisWave.app (macOS bundle)"
echo "         dist/SeisWave/    (standalone dir)"
echo "============================================"
