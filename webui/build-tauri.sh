#!/bin/bash
# Build script for Tauri desktop application (Linux/macOS)

set -e

echo "========================================="
echo "Building Dawei Tauri Desktop App"
echo "========================================="

# Navigate to frontend directory
cd "$(dirname "$0")"

# Check if Rust is installed
if ! command -v cargo &> /dev/null; then
    echo "ERROR: Rust is not installed!"
    echo "Please install Rust from https://rustup.rs/"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js is not installed!"
    echo "Please install Node.js from https://nodejs.org/"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
pnpm install

# Build backend for bundling
echo ""
echo "Building backend..."
cd "../../services/agent-api"

# Check if UV is available
if command -v uv &> /dev/null; then
    echo "Using UV to package backend..."
    # Create a portable Python environment
    if [[ ! -d ".venv" ]]; then
        uv venv .venv
    fi
    uv pip install -e .
else
    echo "Using venv to package backend..."
    if [[ ! -d ".venv" ]]; then
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install -e .
fi

cd "../../apps/web"

# Build frontend
echo ""
echo "Building frontend..."
pnpm build

# Build Tauri app
echo ""
echo "Building Tauri application..."
pnpm tauri build

echo ""
echo "========================================="
echo "Build completed successfully!"
echo "========================================="
echo ""
echo "Desktop application bundles:"
ls -lh src-tauri/target/release/bundle/
echo ""
echo "To install and run:"
echo "  - Linux:   Install the .deb package or extract .AppImage"
echo "  - macOS:   Open the .dmg file and drag to Applications"
echo "  - Windows: Run the .exe installer"
echo ""
