#!/bin/bash
# Fix Python dynamic library linking for portable macOS builds
# This script makes the Python binary truly portable by fixing hardcoded library paths

set -e

echo "========================================"
echo "  Python Portable Build Fix for macOS"
echo "========================================"
echo ""
echo "This script fixes:"
echo "  1. Hardcoded Python.framework references"
echo "  2. Python.app bundle references (if present)"
echo "  3. Code signature issues"
echo ""

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

# Step 0: Remove Python.app if it exists (causes posix_spawn errors)
# Python.app is part of framework Python builds and contains hardcoded paths
echo "Step 0: Checking for Python.app bundle..."
PYTHON_APP_DIRS=$(find "$PYTHON_ENV_DIR" -path "*/lib/Resources/Python.app" -type d 2>/dev/null || true)
if [ -n "$PYTHON_APP_DIRS" ]; then
    echo "⚠️  Found Python.app directories that will cause issues:"
    echo "$PYTHON_APP_DIRS"
    echo ""
    echo "Removing Python.app bundles..."
    while read -r app_dir; do
        if [ -d "$app_dir" ]; then
            echo "  Removing: $app_dir"
            rm -rf "$app_dir"
        fi
    done <<< "$PYTHON_APP_DIRS"
    echo "✓ Removed Python.app bundles"
else
    echo "✓ No Python.app bundles found (good!)"
fi
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

    # Find or copy the libpython dylib
    LIBPYTHON=$(find "$PYTHON_ENV_DIR" -name "libpython*.dylib" -type f | head -1)

    if [ -z "$LIBPYTHON" ]; then
        echo "⚠️  No libpython found in venv, attempting to copy from system Python..."

        # Get the Python version from the binary
        PYTHON_VERSION=$("$PYTHON_BIN" --version 2>&1 | awk '{print $2}')
        PYTHON_MAJOR_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f1,2)

        # Try to find libpython in various locations
        SYSTEM_LIBPYTHON=""

        # 1. Check GitHub Actions Python installation (toolcache) - PRIORITY for CI
        if [ -n "$Python_ROOT_DIR" ]; then
            echo "Checking GitHub Actions toolcache Python at: $Python_ROOT_DIR"
            # Toolcache Python has libpython in lib/ directory
            SYSTEM_LIBPYTHON="$Python_ROOT_DIR/lib/libpython${PYTHON_MAJOR_MINOR}.dylib"
            if [ -f "$SYSTEM_LIBPYTHON" ]; then
                echo "✓ Found toolcache libpython: $SYSTEM_LIBPYTHON"
            else
                SYSTEM_LIBPYTHON=""
            fi
        fi

        # 2. Check standard Python.org framework installation
        if [ -z "$SYSTEM_LIBPYTHON" ]; then
            SYSTEM_LIBPYTHON="/Library/Frameworks/Python.framework/Versions/${PYTHON_MAJOR_MINOR}/Python"
        fi

        # 3. Try to find in Python.framework (any version)
        if [ -z "$SYSTEM_LIBPYTHON" ] || [ ! -f "$SYSTEM_LIBPYTHON" ]; then
            SYSTEM_LIBPYTHON=$(find /Library/Frameworks/Python.framework -name "Python" -type f 2>/dev/null | grep "Versions/${PYTHON_MAJOR_MINOR}" | head -1)
        fi

        # 4. Try using 'locate libpython' or find from the framework reference
        if [ -z "$SYSTEM_LIBPYTHON" ] || [ ! -f "$SYSTEM_LIBPYTHON" ]; then
            # The framework path should point to the actual dylib
            FRAMEWORK_DIR=$(dirname "$PYTHON_FRAMEWORK_PATH")
            if [ -d "$FRAMEWORK_DIR" ]; then
                SYSTEM_LIBPYTHON=$(find "$FRAMEWORK_DIR" -name "libpython*.dylib" -o -name "Python" | grep -v ".framework" | head -1)
            fi
        fi

        if [ -z "$SYSTEM_LIBPYTHON" ] || [ ! -f "$SYSTEM_LIBPYTHON" ]; then
            echo "❌ Error: Cannot find libpython in system Python installation"
            echo "   Searched for libpython${PYTHON_MAJOR_MINOR} in:"
            echo "   - Python_ROOT_DIR: ${Python_ROOT_DIR:-not set}"
            echo "   - /Library/Frameworks/Python.framework/Versions/${PYTHON_MAJOR_MINOR}/"
            echo "   - Framework path: $PYTHON_FRAMEWORK_PATH"
            echo ""
            echo "💡 TIP: If running on GitHub Actions macOS, ensure:"
            echo "   - Python is setup with 'actions/setup-python@v5'"
            echo "   - The venv is created using: \$Python_ROOT_DIR/bin/python3 -m venv .venv"
            echo "   - This uses the self-contained toolcache Python instead of system Python"
            exit 1
        fi

        # Create lib directory in venv
        LIB_DIR="$PYTHON_ENV_DIR/lib"
        mkdir -p "$LIB_DIR"

        # Copy libpython dylib to venv
        LIBPYTHON_NAME="libpython${PYTHON_MAJOR_MINOR}.dylib"
        LIBPYTHON="$LIB_DIR/$LIBPYTHON_NAME"
        echo "Copying $SYSTEM_LIBPYTHON to $LIBPYTHON"
        cp "$SYSTEM_LIBPYTHON" "$LIBPYTHON"

        if [ ! -f "$LIBPYTHON" ]; then
            echo "❌ Error: Failed to copy libpython to venv"
            exit 1
        fi
        echo "✓ Copied libpython to venv: $LIBPYTHON"

        # Remove and re-sign the copied libpython (required for portability)
        echo "Re-signing libpython with ad-hoc signature..."
        codesign --remove-signature "$LIBPYTHON" 2>/dev/null || true
        codesign -s - "$LIBPYTHON"
        echo "✓ Re-signed libpython"
    else
        echo "✓ Found libpython in venv: $LIBPYTHON"
        # Re-sign existing libpython to ensure valid signature
        echo "Re-signing existing libpython with ad-hoc signature..."
        codesign --remove-signature "$LIBPYTHON" 2>/dev/null || true
        codesign -s - "$LIBPYTHON"
        echo "✓ Re-signed libpython"
    fi
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

    # Re-sign the binary after modification (install_name_tool invalidates the signature)
    echo "Re-signing Python binary with ad-hoc signature..."
    codesign --remove-signature "$PYTHON_BIN" 2>/dev/null || true
    codesign -s - "$PYTHON_BIN"
    echo "✓ Re-signed Python binary"

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

        # Check if Python.app is still referenced
        PYTHON_APP_CHECK=$(strings "$PYTHON_BIN" 2>/dev/null | grep -i "Python.app" || true)
        if [ -n "$PYTHON_APP_CHECK" ]; then
            echo ""
            echo "⚠️  Binary still contains Python.app references:"
            echo "$PYTHON_APP_CHECK"
            echo ""
            echo "This binary may have been built from a framework Python installation."
            echo "Consider rebuilding the venv with: python3 -m venv --symlinks=false .venv"
        fi
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
