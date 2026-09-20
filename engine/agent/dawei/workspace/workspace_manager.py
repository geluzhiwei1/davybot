# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工作区管理器"""

import json
from pathlib import Path
from typing import List, Dict, Any

from dawei import get_dawei_home
from dawei.config.settings import get_settings


class WorkspaceManager:
    """工作区UUID映射管理"""

    def __init__(self, settings):
        # 使用 DAWEI_HOME 作为工作区根目录
        workspaces_root = get_dawei_home()

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

    @staticmethod
    def _is_workspace_alive(workspace: Dict[str, Any]) -> bool:
        """检查工作区目录是否真实存在（防止 stale 注册）"""
        path = workspace.get("path")
        if not path:
            return False
        return Path(path).is_dir()

    def get_workspace_by_id(self, workspace_id: str) -> Dict[str, Any] | None:
        """根据UUID获取工作区信息

        如果第一次未找到，会自动重新加载并重试一次。
        如果工作区目录不存在（stale 注册），返回 None。
        """
        workspace = self.workspaces_mapping.get(workspace_id)

        # 如果找不到工作区，或者找到但缺少 path 字段，重新加载并重试
        if not workspace or (workspace and not workspace.get("path")):
            self.load_workspaces()
            workspace = self.workspaces_mapping.get(workspace_id)

        # stale 检查：目录不存在则视为未注册
        if workspace and not self._is_workspace_alive(workspace):
            return None

        return workspace

    def get_all_workspaces(
        self, user_id: str | None = None, tenant_id: str | None = None
    ) -> List[Dict[str, Any]]:
        """获取所有工作区（可选按 owner_user_id + tenant_id 过滤；None=不过滤，向后兼容）。

        自动过滤目录已不存在的 stale 注册。
        """
        all_ws = [w for w in self.workspaces_mapping.values() if self._is_workspace_alive(w)]
        if user_id is None and tenant_id is None:
            return all_ws
        result = all_ws
        if user_id is not None:
            result = [w for w in result if w.get("owner_user_id", "default_user") == user_id]
        if tenant_id is not None:
            result = [w for w in result if w.get("tenant_id", "personal") == tenant_id]
        return result

    def get_workspace_name_by_id(self, workspace_id: str) -> str | None:
        """根据UUID获取工作区名称"""
        workspace = self.get_workspace_by_id(workspace_id)
        return workspace.get("name") if workspace else None

    async def get_workspace(self, workspace_id: str):
        """获取工作区对象（UserWorkspace 实例）

        Args:
            workspace_id: 工作区UUID

        Returns:
            UserWorkspace 对象，如果工作区不存在则返回 None

        """
        from .user_workspace import UserWorkspace

        workspace_info = self.get_workspace_by_id(workspace_id)
        if not workspace_info or not workspace_info.get("path"):
            return None

        # 创建 UserWorkspace 实例
        workspace_path = workspace_info["path"]
        workspace = UserWorkspace(workspace_path)
        # 注入归属账号（须在 initialize() 之前）：context 按 (path, user_id) 分键，
        # 账户隔离资源（MCP/relay stub、SecurityManager）跟随该键。
        owner_uid = workspace_info.get("owner_user_id")
        if owner_uid:
            workspace.user_id = owner_uid
        return workspace

    def reload(self):
        """重新加载工作区映射"""
        self.load_workspaces()


# 创建全局工作区管理器实例
workspace_manager = WorkspaceManager(get_settings())
