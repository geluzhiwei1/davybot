# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""运行模式统一出口 (多模式统一方案 §L3)

**唯一合法的 mode 读取点**: 引擎其他模块禁止绕过本模块读
DAWEI_RUNTIME_MODE 或嗅探配置推断模式 (硬规则, 见
project/docs/多模式统一方案.md §6)。

变量关系::

    DAWEI_RUNTIME_MODE    = saas | desktop | server | tui   (唯一上游)
    DAWEI_DEPLOYMENT_MODE = local | saas   (兼容输入, 仅当上游未设时使用)

派生::

    deployment_class = "saas" if mode == "saas" else "local"
    capabilities     = 按 mode + 配置声明的能力 (能力判定即配置判定)

冲突规则: 两个变量都设且矛盾 → validate_environment() 在 boot 时
fail-fast (RuntimeError)。

产物盖戳 (多模式统一方案 §L1/§4-3):
    构建脚本 (build-desktop.sh / build-saas.sh / ...) 调 build-binary.py
    --runtime-mode 时, 在包内写入 ``_mode_`` 清单 (允许的运行模式集合,
    逗号分隔; PyInstaller --collect-all dawei 自动入包)。
    validate_environment() boot 时比对运行环境 mode 与盖戳, 不符拒启 —
    防 saas 产物被降级当 local/server 跑 (隔离守卫被绕过)。
    缺戳 = 不限制 (源码开发运行、未指定 --runtime-mode 的构建)。
"""

from __future__ import annotations

import os
from pathlib import Path

RUNTIME_MODES = ("saas", "desktop", "server", "tui")

# 兼容输入 → 上游模式的映射 (DAWEI_DEPLOYMENT_MODE)
_LEGACY_TO_MODE = {"saas": "saas", "local": "desktop"}

# 沙箱能力归属的模式 (server/tui 无沙箱 — 多模式统一方案 §3)
SANDBOX_MODES = ("saas", "desktop")

# 账号体系能力归属的模式 (server/tui 自包含无账号 — server 自包含方案)
AUTH_MODES = ("saas", "desktop")


def runtime_mode() -> str:
    """解析当前运行模式 (saas | desktop | server | tui)。

    - DAWEI_RUNTIME_MODE 优先, 非法值直接抛 ValueError (FAST FAIL);
    - 未设时回退 DAWEI_DEPLOYMENT_MODE (saas→saas, local/非法→desktop);
    - 都未设 → desktop (单机默认)。
    """
    rt = os.environ.get("DAWEI_RUNTIME_MODE", "").strip().lower()
    if rt:
        if rt not in RUNTIME_MODES:
            raise ValueError(
                f"DAWEI_RUNTIME_MODE 非法: {rt!r} (合法值: {'|'.join(RUNTIME_MODES)})"
            )
        return rt

    legacy = os.environ.get("DAWEI_DEPLOYMENT_MODE", "").strip().lower()
    return _LEGACY_TO_MODE.get(legacy, "desktop")


def deployment_class() -> str:
    """部署隔离等级: "saas" (多租户) | "local" (单机)。

    现有守卫 (_guard_saas_isolation 等) 依据此值, 语义不变。
    """
    return "saas" if runtime_mode() == "saas" else "local"


def get_capabilities() -> list[str]:
    """声明当前运行期能力 (能力判定即配置判定)。

    - auth:              saas/desktop (账号体系; server/tui 自包含, 固定本地身份)
    - sandbox:           saas/desktop (server/tui 无沙箱)
    - local-mcp:         desktop (本机私有 MCP, 需 Tauri 壳)
    - market:            saas/desktop 恒有; server 仅在显式配置 MARKET_API_URL 时
                         (自包含默认不连市场)
    - relay:             有 UI 的模式 (设备/会话管理端点在引擎内)
    - workspace-store-s3: WORKSPACE_STORE_BACKEND ∈ {rustfs, minio, s3}
    """
    mode = runtime_mode()
    caps: list[str] = []

    if mode in AUTH_MODES:
        caps.append("auth")
    if mode in SANDBOX_MODES:
        caps.append("sandbox")
    if mode == "desktop":
        caps.append("local-mcp")
    if mode in ("saas", "desktop", "server"):
        caps.append("relay")
        # server 自包含: market 配置判定 (显式设了 MARKET_API_URL 才算接入市场)
        if mode != "server" or os.environ.get("MARKET_API_URL", "").strip():
            caps.append("market")

    backend = os.environ.get("WORKSPACE_STORE_BACKEND", "local").strip().lower()
    if backend in ("rustfs", "minio", "s3"):
        caps.append("workspace-store-s3")

    return caps


# 盖戳清单文件: 构建时写入 dawei 包内 (onefile 解压后位于 sys._MEIPASS)
MODE_STAMP_FILENAME = "_mode_"


def read_mode_stamp(path: Path | None = None) -> list[str] | None:
    """读取产物盖戳 (dawei/_mode_, 允许的运行模式集合)。

    - 源码开发运行 / 未盖戳的构建 → 文件不存在 → None (不限制);
    - 内容为逗号分隔的模式列表, 忽略空白与 # 注释行;
    - 空清单视为无戳 (容错, 不因空文件拒启所有模式)。
    """
    stamp_path = path or Path(__file__).resolve().parent / MODE_STAMP_FILENAME
    try:
        text = stamp_path.read_text(encoding="utf-8")
    except OSError:
        return None

    modes: list[str] = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        for item in line.split(","):
            item = item.strip()
            if item:
                modes.append(item)
    return modes or None


def validate_environment() -> dict:
    """boot 时一致性校验 (FAST FAIL)。

    1. 两个模式变量都设且矛盾 → RuntimeError, 拒绝启动;
    2. 产物盖戳存在且运行模式不在允许集合内 → RuntimeError, 拒绝启动
       (防 saas 产物被当 local/server 跑, 隔离守卫被绕过)。
    返回 runtime info 供调用方记录日志。
    """
    rt = os.environ.get("DAWEI_RUNTIME_MODE", "").strip().lower()
    legacy = os.environ.get("DAWEI_DEPLOYMENT_MODE", "").strip().lower()

    if rt and legacy:
        # legacy 非法值历史行为按 local 处理 (provider_factory 旧行为)
        legacy_class = legacy if legacy in ("local", "saas") else "local"
        if deployment_class() != legacy_class:
            raise RuntimeError(
                f"模式变量矛盾: DAWEI_RUNTIME_MODE={rt} 与 "
                f"DAWEI_DEPLOYMENT_MODE={legacy} 不一致。"
                f"请只设 DAWEI_RUNTIME_MODE (saas|desktop|server|tui), "
                "DAWEI_DEPLOYMENT_MODE 仅为兼容保留。"
            )

    stamp = read_mode_stamp()
    if stamp is not None:
        mode = runtime_mode()
        if mode not in stamp:
            raise RuntimeError(
                f"运行模式 ({mode}) 与构建盖戳 ({','.join(stamp)}) 不符 — "
                "该产物不允许以当前模式启动 (多模式统一方案 §L1 产物盖戳)。"
                "请核对部署用的 env 文件 DAWEI_RUNTIME_MODE 与构建目标模式。"
            )

    return get_runtime_info()


def get_runtime_info() -> dict:
    """GET /api/runtime-info 的数据源 (mode + deployment_class + capabilities)。"""
    return {
        "mode": runtime_mode(),
        "deployment_class": deployment_class(),
        "capabilities": get_capabilities(),
    }
