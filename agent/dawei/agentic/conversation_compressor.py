# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""对话压缩器 - 长对话Token限制处理方案

实现三层渐进式架构：
- Level 1: Token使用率 < 60% - 全量消息
- Level 2: Token使用率 60%-90% - 智能压缩
- Level 3: Token使用率 > 90% - 虚拟上下文
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar

from .context_manager import TokenEstimator

logger = logging.getLogger(__name__)


@dataclass
class CompressionStats:
    """压缩统计信息"""

    original_count: int = 0
    compressed_count: int = 0
    original_tokens: int = 0
    compressed_tokens: int = 0
    key_messages_kept: int = 0
    compressed_messages: int = 0
    strategy_used: str = "none"
    compression_ratio: float = 0.0


@dataclass
class MessageMetadata:
    """消息元数据"""

    index: int
    role: str
    content: str
    tokens: int
    is_key_message: bool = False
    key_reason: str = ""
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


class ConversationCompressor:
    """对话压缩器

    处理长对话场景下的token限制问题，通过智能压缩保留关键信息。

    策略：
    1. 滑动窗口 - 保留最近N条完整消息
    2. 关键消息识别 - 保留工具调用、错误、模式切换等重要消息
    3. 摘要生成 - 对中间消息生成摘要
    """

    # 关键消息识别规则
    KEY_MESSAGE_RULES: ClassVar[dict[str, list[str]]] = {
        "tool_call_keywords": ["tool_call", "function_call", "tool_calls"],
        "error_keywords": ["error", "exception", "failed", "failure"],
        "mode_switch_keywords": ["mode_switch", "switched_mode", "mode_changed"],
        "completion_keywords": ["attempt_completion", "task_complete", "finished"],
    }

    def __init__(
        self,
        context_manager=None,
        preserve_recent: ClassVar[int] = 20,
        max_tokens: ClassVar[int] = 100000,
        compression_threshold: ClassVar[float] = 0.6,
        aggressive_threshold: ClassVar[float] = 0.9,
    ):
        """初始化对话压缩器

        Args:
            context_manager: 上下文管理器实例
            preserve_recent: 保留最近的消息数量
            max_tokens: 最大token数限制
            compression_threshold: 开始压缩的阈值（0-1）
            aggressive_threshold: 激进压缩的阈值（0-1）

        """
        self.context_manager = context_manager
        self.preserve_recent = preserve_recent
        self.max_tokens = max_tokens
        self.compression_threshold = compression_threshold
        self.aggressive_threshold = aggressive_threshold

        self.logger = logging.getLogger(__name__)

    def estimate_messages_tokens(self, messages: list[dict[str, Any]]) -> int:
        """估算消息列表的总token数

        Args:
            messages: 消息列表

        Returns:
            估算的token总数

        """
        total_tokens = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                # 多模态内容（如图片+文本）
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        total_tokens += TokenEstimator.estimate(item.get("text", ""))
                    elif isinstance(item, dict) and item.get("type") == "image_url":
                        # 图片通常占用较多token，使用固定估算
                        total_tokens += 1000
            else:
                total_tokens += TokenEstimator.estimate(str(content))

            # 工具调用也占用token
            if msg.get("tool_calls"):
                total_tokens += len(msg["tool_calls"]) * 50  # 每个工具调用约50 tokens

        return total_tokens

    def identify_key_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[set[int], list[MessageMetadata]]:
        """识别关键消息

        关键消息类型：
        1. 工具调用消息
        2. 错误消息
        3. 模式切换消息
        4. 任务完成消息
        5. 用户标记的重要消息（metadata.important=true）

        Args:
            messages: 消息列表

        Returns:
            (关键消息索引集合, 消息元数据列表)

        """
        key_indices = set()
        metadata_list = []

        for idx, msg in enumerate(messages):
            content = msg.get("content", "")
            role = msg.get("role", "")

            # 估算token
            text_content = " ".join([item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]) if isinstance(content, list) else str(content)

            tokens = TokenEstimator.estimate(text_content)
            if msg.get("tool_calls"):
                tokens += len(msg["tool_calls"]) * 50

            msg_meta = MessageMetadata(index=idx, role=role, content=text_content, tokens=tokens)

            # 检查是否为关键消息
            is_key = False
            reason = ""

            # 检查工具调用
            if msg.get("tool_calls"):
                is_key = True
                reason = "tool_call"
            elif "tool_responses" in msg:
                is_key = True
                reason = "tool_response"

            # 检查错误
            if not is_key:
                content_lower = text_content.lower()
                for keyword in self.KEY_MESSAGE_RULES["error_keywords"]:
                    if keyword in content_lower:
                        is_key = True
                        reason = "error"
                        break

            # 检查模式切换
            if not is_key:
                metadata = msg.get("metadata", {})
                if isinstance(metadata, dict):
                    if metadata.get("mode_switch") or metadata.get("mode_changed"):
                        is_key = True
                        reason = "mode_switch"
                    elif metadata.get("important"):
                        is_key = True
                        reason = "user_marked_important"

            # 检查完成关键字
            if not is_key:
                content_lower = text_content.lower()
                for keyword in self.KEY_MESSAGE_RULES["completion_keywords"]:
                    if keyword in content_lower:
                        is_key = True
                        reason = "completion"
                        break

            msg_meta.is_key_message = is_key
            msg_meta.key_reason = reason

            if is_key:
                key_indices.add(idx)

            metadata_list.append(msg_meta)

        return key_indices, metadata_list

    def compress_conversation(
        self,
        messages: list[dict[str, Any]],
        target_tokens: ClassVar[int | None] = None,
        current_tokens: ClassVar[int | None] = None,
    ) -> tuple[list[dict[str, Any]], CompressionStats]:
        """压缩对话历史

        Args:
            messages: 原始消息列表
            target_tokens: 目标token数（默认使用max_tokens）
            current_tokens: 当前已使用的token数

        Returns:
            (压缩后的消息列表, 压缩统计信息)

        """
        target = target_tokens or self.max_tokens

        # 估算当前token
        estimated_tokens = current_tokens or self.estimate_messages_tokens(messages)

        # 计算使用率 - 基于消息自身的token占用
        usage_ratio = estimated_tokens / target if target > 0 else 1.0

        stats = CompressionStats(original_count=len(messages), original_tokens=estimated_tokens)

        # 根据使用率选择策略
        if usage_ratio < 0.5:
            # Level 1: 不需要压缩 (< 50%)
            stats.compressed_count = len(messages)
            stats.compressed_tokens = estimated_tokens
            stats.strategy_used = "none"
            stats.compression_ratio = 0.0
            return messages, stats

        if usage_ratio < self.aggressive_threshold:
            # Level 2: 智能压缩 (50% - 90%)
            compressed, stats = self._intelligent_compression(messages, target, estimated_tokens)
            stats.strategy_used = "intelligent"
            return compressed, stats

        # Level 3: 激进压缩 (> 90%)
        compressed, stats = self._aggressive_compression(messages, target, estimated_tokens)
        stats.strategy_used = "aggressive"
        return compressed, stats

    def _intelligent_compression(
        self,
        messages: list[dict[str, Any]],
        _target_tokens: int,
        estimated_tokens: int,
    ) -> tuple[list[dict[str, Any]], CompressionStats]:
        """智能压缩策略

        1. 保留最近N条完整消息
        2. 识别并保留关键消息
        3. 对中间消息生成摘要
        """
        key_indices, metadata_list = self.identify_key_messages(messages)

        # 保留最近的消息
        recent_messages = messages[-self.preserve_recent :] if len(messages) > self.preserve_recent else messages

        # 构建压缩后的消息列表
        compressed = []
        kept_indices = set()

        # 保留关键消息
        for idx in sorted(key_indices):
            if idx < len(messages) - self.preserve_recent:  # 不在最近消息范围内
                compressed.append(messages[idx])
                kept_indices.add(idx)

        # 添加最近的消息
        compressed.extend(recent_messages)
        for idx in range(max(0, len(messages) - self.preserve_recent), len(messages)):
            kept_indices.add(idx)

        # 检查是否还需要添加压缩说明
        if len(compressed) < len(messages):
            # 生成中间消息的摘要
            middle_messages = [msg for idx, msg in enumerate(messages) if idx not in kept_indices]

            if middle_messages:
                summary = self._generate_summary(middle_messages, metadata_list)
                if summary:
                    # 在最近消息前插入摘要
                    insert_pos = max(0, len(compressed) - len(recent_messages))
                    compressed.insert(
                        insert_pos,
                        {
                            "role": "system",
                            "content": f"[Conversation Summary]\n{summary}",
                            "metadata": {"is_summary": True},
                        },
                    )

        # 重新估算token
        compressed_tokens = self.estimate_messages_tokens(compressed)

        stats = CompressionStats(
            original_count=len(messages),
            compressed_count=len(compressed),
            original_tokens=estimated_tokens,
            compressed_tokens=compressed_tokens,
            key_messages_kept=len([idx for idx in key_indices if idx in kept_indices]),
            compressed_messages=len(messages) - len(compressed),
            strategy_used="intelligent",
            compression_ratio=(1.0 - (compressed_tokens / estimated_tokens) if estimated_tokens > 0 else 0),
        )

        self.logger.info(
            f"Intelligent compression: {len(messages)} -> {len(compressed)} messages, {estimated_tokens} -> {compressed_tokens} tokens ({stats.compression_ratio:.1%} reduction)",
        )

        return compressed, stats

    def _aggressive_compression(
        self,
        messages: list[dict[str, Any]],
        _target_tokens: int,
        estimated_tokens: int,
    ) -> tuple[list[dict[str, Any]], CompressionStats]:
        """激进压缩策略

        1. 仅保留最近N条消息
        2. 仅保留关键消息中的最关键部分
        3. 生成详细摘要
        """
        # 识别关键消息
        key_indices, metadata_list = self.identify_key_messages(messages)

        # 只保留最近的少数消息
        preserve_count = max(5, self.preserve_recent // 2)
        recent_messages = messages[-preserve_count:] if len(messages) > preserve_count else messages

        # 只保留最关键的消息（错误、工具调用结果）
        most_critical = []
        for idx in key_indices:
            if idx < len(messages) - preserve_count:
                meta = metadata_list[idx]
                # 只保留错误和工具调用
                if meta.key_reason in ["error", "tool_call", "tool_response"]:
                    most_critical.append(messages[idx])

        # 生成详细摘要
        all_kept_indices = set(range(max(0, len(messages) - preserve_count), len(messages)))
        all_kept_indices.update(
            [idx for idx in key_indices if idx < len(messages) - preserve_count],
        )

        middle_messages = [msg for idx, msg in enumerate(messages) if idx not in all_kept_indices]

        compressed = []

        # 添加系统说明
        compressed.append(
            {
                "role": "system",
                "content": (f"The conversation history has been compressed to fit within token limits. Original conversation had {len(messages)} messages. Showing only the most recent and critical messages."),
                "metadata": {"is_compression_notice": True},
            },
        )

        # 添加最关键的消息
        compressed.extend(most_critical)

        # 添加摘要
        if middle_messages:
            summary = self._generate_summary(middle_messages, metadata_list, detailed=True)
            if summary:
                compressed.append(
                    {
                        "role": "system",
                        "content": f"[Detailed Conversation Summary]\n{summary}",
                        "metadata": {"is_summary": True},
                    },
                )

        # 添加最近的消息
        compressed.extend(recent_messages)

        # 重新估算token
        compressed_tokens = self.estimate_messages_tokens(compressed)

        stats = CompressionStats(
            original_count=len(messages),
            compressed_count=len(compressed),
            original_tokens=estimated_tokens,
            compressed_tokens=compressed_tokens,
            key_messages_kept=len(most_critical),
            compressed_messages=len(messages) - len(compressed),
            strategy_used="aggressive",
            compression_ratio=(1.0 - (compressed_tokens / estimated_tokens) if estimated_tokens > 0 else 0),
        )

        self.logger.warning(
            f"Aggressive compression: {len(messages)} -> {len(compressed)} messages, {estimated_tokens} -> {compressed_tokens} tokens ({stats.compression_ratio:.1%} reduction)",
        )

        return compressed, stats

    def _generate_summary(
        self,
        messages: list[dict[str, Any]],
        _metadata_list: list[MessageMetadata],
        detailed: bool = False,
    ) -> str:
        """生成消息摘要

        Args:
            messages: 要摘要的消息列表
            metadata_list: 消息元数据列表
            detailed: 是否生成详细摘要

        Returns:
            摘要文本

        """
        if not messages:
            return ""

        summary_parts = []

        # 统计信息
        role_counts = {}
        for msg in messages:
            role = msg.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        summary_parts.append(f"Compressed {len(messages)} messages:")
        for role, count in role_counts.items():
            summary_parts.append(f"  - {count} {role} messages")

        # 关键内容提取
        if detailed:
            # 提取关键句
            key_contents = []
            for msg in messages[:10]:  # 最多10条
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 20:
                    # 取第一句
                    first_sentence = content.split(".")[0].split("\n")[0][:100]
                    key_contents.append(f"  - [{msg.get('role', 'unknown')}] {first_sentence}...")

            if key_contents:
                summary_parts.append("\nKey topics discussed:")
                summary_parts.extend(key_contents[:5])

        return "\n".join(summary_parts)

    def should_compress(self, messages: list[dict[str, Any]]) -> bool:
        """检查是否需要压缩

        Args:
            messages: 消息列表

        Returns:
            是否需要压缩

        """
        # 快速检查：消息数量超过阈值
        if len(messages) > 50:
            return True

        # 检查token使用
        estimated_tokens = self.estimate_messages_tokens(messages)
        if estimated_tokens > self.max_tokens * self.compression_threshold:
            return True

        # 如果有context_manager，使用它的统计
        if self.context_manager:
            stats = self.context_manager.get_stats()
            if stats.percentage > self.compression_threshold * 100:
                return True

        return False

    def get_compression_level(self, messages: list[dict[str, Any]]) -> str:
        """获取当前压缩级别

        Args:
            messages: 消息列表

        Returns:
            压缩级别: "none", "intelligent", "aggressive"

        """
        if not self.should_compress(messages):
            return "none"

        estimated_tokens = self.estimate_messages_tokens(messages)

        if self.context_manager:
            stats = self.context_manager.get_stats()
            usage_ratio = stats.used / stats.total
        else:
            usage_ratio = estimated_tokens / self.max_tokens

        if usage_ratio < self.aggressive_threshold:
            return "intelligent"
        return "aggressive"
