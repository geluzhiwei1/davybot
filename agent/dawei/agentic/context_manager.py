# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""上下文管理器（
实时追踪 token 使用，避免超出上下文限制
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

# ============================================================================
# 数据类定义
# ============================================================================


@dataclass
class FileTokenUsage:
    """文件 token 使用情况"""

    path: str
    tokens: int
    last_updated: float
    char_count: int = 0


@dataclass
class SkillContext:
    """技能上下文信息"""

    name: str
    content: str
    tokens: int
    last_updated: float


@dataclass
class ContextBreakdown:
    """上下文分类统计"""

    system_prompt: int = 0
    conversation: int = 0
    workspace_files: int = 0
    tool_definitions: int = 0
    skills: int = 0  # 技能上下文 token
    files: list[FileTokenUsage] = field(default_factory=list)

    def total(self) -> int:
        """计算总 token 数"""
        return self.system_prompt + self.conversation + self.workspace_files + self.tool_definitions + self.skills


@dataclass
class ContextStats:
    """上下文统计信息"""

    total: int  # 总容量
    used: int  # 已使用
    percentage: float  # 使用百分比
    breakdown: ContextBreakdown  # 详细分解
    remaining: int  # 剩余容量
    warnings: list[str] = field(default_factory=list)  # 警告信息


@dataclass
class ContextUpdate:
    """上下文更新事件数据"""

    stats: ContextStats
    timestamp: float = field(default_factory=time.time)


# ============================================================================
# Token 估算器
# ============================================================================


class TokenEstimator:
    """Token 估算器

    用于快速估算文本的 token 数量，避免调用 tiktoken 等 heavy 库
    """

    # 平均字符/token 比率
    CHARS_PER_TOKEN_ENG = 4.0  # 英文约 4 字符/token
    CHARS_PER_TOKEN_CHN = 2.0  # 中文约 2 字符/token

    @classmethod
    def estimate(cls, text: str) -> int:
        """估算文本的 token 数

        Args:
            text: 待估算的文本

        Returns:
            估算的 token 数

        """
        if not text:
            return 0

        # 统计中文字符
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other_chars = len(text) - chinese_chars

        # 计算 token 数
        chinese_tokens = chinese_chars / cls.CHARS_PER_TOKEN_CHN
        other_tokens = other_chars / cls.CHARS_PER_TOKEN_ENG

        return int(chinese_tokens + other_tokens)

    @classmethod
    def estimate_file(cls, file_path: Path) -> int:
        """估算文件的 token 数

        Args:
            file_path: 文件路径

        Returns:
            估算的 token 数

        """
        try:
            if file_path.exists() and file_path.is_file():
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                return cls.estimate(content)
        except (OSError, UnicodeDecodeError) as e:
            logging.warning(f"Failed to estimate tokens for {file_path}: {e}", exc_info=True)
            raise ValueError(
                f"Cannot read file {file_path}: {e}",
            ) from e  # Fast fail with specific error

        return 0


# ============================================================================
# 上下文管理器
# ============================================================================


class ContextManager:
    """上下文管理器

    功能：
    1. 追踪各类 token 使用
    2. 管理上下文中的文件
    3. 实时计算使用率
    4. 生成警告和建议
    """

    def __init__(self, max_tokens: int = 200000):
        """初始化上下文管理器

        Args:
            max_tokens: 最大 token 容量（默认 200K，Claude Opus 4 的限制）

        """
        self.max_tokens = max_tokens
        self.system_prompt_tokens = 0
        self.conversation_tokens = 0
        self.tool_tokens = 0
        self.files: dict[str, FileTokenUsage] = {}
        self.skills: dict[str, SkillContext] = {}  # 技能上下文存储

        self.logger = logging.getLogger(__name__)

    def set_system_prompt(self, prompt: str):
        """设置系统提示词

        Args:
            prompt: 系统提示词内容

        """
        self.system_prompt_tokens = TokenEstimator.estimate(prompt)
        self.logger.debug(f"System prompt: {self.system_prompt_tokens} tokens")

    def update_conversation(self, user_message: str, assistant_response: str):
        """更新对话历史 token 使用

        Args:
            user_message: 用户消息
            assistant_response: 助手回复

        """
        user_tokens = TokenEstimator.estimate(user_message)
        assistant_tokens = TokenEstimator.estimate(assistant_response)

        self.conversation_tokens += user_tokens + assistant_tokens

        self.logger.debug(
            f"Conversation updated: +{user_tokens + assistant_tokens} tokens (total: {self.conversation_tokens})",
        )

    def set_tool_definitions(self, tools: list):
        """设置工具定义的 token 消耗

        Args:
            tools: 工具列表（需要有 schema 属性）

        """
        # 将工具定义转换为 JSON 字符串并估算
        try:
            tools_json = str(tools)  # 简化处理，实际可以用 json.dumps
            self.tool_tokens = TokenEstimator.estimate(tools_json)
            self.logger.debug(f"Tool definitions: {self.tool_tokens} tokens")
        except (AttributeError, TypeError, ValueError) as e:
            self.logger.warning(f"Failed to estimate tool tokens: {e}", exc_info=True)
            self.tool_tokens = 0
            raise ValueError(
                f"Invalid tool definitions format: {e}",
            ) from e  # Fast fail with specific error

    def add_file(self, file_path: str, content: str | None = None):
        """添加文件到上下文

        Args:
            file_path: 文件路径
            content: 文件内容（可选，如果不提供则从文件读取）

        """
        # 如果文件已存在，先移除
        if file_path in self.files:
            self.remove_file(file_path)

        # 获取内容
        if content is None:
            path = Path(file_path)
            if not path.exists():
                self.logger.warning(f"File not found: {file_path}")
                return

            # 【安全增强】检查文件大小，防止读取超大文件导致OOM
            max_file_size = 10 * 1024 * 1024  # 10MB
            try:
                file_size = path.stat().st_size
                if file_size > max_file_size:
                    self.logger.warning(
                        f"File too large ({file_size / 1024 / 1024:.1f}MB), skipping: {file_path} (max: {max_file_size / 1024 / 1024:.0f}MB)",
                    )
                    return
            except OSError as e:
                self.logger.warning(
                    f"Failed to check file size for {file_path}: {e}",
                    exc_info=True,
                )
                raise OSError(
                    f"Cannot access file {file_path}: {e}",
                ) from e  # Fast fail with specific error

            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                char_count = len(content)
            except Exception as e:
                self.logger.error(f"Failed to read file {file_path}: {e}", exc_info=True)
                return
        else:
            char_count = len(content)

        # 估算 token
        tokens = TokenEstimator.estimate(content)

        # 记录文件
        self.files[file_path] = FileTokenUsage(
            path=file_path,
            tokens=tokens,
            last_updated=time.time(),
            char_count=char_count,
        )

        self.logger.debug(f"Added file: {file_path} ({tokens} tokens)")

    def add_skill_context(self, skill_name: str, skill_content: str):
        """添加技能上下文

        Args:
            skill_name: 技能名称
            skill_content: 技能内容（SKILL.md 的完整内容）

        """
        # 如果技能已存在，先移除
        if skill_name in self.skills:
            del self.skills[skill_name]

        # 估算 token
        tokens = TokenEstimator.estimate(skill_content)

        # 记录技能上下文
        self.skills[skill_name] = SkillContext(
            name=skill_name,
            content=skill_content,
            tokens=tokens,
            last_updated=time.time(),
        )

        self.logger.info(f"Added skill context: {skill_name} ({tokens} tokens)")

    def get_skill_context(self, skill_name: str) -> SkillContext | None:
        """获取技能上下文

        Args:
            skill_name: 技能名称

        Returns:
            技能上下文，如果不存在则返回 None

        """
        return self.skills.get(skill_name)

    def get_all_skills(self) -> dict[str, SkillContext]:
        """获取所有技能上下文

        Returns:
            技能上下文字典

        """
        return self.skills.copy()

    def remove_file(self, file_path: str):
        """从上下文移除文件

        Args:
            file_path: 文件路径

        """
        if file_path in self.files:
            del self.files[file_path]
            self.logger.debug(f"Removed file: {file_path}")

    def get_stats(self) -> ContextStats:
        """获取上下文统计信息

        Returns:
            上下文统计

        """
        # 计算文件总 token
        file_tokens = sum(f.tokens for f in self.files.values())

        # 计算技能总 token
        skill_tokens = sum(s.tokens for s in self.skills.values())

        # 构建分类统计
        breakdown = ContextBreakdown(
            system_prompt=self.system_prompt_tokens,
            conversation=self.conversation_tokens,
            workspace_files=file_tokens,
            tool_definitions=self.tool_tokens,
            skills=skill_tokens,
            files=[
                FileTokenUsage(
                    path=f.path,
                    tokens=f.tokens,
                    last_updated=f.last_updated,
                    char_count=f.char_count,
                )
                for f in self.files.values()
            ],
        )

        # 计算总量
        used = breakdown.total()

        # 生成警告
        warnings = self._generate_warnings(used, file_tokens)

        return ContextStats(
            total=self.max_tokens,
            used=used,
            percentage=(used / self.max_tokens) * 100,
            breakdown=breakdown,
            remaining=self.max_tokens - used,
            warnings=warnings,
        )

    def _generate_warnings(self, used: int, _file_tokens: int) -> list[str]:
        """生成上下文警告"""
        warnings = []
        percentage = (used / self.max_tokens) * 100

        if percentage > 90:
            warnings.append("严重警告：上下文即将用尽（> 90%）")
        elif percentage > 75:
            warnings.append("警告：上下文使用超过 75%")

        if self.max_tokens - used < 8000:
            warnings.append("剩余空间不足 8000 tokens")

        # 文件数量警告
        if len(self.files) > 20:
            warnings.append(f"上下文文件过多（{len(self.files)} 个），建议移除部分文件")

        # 【透明度增强】Token 估算误差警告
        if used > 0:
            percentage_text = f"注意：Token 数为估算值，实际可能偏差 ±20%。当前估算：{used:,} tokens"
            if percentage > 80:
                # 高使用量时强调误差风险
                warnings.append(f"{percentage_text}（建议保守计算）")
            elif percentage > 50:
                # 中等使用量时温和提醒
                warnings.append(percentage_text)

        return warnings

    def get_warnings(self) -> list[str]:
        """获取当前警告"""
        stats = self.get_stats()
        return stats.warnings

    def get_files_summary(self) -> list[dict]:
        """获取文件摘要

        Returns:
            文件列表，包含路径、token、大小等信息

        """
        return [
            {
                "path": f.path,
                "tokens": f.tokens,
                "percentage": (f.tokens / self.max_tokens) * 100,
                "last_updated": f.last_updated,
                "char_count": f.char_count,
            }
            for f in self.files.values()
        ]

    def compress_conversation(self, target_tokens: int) -> int:
        """压缩对话历史

        Args:
            target_tokens: 目标 token 数

        Returns:
            压缩掉的 token 数

        """
        if self.conversation_tokens <= target_tokens:
            return 0

        removed = self.conversation_tokens - target_tokens
        self.conversation_tokens = target_tokens

        self.logger.info(f"Compressed conversation: -{removed} tokens")
        return removed

    def clear_conversation(self):
        """清空对话历史"""
        old_tokens = self.conversation_tokens
        self.conversation_tokens = 0
        self.logger.info(f"Cleared conversation: -{old_tokens} tokens")

    def clear_files(self):
        """清空所有文件"""
        count = len(self.files)
        self.files.clear()
        self.logger.info(f"Cleared {count} files from context")

    def get_optimization_suggestions(self) -> list[str]:
        """获取上下文优化建议

        Returns:
            优化建议列表

        """
        suggestions = []
        stats = self.get_stats()

        # 文件优化建议
        if stats.breakdown.workspace_files > stats.total * 0.5:
            suggestions.append("工作区文件占用过多，考虑移除不必要的文件")

        # 对话历史优化
        if stats.breakdown.conversation > stats.total * 0.6:
            suggestions.append("对话历史较长，考虑压缩或清空早期消息")

        # 工具定义优化
        if len(self.files) > 15:
            suggestions.append(f"有 {len(self.files)} 个文件在上下文中，建议移除部分")

        return suggestions


# ============================================================================
# 上下文监控器（集成到 Agent）
# ============================================================================


class ContextMonitor:
    """上下文监控器

    提供定期监控和自动优化功能
    """

    def __init__(self, context_manager: ContextManager, check_interval: int = 30):
        """初始化监控器

        Args:
            context_manager: 上下文管理器实例
            check_interval: 检查间隔（秒）

        """
        self.context_manager = context_manager
        self.check_interval = check_interval
        self.last_check = 0
        self.logger = logging.getLogger(__name__)

    def check_and_optimize(self) -> ContextUpdate | None:
        """检查并优化上下文

        Returns:
            上下文更新（如果有变化）

        """
        now = time.time()

        # 检查是否需要更新
        if now - self.last_check < self.check_interval:
            return None

        self.last_check = now
        stats = self.context_manager.get_stats()

        # 如果使用率过高，自动优化
        if stats.percentage > 85:
            self.logger.warning(f"Context usage at {stats.percentage:.1f}%, optimizing...")

            # 压缩对话历史
            if stats.breakdown.conversation > stats.total * 0.4:
                target = int(stats.total * 0.3)
                self.context_manager.compress_conversation(target)

        return ContextUpdate(stats=self.context_manager.get_stats())

    def force_update(self) -> ContextUpdate:
        """强制更新并返回上下文状态"""
        return ContextUpdate(stats=self.context_manager.get_stats())
