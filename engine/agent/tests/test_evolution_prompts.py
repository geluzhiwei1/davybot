# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for Evolution Prompt Builder

测试EvolutionPromptBuilder的上下文注入功能。
所有测试都是纯同步的（无asyncio依赖），不需要mock workspace。
"""

import pytest

from dawei.evolution.prompts import EvolutionPromptBuilder


@pytest.fixture
def builder():
    return EvolutionPromptBuilder()


class TestEvolutionPromptBuilder:
    """EvolutionPromptBuilder单元测试"""

    def test_build_plan_first_cycle(self, builder):
        """第一轮cycle的plan phase应包含workspace.md且无prev action"""
        inputs = {"workspace_md": "Goal: improve code quality", "prev_action": "", "prev_cycle_id": None}

        result = builder.build("plan", inputs, "001", None)

        assert "Evolution Cycle 001" in result
        assert "PLAN" in result
        assert "Goal: improve code quality" in result
        assert "FIRST evolution cycle" in result
        assert "plan.md" in result

    def test_build_plan_subsequent_cycle(self, builder):
        """后续cycle的plan phase应包含prev action"""
        inputs = {"workspace_md": "Goal: improve code quality", "prev_action": "Fix bug #123", "prev_cycle_id": "001"}

        result = builder.build("plan", inputs, "002", "001")

        assert "Evolution Cycle 002" in result
        assert "Previous Cycle (001)" in result
        assert "Fix bug #123" in result
        assert "FIRST evolution cycle" not in result

    def test_build_do(self, builder):
        """DO phase应包含plan输入"""
        inputs = {"plan": "1. Fix bug\n2. Add tests", "workspace_md": "", "prev_action": "", "prev_cycle_id": None}

        result = builder.build("do", inputs, "001", None)

        assert "DO" in result
        assert "Current Plan" in result
        assert "Fix bug" in result
        assert "do.md" in result

    def test_build_check(self, builder):
        """CHECK phase应包含plan和do输入"""
        inputs = {"plan": "Plan content", "do": "Did task 1", "workspace_md": "Goals", "prev_action": "", "prev_cycle_id": None}

        result = builder.build("check", inputs, "001", None)

        assert "CHECK" in result
        assert "Plan" in result
        assert "Do Progress" in result
        assert "Plan content" in result
        assert "Did task 1" in result
        assert "check.md" in result

    def test_build_act(self, builder):
        """ACT phase应包含check报告和plan摘要"""
        inputs = {"plan": "Plan content", "do": "Did tasks", "check": "Check report", "workspace_md": "Goals", "prev_action": "", "prev_cycle_id": None}

        result = builder.build("act", inputs, "001", None)

        assert "ACT" in result
        assert "Check Report" in result
        assert "Check report" in result
        assert "Plan Summary" in result
        assert "action.md" in result

    def test_build_act_truncates_long_plan(self, builder):
        """ACT phase应截断过长的plan内容"""
        long_plan = "x" * 1000
        inputs = {"plan": long_plan, "do": "done", "check": "checked", "workspace_md": "", "prev_action": "", "prev_cycle_id": None}

        result = builder.build("act", inputs, "001", None)

        # Plan should be truncated to ~500 chars
        assert len(result) < len(long_plan) + 1000  # generous bound

    def test_build_truncates_long_prev_action(self, builder):
        """过长的prev action应被截断"""
        long_action = "y" * 2000
        inputs = {"workspace_md": "", "prev_action": long_action, "prev_cycle_id": "001"}

        result = builder.build("plan", inputs, "002", "001")

        assert "truncated" in result

    def test_build_invalid_phase_raises(self, builder):
        """无效的phase名称应抛出ValueError"""
        with pytest.raises(ValueError, match="Unknown phase"):
            builder.build("invalid", {}, "001", None)

    def test_build_empty_inputs(self, builder):
        """空输入不应崩溃"""
        inputs = {"workspace_md": "", "prev_action": "", "prev_cycle_id": None}

        result = builder.build("plan", inputs, "001", None)

        assert "Evolution Cycle 001" in result
        assert "No dao.md defined" in result

    def test_phase_specific_rules(self, builder):
        """每个phase应有特定的补充规则"""
        empty_inputs = {"workspace_md": "", "prev_action": "", "prev_cycle_id": None}

        plan = builder.build("plan", empty_inputs, "001", None)
        assert "Analyze the workspace goals" in plan

        do = builder.build("do", empty_inputs, "001", None)
        assert "Execute the plan tasks" in do

        check = builder.build("check", empty_inputs, "001", None)
        assert "Verify results" in check

        act = builder.build("act", empty_inputs, "001", None)
        assert "Synthesize insights" in act

    def test_output_file_in_rules(self, builder):
        """每个phase的output path应正确"""
        empty_inputs = {"workspace_md": "", "prev_action": "", "prev_cycle_id": None}

        plan = builder.build("plan", empty_inputs, "001", None)
        assert "evolution-001/plan.md" in plan

        do = builder.build("do", empty_inputs, "001", None)
        assert "evolution-001/do.md" in do

        check = builder.build("check", empty_inputs, "001", None)
        assert "evolution-001/check.md" in check

        act = builder.build("act", empty_inputs, "001", None)
        assert "evolution-001/action.md" in act

    def test_no_phase_inputs_for_plan(self, builder):
        """Plan phase不需要额外输入文件"""
        inputs = {"workspace_md": "goals", "prev_action": "", "prev_cycle_id": None}

        result = builder.build("plan", inputs, "001", None)

        # Should not have "Current Plan" or other phase input sections
        assert "Current Plan" not in result
        assert "No additional inputs for this phase" in result

    def test_all_phases_have_pdca_reference(self, builder):
        """所有phase都应引用PDCA cycle"""
        empty_inputs = {"workspace_md": "", "prev_action": "", "prev_cycle_id": None}

        for phase in ["plan", "do", "check", "act"]:
            result = builder.build(phase, empty_inputs, "001", None)
            assert "PDCA" in result or "Evolution Cycle" in result
