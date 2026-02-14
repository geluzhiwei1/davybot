# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Plan Mode 文件管理器

管理 plan mode 下的计划文件创建、读取、更新
"""

import logging
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PlanFileManager:
    """Plan 文件管理器"""

    def __init__(self, workspace_root: Path):
        """初始化 Plan 文件管理器

        Args:
            workspace_root: 工作区根目录

        """
        self.workspace_root = Path(workspace_root)
        self.plans_dir = self.workspace_root / ".dawei" / "plans"
        self._ensure_plans_directory()

    def _ensure_plans_directory(self):
        """确保计划目录存在

        Raises:
            OSError: 如果无法创建目录

        """
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Plans directory ensured: {self.plans_dir}")

    def get_plan_path(self, session_id: str, timestamp: int | None = None) -> Path:
        """获取计划文件路径

        Args:
            session_id: 会话 ID
            timestamp: 时间戳（可选）

        Returns:
            计划文件的完整路径

        """
        if timestamp is None:
            timestamp = int(datetime.now(UTC).timestamp())

        # 格式: {timestamp}-{session_id}.md
        filename = f"{timestamp}-{session_id}.md"
        return self.plans_dir / filename

    def create_plan_file(
        self,
        session_id: str,
        title: str,
        content: str | None = None,
        timestamp: int | None = None,
    ) -> Path:
        """创建新的计划文件

        Args:
            session_id: 会话 ID
            title: 计划标题
            content: 初始内容（可选，如果为None则使用默认模板）
            timestamp: 时间戳（可选）

        Returns:
            创建的文件路径

        """
        plan_path = self.get_plan_path(session_id, timestamp)

        # 如果没有提供内容，使用默认模板
        if content is None:
            creation_time = datetime.now(UTC).isoformat()
            content = f"""# {title}

**Created**: {creation_time}
**Session**: {session_id}

---

## Overview
<!-- Brief description of what this plan covers -->

---

## Phase 1: Understanding
<!-- User requirements and exploration results -->

---

## Phase 2: Design
<!-- Implementation approach -->

---

## Phase 3: Review
<!-- Alternative approaches considered -->

---

## Implementation Plan

### Critical Files to Modify
<!-- List of files that will be modified -->

### Step-by-Step Implementation
<!-- Detailed implementation steps -->

---

## Verification
<!-- How to test the implementation -->

"""

        # 直接写入，任何错误都会抛出异常（fail-fast）
        plan_path.write_text(content, encoding="utf-8")
        logger.info(f"Created plan file: {plan_path}")
        return plan_path

    def read_plan_file(self, session_id: str, timestamp: int | None = None) -> str:
        """读取计划文件

        Args:
            session_id: 会话 ID
            timestamp: 时间戳（可选，如果不确定会查找最新的）

        Returns:
            文件内容

        Raises:
            FileNotFoundError: 如果计划文件不存在
            IOError: 如果文件读取失败

        """
        plan_path = self._get_latest_plan_path(session_id, timestamp)

        if plan_path is None or not plan_path.exists():
            logger.warning(f"Plan file not found for session: {session_id}")
            raise FileNotFoundError(f"Plan file not found for session: {session_id}")

        # 直接读取，任何错误都会抛出异常（fail-fast）
        content = plan_path.read_text(encoding="utf-8")
        logger.debug(f"Read plan file: {plan_path}")
        return content

    def update_plan_file(
        self,
        session_id: str,
        content: str,
        timestamp: int | None = None,
    ) -> None:
        """更新计划文件

        Args:
            session_id: 会话 ID
            content: 新内容
            timestamp: 时间戳（可选）

        Raises:
            FileNotFoundError: 如果无法找到或创建计划文件
            IOError: 如果文件写入失败

        """
        plan_path = self._get_latest_plan_path(session_id, timestamp)

        if plan_path is None:
            # 如果找不到现有文件，创建新文件
            logger.info(f"No existing plan file, creating new one for session: {session_id}")
            self.create_plan_file(session_id, "Plan", content)
            return

        # 直接写入，任何错误都会抛出异常（fail-fast）
        plan_path.write_text(content, encoding="utf-8")
        logger.info(f"Updated plan file: {plan_path}")

    def _get_latest_plan_path(
        self,
        session_id: str,
        timestamp: int | None = None,
    ) -> Path | None:
        """获取最新的计划文件路径

        Args:
            session_id: 会话 ID
            timestamp: 时间戳（可选）

        Returns:
            计划文件路径，如果找不到返回 None

        Raises:
            OSError: 如果文件系统操作失败

        """
        if timestamp is not None:
            # 使用指定的时间戳
            filename = f"{timestamp}-{session_id}.md"
            plan_path = self.plans_dir / filename
            return plan_path if plan_path.exists() else None

        # 查找该会话的最新计划文件
        # 直接操作，任何文件系统错误都会抛出（fail-fast）
        try:
            plan_files = list(self.plans_dir.glob(f"*-{session_id}.md"))
        except OSError as e:
            logger.warning(f"Failed to access plans directory: {e}")
            return None

        if not plan_files:
            return None

        # 按修改时间排序，返回最新的
        try:
            plan_path = max(plan_files, key=lambda p: p.stat().st_mtime)
        except (OSError, ValueError) as e:
            logger.warning(f"Failed to get latest plan file: {e}")
            return None

        return plan_path

    def list_plan_files(self, limit: int = 10) -> list[dict[str, Any]]:
        """列出计划文件

        Args:
            limit: 最多返回的文件数

        Returns:
            计划文件信息列表

        Raises:
            OSError: 如果文件系统操作失败

        """
        # 直接操作，任何错误都会抛出异常（fail-fast）
        try:
            plan_files = list(self.plans_dir.glob("*.md"))
        except OSError as e:
            logger.warning(f"Failed to access plans directory: {e}")
            return []

        # 按修改时间排序，返回最新的
        valid_plan_files = []
        for plan_path in plan_files:
            try:
                stat = plan_path.stat()
                valid_plan_files.append(plan_path)
            except OSError as e:
                logger.warning(f"Failed to get stats for plan file {plan_path}: {e}")
                continue

        plan_files = sorted(valid_plan_files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]

        result = []
        for plan_path in plan_files:
            try:
                stat = plan_path.stat()
                # 解析文件名: {timestamp}-{session_id}.md
                stem = plan_path.stem  # 去掉 .md
                parts = stem.split("-", 1)

                result.append(
                    {
                        "path": str(plan_path.relative_to(self.workspace_root)),
                        "absolute_path": str(plan_path),
                        "session_id": parts[1] if len(parts) > 1 else "unknown",
                        "timestamp": (int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else None),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    },
                )
            except OSError as e:
                logger.warning(f"Failed to get details for plan file {plan_path}: {e}")
                continue

        return result

    def plan_file_exists(self, session_id: str) -> bool:
        """检查会话的计划文件是否存在

        Args:
            session_id: 会话 ID

        Returns:
            是否存在计划文件

        """
        plan_path = self._get_latest_plan_path(session_id)
        return plan_path is not None and plan_path.exists()

    def get_plan_metadata(self, session_id: str) -> dict[str, Any]:
        """获取计划文件的元数据

        Args:
            session_id: 会话 ID

        Returns:
            元数据字典

        Raises:
            FileNotFoundError: 如果计划文件不存在
            OSError: 如果文件系统操作失败

        """
        plan_path = self._get_latest_plan_path(session_id)

        if plan_path is None or not plan_path.exists():
            raise FileNotFoundError(f"Plan file not found for session: {session_id}")

        # 直接操作，任何错误都会抛出异常（fail-fast）
        stat = plan_path.stat()
        stem = plan_path.stem
        parts = stem.split("-", 1)

        return {
            "path": str(plan_path.relative_to(self.workspace_root)),
            "session_id": session_id,
            "timestamp": int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else None,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
