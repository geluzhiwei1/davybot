# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""云沙箱 provider 装载器（拆库方案 §18.3-S4，阶段六 6b）。

核心 provider_factory 只内置本地形态（docker/subprocess/lightweight/
workspace-store）；云 provider（e2b/cubesandbox/agentenv/saas_gateway/
backend_selector 等 ×7）随 davybot-biz 经 entry point group
``dawei.sandbox_providers`` 提供：

- biz 缺席 → ImportError（由调用方转为 SandboxError，FAST FAIL 不降级）；
- biz 在场但模块损坏 → ep.load() 异常原样上抛（不允许半 boot）。

用法::

    from dawei.sandbox.saas_loader import load_saas_module

    CubeSandboxProvider = load_saas_module("cubesandbox").CubeSandboxProvider
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from types import ModuleType

logger = logging.getLogger(__name__)

_GROUP = "dawei.sandbox_providers"


def load_saas_module(name: str) -> ModuleType:
    """按 entry point 名装载云沙箱模块；缺席/损坏均显式失败。"""
    for ep in entry_points(group=_GROUP):
        if ep.name == name:
            return ep.load()  # 损坏 = 异常上抛（FAST FAIL）
    raise ImportError(
        f"云沙箱 provider '{name}' 不可用 — 未安装 davybot-biz "
        f"（开源核心形态仅支持本地 docker/subprocess 沙箱）"
    )


def available_saas_providers() -> list[str]:
    """列出当前环境中可用的云 provider entry 名（诊断用）。"""
    return sorted(ep.name for ep in entry_points(group=_GROUP))


__all__ = ["available_saas_providers", "load_saas_module"]
