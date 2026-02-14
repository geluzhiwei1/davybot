#!/bin/bash
set -e

echo "🚀 Starting E2E Test Automation..."

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo -e "${BLUE}📂 Working directory: ${ROOT_DIR}${NC}"

# 1. 检查依赖
echo -e "${YELLOW}📦 Checking dependencies...${NC}"

if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js not found. Please install Node.js 20+${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Node.js: $(node --version)${NC}"

if ! command -v pnpm &> /dev/null; then
    echo -e "${RED}❌ pnpm not found. Install with: npm install -g pnpm${NC}"
    exit 1
fi
echo -e "${GREEN}✅ pnpm: $(pnpm --version)${NC}"

# 2. 进入前端目录
cd webui

# 3. 安装依赖
echo -e "${YELLOW}📥 Installing dependencies...${NC}"
pnpm install --frozen-lockfile

# 4. 检查Playwright
if ! npx playwright --version &> /dev/null; then
    echo -e "${YELLOW}📦 Installing Playwright...${NC}"
    pnpm add -D @playwright/test
fi

# 5. 安装Playwright浏览器
echo -e "${YELLOW}🌐 Installing Playwright browsers...${NC}"
pnpm exec playwright install --with-deps chromium

# 6. 检查后端服务
echo -e "${YELLOW}🔍 Checking backend service...${NC}"
BACKEND_RUNNING=false

if curl -s http://localhost:8465/docs > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend is already running${NC}"
    BACKEND_RUNNING=true
else
    echo -e "${YELLOW}⚠️  Backend not running, starting...${NC}"

    # 检查后端目录
    if [ ! -d "../../agent" ]; then
        echo -e "${RED}❌ Backend directory not found${NC}"
        exit 1
    fi

    cd ../../agent

    # 检查uv
    if ! command -v uv &> /dev/null; then
        echo -e "${RED}❌ uv not found. Install from: https://astral.sh/uv${NC}"
        exit 1
    fi

    # 安装后端依赖
    echo -e "${YELLOW}📦 Installing backend dependencies...${NC}"
    uv pip install -e . --quiet

    # 后台启动后端
    echo -e "${YELLOW}🚀 Starting backend server...${NC}"
    nohup uv run python -m dawei.server > /tmp/dawei-backend.log 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > /tmp/dawei-backend.pid

    # 等待后端启动
    echo -e "${YELLOW}⏳ Waiting for backend to start...${NC}"
    for i in {1..60}; do
        if curl -s http://localhost:8465/docs > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Backend started (PID: ${BACKEND_PID})${NC}"
            break
        fi
        if [ $i -eq 60 ]; then
            echo -e "${RED}❌ Backend failed to start${NC}"
            cat /tmp/dawei-backend.log
            exit 1
        fi
        sleep 1
    done

    cd ../webui
fi

# 7. 运行E2E测试
echo -e "${YELLOW}🧪 Running E2E tests...${NC}"
TEST_FAILED=false

if pnpm test:e2e; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
else
    echo -e "${RED}❌ Some tests failed!${NC}"
    TEST_FAILED=true
fi

# 8. 清理
echo -e "${YELLOW}🧹 Cleaning up...${NC}"

if [ "$BACKEND_RUNNING" = false ] && [ -f /tmp/dawei-backend.pid ]; then
    BACKEND_PID=$(cat /tmp/dawei-backend.pid)
    echo -e "${YELLOW}🛑 Stopping backend (PID: ${BACKEND_PID})...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    rm /tmp/dawei-backend.pid
fi

# 9. 结果报告
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${BLUE}           E2E TEST RESULTS                   ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo ""

if [ "$TEST_FAILED" = true ]; then
    echo -e "${RED}❌ Tests FAILED!${NC}"
    echo ""
    echo -e "${YELLOW}📊 View detailed report:${NC}"
    echo -e "   cd webui && pnpm test:e2e:report"
    echo ""
    echo -e "${YELLOW}📸 View screenshots:${NC}"
    echo -e "   ls -la webui/test-results/"
    echo ""
    exit 1
else
    echo -e "${GREEN}✅ All tests PASSED!${NC}"
    echo ""
    echo -e "${YELLOW}📊 View test report:${NC}"
    echo -e "   cd webui && pnpm test:e2e:report"
    echo ""
    exit 0
fi
