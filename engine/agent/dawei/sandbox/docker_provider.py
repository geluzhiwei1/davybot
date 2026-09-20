# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""DockerProvider — 容器级沙箱 Provider (§沙箱系统升级 v2 — Phase 1)

基于现有 sandbox_manager.py 的 SandboxManager, 实现 SandboxProvider ABC。
- Docker/Podman 容器隔离
- 资源限制: CPU、内存、PID、网络、超时
- 隔离级别: CONTAINER
- 支持 ro/rw 挂载模式 + N3 命令读写分类

向后兼容: 保留 SandboxManager 作为别名, 不破坏现有调用方。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dawei.sandbox.base import (
    IsolationLevel,
    SandboxCapabilities,
    SandboxProvider,
    SandboxResult,
    TrustedContext,
)
from dawei.sandbox.command_classifier import CommandRisk, classify_command
from dawei.sandbox.pii_logger import PiiSafeLogger

logger = PiiSafeLogger(logging.getLogger(__name__))


class DockerProvider(SandboxProvider):
    """Docker/Podman 容器沙箱 Provider

    隔离级别: CONTAINER (容器级, 共享主机内核)
    适用场景: 本地增强隔离 / SaaS 模式容器隔离

    注意: 此 Provider 需要 docker-py 依赖。
    若 Docker/Podman 不可用, provider_factory 会降级到 SubprocessProvider。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        # 延迟导入: 避免 docker-py 未安装时整个模块无法加载
        self._manager: Any = None

    # ================================================================
    # 懒加载 SandboxManager
    # ================================================================

    @property
    def manager(self):
        """懒加载 SandboxManager 实例"""
        if self._manager is None:
            from dawei.sandbox.sandbox_manager import SandboxConfig, SandboxManager

            sandbox_config = SandboxConfig(
                image=self.config.get("image", "alpine:latest"),
                memory_limit=self.config.get("memory_limit", "512m"),
                cpu_quota=self.config.get("cpu_quota", 100000),
                timeout=self.config.get("timeout", 30),
                workspace_mount_mode=self.config.get("workspace_mount_mode", "ro"),
                container_runtime=self.config.get("container_runtime", "auto"),
            )
            self._manager = SandboxManager(sandbox_config)
        return self._manager

    # ================================================================
    # SandboxProvider 接口实现
    # ================================================================

    def execute_command(
        self,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """同步执行命令 (容器隔离)

        流程:
        1. N3 命令读写分类 — ro 模式下 WRITE 命令提前失败
        2. 委托 SandboxManager 执行
        3. 将 dict 结果转换为 SandboxResult

        timeout: 接口契约参数（facade 强制透传）；容器内超时由
        SandboxManager 部署侧缺省管理，暂不透传（签名兼容优先，杜绝 TypeError）。
        """
        # N3: 命令读写分类
        mount_mode = self.config.get("workspace_mount_mode", "ro")
        risk = classify_command(command)

        if mount_mode == "ro" and risk in (CommandRisk.WRITE, CommandRisk.UNKNOWN):
            return SandboxResult(
                success=False,
                stdout="",
                stderr=(f"命令需要写权限, 但当前 workspace 以只读模式挂载: {command[:100]}\n分类结果: {risk.value}\n解决方案: 在 .dawei/settings.json 中将 workspace_mount_mode 改为 'rw'"),
                exit_code=77,  # EX_NOPERM
                execution_time=0,
                workspace=str(ctx.workspace_id),
                provider="docker",
                isolation_level=IsolationLevel.CONTAINER,
            )

        # 委托 SandboxManager 执行
        result_dict = self.manager.execute_command(
            command=command,
            workspace_path=ctx.workspace_path,
            user_id=str(ctx.user_id),
        )

        # 转换为 SandboxResult
        return SandboxResult(
            success=result_dict.get("success", False),
            stdout=result_dict.get("stdout", ""),
            stderr=result_dict.get("stderr", ""),
            exit_code=result_dict.get("exit_code", -1),
            execution_time=result_dict.get("execution_time", 0),
            workspace=str(ctx.workspace_id),
            provider="docker",
            isolation_level=IsolationLevel.CONTAINER,
        )

    async def execute_command_async(
        self,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """异步执行命令"""
        return await asyncio.to_thread(self.execute_command, command, ctx, timeout)

    def health_check(self) -> bool:
        """健康检查 — 检查 Docker/Podman daemon"""
        try:
            return self.manager.health_check()
        except Exception as e:
            logger.warning("[DOCKER_PROVIDER] health_check 异常: %s", e)
            return False

    def get_capabilities(self) -> SandboxCapabilities:
        """能力声明"""
        return SandboxCapabilities(
            isolation_level=IsolationLevel.CONTAINER,
            supports_network=self.config.get("sandbox_disable_network", True) is False,
            supports_filesystem=True,
            supports_resource_limits=True,
            supports_pause=False,
            max_timeout=self.config.get("timeout", 30),
            cold_start_ms=500,
        )


# ================================================================
# 向后兼容: SandboxManager 别名
# ================================================================


def get_sandbox_manager(config: dict[str, Any] | None = None) -> Any:
    """获取底层 SandboxManager 实例 (向后兼容用)

    旧调用方可直接替换:
        # 旧: from dawei.sandbox.sandbox_manager import SandboxManager
        # 新: from dawei.sandbox.docker_provider import get_sandbox_manager
    """
    provider = DockerProvider(config)
    return provider.manager
