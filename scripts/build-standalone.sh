#!/bin/bash
# 构建完整的独立桌面应用（包含 Python 和前端）
# 用法: bash scripts/build-standalone.sh

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${BLUE}========================================"
echo "  构建完整的独立桌面应用"
echo "========================================${NC}"
echo ""
echo "项目根目录: $PROJECT_ROOT"
echo ""

# 1. 准备 Python 环境
echo -e "${YELLOW}[1/5] 准备 Python 虚拟环境...${NC}"
cd "$PROJECT_ROOT"
bash scripts/prepare-python-env.sh

# 2. 复制虚拟环境
echo ""
echo -e "${YELLOW}[2/5] 复制 Python 虚拟环境到 Tauri...${NC}"
bash scripts/copy-python-env.sh

# 3. 构建前端
echo ""
echo -e "${YELLOW}[3/5] 构建前端应用...${NC}"
cd "$PROJECT_ROOT/webui"
pnpm build-only

# 4. 构建 Tauri 应用 (Standalone)
echo ""
echo -e "${YELLOW}[4/5] 构建 Tauri 桌面应用 (Standalone)...${NC}"
echo "这可能需要 5-10 分钟..."
cd "$PROJECT_ROOT/webui"
# Note: Tauri builds in release mode by default, --release flag is not needed
# Using default config which is now the standalone configuration
pnpm tauri build

# 5. 显示构建结果
echo ""
echo -e "${YELLOW}[5/5] 构建完成！${NC}"
echo ""

# 查找构建产物
BUNDLE_DIR="$PROJECT_ROOT/webui/src-tauri/target/release/bundle"

if [ -d "$BUNDLE_DIR" ]; then
    echo -e "${GREEN}✅ 构建产物：${NC}"
    echo ""

    # DEB 包
    if [ -f "$BUNDLE_DIR/deb"/*.deb ]; then
        echo -e "${BLUE}Debian/Ubuntu 包:${NC}"
        ls -lh "$BUNDLE_DIR/deb"/*.deb | awk '{print "  " $9 " (" $5 ")"}'
        echo ""
    fi

    # AppImage
    if [ -f "$BUNDLE_DIR/appimage"/*.AppImage ]; then
        echo -e "${BLUE}AppImage 包:${NC}"
        ls -lh "$BUNDLE_DIR/appimage"/*.AppImage | awk '{print "  " $9 " (" $5 ")"}'
        echo ""
    fi

    # RPM 包
    if [ -f "$BUNDLE_DIR/rpm"/*.rpm ]; then
        echo -e "${BLUE}RedHat/Fedora 包:${NC}"
        ls -lh "$BUNDLE_DIR/rpm"/*.rpm | awk '{print "  " $9 " (" $5 ")"}'
        echo ""
    fi
else
    echo -e "${YELLOW}⚠️ 未找到构建产物${NC}"
fi

echo -e "${GREEN}📦 应用特性：${NC}"
echo "  ✓ 包含完整 Python 运行时"
echo "  ✓ 包含所有 Python 依赖 (42+ 个包)"
echo "  ✓ 包含前端应用 (Vue 3)"
echo "  ✓ 完全独立，无需额外安装"
echo "  ✓ 开箱即用"
echo ""

# 计算虚拟环境大小
VENV_SIZE=$(du -sh "$PROJECT_ROOT/webui/src-tauri/resources/python-env" 2>/dev/null | cut -f1)
if [ -n "$VENV_SIZE" ]; then
    echo -e "${BLUE}虚拟环境大小:${NC} $VENV_SIZE"
fi

echo ""
echo -e "${GREEN}✅ 构建成功！${NC}"
echo ""
echo "要安装应用，请参考对应平台的安装说明："
echo "  - Linux (Debian/Ubuntu): sudo dpkg -i dawei-standalone_*.deb"
echo "  - Linux (AppImage): chmod +x dawei-standalone*.AppImage && ./dawei-standalone*.AppImage"
echo "  - Linux (RedHat/Fedora): sudo rpm -i dawei-standalone-*.rpm"
