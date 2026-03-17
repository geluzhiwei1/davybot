# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Batch Memory Extractor
定时或手动从会话文件中批量提取记忆
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from dawei.core.datetime_compat import UTC
from pathlib import Path
from typing import List, Dict, Any, Optional

from dawei.memory.memory_graph import MemoryEntry, MemoryGraph, MemoryType


class BatchMemoryExtractor:
    """批量记忆提取器

    从会话文件中批量提取记忆，支持：
    1. 定时提取（每天0点提取前一天的所有会话）
    2. 手动提取（从指定日期的会话中提取）

    Usage:
        extractor = BatchMemoryExtractor(
            workspace_path="/path/to/workspace",
            memory_graph=memory_graph
        )

        # 提取指定日期的会话
        result = await extractor.extract_from_date("2026-02-18")

        # 提取昨天的所有会话
        result = await extractor.extract_yesterday()
    """

    def __init__(
        self,
        workspace_path: str,
        memory_graph: MemoryGraph,
        llm_service=None,
    ):
        """初始化批量记忆提取器

        Args:
            workspace_path: 工作空间路径
            memory_graph: MemoryGraph实例
            llm_service: LLM服务（可选，用于智能提取）
        """
        self.workspace_path = Path(workspace_path).resolve()
        self.memory_graph = memory_graph
        self.llm_service = llm_service
        self.logger = logging.getLogger(__name__)

        # 会话目录
        self.conversations_dir = self.workspace_path / ".dawei" / "conversations"

    async def extract_from_date(
        self,
        target_date: str,
        extract_all: bool = False,
    ) -> Dict[str, Any]:
        """从指定日期的会话中提取记忆

        Args:
            target_date: 目标日期 (格式: "2026-02-18")
            extract_all: 是否提取所有会话（False=仅提取未提取过的）

        Returns:
            提取结果字典
        """
        try:
            # 解析日期
            date_obj = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=UTC)
            date_start = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
            date_end = date_start + timedelta(days=1)

            self.logger.info(f"Extracting memories from {target_date}")

            # 获取指定日期的会话文件
            conversation_files = self._get_conversation_files_in_range(
                date_start, date_end
            )

            if not conversation_files:
                self.logger.info(f"No conversations found for {target_date}")
                return {
                    "success": True,
                    "date": target_date,
                    "total_conversations": 0,
                    "extracted_memories": 0,
                    "skipped": 0,
                }

            # 批量提取记忆
            total_memories = 0
            skipped = 0
            processed_files = []

            for conv_file in conversation_files:
                try:
                    # 检查是否已提取
                    if not extract_all and self._is_conversation_extracted(conv_file):
                        self.logger.debug(f"Skipping already extracted: {conv_file.name}")
                        skipped += 1
                        continue

                    # 从会话中提取记忆
                    memories = await self._extract_from_conversation_file(conv_file)

                    if memories:
                        # 保存到数据库
                        for memory in memories:
                            try:
                                await self.memory_graph.add_memory(memory)
                            except Exception as e:
                                self.logger.warning(f"Failed to add memory: {e}")

                        total_memories += len(memories)
                        processed_files.append(conv_file.name)

                        # 标记为已提取
                        self._mark_conversation_extracted(conv_file)

                except Exception as e:
                    self.logger.error(
                        f"Failed to extract from {conv_file.name}: {e}",
                        exc_info=True,
                    )
                    skipped += 1

            result = {
                "success": True,
                "date": target_date,
                "total_conversations": len(conversation_files),
                "processed_conversations": len(processed_files),
                "extracted_memories": total_memories,
                "skipped": skipped,
                "processed_files": processed_files,
            }

            self.logger.info(
                f"Extraction complete for {target_date}: "
                f"{total_memories} memories from {len(processed_files)} conversations"
            )

            return result

        except Exception as e:
            self.logger.error(f"Batch extraction failed: {e}", exc_info=True)
            return {
                "success": False,
                "date": target_date,
                "error": str(e),
                "extracted_memories": 0,
            }

    async def extract_yesterday(self) -> Dict[str, Any]:
        """提取昨天的所有会话记忆"""
        yesterday = datetime.now(UTC) - timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")
        return await self.extract_from_date(target_date, extract_all=False)

    async def extract_today(self) -> Dict[str, Any]:
        """提取今天的所有会话记忆"""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        return await self.extract_from_date(today, extract_all=True)

    async def extract_recent(
        self,
        days: int = 7,
        limit_per_day: int = 10,
    ) -> Dict[str, Any]:
        """提取最近几天的会话记忆

        Args:
            days: 提取最近几天的会话
            limit_per_day: 每天最多提取的会话数

        Returns:
            提取结果字典
        """
        total_memories = 0
        total_conversations = 0
        results_by_day = {}

        for i in range(days):
            date = datetime.now(UTC) - timedelta(days=i)
            target_date = date.strftime("%Y-%m-%d")

            result = await self.extract_from_date(target_date, extract_all=False)
            results_by_day[target_date] = result
            total_memories += result.get("extracted_memories", 0)
            total_conversations += result.get("total_conversations", 0)

        return {
            "success": True,
            "days": days,
            "total_conversations": total_conversations,
            "extracted_memories": total_memories,
            "results_by_day": results_by_day,
        }

    def _get_conversation_files_in_range(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Path]:
        """获取时间范围内的会话文件"""
        if not self.conversations_dir.exists():
            return []

        conversation_files = []

        for conv_file in self.conversations_dir.glob("*.json"):
            try:
                # 读取会话文件获取创建时间
                with open(conv_file, "r", encoding="utf-8") as f:
                    conv_data = json.load(f)

                created_at_str = conv_data.get("created_at")
                if not created_at_str:
                    continue

                # 解析创建时间
                if isinstance(created_at_str, str):
                    # 处理时区
                    if created_at_str.endswith("Z"):
                        created_at_str = created_at_str[:-1] + "+00:00"
                    created_at = datetime.fromisoformat(created_at_str)
                else:
                    continue

                # 检查是否在时间范围内
                if start_time <= created_at < end_time:
                    conversation_files.append(conv_file)

            except Exception as e:
                self.logger.warning(f"Failed to parse {conv_file.name}: {e}")
                continue

        # 按创建时间排序
        conversation_files.sort(key=lambda f: f.stat().st_mtime)

        return conversation_files

    async def _extract_from_conversation_file(
        self,
        conv_file: Path,
    ) -> List[MemoryEntry]:
        """从单个会话文件中提取记忆"""
        try:
            # 读取会话文件
            with open(conv_file, "r", encoding="utf-8") as f:
                conv_data = json.load(f)

            messages = conv_data.get("messages", [])
            if not messages:
                return []

            # 提取用户消息
            user_messages = [
                msg.get("content", "")
                for msg in messages
                if msg.get("role") == "user" and msg.get("content")
            ]

            if not user_messages:
                return []

            # 使用LLM提取记忆
            if self.llm_service:
                return await self._extract_with_llm(user_messages, conv_file)
            else:
                return await self._extract_with_rules(user_messages, conv_file)

        except Exception as e:
            self.logger.error(f"Failed to extract from {conv_file.name}: {e}")
            return []

    async def _extract_with_llm(
        self,
        user_messages: List[str],
        conv_file: Path,
    ) -> List[MemoryEntry]:
        """使用LLM提取记忆"""
        try:
            # 合并用户消息
            messages_text = "\n".join(
                [f"{i+1}. {msg}" for i, msg in enumerate(user_messages)]
            )

            extraction_prompt = f"""从以下对话中提取结构化的用户偏好、事实和策略。

格式：每行一个事实，格式为：[主体] [关系] [客体]

示例：
- User prefers Python
- User uses FastAPI框架
- User dislikes JavaScript
- User projects use PostgreSQL

对话内容：
{messages_text}

提取事实："""

            response = await self.llm_service.generate(
                messages=[{"role": "user", "content": extraction_prompt}],
                max_tokens=500,
                temperature=0.3,
            )

            if not response or not response.content:
                return []

            # 解析并创建记忆
            memories = []
            for line in response.content.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("-"):
                    line = line.lstrip("-").strip()

                parts = line.split(maxsplit=2)
                if len(parts) >= 3:
                    memory = MemoryEntry(
                        id=str(uuid.uuid4()),
                        subject=parts[0],
                        predicate=parts[1],
                        object=parts[2],
                        valid_start=datetime.now(UTC),
                        memory_type=self._infer_memory_type(parts[1]),
                        confidence=0.7,
                        energy=1.0,
                        keywords=self._extract_keywords(" ".join(parts)),
                        metadata={
                            "source": "batch_extraction",
                            "conversation_file": conv_file.name,
                            "extraction_date": datetime.now(UTC).isoformat(),
                        },
                    )

                    memories.append(memory)

            return memories

        except Exception as e:
            self.logger.error(f"LLM extraction failed: {e}")
            # 降级到规则提取
            return await self._extract_with_rules(user_messages, conv_file)

    async def _extract_with_rules(
        self,
        user_messages: List[str],
        conv_file: Path,
    ) -> List[MemoryEntry]:
        """使用规则提取记忆"""
        import re

        memories = []

        # 扩展的模式匹配
        patterns = {
            # 偏好类
            r"我喜欢(.+)": ("User", "prefers", MemoryType.PREFERENCE),
            r"我偏好(.+)": ("User", "prefers", MemoryType.PREFERENCE),
            r"我喜欢用(.+)": ("User", "prefers", MemoryType.PREFERENCE),
            r"我不喜欢(.+)": ("User", "dislikes", MemoryType.PREFERENCE),
            r"我不想用(.+)": ("User", "dislikes", MemoryType.PREFERENCE),

            # 工具/技术使用
            r"我使用(.+)": ("User", "uses", MemoryType.PROCEDURE),
            r"我用(.+)": ("User", "uses", MemoryType.PROCEDURE),
            r"使用@skill:(\w+)": ("User", "uses_skill", MemoryType.PROCEDURE),
            r"我的项目使用(.+)": ("Project", "uses", MemoryType.FACT),
            r"项目使用(.+)": ("Project", "uses", MemoryType.FACT),

            # 工作内容
            r"我在做(.+)": ("User", "works_on", MemoryType.CONTEXT),
            r"我在开发(.+)": ("User", "develops", MemoryType.CONTEXT),
            r"我正在(.+)": ("User", "doing", MemoryType.CONTEXT),
            r"帮我(.+)": ("User", "requests", MemoryType.CONTEXT),

            # 文档/知识
            r"把(.+)转为(.+)": ("User", "converts", MemoryType.PROCEDURE),
            r"保存到(.+)": ("User", "saves_to", MemoryType.PROCEDURE),
            r"关于(.+)的相关文档": ("User", "searches", MemoryType.CONTEXT),
        }

        for msg in user_messages:
            for pattern, (subject, predicate, mem_type) in patterns.items():
                matches = re.findall(pattern, msg)
                for match in matches:
                    # 如果match是元组（多个捕获组），合并它们
                    if isinstance(match, tuple):
                        object_text = " ".join(m.strip() for m in match if m.strip())
                    else:
                        object_text = match.strip()

                    # 跳过太短的对象
                    if len(object_text) < 2:
                        continue

                    memory = MemoryEntry(
                        id=str(uuid.uuid4()),
                        subject=subject,
                        predicate=predicate,
                        object=object_text,
                        valid_start=datetime.now(UTC),
                        memory_type=mem_type,
                        confidence=0.5,
                        energy=1.0,
                        keywords=self._extract_keywords(object_text),
                        metadata={
                            "source": "batch_extraction_rule",
                            "conversation_file": conv_file.name,
                            "extraction_date": datetime.now(UTC).isoformat(),
                        },
                    )
                    memories.append(memory)

        return memories

    def _infer_memory_type(self, predicate: str) -> MemoryType:
        """根据谓词推断记忆类型"""
        predicate_lower = predicate.lower()

        if any(w in predicate_lower for w in ["prefers", "likes", "loves", "wants", " dislikes"]):
            return MemoryType.PREFERENCE
        elif any(w in predicate_lower for w in ["uses", "requires", "needs"]):
            return MemoryType.PROCEDURE
        elif any(w in predicate_lower for w in ["learned", "discovered", "figured"]):
            return MemoryType.STRATEGY
        else:
            return MemoryType.FACT

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        import re

        keywords = []
        # 提取大写开头的词
        words = re.findall(r"\b[A-Z][a-z]+\b", text)
        keywords.extend(words)

        # 提取技术术语
        technical = re.findall(r"\b[A-Z]{2,}\b|\b\w+\.\w+\b", text)
        keywords.extend(technical)

        # 返回唯一的关键词，限制为5个
        return list(set(keywords))[:5]

    def _is_conversation_extracted(self, conv_file: Path) -> bool:
        """检查会话是否已提取过"""
        # 使用元数据文件记录已提取的会话
        metadata_file = self.conversations_dir / ".extraction_metadata.json"

        if not metadata_file.exists():
            return False

        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            extracted_files = metadata.get("extracted_files", [])
            return conv_file.name in extracted_files

        except Exception:
            return False

    def _mark_conversation_extracted(self, conv_file: Path):
        """标记会话为已提取"""
        metadata_file = self.conversations_dir / ".extraction_metadata.json"

        try:
            # 读取现有元数据
            if metadata_file.exists():
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            else:
                metadata = {"extracted_files": []}

            # 添加新文件
            if conv_file.name not in metadata["extracted_files"]:
                metadata["extracted_files"].append(conv_file.name)

            # 保存元数据
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

        except Exception as e:
            self.logger.warning(f"Failed to mark conversation as extracted: {e}")
