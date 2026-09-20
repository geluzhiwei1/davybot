# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""命令执行器 (v1 兼容层) — 已迁移至 subprocess_provider.py

此文件仅作为向后兼容 shim 存在。
新代码请直接使用:
    from dawei.sandbox.subprocess_provider import SubprocessProvider, CommandExecutor
    # 或使用 v2 统一入口:
    from dawei.sandbox.sandbox_facade import SandboxFacade
"""

from dawei.sandbox.subprocess_provider import CommandExecutor, SubprocessProvider

__all__ = ["CommandExecutor", "SubprocessProvider"]
