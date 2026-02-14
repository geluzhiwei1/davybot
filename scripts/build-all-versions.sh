#!/bin/bash
# 同时构建普通版本和 Standalone 版本
# 用法: bash scripts/build-all-versions.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${BLUE}========================================"
echo "  构建所有 Tauri 版本"
echo "========================================${NC}"
echo ""
echo "这将构建两个版本:"
echo "  1. 普通版本 (不包含 Python, ~50 MB)"
echo "  2. Standalone 版本 (包含 Python 1.3 GB, ~450 MB)"
echo ""
echo "预计总时间: 10-20 分钟"
echo ""

# 询问是否继续
read -p "是否继续? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

echo ""
echo -e "${GREEN}========================================"
echo "  [1/2] 构建普通版本"
echo "========================================${NC}"
echo ""

bash "$PROJECT_ROOT/scripts/build-tauri-regular.sh"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 普通版本构建成功${NC}"
else
    echo -e "${YELLOW}⚠️ 普通版本构建失败${NC}"
fi

echo ""
echo -e "${GREEN}========================================"
echo "  [2/2] 构建 Standalone 版本"
echo "========================================${NC}"
echo ""

bash "$PROJECT_ROOT/scripts/build-standalone.sh"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Standalone 版本构建成功${NC}"
else
    echo -e "${YELLOW}⚠️ Standalone 版本构建失败${NC}"
fi

echo ""
echo -e "${BLUE}========================================"
echo "  构建总结"
echo "========================================${NC}"
echo ""

BUNDLE_DIR="$PROJECT_ROOT/webui/src-tauri/target/release/bundle"

echo -e "${GREEN}构建产物位置:${NC}"
echo "  $BUNDLE_DIR"
echo ""

echo -e "${BLUE}版本对比:${NC}"
echo ""
echo "1. 普通版本:"
echo "   - 体积: ~50-100 MB"
echo "   - Python: 需要外部安装 Python 3.12+"
echo "   - 依赖: 需要手动安装 pip install -e agent"
echo "   - 适用: 开发环境、已有 Python 的用户"
echo ""

echo "2. Standalone 版本:"
echo "   - 体积: ~450-500 MB (Release)"
echo "   - Python: 内置 Python 3.12 + 所有依赖"
echo "   - 依赖: 无需任何额外安装"
echo "   - 适用: 生产环境、普通用户"
echo ""

echo -e "${GREEN}✅ 所有构建完成！${NC}"
