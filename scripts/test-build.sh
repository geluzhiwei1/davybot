#!/bin/bash
# Test build script for standalone application

set -e

echo "========================================"
echo "  Full Build Test (No Tauri)"
echo "========================================"
echo

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/agent"
BACKEND_VENV="$BACKEND_DIR/.venv"
TAURI_RESOURCES="$PROJECT_ROOT/webui/src-tauri/resources/python-env"
REQUIREMENTS_FILE="$BACKEND_DIR/requirements-freeze.txt"

# 1. Check Python
echo "[1/6] Checking Python..."
if ! command -v python &> /dev/null; then
    echo "[ERROR] Python not found"
    exit 1
fi
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo "[OK] Python: $PYTHON_VERSION"

# 2. Check venv
echo
echo "[2/6] Checking venv..."
if [ ! -d "$BACKEND_VENV" ]; then
    echo "[ERROR] venv not found"
    exit 1
fi
echo "[OK] venv exists"

# 3. Test dawei
echo
echo "[3/6] Testing dawei..."
if ! "$BACKEND_VENV/Scripts/python.exe" -c "import dawei; print(f'dawei version: {dawei.__version__}')" 2>/dev/null; then
    echo "[ERROR] dawei import failed"
    exit 1
fi
echo "[OK] dawei works"

# 4. Export requirements
echo
echo "[4/6] Exporting requirements..."
cd "$BACKEND_DIR"
if ! uv pip freeze > "$REQUIREMENTS_FILE"; then
    echo "[ERROR] Failed to export"
    exit 1
fi
SIZE=$(wc -c < "$REQUIREMENTS_FILE")
echo "[OK] Exported $SIZE bytes"

# 5. Copy venv
echo
echo "[5/6] Copying venv to Tauri..."
rm -rf "$TAURI_RESOURCES"
cp -r "$BACKEND_VENV" "$TAURI_RESOURCES"
echo "[OK] Venv copied"

# 6. Test copied venv
echo
echo "[6/6] Testing copied venv..."
if ! "$TAURI_RESOURCES/Scripts/python.exe" -c "import dawei; print(f'dawei version: {dawei.__version__}')" 2>/dev/null; then
    echo "[ERROR] Copy verification failed"
    exit 1
fi
echo "[OK] Copied venv works"

# Calculate sizes
SRC_SIZE=$(du -sb "$BACKEND_VENV" | awk '{print $1}')
DST_SIZE=$(du -sb "$TAURI_RESOURCES" | awk '{print $1}')

echo
echo "========================================"
echo "  [OK] All Tests Passed!"
echo "========================================"
echo
echo "Source:      $SRC_SIZE bytes"
echo "Destination: $DST_SIZE bytes"
echo "Requirements: $REQUIREMENTS_FILE"
echo "Tauri resources: $TAURI_RESOURCES"
echo
