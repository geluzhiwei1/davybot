#!/bin/bash
# 准备 Python 虚拟环境脚本
# 用法: bash scripts/prepare-python-env.sh

set -e

echo "========================================="
echo "准备 Python 虚拟环境"
echo "========================================="

# 进入后端目录
cd "$(dirname "$0")/../agent"

# 检查 Python 版本
PYTHON_CMD=""

# 优先使用 UV 的 Python 3.12
if command -v uv &> /dev/null; then
    if uv python list | grep -q "3.12"; then
        PYTHON_CMD="uv run --python 3.12 python"
        PYTHON_VERSION="3.12.12 (via UV)"
        echo "✓ 检测到 Python 版本: $PYTHON_VERSION"
    fi
fi

# 回退到系统 Python 3
if [ -z "$PYTHON_CMD" ]; then
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        echo "✓ 检测到 Python 版本: $PYTHON_VERSION"

        # 检查版本是否满足要求
        major=$(echo $PYTHON_VERSION | cut -d. -f1)
        minor=$(echo $PYTHON_VERSION | cut -d. -f2)

        if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 12 ]); then
            echo "❌ 错误: Python 版本过低 (需要 >= 3.12)"
            echo "当前版本: $PYTHON_VERSION"
            echo ""
            echo "建议: 安装 UV 并使用 Python 3.12"
            echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
            exit 1
        fi
    else
        echo "❌ 错误: 未找到 python3"
        echo "请安装 Python 3.12 或更高版本"
        exit 1
    fi
fi

# 创建虚拟环境（如果不存在）
if [ ! -d ".venv" ]; then
    echo "创建虚拟环境..."
    $PYTHON_CMD -m venv .venv
    echo "✓ 虚拟环境创建成功"
else
    echo "✓ 虚拟环境已存在"
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source .venv/bin/activate

# 升级 pip
echo "升级 pip..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1

# 安装 dawei 包
echo "安装 dawei 包..."
if [ -f "pyproject.toml" ]; then
    pip install -e . > /dev/null 2>&1
else
    echo "❌ 错误: 未找到 pyproject.toml"
    exit 1
fi

# 验证安装
echo ""
echo "验证安装..."
if python -c "import dawei; print(f'✓ dawei 版本: {dawei.__version__}')" 2>/dev/null; then
    :
else
    echo "❌ 错误: dawei 包安装失败"
    exit 1
fi

# 显示已安装的包数量
package_count=$(pip list | wc -l)
echo "✓ 已安装 $package_count 个包"

# 计算虚拟环境大小
venv_size=$(du -sh .venv 2>/dev/null | cut -f1)
echo ""
echo "========================================="
echo "✅ 虚拟环境准备完成！"
echo "========================================="
echo "📦 大小: $venv_size"
echo "📍 位置: $(pwd)/.venv"
echo ""
echo "要使用虚拟环境，请运行:"
echo "  source .venv/bin/activate"
