# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Evolution Prompt Builder

为各PDCA phase构建evolution上下文注入prompt。

融合架构：内置Mode System的roleDefinition + rules定义了每个phase的行为和工具权限。
本模块只负责注入evolution特有的上下文（workspace goals, cycle history, phase inputs），
不替代内置mode的prompt。

Phase输入输出关系：
    - PLAN: dao.md + (prev/action.md) → plan.md
    - DO: plan.md → do.md
    - CHECK: dao.md + (prev/action.md) + plan.md + do.md → check.md
    - ACT: dao.md + plan.md + do.md + check.md → action.md
"""

import logging

logger = logging.getLogger(__name__)


class EvolutionPromptBuilder:
    """Evolution上下文注入器

    为每个PDCA phase注入evolution特有的上下文信息。
    内置mode的roleDefinition处理"怎么做"，这里只提供"做什么"和"上下文"。

    使用方式：
        builder = EvolutionPromptBuilder()
        context = builder.build("plan", inputs, "001", None)
        # context 会作为用户消息发送给Agent
    """

    PHASE_OUTPUT_FILES = {
        "plan": "plan.md",
        "do": "do.md",
        "check": "check.md",
        "act": "action.md",
    }

    def build(self, phase: str, inputs: dict, cycle_id: str, prev_cycle_id: str | None) -> str:
        """构建evolution上下文prompt

        Args:
            phase: Phase名称（plan, do, check, act）
            inputs: 输入数据字典（来自_load_phase_inputs）
            cycle_id: 当前cycle ID
            prev_cycle_id: 上一个cycle ID（可选）

        Returns:
            str: evolution上下文prompt

        Raises:
            ValueError: 当phase名称无效时

        """
        if phase not in self.PHASE_OUTPUT_FILES:
            raise ValueError(f"Unknown phase: {phase}. Must be one of: {list(self.PHASE_OUTPUT_FILES.keys())}")

        prompt = self._build_evolution_context(phase, inputs, cycle_id, prev_cycle_id)

        logger.debug(f"[EVOLUTION_PROMPT] Built {phase.upper()} context for cycle {cycle_id} ({len(prompt)} chars)")

        return prompt

    def _build_evolution_context(self, phase: str, inputs: dict, cycle_id: str, prev_cycle_id: str | None) -> str:
        """构建evolution上下文

        只注入evolution特有的信息，不定义phase行为（由内置mode处理）。

        """
        workspace_md = inputs.get("workspace_md", "")
        prev_action = inputs.get("prev_action", "")
        output_file = self.PHASE_OUTPUT_FILES[phase]

        # Phase-specific input files
        phase_files = self._get_phase_input_files(phase, inputs, cycle_id)

        # Previous cycle section
        prev_section = self._get_prev_cycle_section(prev_cycle_id, prev_action)

        return f"""# Evolution Context

You are running as part of **Evolution Cycle {cycle_id}**, phase: **{phase.upper()}**

## Workspace Goals
{workspace_md or "(No dao.md defined)"}
{prev_section}
## Phase Inputs
{phase_files or "(No additional inputs for this phase)"}

## Evolution Rules
- Save your phase output to `.dawei/evolution-{cycle_id}/{output_file}`
- Focus on the workspace goals above
- Be specific and actionable
- This is part of an automated PDCA improvement cycle
- {self._get_phase_specific_rule(phase)}
"""

    def _get_phase_input_files(self, phase: str, inputs: dict, cycle_id: str) -> str:
        """获取phase特定的输入文件内容"""
        sections = []

        if phase == "do":
            plan = inputs.get("plan", "")
            if plan:
                sections.append(f"### Current Plan (.dawei/evolution-{cycle_id}/plan.md)\n```\n{plan}\n```")

        elif phase == "check":
            plan = inputs.get("plan", "")
            do = inputs.get("do", "")
            if plan:
                sections.append(f"### Plan (.dawei/evolution-{cycle_id}/plan.md)\n```\n{plan}\n```")
            if do:
                sections.append(f"### Do Progress (.dawei/evolution-{cycle_id}/do.md)\n```\n{do}\n```")

        elif phase == "act":
            plan = inputs.get("plan", "")
            check = inputs.get("check", "")
            if plan:
                # Truncate plan for act phase to reduce token usage
                sections.append(f"### Plan Summary (.dawei/evolution-{cycle_id}/plan.md)\n```\n{plan[:500]}\n```")
            if check:
                sections.append(f"### Check Report (.dawei/evolution-{cycle_id}/check.md)\n```\n{check}\n```")

        return "\n\n".join(sections)

    def _get_prev_cycle_section(self, prev_cycle_id: str | None, prev_action: str) -> str:
        """获取上一个cycle的上下文"""
        if not prev_cycle_id or not prev_action:
            return "## Note\nThis is the FIRST evolution cycle. No previous action.md exists.\n"

        # Truncate to avoid excessive token usage
        truncated = prev_action[:1000] if len(prev_action) > 1000 else prev_action
        suffix = "\n...(truncated)\n" if len(prev_action) > 1000 else ""

        return f"""## Previous Cycle ({prev_cycle_id}) Actions
```
{truncated}{suffix}
```
"""

    def _get_phase_specific_rule(self, phase: str) -> str:
        """获取phase特定的补充规则"""
        rules = {
            "plan": "Analyze the workspace goals and previous actions to create an actionable improvement plan",
            "do": "Execute the plan tasks and track progress — make real changes using available tools",
            "check": "Verify results against plan and workspace goals — identify gaps and measure outcomes",
            "act": "Synthesize insights and create action items for the next cycle's plan",
        }
        return rules.get(phase, "")
