#!/bin/bash
set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPS_DRAWIO="$PROJECT_ROOT/../deps/drawio"
PUBLIC_DRAWIO="$PROJECT_ROOT/public/drawio"
DRAWIO_REPO="https://github.com/geluzhiwei1/drawio.git"

echo -e "${YELLOW}正在检查 drawio 资源...${NC}"

# 步骤 1: 检查 public/drawio 是否存在
if [ -d "$PUBLIC_DRAWIO" ]; then
    echo -e "${GREEN}✓ webui/public/drawio 已存在${NC}"
    exit 0
fi

echo -e "${YELLOW}webui/public/drawio 不存在，正在准备...${NC}"

# 步骤 2: 检查 deps/drawio 是否存在
if [ -d "$DEPS_DRAWIO" ]; then
    echo -e "${GREEN}✓ 从 deps/drawio 复制...${NC}"
    cp -r "$DEPS_DRAWIO/src/main/webapp/." "$PUBLIC_DRAWIO/"
    echo -e "${GREEN}✓ drawio 资源准备完成${NC}"
    exit 0
fi

# 步骤 3: deps/drawio 也不存在，需要 clone
echo -e "${YELLOW}deps/drawio 不存在，正在从 GitHub clone...${NC}"
mkdir -p "$(dirname "$DEPS_DRAWIO")"

if git clone "$DRAWIO_REPO" "$DEPS_DRAWIO"; then
    echo -e "${GREEN}✓ drawio clone 成功${NC}"
    echo -e "${GREEN}✓ 从 deps/drawio 复制...${NC}"
    cp -r "$DEPS_DRAWIO/src/main/webapp/." "$PUBLIC_DRAWIO/"
    echo -e "${GREEN}✓ drawio 资源准备完成${NC}"
    exit 0
else
    echo -e "${RED}✗ clone drawio 失败${NC}"
    echo -e "${RED}请手动执行以下命令：${NC}"
    echo -e "${RED}  cd davybot/deps${NC}"
    echo -e "${RED}  git clone https://github.com/geluzhiwei1/drawio.git${NC}"
    exit 1
fi
