# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具契约测试（schema ↔ _run 签名一致性）

背景（2026-09-17 事故）：smart_text_edit 的 args_schema 字段 chunk_size
与 _run 形参 _chunk_size 命名不一致，run() 以 _run(**schema.dict()) 调用
必然抛 TypeError，被 @safe_tool_operation 吞成 "Error: Failed to edit
file" —— 工具自上线起 100% 失效却无人察觉（无测试、CI 禁用、错误被吞）。

本文件从三个层面防止同类缺陷：
1. 校验器本身的正确性（能抓正向/反向违规）
2. CustomBaseTool 在实例化期 / run() 首次执行期强制校验
3. 全量 CustomBaseTool 子类（= 服务启动路径实例化的同一批工具）通过契约
"""

import inspect

import pytest
from pydantic import BaseModel

from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.tool_contract import (
    ToolContractError,
    get_contract_violations,
    validate_tool_contract,
)

pytestmark = pytest.mark.unit


# ─────────────────────────── 1. 校验器单元测试 ───────────────────────────
# 注意：违规示例用普通 stub 类（不继承 CustomBaseTool）——因为
# CustomBaseTool.__init__ 现在会强制校验，违规子类根本无法实例化。
# 校验器本身是通用的，接受任何带 args_schema + _run 的对象。


class _GoodInput(BaseModel):
    file_path: str
    chunk_size: int = 50


class GoodTool(CustomBaseTool):
    name = "good_tool"
    args_schema = _GoodInput

    def _run(self, file_path: str, chunk_size: int = 50) -> str:
        return f"{file_path}:{chunk_size}"


class _ForwardViolationStub:
    """复现 2026-09-17 事故：schema 叫 chunk_size，_run 形参误命名 _chunk_size。"""

    name = "forward_violation_tool"
    args_schema = _GoodInput

    def _run(self, file_path: str, _chunk_size: int = 50) -> str:
        return file_path


class _ReverseViolationStub:
    """_run 必填（无默认值）形参不在 schema 中 → run() 必抛 missing argument。"""

    name = "reverse_violation_tool"
    args_schema = _GoodInput

    def _run(self, file_path: str, secret: str, chunk_size: int = 50) -> str:
        return f"{file_path}:{secret}"


class _VarKeywordStub:
    """**kwargs 形态：接受一切 kwargs，天然满足契约。"""

    name = "var_keyword_tool"
    args_schema = _GoodInput

    def _run(self, **kwargs) -> str:
        return str(kwargs)


class _BareStub:
    """无 args_schema → 不校验。"""

    name = "bare_tool"

    def _run(self, **kwargs) -> str:
        return "ok"


class TestValidator:
    def test_forward_violation_detected(self):
        """事故原始形态：schema 字段不是 _run 形参 → 必须报违规。"""
        violations = get_contract_violations(_ForwardViolationStub(), "forward_violation_tool")
        assert any("chunk_size" in v for v in violations), violations

    def test_valid_tool_passes(self):
        assert get_contract_violations(GoodTool(), "good_tool") == []

    def test_var_keyword_tool_passes(self):
        assert get_contract_violations(_VarKeywordStub(), "var_keyword_tool") == []

    def test_validate_raises_with_context(self):
        with pytest.raises(ToolContractError, match="chunk_size"):
            validate_tool_contract(_ForwardViolationStub(), "forward_violation_tool")

    def test_reverse_violation_detected(self):
        """_run 必填形参不在 schema 中 → 违规。"""
        violations = get_contract_violations(_ReverseViolationStub(), "reverse_violation_tool")
        assert any("secret" in v for v in violations), violations

    def test_no_schema_skipped(self):
        assert get_contract_violations(_BareStub(), "bare_tool") == []


class TestEnforcementPoints:
    def test_instantiation_fails_fast(self):
        """类级 args_schema 违规 → 实例化（= 服务启动）即爆炸。"""

        class BrokenTool(CustomBaseTool):
            name = "broken_tool"
            args_schema = _GoodInput

            def _run(self, file_path: str, _chunk_size: int = 50) -> str:
                return file_path

        with pytest.raises(ToolContractError, match="chunk_size"):
            BrokenTool()

    def test_run_enforces_instance_level_schema(self):
        """__init__ 里才设置 self.args_schema 的工具（normflow 形态）→ run() 首次执行拦截。"""

        class LateSchemaTool(CustomBaseTool):
            name = "late_schema_tool"

            def __init__(self):
                super().__init__()
                # 模拟 normflow_tools：super() 之后才设置 schema（违规形态）
                self.args_schema = _GoodInput  # type: ignore[assignment]

            def _run(self, file_path: str, _chunk_size: int = 50) -> str:
                return file_path

        tool = LateSchemaTool()  # 实例化期 schema 尚未设置，不炸
        with pytest.raises(ToolContractError, match="chunk_size"):
            tool.run(file_path="x")  # run() 首次执行兜底拦截

    def test_good_tool_run_roundtrip(self):
        """契约通过的工具，run() 注入全部 schema 字段（含默认值）可正常执行。"""
        result = GoodTool().run(file_path="a.md")
        assert result == "a.md:50"


# ─────────────────────── 2. 全量工具契约扫描（启动等价） ───────────────────────


def _discover_all_tools() -> list:
    """按 CustomToolProvider.get_tools 的同一通路扫描全部工具类并实例化。

    biz 工具经 entry point group "dawei.tools" 装载（S1，与 provider 完全同源）。
    """
    from dawei.tools import a2ui_tools, custom_tools
    from dawei.tools.custom_tools import (
        acp_tools,
        command_tools,
        cost_tools,
        edit_tools,
        knowledge_tool,
        mcp_tools,
        read_tools,
        timer_tools,
    )
    from importlib.metadata import entry_points

    modules = [
        edit_tools,
        read_tools,
        command_tools,
        acp_tools,
        mcp_tools,
        timer_tools,
        a2ui_tools,
        knowledge_tool,
        cost_tools,
        custom_tools,
    ]
    # biz 模块（阶段六 6b S1：与 provider 同一 entry point 通路装载）
    for _ep in entry_points(group="dawei.tools"):
        modules.append(_ep.load())

    seen_classes: set[type] = set()
    instances = []
    for module in modules:
        for name in dir(module):
            obj = getattr(module, name)
            if (
                inspect.isclass(obj)
                and obj is not CustomBaseTool
                and issubclass(obj, CustomBaseTool)
                and obj not in seen_classes
            ):
                seen_classes.add(obj)
                try:
                    instances.append(obj())
                except TypeError:
                    # __init__ 需要 workspace_root/user_id 的工具（provider 会注入）
                    try:
                        instances.append(obj(workspace_root=None, user_id="test_user"))
                    except TypeError:
                        instances.append(obj(user_id="test_user"))
    return instances


class TestAllToolsContract:
    def test_every_tool_satisfies_contract(self):
        """所有 CustomBaseTool 子类的 schema 字段 ⊆ _run 形参。

        任一失败都意味着该工具经 run() 100% 必挂 —— 请修工具而非放宽断言。
        """
        instances = _discover_all_tools()
        assert len(instances) > 20, f"工具发现异常：仅找到 {len(instances)} 个工具"

        violations_by_tool: dict[str, list] = {}
        for tool in instances:
            violations = get_contract_violations(tool)
            if violations:
                violations_by_tool[getattr(tool, "name", type(tool).__name__)] = violations

        assert not violations_by_tool, f"契约违规: {violations_by_tool}"
