# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""smart_text_edit 功能测试 —— 全部走 run() 公共入口

背景（2026-09-17 事故）：该工具自首次提交起 schema 字段 chunk_size 与
_run 形参 _chunk_size 命名不一致，run() 每次调用必抛 TypeError，被兜底
装饰器吞成 "Error: Failed to edit file"。历史上没有任何测试调用过
run()（只测 _run 或干脆没测），所以 100% 失效的工具存活至今。

本文件锁死事故的两条根因：
1. run() 注入全部 schema 字段（含默认 chunk_size）不得抛 TypeError
2. LLM 实际使用的 old_string/new_string key 形态必须被接受
"""

from types import SimpleNamespace

import pytest

from dawei.tools.custom_tools.smart_file_edit import SmartFileEditTool

pytestmark = pytest.mark.unit

INITIAL_CONTENT = """# DAO 文档
- [ ] 种子论文数量（当前 2 篇）：是否补充？
- [ ] 数据集范围（多车辆 Camera/LiDAR/Radar）。
- [x] 已完成项。
"""


@pytest.fixture
def tool_with_workspace(tmp_path):
    """构造带临时 workspace 上下文的工具实例（模拟 tool_executor 注入）。"""
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "dao.md").write_text(INITIAL_CONTENT, encoding="utf-8")
    tool = SmartFileEditTool()
    tool.set_context(SimpleNamespace(cwd=str(tmp_path)))
    return tool


class TestRunPublicInterface:
    def test_run_with_explicit_chunk_size_no_typeerror(self):
        """事故回归 #1：LLM 显式传 chunk_size 时不得抛 TypeError。

        历史缺陷：_run 形参误命名 _chunk_size，schema 注入 chunk_size=50
        必抛 'unexpected keyword argument'。修复后应正常返回编辑结果。
        """
        tool = SmartFileEditTool()
        result = tool.run(
            file_path="nonexistent.md",
            edits=[{"search": "x", "replace": "y"}],
            chunk_size=30,  # 事故触发参数
        )
        # 文件不存在 → 软失败（不是 TypeError 兜底串）
        assert "not found" in result
        assert "Failed to edit file" not in result

    def test_run_with_default_injection_no_typeerror(self, tool_with_workspace, tmp_path):
        """事故回归 #2：不传 chunk_size 时 .dict() 默认注入同样不得抛。"""
        result = tool_with_workspace.run(
            file_path="input/dao.md",
            edits=[{"search": "当前 2 篇", "replace": "当前 6 篇"}],
        )
        assert "✅" in result
        assert "当前 6 篇" in (tmp_path / "input" / "dao.md").read_text(encoding="utf-8")


class TestEditKeyForms:
    def test_search_replace_form(self, tool_with_workspace, tmp_path):
        result = tool_with_workspace.run(
            file_path="input/dao.md",
            edits=[{"search": "- [ ] 数据集范围", "replace": "- [x] 数据集范围"}],
        )
        assert "✅" in result
        content = (tmp_path / "input" / "dao.md").read_text(encoding="utf-8")
        assert "- [x] 数据集范围" in content

    def test_old_string_new_string_alias_form(self, tool_with_workspace, tmp_path):
        """事故回归 #3：GLM 在野调用实际用的 key 形态必须被接受。"""
        result = tool_with_workspace.run(
            file_path="input/dao.md",
            edits=[
                {
                    "old_string": "- [ ] 种子论文数量（当前 2 篇）：是否补充？",
                    "new_string": "- [x] 种子论文：已确认 6 篇。",
                },
            ],
        )
        assert "✅" in result
        content = (tmp_path / "input" / "dao.md").read_text(encoding="utf-8")
        assert "- [x] 种子论文：已确认 6 篇。" in content

    def test_missing_keys_clear_error(self, tool_with_workspace):
        result = tool_with_workspace.run(
            file_path="input/dao.md",
            edits=[{"foo": "bar"}],
        )
        assert result.startswith("Error:")
        assert "missing" in result


class TestSoftFailureSemantics:
    def test_search_not_found_reports_but_applies_others(self, tool_with_workspace, tmp_path):
        """找不到 search 文本：该条 ❌ 跳过，其余照常应用（软失败语义）。"""
        result = tool_with_workspace.run(
            file_path="input/dao.md",
            edits=[
                {"search": "根本不存在的内容 xyz", "replace": "whatever"},
                {"search": "已完成项", "replace": "已完成项（锁定）"},
            ],
        )
        assert "❌" in result
        assert "✅" in result
        content = (tmp_path / "input" / "dao.md").read_text(encoding="utf-8")
        assert "whatever" not in content
        assert "已完成项（锁定）" in content

    def test_fallback_carries_exception_detail(self):
        """兜底串必须携带真实异常信息（不再 26 字符裸奔）。

        构造 read_text 必然失败的场景：路径指向目录（IsADirectoryError）。
        """
        tool = SmartFileEditTool()
        result = tool.run(
            file_path=".",
            edits=[{"search": "x", "replace": "y"}],
        )
        if result.startswith("Error: Failed to edit file"):
            assert "[" in result
            assert "Error" in result.split("[", 1)[1], "兜底串未携带异常详情，LLM 无法自纠"


class TestFallbackAugmentation:
    """兜底增强单元测试：错误详情必须可见且不破坏调用方解析。"""

    def test_plain_string_gets_bracket_detail(self):
        from dawei.core.decorators import SafeOperationConfig, _augment_fallback

        config = SafeOperationConfig(
            component="tools",
            fallback_value="Error: Failed to edit file",
            include_error_in_fallback=True,
        )
        result = _augment_fallback(config, TypeError("boom"))
        assert result.startswith("Error: Failed to edit file")
        assert "[TypeError: boom]" in result

    def test_json_fallback_stays_parseable(self):
        """JSON 形态 fallback 注入 error_detail 字段，json.loads 不被破坏。"""
        import json

        from dawei.core.decorators import SafeOperationConfig, _augment_fallback

        config = SafeOperationConfig(
            component="tools",
            fallback_value='{"status": "error", "message": "Failed to execute command"}',
            include_error_in_fallback=True,
        )
        result = _augment_fallback(config, RuntimeError("ssl broken"))
        payload = json.loads(result)  # 不得抛
        assert payload["status"] == "error"
        assert "RuntimeError: ssl broken" in payload["error_detail"]

    def test_non_string_fallback_untouched(self):
        from dawei.core.decorators import SafeOperationConfig, _augment_fallback

        config = SafeOperationConfig(
            component="tools",
            fallback_value=None,
            include_error_in_fallback=True,
        )
        assert _augment_fallback(config, ValueError("x")) is None

    def test_disabled_flag_keeps_legacy_behavior(self):
        from dawei.core.decorators import SafeOperationConfig, _augment_fallback

        config = SafeOperationConfig(
            component="core",
            fallback_value="legacy fallback",
            include_error_in_fallback=False,
        )
        assert _augment_fallback(config, ValueError("x")) == "legacy fallback"
