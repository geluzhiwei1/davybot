# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""本地文件系统存储提供者"""

import asyncio
import shutil
from pathlib import Path
from typing import Any

from dawei.storage.storage import Storage


class LocalFileSystemStorage(Storage):
    """使用本地文件系统实现存储接口."""

    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir).resolve()
        if not self.root_dir.exists():
            self.root_dir.mkdir(parents=True, exist_ok=True)

    def _get_safe_path(self, user_path: str) -> Path:
        """将用户提供的路径转换为安全的、绝对的路径,并防止路径穿越."""
        # 移除前导斜杠以防止被解释为绝对路径
        clean_path = user_path.lstrip("/")
        absolute_path = (self.root_dir / clean_path).resolve()

        # 验证路径是否在 root_dir 内
        if not str(absolute_path).startswith(str(self.root_dir)):
            raise PermissionError("不允许访问根目录之外的路径.")

        return absolute_path

    async def list_directory(
        self,
        path: str,
        recursive: bool = False,
        include_hidden: bool = False,
        max_depth: int = 3,
    ) -> list[dict[str, Any]]:
        safe_path = self._get_safe_path(path)
        if not safe_path.is_dir():
            raise FileNotFoundError(f"目录不存在: {path}")

        results = []

        def _walk(current_path: Path, current_depth: int):
            if current_depth > max_depth:
                return

            for entry in current_path.iterdir():
                if not include_hidden and entry.name.startswith("."):
                    continue

                rel_path = entry.relative_to(self.root_dir).as_posix()
                is_dir = entry.is_dir()

                file_info = {
                    "name": entry.name,
                    "path": rel_path,
                    "is_directory": is_dir,
                    "size": entry.stat().st_size if not is_dir else 0,
                    "last_modified": entry.stat().st_mtime,
                }
                results.append(file_info)

                if is_dir and recursive:
                    _walk(entry, current_depth + 1)

        _walk(safe_path, 1)
        return results

    async def get_file_content(self, path: str, max_size: int = -1) -> str:
        safe_path = self._get_safe_path(path)
        if not safe_path.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")

        if max_size > 0 and safe_path.stat().st_size > max_size:
            raise ValueError(f"文件大小超过最大限制 {max_size} 字节.")

        try:
            with Path(safe_path).open(encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError as e:
            raise ValueError(f"文件编码错误,无法以 UTF-8 编码读取文件: {e}")
        except Exception as e:
            raise OSError(f"读取文件失败: {e}")

    async def write_file_content(self, path: str, content: str) -> bool:
        import logging

        logger = logging.getLogger(__name__)

        safe_path = self._get_safe_path(path)
        logger.debug(f"Writing to path: {safe_path}, content length: {len(content)}")

        safe_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with safe_path.open("w", encoding="utf-8") as f:
                f.write(content)
        except UnicodeEncodeError as e:
            raise ValueError(f"文件编码错误,无法以 UTF-8 编码写入文件: {e}") from e
        except OSError as e:
            raise OSError(f"写入文件失败: {e}") from e

        logger.debug(f"Successfully wrote {len(content)} bytes to {safe_path}")
        return True

    async def create_directory(self, path: str) -> bool:
        safe_path = self._get_safe_path(path)
        safe_path.mkdir(parents=True, exist_ok=True)
        return True

    async def rename(self, old_path: str, new_path: str) -> bool:
        safe_old_path = self._get_safe_path(old_path)
        safe_new_path = self._get_safe_path(new_path)

        # Windows 文件锁定重试逻辑
        max_retries = 5
        retry_delay = 0.05  # 50ms

        for attempt in range(max_retries):
            try:
                safe_old_path.rename(safe_new_path)
                return True
            except (OSError, PermissionError):
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    # 最后一次重试失败,尝试备用策略
                    if safe_new_path.exists():
                        safe_new_path.unlink()
                    safe_old_path.rename(safe_new_path)
                    return True
        # All retries exhausted - raise exception instead of returning None
        raise OSError(f"Failed to rename '{old_path}' to '{new_path}' after {max_retries} attempts")

    async def move(self, source_path: str, destination_path: str) -> bool:
        safe_source = self._get_safe_path(source_path)
        safe_destination = self._get_safe_path(destination_path)

        # Windows 文件锁定重试逻辑
        max_retries = 5
        retry_delay = 0.05  # 50ms

        for attempt in range(max_retries):
            try:
                shutil.move(str(safe_source), str(safe_destination))
                return True
            except (OSError, PermissionError):
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    # 最后一次重试失败,尝试备用策略
                    if safe_destination.exists():
                        if safe_destination.is_dir():
                            shutil.rmtree(safe_destination)
                        else:
                            safe_destination.unlink()
                    shutil.move(str(safe_source), str(safe_destination))
                    return True
        # All retries exhausted - raise exception instead of returning None
        raise OSError(f"Failed to move '{source_path}' to '{destination_path}' after {max_retries} attempts")

    async def delete(self, path: str, recursive: bool = False) -> bool:
        safe_path = self._get_safe_path(path)
        if not safe_path.exists():
            raise FileNotFoundError(f"路径不存在: {path}") from None

        if safe_path.is_dir():
            if recursive:
                shutil.rmtree(safe_path)
            else:
                # 检查目录是否为空
                if any(safe_path.iterdir()):
                    raise ValueError("目录不为空,无法非递归删除.") from None
                safe_path.rmdir()
        else:
            safe_path.unlink()
        return True

    async def exists(self, path: str) -> bool:
        safe_path = self._get_safe_path(path)
        return safe_path.exists()

    async def is_directory(self, path: str) -> bool:
        safe_path = self._get_safe_path(path)
        return safe_path.is_dir()

    async def read_file(self, path: str) -> str:
        """Reads the content of a file."""
        safe_path = self._get_safe_path(path)
        try:
            if not safe_path.is_file():
                raise FileNotFoundError(f"File not found at path: {path}") from None
            return safe_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        except Exception as e:
            raise OSError(f"Could not read file at path: {path}. Error: {e}")

    async def write_file(self, path: str, content: str) -> None:
        """Writes content to a file, creating it if it doesn't exist."""
        safe_path = self._get_safe_path(path)
        try:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            safe_path.write_text(content, encoding="utf-8")
        except Exception as e:
            raise OSError(f"Could not write to file at path: {path}. Error: {e}")

    async def read_binary_file(self, path: str) -> bytes:
        """Reads the content of a binary file (e.g., images, PDFs)."""
        safe_path = self._get_safe_path(path)
        try:
            if not safe_path.is_file():
                raise FileNotFoundError(f"File not found at path: {path}") from None
            return safe_path.read_bytes()
        except FileNotFoundError:
            raise
        except Exception as e:
            raise OSError(f"Could not read binary file at path: {path}. Error: {e}")
