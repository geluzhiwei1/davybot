#!/bin/bash
set -e

echo "🧪 Running CLI Tests with Ollama..."

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

# 加载测试配置
PYTHONPATH="$ROOT_DIR/agent:$PYTHONPATH"
export PYTHONPATH

# 1. 检查Ollama是否运行
echo -e "${YELLOW}🦙 Checking Ollama service...${NC}"
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${RED}❌ Ollama is not running!${NC}"
    echo -e "${YELLOW}💡 Start Ollama with: ollama serve${NC}"
    echo -e "${YELLOW}💡 Pull a model: ollama pull qwen2:7b${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Ollama is running${NC}"

# 2. 检查是否有可用模型
echo -e "${YELLOW}🔍 Checking available models...${NC}"
MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "import sys, json; data=json.load(sys.stdin); print('\n'.join([m['name'] for m in data.get('models', [])]))")
if [ -z "$MODELS" ]; then
    echo -e "${RED}❌ No models found in Ollama${NC}"
    echo -e "${YELLOW}💡 Pull a model: ollama pull qwen2:7b${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Available models:${NC}"
echo "$MODELS" | head -5

# 3. 设置测试环境
echo -e "${YELLOW}⚙️  Setting up test environment...${NC}"
TEST_WORKSPACE="$ROOT_DIR/agent/tests/cli-test-workspace"
export WORKSPACE="$TEST_WORKSPACE"
export LITELLM_MODEL="ollama/qwen2:7b"
export LITELLM_API_BASE="http://localhost:11434"
export NO_MOCK="1"
echo -e "${GREEN}✅ Workspace: $TEST_WORKSPACE${NC}"
echo -e "${GREEN}✅ Model: $LITELLM_MODEL${NC}"

# 4. 解析命令行参数
TEST_LEVEL="${1:-all}"
VERBOSE="${2:-false}"

# 5. 运行测试
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${BLUE}       CLI Tests with Ollama                    ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo ""

case "$TEST_LEVEL" in
    simple|smoke)
        echo -e "${YELLOW}🔬 Running simple tests with Ollama...${NC}"
        TEST_ARGS="tests/cli/simple/ -v -m smoke -s"
        ;;
    medium)
        echo -e "${YELLOW}🔬 Running medium tests with Ollama...${NC}"
        TEST_ARGS="tests/cli/medium/ -v -m medium -s"
        ;;
    complex)
        echo -e "${YELLOW}🔬 Running complex tests with Ollama...${NC}"
        TEST_ARGS="tests/cli/complex/ -v -m complex -s"
        ;;
    all)
        echo -e "${YELLOW}🔬 Running all CLI tests with Ollama...${NC}"
        TEST_ARGS="tests/cli/ -v -s"
        ;;
    ollama-check)
        echo -e "${YELLOW}🔍 Testing Ollama connection only...${NC}"
        python3 -c "
import requests
try:
    response = requests.get('http://localhost:11434/api/tags', timeout=5)
    if response.status_code == 200:
        data = response.json()
        print('✅ Ollama is running')
        print('📦 Available models:')
        for model in data.get('models', [])[:5]:
            print(f'  - {model[\"name\"]} ({model.get(\"size\", 0) / 1024 / 1024:.1f} GB)')
    else:
        print('❌ Ollama returned error:', response.status_code)
except Exception as e:
    print('❌ Cannot connect to Ollama:', e)
"
        exit 0
        ;;
    *)
        echo -e "${RED}❌ Unknown test level: $TEST_LEVEL${NC}"
        echo "Usage: $0 [simple|medium|complex|all|ollama-check] [verbose]"
        exit 1
        ;;
esac

# 添加verbose标志
if [ "$VERBOSE" = "true" ]; then
    TEST_ARGS="$TEST_ARGS -vv"
fi

# 运行测试
echo ""
echo -e "${YELLOW}🚀 Executing: pytest ${TEST_ARGS}${NC}"
echo ""

START_TIME=$(date +%s)

# 设置环境变量并运行测试
export PYTHONPATH="$ROOT_DIR/agent:$PYTHONPATH"

if pytest $TEST_ARGS --tb=short --maxfail=5; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ All tests PASSED with Ollama!${NC}"
    echo -e "${GREEN}⏱️  Duration: ${DURATION}s${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo ""

    # 显示测试统计
    echo -e "${YELLOW}📊 Test Statistics:${NC}"
    echo -e "   Model: ollama/qwen2:7b"
    echo -e "   Workspace: $TEST_WORKSPACE"

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

    # 故障排除提示
    echo -e "${YELLOW}💡 Troubleshooting:${NC}"
    echo -e "   1. Check Ollama: curl http://localhost:11434/api/tags"
    echo -e "   2. Check model: ollama list"
    echo -e "   3. Pull model: ollama pull qwen2:7b"
    echo -e "   4. Run verbose: $0 $TEST_LEVEL true"
    echo ""

    exit 1
fi
