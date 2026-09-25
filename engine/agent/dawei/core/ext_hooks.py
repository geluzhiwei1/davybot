# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""业务扩展钩子注册表（拆库方案 §18.3-S5，阶段六 6a）。

核心主链（chat handler / tool executor）不感知任何业务域：

1. **会话上下文抽取** —— 业务把前端 WS 消息 metadata 中的域上下文
   （如 ``social_context``）写入自己的 ContextVar（与 ``local_context``
   的 auth_token 同通路：不进 LLM 上下文、不落盘）；
2. **工具调用观测** —— 业务编队（social/market/research）按 tool 前缀 +
   当前 mode 自门控，点亮各自的 fleet 徽标 WS 事件；
3. **任务 idle 观测** —— agent 任务结束（成功/失败）后各编队归位 idle。

业务侧 import 时注册（当前：dawei/websocket/{social,market,research}_fleet.py
模块底部的注册块；6b 起随 dawei_biz 经 entry points 触发 import 链）。
缺席即无行为 —— 业务不在场 = 钩子不存在。

约定：所有分发函数绝不向调用方抛异常（可观测性/上下文失败不阻断主流程），
单个钩子失败仅告警并继续其余钩子。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# (metadata, agent) -> None（同步；含各自的清除/兜底语义）
SessionContextExtractor = Callable[[dict[str, Any] | None, Any], None]
# (workspace_id, current_mode, tool_name) -> coroutine（自门控：tool 前缀 + mode）
ToolCallObserver = Callable[[str, str | None, str], Awaitable[None]]
# (workspace_id, session_id) -> coroutine
TaskIdleObserver = Callable[[str, str], Awaitable[None]]

_session_extractors: dict[str, SessionContextExtractor] = {}
_tool_call_observers: dict[str, ToolCallObserver] = {}
_task_idle_observers: dict[str, TaskIdleObserver] = {}


def register_session_context_extractor(name: str, fn: SessionContextExtractor) -> None:
    """注册会话上下文抽取器（同名覆盖；每条 WS 消息分发一次）。"""
    _session_extractors[name] = fn


def register_tool_call_observer(name: str, fn: ToolCallObserver) -> None:
    """注册工具调用观测器（同名覆盖；每次工具执行前分发）。"""
    _tool_call_observers[name] = fn


def register_task_idle_observer(name: str, fn: TaskIdleObserver) -> None:
    """注册任务 idle 观测器（同名覆盖；agent 任务结束时分发）。"""
    _task_idle_observers[name] = fn


def apply_session_context_extractors(metadata: dict[str, Any] | None, agent: Any = None) -> None:
    """按注册表把消息 metadata 分发给各业务抽取器（自含清除/兜底语义）。"""
    for name, fn in list(_session_extractors.items()):
        try:
            fn(metadata, agent)
        except Exception:  # noqa: BLE001 —— 上下文失败不阻断消息主流程
            logger.warning("[EXT_HOOKS] session extractor %r failed", name, exc_info=True)


async def notify_tool_call_observers(workspace_id: str, current_mode: str | None, tool_name: str) -> None:
    """把工具调用事件分发给各编队观察者（自门控；失败仅告警）。"""
    for name, fn in list(_tool_call_observers.items()):
        try:
            await fn(workspace_id, current_mode, tool_name)
        except Exception:  # noqa: BLE001 —— 可观测性失败不阻断工具执行
            logger.warning("[EXT_HOOKS] tool-call observer %r failed", name, exc_info=True)


async def notify_task_idle_observers(workspace_id: str, session_id: str = "") -> None:
    """把任务结束事件分发给各编队观察者（失败仅告警）。"""
    for name, fn in list(_task_idle_observers.items()):
        try:
            await fn(workspace_id, session_id)
        except Exception:  # noqa: BLE001 —— 可观测性失败不阻断对话收尾
            logger.warning("[EXT_HOOKS] task idle observer %r failed", name, exc_info=True)


# (workspace_path, template_slug, form_data, storage) -> coroutine[result dict | None]
# 返回 None = 该初始化器不认领此 slug（领域不匹配），轮询下一个。
WorkspaceTemplateInitializer = Callable[..., Awaitable[dict[str, Any] | None]]

_workspace_template_initializers: dict[str, WorkspaceTemplateInitializer] = {}


def register_workspace_template_initializer(name: str, fn: WorkspaceTemplateInitializer) -> None:
    """注册工作区模板初始化器（同名覆盖；workspace 创建流程按序轮询）。

    核心侧 crud.create_workspace 的模板初始化步骤经此分发（§18.3 缝改造），
    核心不 import 任何业务模板管理器 —— biz 缺席 = 无初始化器 = 跳过该步。
    """
    _workspace_template_initializers[name] = fn


async def run_workspace_template_initializers(
    workspace_path: str,
    template_slug: str,
    form_data: dict[str, Any],
    storage: Any = None,
) -> dict[str, Any] | None:
    """按注册序轮询模板初始化器；返回首个认领结果，失败仅告警不抛。"""
    for name, fn in list(_workspace_template_initializers.items()):
        try:
            result = await fn(workspace_path, template_slug, form_data, storage)
            if result is not None:
                return result
        except Exception:  # noqa: BLE001 —— 模板初始化失败不阻断 workspace 创建
            logger.warning("[EXT_HOOKS] template initializer %r failed", name, exc_info=True)
    return None


# ---------------------------------------------------------------------------
# 进程生命周期钩子（§18.5-G1 倒挂清零）：server_app lifespan 启停时分发。
# 原软 import（from dawei_biz.saas.remote import ...）改 biz 侧注册 —— 核心
# 零 dawei_biz import；业务缺席 = 无钩子 = 无行为。
# ---------------------------------------------------------------------------

# () -> coroutine（进程级服务启动/停止）
LifespanHook = Callable[[], Awaitable[None]]

_lifecycle_hooks: dict[str, tuple[LifespanHook, LifespanHook]] = {}


def register_lifecycle_hooks(name: str, startup: LifespanHook, shutdown: LifespanHook) -> None:
    """注册进程生命周期钩子（同名覆盖；biz import 时调用）。

    saas ping 等进程级业务服务经此接入；门控（caps / env）在钩子内部。
    """
    _lifecycle_hooks[name] = (startup, shutdown)


async def run_lifecycle_startup() -> int:
    """依序执行生命周期启动钩子；任一失败即抛出（FAST FAIL，拒半 boot）。"""
    for name, (startup, _shutdown) in list(_lifecycle_hooks.items()):
        try:
            await startup()
        except Exception:
            logger.error("[EXT_HOOKS] lifecycle startup %r failed — aborting boot", name, exc_info=True)
            raise
    return len(_lifecycle_hooks)


async def run_lifecycle_shutdown() -> int:
    """执行全部生命周期停止钩子（失败仅告警，不阻断其余停机步骤）。"""
    stopped = 0
    for name, (_startup, shutdown) in list(_lifecycle_hooks.items()):
        try:
            await shutdown()
            stopped += 1
        except Exception:  # noqa: BLE001 —— 停机钩子失败不阻断其余停机
            logger.warning("[EXT_HOOKS] lifecycle shutdown %r failed", name, exc_info=True)
    return stopped


__all__ = [
    "LifespanHook",
    "apply_session_context_extractors",
    "notify_task_idle_observers",
    "notify_tool_call_observers",
    "register_lifecycle_hooks",
    "register_session_context_extractor",
    "register_task_idle_observer",
    "register_tool_call_observer",
    "register_workspace_template_initializer",
    "run_lifecycle_shutdown",
    "run_lifecycle_startup",
    "run_workspace_template_initializers",
]
