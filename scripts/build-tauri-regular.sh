#!/bin/bash
# 构建 Tauri 普通版本（纯前端，不包含后端）
# 用法: bash scripts/build-tauri-regular.sh

set -e

echo "========================================="
echo "  构建 Tauri 普通版本 (纯前端)"
echo "========================================="
echo ""
echo "特点:"
echo "  - 只包含前端应用"
echo "  - 体积小 (~30-50 MB)"
echo "  - 不包含后端和 Python"
echo "  - 需要单独运行后端服务器"
echo ""

# 进入前端目录
cd "$(dirname "$0")/../webui"

# 构建前端
echo "[1/2] 构建前端应用..."
pnpm build-only

# 构建 Tauri (普通版本 - 无后端)
echo ""
echo "[2/2] 构建 Tauri 应用 (普通版本 - 纯前端)..."
echo "不包含后端管理功能..."
# Note: Tauri builds in release mode by default, --release flag is not needed
pnpm tauri build --config src-tauri/tauri.conf.json

# 显示构建结果
echo ""
echo "========================================="
echo "✅ 构建完成！"
echo "========================================="
echo ""
echo "构建产物:"
echo "  Linux: src-tauri/target/release/bundle/"
echo "    - DEB 包 (~30 MB)"
echo "    - AppImage (~40 MB)"
echo "    - RPM 包 (~30 MB)"
echo ""
echo "使用要求:"
echo "  1. 安装后端:"
echo "     pip install agent/dist/dawei_server-*.whl"
echo ""
echo "  2. 启动后端服务器:"
echo "     dawei-server"
echo ""
echo "  3. 启动前端应用:"
echo "     - 方式1: 从应用菜单启动"
echo "     - 方式2: 运行可执行文件"
echo ""
echo "连接配置:"
echo "  - 前端会自动连接到: ws://localhost:8465/ws"
echo "  - 后端服务器运行在: http://localhost:8465"
echo ""
