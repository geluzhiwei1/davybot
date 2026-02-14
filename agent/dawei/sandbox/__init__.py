# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""沙箱模块 - 为系统命令提供安全的隔离执行环境

该模块实现了轻量级沙箱隔离系统，包括：
- LightweightSandbox: 轻量级沙箱（无需Docker）
- CommandWhitelist: 命令白名单验证器

使用示例:
    from dawei.sandbox.lightweight_executor import LightweightSandbox
    from pathlib import Path

    executor = LightweightSandbox()
    result = executor.execute_command(
        command="ls -la",
        workspace_path=Path("/path/to/workspace"),
        user_id="user123"
    )
"""

from dawei.sandbox.command_whitelist import CommandWhitelist
from dawei.sandbox.lightweight_executor import LightweightSandbox

__all__ = [
    "CommandWhitelist",
    "LightweightSandbox",
]

__version__ = "2.0.0"
