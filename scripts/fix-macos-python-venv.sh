#!/bin/bash
# Fix Python dynamic library linking for portable macOS builds
# This script makes the Python binary truly portable by fixing hardcoded library paths

set -e

PYTHON_ENV_DIR="$1"

if [ -z "$PYTHON_ENV_DIR" ]; then
    echo "Usage: $0 <path-to-python-env>"
    echo ""
    echo "Example:"
    echo "  $0 webui/src-tauri/resources/python-env"
    exit 1
fi

if [ ! -d "$PYTHON_ENV_DIR" ]; then
    echo "❌ Error: Directory not found: $PYTHON_ENV_DIR"
    exit 1
fi

echo "========================================"
echo "  Fixing Python for Portable macOS"
echo "========================================"
echo ""
echo "Target: $PYTHON_ENV_DIR"
echo ""

# Python binary location
PYTHON_BIN="$PYTHON_ENV_DIR/bin/python"

if [ ! -f "$PYTHON_BIN" ]; then
    echo "❌ Error: Python binary not found: $PYTHON_BIN"
    exit 1
fi

echo "✓ Found Python binary: $PYTHON_BIN"
echo ""

# Check current linking
echo "Current dynamic library dependencies:"
otool -L "$PYTHON_BIN" | grep Python || echo "  (No Python.framework dependencies found)"
echo ""

# Get the Python framework that's being referenced
PYTHON_FRAMEWORK_PATH=$(otool -L "$PYTHON_BIN" | grep Python | awk '{print $1}' | head -1)

if [ -z "$PYTHON_FRAMEWORK_PATH" ]; then
    echo "⚠️  Warning: No Python.framework dependency found"
    echo "   This might mean the venv was already fixed or uses a different Python installation"
    echo ""
    echo "Checking for libpython dylib..."
    LIBPYTHON=$(find "$PYTHON_ENV_DIR" -name "libpython*.dylib" -type f | head -1)
    if [ -n "$LIBPYTHON" ]; then
        echo "✓ Found libpython at: $LIBPYTHON"
        echo ""
        echo "Current Python binary state:"
        otool -L "$PYTHON_BIN" | grep -i python || echo "  (no python dependencies shown)"
        echo ""
        echo "The binary might already be portable. Testing..."
        "$PYTHON_BIN" --version && echo "✓ Python appears to work correctly"
    fi
    exit 0
fi

echo "Found hardcoded reference: $PYTHON_FRAMEWORK_PATH"
echo ""

# Check if the referenced Python framework exists
if [ -f "$PYTHON_FRAMEWORK_PATH" ]; then
    echo "⚠️  Warning: The referenced Python framework exists on this system"
    echo "   This means the venv is tied to the system Python installation"
    echo ""

    # Find the libpython in the venv
    LIBPYTHON=$(find "$PYTHON_ENV_DIR" -name "libpython*.dylib" -type f | head -1)

    if [ -z "$LIBPYTHON" ]; then
        echo "❌ Error: Cannot find libpython in the venv"
        echo "   The venv may not be properly self-contained"
        exit 1
    fi

    echo "✓ Found libpython in venv: $LIBPYTHON"
    echo ""

    # Calculate relative path from bin to lib
    BIN_DIR=$(dirname "$PYTHON_BIN")
    LIB_DIR=$(dirname "$LIBPYTHON")
    REL_PATH=$(realpath --relative-to="$BIN_DIR" "$LIB_DIR" 2>/dev/null || echo "../lib")

    # New reference will be @executable_path relative
    NEW_PYTHON_LIB="@executable_path/${REL_PATH}/$(basename "$LIBPYTHON")"

    echo "Fixing dynamic library reference..."
    echo "  Old: $PYTHON_FRAMEWORK_PATH"
    echo "  New: $NEW_PYTHON_LIB"
    echo ""

    # Use install_name_tool to fix the reference
    install_name_tool -change "$PYTHON_FRAMEWORK_PATH" "$NEW_PYTHON_LIB" "$PYTHON_BIN"

    # Also add rpath if needed
    install_name_tool -add_rpath "@executable_path/../lib" "$PYTHON_BIN" 2>/dev/null || true

    echo "✓ Fixed Python binary"
    echo ""

    # Verify the fix
    echo "Updated dynamic library dependencies:"
    otool -L "$PYTHON_BIN" | grep -i python || echo "  (Python dependencies now use relative paths)"
    echo ""

    # Test if it works
    echo "Testing Python binary..."
    if "$PYTHON_BIN" --version 2>&1; then
        echo ""
        echo "✅ Success! Python binary is now portable"
        echo ""
        echo "The Python environment can now be copied to another macOS machine"
        echo "and will work without requiring Python.framework to be installed"
    else
        echo ""
        echo "⚠️  Warning: Python test failed"
        echo "   The binary may have additional dependencies"
        echo ""
        echo "Checking for other hardcoded paths..."
        otool -L "$PYTHON_BIN" | grep -E "^/[^@]" || echo "  (no other absolute paths found)"
    fi
else
    echo "❌ Error: Referenced Python framework does not exist on this system"
    echo "   $PYTHON_FRAMEWORK_PATH"
    echo ""
    echo "This venv was created on a different machine with Python installed"
    echo "at a different location. You need to recreate the venv on this machine."
    exit 1
fi

echo ""
echo "========================================"
echo "  Fix Complete"
echo "========================================"
