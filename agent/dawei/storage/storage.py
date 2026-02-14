# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""存储提供者抽象基类"""

from abc import ABC, abstractmethod
from typing import Any


class Storage(ABC):
    """定义了与文件系统交互的统一接口。
    所有与存储相关的操作都应通过此接口的实现来完成。
    """

    @abstractmethod
    async def list_directory(
        self,
        path: str,
        recursive: bool = False,
        include_hidden: bool = False,
        max_depth: int = 3,
    ) -> list[dict[str, Any]]:
        """列出目录内容"""

    @abstractmethod
    async def get_file_content(self, path: str, max_size: int = -1) -> str:
        """获取文件内容"""

    @abstractmethod
    async def write_file_content(self, path: str, content: str) -> bool:
        """写入或更新文件内容"""

    @abstractmethod
    async def create_directory(self, path: str) -> bool:
        """创建目录"""

    @abstractmethod
    async def rename(self, old_path: str, new_path: str) -> bool:
        """重命名文件或目录"""

    @abstractmethod
    async def move(self, source_path: str, destination_path: str) -> bool:
        """移动文件或目录"""

    @abstractmethod
    async def delete(self, path: str, recursive: bool = False) -> bool:
        """删除文件或目录"""

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """检查文件或目录是否存在"""

    @abstractmethod
    async def is_directory(self, path: str) -> bool:
        """检查路径是否为目录"""

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """Reads the content of a file."""

    @abstractmethod
    async def write_file(self, path: str, content: str) -> None:
        """Writes content to a file, creating it if it doesn't exist."""

    @abstractmethod
    async def read_binary_file(self, path: str) -> bytes:
        """Reads the content of a binary file (e.g., images, PDFs)."""
