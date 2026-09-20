# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具系统全面体检脚本（诊断用，可重复执行）

实现已下沉到 dawei/tools/tool_system_health.py（单一实现源），
本脚本仅作 CLI 入口。CI 常驻门禁见 tests/test_tool_system_health.py。

用法: uv run python scripts/audit_tool_system.py
"""

from dawei.tools.tool_system_health import audit, format_report


def main() -> None:
    print(format_report(audit()))


if __name__ == "__main__":
    main()
