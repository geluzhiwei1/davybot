# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""文件引用语法解析器（

支持的语法：
- @file.py           - 引用单个文件
- @folder/           - 引用整个文件夹
- @*.py              - 通配符匹配
- @**/*.py           - 递归通配符
- @file1.py @file2.py - 多个文件引用

示例：
"帮我分析 @agent.py 和 @context_manager.py 的区别"
"请重构 @dawei/agentic/ 目录下的所有文件"
"""

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

# ============================================================================
# 数据类定义
# ============================================================================


class ReferenceType(StrEnum):
    """引用类型"""

    FILE = "file"  # 单个文件
    FOLDER = "folder"  # 文件夹
    WILDCARD = "wildcard"  # 通配符
    RECURSIVE = "recursive"  # 递归通配符
    SKILL = "skill"  # 技能引用 (@skill:xxx)
    OTHER = "other"  # 其他特殊引用 (@command:, @mention:等)


@dataclass
class FileReference:
    """文件引用"""

    raw_path: str  # 原始路径 (如 "@file.py")
    reference_type: ReferenceType
    resolved_paths: list[str] = field(default_factory=list)  # 解析后的路径列表
    line_number: int | None = None  # 在消息中的行号
    is_valid: bool = True
    error_message: str | None = None


@dataclass
class ParsedMessage:
    """解析后的消息"""

    original_message: str
    cleaned_message: str  # 移除引用后的消息
    references: list[FileReference]
    total_files: int  # 引用的文件总数


# ============================================================================
# 文件引用解析器
# ============================================================================


class FileReferenceParser:
    """文件引用语法解析器

    功能：
    1. 识别 @file.py, @folder/ 语法
    2. 支持通配符 *.py, **/*.py
    3. 解析多个文件引用
    4. 提供清理后的消息（移除引用标记）
    """

    # 正则表达式模式
    REFERENCE_PATTERN = re.compile(
        r"@([^\s@]+?)(?=\s|$)",
        re.MULTILINE,  # 匹配 @xxx (遇到空格或行尾结束，不包含空格)
    )

    WILDCARD_PATTERNS: ClassVar[dict[str, ReferenceType]] = {
        "*": ReferenceType.WILDCARD,
        "**": ReferenceType.RECURSIVE,
    }

    def __init__(self, workspace_root: Path | None = None):
        """初始化解析器

        Args:
            workspace_root: 工作区根目录（用于解析相对路径）

        """
        self.workspace_root = workspace_root or Path.cwd()
        self.logger = logging.getLogger(__name__)

    def parse(self, message: str) -> ParsedMessage:
        """解析消息中的文件引用

        Args:
            message: 用户消息

        Returns:
            解析后的消息对象

        """
        references = []

        # 查找所有引用
        for match in self.REFERENCE_PATTERN.finditer(message):
            raw_ref = match.group(0)  # "@file.py"
            path = match.group(1)  # "file.py"

            # 确定引用类型
            ref_type = self._detect_reference_type(path)

            # 创建引用对象（路径解析在下一步进行）
            reference = FileReference(
                raw_path=raw_ref,
                reference_type=ref_type,
                resolved_paths=[],
                is_valid=True,
            )

            references.append(reference)

        # 清理消息（移除引用标记）
        cleaned_message = self._clean_message(message, references)

        return ParsedMessage(
            original_message=message,
            cleaned_message=cleaned_message,
            references=references,
            total_files=0,  # 稍后计算
        )

    def _detect_reference_type(self, path: str) -> ReferenceType:
        """检测引用类型"""
        # 技能引用 (@skill:xxx)
        if path.startswith("skill:"):
            return ReferenceType.SKILL

        # 其他特殊引用 (如 @command:, @mention: 等)
        if ":" in path and not path.startswith("."):
            # 跳过非文件路径的特殊引用
            return ReferenceType.OTHER

        # 文件夹（以 / 结尾）
        if path.endswith("/"):
            return ReferenceType.FOLDER

        # 通配符
        if "*" in path:
            if "**" in path:
                return ReferenceType.RECURSIVE
            return ReferenceType.WILDCARD

        # 默认为文件
        return ReferenceType.FILE

    def _clean_message(self, message: str, references: list[FileReference]) -> str:
        """清理消息，移除文件引用标记

        Args:
            message: 原始消息
            references: 文件引用列表

        Returns:
            清理后的消息

        """
        cleaned = message

        # 按出现顺序倒序移除（避免位置偏移）
        for ref in reversed(references):
            # 移除引用标记
            cleaned = cleaned.replace(ref.raw_path, "", 1)

        # 清理多余的空格
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = cleaned.strip()

        # 移除孤立的连接词（中文和英文）
        # 使用更宽松的模式：开头、中间、结尾的连接词都移除
        connector_patterns = [
            r"^[和与及以及]+",  # 开头 - 中文
            r"\s+[和与及以及]+",  # 中间 - 中文
            r"[和与及以及]+$",  # 结尾 - 中文
            r"\s+(and|or|with)\s*",  # 英文连接词
            r"^(and|or|with)\s*",  # 开头 - 英文
            r"\s+(and|or|with)$",  # 结尾 - 英文
        ]
        for pattern in connector_patterns:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

        # 再次清理空格
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def extract_references_from_lines(self, lines: list[str]) -> list[FileReference]:
        """从多行文本中提取引用（支持代码块）

        Args:
            lines: 文本行列表

        Returns:
            文件引用列表

        """
        references = []

        for line_num, line in enumerate(lines, start=1):
            refs = self.parse(line).references
            for ref in refs:
                ref.line_number = line_num
                references.append(ref)

        return references


# ============================================================================
# 路径解析器
# ============================================================================


class PathResolver:
    """智能路径解析器

    功能：
    1. 解析相对路径（相对于工作区）
    2. 解析绝对路径
    3. 解析通配符模式
    4. 验证文件/文件夹存在性
    """

    def __init__(self, workspace_root: Path | None = None):
        """初始化路径解析器

        Args:
            workspace_root: 工作区根目录

        """
        self.workspace_root = workspace_root or Path.cwd()
        self.logger = logging.getLogger(__name__)

    def resolve(self, reference: FileReference) -> list[str]:
        """解析文件引用为实际路径列表

        Args:
            reference: 文件引用

        Returns:
            解析后的路径列表

        """
        path_str = reference.raw_path[1:]  # 移除 @ 符号

        # 特殊引用类型（SKILL, OTHER）不应该作为文件路径处理
        # 应该直接跳过所有路径解析逻辑
        if reference.reference_type in (ReferenceType.SKILL, ReferenceType.OTHER):
            reference.is_valid = True
            reference.resolved_paths = []
            self.logger.debug(
                f"Skipping path resolution for {reference.reference_type.value}: {path_str}",
            )
            return []

        try:
            # 【安全修复】先展开用户目录（~），再判断是否为绝对路径
            expanded_str = Path(path_str).expanduser()

            # 判断是否为绝对路径
            if expanded_str.is_absolute():
                base_path = expanded_str
            else:
                # 确保 path_str 被转换为 Path 对象再连接
                base_path = self.workspace_root / Path(path_str)

            # 验证路径是否在工作区内，防止路径遍历攻击
            try:
                resolved_path = base_path.resolve()
                workspace_resolved = self.workspace_root.resolve()

                # 检查解析后的路径是否仍在工作区内
                if not str(resolved_path).startswith(str(workspace_resolved)):
                    reference.is_valid = False
                    reference.error_message = f"Path outside workspace not allowed: {path_str} (resolved to {resolved_path})"
                    self.logger.warning(
                        f"Blocked path traversal attempt: {path_str} -> {resolved_path}",
                    )
                    return []
            except Exception as e:
                reference.is_valid = False
                reference.error_message = f"Invalid path: {e}"
                self.logger.warning(f"Invalid path attempt: {path_str} - {e}")
                return []

            # 根据引用类型解析
            if reference.reference_type == ReferenceType.FILE:
                return self._resolve_file(base_path, reference)

            if reference.reference_type == ReferenceType.FOLDER:
                return self._resolve_folder(base_path, reference)

            if reference.reference_type == ReferenceType.WILDCARD:
                return self._resolve_wildcard(base_path, reference, recursive=False)

            if reference.reference_type == ReferenceType.RECURSIVE:
                return self._resolve_wildcard(base_path, reference, recursive=True)

            reference.is_valid = False
            reference.error_message = f"Unknown reference type: {reference.reference_type}"
            return []

        except Exception as e:
            self.logger.exception("Failed to resolve path {path_str}: ")
            reference.is_valid = False
            reference.error_message = str(e)
            return []

    def _resolve_file(self, path: Path, reference: FileReference) -> list[str]:
        """解析单个文件"""
        if not path.exists():
            reference.is_valid = False
            reference.error_message = f"File not found: {path}"
            return []

        if not path.is_file():
            reference.is_valid = False
            reference.error_message = f"Not a file: {path}"
            return []

        return [str(path)]

    def _resolve_folder(self, path: Path, reference: FileReference) -> list[str]:
        """解析文件夹"""
        if not path.exists():
            reference.is_valid = False
            reference.error_message = f"Folder not found: {path}"
            return []

        if not path.is_dir():
            reference.is_valid = False
            reference.error_message = f"Not a folder: {path}"
            return []

        # 获取文件夹内所有文件
        try:
            files = [
                str(f)
                for f in path.rglob("*")
                if f.is_file()
                # 排除隐藏文件和常见忽略目录
                and not any(part.startswith(".") for part in f.parts)
                and not any(part.startswith("__pycache__") for part in f.parts)
            ]
            return sorted(files)
        except Exception as e:
            reference.is_valid = False
            reference.error_message = f"Failed to list folder: {e}"
            return []

    def _resolve_wildcard(self, path: Path, reference: FileReference, recursive: bool) -> list[str]:
        """解析通配符模式"""
        # 获取父目录和模式
        path_str = str(path)

        # 处理 ** 的情况
        if "**" in path_str:
            # 分割路径找到 ** 的位置
            if "**/" in path_str:
                # 例如: **/*.py 或 subdir/**/*.py
                parts = path_str.split("**/")
                if len(parts) == 2:
                    base_dir, pattern = parts
                    base_path = Path(base_dir) if base_dir else self.workspace_root
                else:
                    # 多个 **，使用整个路径作为模式
                    base_path = self.workspace_root
                    pattern = path_str.replace("**", "*")
            else:
                # ** 在末尾或开头
                base_path = self.workspace_root
                pattern = path_str.replace("**", "*")
        elif "*" in path.name:
            # 单层通配符: *.py 或 subdir/*.py
            base_path = path.parent
            pattern = path.name
        else:
            # 没有通配符
            base_path = path
            pattern = "*"

        if base_path and not base_path.exists():
            reference.is_valid = False
            reference.error_message = f"Path not found: {base_path}"
            return []

        # 匹配文件
        try:
            files = list(base_path.rglob(pattern)) if recursive or "**" in path_str else list(base_path.glob(pattern))

            # 过滤：只保留文件
            files = [str(f) for f in files if f.is_file()]

            return sorted(files)
        except Exception as e:
            reference.is_valid = False
            reference.error_message = f"Failed to match pattern: {e}"
            return []

    def resolve_all(self, parsed_message: ParsedMessage) -> ParsedMessage:
        """解析消息中的所有引用

        Args:
            parsed_message: 解析后的消息

        Returns:
            更新后的消息（包含解析后的路径）

        """
        resolver = PathResolver(self.workspace_root)

        total_files = 0
        for ref in parsed_message.references:
            resolved = resolver.resolve(ref)
            ref.resolved_paths = resolved
            total_files += len(resolved)

        parsed_message.total_files = total_files

        return parsed_message


# ============================================================================
# 工厂函数
# ============================================================================


def parse_file_references(message: str, workspace_root: Path | None = None) -> ParsedMessage:
    """便捷函数：解析消息中的文件引用

    Args:
        message: 用户消息
        workspace_root: 工作区根目录

    Returns:
        解析后的消息

    """
    parser = FileReferenceParser(workspace_root)
    resolver = PathResolver(workspace_root)

    # 解析引用
    parsed = parser.parse(message)

    # 解析路径
    return resolver.resolve_all(parsed)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    # 测试用例
    message = "帮我分析 @agent.py 和 @context_manager.py 的代码"
    parsed = parse_file_references(message)

    print(f"原始消息: {parsed.original_message}")
    print(f"清理后: {parsed.cleaned_message}")
    print(f"引用数: {len(parsed.references)}")
    print(f"文件数: {parsed.total_files}")

    for ref in parsed.references:
        print(f"  - {ref.raw_path}: {len(ref.resolved_paths)} files")
