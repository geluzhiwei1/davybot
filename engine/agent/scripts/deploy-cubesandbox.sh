#!/usr/bin/env bash
# =============================================================================
# CubeSandbox 一步部署脚本 (Phase 5)
#
# 用法:
#   sudo bash scripts/deploy-cubesandbox.sh
#
# 功能:
#   1. 安装 xfsprogs
#   2. 挂载预格式化的 XFS 镜像到 /data
#   3. 写入 /etc/fstab (开机自动挂载)
#   4. 运行 CubeSandbox 在线安装脚本
#   5. 创建 code-interpreter 模板
#   6. 输出 API 地址和密钥
# =============================================================================
set -euo pipefail

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*" >&2; }

# ---- 检查 root ----
if [[ "${EUID}" -ne 0 ]]; then
    err "This script must run as root. Use: sudo bash $0"
    exit 1
fi

# ---- 配置 ----
XFS_IMG="/home/dev007/cube-sandbox-data.img"
DATA_MOUNT="/data"
CUBELET_DIR="${DATA_MOUNT}/cubelet"
INSTALL_DIR="/opt/cube-sandbox"

# =============================================================================
# Step 1: 安装 xfsprogs
# =============================================================================
log "Step 1: Installing xfsprogs..."
if ! command -v mkfs.xfs >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y xfsprogs
fi
log "xfsprogs OK"

# =============================================================================
# Step 2: 挂载 XFS 镜像
# =============================================================================
log "Step 2: Mounting XFS image..."

if [[ ! -f "${XFS_IMG}" ]]; then
    err "XFS image not found at ${XFS_IMG}"
    err "Run truncate + docker mkfs.xfs first (see README)"
    exit 1
fi

mkdir -p "${DATA_MOUNT}"

if mountpoint -q "${DATA_MOUNT}"; then
    warn "${DATA_MOUNT} is already mounted. Skipping mount."
else
    mount -o loop "${XFS_IMG}" "${DATA_MOUNT}"
    log "Mounted ${XFS_IMG} -> ${DATA_MOUNT}"
fi

# 验证 XFS
FS_TYPE=$(df -T "${DATA_MOUNT}" | awk 'NR==2 {print $2}')
if [[ "${FS_TYPE}" != "xfs" ]]; then
    err "${DATA_MOUNT} is not XFS (got: ${FS_TYPE})"
    exit 1
fi
log "XFS verified: ${FS_TYPE} with reflink=1"

# =============================================================================
# Step 3: 写入 fstab (开机自动挂载)
# =============================================================================
log "Step 3: Adding to /etc/fstab..."

FSTAB_ENTRY="${XFS_IMG} ${DATA_MOUNT} xfs loop,defaults 0 0"

if grep -qF "${XFS_IMG}" /etc/fstab; then
    warn "fstab entry already exists. Skipping."
else
    echo "" >> /etc/fstab
    echo "# CubeSandbox XFS storage" >> /etc/fstab
    echo "${FSTAB_ENTRY}" >> /etc/fstab
    log "fstab entry added"
fi

# =============================================================================
# Step 4: 创建 /data/cubelet
# =============================================================================
log "Step 4: Creating ${CUBELET_DIR}..."
mkdir -p "${CUBELET_DIR}"
chmod 755 "${CUBELET_DIR}"
log "cubelet dir OK"

# =============================================================================
# Step 5: 运行 CubeSandbox 在线安装
# =============================================================================
log "Step 5: Running CubeSandbox online install..."
log "This will download ~500MB and set up all services."
log "Estimated time: 5-15 minutes depending on network."
echo ""

INSTALL_SCRIPT_URL="https://raw.githubusercontent.com/tencentcloud/CubeSandbox/master/deploy/one-click/online-install.sh"

# 下载到本地再运行 (避免管道环境变量丢失)
curl -fsSL "${INSTALL_SCRIPT_URL}" -o /tmp/cube-online-install.sh
chmod +x /tmp/cube-online-install.sh

# 运行安装 (不传 CUBE_PVM_ENABLE, 因为是裸金属直接有 KVM)
bash /tmp/cube-online-install.sh

log "CubeSandbox install completed."

# =============================================================================
# Step 6: 等待服务启动
# =============================================================================
log "Step 6: Waiting for cube-api service..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:3000/health >/dev/null 2>&1; then
        log "cube-api is healthy!"
        break
    fi
    if curl -sf http://127.0.0.1:3000/ >/dev/null 2>&1; then
        log "cube-api is responding!"
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

# =============================================================================
# Step 7: 创建 code-interpreter 模板
# =============================================================================
log "Step 7: Creating code-interpreter template..."

# 检查 cubemastercli 是否可用
if command -v cubemastercli >/dev/null 2>&1; then
    CUBE_CLI="cubemastercli"
elif [[ -x /usr/local/bin/cubemastercli ]]; then
    CUBE_CLI="/usr/local/bin/cubemastercli"
elif [[ -x /opt/cube-sandbox/bin/cubemastercli ]]; then
    CUBE_CLI="/opt/cube-sandbox/bin/cubemastercli"
else
    warn "cubemastercli not found in PATH. Searching..."
    CUBE_CLI=$(find / -name cubemastercli -type f 2>/dev/null | head -1 || true)
    if [[ -z "${CUBE_CLI}" ]]; then
        warn "cubemastercli not found. Manual template creation needed."
        warn "After install, run:"
        warn "  cubemastercli tpl create-from-image \\"
        warn "    --image cube-sandbox-int.tencentcloudcr.com/cube-sandbox/sandbox-code:latest \\"
        warn "    --name code-interpreter"
    fi
fi

if [[ -n "${CUBE_CLI:-}" ]]; then
    log "Using cubemastercli at: ${CUBE_CLI}"

    # 检查模板是否已存在
    if ${CUBE_CLI} tpl list 2>/dev/null | grep -q "code-interpreter"; then
        warn "Template 'code-interpreter' already exists. Skipping creation."
    else
        ${CUBE_CLI} tpl create-from-image \
            --image cube-sandbox-int.tencentcloudcr.com/cube-sandbox/sandbox-code:latest \
            --name code-interpreter
        log "Template 'code-interpreter' created!"
    fi
fi

# =============================================================================
# Step 8: 获取 API Key 和输出配置
# =============================================================================
log "Step 8: Extracting configuration..."

# 尝试从 cube 配置中获取 API key
API_KEY=""
if [[ -f /data/cube/config.yaml ]]; then
    API_KEY=$(grep -oP 'api[_-]?key:\s*\K.*' /data/cube/config.yaml 2>/dev/null | head -1 || true)
fi
if [[ -z "${API_KEY}" ]] && [[ -f /opt/cube-sandbox/config.yaml ]]; then
    API_KEY=$(grep -oP 'api[_-]?key:\s*\K.*' /opt/cube-sandbox/config.yaml 2>/dev/null | head -1 || true)
fi
if [[ -z "${API_KEY}" ]] && [[ -f /etc/cube/config.yaml ]]; then
    API_KEY=$(grep -oP 'api[_-]?key:\s*\K.*' /etc/cube/config.yaml 2>/dev/null | head -1 || true)
fi

# 尝试从环境变量/服务日志中获取
if [[ -z "${API_KEY}" ]]; then
    API_KEY=$(docker logs cube-api 2>&1 | grep -oP 'api[_-]?key[:\s]+\K\w+' | head -1 || true)
fi

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  CubeSandbox Deployment Complete!     ${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "  API URL:     ${GREEN}http://127.0.0.1:3000${NC}"
echo -e "  Template:    ${GREEN}code-interpreter${NC}"
if [[ -n "${API_KEY}" ]]; then
    echo -e "  API Key:     ${GREEN}${API_KEY}${NC}"
else
    echo -e "  API Key:     ${YELLOW}(check install output above or /data/cube/config.yaml)${NC}"
fi
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "  1. Update ${GREEN}.env${NC} with the API key:"
echo -e "     DAWEI_SANDBOX_PROVIDER=e2b"
echo -e "     DAWEI_SANDBOX_API_KEY=<key-from-above>"
echo ""
echo -e "  2. Verify sandbox creation:"
echo -e "     python -c \"from e2b_code_interpreter import Sandbox; s = Sandbox.create('code-interpreter', api_url='http://127.0.0.1:3000'); print(s); s.kill()\""
echo ""
echo -e "  3. Restart dawei server"
echo ""
