# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""批量并行派发与去重身份（批次 B：C7-C9）单元测试

覆盖 project/docs/子任务编排最优架构方案.md §3.2/§3.3 的已实施改动：
- C7 new_task_batch：模板展开、R5 条目硬顶（>max_batch_items fast-fail）、
  identity 唯一性校验、逐项容错（占位符缺失/粒度违规不炸整批）
- C8 dispatch_identity：hash(mode+deliverable+item.identity) 去重身份；
  等价重派熔断（标点差异不再绕过）、不同 identity 互不误伤、
  legacy 节点（无身份）回落 description 前缀比对
- C9 闸门重划：batch 合法形态放行（工具层 fast-path 旁路）、
  配置默认值钉死（8/8/16 + agent_config.max_parallel_tasks=3）

不依赖 LLM / 网络 / 持久化，全部走内存 fake。
"""

import json
from types import SimpleNamespace

import pytest

from dawei.entity.task_types import TaskStatus
from dawei.tools.custom_tools import workflow_tools_fixed as wtf

pytestmark = pytest.mark.unit


# ==================== Fakes（与 test_granularity_contract 同构） ====================


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


def _node_of(data, status=TaskStatus.PENDING) -> FakeTaskNode:
    """把已创建的 TaskData 包装回 FakeTaskNode 入图（模拟后续轮次重派视角）"""
    node = FakeTaskNode(data.task_node_id, status=status, parent_id="root", description=str(data.description))
    node.data.metadata = dict(data.metadata or {})
    return node


# ==================== 夹具 ====================


@pytest.fixture
def pdca_modes(monkeypatch):
    """模式层打桩：清单 + 可委派校验。类级打桩使 NewTaskBatchTool._run
    内部的临时 NewTaskTool 实例同享；registry 打桩保证 can_delegate 判定确定性。"""
    monkeypatch.setattr(
        wtf.NewTaskTool,
        "_load_available_modes",
        lambda _self: {"pdca": "PDCA 模式", "orchestrator": "协调者"},
    )
    monkeypatch.setattr(
        "dawei.mode.registry.get_registry",
        lambda _workspace_root=None: SimpleNamespace(can_delegate_to=lambda slug: slug != "orchestrator"),
    )


@pytest.fixture
def gates8(monkeypatch):
    """C9 语义钉死：并发 8 / 单批 16（防宿主 env 覆盖导致用例漂移）"""
    from dawei.config.settings import get_settings

    ae = get_settings().agent_execution
    monkeypatch.setattr(ae, "max_concurrent_subtasks", 8)
    monkeypatch.setattr(ae, "max_batch_items", 16)


def _make_batch_tool(graph):
    return wtf.NewTaskBatchTool(task_graph=graph, workspace_root=None)


BATCH_KW = {
    "mode": "pdca",
    "template": "审查文件 {item.path}，出具审查意见",
    "acceptance_template": "{item.identity} 的审查报告包含 7 个章节",
    "deliverable_template": "交付/审查报告/{item.identity}.md",
}


async def _dispatch(tool, items, **overrides):
    kw = {**BATCH_KW, "items": items, **overrides}
    return json.loads(await tool._run(**kw))


# ==================== C8: _dispatch_identity ====================


def test_dispatch_identity_stable_and_discriminating():
    a = wtf._dispatch_identity("pdca", "交付/报告.md", item_identity="新加坡")
    assert a == wtf._dispatch_identity("pdca", "交付/报告.md", item_identity="新加坡")
    assert len(a) == 16
    # 任一分量变化 → 身份不同（batch 项互异 → 互不误伤）
    assert a != wtf._dispatch_identity("pdca", "交付/报告.md", item_identity="日本")
    assert a != wtf._dispatch_identity("pdca", "交付/其他.md", item_identity="新加坡")
    assert a != wtf._dispatch_identity("research", "交付/报告.md", item_identity="新加坡")


def test_dispatch_identity_ignores_punctuation_difference():
    """2026-09-20 conv 9f2d4586 回归：仅差标点的等价重派必须同身份"""
    a = wtf._dispatch_identity("pdca", "D", message="任务——审查新加坡劳动合同")
    b = wtf._dispatch_identity("pdca", "D", message="任务：审查新加坡劳动合同")
    assert a == b


def test_dispatch_identity_message_window_400():
    """无 item_identity 时归一化 message 取 400 字窗口：尾部差异不影响身份"""
    base = "审查目标" * 150  # 600 字，超出窗口
    a = wtf._dispatch_identity("pdca", "D", message=base + "AAAA")
    b = wtf._dispatch_identity("pdca", "D", message=base + "BBBB")
    assert a == b
    # 窗口内的差异仍然生效
    assert a != wtf._dispatch_identity("pdca", "D", message="X" + base)


# ==================== C7: 模板展开 happy path ====================


async def test_batch_expansion_creates_all_items(pdca_modes, gates8):
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)
    items = [wtf.BatchItem(identity=f"file-{i}", path=f"交付/{i}.docx") for i in range(3)]

    out = await _dispatch(tool, items)

    assert out["status"] == "dispatched"
    assert out["created_count"] == 3
    assert out["batch_id"]
    assert [r["identity"] for r in out["results"]] == ["file-0", "file-1", "file-2"]
    assert all(r["status"] == "created" for r in out["results"])
    assert len(graph.created_subtasks) == 3

    identities = set()
    for parent, data in graph.created_subtasks:
        assert parent == "root"
        meta = data.metadata
        assert meta["batch_id"] == out["batch_id"]
        assert meta["created_by"] == "NewTaskBatchTool"
        assert meta["item_identity"].startswith("file-")
        assert meta["deliverable"] == f"交付/审查报告/{meta['item_identity']}.md"
        assert meta["dispatch_identity"]
        # 模板展开进描述与验收（每项自包含单交付物）
        assert "审查文件 交付/" in data.description
        assert data.acceptance_criteria.startswith(meta["item_identity"])
        identities.add(meta["dispatch_identity"])
    assert len(identities) == 3  # 身份互异（去重分量生效）


async def test_batch_output_file_template_writes_contract(pdca_modes, gates8):
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)

    out = await _dispatch(
        tool,
        [wtf.BatchItem(identity="file-0", path="交付/0.docx")],
        output_file_template="交付/审查报告/{item.identity}.md",
    )
    assert out["created_count"] == 1
    _, data = graph.created_subtasks[0]
    assert data.metadata["output_file"] == "交付/审查报告/file-0.md"
    note = data.metadata["context_note"]
    assert "输出契约" in note
    assert "交付/审查报告/file-0.md" in note
    assert "≤500 字摘要" in note


def test_batch_schema_constraints():
    """schema 层：template≤600、identity 1-200、items≥1"""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        wtf.NewTaskBatchInput(
            mode="pdca",
            template="t" * 601,
            items=[wtf.BatchItem(identity="a")],
            acceptance_template="x",
            deliverable_template="d",
        )
    with pytest.raises(pydantic.ValidationError):
        wtf.BatchItem(identity="")
    with pytest.raises(pydantic.ValidationError):
        wtf.BatchItem(identity="x" * 201)


def test_new_task_batch_registered_in_workflow_group():
    from dawei.tools.tool_manager import TOOL_GROUPS

    assert "new_task_batch" in TOOL_GROUPS["workflow"]["tools"]


# ==================== R5: 条目硬顶 / identity 唯一性 ====================


async def test_r5_rejects_items_over_hard_cap(pdca_modes, gates8):
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)

    out = await _dispatch(tool, [wtf.BatchItem(identity=f"x-{i}") for i in range(17)])
    assert out["status"] == "error"
    assert out["error"] == "batch_limit"
    assert "max_batch_items=16" in out["message"]
    assert graph.created_subtasks == []


async def test_r5_empty_items_rejected(pdca_modes, gates8):
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)

    out = await _dispatch(tool, [])
    assert out["status"] == "error"
    assert out["error"] == "empty_items"
    assert graph.created_subtasks == []


async def test_duplicate_identity_rejected_with_indices(pdca_modes, gates8):
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)

    out = await _dispatch(tool, [wtf.BatchItem(identity="a"), wtf.BatchItem(identity="b"), wtf.BatchItem(identity="a")])
    assert out["status"] == "error"
    assert out["error"] == "duplicate_identity"
    assert "items[0]" in out["message"]
    assert "items[2]" in out["message"]
    assert graph.created_subtasks == []


async def test_whitespace_identity_rejected(pdca_modes, gates8):
    """identity 仅空白（绕过 pydantic min_length）→ 工具层 strip 校验拦截"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)

    out = await _dispatch(tool, [wtf.BatchItem(identity="  ")])
    assert out["status"] == "error"
    assert out["error"] == "invalid_identity"
    assert "items[0]" in out["message"]


# ==================== 逐项容错（单条失败不炸整批） ====================


async def test_template_placeholder_error_is_per_item(pdca_modes, gates8):
    """模板引用 item.path，缺失该项的条目逐项报错，其余照常创建"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)
    items = [wtf.BatchItem(identity="ok", path="交付/a.docx"), wtf.BatchItem(identity="bad")]

    out = await _dispatch(tool, items)
    assert out["created_count"] == 1
    statuses = {r["identity"]: r["status"] for r in out["results"]}
    assert statuses["ok"] == "created"
    assert statuses["bad"] == "error"
    bad = next(r for r in out["results"] if r["identity"] == "bad")
    assert bad["error"] == "template_placeholder"


async def test_granularity_contract_applies_per_item(pdca_modes, gates8):
    """R2 巨子任务正则在展开后的 message 上逐项生效（batch 不是粒度豁免通道）"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)

    out = await _dispatch(
        tool,
        [wtf.BatchItem(identity="file-0", path="交付/x.docx"), wtf.BatchItem(identity="file-1", path="交付/y.docx")],
        template="审查工作区 /交付/ 目录下的 6 份法律文件：{item.identity}",
    )
    assert out["status"] == "error"
    assert out["created_count"] == 0
    assert all(r["error"] == "granularity_contract" and r["rule"] == "R2_plural_deliverables" for r in out["results"])
    assert graph.created_subtasks == []


# ==================== C8: 去重语义（等价重派熔断 / 互不误伤） ====================


async def test_redispatch_same_batch_all_duplicate(pdca_modes, gates8):
    """同批等价重派 → 逐项 duplicate + 回指既有 subtask_id，不再重复入图"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)
    items = [wtf.BatchItem(identity="a", path="交付/a.docx"), wtf.BatchItem(identity="b", path="交付/b.docx")]

    first = await _dispatch(tool, items)
    assert first["created_count"] == 2

    # 模拟报告回来前的等价重派：已建节点入图（未终结 → 阻断集）
    for _, data in graph.created_subtasks:
        graph.tasks.append(_node_of(data, status=TaskStatus.RUNNING))

    second = await _dispatch(tool, items)
    assert second["created_count"] == 0
    assert all(r["status"] == "duplicate" and r.get("existing_subtask_id") for r in second["results"])
    assert len(graph.created_subtasks) == 2  # 未新增


async def test_different_identity_never_collides(pdca_modes, gates8):
    """同模板不同 identity 的第二批 → 照常创建（去重身份区分 batch 项）"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)

    first = await _dispatch(tool, [wtf.BatchItem(identity="a", path="交付/a.docx")])
    assert first["created_count"] == 1
    graph.tasks.append(_node_of(graph.created_subtasks[0][1], status=TaskStatus.RUNNING))

    second = await _dispatch(tool, [wtf.BatchItem(identity="b", path="交付/b.docx")])
    assert second["created_count"] == 1
    assert second["results"][0]["status"] == "created"


async def test_new_task_equivalent_redispatch_blocked(pdca_modes, gates8):
    """C8 回归：单个 new_task 等价重派（仅标点差异）→ dispatch_identity 熔断

    事故背景（1.79M tokens）：旧前缀熔断被"任务——"vs"任务："的 1 字标点差绕过。
    """
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = wtf.NewTaskTool(task_graph=graph, workspace_root=None)

    first = json.loads(
        await tool._run(
            mode="pdca",
            message="任务——审查新加坡劳动合同",
            acceptance="报告包含风险清单",
            deliverable="交付/审查报告/新加坡.md",
        )
    )
    assert first["status"] == "created"
    graph.tasks.append(_node_of(graph.created_subtasks[0][1]))

    second = json.loads(
        await tool._run(
            mode="pdca",
            message="任务：审查新加坡劳动合同",  # 仅标点差异 → 等价重派
            acceptance="报告包含风险清单",
            deliverable="交付/审查报告/新加坡.md",
        )
    )
    assert second["status"] == "error"
    assert second["error"] == "duplicate_subtask"
    assert second["existing_subtask_id"]
    assert len(graph.created_subtasks) == 1


async def test_legacy_node_prefix_fallback_still_blocks(pdca_modes, gates8):
    """历史节点（无 dispatch_identity）回落 description 前缀比对（会话恢复兼容）"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    legacy = FakeTaskNode("legacy-1", status=TaskStatus.RUNNING, parent_id="root", description="调研制裁图谱 API 的最新进展")
    graph.tasks.append(legacy)

    tool = wtf.NewTaskTool(task_graph=graph, workspace_root=None)
    out = json.loads(
        await tool._run(
            mode="pdca",
            message="调研制裁图谱 API 的最新进展",
            acceptance="产出清单",
            deliverable="交付/调研/图谱.md",
        )
    )
    assert out["status"] == "error"
    assert out["error"] == "duplicate_subtask"


# ==================== C9: batch 合法形态放行（工具层 fast-path） ====================


async def test_batch_bypasses_tool_layer_concurrency_gate(pdca_modes, gates8):
    """8 个未终结占满创建闸后 —— 单个 new_task 被拒，batch 3 项照常展开"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    for i in range(8):
        graph.tasks.append(FakeTaskNode(f"busy-{i}", parent_id="root", description=f"占用槽位 {i}"))

    single = wtf.NewTaskTool(task_graph=graph, workspace_root=None)
    out_single = json.loads(await single._run(mode="pdca", message="零散调研任务", acceptance="产出清单", deliverable="交付/调研.md"))
    assert out_single["status"] == "error"
    assert "并发子任务上限" in out_single["error"]

    tool = _make_batch_tool(graph)
    out_batch = await _dispatch(tool, [wtf.BatchItem(identity=f"file-{i}", path=f"交付/{i}.docx") for i in range(3)])
    assert out_batch["status"] == "dispatched"
    assert out_batch["created_count"] == 3


def test_c9_default_gate_limits():
    """C9 默认值钉死：创建/广度闸 8、单批硬顶 16、执行并发信号量 3
    （agent_config 此前无 max_parallel_tasks 字段，引擎恒回落 2）"""
    from dawei.config.settings import get_settings

    ae = get_settings().agent_execution
    assert ae.max_active_subtasks == 8
    assert ae.max_concurrent_subtasks == 8
    assert ae.max_batch_items == 16

    from dawei.agentic.agent_config import Config

    cfg = Config()
    assert cfg.max_concurrent_subtasks == 8
    assert cfg.max_parallel_tasks == 3


def test_max_parallel_tasks_env_and_dict_override(monkeypatch):
    """引擎信号量字段可经 dict / env 覆盖（4 处配置管道全部接线）"""
    from dawei.agentic.agent_config import Config, create_config_from_dict

    assert create_config_from_dict({"max_parallel_tasks": 7}).max_parallel_tasks == 7
    monkeypatch.setenv("AGENT_MAX_PARALLEL_TASKS", "5")
    assert Config().max_parallel_tasks == 5


# ==================== 模式校验 ====================


async def test_batch_mode_not_found(pdca_modes, gates8):
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)

    out = await _dispatch(tool, [wtf.BatchItem(identity="a", path="交付/a.docx")], mode="ghost")
    assert out["status"] == "error"
    assert "ghost" in out["message"]
    assert "available_modes" in out
    assert graph.created_subtasks == []


async def test_batch_rejects_non_delegable_mode(pdca_modes, gates8):
    """can_delegate=false（如 orchestrator）不可作为批量派发目标"""
    graph = FakeTaskGraph([FakeTaskNode("root", status=TaskStatus.RUNNING)])
    tool = _make_batch_tool(graph)

    out = await _dispatch(tool, [wtf.BatchItem(identity="a", path="交付/a.docx")], mode="orchestrator")
    assert out["status"] == "error"
    assert "cannot be delegated" in out["message"]
    assert graph.created_subtasks == []
