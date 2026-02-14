#!/bin/bash
# 复制 Python 虚拟环境到 Tauri 资源目录
# 用法: bash scripts/copy-python-env.sh

set -e

# 路径配置
BACKEND_VENV="agent/.venv"
TAURI_RESOURCES="webui/src-tauri/resources/python-env"

echo "========================================="
echo "复制 Python 虚拟环境到 Tauri"
echo "========================================="

# 检查源虚拟环境
if [ ! -d "$BACKEND_VENV" ]; then
    echo "❌ 错误: 虚拟环境不存在"
    echo "   期望位置: $BACKEND_VENV"
    echo ""
    echo "请先运行: bash scripts/prepare-python-env.sh"
    exit 1
fi

echo "✓ 源虚拟环境: $BACKEND_VENV"

# 创建目标目录
echo "创建目标目录: $TAURI_RESOURCES"
mkdir -p "$(dirname "$TAURI_RESOURCES")"

# 清理旧文件
if [ -d "$TAURI_RESOURCES" ]; then
    echo "清理旧文件..."
    rm -rf "$TAURI_RESOURCES"
fi

# 复制虚拟环境
echo "复制虚拟环境（这可能需要几分钟）..."
cp -r "$BACKEND_VENV" "$TAURI_RESOURCES"

# 优化虚拟环境大小
echo "优化虚拟环境..."
cd "$TAURI_RESOURCES"

# 删除 Python 缓存
echo "  - 删除 __pycache__ ..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# 删除 .pyc 文件
echo "  - 删除 .pyc 文件..."
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# 删除 .egg-info 目录
echo "  - 删除 .egg-info 目录..."
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# 删除测试目录
echo "  - 删除 tests 目录..."
find . -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "test" -exec rm -rf {} + 2>/dev/null || true

cd - > /dev/null

# 计算大小
original_size=$(du -sh "$BACKEND_VENV" 2>/dev/null | cut -f1)
optimized_size=$(du -sh "$TAURI_RESOURCES" 2>/dev/null | cut -f1)

echo ""
echo "========================================="
echo "✅ 虚拟环境复制完成！"
echo "========================================="
echo "原始大小: $original_size"
echo "优化后:   $optimized_size"
echo "位置:     $TAURI_RESOURCES"
echo ""
echo "下一步:"
echo "  1. 更新 tauri.conf.json 包含 resources/python-env/*"
echo "  2. 运行 pnpm tauri build"
