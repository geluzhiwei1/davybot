#!/usr/bin/env bash
# Build the dawei server binary (PyInstaller single-file) for the current platform.
#
# Canonical name: build-server-binary.sh (renamed 2026-09-15 from build-sidecar.sh;
# "sidecar" was Tauri-desktop terminology — the same binary serves BOTH the SaaS
# demo/prod deployment on :8431 and the Tauri desktop app as its sidecar process.
# The old name remains as a thin wrapper for compatibility.)
#
# Uses build-binary.py (--collect-all dawei) — NEVER use raw `pyinstaller dawei.spec`
# (hand-written spec has hiddenimports=[] → tool modules missing → tools:[] at runtime).
#
# Usage: bash project/scripts/build-server-binary.sh [--clean] [--no-upx]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"            # davybot/ (单仓: engine/ + app/ + scripts/)
AGENT_DIR="$REPO_ROOT/engine/agent"

if [[ ! -d "$AGENT_DIR" ]]; then
  echo "ERROR: agent dir not found: $AGENT_DIR" >&2
  exit 1
fi

# Same invocation as build-desktop.sh / mac-build-and-sign.sh / build-desktop.ps1:
# uv run resolves the project env from uv.lock and injects pyinstaller, so the
# server binary is built from the SAME dependency set as the desktop one.
# (Previously this used .venv/bin/python directly, which could drift from the
# lockfile or lack pyinstaller entirely.)
command -v uv >/dev/null 2>&1 || {
  echo "ERROR: uv not found (install: https://docs.astral.sh/uv)" >&2
  exit 1
}

# ---- Runtime-mode stamp + env consistency (多模式统一方案 §L1 产物盖戳) ----
# DAWEI_RUNTIME_STAMP: 逗号分隔的允许运行模式, 构建时写入 dawei/_mode_;
# boot 时 runtime.validate_environment() 比对, 不符拒启。
# 本脚本默认【不盖戳】: 它是多用途入口 (server 部署 / saas scp 经 build-saas.sh /
# desktop 兜底, 见 build-desktop.sh copy_sidecar 提示)。明确目标的调用方自行收窄:
#   build-saas.sh → DAWEI_RUNTIME_STAMP=saas
check_runtime_mode_env() {
  # $1 env 文件, $2 期望模式 — 声明不符 → FAST FAIL
  local f="$1" want="$2" got
  [[ -f "$f" ]] || return 0
  got="$(grep -E '^[[:space:]]*DAWEI_RUNTIME_MODE[[:space:]]*=' "$f" | tail -1 | cut -d= -f2- || true)"
  if [[ -z "$got" ]]; then
    echo "    WARN: $f 未声明 DAWEI_RUNTIME_MODE (建议补, 见 .env.server.*.example)"
    return 0
  fi
  got="${got%%#*}"
  got="${got//\"/}"
  got="${got//\'/}"
  got="$(echo "$got" | tr -d '[:space:]')"
  if [[ "$got" != "$want" ]]; then
    echo "ERROR: $f 声明 DAWEI_RUNTIME_MODE=$got, 与目标模式 '$want' 不符 (多模式统一方案 §L1)" >&2
    exit 1
  fi
  echo "    OK: $f DAWEI_RUNTIME_MODE=$got"
}

for _f in .env.server .env.server.dev .env.server.prod; do
  check_runtime_mode_env "$AGENT_DIR/$_f" server
done

STAMP_ARGS=()
if [[ -n "${DAWEI_RUNTIME_STAMP:-}" ]]; then
  STAMP_ARGS=(--runtime-mode "$DAWEI_RUNTIME_STAMP")
  echo "==> Mode stamp: ${DAWEI_RUNTIME_STAMP}"
fi

# ---- Biz backend inclusion (拆库方案 §18 S8 缝) ----
# DAWEI_BIZ_PKG: davybot-biz 项目目录 (engine/biz)。设置后 uv run 以 --with 注入
# 临时构建层 (wheel 化安装, 非 editable — 冻结干净), build-binary.py 检测到
# dawei_biz 即 --collect-all dawei_biz + --copy-metadata davybot-biz (注册缝
# entry points 冻结可见)。未设 = 核心纯净构建 (desktop/server, 业务不在场 = 不存在)。
# 调用方: davy-ops build-saas.sh (saas) / 闭源 enterprise workflow (enterprise desktop)。
BIZ_WITH_ARGS=()
if [[ -n "${DAWEI_BIZ_PKG:-}" ]]; then
  if [[ ! -d "$DAWEI_BIZ_PKG" ]]; then
    echo "ERROR: DAWEI_BIZ_PKG set but not a dir: $DAWEI_BIZ_PKG" >&2
    exit 1
  fi
  BIZ_WITH_ARGS=(--with "$DAWEI_BIZ_PKG")
  echo "==> Biz backend: $DAWEI_BIZ_PKG (davybot-biz, frozen into bundle)"
fi

echo "==> Building dawei server binary via build-binary.py"
echo "    Agent dir: $AGENT_DIR"

cd "$AGENT_DIR"
# --with e2b --with boto3 --with cryptography: saas 部署所需 ([sandbox]/[workspace-store]
# extras; CubeSandbox SDK + WorkspaceStore S3)。build-binary.py find_spec 守卫按需
# collect; desktop 走 build-desktop.sh 自有入口, 不经本脚本。(2026-09-22 demo 两事故
# 的修复对齐 —— 见 project/scripts/build-server-binary.sh 同段注释。)
uv run --python 3.12 --with pyinstaller "${BIZ_WITH_ARGS[@]}" \
  --with e2b --with boto3 --with cryptography \
  python scripts/build-binary.py "${STAMP_ARGS[@]}" "$@"

# Show result
BIN="dist/dawei"
[[ -f "$BIN.exe" ]] && BIN="dist/dawei.exe"
echo "==> Server binary built: $BIN ($(du -h "$BIN" | cut -f1))"
