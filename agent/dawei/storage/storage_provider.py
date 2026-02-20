# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""存储提供者工厂和管理器

支持两级存储架构：
1. system_storage: 系统级存储 (DAWEI_HOME)
2. workspace_storage: 工作区级存储 (workspace_path)
"""

import logging
import os
from pathlib import Path
from typing import Any, ClassVar

from .config import config_manager
from .impl.local_filesystem import LocalFileSystemStorage
from .storage import Storage
from .types import StorageType

logger = logging.getLogger(__name__)


class StorageProvider:
    """存储提供者工厂类，负责创建和管理不同的存储实现

    支持两级存储架构：
    - system_storage: 系统级存储（DAWEI_HOME）
    - workspace_storage: 工作区级存储（workspace_path）
    """

    _storage_registry: ClassVar[dict[StorageType, type[Storage]]] = {
        StorageType.LOCAL_FILESYSTEM: LocalFileSystemStorage,
    }

    _default_storage: ClassVar[Storage | None] = None
    _default_config: ClassVar[dict[str, Any] | None] = None

    # 两级存储架构的缓存
    _system_storage: ClassVar[Storage | None] = None
    _workspace_storages: ClassVar[dict[str, Storage]] = {}

    @classmethod
    def register_storage(cls, storage_type: StorageType, storage_class: type[Storage]) -> None:
        """注册新的存储类型

        Args:
            storage_type: 存储类型枚举
            storage_class: 存储实现类

        """
        cls._storage_registry[storage_type] = storage_class

    @classmethod
    def create_storage(cls, storage_type: StorageType, **kwargs) -> Storage:
        """创建指定类型的存储实例

        Args:
            storage_type: 存储类型枚举
            **kwargs: 存储实例初始化参数

        Returns:
            Storage: 存储实例

        Raises:
            ValueError: 当存储类型未注册时

        """
        if storage_type not in cls._storage_registry:
            raise ValueError(f"不支持的存储类型: {storage_type}")

        storage_class = cls._storage_registry[storage_type]
        return storage_class(**kwargs)

    @classmethod
    def set_default_config(cls, config: dict[str, Any]) -> None:
        """设置默认存储配置

        Args:
            config: 配置字典，包含存储类型和初始化参数

        """
        cls._default_config = config
        cls._default_storage = None  # 重置默认存储实例

    @classmethod
    def get_default_storage(cls) -> Storage:
        """获取默认存储实例

        Returns:
            Storage: 默认存储实例

        Raises:
            ValueError: 当未设置默认配置时

        """
        if cls._default_storage is None:
            # 从配置管理器获取配置
            config = config_manager.get_config()

            # 如果有手动设置的配置，优先使用
            if cls._default_config is not None:
                storage_type = cls._default_config["storage_type"]
                init_params = {k: v for k, v in cls._default_config.items() if k != "storage_type"}
            else:
                # 使用配置管理器的配置
                storage_type = config.storage_type
                init_params = {"root_dir": config.root_dir}

            cls._default_storage = cls.create_storage(storage_type, **init_params)

        return cls._default_storage

    @classmethod
    def get_local_filesystem_storage(cls, root_dir: str | None = None) -> LocalFileSystemStorage:
        """获取本地文件系统存储实例的便捷方法

        Args:
            root_dir: 根目录路径，如果为None则使用当前工作目录

        Returns:
            LocalFileSystemStorage: 本地文件系统存储实例

        """
        if root_dir is None:
            root_dir = os.getcwd()

        return LocalFileSystemStorage(root_dir=root_dir)

    # ==================== 两级存储架构方法 ====================

    @classmethod
    def get_system_storage(cls) -> Storage:
        """获取系统级 Storage

        Root dir: DAWEI_HOME (~/.dawei)
        用于操作 workspaces.json 等系统文件

        Returns:
            Storage: 系统级存储实例

        """
        if cls._system_storage is None:
            from dawei.config import get_dawei_home

            dawei_home = get_dawei_home()

            logger.info(f"Creating system_storage with root_dir: {dawei_home}")
            cls._system_storage = LocalFileSystemStorage(root_dir=str(dawei_home))

        return cls._system_storage

    @classmethod
    def get_workspace_storage(cls, workspace_path: str) -> Storage:
        """获取工作区级 Storage

        Root dir: workspace_path (用户指定的路径)
        用于操作工作区内的 .dawei 目录

        Args:
            workspace_path: 工作区的完整路径

        Returns:
            Storage: 工作区级存储实例

        """
        # 规范化路径
        workspace_path_obj = Path(workspace_path).resolve()
        workspace_path_str = str(workspace_path_obj)

        # 缓存 Storage 实例
        if workspace_path_str not in cls._workspace_storages:
            logger.info(f"Creating workspace_storage with root_dir: {workspace_path_str}")
            cls._workspace_storages[workspace_path_str] = LocalFileSystemStorage(
                root_dir=workspace_path_str,
            )

        return cls._workspace_storages[workspace_path_str]

    @classmethod
    def clear_workspace_storage_cache(cls):
        """清除工作区存储缓存

        用于测试或重置
        """
        cls._workspace_storages.clear()
        logger.info("Cleared workspace_storage cache")

    @classmethod
    def clear_system_storage_cache(cls):
        """清除系统存储缓存

        用于 workspaces.json 更新后强制重新读取
        """
        cls._system_storage = None
        logger.info("Cleared system_storage cache")

    @classmethod
    def reset(cls):
        """重置所有 Storage 实例

        用于测试
        """
        cls._system_storage = None
        cls._workspace_storages.clear()
        cls._default_storage = None
        logger.info("Reset StorageProvider")


# 全局默认存储实例
default_storage = StorageProvider.get_default_storage()
