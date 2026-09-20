# Copyright (c) 2025 格律至微
from typing import List, Dict
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel, ValidationError

from dawei.tools.tool_contract import validate_tool_contract


class CustomBaseTool(ABC):
    """Simplified BaseTool class for our custom tools."""

    def __init__(self):
        # Don't override class attributes if they exist
        if not hasattr(self, "name"):
            self.name = ""
        if not hasattr(self, "description"):
            self.description = ""
        if not hasattr(self, "args_schema"):
            self.args_schema = None
        # Add a logger
        self.logger = logging.getLogger(self.__class__.__name__)
        # Initialize context as None
        self.context = None
        # Initialize user_workspace as None
        self.user_workspace = None
        # 契约标记：run() 首次执行时校验一次（覆盖 __init__ 里才设置
        # self.args_schema 的工具，如 normflow_tools）
        self._contract_validated = False
        # FAST FAIL：类级 args_schema 在实例化期（= 服务启动期）即校验。
        # 历史（2026-09-17）：smart_text_edit 因 schema 字段 chunk_size 与
        # _run 形参 _chunk_size 命名不一致，上线以来 100% 必挂却被兜底
        # 装饰器吞掉，无人察觉。此校验让同类缺陷在启动时爆炸。
        if self.args_schema is not None:
            validate_tool_contract(self, self.name)

    def set_context(self, context):
        """Set the context for the tool"""
        self.context = context

    # ==================== 执行期上下文解析（单一事实源） ====================
    #
    # 背景工具实例化生命周期（2026-09-12 架构修复）：
    #   ToolManager/CustomToolProvider 在反射扫描期实例化工具，构造参数只有
    #   workspace_root/user_id —— 此时 user_workspace.task_graph /
    #   execution_engine 尚未创建（Agent.create_with_default_engine 在工具
    #   实例化 *之后* 才创建它们，agent.py）。因此构造参数里冻结的
    #   task_graph=None 永远不会更新，工具若直接读 self.task_graph 必然
    #   拿到 None（E2E 故障：new_task "No task graph available"）。
    #
    # 正确解析顺序（与 TaskGraphExecutionEngine 自己读
    #   self._user_workspace.task_graph 的惯用法一致）：
    #   1. 显式构造参数（REST 端点 / 单测注入的 task_graph 优先）
    #   2. ToolExecutor 注入的 user_workspace（chat 路径的活上下文）

    def _resolve_task_graph(self):
        """执行期解析当前 task_graph。

        显式构造参数优先（REST/测试），否则读注入的 user_workspace.task_graph
        （由 Agent.create_with_default_engine 在 agent.py 创建并挂载）。
        """
        tg = getattr(self, "task_graph", None)
        if tg is not None:
            return tg
        ws = self.user_workspace
        return getattr(ws, "task_graph", None) if ws is not None else None

    def _resolve_execution_engine(self):
        """执行期解析当前 TaskGraphExecutionEngine。

        解析顺序：
        1. user_workspace.execution_engine（agent.py 创建 engine 后挂载，按工作区隔离）
        2. workflow_tools_fixed 的活动引擎注册表（兜底；单测试/无工作区上下文）
        """
        ws = self.user_workspace
        if ws is not None:
            engine = getattr(ws, "execution_engine", None)
            if engine is not None:
                return engine
        try:
            from dawei.tools.custom_tools.workflow_tools_fixed import get_active_execution_engine

            return get_active_execution_engine()
        except Exception:  # noqa: BLE001 — 延迟导入失败仅意味着无引擎可用
            return None

    def _schedule_on_main_loop(self, coro) -> bool:
        """把协程 fire-and-forget 调度到主事件循环（worker 线程安全，不阻塞）。

        工具的同步 _run 经 tool_executor 的 asyncio.to_thread 在
        ThreadPoolExecutor worker 线程执行，线程内没有事件循环，
        asyncio.create_task/get_event_loop 必然抛 RuntimeError —— 所有
        从同步 _run 内发起异步善后的工具必须经此方法调度。

        Returns:
            是否成功调度
        """
        import asyncio

        from dawei.tools.custom_tools.async_utils import get_main_loop

        try:
            loop = get_main_loop()
        except RuntimeError:
            loop = None
        if loop is None or loop.is_closed():
            self.logger.warning("%s: main event loop unavailable; async follow-up skipped", self.name)
            if asyncio.iscoroutine(coro):
                coro.close()  # 避免"coroutine was never awaited" RuntimeWarning
            return False
        asyncio.run_coroutine_threadsafe(coro, loop)
        return True

    @abstractmethod
    def _run(self, **kwargs) -> str:
        """The actual implementation of the tool.
        This method should be implemented by subclasses.
        It will receive validated arguments.
        """

    def run(self, context=None, **kwargs) -> str:
        """Public interface for running the tool with Pydantic validation.
        This method should not be overridden by subclasses.
        """
        # Set the context if provided
        if context is not None:
            self.set_context(context)

        # 契约兜底校验（一次性）：覆盖在 __init__ 里才设置 self.args_schema
        # 的工具（类级校验时 args_schema 尚为 None）。违规在此爆炸，
        # 而不是让 TypeError 被上层兜底装饰器吞成裸错误串。
        if not getattr(self, "_contract_validated", False):
            validate_tool_contract(self, self.name)
            self._contract_validated = True

        result = None
        if self.args_schema and issubclass(self.args_schema, BaseModel):
            try:
                # Preprocess kwargs to handle JSON strings for object parameters
                # Some LLMs (like GLM) serialize object parameters as JSON strings
                processed_kwargs = self._preprocess_json_strings(kwargs)

                # Validate and parse the arguments using the Pydantic schema
                validated_args = self.args_schema(**processed_kwargs)
                # Call the actual implementation with validated arguments
                result = self._run(**validated_args.dict())
            except ValidationError:
                # Re-raise the validation error so it can be caught by the ToolExecutor
                # and sent back to the LLM for self-correction.
                raise
        else:
            # If no schema is defined, run the tool directly.
            # This provides backward compatibility for simpler tools.
            result = self._run(**kwargs)

        return result

    def _preprocess_json_strings(self, kwargs: dict) -> dict:
        """Preprocess kwargs to parse JSON strings for object parameters.

        Some LLMs (like GLM) serialize object parameters as JSON strings
        instead of proper objects. This method detects and parses such strings.

        Args:
            kwargs: The raw keyword arguments from the LLM

        Returns:
            Preprocessed kwargs with JSON strings parsed to objects

        """
        import json

        processed = {}
        for key, value in kwargs.items():
            # Check if this field exists in the schema and is an object type
            if key in self.args_schema.model_fields:
                field_info = self.args_schema.model_fields[key]

                # Check if the field annotation indicates a dict or nested model type
                # Common patterns: Dict[str, Any], dict, BaseModel subclass
                field_annotation = str(field_info.annotation)

                # If the value is a string that looks like JSON and the field expects an object
                if (
                    isinstance(value, str)
                    and value.strip().startswith("{")
                    and any(
                        pattern in field_annotation
                        for pattern in [
                            "Dict",
                            "dict",
                            "BaseModel",
                            "TimerSetInput",
                            "object",
                        ]
                    )
                ):
                    try:
                        parsed = json.loads(value)
                        processed[key] = parsed
                        continue
                    except (json.JSONDecodeError, ValueError):
                        # If parsing fails, use the original value
                        pass

            processed[key] = value

        return processed
