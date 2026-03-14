#!/bin/bash
set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPS_ONLYOFFICE="$PROJECT_ROOT/../deps/onlyoffice-web-local"
PUBLIC_ONLYOFFICE="$PROJECT_ROOT/public/onlyoffice"
ONLYOFFICE_REPO="https://github.com/geluzhiwei1/onlyoffice-web-local.git"

echo -e "${YELLOW}正在检查 OnlyOffice 资源...${NC}"

# 步骤 1: 检查 public/onlyoffice 是否存在
if [ -d "$PUBLIC_ONLYOFFICE" ]; then
    echo -e "${GREEN}✓ webui/public/onlyoffice 已存在${NC}"
    exit 0
fi

echo -e "${YELLOW}webui/public/onlyoffice 不存在，正在准备...${NC}"

# 步骤 2: 检查 deps/onlyoffice-web-local/html 是否存在（已构建）
if [ -d "$DEPS_ONLYOFFICE/html" ]; then
    echo -e "${GREEN}✓ 从 deps/onlyoffice-web-local/html 复制...${NC}"
    cp -r "$DEPS_ONLYOFFICE/html/." "$PUBLIC_ONLYOFFICE/"
    echo -e "${GREEN}✓ OnlyOffice 资源准备完成${NC}"
    exit 0
fi

# 步骤 3: deps/onlyoffice-web-local 存在但未构建，需要先构建
if [ -d "$DEPS_ONLYOFFICE" ]; then
    echo -e "${YELLOW}deps/onlyoffice-web-local 存在但未构建，正在构建...${NC}"
    cd "$DEPS_ONLYOFFICE"

    # 检查 pnpm 是否安装
    if ! command -v pnpm &> /dev/null; then
        echo -e "${RED}✗ pnpm 未安装，请先安装 pnpm${NC}"
        echo -e "${RED}npm install -g pnpm${NC}"
        exit 1
    fi

    # 安装依赖并构建
    echo -e "${YELLOW}正在安装 pnpm 依赖...${NC}"
    if pnpm install; then
        echo -e "${GREEN}✓ pnpm install 成功${NC}"
    else
        echo -e "${RED}✗ pnpm install 失败${NC}"
        exit 1
    fi

    echo -e "${YELLOW}正在构建 OnlyOffice...${NC}"
    if pnpm build; then
        echo -e "${GREEN}✓ OnlyOffice 构建成功${NC}"
    else
        echo -e "${RED}✗ OnlyOffice 构建失败${NC}"
        exit 1
    fi

    # 复制构建产物
    echo -e "${GREEN}✓ 从 deps/onlyoffice-web-local/html 复制...${NC}"
    cp -r "$DEPS_ONLYOFFICE/html/." "$PUBLIC_ONLYOFFICE/"
    echo -e "${GREEN}✓ OnlyOffice 资源准备完成${NC}"
    exit 0
fi

# 步骤 4: deps/onlyoffice-web-local 也不存在，需要 clone
echo -e "${YELLOW}deps/onlyoffice-web-local 不存在，正在从 GitHub clone...${NC}"
mkdir -p "$(dirname "$DEPS_ONLYOFFICE")"

if git clone "$ONLYOFFICE_REPO" "$DEPS_ONLYOFFICE"; then
    echo -e "${GREEN}✓ OnlyOffice clone 成功${NC}"

    # 检查 pnpm 是否安装
    if ! command -v pnpm &> /dev/null; then
        echo -e "${RED}✗ pnpm 未安装，请先安装 pnpm${NC}"
        echo -e "${RED}npm install -g pnpm${NC}"
        exit 1
    fi

    # 安装依赖并构建
    cd "$DEPS_ONLYOFFICE"
    echo -e "${YELLOW}正在安装 pnpm 依赖...${NC}"
    if pnpm install; then
        echo -e "${GREEN}✓ pnpm install 成功${NC}"
    else
        echo -e "${RED}✗ pnpm install 失败${NC}"
        exit 1
    fi

    echo -e "${YELLOW}正在构建 OnlyOffice...${NC}"
    if pnpm build; then
        echo -e "${GREEN}✓ OnlyOffice 构建成功${NC}"
    else
        echo -e "${RED}✗ OnlyOffice 构建失败${NC}"
        exit 1
    fi

    # 复制构建产物
    echo -e "${GREEN}✓ 从 deps/onlyoffice-web-local/html 复制...${NC}"
    cp -r "$DEPS_ONLYOFFICE/html/." "$PUBLIC_ONLYOFFICE/"
    echo -e "${GREEN}✓ OnlyOffice 资源准备完成${NC}"
    exit 0
else
    echo -e "${RED}✗ clone OnlyOffice 失败${NC}"
    echo -e "${RED}请手动执行以下命令：${NC}"
    echo -e "${RED}  cd davybot/deps${NC}"
    echo -e "${RED}  git clone https://github.com/geluzhiwei1/onlyoffice-web-local.git${NC}"
    exit 1
fi
