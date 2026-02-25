#!/bin/bash
# Linux/macOS standalone ZIP packager script
# This script creates a portable ZIP package that users can extract and run

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="${PROJECT_ROOT}/webui"
TAURI_DIR="${WEB_DIR}/src-tauri"
TARGET_DIR="${TAURI_DIR}/target/release"

echo "========================================"
echo "  Tauri Standalone ZIP Packager"
echo "========================================"
echo ""

# Detect OS
OS_TYPE=$(uname -s)
echo "Detected OS: ${OS_TYPE}"

# Get version from Cargo.toml
APP_NAME=$(grep "^name" "${TAURI_DIR}/Cargo.toml" | head -1 | awk '{print $2}' | tr -d '"')
APP_VERSION=$(grep "^version" "${TAURI_DIR}/Cargo.toml" | head -1 | awk '{print $2}' | tr -d '"')

echo "App: ${APP_NAME} v${APP_VERSION}"
echo ""

# 1. Build Tauri application
echo "[1/5] Building Tauri application..."
cd "${WEB_DIR}"

echo "Building frontend..."
pnpm build-only

echo "Building Tauri app..."
pnpm tauri build --config "${TAURI_DIR}/tauri.conf.standalone.json" --no-bundle

echo "✓ Tauri build completed"
echo ""

# 2. Prepare portable package directory
echo "[2/5] Preparing portable package..."
# Convert version format for directory name (0.1.0 -> 0_1_0)
VERSION_DIR=$(echo "${APP_VERSION}" | tr '.')
ZIP_DIR="${TARGET_DIR}/${APP_NAME}-standalone-${OS_TYPE,,}-portable-v${VERSION_DIR}"
ZIP_NAME="${APP_NAME}-standalone-${OS_TYPE,,}-portable-v${APP_VERSION}.zip"

rm -rf "${ZIP_DIR}"
mkdir -p "${ZIP_DIR}/resources"

# 3. Copy application files
echo "[3/5] Copying application files..."

# Main executable
echo "Copying main executable..."
if [ "${OS_TYPE}" = "Darwin" ]; then
    # macOS: Try universal-apple-darwin target first, then regular release
    if [ -f "${TARGET_DIR}/../universal-apple-darwin/release/${APP_NAME}" ]; then
        cp "${TARGET_DIR}/../universal-apple-darwin/release/${APP_NAME}" "${ZIP_DIR}/"
        echo "✓ macOS universal binary copied"
    elif [ -f "${TARGET_DIR}/${APP_NAME}" ]; then
        cp "${TARGET_DIR}/${APP_NAME}" "${ZIP_DIR}/"
        echo "✓ macOS executable copied"
    else
        echo "❌ macOS executable not found"
        exit 1
    fi
else
    # Linux executable
    cp "${TARGET_DIR}/${APP_NAME}" "${ZIP_DIR}/"
    echo "✓ Executable copied"
fi

# Resources
echo "Copying Python environment..."
if [ -d "${TAURI_DIR}/resources/python-env" ]; then
    cp -r "${TAURI_DIR}/resources/python-env" "${ZIP_DIR}/resources/"
    echo "✓ Python environment copied"
else
    echo "⚠ Warning: Python environment not found"
    echo "   Please run scripts/copy-resources.py first"
fi

echo "Copying backend scripts..."
cp "${TAURI_DIR}/start-backend.sh" "${ZIP_DIR}/resources/" 2>/dev/null || true
cp "${TAURI_DIR}/stop-backend.sh" "${ZIP_DIR}/resources/" 2>/dev/null || true
cp "${TAURI_DIR}/start-backend.bat" "${ZIP_DIR}/resources/" 2>/dev/null || true
cp "${TAURI_DIR}/stop-backend.bat" "${ZIP_DIR}/resources/" 2>/dev/null || true

echo "Copying icons..."
if [ -d "${TAURI_DIR}/icons" ]; then
    cp -r "${TAURI_DIR}/icons" "${ZIP_DIR}/"
fi

# Make scripts executable
chmod +x "${ZIP_DIR}/resources/"*.sh 2>/dev/null || true

echo "✓ Application files copied"
echo ""

# 4. Create README
echo "[4/5] Creating README..."
README_FILE="${ZIP_DIR}/README.txt"

cat > "${README_FILE}" << 'EOF'
# 大微 AI 助手 - Standalone 便携版

版本: ${APP_VERSION}

## 使用方法

1. 解压缩此 ZIP 文件到任意目录
2. 运行应用程序

EOF

if [ "${OS_TYPE}" = "Darwin" ]; then
    cat >> "${README_FILE}" << EOF
macOS:
  - 在终端运行: ./${APP_NAME}
  - 或添加执行权限: chmod +x ${APP_NAME}
  - 首次运行可能需要授予安全权限（系统偏好设置 > 安全性与隐私）

EOF
else
    cat >> "${README_FILE}" << EOF
Linux:
  - 在终端运行: ./${APP_NAME}
  - 首次运行可能需要添加执行权限: chmod +x ${APP_NAME}

EOF
fi

cat >> "${README_FILE}" << EOF
应用会在首次启动时自动启动后端服务。

## 目录结构

- ${APP_NAME}           : 主应用程序
- resources/            : 资源文件目录
  - python-env/         : Python 运行时环境
    - bin/python        : Python 解释器
    - bin/pip           : Python 包管理器
    - lib/              : Python 标准库
    - lib/site-packages/ : 第三方库 (FastAPI, uvicorn 等)
  - start-backend.sh    : 后端启动脚本
  - stop-backend.sh     : 后端停止脚本
- icons/                : 应用图标

## 系统要求

EOF

if [ "${OS_TYPE}" = "Darwin" ]; then
    cat >> "${README_FILE}" << EOF
- macOS 11 (Big Sur) 或更高版本（支持 Intel 和 Apple Silicon）
- 约 500 MB 可用磁盘空间
EOF
else
    cat >> "${README_FILE}" << EOF
- Linux x86_64 发行版（glibc 2.17+）
- 约 500 MB 可用磁盘空间
EOF
fi

cat >> "${README_FILE}" << EOF

## 注意事项

- 首次运行可能需要几秒钟来初始化
- 请勿移动或删除 resources 目录
- 如遇问题，请查看应用日志
- Linux/macOS 版本使用 bin/python

## 技术支持

项目主页: https://github.com/dawei/patent-agent

Copyright © 2026 大微团队. All rights reserved.
EOF

# Replace ${APP_VERSION} placeholder
sed -i.tmp "s/\${APP_VERSION}/${APP_VERSION}/g" "${README_FILE}" 2>/dev/null || sed -i.bak "s/\${APP_VERSION}/${APP_VERSION}/g" "${README_FILE}"
rm -f "${README_FILE}".tmp "${README_FILE}".bak 2>/dev/null || true

echo "✓ README created"
echo ""

# 5. Create ZIP package
echo "[5/5] Creating ZIP package..."

# Get the directory basename for zip
ZIP_BASENAME=$(basename "${ZIP_DIR}")

if [ "${OS_TYPE}" = "Darwin" ]; then
    # macOS: use zip
    if command -v zip &> /dev/null; then
        (cd "${TARGET_DIR}" && zip -qr "${ZIP_NAME}" "${ZIP_BASENAME}")
    else
        echo "❌ zip command not found. Please install: brew install zip"
        exit 1
    fi
else
    # Linux: use zip
    if command -v zip &> /dev/null; then
        (cd "${TARGET_DIR}" && zip -qr "${ZIP_NAME}" "${ZIP_BASENAME}")
    elif command -v 7z &> /dev/null; then
        (cd "${TARGET_DIR}" && 7z a -tzip "${ZIP_NAME}" "${ZIP_BASENAME}")
    else
        echo "❌ Neither zip nor 7z found. Please install: sudo apt-get install zip"
        exit 1
    fi
fi

if [ $? -eq 0 ]; then
    echo "✓ ZIP package created"
else
    echo "❌ Failed to create ZIP package"
    exit 1
fi

echo ""

# 6. Show results
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
echo "   - Application executable/bundle"
echo "   - resources/python-env/ (Python runtime + dependencies)"
echo "   - resources/start-backend.sh (Backend startup script)"
echo "   - resources/stop-backend.sh (Backend shutdown script)"
echo "   - README.txt (Usage instructions)"
echo ""

echo "📋 Distribution Instructions:"
echo ""
echo "  1. Upload the ZIP file to your distribution platform"
echo "  2. Users can:"
echo "     - Download the ZIP file"
echo "     - Extract it to any folder"
echo "     - Run the application directly"
echo "     - No installation required!"
echo ""

echo "========================================="

endlocal
