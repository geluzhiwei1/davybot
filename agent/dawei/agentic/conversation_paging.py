# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""对话分页管理器 - 虚拟上下文管理 (Phase 3)

实现MemGPT风格的对话分页，将对话历史切分为页面存储，
基于查询加载相关页面，集成VirtualContextManager的LRU机制。
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import Any

from .conversation_compressor import ConversationCompressor

logger = logging.getLogger(__name__)


@dataclass
class ConversationPage:
    """对话页面"""

    page_id: str
    session_id: str
    start_index: int
    end_index: int
    message_count: int
    content: str
    summary: str
    tokens: int

    # 元数据
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_accessed: float = field(default_factory=lambda: datetime.now(UTC).timestamp())
    access_count: int = 0
    keywords: list[str] = field(default_factory=list)

    @property
    def lru_score(self) -> float:
        """LRU淘汰分数：越高越容易被淘汰"""
        age_hours = (datetime.now(UTC).timestamp() - self.last_accessed) / 3600
        access_factor = 1 / (self.access_count + 1)
        return age_hours * access_factor


class ConversationPagingManager:
    """对话分页管理器

    负责将长对话切分为页面存储，实现：
    1. 对话分页存储
    2. 基于查询的相关页面加载
    3. LRU淘汰策略
    4. 与VirtualContextManager集成
    """

    def __init__(
        self,
        virtual_context_manager=None,
        page_size: int = 20,
        max_active_pages: int = 5,
        compressor: ConversationCompressor | None = None,
    ):
        """初始化对话分页管理器

        Args:
            virtual_context_manager: VirtualContextManager实例
            page_size: 每页消息数量
            max_active_pages: 最大活动页面数
            compressor: 可选的对话压缩器

        """
        self.virtual_context = virtual_context_manager
        self.page_size = page_size
        self.max_active_pages = max_active_pages
        self.compressor = compressor

        # 页面存储
        self.pages: dict[str, ConversationPage] = {}
        self.session_pages: dict[str, list[str]] = {}  # session_id -> [page_ids]

        self.logger = logging.getLogger(__name__)

    async def create_pages(self, messages: list[dict[str, Any]], session_id: str) -> list[str]:
        """将对话切分为页面

        Args:
            messages: 消息列表
            session_id: 会话ID

        Returns:
            创建的页面ID列表

        """
        page_ids = []
        total_messages = len(messages)

        for i in range(0, total_messages, self.page_size):
            end_idx = min(i + self.page_size, total_messages)
            page_messages = messages[i:end_idx]

            # 生成页面内容
            content = self._format_page_content(page_messages, i, session_id)
            summary = self._generate_page_summary(page_messages, i, session_id)

            # 估算token
            tokens = self._estimate_tokens(content)

            # 提取关键词
            keywords = self._extract_keywords(page_messages)

            # 创建页面
            page = ConversationPage(
                page_id=str(uuid.uuid4()),
                session_id=session_id,
                start_index=i,
                end_index=end_idx,
                message_count=len(page_messages),
                content=content,
                summary=summary,
                tokens=tokens,
                keywords=keywords,
            )

            self.pages[page.page_id] = page

            # 更新会话页面索引
            if session_id not in self.session_pages:
                self.session_pages[session_id] = []
            self.session_pages[session_id].append(page.page_id)

            page_ids.append(page.page_id)

            # 如果有VirtualContextManager，同步创建页面
            if self.virtual_context:
                try:
                    await self.virtual_context.create_page(
                        session_id=session_id,
                        content=content,
                        summary=summary,
                        source_type="conversation",
                        source_ref=f"page_{i // self.page_size}",
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to create virtual context page: {e}")

        self.logger.info(
            f"Created {len(page_ids)} conversation pages ({total_messages} messages, session={session_id})",
        )

        return page_ids

    def _format_page_content(
        self,
        messages: list[dict[str, Any]],
        start_index: int,
        session_id: str,
    ) -> str:
        """格式化页面内容"""
        lines = [
            f"# Conversation Page {start_index // self.page_size + 1}",
            f"Session: {session_id}",
            f"Messages: {start_index + 1}-{start_index + len(messages)}",
            "",
        ]

        for i, msg in enumerate(messages):
            msg_idx = start_index + i
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # 处理多模态内容
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif isinstance(item, dict) and item.get("type") == "image_url":
                        text_parts.append("[Image]")
                content = " ".join(text_parts)

            lines.append(f"## [{role.upper()}] Message {msg_idx + 1}")
            lines.append(str(content)[:500])  # 限制长度
            lines.append("")

        return "\n".join(lines)

    def _generate_page_summary(
        self,
        messages: list[dict[str, Any]],
        start_index: int,
        _session_id: str,
    ) -> str:
        """生成页面摘要"""
        # 统计角色分布
        role_counts = {}
        for msg in messages:
            role = msg.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        parts = [
            f"Page {start_index // self.page_size + 1} (messages {start_index + 1}-{start_index + len(messages)}): ",
        ]

        # 添加角色统计
        role_str = ", ".join([f"{count} {role}" for role, count in role_counts.items()])
        parts.append(role_str)

        # 提取关键词
        keywords = self._extract_keywords(messages)
        if keywords:
            parts.append(f"Topics: {', '.join(keywords[:5])}")

        return ", ".join(parts)

    def _estimate_tokens(self, text: str) -> int:
        """估算token数"""
        if self.compressor:
            from dawei.agentic.context_manager import TokenEstimator

            return TokenEstimator.estimate(text)
        return len(text) // 4  # 简单估算

    def _extract_keywords(self, messages: list[dict[str, Any]]) -> list[str]:
        """提取关键词"""
        import re

        all_text = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"],
                )
            all_text.append(str(content))

        text = " ".join(all_text)

        # 移除标点
        text = re.sub(r"[^\w\s]", " ", text)
        words = text.split()

        # 过滤停用词
        stopwords = {
            "the",
            "is",
            "a",
            "an",
            "and",
            "or",
            "but",
            "的",
            "是",
            "在",
            "了",
            "和",
            "这",
            "那",
        }

        keywords = [w for w in words if len(w) > 2 and w.lower() not in stopwords]

        # 统计频率
        freq = {}
        for kw in keywords:
            freq[kw] = freq.get(kw, 0) + 1

        # 返回高频词
        sorted_kw = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [kw for kw, _ in sorted_kw[:10]]

    async def load_relevant_pages(
        self,
        query: str,
        session_id: str,
        top_k: int = 3,
        current_tokens: int = 0,
        max_tokens: int = 10000,
    ) -> list[ConversationPage]:
        """加载相关页面

        基于查询关键词匹配和LRU策略选择相关页面。

        Args:
            query: 查询文本
            session_id: 会话ID
            top_k: 返回的页面数量
            current_tokens: 当前token数
            max_tokens: 最大token数

        Returns:
            加载的页面列表

        """
        if session_id not in self.session_pages:
            return []

        # 获取会话的所有页面
        page_ids = self.session_pages[session_id]
        candidates = [self.pages[pid] for pid in page_ids if pid in self.pages]

        # 计算相关性分数
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored_pages = []
        for page in candidates:
            # 关键词匹配分数
            content_lower = page.content.lower()
            summary_lower = page.summary.lower()

            keyword_score = sum(1 for word in query_words if word in content_lower)
            keyword_score += sum(1 for word in query_words if word in summary_lower) * 2

            # LRU分数（访问次数多的优先）
            lru_bonus = page.access_count * 0.1

            total_score = keyword_score + lru_bonus

            scored_pages.append((total_score, page))

        # 按分数排序
        scored_pages.sort(key=lambda x: x[0], reverse=True)

        # 选择top页面，考虑token限制
        loaded_pages = []
        used_tokens = current_tokens

        for _score, page in scored_pages[: top_k * 2]:  # 多取一些候选
            if used_tokens + page.tokens <= max_tokens:
                loaded_pages.append(page)
                used_tokens += page.tokens

                # 更新访问信息
                page.access_count += 1
                page.last_accessed = datetime.now(UTC).timestamp()

                if len(loaded_pages) >= top_k:
                    break

        self.logger.info(f"Loaded {len(loaded_pages)} relevant pages (query: {query[:50]}...)")

        return loaded_pages

    async def page_out(self, session_id: str, count: int = 1) -> list[str]:
        """淘汰最少使用的页面

        Args:
            session_id: 会话ID
            count: 淘汰数量

        Returns:
            被淘汰的页面ID列表

        """
        if session_id not in self.session_pages:
            return []

        page_ids = self.session_pages[session_id]
        candidates = [self.pages[pid] for pid in page_ids if pid in self.pages]

        # 按LRU分数排序（分数高的先淘汰）
        sorted_pages = sorted(candidates, key=lambda p: p.lru_score, reverse=True)

        evicted_ids = []
        for page in sorted_pages[:count]:
            del self.pages[page.page_id]
            self.session_pages[session_id].remove(page.page_id)
            evicted_ids.append(page.page_id)

        self.logger.info(f"Evicted {len(evicted_ids)} pages from session {session_id}")

        return evicted_ids

    def get_page(self, page_id: str) -> ConversationPage | None:
        """获取指定页面"""
        return self.pages.get(page_id)

    def get_session_pages(self, session_id: str) -> list[ConversationPage]:
        """获取会话的所有页面"""
        if session_id not in self.session_pages:
            return []

        page_ids = self.session_pages[session_id]
        return [self.pages[pid] for pid in page_ids if pid in self.pages]

    def get_active_context(self, pages: list[ConversationPage]) -> str:
        """获取活动页面的上下文内容"""
        if not pages:
            return ""

        sections = []
        for page in pages:
            sections.append(f"## {page.summary}")
            sections.append(page.content[:300])  # 截取部分内容
            sections.append("")

        return "\n---\n".join(sections)

    async def delete_page(self, page_id: str) -> bool:
        """删除页面"""
        if page_id not in self.pages:
            return False

        page = self.pages[page_id]
        session_id = page.session_id

        # 从存储中删除
        del self.pages[page_id]

        # 从会话索引中删除
        if session_id in self.session_pages:
            self.session_pages[session_id].remove(page_id)

        # 如果有VirtualContextManager，同步删除
        if self.virtual_context:
            try:
                await self.virtual_context.delete_page(page_id)
            except Exception as e:
                self.logger.warning(f"Failed to delete virtual context page: {e}")

        return True

    async def clear_session(self, session_id: str) -> int:
        """清除会话的所有页面"""
        if session_id not in self.session_pages:
            return 0

        count = 0
        for page_id in self.session_pages[session_id][:]:  # 复制列表
            if await self.delete_page(page_id):
                count += 1

        del self.session_pages[session_id]
        self.logger.info(f"Cleared {count} pages for session {session_id}")

        return count

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "total_pages": len(self.pages),
            "total_sessions": len(self.session_pages),
            "max_active_pages": self.max_active_pages,
            "page_size": self.page_size,
            "sessions": {sid: len(pages) for sid, pages in self.session_pages.items()},
        }

    async def optimize_pages(self, session_id: str, target_tokens: int) -> int:
        """优化页面数量以适应token限制

        Args:
            session_id: 会话ID
            target_tokens: 目标token数

        Returns:
            释放的token数

        """
        pages = self.get_session_pages(session_id)
        current_tokens = sum(p.tokens for p in pages)

        if current_tokens <= target_tokens:
            return 0

        # 计算需要释放的token
        tokens_to_free = current_tokens - target_tokens

        # 按LRU分数排序，淘汰分数高的页面
        sorted_pages = sorted(pages, key=lambda p: p.lru_score, reverse=True)

        freed_tokens = 0
        evicted_count = 0

        for page in sorted_pages:
            if freed_tokens >= tokens_to_free:
                break

            freed_tokens += page.tokens
            await self.delete_page(page.page_id)
            evicted_count += 1

        self.logger.info(
            f"Optimized {evicted_count} pages, freed {freed_tokens} tokens (session={session_id})",
        )

        return freed_tokens
