# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""精简的强类型事件系统 (KISS Principle)
从87个事件类型精简为30个核心事件

重构说明：
- 移除未使用的事件类型
- 合并相似功能的事件
- 保留核心业务事件
- 遵循Fast Fail原则
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, TypeVar

from dawei.interfaces.event_bus import IEventBus

# 定义泛型类型变量
T = TypeVar("T")


class TaskEventType(Enum):
    """核心任务事件类型 (30个) - 精简版

    分类：
    - 任务生命周期 (5个)
    - 工具执行 (4个)
    - LLM交互 (3个)
    - 状态管理 (5个)
    - 用户交互 (3个)
    - 错误处理 (2个)
    - 工作流 (3个)
    - 调试 (2个)
    - 系统事件 (3个)

    """

    # ========== 任务生命周期 (5个) ==========
    TASK_STARTED = "task_started"  # 任务开始
    TASK_COMPLETED = "task_completed"  # 任务完成
    TASK_FAILED = "task_failed"  # 任务失败
    TASK_PAUSED = "task_paused"  # 任务暂停
    TASK_RESUMED = "task_resumed"  # 任务恢复

    # ========== 工具执行 (4个) ==========
    TOOL_STARTED = "tool_started"  # 工具开始执行
    TOOL_PROGRESS = "tool_progress"  # 工具执行进度
    TOOL_COMPLETED = "tool_completed"  # 工具执行完成
    TOOL_FAILED = "tool_failed"  # 工具执行失败

    # ========== LLM交互 (3个) ==========
    LLM_REQUEST_STARTED = "llm_request_started"  # LLM请求开始
    LLM_STREAM_CONTENT = "llm_stream_content"  # LLM流式内容
    LLM_REQUEST_COMPLETED = "llm_request_completed"  # LLM请求完成

    # ========== 状态管理 (5个) ==========
    STATE_CHANGED = "state_changed"  # 状态变更
    MODE_SWITCHED = "mode_switched"  # 模式切换
    CHECKPOINT_SAVED = "checkpoint_saved"  # 检查点保存
    CHECKPOINT_RESTORED = "checkpoint_restored"  # 检查点恢复
    CONTEXT_UPDATED = "context_updated"  # 上下文更新

    # ========== 用户交互 (3个) ==========
    USER_QUESTION = "user_question"  # 后端向前端提问
    USER_INPUT = "user_input"  # 用户输入
    UI_EVENT = "ui_event"  # UI事件（A2UI等）

    # ========== 错误处理 (2个) ==========
    ERROR_OCCURRED = "error_occurred"  # 错误发生
    WARNING_OCCURRED = "warning_occurred"  # 警告发生

    # ========== 工作流 (3个) ==========
    WORKFLOW_STARTED = "workflow_started"  # 工作流开始
    WORKFLOW_STEP_COMPLETED = "workflow_step_completed"  # 工作流步骤完成
    WORKFLOW_COMPLETED = "workflow_completed"  # 工作流完成

    # ========== 调试 (2个) ==========
    DEBUG_INFO = "debug_info"  # 调试信息
    USAGE_RECEIVED = "usage_received"  # Token使用统计

    # ========== 系统事件 (3个) ==========
    SYSTEM_READY = "system_ready"  # 系统就绪
    MODEL_SELECTED = "model_selected"  # 模型选择
    FILES_REFERENCED = "files_referenced"  # 文件引用

    # ========== 已弃用的事件（保留用于向后兼容）==========
    # 以下事件映射到新的事件名称
    TASK_ERROR = TASK_FAILED  # 使用 TASK_FAILED
    TOOL_CALL_START = TOOL_STARTED  # 使用 TOOL_STARTED
    TOOL_CALL_PROGRESS = TOOL_PROGRESS  # 使用 TOOL_PROGRESS
    TOOL_CALL_RESULT = TOOL_COMPLETED  # 使用 TOOL_COMPLETED
    CONTENT_STREAM = LLM_STREAM_CONTENT  # 使用 LLM_STREAM_CONTENT
    API_REQUEST_STARTED = LLM_REQUEST_STARTED  # 使用 LLM_REQUEST_STARTED
    API_REQUEST_COMPLETED = LLM_REQUEST_COMPLETED  # 使用 LLM_REQUEST_COMPLETED
    FOLLOWUP_QUESTION = USER_QUESTION  # 使用 USER_QUESTION
    A2UI_SURFACE_EVENT = UI_EVENT  # 使用 UI_EVENT
    CHECKPOINT_CREATED = CHECKPOINT_SAVED  # 使用 CHECKPOINT_SAVED
    API_REQUEST_FAILED = LLM_REQUEST_COMPLETED  # 失败包含在完成事件中
    TOOL_CALLS_DETECTED = TOOL_STARTED  # 使用 TOOL_STARTED
    MODE_AUTO_SWITCH_DETECTED = MODE_SWITCHED  # 使用 MODE_SWITCHED
    TASK_ABORTED = TASK_FAILED  # 使用 TASK_FAILED
    RETRY_SUCCESS = TASK_COMPLETED  # 使用 TASK_COMPLETED
    RETRY_FAILED = TASK_FAILED  # 使用 TASK_FAILED
    COMPLETE_RECEIVED = TASK_COMPLETED  # 使用 TASK_COMPLETED
    REASONING = DEBUG_INFO  # 使用 DEBUG_INFO
    SKILLS_LOADED = SYSTEM_READY  # 使用 SYSTEM_READY
    TODOS_UPDATED = CONTEXT_UPDATED  # 使用 CONTEXT_UPDATED
    TASK_GRAPH_CREATED = WORKFLOW_STARTED  # 使用 WORKFLOW_STARTED
    TASK_GRAPH_UPDATED = WORKFLOW_STEP_COMPLETED  # 使用 WORKFLOW_STEP_COMPLETED
    PERSIST_TASK_GRAPH = WORKFLOW_COMPLETED  # 使用 WORKFLOW_COMPLETED
    TASK_NODE_ADDED = WORKFLOW_STEP_COMPLETED  # 使用 WORKFLOW_STEP_COMPLETED
    TASK_NODE_UPDATED = WORKFLOW_STEP_COMPLETED  # 使用 WORKFLOW_STEP_COMPLETED
    # PDCA事件映射到工作流事件
    PDCA_CYCLE_STARTED = WORKFLOW_STARTED
    PDCA_PHASE_ADVANCED = WORKFLOW_STEP_COMPLETED
    PDCA_CYCLE_COMPLETED = WORKFLOW_COMPLETED
    PDCA_DOMAIN_DETECTED = STATE_CHANGED
    # 定时器事件映射（如果不常用）
    TIMER_TRIGGERED = WORKFLOW_STEP_COMPLETED
    TIMER_COMPLETED = WORKFLOW_STEP_COMPLETED
    TIMER_FAILED = TASK_FAILED
    TIMER_CANCELLED = TASK_FAILED


@dataclass
class TaskEvent[T]:
    """纯强类型任务事件数据结构"""

    event_id: str
    event_type: TaskEventType  # 只接受枚举类型
    source: str
    task_id: str
    data: T  # 泛型数据字段
    priority: int = 5
    timestamp: float = field(default_factory=time.time)

    def get_event_data_dict(self) -> dict[str, Any]:
        """获取事件数据的字典表示（向后兼容）"""
        if hasattr(self.data, "get_event_data"):
            return self.data.get_event_data()
        if hasattr(self.data, "__dict__"):
            return self.data.__dict__
        return {"data": self.data}


class SimpleEventBus(IEventBus):
    """简化的事件总线 (KISS Principle)

    特性：
    - 纯强类型事件系统
    - Fast Fail: handler错误立即抛出（对于关键事件）
    - Event Tolerance: 单个handler失败不影响其他handler（非关键事件）
    - 移除复杂的重试机制
    - 简化统计信息

    """

    # 关键事件集合：这些事件的handler失败应该立即抛出异常
    CRITICAL_EVENTS = {
        TaskEventType.TASK_FAILED,
        TaskEventType.ERROR_OCCURRED,
        TaskEventType.TOOL_FAILED,
    }

    def __init__(self, max_history_size: int = 1000):
        """初始化事件总线

        Args:
            max_history_size: 事件历史记录的最大大小

        """
        self._handlers: dict[TaskEventType, list[Callable]] = {}
        self._event_history: list[TaskEvent[Any]] = []
        self._max_history_size = max_history_size
        self._lock = asyncio.Lock()
        self._statistics: dict[str, Any] = {
            "total_events": 0,
            "event_counts": {},
            "handler_errors": {},
            "last_event_time": None,
        }
        self._logger = logging.getLogger(__name__)

        # 适配器兼容性
        self._handler_id_map: dict[str, TaskEventType] = {}  # handler_id -> event_type
        self._handler_to_id_map: dict[int, str] = {}  # id(handler) -> handler_id (using object id as key)
        self._id_counter = 0
        self._once_handlers: dict[str, str] = {}
        self._event_waiters: dict[TaskEventType, list[asyncio.Future]] = {}

    async def _execute_handler(
        self,
        handler: Callable,
        event: TaskEvent,
        event_type: TaskEventType,
        handler_index: int,
    ) -> None:
        """执行事件处理器（简化版，无重试）

        Fast Fail原则：
        - 关键事件：handler失败立即抛出异常
        - 非关键事件：记录错误但继续执行其他handler

        Args:
            handler: 处理器函数
            event: 事件对象
            event_type: 事件类型
            handler_index: handler索引

        Raises:
            Exception: 关键事件的handler失败时抛出

        """
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception as e:
            # 记录错误
            self._logger.error(
                f"Handler error for {event_type.value} (index={handler_index}): {e}",
                exc_info=True,
            )

            # 更新错误统计
            event_type_str = event_type.value
            self._statistics["handler_errors"][event_type_str] = self._statistics["handler_errors"].get(event_type_str, 0) + 1

            # Fast Fail: 关键事件立即抛出异常
            if event_type in self.CRITICAL_EVENTS:
                self._logger.critical(f"Critical event handler failed for {event_type.value}: {e}")
                raise  # 立即抛出，不继续执行其他handler

            # Event Tolerance: 非关键事件只记录，继续执行其他handler
            self._logger.debug("Non-critical event handler failed, continuing with other handlers")

    def add_handler(self, event_type: TaskEventType, handler: Callable) -> str:
        """添加事件处理器（纯强类型）

        Args:
            event_type: 事件类型（必须是枚举）
            handler: 事件处理函数

        Returns:
            处理器ID

        Raises:
            TypeError: 如果 event_type 不是 TaskEventType 枚举

        """
        if not isinstance(event_type, TaskEventType):
            raise TypeError(f"event_type must be TaskEventType enum, got {type(event_type)}")

        # 🔧 修复：使用全局计数器生成唯一ID，而不是基于列表长度
        # 这样可以避免删除中间元素后ID重复的问题
        handler_id = f"handler_{event_type.value}_{self._id_counter}"
        self._id_counter += 1

        # 🔧 修复：检查handler数量，如果异常多可能是重复注册导致的
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        existing_handlers = self._handlers[event_type]
        if len(existing_handlers) > 50:  # 阈值：超过50个handler视为异常
            self._logger.warning(
                f"[EVENT_BUS] ⚠️ Abnormally high number of handlers detected for event {event_type.value}: {len(existing_handlers)}. This may indicate duplicate handler registrations (memory leak). Consider checking if handlers are being properly removed.",
            )

        # Store handler with its ID for later removal
        self._handlers[event_type].append(handler)

        # 🔧 修复：维护双向映射，以便后续可以通过handler函数查找ID
        self._handler_id_map[handler_id] = event_type
        self._handler_to_id_map[id(handler)] = handler_id

        # 🔧 修复：添加详细的日志，包含当前handler总数
        self._logger.debug(
            f"[EVENT_BUS] Added handler {handler_id} for event type {event_type.value}. Total handlers for this event: {len(self._handlers[event_type])}",
        )

        return handler_id

    def remove_handler(self, event_type: TaskEventType, handler_id: str) -> bool:
        """移除事件处理器（纯强类型）

        Args:
            event_type: 事件类型（必须是枚举）
            handler_id: 处理器ID

        Returns:
            是否成功移除

        Raises:
            TypeError: 如果 event_type 不是 TaskEventType 枚举

        """
        if not isinstance(event_type, TaskEventType):
            raise TypeError(f"event_type must be TaskEventType enum, got {type(event_type)}")

        # 🔧 修复：验证handler_id是否存在于映射中
        if handler_id not in self._handler_id_map:
            self._logger.warning(
                f"[EVENT_BUS] Handler ID {handler_id} not found in registry"
            )
            return False

        # 🔧 修复：验证handler_id映射的event_type是否匹配
        mapped_event_type = self._handler_id_map[handler_id]
        if mapped_event_type != event_type:
            self._logger.error(
                f"[EVENT_BUS] Handler ID mismatch: {handler_id} is registered for {mapped_event_type.value}, but removal attempted for {event_type.value}"
            )
            return False

        if event_type not in self._handlers:
            self._logger.warning(
                f"[EVENT_BUS] No handlers registered for event type {event_type.value}"
            )
            return False

        handlers = self._handlers[event_type]

        # 🔧 修复：通过遍历查找handler并移除（使用identity比较）
        # 由于我们维护了_handler_to_id_map，我们可以反向查找handler
        handler_to_remove = None
        for handler in handlers:
            if id(handler) in self._handler_to_id_map and self._handler_to_id_map[id(handler)] == handler_id:
                handler_to_remove = handler
                break

        if handler_to_remove is None:
            self._logger.warning(
                f"[EVENT_BUS] Handler {handler_id} not found in handlers list for event {event_type.value}"
            )
            return False

        # 移除handler
        try:
            handlers.remove(handler_to_remove)

            # 清理映射
            del self._handler_id_map[handler_id]
            del self._handler_to_id_map[id(handler_to_remove)]

            self._logger.debug(
                f"[EVENT_BUS] Removed handler {handler_id} for event type {event_type.value}. Remaining handlers: {len(handlers)}"
            )
            return True
        except ValueError:
            self._logger.error(
                f"[EVENT_BUS] Failed to remove handler {handler_id} from list"
            )
            return False

    async def emit_event(self, event_message) -> None:
        """发送强类型事件消息（实现 IEventBus 接口）

        Args:
            event_message: 强类型事件消息对象 (TaskEvent)

        """
        # 验证event_message类型
        if not isinstance(event_message, TaskEvent):
            raise TypeError(f"event_message must be TaskEvent, got {type(event_message)}")

        await self._process_event(event_message)

    async def publish(
        self,
        event_type: TaskEventType,
        data: Any,
        task_id: ClassVar[str] = "",
        source: ClassVar[str] = "system",
    ) -> None:
        """发布事件（纯强类型）

        Args:
            event_type: 事件类型（必须是枚举）
            data: 事件数据
            task_id: 任务ID
            source: 事件源

        Raises:
            TypeError: 如果 event_type 不是 TaskEventType 枚举

        """
        if not isinstance(event_type, TaskEventType):
            raise TypeError(f"event_type must be TaskEventType enum, got {type(event_type)}")

        # 创建 TaskEvent 对象并调用 emit_event
        event = TaskEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            data=data,
            task_id=task_id,
            source=source,
            timestamp=time.time(),
        )
        await self.emit_event(event)

    async def _process_event(self, event: TaskEvent) -> None:
        """处理事件（简化版）

        Args:
            event: 要处理的事件

        Raises:
            Exception: 关键事件的handler失败时抛出

        """
        event_type = event.event_type

        try:
            # 执行处理器（使用简化的执行逻辑）
            if event_type in self._handlers:
                handlers = self._handlers[event_type].copy()  # 创建副本避免在迭代时修改
                for i, handler in enumerate(handlers):
                    await self._execute_handler(handler, event, event_type, i)

            # 记录事件历史
            await self._record_event(event)

            # 处理等待此事件的Future
            await self._resolve_event_waiters(event_type, event)

        except Exception as e:
            # 关键事件失败会传播到这里
            self._logger.error(
                f"Critical failure processing event {event.event_id} (type={event_type.value}): {e}",
                exc_info=True,
            )
            raise  # 重新抛出，遵循Fast Fail原则

    async def _resolve_event_waiters(self, event_type: TaskEventType, event: TaskEvent) -> None:
        """解析等待此事件的Future

        Args:
            event_type: 事件类型
            event: 事件对象

        """
        self._logger.debug(f"Resolving waiters for event type: {event_type}")
        self._logger.debug(f"Available waiter types: {list(self._event_waiters.keys())}")

        if event_type in self._event_waiters:
            waiters = self._event_waiters[event_type].copy()
            self._logger.debug(f"Found {len(waiters)} waiters for event type: {event_type}")

            # 先清空等待列表，避免竞态条件
            self._event_waiters[event_type] = []

            for future in waiters:
                if not future.done():
                    self._logger.debug("Setting result for future")
                    # 转换为字典格式，使用强类型数据的字典表示
                    event_dict = {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "source": event.source,
                        "task_id": event.task_id,
                        "data": event.get_event_data_dict(),  # 使用强类型数据的字典表示
                        "priority": event.priority,
                        "timestamp": event.timestamp,
                    }
                    future.set_result(event_dict)
                else:
                    self._logger.debug("Future already done")

            self._logger.debug(f"Cleared waiters for event type: {event_type}")
        else:
            self._logger.debug(f"No waiters found for event type: {event_type}")

    async def _record_event(self, event: TaskEvent) -> None:
        """记录事件历史（纯强类型）

        Args:
            event: 要记录的事件

        """
        async with self._lock:
            self._event_history.append(event)

            # 限制历史大小
            if len(self._event_history) > self._max_history_size:
                self._event_history = self._event_history[-self._max_history_size :]

            # 更新统计
            self._statistics["total_events"] += 1
            event_type_value = event.event_type.value  # 直接从枚举获取值

            self._statistics["event_counts"][event_type_value] = self._statistics["event_counts"].get(event_type_value, 0) + 1

            self._statistics["last_event_time"] = event.timestamp

    def on(self, event_type: str, handler: Callable) -> str:
        """订阅事件（实现 IEventBus 接口）

        Args:
            event_type: 事件类型字符串
            handler: 事件处理器

        Returns:
            处理器ID

        Raises:
            TypeError: 如果事件类型无效或处理器不可调用
            ValueError: 如果处理器参数无效

        """
        self._logger.debug(f"Adding handler for event: {event_type}")

        # 生成唯一的处理器ID
        handler_id = f"adapter_handler_{self._id_counter}"
        self._id_counter += 1

        try:
            # 将字符串事件类型转换为TaskEventType枚举
            # 如果事件类型字符串不匹配任何枚举值，使用通用类型
            try:
                task_event_type = TaskEventType(event_type)
            except ValueError:
                # 如果没有匹配的枚举值，创建一个通用的TaskEventType
                # 这里需要动态扩展TaskEventType枚举，或者使用已有的通用类型
                # 为了保持兼容性，我们使用一个通用的方法
                task_event_type = None
                # 检查是否有匹配的枚举值
                for enum_type in TaskEventType:
                    if enum_type.value == event_type:
                        task_event_type = enum_type
                        break

                if task_event_type is None:
                    # 如果没有匹配的枚举值，使用TASK_COMPLETED作为默认值
                    # 这应该在实际应用中根据需求调整
                    task_event_type = TaskEventType.TASK_COMPLETED
                    self._logger.warning(
                        f"Unknown event type string '{event_type}', using default TaskEventType.TASK_COMPLETED",
                    )

            # 添加处理器到 SimpleEventBus
            internal_handler_id = self.add_handler(task_event_type, handler)
        except (TypeError, ValueError) as e:
            # Fast Fail: handler注册失败应立即抛出
            self._logger.error(f"Failed to add handler for {event_type}: {e}", exc_info=True)
            raise

        # 映射内部ID到外部ID
        self._handler_id_map[handler_id] = internal_handler_id

        self._logger.debug(f"Handler added successfully: {event_type} (ID: {handler_id})")
        return handler_id

    def off(self, event_type: str, handler_id: str) -> bool:
        """取消订阅事件（实现 IEventBus 接口）

        Args:
            event_type: 事件类型字符串
            handler_id: 处理器ID

        Returns:
            是否取消成功

        Raises:
            TypeError: 如果事件类型无效
            KeyError: 如果handler_id不存在

        """
        self._logger.debug(f"Removing handler for event: {event_type} (ID: {handler_id})")

        # 获取内部处理器ID
        internal_handler_id = self._handler_id_map.get(handler_id)
        if not internal_handler_id:
            self._logger.warning(f"Handler ID not found: {handler_id}")
            return False

        try:
            # 将字符串事件类型转换为TaskEventType枚举
            try:
                task_event_type = TaskEventType(event_type)
            except ValueError:
                # 如果没有匹配的枚举值，检查是否有匹配的枚举值
                task_event_type = None
                for enum_type in TaskEventType:
                    if enum_type.value == event_type:
                        task_event_type = enum_type
                        break

                if task_event_type is None:
                    # 如果没有匹配的枚举值，使用TASK_COMPLETED作为默认值
                    task_event_type = TaskEventType.TASK_COMPLETED
                    self._logger.warning(
                        f"Unknown event type string '{event_type}', using default TaskEventType.TASK_COMPLETED",
                    )

            # 从 SimpleEventBus 移除处理器
            success = self.remove_handler(task_event_type, internal_handler_id)
        except (TypeError, KeyError) as e:
            # Fast Fail: handler移除失败应立即抛出
            self._logger.error(
                f"Failed to remove handler for {event_type} (ID: {handler_id}): {e}",
                exc_info=True,
            )
            raise

        if success:
            # 移除ID映射
            del self._handler_id_map[handler_id]
            self._logger.debug(f"Handler removed successfully: {event_type} (ID: {handler_id})")
        else:
            self._logger.warning(f"Failed to remove handler: {event_type} (ID: {handler_id})")

        return success

    def once(self, event_type: str, handler: Callable) -> str:
        """订阅一次性事件（实现 IEventBus 接口）

        Args:
            event_type: 事件类型字符串
            handler: 事件处理器

        Returns:
            处理器ID

        Raises:
            TypeError: 如果事件类型无效或处理器不可调用
            ValueError: 如果处理器参数无效

        """
        self._logger.debug(f"Adding once handler for event: {event_type}")

        # 先添加包装器处理器，获取handler_id
        # 创建包装器处理器，在第一次调用后自动移除
        def once_wrapper(event):
            try:
                # Event Tolerance: wrapper内部错误不应影响其他handler
                # 调用原始处理器
                if asyncio.iscoroutinefunction(handler):
                    # 如果是异步函数，需要创建任务
                    asyncio.create_task(handler(event))
                else:
                    handler(event)

                # 移除处理器 - 使用外部event_type字符串
                self.off(event_type, handler_id)

            except (RuntimeError, ValueError, TypeError, AttributeError) as e:
                # Wrapper执行错误 - 记录但不中断事件
                self._logger.error(
                    f"Error in once handler for {event_type} (ID: {handler_id}): {e}",
                    exc_info=True,
                )

        try:
            # 添加包装器处理器
            handler_id = self.on(event_type, once_wrapper)
        except (TypeError, ValueError) as e:
            # Fast Fail: once handler注册失败应立即抛出
            self._logger.error(f"Failed to add once handler for {event_type}: {e}", exc_info=True)
            raise

        # 记录一次性处理器
        self._once_handlers[handler_id] = event_type

        self._logger.debug(f"Once handler added successfully: {event_type} (ID: {handler_id})")
        return handler_id

    def get_event_history(self, event_type: str | None = None) -> list[dict[str, Any]]:
        """获取事件历史（实现 IEventBus 接口）

        Args:
            event_type: 事件类型，为 None 时获取所有事件

        Returns:
            事件历史列表（失败时返回空列表）

        Note:
            数据访问错误使用Fallback模式，返回空列表而非抛出异常

        """
        self._logger.debug(f"Getting event history for: {event_type or 'all'}")

        try:
            # 获取事件历史
            events = self._get_event_history_by_type(event_type) if event_type else self._event_history.copy()

            # 转换为字典格式，使用强类型数据的字典表示
            history = []
            for event in events:
                event_dict = {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "source": event.source,
                    "task_id": event.task_id,
                    "data": event.get_event_data_dict(),  # 使用强类型数据的字典表示
                    "priority": event.priority,
                    "timestamp": event.timestamp,
                }
                history.append(event_dict)

            self._logger.debug(f"Retrieved event history: {len(history)} events")
            return history

        except (AttributeError, KeyError, ValueError, TypeError) as e:
            # Fallback: 数据访问错误返回空列表
            self._logger.error(
                f"Failed to get event history for {event_type or 'all'}: {e}",
                exc_info=True,
            )
            return []

    def _get_event_history_by_type(
        self,
        event_type: ClassVar[str | TaskEventType | None] = None,
        limit: ClassVar[int] = 100,
    ) -> list[TaskEvent[Any]]:
        """获取事件历史（内部方法）

        Args:
            event_type: 事件类型过滤（可选）
            limit: 返回的最大事件数量

        Returns:
            事件历史列表

        """
        events = self._event_history.copy()

        if event_type:
            # 处理事件类型
            if isinstance(event_type, TaskEventType):
                # 如果是枚举类型，直接比较
                events = [e for e in events if e.event_type == event_type]
            else:
                # 如果是字符串类型，转换为枚举或比较字符串值
                try:
                    task_event_type = TaskEventType(event_type)
                    events = [e for e in events if e.event_type == task_event_type]
                except ValueError:
                    # 如果没有匹配的枚举值，比较字符串值
                    events = [e for e in events if e.event_type.value == event_type]

        return events[-limit:] if len(events) > limit else events

    def clear_history(self, event_type: str | None = None) -> None:
        """清除事件历史（实现 IEventBus 接口）

        Args:
            event_type: 事件类型，为 None 时清除所有事件历史

        Raises:
            RuntimeError: 如果清除操作失败

        """
        self._logger.debug(f"Clearing event history for: {event_type or 'all'}")

        try:
            if event_type:
                # 处理字符串事件类型
                if isinstance(event_type, TaskEventType):
                    # 如果是枚举类型，直接比较
                    events_to_remove = [e for e in self._event_history if e.event_type == event_type]
                else:
                    # 如果是字符串类型，转换为枚举或比较字符串值
                    try:
                        task_event_type = TaskEventType(event_type)
                        events_to_remove = [e for e in self._event_history if e.event_type == task_event_type]
                    except ValueError:
                        # 如果没有匹配的枚举值，比较字符串值
                        events_to_remove = [e for e in self._event_history if e.event_type.value == event_type]

                # 移除匹配的事件
                for event in events_to_remove:
                    self._event_history.remove(event)

                # 更新统计信息
                for event in events_to_remove:
                    event_type_value = event.event_type.value
                    if event_type_value in self._statistics["event_counts"]:
                        self._statistics["event_counts"][event_type_value] -= 1

                self._logger.info(f"Cleared history for event type: {event_type}")
            else:
                # 清除所有历史
                self._event_history.clear()
                self._statistics = {
                    "total_events": 0,
                    "event_counts": {},
                    "handler_errors": {},
                    "last_event_time": None,
                }
                self._logger.info("Cleared all event history")

        except (RuntimeError, ValueError, AttributeError, KeyError) as e:
            # Fast Fail: 清除历史失败应立即抛出
            self._logger.error(
                f"Failed to clear event history for {event_type or 'all'}: {e}",
                exc_info=True,
            )
            raise RuntimeError(f"Failed to clear event history: {e}")

    def get_handler_count(self, event_type: str) -> int:
        """获取事件处理器数量（实现 IEventBus 接口）

        Args:
            event_type: 事件类型字符串

        Returns:
            处理器数量（失败时返回0）

        Note:
            数据访问错误使用Fallback模式，返回0而非抛出异常

        """
        try:
            # 将字符串事件类型转换为TaskEventType枚举
            try:
                task_event_type = TaskEventType(event_type)
            except ValueError:
                # 如果没有匹配的枚举值，检查是否有匹配的枚举值
                task_event_type = None
                for enum_type in TaskEventType:
                    if enum_type.value == event_type:
                        task_event_type = enum_type
                        break

                if task_event_type is None:
                    # 如果没有匹配的枚举值，返回0
                    self._logger.warning(f"Unknown event type string: {event_type}")
                    return 0

            count = self.get_handlers_count(task_event_type)
            self._logger.debug(f"Handler count for {event_type}: {count}")
            return count

        except (TypeError, AttributeError, KeyError) as e:
            # Fallback: 类型转换或访问错误返回0
            self._logger.error(f"Failed to get handler count for {event_type}: {e}", exc_info=True)
            return 0

    def set_max_history_size(self, size: int) -> None:
        """设置最大历史记录大小（实现 IEventBus 接口）

        Args:
            size: 最大历史记录数量

        Raises:
            ValueError: 如果size参数无效
            RuntimeError: 如果设置操作失败

        """
        self._logger.debug(f"Setting max history size to: {size}")

        try:
            # 验证参数
            if size < 0:
                raise ValueError(f"max_history_size must be non-negative, got {size}")

            # 更新最大历史记录大小
            self._max_history_size = size

            # 如果当前历史记录超过新的大小，截断
            if len(self._event_history) > size:
                self._event_history = self._event_history[-size:]

            self._logger.info(f"Max history size set to: {size}")

        except (ValueError, RuntimeError, TypeError) as e:
            # Fast Fail: 设置失败应立即抛出
            self._logger.error(f"Failed to set max history size to {size}: {e}", exc_info=True)
            raise

    async def wait_for_event(
        self,
        event_type: str,
        timeout: ClassVar[float | None] = None,
    ) -> dict[str, Any] | None:
        """等待特定事件（实现 IEventBus 接口）

        Args:
            event_type: 事件类型字符串
            timeout: 超时时间（秒）

        Returns:
            事件数据或 None（超时/失败）

        Note:
            等待操作失败使用Fallback模式，返回None而非抛出异常

        """
        self._logger.debug(f"Waiting for event: {event_type} (timeout: {timeout})")

        # 将字符串事件类型转换为TaskEventType枚举
        try:
            task_event_type = TaskEventType(event_type)
        except ValueError:
            # 如果没有匹配的枚举值，检查是否有匹配的枚举值
            task_event_type = None
            for enum_type in TaskEventType:
                if enum_type.value == event_type:
                    task_event_type = enum_type
                    break

            if task_event_type is None:
                # 如果没有匹配的枚举值，返回None
                self._logger.warning(f"Unknown event type string: {event_type}")
                return None

        # 创建事件等待逻辑
        event_future = asyncio.Future()

        try:
            # 添加到等待列表
            if task_event_type not in self._event_waiters:
                self._event_waiters[task_event_type] = []
            self._event_waiters[task_event_type].append(event_future)
            self._logger.debug(
                f"Added waiter for event type: {task_event_type}, total waiters: {len(self._event_waiters[task_event_type])}",
            )

            # 等待事件或超时
            try:
                if timeout:
                    event = await asyncio.wait_for(event_future, timeout=timeout)
                else:
                    event = await event_future

                self._logger.debug(f"Event received: {event_type}")
                return event

            except TimeoutError:
                self._logger.warning(f"Timeout waiting for event: {event_type}")
                return None

            except (RuntimeError, ValueError, AttributeError, KeyError) as e:
                # Fallback: 等待过程中错误返回None
                self._logger.error(f"Error waiting for event {event_type}: {e}", exc_info=True)
                return None

        except (RuntimeError, ValueError, AttributeError, KeyError) as e:
            # Fallback: 设置等待失败返回None
            self._logger.error(f"Failed to setup wait for event {event_type}: {e}", exc_info=True)
            return None

    def get_event_statistics(self) -> dict[str, Any]:
        """获取事件统计

        Returns:
            事件统计信息

        """
        # 计算最常见的事件类型
        most_common_event = max(self._statistics["event_counts"].items(), key=lambda x: x[1])[0] if self._statistics["event_counts"] else None

        return {
            **self._statistics,
            "most_common_event": most_common_event,
            "handlers_count": {event_type: len(handlers) for event_type, handlers in self._handlers.items()},
            "history_size": len(self._event_history),
            "max_history_size": self._max_history_size,
        }

    def clear_all_history(self) -> None:
        """清除所有事件历史（兼容方法）"""
        self.clear_history()

    def clear_handlers(self) -> None:
        """清除所有处理器"""
        self._handlers.clear()
        self._handler_id_map.clear()
        self._once_handlers.clear()
        self._logger.info("All handlers cleared")

    def has_handlers(self, event_type: TaskEventType) -> bool:
        """检查是否有指定类型的处理器（纯强类型）

        Args:
            event_type: 事件类型（必须是枚举）

        Returns:
            是否有处理器

        Raises:
            TypeError: 如果 event_type 不是 TaskEventType 枚举

        """
        if not isinstance(event_type, TaskEventType):
            raise TypeError(f"event_type must be TaskEventType enum, got {type(event_type)}")

        return event_type in self._handlers and len(self._handlers[event_type]) > 0

    def get_handlers_count(self, event_type: TaskEventType) -> int:
        """获取指定类型的处理器数量（纯强类型）

        Args:
            event_type: 事件类型（必须是枚举）

        Returns:
            处理器数量

        Raises:
            TypeError: 如果 event_type 不是 TaskEventType 枚举

        """
        if not isinstance(event_type, TaskEventType):
            raise TypeError(f"event_type must be TaskEventType enum, got {type(event_type)}")

        return len(self._handlers.get(event_type, []))

    def get_handler_ids(self) -> list[str]:
        """获取所有处理器ID

        Returns:
            处理器ID列表

        """
        return list(self._handler_id_map.keys())


# core events
CORE_EVENT_BUS = SimpleEventBus()


# 便利函数
async def emit_typed_event(
    event_type: TaskEventType,
    data: Any,
    task_id: str = "",
    source: str = "system",
) -> str:
    """发送强类型事件的便利函数

    Args:
        event_type: 事件类型枚举
        data: 事件数据（泛型）
        task_id: 任务ID
        source: 事件源

    Returns:
        事件ID

    """
    event_id = str(uuid.uuid4())
    # 使用 publish() 方法，它接受多个参数并创建 TaskEvent 对象
    await CORE_EVENT_BUS.publish(event_type, data, task_id, source)
    return event_id


# 导出主要类和类型
__all__ = [
    # 事件类型枚举
    "TaskEventType",
    # 事件类
    "TaskEvent",
    "SimpleEventBus",
    # 便利函数
    "emit_typed_event",
    "add_event_handler",
    "remove_event_handler",
    "get_event_history",
    "get_event_statistics",
    "CORE_EVENT_BUS",
]
