#!/bin/bash
set -e

echo "🧪 Running Backend CLI Tests..."

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 项目根目录
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo -e "${BLUE}📂 Working directory: ${ROOT_DIR}${NC}"

# 进入后端目录
cd agent

# 1. 检查Python环境
echo -e "${YELLOW}🐍 Checking Python environment...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✅ Python version: ${PYTHON_VERSION}${NC}"

# 2. 检查uv
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}⚠️  uv not found. Install from: https://astral.sh/uv${NC}"
fi

# 3. 安装测试依赖
echo -e "${YELLOW}📦 Installing test dependencies...${NC}"
if command -v uv &> /dev/null; then
    uv pip install pytest pytest-asyncio pytest-cov --quiet
else
    pip install pytest pytest-asyncio pytest-cov --quiet
fi

# 4. 运行不同级别的测试
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${BLUE}       Backend CLI Test Suite                   ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo ""

# 解析命令行参数
TEST_LEVEL="${1:-all}"
VERBOSE="${2:-false}"

case "$TEST_LEVEL" in
    simple|smoke)
        echo -e "${YELLOW}🔬 Running simple/smoke tests...${NC}"
        TEST_ARGS="tests/cli/simple/ -v -m smoke"
        ;;
    medium)
        echo -e "${YELLOW}🔬 Running medium complexity tests...${NC}"
        TEST_ARGS="tests/cli/medium/ -v -m medium"
        ;;
    complex)
        echo -e "${YELLOW}🔬 Running complex tests...${NC}"
        TEST_ARGS="tests/cli/complex/ -v -m complex"
        ;;
    all)
        echo -e "${YELLOW}🔬 Running all CLI tests...${NC}"
        TEST_ARGS="tests/cli/ -v"
        ;;
    coverage)
        echo -e "${YELLOW}🔬 Running tests with coverage...${NC}"
        TEST_ARGS="tests/ -v --cov=agent/dawei --cov-report=html"
        ;;
    *)
        echo -e "${RED}❌ Unknown test level: $TEST_LEVEL${NC}"
        echo "Usage: $0 [simple|medium|complex|all|coverage] [verbose]"
        exit 1
        ;;
esac

# 添加verbose标志
if [ "$VERBOSE" = "true" ]; then
    TEST_ARGS="$TEST_ARGS -s"
fi

# 运行测试
echo ""
echo -e "${YELLOW}🚀 Executing: pytest ${TEST_ARGS}${NC}"
echo ""

START_TIME=$(date +%s)

if pytest $TEST_ARGS; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ All tests PASSED!${NC}"
    echo -e "${GREEN}⏱️  Duration: ${DURATION}s${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo ""

    # 如果是coverage测试，显示报告路径
    if [ "$TEST_LEVEL" = "coverage" ]; then
        echo -e "${YELLOW}📊 Coverage report: agent/htmlcov/index.html${NC}"
    fi

    exit 0
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo -e "${RED}❌ Tests FAILED!${NC}"
    echo -e "${RED}⏱️  Duration: ${DURATION}s${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}💡 Run with verbose to see more details:${NC}"
    echo -e "   $0 $TEST_LEVEL true"
    echo ""

    exit 1
fi
