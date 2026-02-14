# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""存储模块

提供统一的文件系统接口，支持多种存储后端，默认使用本地文件系统存储。
"""

from .config import StorageConfig, config_manager
from .impl import LocalFileSystemStorage
from .storage import Storage
from .storage_provider import StorageProvider
from .types import StorageType

__all__ = [
    "LocalFileSystemStorage",
    "Storage",
    "StorageConfig",
    "StorageProvider",
    "StorageType",
    "config_manager",
]

# 版本信息
__version__ = "1.0.0"
