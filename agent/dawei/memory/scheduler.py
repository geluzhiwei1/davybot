# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Memory Extraction Scheduler
定时记忆提取调度器（每天0点执行）
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from dawei.core.datetime_compat import UTC
from pathlib import Path
from typing import Dict, Any, Optional

from dawei.memory.batch_extractor import BatchMemoryExtractor


class MemoryExtractionScheduler:
    """记忆提取调度器

    每天凌晨0点自动执行记忆提取任务
    使用asyncio.sleep实现精确定时

    Usage:
        scheduler = MemoryExtractionScheduler(
            workspace_path="/path/to/workspace",
            memory_graph=memory_graph,
            llm_service=llm_service
        )

        await scheduler.start()
        # ... 运行 ...
        await scheduler.stop()
    """

    def __init__(
        self,
        workspace_path: str,
        memory_graph,
        llm_service=None,
        extraction_hour: int = 0,  # 凌晨0点
        extraction_minute: int = 0,
    ):
        """初始化调度器

        Args:
            workspace_path: 工作空间路径
            memory_graph: MemoryGraph实例
            llm_service: LLM服务（可选）
            extraction_hour: 提取时间（小时，默认0）
            extraction_minute: 提取时间（分钟，默认0）
        """
        self.workspace_path = Path(workspace_path).absolute_path
        self.memory_graph = memory_graph
        self.llm_service = llm_service
        self.extraction_hour = extraction_hour
        self.extraction_minute = extraction_minute

        self.logger = logging.getLogger(__name__)
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # 批量提取器
        self.extractor = BatchMemoryExtractor(
            workspace_path=str(self.workspace_path),
            memory_graph=self.memory_graph,
            llm_service=self.llm_service,
        )

    async def start(self):
        """启动调度器"""
        if self._running:
            self.logger.warning("Memory extraction scheduler is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        self.logger.info(
            f"Memory extraction scheduler started (scheduled at {self.extraction_hour:02d}:{self.extraction_minute:02d})"
        )

    async def stop(self):
        """停止调度器"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self.logger.info("Memory extraction scheduler stopped")

    async def _scheduler_loop(self):
        """调度器主循环"""
        self.logger.info("Scheduler loop started")

        while self._running:
            try:
                # 计算下一次执行时间
                next_run = self._calculate_next_run_time()
                wait_seconds = (next_run - datetime.now(UTC)).total_seconds()

                self.logger.info(
                    f"Next memory extraction scheduled at: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"(in {wait_seconds/3600:.1f} hours)"
                )

                # 等待到执行时间
                try:
                    await asyncio.sleep(wait_seconds)
                except asyncio.CancelledError:
                    break

                # 检查是否仍在运行
                if not self._running:
                    break

                # 执行提取
                self.logger.info("Executing scheduled memory extraction...")
                result = await self.extractor.extract_yesterday()

                if result["success"]:
                    self.logger.info(
                        f"Scheduled extraction completed: "
                        f"{result['extracted_memories']} memories from "
                        f"{result['total_conversations']} conversations"
                    )
                else:
                    self.logger.error(
                        f"Scheduled extraction failed: {result.get('error', 'Unknown error')}"
                    )

            except Exception as e:
                self.logger.error(f"Scheduler loop error: {e}", exc_info=True)
                # 出错后等待1小时再试
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    break

        self.logger.info("Scheduler loop stopped")

    def _calculate_next_run_time(self) -> datetime:
        """计算下一次执行时间"""
        now = datetime.now(UTC)

        # 今天的执行时间
        target = now.replace(
            hour=self.extraction_hour,
            minute=self.extraction_minute,
            second=0,
            microsecond=0,
        )

        # 如果今天的执行时间已过，则设置为明天
        if now >= target:
            target = target + timedelta(days=1)

        return target

    async def trigger_now(self) -> Dict[str, Any]:
        """立即触发一次提取（手动触发）

        Returns:
            提取结果
        """
        self.logger.info("Manual memory extraction triggered")

        try:
            result = await self.extractor.extract_today()
            self.logger.info(
                f"Manual extraction completed: "
                f"{result['extracted_memories']} memories from "
                f"{result['total_conversations']} conversations"
            )
            return result
        except Exception as e:
            self.logger.error(f"Manual extraction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "extracted_memories": 0,
            }

    async def extract_from_date(
        self,
        target_date: str,
        extract_all: bool = False,
    ) -> Dict[str, Any]:
        """手动触发指定日期的提取

        Args:
            target_date: 目标日期 (格式: "2026-02-18")
            extract_all: 是否提取所有会话

        Returns:
            提取结果
        """
        self.logger.info(f"Manual extraction triggered for date: {target_date}")

        try:
            result = await self.extractor.extract_from_date(target_date, extract_all)
            self.logger.info(
                f"Manual extraction completed: "
                f"{result['extracted_memories']} memories from "
                f"{result['total_conversations']} conversations"
            )
            return result
        except Exception as e:
            self.logger.error(f"Manual extraction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "extracted_memories": 0,
            }

    def get_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        next_run = self._calculate_next_run_time() if self._running else None

        return {
            "running": self._running,
            "scheduled_time": f"{self.extraction_hour:02d}:{self.extraction_minute:02d}",
            "next_run": next_run.isoformat() if next_run else None,
            "workspace_path": str(self.workspace_path),
        }
