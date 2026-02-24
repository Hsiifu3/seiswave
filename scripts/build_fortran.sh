#!/bin/bash
# SeisWave Fortran Build Script
# Compiles eqs.f90 into _eqsignal Python extension module using f2py
# Usage: bash scripts/build_fortran.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FORTRAN_SRC="/Users/yachiyo/Developer/EQSignal_ref/libeqs/eqs.f90"
OUTPUT_DIR="$PROJECT_DIR/seiswave/core"
BUILD_DIR="$PROJECT_DIR/build/fortran"

# Add homebrew to PATH (user-local install)
export PATH="$HOME/.homebrew/bin:$HOME/.homebrew/sbin:$PATH"

echo "============================================"
echo " SeisWave Fortran Build (_eqsignal)"
echo "============================================"

# --- Check dependencies ---
if ! command -v gfortran &>/dev/null; then
    echo "[ERROR] gfortran not found. Install with: brew install gcc"
    exit 1
fi
echo "gfortran: $(gfortran --version | head -1)"

if ! python3 -m numpy.f2py --version &>/dev/null 2>&1; then
    echo "[ERROR] f2py not found. Install numpy: pip3 install numpy"
    exit 1
fi
echo "f2py: available"

# FFTW3 paths
FFTW_PREFIX="$HOME/.homebrew"
if [ ! -f "$FFTW_PREFIX/lib/libfftw3.dylib" ] && [ ! -f "$FFTW_PREFIX/lib/libfftw3.a" ]; then
    # Try opt path
    FFTW_PREFIX="$HOME/.homebrew/opt/fftw"
fi
if [ ! -f "$FFTW_PREFIX/lib/libfftw3.dylib" ] && [ ! -f "$FFTW_PREFIX/lib/libfftw3.a" ]; then
    echo "[ERROR] FFTW3 not found. Install with: brew install fftw"
    exit 1
fi
echo "FFTW3: $FFTW_PREFIX"

# --- Prepare build directory ---
mkdir -p "$BUILD_DIR"
rm -rf "$BUILD_DIR"/*

# Copy Fortran source to build dir, stripping non-ASCII comments for f2py compatibility
# (eqs.f90 contains Chinese comments that cause f2py's ASCII parser to fail)
LC_ALL=C sed 's/[^[:print:][:space:]]//g' "$FORTRAN_SRC" > "$BUILD_DIR/eqs.f90"

# Create fftw3.fi from fftw3.f03 (source uses include "fftw3.fi" with C-binding FFTW calls)
# fftw3.f03 provides the iso_c_binding interface needed for fftw_plan_dft_r2c_1d etc.
if [ -f "$FFTW_PREFIX/include/fftw3.f03" ]; then
    cp "$FFTW_PREFIX/include/fftw3.f03" "$BUILD_DIR/fftw3.fi"
elif [ -f "$FFTW_PREFIX/include/fftw3.f" ]; then
    cp "$FFTW_PREFIX/include/fftw3.f" "$BUILD_DIR/fftw3.fi"
fi

# --- Compile with f2py ---
echo ""
echo "[1/2] Compiling Fortran source with f2py..."
cd "$BUILD_DIR"

# GCC lib path for gfortran runtime
GCC_LIB="$HOME/.homebrew/lib/gcc/current"

# Force single architecture (gfortran doesn't support universal/x86 on ARM Mac)
export ARCHFLAGS="-arch arm64"
# Prevent distutils from adding -arch x86_64
export _PYTHON_HOST_PLATFORM="macosx-14.0-arm64"

# Step 1: Pre-compile eqs.f90 with gfortran to generate .mod files and .o
# This resolves the module dependency (eqs uses basic)
echo "  Pre-compiling with gfortran to generate .mod files..."
gfortran -O3 -fPIC -c \
    -I"$BUILD_DIR" -I"$FFTW_PREFIX/include" \
    eqs.f90 -o eqs_precompiled.o \
    -J"$BUILD_DIR" 2>&1

echo "  Generated .mod files:"
ls -la "$BUILD_DIR"/*.mod 2>/dev/null || echo "  (none)"

# Step 2: Use f2py with the pre-compiled object and .mod files
python3 -m numpy.f2py \
    -c eqs.f90 \
    -m _eqsignal \
    --f90exec=gfortran \
    --f90flags="-O3 -fPIC -I$BUILD_DIR -I$FFTW_PREFIX/include" \
    -L"$FFTW_PREFIX/lib" -lfftw3 \
    -L"$GCC_LIB" \
    --build-dir "$BUILD_DIR/f2py_build" \
    2>&1

# --- Install to seiswave/core ---
echo ""
echo "[2/2] Installing to $OUTPUT_DIR..."

# Find the built .so file
SO_FILE=$(find "$BUILD_DIR" -name "_eqsignal*.so" -o -name "_eqsignal*.dylib" | head -1)
if [ -z "$SO_FILE" ]; then
    echo "[ERROR] Build failed - no _eqsignal module found"
    exit 1
fi

cp "$SO_FILE" "$OUTPUT_DIR/"
INSTALLED=$(basename "$SO_FILE")

echo ""
echo "============================================"
echo " Build complete!"
echo " Output: $OUTPUT_DIR/$INSTALLED"
echo "============================================"

# Quick verification
echo ""
echo "Verifying import..."
cd "$PROJECT_DIR"
python3 -c "
import sys
sys.path.insert(0, '$OUTPUT_DIR')
import _eqsignal
print('✅ _eqsignal module loaded successfully')
print('   Available:', [x for x in dir(_eqsignal) if not x.startswith('_')][:10], '...')
"
