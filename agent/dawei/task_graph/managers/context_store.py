# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""上下文存储器
新架构中专门负责任务上下文存储和管理的组件
"""

import asyncio
from datetime import UTC, datetime, timezone
from typing import Any

from dawei.core.errors import ValidationError
from dawei.logg.logging import get_logger
from dawei.task_graph.task_node_data import TaskContext, ValidationResult


class ContextStore:
    """上下文存储器"""

    def __init__(self):
        self._contexts: dict[str, TaskContext] = {}
        self._lock = asyncio.Lock()
        self.logger = get_logger(__name__)

    async def update_context(self, task_id: str, context: TaskContext) -> bool:
        """更新任务上下文"""
        try:
            async with self._lock:
                # 验证上下文
                validation_result = self.validate_context(context)
                if not validation_result.is_valid:
                    self.logger.error(
                        f"Context validation failed for task {task_id}: {validation_result.errors}",
                    )
                    return False

                self._contexts.get(task_id)
                self._contexts[task_id] = context

                self.logger.info(f"Updated context for task {task_id}")
                return True

        except (ValidationError, AttributeError) as e:
            self.logger.error(
                f"Validation or attribute error updating context for task {task_id}: {e}",
                exc_info=True,
            )
            return False
        except (KeyError, TypeError) as e:
            self.logger.error(
                f"Data access error updating context for task {task_id}: {e}",
                exc_info=True,
            )
            return False

    async def get_context(self, task_id: str) -> TaskContext | None:
        """获取任务上下文"""
        try:
            async with self._lock:
                context = self._contexts.get(task_id)
                return context.copy() if context else None
        except (AttributeError, TypeError) as e:
            self.logger.error(f"Context type error for task {task_id}: {e}", exc_info=True)
            return None

    async def merge_context(self, task_id: str, updates: dict[str, Any]) -> bool:
        """合并更新上下文"""
        try:
            async with self._lock:
                context = self._contexts.get(task_id)
                if not context:
                    self.logger.warning(f"Context not found for task {task_id}, creating new one")
                    # 创建基本上下文
                    context = TaskContext(
                        user_id=updates.get("user_id", ""),
                        session_id=updates.get("session_id", ""),
                        message_id=updates.get("message_id", ""),
                    )

                # 合并更新
                context.merge(updates)
                self._contexts[task_id] = context

                self.logger.info(f"Merged context updates for task {task_id}")
                return True

        except (AttributeError, TypeError) as e:
            self.logger.error(f"Context merge error for task {task_id}: {e}", exc_info=True)
            return False

    async def inherit_context(self, parent_id: str, child_id: str) -> bool:
        """子任务继承父任务上下文"""
        try:
            async with self._lock:
                parent_context = self._contexts.get(parent_id)
                if not parent_context:
                    self.logger.warning(f"Parent context not found for task {parent_id}")
                    return False

                # 创建子任务上下文，继承父任务信息
                child_context = TaskContext(
                    user_id=parent_context.user_id,
                    session_id=parent_context.session_id,
                    message_id=parent_context.message_id,
                    workspace_path=parent_context.workspace_path,
                    parent_context=parent_context.to_dict(),
                    task_files=parent_context.task_files.copy(),
                    task_images=parent_context.task_images.copy(),
                )

                self._contexts[child_id] = child_context

                self.logger.info(f"Inherited context from parent {parent_id} to child {child_id}")
                return True

        except (AttributeError, TypeError, ValueError):
            self.logger.exception("Failed to inherit context from {parent_id} to {child_id}: ")
            return False

    async def get_context_hierarchy(self, task_id: str) -> dict[str, TaskContext]:
        """获取上下文层级关系"""
        try:
            async with self._lock:
                hierarchy = {}
                context = self._contexts.get(task_id)

                if not context:
                    return hierarchy

                # 收集所有相关上下文
                current_context = context
                current_id = task_id

                while current_context:
                    hierarchy[current_id] = current_context

                    # 如果有父上下文，继续向上查找
                    if current_context.parent_context:
                        # 查找父任务ID
                        parent_id = None
                        for tid, ctx in self._contexts.items():
                            if ctx.to_dict() == current_context.parent_context:
                                parent_id = tid
                                break

                        if parent_id:
                            current_context = self._contexts.get(parent_id)
                            current_id = parent_id
                        else:
                            # 找不到父任务，停止查找
                            break
                    else:
                        break

                return hierarchy

        except (KeyError, AttributeError, TypeError):
            self.logger.exception("Failed to get context hierarchy for task {task_id}: ")
            return {}

    async def update_context_files(
        self,
        task_id: str,
        files: list[str],
        images: list[str] | None = None,
    ) -> bool:
        """更新上下文中的文件列表"""
        try:
            async with self._lock:
                context = self._contexts.get(task_id)
                if not context:
                    self.logger.warning(f"Context not found for task {task_id}")
                    return False

                context.task_files = files
                if images is not None:
                    context.task_images = images

                context.updated_at = datetime.now(UTC)

                self.logger.info(
                    f"Updated context files for task {task_id}: {len(files)} files, {len(images or [])} images",
                )
                return True

        except (KeyError, AttributeError, TypeError):
            self.logger.exception("Failed to update context files for task {task_id}: ")
            return False

    async def add_context_file(self, task_id: str, file_path: str) -> bool:
        """添加单个文件到上下文"""
        try:
            async with self._lock:
                context = self._contexts.get(task_id)
                if not context:
                    self.logger.warning(f"Context not found for task {task_id}")
                    return False

                if file_path not in context.task_files:
                    context.task_files.append(file_path)
                    context.updated_at = datetime.now(UTC)

                self.logger.info(f"Added file to context for task {task_id}: {file_path}")
                return True

        except (KeyError, AttributeError, TypeError):
            self.logger.exception("Failed to add file to context for task {task_id}: ")
            return False

    async def remove_context_file(self, task_id: str, file_path: str) -> bool:
        """从上下文中移除文件"""
        try:
            async with self._lock:
                context = self._contexts.get(task_id)
                if not context:
                    self.logger.warning(f"Context not found for task {task_id}")
                    return False

                if file_path in context.task_files:
                    context.task_files.remove(file_path)
                    context.updated_at = datetime.now(UTC)

                self.logger.info(f"Removed file from context for task {task_id}: {file_path}")
                return True

        except (KeyError, AttributeError, TypeError):
            self.logger.exception("Failed to remove file from context for task {task_id}: ")
            return False

    async def add_context_metadata(self, task_id: str, key: str, value: Any) -> bool:
        """添加上下文元数据"""
        try:
            async with self._lock:
                context = self._contexts.get(task_id)
                if not context:
                    self.logger.warning(f"Context not found for task {task_id}")
                    return False

                context.metadata[key] = value
                context.updated_at = datetime.now(UTC)

                self.logger.info(f"Added metadata to context for task {task_id}: {key}")
                return True

        except (KeyError, AttributeError, TypeError):
            self.logger.exception("Failed to add metadata to context for task {task_id}: ")
            return False

    async def get_context_metadata(self, task_id: str, key: str | None = None) -> Any:
        """获取上下文元数据"""
        try:
            async with self._lock:
                context = self._contexts.get(task_id)
                if not context:
                    return None

                if key:
                    return context.metadata.get(key)
                return context.metadata.copy()

        except (KeyError, AttributeError, TypeError):
            self.logger.exception("Failed to get metadata from context for task {task_id}: ")
            return None

    def validate_context(self, context: TaskContext) -> ValidationResult:
        """验证上下文"""
        result = ValidationResult(is_valid=True)

        # 检查必需字段
        if not context.user_id or not context.user_id.strip():
            result.add_error("User ID is required")

        if not context.session_id or not context.session_id.strip():
            result.add_error("Session ID is required")

        if not context.message_id or not context.message_id.strip():
            result.add_error("Message ID is required")

        # 检查文件路径格式
        for file_path in context.task_files:
            if not file_path or not file_path.strip():
                result.add_warning("Empty file path found in context")

        # 检查时间戳
        if context.created_at > context.updated_at:
            result.add_warning("Context created time is after updated time")

        return result

    async def get_all_contexts(self) -> dict[str, TaskContext]:
        """获取所有上下文"""
        try:
            async with self._lock:
                return {task_id: context.copy() for task_id, context in self._contexts.items()}
        except (KeyError, AttributeError, TypeError):
            self.logger.exception("Failed to get all contexts: ")
            return {}

    async def clear_context(self, task_id: str) -> bool:
        """清除任务上下文"""
        try:
            async with self._lock:
                if task_id in self._contexts:
                    del self._contexts[task_id]
                    self.logger.info(f"Cleared context for task {task_id}")
                    return True

                self.logger.warning(f"Context not found for task {task_id}")
                return False

        except (KeyError, AttributeError):
            self.logger.exception("Failed to clear context for task {task_id}: ")
            return False

    async def save_context(self, task_id: str) -> dict[str, Any]:
        """保存上下文到持久化存储"""
        try:
            context = await self.get_context(task_id)
            if not context:
                return {}

            return {
                "task_id": task_id,
                "context": context.to_dict(),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except (KeyError, AttributeError, TypeError):
            self.logger.exception("Failed to save context for task {task_id}: ")
            return {}

    async def load_context(self, task_id: str, data: dict[str, Any]) -> bool:
        """从持久化存储加载上下文"""
        try:
            if not data or "context" not in data:
                return False

            context = TaskContext.from_dict(data["context"])
            return await self.update_context(task_id, context)

        except (KeyError, AttributeError, TypeError):
            self.logger.exception("Failed to load context for task {task_id}: ")
            return False
