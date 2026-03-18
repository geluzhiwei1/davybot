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

    # Find or copy the libpython dylib
    LIBPYTHON=$(find "$PYTHON_ENV_DIR" -name "libpython*.dylib" -type f | head -1)

    if [ -z "$LIBPYTHON" ]; then
        echo "⚠️  No libpython found in venv, attempting to copy from system Python..."

        # Get the Python version from the binary
        PYTHON_VERSION=$("$PYTHON_BIN" --version 2>&1 | awk '{print $2}')
        PYTHON_MAJOR_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f1,2)

        # Try to find libpython in various locations
        SYSTEM_LIBPYTHON=""
        TOOLCACHE_RESOURCES=""

        # 1. Check GitHub Actions Python installation (toolcache) - PRIORITY for CI
        if [ -n "$Python_ROOT_DIR" ]; then
            echo "Checking GitHub Actions toolcache Python at: $Python_ROOT_DIR"
            
            # Toolcache Python has a special structure:
            # lib/libpythonX.Y.dylib -> ../lib/Resources/Python.app/Contents/MacOS/Python
            # We need to copy the actual binary and resolve the structure
            
            TOOLCACHE_LIBPYTHON="$Python_ROOT_DIR/lib/libpython${PYTHON_MAJOR_MINOR}.dylib"
            
            if [ -L "$TOOLCACHE_LIBPYTHON" ]; then
                echo "  Found symlink libpython, resolving..."
                TOOLCACHE_RESOURCES="$Python_ROOT_DIR/lib/Resources"
                if [ -d "$TOOLCACHE_RESOURCES/Python.app/Contents/MacOS" ]; then
                    ACTUAL_PYTHON_BIN="$TOOLCACHE_RESOURCES/Python.app/Contents/MacOS/Python"
                    if [ -f "$ACTUAL_PYTHON_BIN" ]; then
                        echo "✓ Found actual Python binary in toolcache: $ACTUAL_PYTHON_BIN"
                        SYSTEM_LIBPYTHON="$ACTUAL_PYTHON_BIN"
                    fi
                fi
            elif [ -f "$TOOLCACHE_LIBPYTHON" ]; then
                # Check if it's a regular file that references Python.app
                LIBPYTHON_DEPS_CHECK=$(otool -L "$TOOLCACHE_LIBPYTHON" 2>/dev/null | grep -c "Python.app" || true)
                if [ "$LIBPYTHON_DEPS_CHECK" -gt 0 ]; then
                    echo "  libpython references Python.app, checking Resources..."
                    TOOLCACHE_RESOURCES="$Python_ROOT_DIR/lib/Resources"
                    if [ -d "$TOOLCACHE_RESOURCES/Python.app/Contents/MacOS" ]; then
                        ACTUAL_PYTHON_BIN="$TOOLCACHE_RESOURCES/Python.app/Contents/MacOS/Python"
                        if [ -f "$ACTUAL_PYTHON_BIN" ]; then
                            echo "✓ Found actual Python binary in toolcache: $ACTUAL_PYTHON_BIN"
                            SYSTEM_LIBPYTHON="$ACTUAL_PYTHON_BIN"
                        fi
                    fi
                else
                    SYSTEM_LIBPYTHON="$TOOLCACHE_LIBPYTHON"
                    echo "✓ Found toolcache libpython: $SYSTEM_LIBPYTHON"
                fi
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

        # Copy libpython to venv
        # If we found toolcache Resources, we copy the actual binary directly
        if [ -n "$TOOLCACHE_RESOURCES" ] && [ -d "$TOOLCACHE_RESOURCES" ]; then
            echo "Found toolcache Python with Python.app structure..."
            ACTUAL_PYTHON="$TOOLCACHE_RESOURCES/Python.app/Contents/MacOS/Python"
            
            if [ -f "$ACTUAL_PYTHON" ]; then
                echo "✓ Found actual Python binary: $ACTUAL_PYTHON"
                
                # Verify it's a Mach-O binary (not a symlink or wrapper)
                FILE_TYPE=$(file "$ACTUAL_PYTHON" | head -1)
                echo "  File type: $FILE_TYPE"
                
                if [[ "$FILE_TYPE" == *"Mach-O"* ]] && [[ "$FILE_TYPE" == *"executable"* ]]; then
                    echo "  ✓ Confirmed as Mach-O executable"
                else
                    echo "  ⚠️ Warning: Unexpected file type, proceeding anyway..."
                fi
                
                # Copy the actual binary directly to lib/libpythonX.Y.dylib
                LIBPYTHON_NAME="libpython${PYTHON_MAJOR_MINOR}.dylib"
                LIBPYTHON="$LIB_DIR/$LIBPYTHON_NAME"
                
                echo "Copying actual Python binary to $LIBPYTHON"
                cp "$ACTUAL_PYTHON" "$LIBPYTHON"
                
                echo "✓ Copied libpython to venv: $LIBPYTHON"
                echo "Checking its current dependencies..."
                otool -L "$LIBPYTHON" | head -10
            else
                echo "❌ Error: Actual Python binary not found at $ACTUAL_PYTHON"
                exit 1
            fi
        else
            LIBPYTHON_NAME="libpython${PYTHON_MAJOR_MINOR}.dylib"
            LIBPYTHON="$LIB_DIR/$LIBPYTHON_NAME"
            echo "Copying $SYSTEM_LIBPYTHON to $LIBPYTHON"
            cp "$SYSTEM_LIBPYTHON" "$LIBPYTHON"
        fi

        if [ ! -f "$LIBPYTHON" ]; then
            echo "❌ Error: Failed to copy libpython to venv"
            exit 1
        fi
        echo "✓ Copied libpython to venv: $LIBPYTHON"

        # Check and fix libpython's own dependencies
        echo "Checking libpython's dynamic library dependencies..."
        LIBPYTHON_DEPS=$(otool -L "$LIBPYTHON" | grep -E "^\t/" | awk '{print $1}')
        if [ -n "$LIBPYTHON_DEPS" ]; then
            echo "Found hardcoded paths in libpython:"
            echo "$LIBPYTHON_DEPS"
            echo ""
            echo "Fixing libpython's internal references..."
            
            # Fix each hardcoded path in libpython
            while IFS= read -r dep_path; do
                if [ -n "$dep_path" ]; then
                    # Skip system libraries
                    if [[ "$dep_path" == /usr/lib/* ]] || [[ "$dep_path" == /System/Library/* ]]; then
                        continue
                    fi
                    
                    # Check if this is a Python-related reference
                    if [[ "$dep_path" == *Python.framework* ]] || [[ "$dep_path" == *python* ]] || [[ "$dep_path" == *Python.app* ]]; then
                        # The libpython binary should reference itself
                        # Set it to use @rpath
                        echo "  Changing: $dep_path -> @rpath/$(basename "$LIBPYTHON")"
                        install_name_tool -change "$dep_path" "@rpath/$(basename "$LIBPYTHON")" "$LIBPYTHON" 2>/dev/null || true
                    fi
                fi
            done <<< "$LIBPYTHON_DEPS"
            
            # Set the libpython's own id
            install_name_tool -id "@rpath/$(basename "$LIBPYTHON")" "$LIBPYTHON" 2>/dev/null || true
        fi
        
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
    
    # Add rpath to libpython so it can find its dependencies
    install_name_tool -add_rpath "@loader_path" "$LIBPYTHON" 2>/dev/null || true

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
        echo "Checking for other hardcoded paths in Python binary..."
        otool -L "$PYTHON_BIN" | grep -E "^\t/" || echo "  (no other absolute paths found)"
        echo ""
        echo "Checking for hardcoded paths in libpython..."
        otool -L "$LIBPYTHON" | grep -E "^\t/" || echo "  (no other absolute paths found)"
        echo ""
        echo "Checking rpaths in Python binary..."
        otool -l "$PYTHON_BIN" | grep -A2 LC_RPATH || echo "  (no rpaths found)"
        echo ""
        echo "Checking rpaths in libpython..."
        otool -l "$LIBPYTHON" | grep -A2 LC_RPATH || echo "  (no rpaths found)"
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
