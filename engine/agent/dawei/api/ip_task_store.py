# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""
IP 任务持久化存储。

用 dict 子类包装 JSON 文件持久化，对调用方完全透明：
  - task_store[task_id] = {...}   → 同步写入 {DAWEI_HOME}/ip_tasks/{task_id}.json
  - task_store.get(task_id)       → 先查内存，未命中查磁盘
  - task_store[task_id] 读取       → 同上
  - del task_store[task_id]       → 删除磁盘文件
  - task_store.load()             → 启动时批量加载到内存

这样 ip_agent_executor.execute_ip_task_background 无需任何改动。
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _ip_tasks_dir() -> Path:
    """返回 IP 任务持久化目录（懒创建）。"""
    from dawei import get_dawei_home

    d = get_dawei_home() / "ip_tasks"
    d.mkdir(parents=True, exist_ok=True)
    return d


class PersistentTaskDict(dict):
    """dict 子类：每次写操作同步持久化到 JSON 文件。

    线程安全：写文件加锁，避免并发写同一 task 产生截断。
    内存仍是主读路径（热数据），磁盘用于跨重启恢复。
    """

    def __init__(self) -> None:
        super().__init__()
        self._dir = _ip_tasks_dir()
        self._lock = threading.Lock()

    # ── 写路径：内存 + 磁盘双写 ──────────────────────────────

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self._persist(key, value)

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        (self._dir / f"{key}.json").unlink(missing_ok=True)

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        super().update(*args, **kwargs)
        merged = dict(*args, **kwargs)
        for k, v in merged.items():
            self._persist(k, v)

    # ── 读路径：内存未命中时回查磁盘 ─────────────────────────

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        val = super().get(key)
        if val is not None:
            return val
        loaded = self._load_one(key)
        if loaded is not None:
            # 用 dict.__setitem__ 避免再次触发 _persist
            dict.__setitem__(self, key, loaded)
            return loaded
        return default

    def __getitem__(self, key: str) -> Any:
        try:
            return super().__getitem__(key)
        except KeyError:
            loaded = self._load_one(key)
            if loaded is not None:
                dict.__setitem__(self, key, loaded)
                return loaded
            raise

    def __contains__(self, key: object) -> bool:  # type: ignore[override]
        if super().__contains__(key):
            return True
        return self._load_one(str(key)) is not None  # type: ignore[arg-type]

    # ── 持久化原语 ──────────────────────────────────────────

    def _persist(self, key: str, value: Any) -> None:
        try:
            path = self._dir / f"{key}.json"
            data = json.dumps(value, default=str, ensure_ascii=False)
            with self._lock:
                path.write_text(data, encoding="utf-8")
        except (TypeError, ValueError, OSError) as e:
            logger.warning(f"[IP-TASK-STORE] Failed to persist task {key}: {e}")

    def _load_one(self, key: str) -> dict[str, Any] | None:
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            with path.open(encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[IP-TASK-STORE] Corrupt task file {key}: {e}")
            return None

    # ── 启动恢复 ────────────────────────────────────────────

    def load(self) -> int:
        """启动时批量加载磁盘任务到内存，返回加载数量。"""
        count = 0
        for path in self._dir.glob("*.json"):
            try:
                with path.open(encoding="utf-8") as f:
                    data = json.load(f)
                dict.__setitem__(self, path.stem, data)
                count += 1
            except (json.JSONDecodeError, OSError):
                continue
        if count:
            logger.info(f"[IP-TASK-STORE] Loaded {count} persisted tasks from disk")
        return count

    # ── 清理 ────────────────────────────────────────────────

    def cleanup_expired(self, max_age_seconds: int = 3600) -> int:
        """清理超期任务（内存 + 磁盘）。返回清理数量。"""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        expired_keys: list[str] = []
        for tid, task in list(self.items()):
            created = task.get("createdAt")
            if not created:
                continue
            try:
                age = (now - datetime.fromisoformat(created)).total_seconds()
                if age > max_age_seconds:
                    expired_keys.append(tid)
            except (ValueError, TypeError):
                continue
        for tid in expired_keys:
            self.pop(tid, None)
            (self._dir / f"{tid}.json").unlink(missing_ok=True)
        if expired_keys:
            logger.info(
                f"[IP-TASK-STORE] Cleaned {len(expired_keys)} expired tasks "
                f"(>{max_age_seconds}s)"
            )
        return len(expired_keys)


# 模块级单例 —— 替代 ip_routes.py 原来的 _task_store: dict
task_store = PersistentTaskDict()
