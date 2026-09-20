# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""SaaSGateway — SaaS 多后端沙箱网关 (SaaS 沙箱方案 §3.2)

职责:
1. 按 workspace 路由到具体 backend (CubeSandboxProvider / AgentENVProvider)
2. 共享配额 / WebSocket grace / pause / 敏感遮蔽策略
3. 统一 execute_command / execute_tool 接口

用法:
    provider = SandboxFacade.get_provider()  # 返回 SaaSGateway
    provider.execute_command(cmd, ctx)       # 自动路由
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from dawei.sandbox.agentenv_provider import AgentENVProvider
from dawei.sandbox.backend_selector import BackendSelector, select_backend
from dawei.sandbox.base import (
    BackendType,
    GlobalQuota,
    IsolationLevel,
    PausePolicy,
    ProviderType,
    ResourceQuota,
    SandboxCapabilities,
    SandboxProvider,
    SandboxResult,
    TrustedContext,
)
from dawei.sandbox.cubesandbox_provider import CubeSandboxProvider
from dawei.sandbox.pii_logger import PiiSafeLogger

logger = PiiSafeLogger(logging.getLogger(__name__))


@dataclass
class GatewayQuotaState:
    """网关共享配额状态 (跨 backend 计数)"""

    user_quota: ResourceQuota = field(default_factory=ResourceQuota)
    global_quota: GlobalQuota = field(default_factory=GlobalQuota)
    # 当前各 backend 的活跃会话数 (key: backend_type)
    active_by_backend: dict[str, int] = field(default_factory=dict)

    def increment(self, backend: str) -> None:
        self.active_by_backend[backend] = self.active_by_backend.get(backend, 0) + 1

    def decrement(self, backend: str) -> None:
        self.active_by_backend[backend] = max(0, self.active_by_backend.get(backend, 0) - 1)

    def total_active(self) -> int:
        return sum(self.active_by_backend.values())


class SaaSGateway(SandboxProvider):
    """SaaS 沙箱网关 — 按 workspace 路由到 backend

    配置 (env):
      DAWEI_SANDBOX_GATEWAY_ENABLED   默认 false (未启用时, 走原本的单 backend 路径)
      DAWEI_SANDBOX_BACKEND_BY_TENANT JSON 配置 (见 backend_selector.py)

    注: 当前 Phase 1c 实现是"轻量版", 配额只在网关层面做 user/global 级
    跨 backend 计数; 各 backend Provider 仍然保留自己的内部 quota (双层防护)。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

        # 子 Provider (按 backend 类型懒加载)
        self._cubesandbox: CubeSandboxProvider | None = None
        self._agentenv: AgentENVProvider | None = None

        # 网关级配额 (跨 backend 共享)
        self.gateway_quota = GatewayQuotaState(
            user_quota=ResourceQuota(
                max_concurrent_sandboxes=self.config.get("max_sessions_per_user", 20),
                max_total_memory_mb=self.config.get("max_memory_per_user_mb", 10240),
            ),
            global_quota=GlobalQuota(
                max_total_sandboxes=self.config.get("max_total_sessions", 5000),
                max_total_memory_mb=self.config.get("max_total_memory_mb", 512000),
            ),
        )

        # BackendSelector 单例
        self.selector = BackendSelector.instance()

    # ================================================================
    # 子 Provider 工厂
    # ================================================================

    def _get_cubesandbox(self) -> CubeSandboxProvider:
        if self._cubesandbox is None:
            self._cubesandbox = CubeSandboxProvider(self.config.get("cubesandbox", {}))
        return self._cubesandbox

    def _get_agentenv(self) -> AgentENVProvider:
        if self._agentenv is None:
            self._agentenv = AgentENVProvider(self.config.get("agentenv", {}))
        return self._agentenv

    def _provider_for(self, backend: BackendType) -> SandboxProvider:
        if backend == BackendType.AGENTENV:
            return self._get_agentenv()
        return self._get_cubesandbox()  # 默认 cubesandbox

    # ================================================================
    # SandboxProvider 接口
    # ================================================================

    def execute_command(self, command: str, ctx: TrustedContext, timeout: int | None = None) -> SandboxResult:
        # 1. 选择 backend
        meta = self.selector.select(ctx)
        provider = self._provider_for(meta.backend)

        # 2. 网关级配额检查 (粗粒度, 跨 backend 限额)
        self._check_gateway_quota(ctx, meta.backend)

        # 3. 委托给具体 backend（timeout 接口契约透传）
        # 计数更新 (注: 各子 Provider 内部已维护会话, 这里只做轻量统计)
        return provider.execute_command(command, ctx, timeout=timeout)

    async def execute_command_async(self, command: str, ctx: TrustedContext, timeout: int | None = None) -> SandboxResult:
        return await asyncio.to_thread(self.execute_command, command, ctx, timeout)

    def health_check(self) -> bool:
        """健康检查 — 任一 backend 可用即可"""
        results = []
        if self._cubesandbox:
            results.append(self._cubesandbox.health_check())
        if self._agentenv:
            results.append(self._agentenv.health_check())
        return any(results) if results else False

    def get_capabilities(self) -> SandboxCapabilities:
        """网关能力声明 = 各 backend 能力的并集"""
        return SandboxCapabilities(
            isolation_level=IsolationLevel.HARDWARE,
            supports_network=True,
            supports_filesystem=True,
            supports_resource_limits=True,
            supports_pause=True,
            max_timeout=300,
            cold_start_ms=50,  # 取最快 backend 的冷启动
        )

    # ================================================================
    # 会话生命周期 (透传给具体 backend)
    # ================================================================

    def prewarm_session(self, ctx: TrustedContext) -> None:
        meta = self.selector.select(ctx)
        self._provider_for(meta.backend).prewarm_session(ctx)

    def on_disconnect(self, ctx: TrustedContext) -> None:
        meta = self.selector.select(ctx)
        self._provider_for(meta.backend).on_disconnect(ctx)

    def on_reconnect(self, ctx: TrustedContext) -> None:
        meta = self.selector.select(ctx)
        self._provider_for(meta.backend).on_reconnect(ctx)

    def destroy_session(self, ctx: TrustedContext) -> None:
        # 尝试销毁所有 backend (因为 ctx 在哪里不确定)
        if self._cubesandbox:
            self._cubesandbox.destroy_session(ctx)
        if self._agentenv:
            self._agentenv.destroy_session(ctx)

    def destroy_all_sessions(self) -> None:
        if self._cubesandbox:
            self._cubesandbox.destroy_all_sessions()
        if self._agentenv:
            self._agentenv.destroy_all_sessions()
        self.gateway_quota.active_by_backend.clear()
        logger.info("[SAAS_GATEWAY] 所有 backend 会话已销毁")

    async def cleanup_idle(self) -> None:
        if self._cubesandbox:
            await self._cubesandbox.cleanup_idle()
        if self._agentenv:
            await self._agentenv.cleanup_idle()

    # ================================================================
    # 网关配额 (跨 backend 共享)
    # ================================================================

    def _check_gateway_quota(self, ctx: TrustedContext, backend: BackendType) -> None:
        """网关层粗粒度配额

        注: 子 Provider 内部仍有细粒度 per-user 配额,
        网关配额只防"全局过载"这种粗粒度问题。
        """
        from dawei.core.exceptions import QuotaExceededError

        # 用户级: 沙箱数 (跨 backend 累加)
        user_total = self._count_user_sessions(ctx.user_id)
        if user_total >= self.gateway_quota.user_quota.max_concurrent_sandboxes:
            raise QuotaExceededError(
                f"网关级用户沙箱上限: {user_total}/{self.gateway_quota.user_quota.max_concurrent_sandboxes}",
            )

        # 全局级
        total = self.gateway_quota.total_active()
        if total >= self.gateway_quota.global_quota.max_total_sandboxes:
            raise QuotaExceededError(
                f"网关级全局沙箱上限: {total}/{self.gateway_quota.global_quota.max_total_sandboxes}",
            )

    def _count_user_sessions(self, user_id: str) -> int:
        """统计用户在所有 backend 上的活跃会话数"""
        total = 0
        for prov in (self._cubesandbox, self._agentenv):
            if prov is None:
                continue
            # 依赖子 Provider 暴露的 _sessions (约定俗成)
            sessions = getattr(prov, "_sessions", {})
            for session in sessions.values():
                if getattr(session, "user_id", None) == user_id:
                    total += 1
        return total


# ================================================================
# 工厂辅助
# ================================================================


def is_saas_gateway_enabled() -> bool:
    """判断是否启用 SaaSGateway

    启用条件:
    - 环境变量 DAWEI_SANDBOX_GATEWAY_ENABLED=true
    - 或 DAWEI_SANDBOX_PROVIDER=saas
    """
    explicit = os.environ.get("DAWEI_SANDBOX_GATEWAY_ENABLED", "").lower() in ("1", "true", "yes")
    provider_env = os.environ.get("DAWEI_SANDBOX_PROVIDER", "").lower()
    return explicit or provider_env == ProviderType.SAAS.value


__all__ = ["SaaSGateway", "GatewayQuotaState", "is_saas_gateway_enabled"]
