#!/bin/bash
# Linux/macOS standalone ZIP packager script (Updated to match GitHub CI)
# This script creates a portable ZIP package that users can extract and run
# Supports: Linux x86_64/ARM64, macOS x86_64/ARM64

set -e

# Get script directory absolute path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
WEB_DIR="${PROJECT_ROOT}/webui"
TAURI_DIR="${WEB_DIR}/src-tauri"
AGENT_DIR="${PROJECT_ROOT}/agent"

echo "========================================"
echo "  Tauri Standalone ZIP Packager v2"
echo "  (Updated to match GitHub CI)"
echo "========================================"
echo ""

# Detect OS and architecture
OS_TYPE=$(uname -s)
ARCH_TYPE=$(uname -m)

echo "Detected OS: ${OS_TYPE}"
echo "Detected Architecture: ${ARCH_TYPE}"
echo ""

# Map architecture names
case "${ARCH_TYPE}" in
    x86_64)
        TARGET_ARCH="x86_64"
        ;;
    aarch64|arm64)
        TARGET_ARCH="aarch64"
        ;;
    *)
        echo "❌ Unsupported architecture: ${ARCH_TYPE}"
        echo "   Supported: x86_64, aarch64, arm64"
        exit 1
        ;;
esac

# Determine Rust target
case "${OS_TYPE}" in
    Linux)
        TARGET_TRIPLE="${TARGET_ARCH}-unknown-linux-gnu"
        ;;
    Darwin)
        TARGET_TRIPLE="${TARGET_ARCH}-apple-darwin"
        ;;
    *)
        echo "❌ Unsupported OS: ${OS_TYPE}"
        echo "   Supported: Linux, Darwin"
        exit 1
        ;;
esac

# Set target directory path (must be set before detecting executable)
TARGET_DIR="${TAURI_DIR}/target/${TARGET_TRIPLE}/release"

# Get app name and version
# Try to detect the actual executable that was built
if [ -f "${TARGET_DIR}/dawei-standalone" ]; then
    APP_NAME="dawei-standalone"
elif [ -f "${TARGET_DIR}/davybot" ]; then
    APP_NAME="davybot"
else
    echo "❌ Cannot detect executable name"
    echo "   Looking in: ${TARGET_DIR}"
    ls -la "${TARGET_DIR}" | grep -E "^-.*x.*"
    exit 1
fi

# Get version from standalone tauri config
APP_VERSION=$(grep '"version"' "${TAURI_DIR}/tauri.conf.standalone.json" | head -1 | sed 's/.*"version": "\(.*\)".*/\1/')

echo "App: ${APP_NAME} v${APP_VERSION}"
echo "Target: ${TARGET_TRIPLE}"
echo ""

# 1. Prepare Python environment
echo "[1/6] Preparing Python environment..."

# Create venv if not exists
if [ ! -d "${AGENT_DIR}/.venv" ]; then
    echo "Creating Python virtual environment..."
    cd "${AGENT_DIR}"
    python3 -m venv .venv

    echo "Installing dependencies..."
    if [ -f ".venv/bin/pip" ]; then
        .venv/bin/pip install -e . -i https://mirrors.aliyun.com/pypi/simple/ --quiet
    else
        echo "❌ Failed to create Python environment"
        exit 1
    fi
fi

# Copy Python environment to Tauri resources
echo "Copying Python environment to Tauri resources..."
rm -rf "${TAURI_DIR}/resources/python-env"
cp -r "${AGENT_DIR}/.venv" "${TAURI_DIR}/resources/python-env"

# Clean up Python cache to reduce size
echo "Cleaning Python cache..."
find "${TAURI_DIR}/resources/python-env" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${TAURI_DIR}/resources/python-env" -name "*.pyc" -delete 2>/dev/null || true

echo "✓ Python environment prepared"
echo ""

# 2. Build frontend
echo "[2/6] Building frontend..."
cd "${WEB_DIR}"
pnpm build-only

# Copy welcome.html to dist (Vite plugin does this, but verify)
if [ -f "${TAURI_DIR}/resources/welcome.html" ]; then
    cp "${TAURI_DIR}/resources/welcome.html" "dist/"
    echo "✓ welcome.html copied to dist/"
fi

echo "✓ Frontend build completed"
echo ""

# 3. Build Tauri application
echo "[3/6] Building Tauri application..."
echo "Building for target: ${TARGET_TRIPLE}"

pnpm tauri build --config "${TAURI_DIR}/tauri.conf.standalone.json" --no-bundle --target "${TARGET_TRIPLE}"

# Verify build output
TARGET_DIR="${TAURI_DIR}/target/${TARGET_TRIPLE}/release"
if [ ! -f "${TARGET_DIR}/${APP_NAME}" ]; then
    echo "❌ Build failed: executable not found"
    echo "   Expected: ${TARGET_DIR}/${APP_NAME}"
    exit 1
fi

echo "✓ Tauri build completed"
echo ""

# 4. Prepare portable package directory
echo "[4/6] Preparing portable package..."
ZIP_DIR="${TARGET_DIR}/${APP_NAME}-standalone-${OS_TYPE,,}-${TARGET_ARCH}-portable-v${APP_VERSION}"
ZIP_NAME="${APP_NAME}-standalone-${OS_TYPE,,}-${TARGET_ARCH}-portable-v${APP_VERSION}.zip"

rm -rf "${ZIP_DIR}"
mkdir -p "${ZIP_DIR}/resources"

echo "Package directory: ${ZIP_DIR}"
echo "Package name: ${ZIP_NAME}"
echo ""

# 5. Copy application files
echo "[5/6] Copying application files..."

# Main executable
echo "Copying main executable..."
cp "${TARGET_DIR}/${APP_NAME}" "${ZIP_DIR}/"
echo "✓ Executable copied"

# Python environment
echo "Copying Python environment..."
cp -r "${TAURI_DIR}/resources/python-env" "${ZIP_DIR}/resources/"
echo "✓ Python environment copied"

# welcome.html
echo "Copying welcome.html..."
cp "${TAURI_DIR}/resources/welcome.html" "${ZIP_DIR}/resources/"
echo "✓ welcome.html copied"

# Icons
echo "Copying icons..."
if [ -d "${TAURI_DIR}/icons" ]; then
    mkdir -p "${ZIP_DIR}/icons"
    cp -r "${TAURI_DIR}/icons"/* "${ZIP_DIR}/icons/" 2>/dev/null || true
    echo "✓ Icons copied"
fi

# Make scripts executable
chmod +x "${ZIP_DIR}/resources/"*.sh 2>/dev/null || true
chmod +x "${ZIP_DIR}/${APP_NAME}"

echo "✓ Application files copied"
echo ""

# 6. Create README
echo "[6/6] Creating README..."
README_FILE="${ZIP_DIR}/README.txt"

cat > "${README_FILE}" << EOF
# Dawei AI Assistant - Standalone Portable Version

Version: ${APP_VERSION}
Architecture: ${TARGET_ARCH}

## Usage

1. Extract this ZIP file to any directory
2. Run ./${APP_NAME} to launch the application

The application will automatically start the backend service on first launch.

## Directory Structure

- ${APP_NAME}                  : Main application (${TARGET_ARCH} binary)
- resources/               : Resource files directory
  - welcome.html           : Welcome page (standalone HTML)
  - python-env/            : Python runtime environment
    - bin/python           : Python interpreter
    - bin/uv               : UV package manager
    - lib/                 : Python standard library
    - lib/site-packages/   : Third-party libraries (FastAPI, uvicorn, etc.)
- icons/                   : Application icons

## System Requirements

EOF

if [ "${OS_TYPE}" = "Darwin" ]; then
    cat >> "${README_FILE}" << EOF
- macOS ${TARGET_ARCH} ($(if [ "${TARGET_ARCH}" = "x86_64" ]; then echo 'Intel/AMD 64-bit'; else echo 'Apple Silicon (ARM64)'; fi))
- About 500 MB free disk space
EOF
else
    cat >> "${README_FILE}" << EOF
- Linux ${TARGET_ARCH} ($(if [ "${TARGET_ARCH}" = "x86_64" ]; then echo 'Intel/AMD 64-bit'; else echo 'ARM 64-bit (aarch64)'; fi))
- About 500 MB free disk space
EOF
fi

cat >> "${README_FILE}" << EOF

## Notes

- First launch may take a few seconds to initialize
- Make the script executable: chmod +x ${APP_NAME}
- Do not move or delete the resources directory
- If you encounter issues, check the application logs

## Support

Project Homepage: https://github.com/dawei/patent-agent

Copyright (c) 2026 Dawei Team. All rights reserved.
EOF

echo "✓ README created"
echo ""

# 7. Create ZIP package
echo "Creating ZIP package..."

# Get the directory basename for zip
ZIP_BASENAME=$(basename "${ZIP_DIR}")

# Use zip command
if command -v zip &> /dev/null; then
    (cd "${TARGET_DIR}" && zip -qr "${ZIP_NAME}" "${ZIP_BASENAME}")
    echo "✓ ZIP package created using zip command"
elif command -v 7z &> /dev/null; then
    (cd "${TARGET_DIR}" && 7z a -tzip "${ZIP_NAME}" "${ZIP_BASENAME}")
    echo "✓ ZIP package created using 7z command"
else
    echo "❌ Neither zip nor 7z found. Please install:"
    echo "   Linux: sudo apt-get install zip"
    echo "   macOS: brew install zip"
    exit 1
fi

if [ $? -eq 0 ]; then
    echo "✓ ZIP package created successfully"
else
    echo "❌ Failed to create ZIP package"
    exit 1
fi

echo ""

# 8. Show results
echo "========================================="
echo "  Build Completed!"
echo "========================================="
echo ""

if [ -f "${TARGET_DIR}/${ZIP_NAME}" ]; then
    SIZE=$(du -h "${TARGET_DIR}/${ZIP_NAME}" | cut -f1)
    echo "✅ Portable ZIP Package:"
    echo "   Name:     ${ZIP_NAME}"
    echo "   Location: ${TARGET_DIR}/${ZIP_NAME}"
    echo "   Size:     ${SIZE}"
    echo ""
fi

echo "📦 Package Contents:"
echo "   - ${APP_NAME} (${TARGET_ARCH} binary)"
echo "   - resources/python-env/ (Python runtime + dependencies)"
echo "   - resources/welcome.html (Startup page)"
echo "   - icons/ (Application icons)"
echo "   - README.txt (Usage instructions)"
echo ""

echo "📋 Distribution Instructions:"
echo ""
echo "  1. Upload the ZIP file to your distribution platform"
echo "  2. Users can:"
echo "     - Download the ZIP file"
echo "     - Extract it to any folder"
echo "     - Run ./${APP_NAME}"
echo "     - No installation required!"
echo ""

echo "========================================="
