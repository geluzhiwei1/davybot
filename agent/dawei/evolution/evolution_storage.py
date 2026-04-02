# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Evolution Storage Manager

管理evolution cycle的文件读写，复用WorkspacePersistenceManager的原子写入机制。

目录结构：
.dawei/
├── dao.md               # Workspace goals and success criteria
├── evolution-001/             # Cycle 1
│   ├── metadata.json          # Cycle state
│   ├── plan.md
│   ├── do.md
│   ├── check.md
│   └── action.md
├── evolution-002/             # Cycle 2
│   ├── metadata.json
│   ├── plan.md
│   ├── do.md
│   ├── check.md
│   └── action.md
└── evolution-current -> evolution-002  # Symlink to current cycle
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dawei.core.datetime_compat import UTC
from dawei.evolution.exceptions import EvolutionStorageError
from dawei.workspace.persistence_manager import WorkspacePersistenceManager

logger = logging.getLogger(__name__)


class EvolutionStorage:
    """Evolution Cycle存储管理器

    负责管理evolution cycle的所有文件操作：
    - 创建cycle目录
    - 保存/加载metadata.json
    - 保存/加载phase输出（plan.md, do.md, check.md, action.md）
    - 枚举所有cycles
    - 加载dao.md

    Attributes:
        workspace: UserWorkspace实例
        _pm: WorkspacePersistenceManager实例
        base: .dawei目录路径
    """

    BASE_DIR = ".dawei"
    PREFIX = "evolution-"
    CURRENT_LINK = "evolution-current"
    WORKSPACE_MD = "/../dao.md"

    def __init__(self, workspace):
        """初始化EvolutionStorage

        Args:
            workspace: UserWorkspace实例

        """
        from dawei.workspace.user_workspace import UserWorkspace

        if not isinstance(workspace, UserWorkspace):
            raise EvolutionStorageError(f"workspace must be UserWorkspace, got {type(workspace)}")

        self.workspace = workspace
        self._pm = WorkspacePersistenceManager(workspace.workspace_path)
        self.base = Path(workspace.workspace_path) / self.BASE_DIR

        logger.debug(f"[EVOLUTION_STORAGE] Initialized for workspace {workspace.workspace_id} at {self.base}")

    def _cycle_dir(self, cycle_id: str) -> Path:
        """获取cycle目录路径

        Args:
            cycle_id: Cycle ID（如 "001", "002"）

        Returns:
            Path: cycle目录路径

        """
        return self.base / f"{self.PREFIX}{cycle_id}"

    async def create_cycle_directory(self, cycle_id: str) -> Path:
        """创建新的cycle目录

        Args:
            cycle_id: Cycle ID（如 "001", "002"）

        Returns:
            Path: 创建的cycle目录路径

        Raises:
            EvolutionStorageError: 当目录创建失败时

        """
        try:
            cycle_dir = self._cycle_dir(cycle_id)
            cycle_dir.mkdir(parents=True, exist_ok=True)

            # 更新current symlink（如果支持）
            link = self.base / self.CURRENT_LINK
            try:
                if link.is_symlink() or link.exists():
                    link.unlink()
                # 创建相对符号链接
                link.symlink_to(cycle_dir.name)
                logger.debug(f"[EVOLUTION_STORAGE] Updated current symlink to {cycle_dir.name}")
            except OSError as symlink_error:
                # Windows可能需要管理员权限创建符号链接
                logger.warning(f"[EVOLUTION_STORAGE] Failed to create symlink {link}: {symlink_error}")

            logger.info(f"[EVOLUTION_STORAGE] Created cycle directory: {cycle_dir}")
            return cycle_dir

        except OSError as e:
            logger.error(f"[EVOLUTION_STORAGE] Failed to create cycle directory for {cycle_id}: {e}")
            raise EvolutionStorageError(f"Failed to create cycle directory for {cycle_id}: {e}")

    async def save_metadata(self, cycle_id: str, metadata: dict[str, Any]) -> bool:
        """保存cycle metadata

        Args:
            cycle_id: Cycle ID
            metadata: Metadata字典

        Returns:
            bool: 是否保存成功

        Raises:
            EvolutionStorageError: 当保存失败时

        """
        try:
            # 使用WorkspacePersistenceManager的保存方法
            success = await self._pm.save_evolution_metadata(cycle_id, metadata)

            if success:
                logger.debug(f"[EVOLUTION_STORAGE] Saved metadata for cycle {cycle_id}")
            else:
                logger.error(f"[EVOLUTION_STORAGE] Failed to save metadata for cycle {cycle_id}")

            return success

        except Exception as e:
            logger.error(f"[EVOLUTION_STORAGE] Error saving metadata for cycle {cycle_id}: {e}")
            raise EvolutionStorageError(f"Error saving metadata for cycle {cycle_id}: {e}")

    async def load_metadata(self, cycle_id: str) -> dict[str, Any]:
        """加载cycle metadata

        Args:
            cycle_id: Cycle ID

        Returns:
            Dict[str, Any]: Metadata字典

        Raises:
            EvolutionStorageError: 当加载失败时

        """
        try:
            metadata = await self._pm.load_evolution_metadata(cycle_id)

            if metadata is None:
                raise EvolutionStorageError(f"Metadata not found for cycle {cycle_id}")

            logger.debug(f"[EVOLUTION_STORAGE] Loaded metadata for cycle {cycle_id}")
            return metadata

        except EvolutionStorageError:
            raise
        except Exception as e:
            logger.error(f"[EVOLUTION_STORAGE] Error loading metadata for cycle {cycle_id}: {e}")
            raise EvolutionStorageError(f"Error loading metadata for cycle {cycle_id}: {e}")

    async def save_phase_output(self, cycle_id: str, phase: str, content: str) -> bool:
        """保存phase输出到{phase}.md文件

        Args:
            cycle_id: Cycle ID
            phase: Phase名称（plan, do, check, act）
            content: Markdown内容

        Returns:
            bool: 是否保存成功

        Raises:
            EvolutionStorageError: 当保存失败时

        """
        try:
            success = await self._pm.save_evolution_phase(cycle_id, phase, content)

            if success:
                logger.debug(f"[EVOLUTION_STORAGE] Saved {phase}.md for cycle {cycle_id} ({len(content)} chars)")
            else:
                logger.error(f"[EVOLUTION_STORAGE] Failed to save {phase}.md for cycle {cycle_id}")

            return success

        except Exception as e:
            logger.error(
                f"[EVOLUTION_STORAGE] Error saving {phase}.md for cycle {cycle_id}: {e}",
                exc_info=True,
            )
            raise EvolutionStorageError(f"Error saving {phase}.md for cycle {cycle_id}: {e}")

    async def load_phase_output(self, cycle_id: str, phase: str) -> str:
        """加载phase输出文件

        Args:
            cycle_id: Cycle ID
            phase: Phase名称（plan, do, check, act）

        Returns:
            str: 文件内容

        Raises:
            EvolutionStorageError: 当文件不存在或读取失败时

        """
        try:
            content = await self._pm.load_evolution_phase(cycle_id, phase)

            if content is None:
                raise EvolutionStorageError(f"Phase file {phase}.md not found for cycle {cycle_id}")

            logger.debug(f"[EVOLUTION_STORAGE] Loaded {phase}.md for cycle {cycle_id}")
            return content

        except EvolutionStorageError:
            raise
        except Exception as e:
            logger.error(f"[EVOLUTION_STORAGE] Error loading {phase}.md for cycle {cycle_id}: {e}")
            raise EvolutionStorageError(f"Error loading {phase}.md for cycle {cycle_id}: {e}")

    async def load_workspace_md(self, dao_path: str | None = None) -> str:
        """加载dao.md文件

        Args:
            dao_path: 自定义dao文件路径。如果提供，则覆盖默认的workspace/dao.md路径。

        Returns:
            str: dao.md内容

        Raises:
            EvolutionStorageError: 当文件不存在时

        """
        if dao_path:
            workspace_md_path = Path(dao_path)
            if not workspace_md_path.is_absolute():
                workspace_md_path = (Path(self.workspace.workspace_path) / dao_path).resolve()
        else:
            workspace_md_path = self.base / self.WORKSPACE_MD

        if workspace_md_path.exists():
            content = workspace_md_path.read_text(encoding="utf-8")
            logger.debug(f"[EVOLUTION_STORAGE] Loaded dao.md from {workspace_md_path} ({len(content)} chars)")
            return content
        else:
            raise EvolutionStorageError(
                f"dao.md not found at {workspace_md_path}. "
                "Please create a dao.md file with workspace goals and success criteria."
            )


    async def get_all_cycles(self) -> list[dict[str, Any]]:
        """获取所有cycles的metadata列表

        Returns:
            List[Dict[str, Any]]: 按cycle_id排序的metadata列表

        """
        try:
            cycles = []
            for cycle_dir in sorted(self.base.glob(f"{self.PREFIX}*")):
                if cycle_dir.is_dir() and not cycle_dir.is_symlink():
                    metadata_file = cycle_dir / "metadata.json"
                    if metadata_file.exists():
                        try:
                            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                            cycles.append(metadata)
                        except (json.JSONDecodeError, OSError) as e:
                            logger.warning(f"[EVOLUTION_STORAGE] Failed to load metadata from {metadata_file}: {e}")
                            continue

            logger.debug(f"[EVOLUTION_STORAGE] Found {len(cycles)} cycles")
            return cycles

        except Exception as e:
            logger.error(f"[EVOLUTION_STORAGE] Error getting all cycles: {e}")
            return []

    async def get_latest_cycle(self) -> dict[str, Any] | None:
        """获取最新的cycle（按cycle_id排序）

        Returns:
            Dict[str, Any] | None: 最新的metadata，如果没有cycle则返回None

        """
        cycles = await self.get_all_cycles()
        if cycles:
            latest = cycles[-1]
            logger.debug(f"[EVOLUTION_STORAGE] Latest cycle: {latest.get('cycle_id')}")
            return latest
        return None

    async def get_latest_completed_cycle_id(self) -> str | None:
        """获取最新已完成的cycle ID

        Returns:
            str | None: 已完成的cycle ID，如果没有则返回None

        """
        cycles = await self.get_all_cycles()
        for cycle in reversed(cycles):
            if cycle.get("status") == "completed":
                cycle_id = cycle.get("cycle_id")
                logger.debug(f"[EVOLUTION_STORAGE] Latest completed cycle: {cycle_id}")
                return cycle_id
        return None

    async def cycle_exists(self, cycle_id: str) -> bool:
        """检查cycle是否存在

        Args:
            cycle_id: Cycle ID

        Returns:
            bool: cycle是否存在

        """
        cycle_dir = self._cycle_dir(cycle_id)
        exists = cycle_dir.is_dir() and (cycle_dir / "metadata.json").exists()
        logger.debug(f"[EVOLUTION_STORAGE] Cycle {cycle_id} exists: {exists}")
        return exists

    async def delete_cycle(self, cycle_id: str) -> bool:
        """删除cycle目录（谨慎使用！）

        Args:
            cycle_id: Cycle ID

        Returns:
            bool: 是否删除成功

        """
        try:
            cycle_dir = self._cycle_dir(cycle_id)
            if cycle_dir.exists():
                import shutil

                shutil.rmtree(cycle_dir)
                logger.info(f"[EVOLUTION_STORAGE] Deleted cycle directory: {cycle_dir}")
                return True
            logger.debug(f"[EVOLUTION_STORAGE] Cycle directory not found: {cycle_dir}")
            return False

        except Exception as e:
            logger.error(f"[EVOLUTION_STORAGE] Error deleting cycle {cycle_id}: {e}")
            raise EvolutionStorageError(f"Error deleting cycle {cycle_id}: {e}")
