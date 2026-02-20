#!/bin/bash
# 构建 Python Wheel 包（包含前后端）
# 用法: bash scripts/build-python-wheel.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${BLUE}========================================"
echo "  构建 Python Wheel 包 (包含前端)"
echo "========================================${NC}"
echo ""
echo "这将构建一个包含前后端的完整 wheel 包"
echo ""

# 1. 构建前端
echo -e "${YELLOW}[1/3] 构建前端应用...${NC}"
cd "$PROJECT_ROOT/webui"
pnpm build-only

echo ""

# 2. 复制前端到后端
echo -e "${YELLOW}[2/3] 复制前端到 Python 包...${NC}"
FRONTEND_DEST="$PROJECT_ROOT/agent/dawei/frontend"

# 清理旧的前端
if [ -d "$FRONTEND_DEST" ]; then
    echo "清理旧的前端文件..."
    rm -rf "$FRONTEND_DEST"
fi

# 创建目标目录
mkdir -p "$FRONTEND_DEST"

# 复制前端构建产物
echo "复制前端文件..."
cp -r "$PROJECT_ROOT/webui/dist/"* "$FRONTEND_DEST/"

echo "前端大小:"
du -sh "$FRONTEND_DEST"
echo ""

# 3. 构建 wheel
echo -e "${YELLOW}[3/3] 构建 Python Wheel 包...${NC}"
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

# 获取并显示版本号
echo ""
echo -e "${BLUE}📌 版本信息:${NC}"
VERSION=$(python3 -c "from setuptools_scm import get_version; print(get_version(root='.'))" 2>/dev/null || echo "N/A")
echo "版本号: ${VERSION}"
echo ""

echo ""
echo -e "${GREEN}✅ Python Wheel 包构建成功！${NC}"
echo ""
echo "安装与使用:"
echo "  1. 安装: pip install dist/davybot-*.whl"
echo "  2. 启动: dawei"
echo "  3. 访问: http://localhost:8465/app"
echo ""
echo "前端路径: http://localhost:8465/app/"
echo "API 文档: http://localhost:8465/docs"
echo ""
