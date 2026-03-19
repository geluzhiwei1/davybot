#!/bin/bash
# 构建 Python Wheel 包（包含前后端和 Tauri 可执行文件）
# 用法: bash scripts/build-python-wheel.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${BLUE}========================================"
echo "  构建 Python Wheel 包 (包含前端和 GUI)"
echo "========================================${NC}"
echo ""
echo "这将构建一个包含前端和 Tauri GUI 可执行文件的完整 wheel 包"
echo ""

# 检查系统依赖 (仅 Linux)
if [ "$(uname -s)" = "Linux" ]; then
    echo -e "${YELLOW}检查系统依赖...${NC}"
    MISSING_DEPS=""

    # 检查 pkg-config
    if ! command -v pkg-config &> /dev/null; then
        MISSING_DEPS="$MISSING_DEPS pkg-config"
    fi

    # 检查 GTK3 和 WebKit 相关库
    for lib in libgtk-3 libsoup-3.0 libjavascriptcoregtk-4.1; do
        if ! pkg-config --exists $lib 2>/dev/null; then
            case $lib in
                libgtk-3)
                    MISSING_DEPS="$MISSING_DEPS libgtk-3-dev"
                    ;;
                libsoup-3.0)
                    MISSING_DEPS="$MISSING_DEPS libsoup-3.0-dev"
                    ;;
                libjavascriptcoregtk-4.1)
                    MISSING_DEPS="$MISSING_DEPS libwebkit2gtk-4.1-dev"
                    ;;
            esac
        fi
    done

    if [ -n "$MISSING_DEPS" ]; then
        echo -e "${RED}✗ 缺少系统依赖${NC}"
        echo ""
        echo "缺少以下依赖包:$MISSING_DEPS"
        echo ""
        echo "请运行以下命令安装:"
        echo -e "${GREEN}sudo apt-get update && sudo apt-get install -y \\"
        echo "  libgtk-3-dev libwebkit2gtk-4.1-dev libappindicator3-dev \\"
        echo "  librsvg2-dev libsoup-3.0-dev${NC}"
        echo ""
        echo "或在 CI/CD 环境中运行此脚本"
        exit 1
    fi
    echo -e "${GREEN}✓ 系统依赖检查通过${NC}"
    echo ""
fi

# 1. 构建前端
echo -e "${YELLOW}[1/5] 构建前端应用...${NC}"
cd "$PROJECT_ROOT/webui"
pnpm install --frozen-lockfile

echo ""

# 2. 准备 drawio 资源
echo -e "${YELLOW}[2/5] 准备 drawio 资源...${NC}"
cd "$PROJECT_ROOT"
mkdir -p deps
if [ ! -d "deps/drawio" ]; then
    echo "克隆 drawio 仓库..."
    git clone https://github.com/geluzhiwei1/drawio.git deps/drawio
fi
cd "$PROJECT_ROOT/webui"
bash scripts/prepare-drawio.sh

echo ""

# 3. 构建 Tauri 应用（仅当前平台，可选）
echo -e "${YELLOW}[3/5] 构建 Tauri 应用 (可选)...${NC}"
cd "$PROJECT_ROOT/webui"

# 检测当前平台
OS_TYPE=$(uname -s)
ARCH_TYPE=$(uname -m)

TARGET=""
EXE_NAME=""

case "$OS_TYPE" in
    Linux*)
        case "$ARCH_TYPE" in
            x86_64)
                TARGET="x86_64-unknown-linux-gnu"
                EXE_NAME="dawei-gui-linux-x86_64"
                ;;
        esac
        ;;
    Darwin*)
        case "$ARCH_TYPE" in
            x86_64)
                TARGET="x86_64-apple-darwin"
                EXE_NAME="dawei-gui-darwin-x86_64"
                ;;
            arm64)
                TARGET="aarch64-apple-darwin"
                EXE_NAME="dawei-gui-darwin-aarch64"
                ;;
        esac
        ;;
    MINGW*|MSYS*|CYGWIN*)
        case "$ARCH_TYPE" in
            x86_64)
                TARGET="x86_64-pc-windows-msvc"
                EXE_NAME="dawei-gui-windows-x86_64.exe"
                ;;
        esac
        ;;
esac

TAURI_BUILT=false
if [ -z "$TARGET" ]; then
    echo -e "${RED}错误: 无法识别当前平台架构 ($OS_TYPE $ARCH_TYPE)${NC}"
    echo -e "${RED}Tauri 构建失败，打包终止${NC}"
    exit 1
else
    echo "检测到平台: $TARGET"
    echo "构建 Tauri 应用..."
    if ! pnpm tauri build --no-bundle --target "$TARGET" 2>&1; then
        echo -e "${RED}✗ Tauri 构建失败${NC}"
        echo -e "${RED}打包终止。请检查 Tauri 构建错误或使用 GitHub Actions 构建完整的跨平台发布包${NC}"
        exit 1
    fi
    TAURI_BUILT=true
    echo -e "${GREEN}✓ Tauri 构建成功${NC}"
fi

echo ""

# 4. 复制前端和 GUI 可执行文件到后端
echo -e "${YELLOW}[4/5] 复制前端和 GUI 到 Python 包...${NC}"
cd "$PROJECT_ROOT"

# 复制前端资源
echo "复制前端资源..."
mkdir -p agent/dawei/frontend
rm -rf agent/dawei/frontend/*
cp -r webui/src-tauri/resources/* agent/dawei/frontend/
# 确保 welcome.html 被包含
if [ -f "webui/src-tauri/resources/welcome.html" ]; then
    cp webui/src-tauri/resources/welcome.html agent/dawei/frontend/
fi

# 复制 Tauri 可执行文件
if [ "$TAURI_BUILT" = true ]; then
    echo "复制 Tauri 可执行文件..."
    mkdir -p agent/dawei/bin

    if [ -f "webui/src-tauri/target/$TARGET/release/dawei-gui" ]; then
        cp "webui/src-tauri/target/$TARGET/release/dawei-gui" "agent/dawei/bin/$EXE_NAME"
        chmod +x "agent/dawei/bin/$EXE_NAME"
        echo "已复制: $EXE_NAME"
    elif [ -f "webui/src-tauri/target/$TARGET/release/dawei-gui.exe" ]; then
        cp "webui/src-tauri/target/$TARGET/release/dawei-gui.exe" "agent/dawei/bin/$EXE_NAME"
        echo "已复制: $EXE_NAME"
    else
        echo -e "${YELLOW}警告: 未找到 Tauri 可执行文件${NC}"
    fi

    echo "bin 目录内容:"
    ls -la agent/dawei/bin/
fi

echo "前端资源大小:"
du -sh agent/dawei/frontend
echo ""

# 5. 构建 wheel
echo -e "${YELLOW}[5/5] 构建 Python Wheel 包...${NC}"
cd "$PROJECT_ROOT/agent"

# 清理旧的构建产物
echo "清理旧的构建产物..."
rm -rf dist/ build/ *.egg-info

# 构建 wheel
echo "构建 wheel..."
python3 -m build

echo ""
echo -e "${GREEN}========================================"
echo "  ✅ 构建完成！"
echo "========================================${NC}"
echo ""

# 显示构建产物
if [ -d "dist" ]; then
    echo -e "${BLUE}📦 构建产物:${NC}"
    ls -lh dist/
    echo ""

    # 显示详细信息
    echo -e "${BLUE}📊 包信息:${NC}"
    for file in dist/*; do
        if [ -f "$file" ]; then
            echo ""
            echo "文件: $(basename $file)"
            echo "大小: $(du -h "$file" | cut -f1)"
            echo "路径: $file"
        fi
    done
fi

echo ""
echo -e "${GREEN}✅ Python Wheel 包构建成功！${NC}"
echo ""
echo "安装与使用:"
echo "  1. 安装: pip install dist/dawei-*.whl"
echo "  2. 启动服务器: dawei-server"
echo "  3. 启动 GUI (如果包含): dawei gui"
echo "  4. 访问: http://localhost:8465/app"
echo ""
echo "前端路径: http://localhost:8465/app/"
echo "API 文档: http://localhost:8465/docs"
echo ""

if [ "$TAURI_BUILT" = true ]; then
    echo -e "${BLUE}注意: 此包包含当前平台 ($EXE_NAME) 的 GUI 可执行文件${NC}"
    echo "如需其他平台的 GUI 可执行文件，请使用 GitHub Actions 构建完整发布包"
    echo ""
fi
