# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""存储配置管理模块"""

import os
from dataclasses import dataclass, field
from typing import Any, Optional, Self

from .types import StorageType


@dataclass
class StorageConfig:
    """存储配置类"""

    storage_type: StorageType = StorageType.LOCAL_FILESYSTEM
    root_dir: str = field(default_factory=os.getcwd)
    # 本地文件系统特定配置
    create_if_missing: bool = True
    # 未来可以添加其他存储类型的配置
    # s3_bucket: Optional[str] = None
    # s3_region: Optional[str] = None
    # azure_container: Optional[str] = None
    # gcs_bucket: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "storage_type": self.storage_type,
            "root_dir": self.root_dir,
            "create_if_missing": self.create_if_missing,
        }

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "StorageConfig":
        """从字典创建配置实例"""
        storage_type = config_dict.get("storage_type", StorageType.LOCAL_FILESYSTEM)
        if isinstance(storage_type, str):
            storage_type = StorageType(storage_type)

        return cls(
            storage_type=storage_type,
            root_dir=config_dict.get("root_dir", os.getcwd()),
            create_if_missing=config_dict.get("create_if_missing", True),
        )

    @classmethod
    def from_env(cls) -> "StorageConfig":
        """从环境变量创建配置实例"""
        storage_type_str = os.getenv("STORAGE_TYPE", "local_filesystem")
        storage_type = StorageType(storage_type_str)

        return cls(
            storage_type=storage_type,
            root_dir=os.getenv("STORAGE_ROOT_DIR", os.getcwd()),
            create_if_missing=os.getenv("STORAGE_CREATE_IF_MISSING", "true").lower() == "true",
        )


class StorageConfigManager:
    """存储配置管理器"""

    _instance: Optional["StorageConfigManager"] = None
    _config: StorageConfig | None = None

    def __new__(cls) -> Self:
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def set_config(self, config: StorageConfig) -> None:
        """设置存储配置"""
        self._config = config

    def get_config(self) -> StorageConfig:
        """获取存储配置"""
        if self._config is None:
            self._config = StorageConfig.from_env()
        return self._config

    def load_from_dict(self, config_dict: dict[str, Any]) -> None:
        """从字典加载配置"""
        self._config = StorageConfig.from_dict(config_dict)

    def load_from_env(self) -> None:
        """从环境变量加载配置"""
        self._config = StorageConfig.from_env()


# 全局配置管理器实例
config_manager = StorageConfigManager()
