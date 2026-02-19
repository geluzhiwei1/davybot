# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工作区管理器"""

import json
from pathlib import Path
from typing import Any

from dawei.config import get_workspaces_root
from dawei.config.settings import get_settings


class WorkspaceManager:
    """工作区UUID映射管理"""

    def __init__(self, settings):
        # 使用 DAWEI_HOME 作为工作区根目录
        workspaces_root = Path(get_workspaces_root())

        # 构建工作区文件的完整路径
        self.workspaces_file = workspaces_root / "workspaces.json"

        # 确保工作区根目录存在
        self.workspaces_root_path = workspaces_root.resolve()
        self.workspaces_root_path.mkdir(parents=True, exist_ok=True)

        self.workspaces_mapping = {}
        self.load_workspaces()

    def load_workspaces(self):
        """加载工作区UUID映射

        Raises:
            FileNotFoundError: 如果 workspaces.json 文件不存在
            json.JSONDecodeError: 如果 JSON 格式无效
            IOError: 如果文件读取失败

        """
        if not self.workspaces_file.exists():
            # 文件不存在时使用空映射（这是正常情况）
            self.workspaces_mapping = {}
            return

        # Fail-fast: 直接读取，任何错误都会抛出异常
        with Path(self.workspaces_file).open(encoding="utf-8") as f:
            data = json.load(f)
            for workspace in data.get("workspaces", []):
                if "id" in workspace:
                    self.workspaces_mapping[workspace["id"]] = workspace

    def get_workspace_by_id(self, workspace_id: str) -> dict[str, Any] | None:
        """根据UUID获取工作区信息

        如果第一次未找到，会自动重新加载并重试一次
        """
        workspace = self.workspaces_mapping.get(workspace_id)

        # 如果找不到工作区，或者找到但缺少 path 字段，重新加载并重试
        if not workspace or (workspace and not workspace.get("path")):
            self.load_workspaces()
            workspace = self.workspaces_mapping.get(workspace_id)

        return workspace

    def get_all_workspaces(self) -> list[dict[str, Any]]:
        """获取所有工作区"""
        return list(self.workspaces_mapping.values())

    def get_workspace_name_by_id(self, workspace_id: str) -> str | None:
        """根据UUID获取工作区名称"""
        workspace = self.get_workspace_by_id(workspace_id)
        return workspace.get("name") if workspace else None

    def reload(self):
        """重新加载工作区映射"""
        self.load_workspaces()


# 创建全局工作区管理器实例
workspace_manager = WorkspaceManager(get_settings())
