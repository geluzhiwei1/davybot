# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""对话-记忆集成模块

将对话压缩与记忆系统结合，实现更智能的长对话处理：

1. 从压缩消息中提取结构化记忆存入MemoryGraph
2. 基于当前查询检索相关记忆
3. 将检索到的记忆注入上下文
"""

import logging
from datetime import datetime, timezone
from typing import Any

from .conversation_compressor import CompressionStats

logger = logging.getLogger(__name__)


class ConversationMemoryIntegration:
    """对话-记忆集成器

    负责在对话压缩和记忆系统之间建立连接，实现：
    - 自动提取和存储对话记忆
    - 智能检索相关记忆
    - 记忆注入到上下文
    """

    def __init__(
        self,
        memory_graph=None,
        virtual_context=None,
        auto_extract: bool = True,
        auto_store: bool = True,
    ):
        """初始化对话-记忆集成器

        Args:
            memory_graph: MemoryGraph实例
            virtual_context: VirtualContextManager实例
            auto_extract: 是否自动提取记忆
            auto_store: 是否自动存储记忆

        """
        self.memory_graph = memory_graph
        self.virtual_context = virtual_context
        self.auto_extract = auto_extract
        self.auto_store = auto_store

        self.logger = logging.getLogger(__name__)

    async def extract_memories_from_compression(
        self,
        original_messages: list[dict[str, Any]],
        compressed_messages: list[dict[str, Any]],
        _stats: CompressionStats,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """从压缩的消息中提取记忆

        提取类型：
        1. 事实记忆 - 用户提及的事实、偏好
        2. 策略记忆 - 解决方案、方法
        3. 情景记忆 - 重要的交互事件

        Args:
            original_messages: 原始消息列表
            compressed_messages: 压缩后的消息列表
            stats: 压缩统计信息
            session_id: 会话ID

        Returns:
            提取的记忆列表

        """
        if not self.memory_graph or not self.auto_extract:
            return []

        memories = []

        # 找出被压缩掉的消息
        compressed_indices = set()
        for msg in compressed_messages:
            # 检查是否有原始索引标记
            metadata = msg.get("metadata", {})
            if isinstance(metadata, dict) and "original_index" in metadata:
                compressed_indices.add(metadata["original_index"])

        # 提取被压缩消息中的记忆
        for idx, msg in enumerate(original_messages):
            if idx in compressed_indices:
                continue

            content = msg.get("content", "")
            role = msg.get("role", "")

            # 只从用户和助手消息中提取
            if role not in ["user", "assistant"]:
                continue

            # 提取不同类型的记忆
            extracted = await self._extract_facts(content, role, session_id)
            memories.extend(extracted)

            extracted = await self._extract_strategies(content, role, session_id)
            memories.extend(extracted)

            extracted = await self._extract_episodic(content, role, session_id, idx)
            memories.extend(extracted)

        # 自动存储记忆
        if self.auto_store and memories:
            await self._store_memories(memories, session_id)

        self.logger.info(f"Extracted {len(memories)} memories from compressed conversation")
        return memories

    async def _extract_facts(
        self,
        content: str,
        role: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """提取事实记忆

        识别用户陈述的事实、偏好等信息。

        规则：
        - "我xxx" 表达用户信息
        - "xxx是yyy" 表达事实
        - "我喜欢xxx" 表达偏好
        """
        if not isinstance(content, str):
            return []

        memories = []
        content_lower = content.lower()

        # 简单模式匹配（实际应用中可以使用LLM辅助提取）
        fact_patterns = [
            ("用户偏好", ["我喜欢", "我偏好", "我倾向", "我prefer"]),
            ("用户信息", ["我是", "我的工作", "我的项目"]),
            ("项目信息", ["项目是", "这个项目", "我们的产品"]),
        ]

        for category, patterns in fact_patterns:
            for pattern in patterns:
                if pattern in content_lower:
                    # 提取句子
                    sentences = content.split("。")
                    for sentence in sentences:
                        if pattern in sentence.lower():
                            memories.append(
                                {
                                    "type": "fact",
                                    "category": category,
                                    "subject": role,
                                    "predicate": category,
                                    "object": sentence.strip()[:200],  # 限制长度
                                    "confidence": 0.7,
                                    "energy": 1.0,
                                    "keywords": self._extract_keywords(sentence),
                                    "metadata": {
                                        "source": "conversation",
                                        "session_id": session_id,
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                    },
                                },
                            )

        return memories

    async def _extract_strategies(
        self,
        content: str,
        role: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """提取策略记忆

        识别解决方案、方法、步骤等。

        规则：
        - "第一步xxx"、"然后xxx" 表示步骤
        - "解决方法是xxx"、"可以通过xxx" 表示方案
        - "建议xxx"、"推荐xxx" 表示建议
        """
        if not isinstance(content, str) or role != "assistant":
            return []

        memories = []
        content_lower = content.lower()

        strategy_patterns = [
            "第一步",
            "首先",
            "然后",
            "接着",
            "最后",
            "解决方法",
            "可以通过",
            "建议",
            "推荐",
            "实现方法",
            "操作步骤",
            "执行流程",
        ]

        for pattern in strategy_patterns:
            if pattern in content_lower:
                # 提取包含该模式的段落
                paragraphs = content.split("\n\n")
                for para in paragraphs:
                    if pattern in para.lower():
                        memories.append(
                            {
                                "type": "strategy",
                                "subject": "solution",
                                "predicate": pattern,
                                "object": para.strip()[:300],
                                "confidence": 0.6,
                                "energy": 0.9,
                                "keywords": self._extract_keywords(para),
                                "metadata": {
                                    "source": "conversation",
                                    "session_id": session_id,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                },
                            },
                        )
                break  # 避免重复

        return memories

    async def _extract_episodic(
        self,
        content: str,
        _role: str,
        session_id: str,
        message_index: int,
    ) -> list[dict[str, Any]]:
        """提取情景记忆

        记录重要的交互事件。

        规则：
        - 工具调用
        - 错误发生
        - 任务完成
        - 模式切换
        """
        memories = []

        # 检查特殊事件
        metadata = content.get("metadata", {}) if isinstance(content, dict) else {}

        # 工具调用
        if "tool_calls" in metadata or "tool_calls" in str(content):
            memories.append(
                {
                    "type": "episodic",
                    "subject": "action",
                    "predicate": "tool_called",
                    "object": f"Tools were called at message {message_index}",
                    "confidence": 0.9,
                    "energy": 0.8,
                    "keywords": ["tool", "call", "action"],
                    "metadata": {
                        "source": "conversation",
                        "session_id": session_id,
                        "message_index": message_index,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )

        # 错误
        content_str = str(content).lower()
        error_keywords = ["error", "exception", "failed", "failure"]
        if any(kw in content_str for kw in error_keywords):
            memories.append(
                {
                    "type": "episodic",
                    "subject": "event",
                    "predicate": "error_occurred",
                    "object": f"Error encountered at message {message_index}",
                    "confidence": 0.8,
                    "energy": 0.7,
                    "keywords": ["error", "exception", "failed"],
                    "metadata": {
                        "source": "conversation",
                        "session_id": session_id,
                        "message_index": message_index,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )

        return memories

    def _extract_keywords(self, text: str) -> list[str]:
        """提取关键词

        简单的关键词提取实现
        """
        if not isinstance(text, str):
            return []

        # 移除标点符号
        import re

        text = re.sub(r"[^\w\s]", " ", text)

        # 分词
        words = text.split()

        # 过滤常见停用词
        stopwords = {
            "的",
            "是",
            "在",
            "了",
            "和",
            "the",
            "is",
            "a",
            "an",
            "and",
            "or",
            "but",
        }
        keywords = [w for w in words if len(w) > 2 and w.lower() not in stopwords]

        return keywords[:10]  # 最多10个关键词

    async def _store_memories(self, memories: list[dict[str, Any]], _session_id: str):
        """存储记忆到MemoryGraph

        Args:
            memories: 记忆列表
            session_id: 会话ID

        """
        if not self.memory_graph:
            return

        from dawei.memory.memory_graph import MemoryEntry, MemoryType

        for mem in memories:
            try:
                memory = MemoryEntry(
                    id=str(datetime.now(timezone.utc).timestamp()),
                    subject=mem["subject"],
                    predicate=mem["predicate"],
                    object=mem["object"],
                    valid_start=datetime.now(timezone.utc),
                    memory_type=MemoryType(mem["type"]),
                    confidence=mem["confidence"],
                    energy=mem["energy"],
                    keywords=mem["keywords"],
                    metadata=mem["metadata"],
                )

                await self.memory_graph.add_memory(memory)
            except Exception as e:
                self.logger.warning(f"Failed to store memory: {e}")

    async def retrieve_relevant_memories(
        self,
        query: str,
        _session_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """检索相关记忆

        Args:
            query: 查询文本
            session_id: 会话ID
            limit: 最大返回数量

        Returns:
            相关记忆列表

        """
        if not self.memory_graph:
            return []

        try:
            # 关键词搜索
            memories = await self.memory_graph.search_memories(query, limit=limit)

            # 转换为更友好的格式
            results = []
            for mem in memories[:limit]:
                results.append(
                    {
                        "subject": mem.subject,
                        "predicate": mem.predicate,
                        "object": mem.object,
                        "type": mem.memory_type.value,
                        "confidence": mem.confidence,
                        "energy": mem.energy,
                        "created_at": mem.valid_start.isoformat(),
                    },
                )

            return results

        except Exception:
            self.logger.exception("Failed to retrieve memories: ")
            return []

    async def inject_memories_to_context(
        self,
        messages: list[dict[str, Any]],
        query: str,
        session_id: str,
        max_memories: int = 5,
    ) -> list[dict[str, Any]]:
        """将相关记忆注入到上下文

        在系统提示后添加检索到的记忆。

        Args:
            messages: 当前消息列表
            query: 当前查询
            session_id: 会话ID
            max_memories: 最大注入记忆数

        Returns:
            注入记忆后的消息列表

        """
        # 检索相关记忆
        memories = await self.retrieve_relevant_memories(query, session_id, max_memories)

        if not memories:
            return messages

        # 构建记忆上下文
        memory_context = self._format_memories(memories)

        # 注入到消息列表（在系统提示后）
        result = []
        for i, msg in enumerate(messages):
            result.append(msg)
            # 在第一个系统消息后插入记忆
            if i == 0 and msg.get("role") == "system" and memory_context:
                result.append(
                    {
                        "role": "system",
                        "content": memory_context,
                        "metadata": {"is_memory_injection": True},
                    },
                )

        self.logger.info(f"Injected {len(memories)} memories into context")
        return result

    def _format_memories(self, memories: list[dict[str, Any]]) -> str:
        """格式化记忆为文本

        Args:
            memories: 记忆列表

        Returns:
            格式化的记忆文本

        """
        if not memories:
            return ""

        lines = ["[Relevant Memories from Previous Conversations]"]

        for mem in memories:
            mem_type = mem.get("type", "fact")
            subject = mem.get("subject", "")
            predicate = mem.get("predicate", "")
            obj = mem.get("object", "")

            if mem_type == "fact":
                lines.append(f"- Fact: {subject} {predicate} {obj}")
            elif mem_type == "strategy":
                lines.append(f"- Strategy: {obj[:150]}...")
            elif mem_type == "episodic":
                lines.append(f"- Event: {obj[:100]}...")

        return "\n".join(lines)

    async def create_context_pages(
        self,
        messages: list[dict[str, Any]],
        session_id: str,
    ) -> list[str]:
        """将对话历史创建为上下文页面

        用于VirtualContextManager的分页管理。

        Args:
            messages: 消息列表
            session_id: 会话ID

        Returns:
            创建的页面ID列表

        """
        if not self.virtual_context:
            return []

        page_ids = []

        # 将消息分组创建页面
        page_size = 20  # 每页20条消息
        for i in range(0, len(messages), page_size):
            page_messages = messages[i : i + page_size]

            # 生成页面内容
            content = self._format_page_content(page_messages, i)
            summary = self._generate_page_summary(page_messages, i)

            try:
                page_id = await self.virtual_context.create_page(
                    session_id=session_id,
                    content=content,
                    summary=summary,
                    source_type="conversation",
                    source_ref=f"page_{i // page_size}",
                )
                page_ids.append(page_id)
            except Exception as e:
                self.logger.warning(f"Failed to create context page: {e}")

        self.logger.info(f"Created {len(page_ids)} context pages for {len(messages)} messages")
        return page_ids

    def _format_page_content(self, messages: list[dict[str, Any]], start_index: int) -> str:
        """格式化页面内容"""
        lines = [f"Conversation Page {start_index // 20 + 1}"]

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"],
                )

            lines.append(f"\n[{role.upper()}]")
            lines.append(str(content)[:500])  # 限制长度

        return "\n".join(lines)

    def _generate_page_summary(self, messages: list[dict[str, Any]], start_index: int) -> str:
        """生成页面摘要"""
        role_counts = {}
        for msg in messages:
            role = msg.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        summary_parts = [f"Page {start_index // 20 + 1}:"]
        for role, count in role_counts.items():
            summary_parts.append(f"{count} {role}")

        # 提取关键词
        all_content = " ".join([str(msg.get("content", "")) for msg in messages])
        keywords = self._extract_keywords(all_content)[:5]

        if keywords:
            summary_parts.append(f"Topics: {', '.join(keywords)}")

        return ", ".join(summary_parts)

    async def load_relevant_pages(
        self,
        query: str,
        session_id: str,
        current_tokens: int = 0,
        max_tokens: int = 10000,
    ) -> str:
        """加载相关的上下文页面

        Args:
            query: 查询文本
            session_id: 会话ID
            current_tokens: 当前token数
            max_tokens: 最大token数

        Returns:
            加载的页面内容

        """
        if not self.virtual_context:
            return ""

        try:
            page_ids = await self.virtual_context.page_in(
                session_id=session_id,
                query=query,
                top_k=3,
                current_tokens=current_tokens,
                max_tokens=max_tokens,
            )

            if page_ids:
                return self.virtual_context.get_active_context()

        except Exception:
            self.logger.exception("Failed to load relevant pages: ")

        return ""

    def get_stats(self) -> dict[str, Any]:
        """获取集成统计信息"""
        return {
            "memory_graph_enabled": self.memory_graph is not None,
            "virtual_context_enabled": self.virtual_context is not None,
            "auto_extract": self.auto_extract,
            "auto_store": self.auto_store,
        }
