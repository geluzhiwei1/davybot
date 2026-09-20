# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""SubprocessProvider — 轻量级沙箱 Provider (§沙箱系统升级 v2 — Phase 1)

基于现有 lightweight_executor.py 的 CommandExecutor, 实现 SandboxProvider ABC。
- 命令白名单验证 (复用 command_whitelist.py)
- subprocess 执行, 资源限制: 超时
- 隔离级别: PROCESS (进程级)
- 全平台支持 (Linux / macOS / Windows)

向后兼容: 保留 CommandExecutor 作为别名, 不破坏现有调用方。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import sys
import time
from typing import Any

from dawei.sandbox.base import (
    IsolationLevel,
    SandboxCapabilities,
    SandboxProvider,
    SandboxResult,
    TrustedContext,
)
from dawei.sandbox.command_whitelist import CommandWhitelist
from dawei.sandbox.pii_logger import PiiSafeLogger

logger = PiiSafeLogger(logging.getLogger(__name__))


class SubprocessProvider(SandboxProvider):
    """Subprocess 沙箱 Provider

    最轻量的 Provider: 直接在宿主机进程中执行命令, 通过白名单做安全限制。
    隔离级别: PROCESS (无容器/硬件隔离)
    适用场景: 本地桌面模式 (Tauri App), 或作为其他 Provider 不可用时的兜底。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.whitelist = CommandWhitelist()
        # 保留会话状态 (cd / env 变更), 按会话 key 存储
        self._session_cwd: dict[str, str] = {}

    # ================================================================
    # SandboxProvider 接口实现
    # ================================================================

    def execute_command(
        self,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """同步执行命令

        timeout: 工具层透传的每命令超时（秒）；None = 用安全设置缺省。
        """
        start_time = time.time()

        try:
            # 安全: 白名单校验 (仅在启用时)
            from dawei.core.security_manager import security_manager

            sec = security_manager.get_settings()
            if sec.get("enable_command_whitelist", True):
                is_valid, error_msg = self.whitelist.validate_command(command)
                if not is_valid:
                    return SandboxResult(
                        success=False,
                        stdout="",
                        stderr=error_msg,
                        exit_code=-1,
                        execution_time=0,
                        workspace=str(ctx.workspace_id),
                        provider="subprocess",
                        isolation_level=IsolationLevel.PROCESS,
                    )

            # 准备执行环境
            workspace_path = ctx.workspace_path
            args = shlex.split(command)
            if timeout is None:
                timeout = sec.get("command_execution_timeout", 30) if sec else 30

            env = self._build_env(workspace_path)

            result = subprocess.run(
                args,
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return SandboxResult(
                success=True,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time=execution_time,
                workspace=str(ctx.workspace_id),
                provider="subprocess",
                isolation_level=IsolationLevel.PROCESS,
            )

        except subprocess.TimeoutExpired:
            execution_time = int((time.time() - start_time) * 1000)
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"Command execution timeout ({timeout}s)",
                exit_code=-1,
                execution_time=execution_time,
                workspace=str(ctx.workspace_id),
                provider="subprocess",
                isolation_level=IsolationLevel.PROCESS,
            )
        except FileNotFoundError:
            execution_time = int((time.time() - start_time) * 1000)
            cmd_name = args[0] if "args" in dir() else command
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"Command not found: {cmd_name}",
                exit_code=127,
                execution_time=execution_time,
                workspace=str(ctx.workspace_id),
                provider="subprocess",
                isolation_level=IsolationLevel.PROCESS,
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error("[SUBPROCESS_PROVIDER] 执行失败: %s", e, exc_info=True)
            return SandboxResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time=execution_time,
                workspace=str(ctx.workspace_id),
                provider="subprocess",
                isolation_level=IsolationLevel.PROCESS,
            )

    async def execute_command_async(
        self,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """异步执行命令 — 通过 asyncio.to_thread 包装同步方法"""
        return await asyncio.to_thread(self.execute_command, command, ctx, timeout)

    def health_check(self) -> bool:
        """健康检查 — Subprocess 总是可用"""
        return True

    def get_capabilities(self) -> SandboxCapabilities:
        """能力声明"""
        return SandboxCapabilities(
            isolation_level=IsolationLevel.PROCESS,
            supports_network=False,
            supports_filesystem=True,
            supports_resource_limits=False,
            supports_pause=False,
            max_timeout=30,
            cold_start_ms=0,
        )

    # ================================================================
    # 内部方法
    # ================================================================

    def _build_env(self, workspace_path) -> dict[str, str]:
        """构建安全的执行环境变量"""
        env = {
            "PATH": os.environ.get("PATH", ""),
            "TERM": "xterm",
        }

        if sys.platform != "win32":
            env["HOME"] = str(workspace_path)
        else:
            env["HOME"] = str(workspace_path)
            env["USERPROFILE"] = str(workspace_path)

        # Unix: 清理危险环境变量
        if sys.platform != "win32":
            for key in list(os.environ.keys()):
                if key.upper() in ["LD_PRELOAD", "LD_LIBRARY_PATH", "IFS", "CDPATH"]:
                    env.pop(key, None)

        return env


# ================================================================
# 向后兼容: CommandExecutor 别名
# ================================================================


class CommandExecutor(SubprocessProvider):
    """向后兼容别名 — 等价于 SubprocessProvider

    旧调用方可直接替换:
        # 旧: from dawei.sandbox.lightweight_executor import CommandExecutor
        # 新: from dawei.sandbox.subprocess_provider import CommandExecutor

    也可通过 v2 接口使用:
        ctx = from_user_workspace(user_id, workspace_path)
        result = SandboxFacade.execute_command(cmd, ctx)
    """

    def execute_command(  # type: ignore[override]
        self,
        command: str,
        workspace_path=None,
        user_id: str = "unknown",
        ctx: TrustedContext | None = None,
    ) -> Any:
        """兼容旧签名 (workspace_path, user_id) 和新签名 (TrustedContext)

        旧签名返回 dict (向后兼容 v1 调用方)。
        新签名 (ctx) 返回 SandboxResult (v2 标准)。
        """
        if ctx is not None:
            return super().execute_command(command, ctx)

        # 旧签名兼容: 构造临时 TrustedContext, 返回 dict
        if workspace_path is not None:
            from dawei.sandbox.base import from_user_workspace

            ctx = from_user_workspace(user_id, workspace_path)
            result = super().execute_command(command, ctx)
            return result.to_dict()

        raise ValueError("必须提供 ctx 或 workspace_path 参数")
