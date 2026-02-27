#!/bin/bash
# Complete standalone build script for Linux/macOS
# Creates portable ZIP package
# Updated to match GitHub CI workflow

set -e

# Get script directory absolute path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

echo "========================================="
echo "   Dawei Standalone Build Script v2"
echo "   ==============================="
echo "   Creates portable ZIP package"
echo "   (Matches GitHub CI workflow)"
echo "========================================="
echo ""

# Build ZIP package
echo "[1/1] Building portable ZIP package..."
bash "${SCRIPT_DIR}/build-standalone-zip.sh"

echo ""
echo "========================================="
echo "   Build Completed!"
echo "========================================="
echo ""

echo "📦 Build Artifact:"
echo ""
echo "   ZIP Package:   dawei-standalone-$(uname -s)-portable-v*.zip"
echo ""
echo "   Users can:"
echo "     - Download the ZIP file"
echo "     - Extract it to any folder"
echo "     - Run the application directly"
echo "     - No installation required!"
echo ""
