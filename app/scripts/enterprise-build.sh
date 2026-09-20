#!/usr/bin/env bash
# Enterprise 构建脚本
# 使用: bash scripts/enterprise-build.sh [platform]
#   platform: linux | macos | windows | all (默认: all)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

PLATFORM="${1:-all}"

echo "=================================="
echo " NormNomos Enterprise Build"
echo " Platform: $PLATFORM"
echo "=================================="

# 检查依赖
check_deps() {
    if ! command -v node &>/dev/null; then
        echo "ERROR: Node.js is required but not installed."
        exit 1
    fi
    if ! command -v npm &>/dev/null; then
        echo "ERROR: npm is required but not installed."
        exit 1
    fi
    NODE_VER=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
    if [ "$NODE_VER" -lt 20 ]; then
        echo "ERROR: Node.js >= 20 required, found $(node -v)"
        exit 1
    fi
    echo "[OK] Node.js $(node -v), npm $(npm -v)"
}

install_deps() {
    echo "[...] Installing dependencies..."
    npm ci
    echo "[OK] Dependencies installed"
}

build_linux() {
    echo "[...] Building Linux packages..."
    echo "  - Target: x86_64-unknown-linux-gnu"
    echo "  - Bundles: deb, AppImage"
    npm run enterprise:package:linux
    echo "[OK] Linux build complete"
}

build_macos() {
    echo "[...] Building macOS package..."
    echo "  - Target: aarch64-apple-darwin"
    echo "  - Bundles: dmg"
    npm run enterprise:package:macos
    echo "[OK] macOS build complete"
}

build_windows() {
    echo "[...] Building Windows package..."
    echo "  - Target: x86_64-pc-windows-msvc"
    echo "  - Bundles: msi"
    npm run enterprise:package:windows
    echo "[OK] Windows build complete"
}

# Main
check_deps
install_deps

case "$PLATFORM" in
    linux)
        build_linux
        ;;
    macos)
        build_macos
        ;;
    windows)
        build_windows
        ;;
    all)
        build_linux
        build_macos
        build_windows
        ;;
    *)
        echo "ERROR: Unknown platform '$PLATFORM'. Use: linux | macos | windows | all"
        exit 1
        ;;
esac

echo ""
echo "=================================="
echo " Build complete!"
echo " Artifacts location: src-tauri/target/release/bundle/"
echo "=================================="
