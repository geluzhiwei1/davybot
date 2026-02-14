# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""异步任务管理相关的接口定义

定义了任务管理器、任务上下文、WebSocket状态管理器等核心接口。
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from .types import (
    CheckpointData,
    CompletionCallback,
    ConnectionState,
    ErrorCallback,
    ProgressCallback,
    StateChangeCallback,
    TaskDefinition,
    TaskResult,
    TaskStatus,
    WebSocketState,
)


class IAsyncTaskManager(ABC):
    """异步任务管理器接口"""

    @abstractmethod
    async def submit_task(self, task_def: TaskDefinition) -> str:
        """提交任务

        Args:
            task_def: 任务定义

        Returns:
            任务ID

        """

    @abstractmethod
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消

        """

    @abstractmethod
    async def pause_task(self, task_id: str) -> bool:
        """暂停任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功暂停

        """

    @abstractmethod
    async def resume_task(self, task_id: str) -> bool:
        """恢复任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功恢复

        """

    @abstractmethod
    async def get_task_status(self, task_id: str) -> TaskStatus | None:
        """获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态

        """

    @abstractmethod
    async def get_task_result(self, task_id: str) -> TaskResult | None:
        """获取任务结果

        Args:
            task_id: 任务ID

        Returns:
            任务结果

        """

    @abstractmethod
    async def list_tasks(self, status_filter: TaskStatus | None = None) -> list[str]:
        """列出任务

        Args:
            status_filter: 状态过滤器

        Returns:
            任务ID列表

        """

    @abstractmethod
    async def wait_for_task(
        self,
        task_id: str,
        timeout: float | None = None,
    ) -> TaskResult | None:
        """等待任务完成

        Args:
            task_id: 任务ID
            timeout: 超时时间

        Returns:
            任务结果

        """

    @abstractmethod
    def set_progress_callback(self, callback: ProgressCallback) -> None:
        """设置进度回调

        Args:
            callback: 进度回调函数

        """

    @abstractmethod
    def set_state_change_callback(self, callback: StateChangeCallback) -> None:
        """设置状态变化回调

        Args:
            callback: 状态变化回调函数

        """

    @abstractmethod
    def set_error_callback(self, callback: ErrorCallback) -> None:
        """设置错误回调

        Args:
            callback: 错误回调函数

        """

    @abstractmethod
    def set_completion_callback(self, callback: CompletionCallback) -> None:
        """设置完成回调

        Args:
            callback: 完成回调函数

        """

    @abstractmethod
    async def start(self) -> None:
        """启动任务管理器"""

    @abstractmethod
    async def stop(self) -> None:
        """停止任务管理器"""

    @abstractmethod
    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典

        """


class ITaskContext(ABC):
    """任务上下文接口"""

    @abstractmethod
    def get_task_id(self) -> str:
        """获取任务ID"""

    @abstractmethod
    def get_status(self) -> TaskStatus:
        """获取任务状态"""

    @abstractmethod
    def set_status(self, status: TaskStatus) -> None:
        """设置任务状态

        Args:
            status: 新状态

        """

    @abstractmethod
    def get_metadata(self, key: str | None = None) -> Any:
        """获取元数据

        Args:
            key: 元数据键，为None时返回所有元数据

        Returns:
            元数据值

        """

    @abstractmethod
    def set_metadata(self, key: str, value: Any) -> None:
        """设置元数据

        Args:
            key: 元数据键
            value: 元数据值

        """

    @abstractmethod
    def get_data(self, key: str | None = None) -> Any:
        """获取任务数据

        Args:
            key: 数据键，为None时返回所有数据

        Returns:
            数据值

        """

    @abstractmethod
    def set_data(self, key: str, value: Any) -> None:
        """设置任务数据

        Args:
            key: 数据键
            value: 数据值

        """

    @abstractmethod
    async def create_checkpoint(self, force: bool = False) -> str:
        """创建检查点

        Args:
            force: 是否强制创建

        Returns:
            检查点ID

        """

    @abstractmethod
    async def restore_checkpoint(self, checkpoint_id: str) -> bool:
        """恢复检查点

        Args:
            checkpoint_id: 检查点ID

        Returns:
            是否成功恢复

        """

    @abstractmethod
    async def report_progress(
        self,
        progress: int,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """报告任务进度

        Args:
            progress: 进度百分比（0-100）
            message: 进度消息
            data: 附加数据

        """

    @abstractmethod
    def should_cancel(self) -> bool:
        """检查是否应该取消任务"""

    @abstractmethod
    def should_pause(self) -> bool:
        """检查是否应该暂停任务"""

    @abstractmethod
    async def wait_if_paused(self) -> None:
        """如果任务被暂停，等待恢复"""

    @abstractmethod
    def get_execution_time(self) -> float:
        """获取已执行时间（秒）"""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""


class IWebSocketStateManager(ABC):
    """WebSocket状态管理器接口"""

    @abstractmethod
    async def register_connection(self, session_id: str) -> bool:
        """注册连接

        Args:
            session_id: 会话ID

        Returns:
            是否成功注册

        """

    @abstractmethod
    async def unregister_connection(self, session_id: str) -> bool:
        """注销连接

        Args:
            session_id: 会话ID

        Returns:
            是否成功注销

        """

    @abstractmethod
    async def get_connection_state(self, session_id: str) -> WebSocketState | None:
        """获取连接状态

        Args:
            session_id: 会话ID

        Returns:
            连接状态

        """

    @abstractmethod
    async def set_connection_state(self, session_id: str, state: ConnectionState) -> bool:
        """设置连接状态

        Args:
            session_id: 会话ID
            state: 新状态

        Returns:
            是否成功设置

        """

    @abstractmethod
    async def update_heartbeat(self, session_id: str) -> bool:
        """更新心跳

        Args:
            session_id: 会话ID

        Returns:
            是否成功更新

        """

    @abstractmethod
    async def increment_message_count(self, session_id: str) -> bool:
        """增加消息计数

        Args:
            session_id: 会话ID

        Returns:
            是否成功增加

        """

    @abstractmethod
    async def increment_error_count(self, session_id: str, error: str | None = None) -> bool:
        """增加错误计数

        Args:
            session_id: 会话ID
            error: 错误信息

        Returns:
            是否成功增加

        """

    @abstractmethod
    async def list_connections(self, state_filter: ConnectionState | None = None) -> list[str]:
        """列出连接

        Args:
            state_filter: 状态过滤器

        Returns:
            会话ID列表

        """

    @abstractmethod
    async def get_healthy_connections(self) -> list[str]:
        """获取健康的连接

        Returns:
            健康连接的会话ID列表

        """

    @abstractmethod
    async def cleanup_stale_connections(self) -> int:
        """清理过期连接

        Returns:
            清理的连接数量

        """

    @abstractmethod
    def set_state_change_callback(
        self,
        callback: Callable[[str, ConnectionState, ConnectionState], Awaitable[None]],
    ) -> None:
        """设置状态变化回调

        Args:
            callback: 状态变化回调函数

        """

    @abstractmethod
    def set_heartbeat_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """设置心跳回调

        Args:
            callback: 心跳回调函数

        """

    @abstractmethod
    async def start(self) -> None:
        """启动状态管理器"""

    @abstractmethod
    async def stop(self) -> None:
        """停止状态管理器"""

    @abstractmethod
    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典

        """


class ICheckpointService(ABC):
    """检查点服务接口"""

    @abstractmethod
    async def create(self, task_id: str, state_data: dict[str, Any], force: bool = False) -> str:
        """创建检查点

        Args:
            task_id: 任务ID
            state_data: 状态数据
            force: 是否强制创建

        Returns:
            检查点ID

        """

    @abstractmethod
    async def restore(self, checkpoint_id: str) -> dict[str, Any] | None:
        """恢复检查点

        Args:
            checkpoint_id: 检查点ID

        Returns:
            状态数据

        """

    @abstractmethod
    async def list(self, task_id: str) -> list[CheckpointData]:
        """列出检查点

        Args:
            task_id: 任务ID

        Returns:
            检查点列表

        """

    @abstractmethod
    async def delete(self, checkpoint_id: str) -> bool:
        """删除检查点

        Args:
            checkpoint_id: 检查点ID

        Returns:
            是否成功删除

        """

    @abstractmethod
    async def cleanup_old_checkpoints(self, task_id: str, keep_count: int = 5) -> int:
        """清理旧检查点

        Args:
            task_id: 任务ID
            keep_count: 保留数量

        Returns:
            删除的检查点数量

        """


class ITaskExecutor(ABC):
    """任务执行器接口"""

    @abstractmethod
    async def execute(self, task_def: TaskDefinition, context: ITaskContext) -> Any:
        """执行任务

        Args:
            task_def: 任务定义
            context: 任务上下文

        Returns:
            执行结果

        """

    @abstractmethod
    def supports(self, task_def: TaskDefinition) -> bool:
        """检查是否支持执行指定任务

        Args:
            task_def: 任务定义

        Returns:
            是否支持

        """

    @abstractmethod
    def get_executor_name(self) -> str:
        """获取执行器名称"""


class ITaskScheduler(ABC):
    """任务调度器接口"""

    @abstractmethod
    async def schedule(self, task_def: TaskDefinition) -> str:
        """调度任务

        Args:
            task_def: 任务定义

        Returns:
            任务ID

        """

    @abstractmethod
    async def get_next_task(self) -> TaskDefinition | None:
        """获取下一个待执行任务

        Returns:
            任务定义

        """

    @abstractmethod
    async def mark_completed(self, task_id: str) -> None:
        """标记任务完成

        Args:
            task_id: 任务ID

        """

    @abstractmethod
    async def get_queue_size(self) -> int:
        """获取队列大小

        Returns:
            队列中的任务数量

        """

    @abstractmethod
    async def clear_queue(self) -> int:
        """清空队列

        Returns:
            清除的任务数量

        """
