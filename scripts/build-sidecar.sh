#!/usr/bin/env bash
# DEPRECATED (2026-09-15): renamed to build-server-binary.sh.
# "sidecar" 是 Tauri 桌面端术语；同一二进制既作 demo/prod 服务端（:8431），
# 也作桌面 app 的 sidecar 进程。规范名 → build-server-binary.sh。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/build-server-binary.sh" "$@"

