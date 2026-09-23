# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""粒度契约（批次 A：C1-C6 / C17-C18）单元测试

覆盖 project/docs/子任务编排最优架构方案.md §3.1/§3.4 的已实施改动：
- R1 message>800 硬闸（schema 层 + _create_subtask 层双保险）
- R2 复数交付正则（宁漏勿伤：事故形态必拦，合法单任务不误伤）
- R3 复数验收（每份/逐份/全部N份 → 目标本身就是 N 份交付）
- C2 deliverable 必填 / output_file 可选约束
- L4 metadata 落库 + context_note 输出契约注入
- C5 报告回注瘦身（默认 300 字 + artifact 产物指针）
- C6 timeout "600"（字符串）经 pydantic 强转后透传 TaskData.timeout_seconds
  （事故里调用传 timeout:"600"，节点落库 null —— 单测钉死透传链）

不依赖 LLM / 网络 / 持久化，全部走内存 fake。
"""

import json
from types import SimpleNamespace

import pytest

from dawei.agentic.errors import SubtaskGranularityError
from dawei.entity.task_types import TaskStatus
from dawei.task_graph.granularity import (
    MAX_SUBTASK_MESSAGE_CHARS,
    acceptance_implies_plural,
    detect_plural_deliverables,
)
from dawei.tools.custom_tools import workflow_tools_fixed as wtf

pytestmark = pytest.mark.unit


# ==================== Fakes（与 test_subtask_delegation 同构的最小子集） ====================


class FakeTaskNode:
    def __init__(self, node_id, status=TaskStatus.PENDING, parent_id=None, description="fake task"):
        self.task_node_id = node_id
        self.task_id = node_id
        self.parent_id = parent_id
        self.status = status
        self.data = SimpleNamespace(
            description=description,
            metadata={},
            context=SimpleNamespace(
                user_id="u1",
                session_id="s1",
                message_id="m1",
                workspace_path="/tmp/ws",
                task_files=[],
                task_images=[],
                to_dict=lambda: {"user_id": "u1"},
            ),
        )

    def update_status(self, status):
        self.status = status


class FakeTaskGraph:
    def __init__(self, tasks=None):
        self.tasks: list[FakeTaskNode] = list(tasks or [])
        self.created_subtasks: list[tuple[str, object]] = []

    async def get_root_task(self):
        roots = [t for t in self.tasks if t.parent_id is None]
        return roots[0] if roots else None

    async def get_all_tasks(self):
        return list(self.tasks)

    async def create_subtask(self, parent_id, subtask_data):
        self.created_subtasks.append((parent_id, subtask_data))
        return subtask_data


# ==================== R1: message 硬顶 ====================


def test_r1_schema_rejects_long_message():
    """schema 层：message > 800 字符 pydantic 直接拒绝（LLM 根本派不出去）"""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        wtf.NewTaskInput(
            mode="pdca",
            message="x" * (MAX_SUBTASK_MESSAGE_CHARS + 1),
            acceptance="验收",
            deliverable="交付/x.md",
        )


async def test_r1_create_subtask_rejects_long_message():
    """创建层第二保险：>800 抛 SubtaskGranularityError(R1)，子任务不入图"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = wtf.NewTaskTool(task_graph=graph, workspace_root=None)

    with pytest.raises(SubtaskGranularityError) as exc_info:
        await tool._create_subtask(
            "pdca",
            "x" * (MAX_SUBTASK_MESSAGE_CHARS + 1),
            initial_todos=[],
        )
    assert exc_info.value.rule == "R1_message_too_long"
    assert graph.created_subtasks == []


# ==================== R2: 复数交付正则（宁漏勿伤） ====================


def test_r2_detects_incident_pattern():
    """事故形态必拦：一句话涵盖 6 份文件的审查指令"""
    assert detect_plural_deliverables("审查工作区 /交付/ 目录下的 6 份法律文件") is not None
    assert detect_plural_deliverables("审查以下 6 份文件：A.docx、B.docx 等") is not None
    assert detect_plural_deliverables("翻译 5 份英文合同") is not None
    assert detect_plural_deliverables("Review the 6 documents and list issues") is not None


def test_r2_legal_single_tasks_pass():
    """合法单任务不误伤（§7 风险表用例 + 既有测试消息）"""
    # "整理 3 个章节成 1 份报告"：产出仍是单一交付物 —— 必须放行
    assert detect_plural_deliverables("整理 3 个章节成 1 份报告") is None
    assert detect_plural_deliverables("起草一份保密协议") is None  # "一"不在数字集
    assert detect_plural_deliverables("审查劳动合同第 3 条") is None  # 无量词+文书组合
    assert detect_plural_deliverables("分析合同条款") is None
    assert detect_plural_deliverables("调研制裁图谱 API") is None
    assert detect_plural_deliverables("只读调研") is None


# ==================== R3: 复数验收 ====================


def test_r3_acceptance_plural_detection():
    assert acceptance_implies_plural("每份文件给出缺陷清单") is not None
    assert acceptance_implies_plural("全部 6 份通过审查") is not None
    assert acceptance_implies_plural("所有 3 份均有结论") is not None
    # 单交付物验收不受影响
    assert acceptance_implies_plural("报告含 3 个可复核引用") is None
    assert acceptance_implies_plural("tests pass with 0 failures") is None


# ==================== 硬闸经 _run 的可见错误（error + hint → 重派） ====================


async def test_new_task_run_r2_gate_returns_actionable_error(monkeypatch):
    """R2 命中 → 结构化 error（granularity_contract + hint），子任务不入图"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = wtf.NewTaskTool(task_graph=graph, workspace_root=None)
    monkeypatch.setattr(tool, "_load_available_modes", lambda: {"pdca": "PDCA 模式"})

    out = json.loads(
        await tool._run(
            mode="pdca",
            message="审查工作区 /交付/ 目录下的 6 份法律文件，逐份对照基准",
            acceptance="6 份文件均有审查结论",
            deliverable="交付/审查报告/全部.md",
        )
    )
    assert out["status"] == "error"
    assert out["error"] == "granularity_contract"
    assert out["rule"] == "R2_plural_deliverables"
    assert "hint" in out
    assert out["hint"]
    assert graph.created_subtasks == []


async def test_new_task_run_r3_gate_returns_actionable_error(monkeypatch):
    """R3 命中（message 无信号、验收是复数对象）→ 同样可操作拒绝"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = wtf.NewTaskTool(task_graph=graph, workspace_root=None)
    monkeypatch.setattr(tool, "_load_available_modes", lambda: {"pdca": "PDCA 模式"})

    out = json.loads(
        await tool._run(
            mode="pdca",
            message="开展合规审查并出具报告",
            acceptance="每份文件给出缺陷清单",
            deliverable="交付/审查报告/全部.md",
        )
    )
    assert out["status"] == "error"
    assert out["rule"] == "R3_plural_acceptance"
    assert graph.created_subtasks == []


async def test_new_task_missing_deliverable_rejected(monkeypatch):
    """C2：deliverable 缺失 → fast-fail error（与 acceptance 同款），不入图"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = wtf.NewTaskTool(task_graph=graph, workspace_root=None)
    monkeypatch.setattr(tool, "_load_available_modes", lambda: {"pdca": "PDCA 模式"})

    out = json.loads(await tool._run(mode="pdca", message="调研制裁图谱", acceptance="产出清单", deliverable="   "))
    assert out["status"] == "error"
    assert "deliverable" in out["message"]
    assert graph.created_subtasks == []


# ==================== C2/L4: deliverable / output_file 落库与输出契约 ====================


async def test_create_subtask_stores_deliverable_and_output_contract():
    """deliverable/output_file 进 metadata；output_file 同步把输出契约注入 context_note"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = wtf.NewTaskTool(task_graph=graph, workspace_root=None)

    await tool._create_subtask(
        "pdca",
        "审查新加坡劳动合同",
        initial_todos=[],
        deliverable="交付/审查报告/新加坡_劳动合同.md",
        output_file="交付/审查报告/新加坡_劳动合同.md",
        context_note="基准：模板 v3",
    )
    _, data = graph.created_subtasks[0]
    assert data.metadata["deliverable"] == "交付/审查报告/新加坡_劳动合同.md"
    assert data.metadata["output_file"] == "交付/审查报告/新加坡_劳动合同.md"
    note = data.metadata["context_note"]
    assert "基准：模板 v3" in note  # 原 context 保留
    assert "输出契约" in note  # 契约段追加
    assert "交付/审查报告/新加坡_劳动合同.md" in note
    assert "≤500 字摘要" in note


async def test_create_subtask_without_deliverable_omits_metadata():
    """内部/历史路径未提供 deliverable → metadata 无该键（零行为变化）"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = wtf.NewTaskTool(task_graph=graph, workspace_root=None)

    await tool._create_subtask("pdca", "分析合同条款", initial_todos=[])
    _, data = graph.created_subtasks[0]
    assert "deliverable" not in data.metadata
    assert "output_file" not in data.metadata


# ==================== C4: TaskValidator 粒度 warning（观察线） ====================


def _make_taskdata(description, metadata=None):
    from dawei.task_graph.task_node_data import TaskContext, TaskData

    return TaskData(
        task_node_id="n1",
        description=description,
        mode="pdca",
        context=TaskContext(user_id="u1", session_id="s1", message_id="m1"),
        metadata=metadata or {},
    )


def test_validator_warns_on_subtask_granularity():
    """子任务（metadata.parent_task_id 在场）：超长 + 疑似复数 → 双 warning"""
    from dawei.task_graph.task_validator import TaskDataValidationRule

    rule = TaskDataValidationRule()
    result = rule.validate(_make_taskdata("审查工作区 /交付/ 目录下的 6 份法律文件", metadata={"parent_task_id": "root"}))
    warnings_text = "\n".join(result.warnings)
    assert "multiple deliverables" in warnings_text  # R4 复数观察

    result2 = rule.validate(_make_taskdata("x" * 600 + "详细展开说明", metadata={"parent_task_id": "root"}))
    warnings_text2 = "\n".join(result2.warnings)
    assert "long" in warnings_text2  # R4 超长观察（>500）


def test_validator_no_granularity_warning_for_root():
    """根任务（无 parent）不加粒度 warning —— 根描述天然较长"""
    from dawei.task_graph.task_validator import TaskDataValidationRule

    rule = TaskDataValidationRule()
    result = rule.validate(_make_taskdata("审查工作区 /交付/ 目录下的 6 份法律文件"))
    warnings_text = "\n".join(result.warnings)
    assert "multiple deliverables" not in warnings_text


# ==================== C5: 报告回注瘦身（默认 300 + artifact 指针） ====================


async def test_report_injection_defaults_to_300_with_artifact_pointer():
    """默认 max_chars=300；output_file 在场 → 条目带 artifact= 指针"""
    from dawei.agentic.task_graph_excutor import TaskGraphExecutionEngine
    from dawei.conversation.conversation import Conversation

    conv = Conversation(title="t")
    ws = SimpleNamespace(current_conversation=conv, saved=0)

    async def _save():
        ws.saved += 1

    ws.save_current_conversation = _save
    engine = TaskGraphExecutionEngine(
        user_workspace=ws,
        message_processor=object(),
        llm_service=object(),
        tool_call_service=object(),
        config=SimpleNamespace(max_parallel_tasks=2),
        agent=SimpleNamespace(event_bus=object()),
    )

    sub = FakeTaskNode("sub-1", status=TaskStatus.COMPLETED, parent_id="root")
    sub.data.result = "y" * 1000
    sub.data.metadata = {"output_file": "交付/审查报告/新加坡_劳动合同.md"}

    await engine._inject_subtask_summaries([sub], [TaskStatus.COMPLETED], msg_snapshot=0)
    report = conv.messages[-1].content

    assert "y" * 300 in report  # 300 字摘要仍在
    assert "y" * 301 not in report  # 全文不再回注
    assert "artifact=交付/审查报告/新加坡_劳动合同.md" in report  # 产物指针


# ==================== C6: timeout 字符串透传钉死 ====================


def test_timeout_string_coerced_at_schema():
    """事故修复：LLM 传 timeout:"600"（字符串）→ pydantic 强转 600.0，不再落 null"""
    t = wtf.NewTaskInput(mode="pdca", message="x", acceptance="验收", deliverable="交付/x.md", timeout="600")
    assert t.timeout == 600.0
    r = wtf.RunTaskInput(mode="pdca", message="x", timeout="600")
    assert r.timeout == 600.0


async def test_timeout_string_passthrough_to_taskdata(monkeypatch):
    """透传链钉死：_run(timeout="600") → TaskData.timeout_seconds == 600.0"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = wtf.NewTaskTool(task_graph=graph, workspace_root=None)
    monkeypatch.setattr(tool, "_load_available_modes", lambda: {"pdca": "PDCA 模式"})

    out = json.loads(
        await tool._run(
            mode="pdca",
            message="调研制裁图谱",
            acceptance="产出清单",
            deliverable="交付/调研/图谱.md",
            timeout="600",
        )
    )
    assert out["status"] == "created"
    _, data = graph.created_subtasks[0]
    assert data.timeout_seconds == 600.0
