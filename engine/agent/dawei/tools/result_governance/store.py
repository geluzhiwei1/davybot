# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""L2 — 结果快照存储

缓存被截断的原始结果，供 expand 工具二次访问。
含 X2 安全加固（UUID v4 ID + 归属校验）+ X3 脱敏。
"""

import logging
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from .sanitizer import sanitize_tool_output

logger = logging.getLogger(__name__)

_MAX_SNAPSHOTS = 200  # LRU 容量
_MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024  # 2MB 单条上限


@dataclass
class ToolResultSnapshot:
    """工具结果快照。"""

    snapshot_id: str
    tool_name: str
    raw_result: Any  # 原始未截断结果（内存中，TTL 后清除）
    redacted_result: Any  # 脱敏版本（REST API 返回此版本）
    timestamp: datetime
    user_id: str = ""
    workspace_id: str = ""
    policy_name: str = ""


class ResultSnapshotStore:
    """缓存被截断的原始结果，供 expand 工具二次访问。

    - Key: snapshot_id (UUID v4)
    - Value: ToolResultSnapshot
    - TTL: 24 小时（默认）
    - 容量: LRU maxsize=200 条，单条最大 2MB
    """

    def __init__(self, default_ttl_hours: int = 24, max_snapshots: int = _MAX_SNAPSHOTS):
        self._default_ttl = timedelta(hours=default_ttl_hours)
        self._max_snapshots = max_snapshots
        self._store: OrderedDict[str, ToolResultSnapshot] = OrderedDict()
        self._lock = threading.Lock()

    def put(
        self,
        tool_name: str,
        raw_result: Any,
        *,
        user_id: str = "",
        workspace_id: str = "",
        policy_name: str = "",
    ) -> str | None:
        """存入快照，返回 snapshot_id。超 2MB 的不存（返回 None）。"""
        try:
            raw_str = str(raw_result)
            if len(raw_str.encode("utf-8")) > _MAX_SNAPSHOT_BYTES:
                logger.warning(f"Snapshot too large for {tool_name}, skipping store")
                return None

            snapshot_id = str(uuid.uuid4())

            # X3 修复：脱敏后存储
            redacted = sanitize_tool_output(raw_result)

            snapshot = ToolResultSnapshot(
                snapshot_id=snapshot_id,
                tool_name=tool_name,
                raw_result=raw_result,
                redacted_result=redacted,
                timestamp=datetime.now(UTC),
                user_id=user_id,
                workspace_id=workspace_id,
                policy_name=policy_name,
            )

            with self._lock:
                # LRU 淘汰
                while len(self._store) >= self._max_snapshots:
                    self._store.popitem(last=False)
                self._store[snapshot_id] = snapshot

            logger.debug(f"Snapshot stored: {snapshot_id} for tool={tool_name}")
            return snapshot_id

        except Exception as e:
            logger.warning(f"Snapshot store failed for {tool_name}: {e}")
            return None

    def get(self, snapshot_id: str) -> ToolResultSnapshot | None:
        """获取快照。返回 None = 不存在或已过期。"""
        with self._lock:
            snapshot = self._store.get(snapshot_id)
            if snapshot is None:
                return None

            # TTL 检查
            if datetime.now(UTC) - snapshot.timestamp > self._default_ttl:
                del self._store[snapshot_id]
                logger.debug(f"Snapshot expired: {snapshot_id}")
                return None

            # LRU 更新：移到末尾
            self._store.move_to_end(snapshot_id)
            return snapshot

    def cleanup_expired(self) -> int:
        """清理过期快照。返回清理数量。"""
        now = datetime.now(UTC)
        expired_ids = []
        with self._lock:
            for sid, snap in self._store.items():
                if now - snap.timestamp > self._default_ttl:
                    expired_ids.append(sid)
            for sid in expired_ids:
                del self._store[sid]

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired snapshots")
        return len(expired_ids)

    def stats(self) -> dict[str, Any]:
        """获取快照存储统计。"""
        with self._lock:
            return {
                "total_snapshots": len(self._store),
                "max_snapshots": self._max_snapshots,
                "ttl_hours": self._default_ttl.total_seconds() / 3600,
            }


# 单例
_snapshot_store: ResultSnapshotStore | None = None


def get_snapshot_store() -> ResultSnapshotStore:
    """获取全局 ResultSnapshotStore 单例。"""
    global _snapshot_store
    if _snapshot_store is None:
        _snapshot_store = ResultSnapshotStore()
    return _snapshot_store
