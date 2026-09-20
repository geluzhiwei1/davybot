#!/bin/bash
# =============================================================================
# sandbox-precheck.sh — 沙箱启动后自检脚本 (§沙箱系统升级 v2 — §2.3)
#
# 写入 Cubelet 镜像, 沙箱启动后立即执行。
# 验证 tmpfs 遮蔽已生效, 任何检查失败立即退出 (fail-closed)。
#
# 安装位置 (CubeSandbox 模板内):
#   /opt/dawei/sandbox-precheck.sh
#
# 退出码:
#   0   PRECHECK_OK
#   100 tmpfs 未挂载到 /workspace/.dawei
#   101 .dawei 目录非空 (遮蔽失效)
#   102 关键文件泄露 (settings.json / workspace.json)
#   103 tmpfs 挂载类型不匹配
# =============================================================================
set -euo pipefail

DAWEI_DIR="/workspace/.dawei"

# ---- 1. tmpfs 必须挂载 ----
if ! mount 2>/dev/null | grep -q "tmpfs on ${DAWEI_DIR}"; then
    echo "FATAL: tmpfs 未挂载到 ${DAWEI_DIR}" >&2
    exit 100
fi

# ---- 2. 目录必须为空 (tmpfs 覆盖后应为空) ----
if [ -n "$(ls -A "${DAWEI_DIR}" 2>/dev/null)" ]; then
    echo "FATAL: ${DAWEI_DIR} 非空, tmpfs 遮蔽失效" >&2
    ls -la "${DAWEI_DIR}" >&2
    exit 101
fi

# ---- 3. 关键文件必须不存在 ----
for f in settings.json workspace.json chat-history sessions; do
    if [ -e "${DAWEI_DIR}/${f}" ]; then
        echo "FATAL: 关键文件泄露: ${f}" >&2
        exit 102
    fi
done

# ---- 4. 验证挂载类型确实是 tmpfs ----
FS_TYPE=$(df -T "${DAWEI_DIR}" 2>/dev/null | awk 'NR==2 {print $2}')
if [[ -n "${FS_TYPE}" && "${FS_TYPE}" != "tmpfs" ]]; then
    echo "FATAL: ${DAWEI_DIR} 挂载类型为 ${FS_TYPE}, 期望 tmpfs" >&2
    exit 103
fi

echo "PRECHECK_OK"
