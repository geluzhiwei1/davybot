# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace持久化异常类

定义工作区持久化操作相关的所有异常类型
"""


class PersistenceError(Exception):
    """持久化操作基础异常"""

    def __init__(
        self,
        message: str,
        resource_type: str = "unknown",
        resource_id: str | None = None,
    ):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(message)


class WorkspaceInfoPersistenceError(PersistenceError):
    """Workspace信息持久化异常"""

    def __init__(self, message: str, workspace_id: str | None = None):
        super().__init__(message, "workspace_info", workspace_id)


class ConversationPersistenceError(PersistenceError):
    """对话持久化异常"""

    def __init__(self, message: str, conversation_id: str | None = None):
        super().__init__(message, "conversation", conversation_id)


class TaskGraphPersistenceError(PersistenceError):
    """任务图持久化异常"""

    def __init__(self, message: str, task_graph_id: str | None = None):
        super().__init__(message, "task_graph", task_graph_id)


class CheckpointPersistenceError(PersistenceError):
    """检查点持久化异常"""

    def __init__(self, message: str, checkpoint_id: str | None = None):
        super().__init__(message, "checkpoint", checkpoint_id)
