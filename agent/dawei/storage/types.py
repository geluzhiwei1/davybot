# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""存储类型定义模块"""

from enum import Enum


class StorageType(Enum):
    """支持的存储类型枚举"""

    LOCAL_FILESYSTEM = "local_filesystem"
    # 未来可以扩展其他存储类型
    # S3 = "s3"
    # AZURE_BLOB = "azure_blob"
    # GCS = "gcs"
