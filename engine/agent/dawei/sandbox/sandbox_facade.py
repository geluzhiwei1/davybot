# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""沙箱统一入口 Facade (§沙箱系统升级 v2 — Phase 1)

v2 关键变更:
- 强制接收 TrustedContext, 不再接受裸参数 (F1 信任边界修复)
- Provider 由 provider_factory 自动检测/创建
- 支持 WebSocket 生命周期钩子透传 (on_disconnect / on_reconnect)
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from dawei.sandbox.base import (
    SandboxCapabilities,
    SandboxProvider,
    SandboxResult,
    TrustedContext,
    UntrustedContextError,
)

logger = logging.getLogger(__name__)


class SandboxFacade:
    """沙箱统一入口 — 上层调用方只需与此类交互

    使用方式:
        ctx = from_user_workspace(user_id, workspace_path)
        result = SandboxFacade.execute_command("ls -la", ctx)

    安全保证:
    - 每次执行前校验 TrustedContext 是否过期
    - Provider 单例, 由 create_provider() 工厂创建
    - 即使 Provider 被直接获取, 也无法绕过 TrustedContext (Provider 层同样校验)
    """

    _provider: SandboxProvider | None = None

    # ================================================================
    # Provider 管理
    # ================================================================

    @classmethod
    def get_provider(cls) -> SandboxProvider:
        """获取当前 Provider (懒加载单例)"""
        if cls._provider is None:
            from dawei.sandbox.provider_factory import create_provider

            cls._provider = create_provider()
            logger.info(
                "[SANDBOX_FACADE] Provider 已初始化: %s",
                cls._provider.__class__.__name__,
            )
        return cls._provider

    @classmethod
    def set_provider(cls, provider: SandboxProvider) -> None:
        """显式设置 Provider (测试 / 依赖注入用)"""
        cls._provider = provider
        logger.info(
            "[SANDBOX_FACADE] Provider 已显式设置: %s",
            provider.__class__.__name__,
        )

    @classmethod
    def reset(cls) -> None:
        """重置 Provider (测试清理用)"""
        if cls._provider is not None:
            try:
                cls._provider.destroy_all_sessions()
            except Exception as e:
                logger.warning("[SANDBOX_FACADE] destroy_all_sessions 异常: %s", e)
        cls._provider = None

    # ================================================================
    # 命令执行 (v2 签名 — 强制 TrustedContext)
    # ================================================================

    @classmethod
    def execute_command(
        cls,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """同步执行命令

        Args:
            command: 命令字符串
            ctx: TrustedContext (由认证层构造, 不可伪造)
            timeout: 每命令超时秒数 (None = provider 缺省; 会在 provider 侧 clamp)

        Raises:
            UntrustedContextError: ctx 已过期或无效
        """
        if ctx.is_expired():
            raise UntrustedContextError(f"TrustedContext 已过期 (workspace_id={ctx.workspace_id})")
        return cls.get_provider().execute_command(command, ctx, timeout=timeout)

    @classmethod
    async def execute_command_async(
        cls,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """异步执行命令

        Args:
            command: 命令字符串
            ctx: TrustedContext (由认证层构造, 不可伪造)
            timeout: 每命令超时秒数 (None = provider 缺省; 会在 provider 侧 clamp)

        Raises:
            UntrustedContextError: ctx 已过期或无效
        """
        if ctx.is_expired():
            raise UntrustedContextError(f"TrustedContext 已过期 (workspace_id={ctx.workspace_id})")
        return await cls.get_provider().execute_command_async(command, ctx, timeout=timeout)

    # ================================================================
    # P3 Path B: 工具调用远程化 — 在沙箱内执行 tool._run()
    # ================================================================

    @classmethod
    def execute_tool(
        cls,
        ctx: TrustedContext,
        tool_class: str,
        kwargs: dict[str, Any],
    ) -> str:
        """在沙箱内执行工具 (P3 Path B)

        将工具调用序列化为 JSON, 通过 tool_runner.py 在沙箱 Python 环境中执行。
        工具代码完全不变, workspace 自动映射到 /workspace。

        Args:
            ctx: TrustedContext
            tool_class: 工具类全限定路径
                        (如 "dawei.tools.custom_tools.read_tools.ReadFileTool")
            kwargs: 已验证的工具参数

        Returns:
            工具执行结果字符串

        Raises:
            UntrustedContextError: ctx 已过期
            RuntimeError: 沙箱执行失败或 tool_runner 输出无效
        """
        import json

        if ctx.is_expired():
            raise UntrustedContextError(
                f"TrustedContext 已过期 (workspace_id={ctx.workspace_id})",
            )

        spec = json.dumps(
            {"tool_class": tool_class, "kwargs": kwargs},
            ensure_ascii=False,
        )

        # 使用 heredoc 安全传递 JSON (单引号分隔符阻止 shell 展开)
        # PYTHONPATH 指向 agent 源码挂载点, 使沙箱内可 import dawei
        command = (
            "PYTHONPATH=/opt/dawei-src:$PYTHONPATH "
            "python3 -m dawei.sandbox.tool_runner <<'DAWEI_TOOL_JSON_EOF'\n"
            f"{spec}\n"
            "DAWEI_TOOL_JSON_EOF"
        )

        result = cls.get_provider().execute_command(command, ctx)

        # 沙箱命令本身失败 (非 tool_runner 内部错误)
        if not result.success:
            raise RuntimeError(
                f"Sandbox tool execution failed (exit={result.exit_code}): "
                f"{result.stderr or result.stdout}",
            )

        # 解析 tool_runner 的 JSON 输出 (取最后一行, 忽略可能的 warning)
        stdout_lines = result.stdout.strip().splitlines()
        if not stdout_lines:
            raise RuntimeError("tool_runner produced no output")

        try:
            output = json.loads(stdout_lines[-1])
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Invalid tool_runner output: {stdout_lines[-1][:200]}",
            ) from e

        if not output.get("success"):
            raise RuntimeError(
                f"Tool execution error: {output.get('error', 'unknown')}",
            )

        return output["result"]

    # ================================================================
    # 能力查询
    # ================================================================

    @classmethod
    def get_capabilities(cls) -> SandboxCapabilities:
        """获取当前 Provider 的能力声明"""
        return cls.get_provider().get_capabilities()

    @classmethod
    def health_check(cls) -> bool:
        """健康检查"""
        return cls.get_provider().health_check()

    # ================================================================
    # 沙箱预热 (P1: 会话启动时预创建, 消除冷启动延迟)
    # ================================================================

    @classmethod
    def prewarm_session(cls, ctx: TrustedContext) -> None:
        """预热沙箱会话

        设计:
        - 配置开关 DAWEI_SANDBOX_PREWARM_ON_SESSION_START (默认 "1"=开启)
        - 失败不抛: Provider 不支持预热或预热失败时, 静默回退到 lazy
        - 上层 (chat handler) 无需 try/except, 但仍建议包一层防御

        Args:
            ctx: TrustedContext (由调用方构造)
        """
        if not cls._is_prewarm_enabled():
            logger.debug("[SANDBOX_FACADE] prewarm 已被配置禁用, 跳过")
            return
        try:
            cls.get_provider().prewarm_session(ctx)
        except NotImplementedError:
            # Provider 默认 no-op 不会触发, 此处仅为防御
            pass
        except Exception as e:
            # 预热失败不影响业务, 首次 execute_command 时会再次尝试创建
            logger.warning(
                "[SANDBOX_FACADE] prewarm_session 失败, 将在首次执行时 lazy 创建: %s",
                e,
            )

    @classmethod
    def _is_prewarm_enabled(cls) -> bool:
        """读取预热配置开关 (环境变量, 默认开启)

        - "1" / "true" / "yes" (大小写不敏感) → 开启
        - 其他 → 关闭
        """
        import os

        val = os.environ.get("DAWEI_SANDBOX_PREWARM_ON_SESSION_START", "1")
        return val.strip().lower() in ("1", "true", "yes", "on")

    # ================================================================
    # WebSocket 生命周期钩子透传 (N1)
    # ================================================================

    @classmethod
    def on_disconnect(cls, ctx: TrustedContext) -> None:
        """WebSocket 断开时调用 — 透传给 Provider"""
        try:
            cls.get_provider().on_disconnect(ctx)
        except Exception as e:
            logger.warning("[SANDBOX_FACADE] on_disconnect 异常: %s", e)

    @classmethod
    def on_reconnect(cls, ctx: TrustedContext) -> None:
        """WebSocket 重连时调用 — 透传给 Provider"""
        try:
            cls.get_provider().on_reconnect(ctx)
        except Exception as e:
            logger.warning("[SANDBOX_FACADE] on_reconnect 异常: %s", e)

    @classmethod
    def destroy_session(cls, ctx: TrustedContext) -> None:
        """销毁指定会话的沙箱"""
        try:
            cls.get_provider().destroy_session(ctx)
        except Exception as e:
            logger.warning("[SANDBOX_FACADE] destroy_session 异常: %s", e)

    @classmethod
    def destroy_all_sessions(cls) -> None:
        """销毁所有会话 (服务关闭时调用)"""
        if cls._provider is not None:
            try:
                cls._provider.destroy_all_sessions()
            except Exception as e:
                logger.warning("[SANDBOX_FACADE] destroy_all_sessions 异常: %s", e)

    @classmethod
    async def cleanup_idle(cls) -> None:
        """空闲沙箱清理 (2026-09-14: 由 server lifespan 周期任务调度)

        Provider 层策略: idle_pause(300s) → pause; idle_destroy(1800s) → 销毁;
        同时回收 grace 期已过的断连会话。Gateway 形态会转发到全部后端。
        """
        if cls._provider is None:
            return
        try:
            await cls._provider.cleanup_idle()
        except Exception as e:
            logger.warning("[SANDBOX_FACADE] cleanup_idle 异常: %s", e)
