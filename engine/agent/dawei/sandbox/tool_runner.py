# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Sandbox-side tool runner (P3 Path B — 工具调用远程化)

在 CubeSandbox MicroVM 内执行, 接收 JSON 工具调用规格, 导入并运行 tool._run(),
返回 JSON 结果。工具代码完全不变, 仅执行环境从宿主迁移到沙箱。

协议:
  输入 (stdin): JSON {"tool_class": "module.Class", "kwargs": {...}}
  输出 (stdout): JSON {"success": true, "result": "..."} | {"success": false, "error": "..."}

workspace 挂载在 /workspace, 所有文件路径相对于 /workspace 解析。

依赖: dawei 包必须在沙箱内可导入 (由 E2B 模板预装或会话启动时部署)。

使用:
  echo '{"tool_class": "...", "kwargs": {...}}' | python3 -m dawei.sandbox.tool_runner
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace


def _fail(msg: str) -> None:
    """Output error JSON and exit."""
    print(json.dumps({"success": False, "error": msg}, ensure_ascii=False))
    sys.exit(1)


def _ok(result: str) -> None:
    """Output success JSON."""
    print(json.dumps({"success": True, "result": result}, ensure_ascii=False))


def main() -> None:
    # 1. Read JSON spec from stdin
    try:
        raw = sys.stdin.read()
        spec = json.loads(raw)
    except Exception as e:
        _fail(f"Invalid JSON spec on stdin: {e}")
        return

    tool_class_path: str = spec.get("tool_class", "")
    kwargs: dict = spec.get("kwargs", {})

    if not tool_class_path:
        _fail("Missing 'tool_class' in spec")
        return

    # 2. Import the tool class
    parts = tool_class_path.rsplit(".", 1)
    if len(parts) != 2:
        _fail(f"Invalid tool_class path (expected module.Class): {tool_class_path}")
        return

    module_path, class_name = parts
    try:
        __import__(module_path)
        module = sys.modules[module_path]
        tool_class = getattr(module, class_name)
    except Exception as e:
        _fail(f"Failed to import {tool_class_path}: {e}")
        return

    # 3. Instantiate tool
    try:
        tool = tool_class()
    except Exception as e:
        _fail(f"Failed to instantiate {class_name}: {e}")
        return

    # 4. Set workspace context — workspace is always /workspace in sandbox
    workspace_path = Path("/workspace")
    ws_ns = SimpleNamespace(path=workspace_path)
    ctx = SimpleNamespace(user_workspace=ws_ns)
    tool.context = ctx
    if hasattr(tool, "user_workspace"):
        tool.user_workspace = ws_ns

    # 5. Execute tool.run(**kwargs) — includes Pydantic validation + _run()
    #    context=None so manually-set context persists (run() won't override)
    try:
        result = tool.run(**kwargs)
        _ok(str(result))
    except Exception as e:
        _fail(f"{e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
