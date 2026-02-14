# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""文件快照管理器（

功能：
1. 自动创建文件快照
2. 恢复文件到历史版本
3. 查看文件修改历史
4. 文件差异对比
"""

import asyncio
import difflib
import gzip
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

# ============================================================================
# 数据类定义
# ============================================================================


class SnapshotStrategy(StrEnum):
    """快照策略"""

    BEFORE_WRITE = "before_write"  # 写入前快照
    BEFORE_EDIT = "before_edit"  # 编辑前快照
    MANUAL = "manual"  # 手动快照
    AUTO = "auto"  # 自动快照
    MILESTONE = "milestone"  # 里程碑快照


@dataclass
class FileSnapshot:
    """文件快照"""

    snapshot_id: str
    file_path: str
    content: str | None  # 文件内容（大文件使用差异）
    checksum: str  # SHA256 哈希
    created_at: datetime
    reason: str  # 创建原因
    size_bytes: int
    compression_type: str = "full"  # "full", "diff", "gzip"
    parent_id: str | None = None  # 父快照（用于增量）
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        # 不序列化 content（单独存储）
        data.pop("content", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], content: str | None = None) -> "FileSnapshot":
        """从字典创建"""
        if isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["content"] = content
        return cls(**data)


@dataclass
class FileSnapshotIndex:
    """文件快照索引"""

    file_path: str
    snapshots: list[FileSnapshot] = field(default_factory=list)
    total_size_bytes: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_snapshot(self, snapshot: FileSnapshot):
        """添加快照"""
        self.snapshots.append(snapshot)
        self.total_size_bytes += snapshot.size_bytes
        self.last_updated = datetime.now(timezone.utc)

    def get_latest_snapshot(self) -> FileSnapshot | None:
        """获取最新快照"""
        return self.snapshots[-1] if self.snapshots else None

    def get_snapshot_by_id(self, snapshot_id: str) -> FileSnapshot | None:
        """根据 ID 获取快照"""
        for snap in self.snapshots:
            if snap.snapshot_id == snapshot_id:
                return snap
        return None


# ============================================================================
# 文件快照管理器
# ============================================================================


class FileSnapshotManager:
    """文件快照管理器

    功能：
    1. 创建文件快照（自动/手动）
    2. 恢复文件到指定快照
    3. 列出文件的所有快照
    4. 获取文件差异
    5. 清理旧快照
    """

    def __init__(
        self,
        workspace_path: str,
        max_snapshots_per_file: int = 50,
        retention_days: int = 30,
        enable_compression: bool = True,
    ):
        """初始化文件快照管理器

        Args:
            workspace_path: 工作区路径
            max_snapshots_per_file: 每个文件最多保留的快照数
            retention_days: 快照保留天数
            enable_compression: 是否启用压缩

        """
        self.workspace_path = Path(workspace_path)
        self.max_snapshots_per_file = max_snapshots_per_file
        self.retention_days = retention_days
        self.enable_compression = enable_compression

        # 快照存储目录
        self.snapshots_dir = self.workspace_path / ".dawei" / "snapshots"
        self.files_dir = self.snapshots_dir / "files"
        self.index_dir = self.snapshots_dir / "index"
        self.locks_dir = self.snapshots_dir / "locks"

        # 创建目录
        self._create_directories()

        # 快照索引缓存
        self._index_cache: dict[str, FileSnapshotIndex] = {}
        self._lock = asyncio.Lock()

        self.logger = logging.getLogger(__name__)

    def _create_directories(self):
        """创建必要的目录"""
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.locks_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # 快照创建
    # -------------------------------------------------------------------------

    def create_snapshot(
        self,
        file_path: str,
        reason: str = "manual",
        strategy: SnapshotStrategy = SnapshotStrategy.MANUAL,
        tags: list[str] | None = None,
    ) -> FileSnapshot | None:
        """创建文件快照

        Args:
            file_path: 文件路径（相对或绝对）
            reason: 快照原因
            strategy: 快照策略
            tags: 标签

        Returns:
            创建的快照对象，失败返回 None

        """
        try:
            # 标准化路径
            file_path = self._normalize_path(file_path)

            # 检查文件是否存在
            if not Path(file_path).exists():
                self.logger.warning(f"File not found: {file_path}")
                return None

            # 读取文件内容
            with Path(file_path, encoding="utf-8").open(errors="ignore") as f:
                content = f.read()

            # 计算校验和
            checksum = self._calculate_checksum(content)

            # 生成快照 ID
            snapshot_id = self._generate_snapshot_id(file_path, strategy)

            # 创建快照对象
            snapshot = FileSnapshot(
                snapshot_id=snapshot_id,
                file_path=file_path,
                content=content,
                checksum=checksum,
                created_at=datetime.now(timezone.utc),
                reason=reason,
                size_bytes=len(content.encode("utf-8")),
                compression_type="gzip" if self.enable_compression else "full",
                tags=tags or [],
            )

            # 保存快照
            self._save_snapshot(snapshot)

            # 更新索引
            self._update_index(snapshot)

            # 清理旧快照
            self._cleanup_old_snapshots(file_path)

            self.logger.info(f"Created snapshot {snapshot_id} for {file_path}")
            return snapshot

        except Exception:
            self.logger.exception("Failed to create snapshot for {file_path}: ")
            return None

    def create_workspace_snapshot(self, reason: str = "workspace") -> list[FileSnapshot]:
        """创建工作区快照（所有文件）

        Args:
            reason: 快照原因

        Returns:
            创建的快照列表

        """
        snapshots = []
        failed_files = []

        # 遍历工作区文件
        for root, dirs, files in Path(self.workspace_path).walk():
            # 跳过隐藏目录和缓存
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]

            for file in files:
                file_path = root / file

                # 跳过二进制文件
                if not self._is_text_file(file_path):
                    continue

                # 创建快照
                try:
                    snapshot = self.create_snapshot(
                        file_path,
                        reason=reason,
                        strategy=SnapshotStrategy.AUTO,
                    )

                    if snapshot:
                        snapshots.append(snapshot)
                    else:
                        failed_files.append(file_path)
                except Exception:
                    self.logger.exception("Failed to create snapshot for {file_path}: ")
                    failed_files.append(file_path)

        if failed_files:
            self.logger.warning(f"Failed to create snapshots for {len(failed_files)} files")
            for failed_file in failed_files:
                self.logger.warning(f"  - {failed_file}")

        self.logger.info(
            f"Created workspace snapshot: {len(snapshots)} files, {len(failed_files)} failed",
        )
        return snapshots

    # -------------------------------------------------------------------------
    # 快照恢复
    # -------------------------------------------------------------------------

    def restore_snapshot(
        self,
        file_path: str,
        snapshot_id: str,
        create_backup: bool = True,
    ) -> bool:
        """恢复文件到指定快照

        Args:
            file_path: 文件路径
            snapshot_id: 快照 ID
            create_backup: 是否在恢复前创建备份

        Returns:
            是否成功

        """
        try:
            # 标准化路径
            file_path = self._normalize_path(file_path)

            # 加载快照
            snapshot = self._load_snapshot(file_path, snapshot_id)
            if not snapshot:
                self.logger.error(f"Snapshot not found: {snapshot_id}")
                return False

            # 可选：创建当前状态的备份
            if create_backup and Path(file_path).exists():
                self.create_snapshot(
                    file_path,
                    reason="before_restore",
                    strategy=SnapshotStrategy.AUTO,
                )

            # 验证快照完整性
            if not self._verify_snapshot(snapshot):
                self.logger.error(f"Snapshot verification failed: {snapshot_id}")
                return False

            # 恢复文件
            with file_path.open("w", encoding="utf-8") as f:
                f.write(snapshot.content)

            self.logger.info(f"Restored {file_path} to snapshot {snapshot_id}")
            return True

        except Exception:
            self.logger.exception("Failed to restore snapshot: ")
            return False

    # -------------------------------------------------------------------------
    # 快照查询
    # -------------------------------------------------------------------------

    def list_snapshots(self, file_path: str) -> list[FileSnapshot]:
        """列出文件的所有快照

        Args:
            file_path: 文件路径

        Returns:
            快照列表（按创建时间倒序）

        """
        # 标准化路径
        file_path = self._normalize_path(file_path)

        # 加载索引
        index = self._load_index(file_path)
        if not index:
            return []

        # 按创建时间倒序排序
        return sorted(index.snapshots, key=lambda s: s.created_at, reverse=True)

    def get_snapshot(self, file_path: str, snapshot_id: str) -> FileSnapshot | None:
        """获取指定快照

        Args:
            file_path: 文件路径
            snapshot_id: 快照 ID

        Returns:
            快照对象

        """
        # 标准化路径
        file_path = self._normalize_path(file_path)

        # 加载索引
        index = self._load_index(file_path)
        if not index:
            return None

        # 查找快照
        snapshot = index.get_snapshot_by_id(snapshot_id)
        if not snapshot:
            return None

        # 加载内容
        return self._load_snapshot(file_path, snapshot_id)

    def get_diff(self, file_path: str, snapshot_id: str) -> str:
        """获取当前文件与快照的差异

        Args:
            file_path: 文件路径
            snapshot_id: 快照 ID

        Returns:
            统一差异格式（unified diff）

        """
        # 加载快照
        snapshot = self.get_snapshot(file_path, snapshot_id)
        if not snapshot:
            return "Error: Snapshot not found"

        # 读取当前文件
        if not Path(file_path).exists():
            current_content = ""
        else:
            with Path(file_path, encoding="utf-8").open(errors="ignore") as f:
                current_content = f.read()

        # 生成差异
        old_lines = snapshot.content.splitlines(keepends=True)
        new_lines = current_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"{file_path} (snapshot {snapshot_id})",
            tofile=f"{file_path} (current)",
            lineterm="",
        )

        return "".join(diff)

    # -------------------------------------------------------------------------
    # 存储管理
    # -------------------------------------------------------------------------

    def _save_snapshot(self, snapshot: FileSnapshot):
        """保存快照到磁盘"""
        try:
            # 获取文件哈希（用于目录组织）
            file_hash = hashlib.md5(snapshot.file_path.encode()).hexdigest()

            # 快照目录
            snapshot_dir = self.files_dir / file_hash
            snapshot_dir.mkdir(exist_ok=True)

            # 快照元数据文件
            metadata_file = snapshot_dir / f"{snapshot.snapshot_id}.json"

            # 快照内容文件
            content_file = snapshot_dir / f"{snapshot.snapshot_id}.content"

            # 保存元数据
            metadata = snapshot.to_dict()
            with metadata_file.open("w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            # 保存内容
            if self.enable_compression:
                # 使用 gzip 压缩
                with gzip.open(content_file, "wt", encoding="utf-8") as f:
                    f.write(snapshot.content)
            else:
                # 不压缩
                with content_file.open("w", encoding="utf-8") as f:
                    f.write(snapshot.content)

        except Exception:
            self.logger.exception("Failed to save snapshot {snapshot.snapshot_id}: ")
            # 清理可能部分创建的文件
            try:
                file_hash = hashlib.md5(snapshot.file_path.encode()).hexdigest()
                snapshot_dir = self.files_dir / file_hash
                metadata_file = snapshot_dir / f"{snapshot.snapshot_id}.json"
                content_file = snapshot_dir / f"{snapshot.snapshot_id}.content"

                if metadata_file.exists():
                    metadata_file.unlink()
                if content_file.exists():
                    content_file.unlink()
            except Exception as cleanup_error:
                self.logger.exception(f"Failed to cleanup partially created snapshot: {cleanup_error}")
            raise

    def _load_snapshot(self, file_path: str, snapshot_id: str) -> FileSnapshot | None:
        """从磁盘加载快照"""
        # 获取文件哈希
        file_hash = hashlib.md5(file_path.encode()).hexdigest()

        # 快照目录
        snapshot_dir = self.files_dir / file_hash

        # 元数据文件
        metadata_file = snapshot_dir / f"{snapshot_id}.json"
        if not metadata_file.exists():
            return None

        # 加载元数据
        with Path(metadata_file).open(encoding="utf-8") as f:
            metadata = json.load(f)

        # 加载内容
        content_file = snapshot_dir / f"{snapshot_id}.content"
        if not content_file.exists():
            return None

        if self.enable_compression:
            with gzip.open(content_file, "rt", encoding="utf-8") as f:
                content = f.read()
        else:
            with Path(content_file).open(encoding="utf-8") as f:
                content = f.read()

        # 创建快照对象
        return FileSnapshot.from_dict(metadata, content)

    def _load_index(self, file_path: str) -> FileSnapshotIndex | None:
        """加载文件快照索引"""
        # 检查缓存
        if file_path in self._index_cache:
            return self._index_cache[file_path]

        # 获取文件哈希
        file_hash = hashlib.md5(file_path.encode()).hexdigest()

        # 索引文件
        index_file = self.index_dir / f"{file_hash}.json"

        if not index_file.exists():
            return None

        # 加载索引
        with Path(index_file).open(encoding="utf-8") as f:
            data = json.load(f)

        # 重建索引对象
        index = FileSnapshotIndex(
            file_path=data["file_path"],
            total_size_bytes=data["total_size_bytes"],
            last_updated=datetime.fromisoformat(data["last_updated"]),
        )

        # 重建快照列表（不加载内容）
        for snap_data in data["snapshots"]:
            snapshot = FileSnapshot.from_dict(snap_data, content=None)
            index.snapshots.append(snapshot)

        # 缓存
        self._index_cache[file_path] = index

        return index

    def _update_index(self, snapshot: FileSnapshot):
        """更新快照索引"""
        # 获取文件哈希
        file_hash = hashlib.md5(snapshot.file_path.encode()).hexdigest()

        # 加载或创建索引
        index = self._load_index(snapshot.file_path)
        if not index:
            index = FileSnapshotIndex(file_path=snapshot.file_path)

        # 添加快照
        index.add_snapshot(snapshot)

        # 保存索引
        index_file = self.index_dir / f"{file_hash}.json"

        index_data = {
            "file_path": index.file_path,
            "total_size_bytes": index.total_size_bytes,
            "last_updated": index.last_updated.isoformat(),
            "snapshots": [snap.to_dict() for snap in index.snapshots],
        }

        with index_file.open("w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)

        # 更新缓存
        self._index_cache[snapshot.file_path] = index

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def _normalize_path(self, file_path: str) -> str:
        """标准化文件路径"""
        path = Path(file_path)

        # 如果是相对路径，相对于工作区
        if not path.is_absolute():
            path = self.workspace_path / path

        return str(path.resolve())

    def _generate_snapshot_id(self, file_path: str, strategy: SnapshotStrategy) -> str:
        """生成快照 ID"""
        # 【修复】添加微秒级时间戳，避免同一秒内创建多个快照时 ID 碰撞
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")  # 包含微秒
        file_hash = hashlib.md5(file_path.encode()).hexdigest()[:8]
        return f"snap_{strategy.value}_{file_hash}_{timestamp}"

    def _calculate_checksum(self, content: str) -> str:
        """计算内容校验和"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _verify_snapshot(self, snapshot: FileSnapshot) -> bool:
        """验证快照完整性"""
        if not snapshot.content:
            return False

        # 验证校验和
        current_checksum = self._calculate_checksum(snapshot.content)
        if current_checksum != snapshot.checksum:
            self.logger.error(f"Checksum mismatch for snapshot {snapshot.snapshot_id}")
            return False

        # 验证大小
        size = len(snapshot.content.encode("utf-8"))
        if size != snapshot.size_bytes:
            self.logger.error(f"Size mismatch for snapshot {snapshot.snapshot_id}")
            return False

        return True

    def _is_text_file(self, file_path: str) -> bool:
        """判断是否为文本文件"""
        # 根据扩展名判断
        text_extensions = {
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".vue",
            ".html",
            ".css",
            ".json",
            ".xml",
            ".yaml",
            ".yml",
            ".md",
            ".txt",
            ".csv",
            ".sql",
            ".sh",
            ".bat",
            ".ps1",
            ".toml",
            ".ini",
            ".cfg",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".java",
            ".go",
            ".rs",
            ".rb",
            ".php",
        }

        ext = Path(file_path).suffix.lower()
        return ext in text_extensions

    def _cleanup_old_snapshots(self, file_path: str):
        """清理旧快照"""
        # 加载索引
        index = self._load_index(file_path)
        if not index:
            return

        # 1. 按数量限制清理
        if len(index.snapshots) > self.max_snapshots_per_file:
            # 删除最旧的快照
            snapshots_to_remove = index.snapshots[: -self.max_snapshots_per_file]
            for snapshot in snapshots_to_remove:
                self._delete_snapshot(snapshot)
            index.snapshots = index.snapshots[-self.max_snapshots_per_file :]

        # 2. 按时间清理
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        index.snapshots = [snap for snap in index.snapshots if snap.created_at > cutoff_time or snap.strategy == SnapshotStrategy.MILESTONE]

        # 保存更新后的索引
        file_hash = hashlib.md5(file_path.encode()).hexdigest()
        index_file = self.index_dir / f"{file_hash}.json"

        index_data = {
            "file_path": index.file_path,
            "total_size_bytes": index.total_size_bytes,
            "last_updated": index.last_updated.isoformat(),
            "snapshots": [snap.to_dict() for snap in index.snapshots],
        }

        with index_file.open("w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)

    def _delete_snapshot(self, snapshot: FileSnapshot):
        """删除快照文件"""
        file_hash = hashlib.md5(snapshot.file_path.encode()).hexdigest()
        snapshot_dir = self.files_dir / file_hash

        # 删除元数据文件
        metadata_file = snapshot_dir / f"{snapshot.snapshot_id}.json"
        if metadata_file.exists():
            metadata_file.unlink()

        # 删除内容文件
        content_file = snapshot_dir / f"{snapshot.snapshot_id}.content"
        if content_file.exists():
            content_file.unlink()

        self.logger.info(f"Deleted snapshot {snapshot.snapshot_id}")

    # -------------------------------------------------------------------------
    # 批量操作
    # -------------------------------------------------------------------------

    def get_storage_stats(self) -> dict[str, Any]:
        """获取存储统计信息"""
        total_size = 0
        total_snapshots = 0
        file_count = 0
        corrupted_files = 0

        for index_file in self.index_dir.glob("*.json"):
            try:
                with Path(index_file).open(encoding="utf-8") as f:
                    data = json.load(f)
                    total_size += data.get("total_size_bytes", 0)
                    total_snapshots += len(data.get("snapshots", []))
                    file_count += 1
            except (json.JSONDecodeError, OSError):
                self.logger.exception("Failed to read index file {index_file}: ")
                corrupted_files += 1

        return {
            "total_snapshots": total_snapshots,
            "total_files": file_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "corrupted_files": corrupted_files,
        }

    def clear_all_snapshots(self) -> int:
        """清除所有快照"""
        count = 0

        # 删除所有快照文件
        for snapshot_dir in self.files_dir.iterdir():
            if snapshot_dir.is_dir():
                for file in snapshot_dir.glob("*"):
                    file.unlink()
                snapshot_dir.rmdir()
                count += 1

        # 删除所有索引
        for index_file in self.index_dir.glob("*.json"):
            index_file.unlink()

        # 清空缓存
        self._index_cache.clear()

        self.logger.info(f"Cleared {count} snapshot directories")
        return count
