# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""@ 文件引用处理模块

解析消息中的 @文件引用，读取文件内容并更新消息
"""

import logging
import re
from pathlib import Path
from typing import List, Dict, Any, ClassVar

logger = logging.getLogger(__name__)


class FileReference:
    """文件引用数据类"""

    def __init__(
        self,
        file_path: str,
        content: ClassVar[str | None] = None,
        metadata: ClassVar[Dict[str, Any] | None] = None,
    ):
        self.file_path = file_path
        self.content = content
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "file_path": self.file_path,
            "content": self.content,
            "metadata": self.metadata,
        }


class AtMessageProcessor:
    """处理消息中的 @ 文件引用"""

    # 匹配 @文件路径的正则表达式
    # 匹配格式: @路径/to/file.txt 或 @路径/to/file
    AT_PATTERN = re.compile(r"@([^\s\n]+)")

    # 支持的文本文件扩展名
    TEXT_FILE_EXTENSIONS = {
        ".txt",
        ".md",
        ".markdown",
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".vue",
        ".html",
        ".css",
        ".json",
        ".xml",
        ".yaml",
        ".yml",
        ".sh",
        ".bash",
        ".zsh",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".java",
        ".kt",
        ".swift",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".sql",
        ".csv",
        ".log",
        ".conf",
        ".config",
        ".ini",
        ".toml",
        ".properties",
        ".env",
        ".gitignore",
        ".dockerignore",
        ".editorconfig",
    }

    # 二进制文件扩展名（只读取元信息）
    BINARY_FILE_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".svg",
        ".ico",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".zip",
        ".tar",
        ".gz",
        ".rar",
        ".7z",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".dat",
        ".db",
        ".sqlite",
    }

    @classmethod
    def extract_file_references(cls, message: str) -> List[str]:
        """从消息中提取所有 @文件引用

        注意: 跳过 @skill: 引用，这些由 Agent 内部的 FileReferenceParser 处理

        Args:
            message: 用户消息文本

        Returns:
            文件路径列表

        """
        matches = cls.AT_PATTERN.findall(message)

        # 过滤掉 @skill: 引用，这些由 Agent 内部处理
        file_matches = [m for m in matches if not m.startswith("skill:")]
        skill_matches = [m for m in matches if m.startswith("skill:")]

        if skill_matches:
            logger.debug(
                f"Skipping {len(skill_matches)} @skill: references (will be handled by Agent): {skill_matches}",
            )

        logger.debug(f"Found {len(file_matches)} @ file references: {file_matches}")
        return file_matches

    @classmethod
    def is_text_file(cls, file_path: str) -> bool:
        """判断文件是否为文本文件

        Args:
            file_path: 文件路径

        Returns:
            是否为文本文件

        """
        ext = Path(file_path).suffix.lower()
        return ext in cls.TEXT_FILE_EXTENSIONS

    @classmethod
    def is_binary_file(cls, file_path: str) -> bool:
        """判断文件是否为二进制文件

        Args:
            file_path: 文件路径

        Returns:
            是否为二进制文件

        """
        ext = Path(file_path).suffix.lower()
        return ext in cls.BINARY_FILE_EXTENSIONS

    @classmethod
    def read_directory_content(
        cls,
        directory_path: str,
        max_items: ClassVar[int] = 50,
    ) -> tuple[str | None, Dict[str, Any]]:
        """读取目录内容

        Args:
            directory_path: 目录的完整路径
            max_items: 最多显示的文件/文件夹数量

        Returns:
            (目录内容字符串, 元信息)

        """
        try:
            path_obj = Path(directory_path)

            if not path_obj.exists():
                return None, {
                    "error": "directory_not_found",
                    "full_path": directory_path,
                }

            if not path_obj.is_dir():
                return None, {"error": "not_a_directory", "full_path": directory_path}

            # 获取目录内容
            try:
                items = list(path_obj.iterdir())
            except PermissionError:
                return None, {"error": "permission_denied", "full_path": directory_path}

            # 排序：文件夹在前，文件在后，按字母顺序
            items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

            # 限制显示数量
            if len(items) > max_items:
                items = items[:max_items]
                truncated = True
            else:
                truncated = False

            # 构建目录树字符串
            lines = []
            lines.append(f"📁 {path_obj.name}/")
            lines.append("")

            # 统计信息
            dirs = [item for item in items if item.is_dir()]
            files = [item for item in items if item.is_file()]

            for item in items:
                try:
                    if item.is_dir():
                        lines.append(f"📁 {item.name}/")
                    else:
                        # 文件大小格式化
                        size = item.stat().st_size
                        if size < 1024:
                            size_str = f"{size}B"
                        elif size < 1024 * 1024:
                            size_str = f"{size / 1024:.1f}KB"
                        else:
                            size_str = f"{size / (1024 * 1024):.1f}MB"
                        lines.append(f"📄 {item.name} ({size_str})")
                except (PermissionError, OSError):
                    lines.append(f"🔒 {item.name} (无法访问)")

            lines.append("")
            lines.append(f"总计: {len(dirs)} 个文件夹, {len(files)} 个文件")

            if truncated:
                lines.append(f"(只显示前 {max_items} 项，共 {len(items)} 项)")

            content = "\n".join(lines)

            metadata = {
                "name": path_obj.name,
                "type": "directory",
                "item_count": len(items),
                "dir_count": len(dirs),
                "file_count": len(files),
                "full_path": str(path_obj.absolute()),
                "truncated": truncated,
            }

            return content, metadata

        except (OSError, PermissionError, ValueError) as e:
            logger.error(f"Error reading directory {directory_path}: {e}", exc_info=True)
            return None, {"error": str(e), "full_path": directory_path}

    @classmethod
    def read_file_content(
        cls,
        full_path: str,
        max_size: ClassVar[int] = 10240,
    ) -> tuple[str | None, Dict[str, Any]]:
        """读取文件内容

        Args:
            full_path: 文件的完整路径
            max_size: 文本文件最大读取大小（字节）

        Returns:
            (文件内容, 元信息)

        """
        try:
            path_obj = Path(full_path)

            # 检查文件是否存在
            if not path_obj.exists():
                return None, {"error": "file_not_found", "full_path": full_path}

            # 如果是目录，使用目录读取方法
            if path_obj.is_dir():
                return cls.read_directory_content(full_path)

            # 获取文件元信息
            metadata = {
                "name": path_obj.name,
                "size": path_obj.stat().st_size,
                "extension": path_obj.suffix,
                "full_path": str(path_obj.absolute()),
                "is_text": cls.is_text_file(full_path),
                "is_binary": cls.is_binary_file(full_path),
            }

            # 如果是文本文件，读取内容
            if metadata["is_text"]:
                # 检查文件大小
                if metadata["size"] > max_size:
                    # 文件太大，只读取部分内容
                    with Path(full_path).open(encoding="utf-8") as f:
                        content = f.read(max_size)
                        content += "\n\n... (文件过大，只显示前 {max_size} 字节)"
                else:
                    with Path(full_path).open(encoding="utf-8") as f:
                        content = f.read()
                return content, metadata

            if metadata["is_binary"]:
                # 二进制文件，不读取内容
                return None, metadata

            # 未知文件类型，尝试读取
            try:
                with Path(full_path).open(encoding="utf-8") as f:
                    content = f.read()
                return content, metadata
            except UnicodeDecodeError:
                return None, metadata

        except (OSError, PermissionError, FileNotFoundError, UnicodeDecodeError) as e:
            logger.error(f"Error reading file {full_path}: {e}", exc_info=True)
            return None, {"error": str(e), "full_path": full_path}

    @classmethod
    def process_message(
        cls,
        message: str,
        workspace_root: str,
        max_file_size: ClassVar[int] = 10240,
    ) -> tuple[str, List[FileReference]]:
        """处理消息中的 @文件引用

        Args:
            message: 原始消息文本
            workspace_root: 工作区根路径
            max_file_size: 单个文件最大读取大小

        Returns:
            (处理后的消息, 文件引用列表)

        """
        file_refs = []
        processed_message = message
        workspace_path = Path(workspace_root).absolute()

        # 提取所有 @文件引用
        file_paths = cls.extract_file_references(message)

        for file_path in file_paths:
            # 构建完整文件路径
            full_path = workspace_path / file_path

            # 读取文件内容
            content, metadata = cls.read_file_content(str(full_path), max_file_size)

            # 创建文件引用对象
            file_ref = FileReference(file_path, content, metadata)
            file_refs.append(file_ref)

            logger.info(
                f"Processed file reference: {file_path} (size: {metadata.get('size', 'unknown')}, type: {metadata.get('extension', 'unknown')})",
            )

        return processed_message, file_refs

    @classmethod
    def enhance_message_with_file_content(cls, message: str, file_refs: List[FileReference]) -> str:
        """将文件引用内容添加到消息中

        Args:
            message: 原始消息
            file_refs: 文件引用列表

        Returns:
            增强后的消息

        """
        if not file_refs:
            return message

        enhanced_parts = [message]

        for file_ref in file_refs:
            if file_ref.content is not None:
                # 检查是否为目录
                if file_ref.metadata.get("type") == "directory":
                    # 目录，添加目录树
                    part = f"\n\n--- 目录: {file_ref.file_path} ---\n{file_ref.content}\n--- 目录结束 ---\n\n"
                else:
                    # 文本文件，添加内容
                    part = f"\n\n--- 文件: {file_ref.file_path} ---\n{file_ref.content}\n--- 文件结束 ---\n\n"
            elif file_ref.metadata.get("is_binary"):
                # 二进制文件，只添加元信息
                size = file_ref.metadata.get("size", 0)
                size_mb = size / (1024 * 1024)
                part = f"\n\n--- 文件: {file_ref.file_path} ---\n类型: 二进制文件\n大小: {size_mb:.2f} MB\n--- 文件结束 ---\n\n"
            else:
                # 文件不存在或读取失败
                error = file_ref.metadata.get("error", "unknown error")
                part = f"\n\n--- 文件: {file_ref.file_path} ---\n错误: {error}\n--- 文件结束 ---\n\n"

            enhanced_parts.append(part)

        return "".join(enhanced_parts)

    @classmethod
    def process_and_enhance(
        cls,
        message: str,
        workspace_root: str,
    ) -> tuple[str, List[FileReference]]:
        """处理消息并增强内容（一步到位）

        Args:
            message: 原始消息
            workspace_root: 工作区根路径

        Returns:
            (增强后的消息, 文件引用列表)

        """
        # 处理文件引用
        processed_message, file_refs = cls.process_message(message, workspace_root)

        # 增强消息内容
        enhanced_message = cls.enhance_message_with_file_content(processed_message, file_refs)

        return enhanced_message, file_refs
