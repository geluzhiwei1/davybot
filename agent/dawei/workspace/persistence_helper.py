# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace持久化辅助器

负责工作区的持久化辅助功能，包括自动保存、重试机制、失败告警等
"""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WorkspacePersistenceHelper:
    """工作区持久化辅助器

    职责：
    - 自动保存机制管理
    - 持久化重试逻辑
    - 持久化失败告警
    - 持久化失败日志管理
    """

    def __init__(self, workspace_path: Path, auto_save_interval: int = 30, event_bus=None):
        """初始化持久化辅助器

        Args:
            workspace_path: 工作区路径
            auto_save_interval: 自动保存间隔（秒）
            event_bus: 事件总线（可选）

        """
        self.workspace_path = Path(workspace_path).resolve()
        self.absolute_path = str(self.workspace_path)
        self.event_bus = event_bus

        # 自动保存机制
        self._auto_save_task: asyncio.Task | None = None
        self._auto_save_interval = auto_save_interval
        self._auto_save_enabled = True
        self._last_message_count = 0

        # 持久化重试机制
        self._max_retry_attempts = 3
        self._retry_base_delay = 1.0
        self._retry_max_delay = 30.0
        self._retry_backoff_multiplier = 2.0

        # 工作区信息（由外部注入，用于告警）
        self.workspace_info = None
        self.uuid = None

        # 保存函数（由外部注入）
        self.save_conversation_func = None

        # 当前对话（由外部注入）
        self.current_conversation = None

        # 初始化状态
        self._initialized = False

        logger.info(f"WorkspacePersistenceHelper created for: {self.absolute_path}")

    # ==================== 初始化方法 ====================

    async def initialize(self):
        """初始化持久化辅助器"""
        self._initialized = True
        logger.info("WorkspacePersistenceHelper initialized")

    async def shutdown(self):
        """关闭持久化辅助器"""
        await self.stop_auto_save()
        self._initialized = False
        logger.info("WorkspacePersistenceHelper shutdown")

    # ==================== 自动保存机制 ====================

    async def start_auto_save(self):
        """启动对话自动保存任务"""
        if not self._auto_save_enabled:
            logger.info("Auto-save is disabled")
            return

        if self._auto_save_task is not None:
            logger.warning("Auto-save task is already running")
            return

        logger.info(f"Starting auto-save task (interval: {self._auto_save_interval}s)")
        self._auto_save_task = asyncio.create_task(self._auto_save_conversation_loop())
        logger.info("Auto-save task started")

    async def stop_auto_save(self):
        """停止对话自动保存任务"""
        if self._auto_save_task is None:
            return

        logger.info("Stopping auto-save task...")

        # 取消任务
        self._auto_save_task.cancel()

        try:
            await self._auto_save_task
        except asyncio.CancelledError:
            logger.info("Auto-save task cancelled")

        self._auto_save_task = None
        logger.info("Auto-save task stopped")

    async def _auto_save_conversation_loop(self):
        """自动保存对话循环"""
        try:
            while self._initialized:
                await asyncio.sleep(self._auto_save_interval)

                # 检查是否需要保存
                if self.current_conversation and self._should_auto_save_conversation():
                    try:
                        logger.debug("Auto-saving conversation...")

                        if self.save_conversation_func:
                            success = await self.save_conversation_func()
                        else:
                            logger.warning("save_conversation_func not set, auto-save skipped")
                            success = False

                        if success and self.current_conversation:
                            self._last_message_count = self.current_conversation.message_count
                            logger.debug(
                                f"Conversation auto-saved ({self.current_conversation.message_count} messages)",
                            )
                        else:
                            logger.warning("Conversation auto-save failed")

                    except Exception as e:
                        logger.error(f"Auto-save conversation error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("Auto-save loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Auto-save loop error: {e}", exc_info=True)

    def _should_auto_save_conversation(self) -> bool:
        """判断是否应该自动保存对话"""
        if not self.current_conversation:
            return False

        # 检查消息数量是否增加
        current_count = self.current_conversation.message_count
        return current_count > self._last_message_count

    async def set_auto_save_interval(self, interval_seconds: int):
        """设置自动保存间隔

        Args:
            interval_seconds: 保存间隔(秒)

        """
        try:
            if not isinstance(interval_seconds, int):
                raise ValueError("interval_seconds must be an integer")

            if interval_seconds < 5:
                logger.warning("Auto-save interval too short, using minimum 5 seconds")
                interval_seconds = 5

            old_interval = self._auto_save_interval
            self._auto_save_interval = interval_seconds
            logger.info(f"Auto-save interval changed: {old_interval}s -> {interval_seconds}s")

            # 重启自动保存任务
            if self._auto_save_task is not None:
                try:
                    await self.stop_auto_save()
                    await self.start_auto_save()
                except Exception as e:
                    logger.error(f"Failed to restart auto-save task: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Failed to set auto-save interval: {e}", exc_info=True)
            raise

    def enable_auto_save(self):
        """启用自动保存"""
        if not self._auto_save_enabled:
            self._auto_save_enabled = True
            logger.info("Auto-save enabled")

    def disable_auto_save(self):
        """禁用自动保存"""
        if self._auto_save_enabled:
            self._auto_save_enabled = False
            logger.info("Auto-save disabled")

    # ==================== 重试机制 ====================

    async def save_with_retry(
        self,
        save_func: Callable,
        resource_type: str,
        *args,
        **kwargs,
    ) -> bool:
        """带重试的持久化保存

        Args:
            save_func: 保存函数
            resource_type: 资源类型(用于日志)
            *args: 传递给保存函数的位置参数
            **kwargs: 传递给保存函数的关键字参数

        Returns:
            bool: 是否保存成功

        """
        if not callable(save_func):
            raise ValueError("save_func must be callable")

        if not isinstance(resource_type, str):
            raise ValueError("resource_type must be a string")

        last_exception = None

        for attempt in range(self._max_retry_attempts):
            try:
                # 尝试保存
                result = await save_func(*args, **kwargs)

                if result:
                    if attempt > 0:
                        logger.info(f"{resource_type} saved successfully after {attempt} retries")
                    return True
                # 保存失败但没抛出异常
                last_exception = Exception("Save function returned False")
                logger.warning(
                    f"{resource_type} save attempt {attempt + 1}/{self._max_retry_attempts} failed",
                )

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"{resource_type} save attempt {attempt + 1}/{self._max_retry_attempts} failed: {e}",
                    exc_info=True,
                )

            # 如果不是最后一次尝试,等待后重试
            if attempt < self._max_retry_attempts - 1:
                try:
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(f"Retrying {resource_type} save in {delay:.1f} seconds...")
                    await asyncio.sleep(delay)
                except Exception as sleep_error:
                    logger.warning(f"Failed to wait before retry: {sleep_error}", exc_info=True)
                    break

        # 所有重试都失败了
        if last_exception is None:
            last_exception = Exception("Unknown error occurred during save")

        logger.error(
            f"{resource_type} save failed after {self._max_retry_attempts} attempts: {last_exception}",
        )

        # 发送持久化失败告警
        try:
            await self._alert_persistence_failure(
                resource_type,
                f"Failed after {self._max_retry_attempts} retries: {last_exception!s}",
            )
        except Exception as alert_error:
            logger.error(
                f"Failed to send persistence failure alert: {alert_error}",
                exc_info=True,
            )

        return False

    def _calculate_retry_delay(self, attempt: int) -> float:
        """计算重试延迟(指数退避)

        Args:
            attempt: 当前尝试次数(从0开始)

        Returns:
            float: 延迟秒数

        """
        if not isinstance(attempt, int):
            raise ValueError("attempt must be an integer")

        if attempt < 0:
            raise ValueError("attempt must be non-negative")

        # 指数退避: delay = base_delay * (multiplier ^ attempt)
        try:
            delay = self._retry_base_delay * (self._retry_backoff_multiplier**attempt)
        except Exception as e:
            logger.error(f"Failed to calculate retry delay: {e}", exc_info=True)
            return self._retry_base_delay

        # 限制最大延迟
        return min(delay, self._retry_max_delay)

    # ==================== 失败告警机制 ====================

    async def _alert_persistence_failure(self, resource_type: str, error_message: str, **kwargs):
        """发送持久化失败告警

        Args:
            resource_type: 资源类型 (workspace_info, conversation, task_graph, checkpoint)
            error_message: 错误信息
            **kwargs: 额外的上下文信息 (conversation_id, task_graph_id, checkpoint_id等)

        """
        try:
            if not isinstance(resource_type, str):
                raise ValueError("resource_type must be a string")

            if not isinstance(error_message, str):
                raise ValueError("error_message must be a string")

            # 构建告警数据
            timestamp = datetime.now(timezone.utc).isoformat()
            workspace_id = self.workspace_info.id if self.workspace_info else self.uuid

            if not workspace_id:
                logger.warning("No workspace_id available for persistence failure alert")

            alert_data = {
                "alert_type": "persistence_failure",
                "resource_type": resource_type,
                "error_message": error_message,
                "timestamp": timestamp,
                "workspace_path": self.absolute_path,
                "workspace_id": workspace_id,
                **kwargs,
            }

            # 1. 记录到错误日志
            logger.error(
                f"[PERSISTENCE_FAILURE] {resource_type}: {error_message}",
                extra={"alert_data": alert_data},
            )

            # 2. 发送到事件总线 (如果其他组件需要监听)
            if self.event_bus:
                try:
                    await self.event_bus.emit("persistence_failure", alert_data)
                except Exception as e:
                    logger.warning(f"Failed to emit persistence_failure event: {e}", exc_info=True)

            # 3. 保存到持久化失败日志文件
            try:
                await self._log_persistence_failure(alert_data)
            except Exception as log_error:
                logger.error(f"Failed to log persistence failure: {log_error}", exc_info=True)

        except Exception as e:
            logger.error(f"Failed to send persistence failure alert: {e}", exc_info=True)

    async def _log_persistence_failure(self, alert_data: dict[str, Any]):
        """将持久化失败记录到日志文件

        Args:
            alert_data: 告警数据

        """
        try:
            # 创建持久化失败日志目录
            failure_log_dir = self.workspace_path / ".dawei" / "persistence_failures"
            failure_log_dir.mkdir(parents=True, exist_ok=True)

            # 生成日志文件名
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
            log_file = failure_log_dir / f"failures_{timestamp}.jsonl"

            # 追加写入日志 (JSONL格式)
            with Path(log_file, "a").open(encoding="utf-8") as f:
                f.write(json.dumps(alert_data, ensure_ascii=False) + "\n")

            logger.debug(f"Persistence failure logged to {log_file}")

        except Exception as e:
            logger.warning(f"Failed to log persistence failure to file: {e}", exc_info=True)

    async def get_persistence_failures(
        self,
        limit: int = 100,
        resource_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取持久化失败记录

        Args:
            limit: 最大返回数量
            resource_type: 资源类型过滤(可选)

        Returns:
            List[Dict[str, Any]]: 失败记录列表

        Raises:
            OSError: 如果文件系统操作失败
            json.JSONDecodeError: 如果日志文件格式无效

        """
        try:
            if not isinstance(limit, int):
                raise ValueError("limit must be an integer")

            if limit < 0:
                raise ValueError("limit must be non-negative")

            if limit > 10000:  # 合理的上限
                logger.warning(f"Limit {limit} is very large, consider using a smaller value")
                limit = 10000

            if resource_type is not None and not isinstance(resource_type, str):
                raise ValueError("resource_type must be a string if provided")

            failure_log_dir = self.workspace_path / ".dawei" / "persistence_failures"

            if not failure_log_dir.exists():
                return []

            # 直接操作，任何错误都会抛出异常（fail-fast）
            failures = []
            for log_file in sorted(failure_log_dir.glob("failures_*.jsonl"), reverse=True):
                try:
                    with Path(log_file).open(encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue

                            record = json.loads(line)

                            # 应用资源类型过滤
                            if resource_type is None or record.get("resource_type") == resource_type:
                                failures.append(record)

                            # 达到限制数量
                            if len(failures) >= limit:
                                break

                    if len(failures) >= limit:
                        break

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to decode JSON from {log_file}: {e}", exc_info=True)
                    continue
                except Exception as e:
                    logger.warning(f"Failed to read {log_file}: {e}", exc_info=True)
                    continue

            return failures[:limit]

        except Exception as e:
            logger.error(f"Failed to get persistence failures: {e}", exc_info=True)
            raise

    def clear_persistence_failures(self) -> None:
        """清除所有持久化失败记录

        Raises:
            OSError: 如果文件系统操作失败

        """
        try:
            failure_log_dir = self.workspace_path / ".dawei" / "persistence_failures"

            if not failure_log_dir.exists():
                logger.info("No persistence failure logs to clear")
                return

            # 检查是否是目录
            if not failure_log_dir.is_dir():
                logger.warning(f"Failure log path is not a directory: {failure_log_dir}")
                return

            # 统计删除的文件数量
            deleted_count = 0

            # 直接操作，任何错误都会抛出异常（fail-fast）
            for log_file in failure_log_dir.glob("*.jsonl"):
                try:
                    log_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete {log_file}: {e}", exc_info=True)
                    raise

            if deleted_count > 0:
                logger.info(f"Cleared {deleted_count} persistence failure log(s)")
            else:
                logger.info("No persistence failure logs to clear")

        except Exception as e:
            logger.error(f"Failed to clear persistence failure logs: {e}", exc_info=True)
            raise
