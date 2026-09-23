# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""韧性批次（批次 D：C13/C14/C15）单元测试

覆盖 project/docs/子任务编排最优架构方案.md §3.4/§4 已实施改动：
- C13 瞬时 LLM provider 错误自动重试：分类器（502/503/504 SSE 包装 /
  stream timeout / 流中断）、node executor 不发致命前端错误（重试待定）、
  graph executor 同节点重试与耗尽 fast-fail
- C14 子任务预算全局闸门默认值：subtask_timeout=900 / subtask_token_budget=200_000
- C15 粒度/批量/单项失败率/自动重试命中率指标埋点

不依赖 LLM / 网络 / 持久化，全部走内存 fake。
"""

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from dawei.agentic.subtask_metrics import get_metrics
from dawei.core.errors import LLMError  # stream_processor/llm_api 实际抛出的类型（handler 捕获同一类）
from dawei.entity.task_types import TaskStatus

pytestmark = pytest.mark.unit


# ==================== 共享 fake ====================


class _FakeData:
    """TaskData 最小面：重试循环只消费 can_retry/increment_retry/retry_count"""

    def __init__(self):
        self.status = TaskStatus.PENDING
        self.retry_count = 0
        self.max_retries = 3
        self.is_retryable = True
        self.metadata: dict = {}

    def can_retry(self) -> bool:
        return self.is_retryable and self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        self.retry_count += 1


class _FakeNode:
    def __init__(self, node_id="sub-1", parent_id=None):
        self.task_node_id = node_id
        self.parent_id = parent_id
        self.status = TaskStatus.PENDING
        self.mode = None
        self.data = _FakeData()
        self.sub_graph = None


class _FlakyExecutor:
    """前 failures 次抛 exc，之后置节点 COMPLETED（模拟重试后恢复）"""

    def __init__(self, node, failures=0, exc=None):
        self._node = node
        self._failures = failures
        self._exc = exc
        self.calls = 0

    async def execute_task(self):
        self.calls += 1
        if self.calls <= self._failures:
            raise self._exc
        self._node.status = TaskStatus.COMPLETED


@pytest.fixture
def metrics():
    """全局指标单例：每用例前后清零，避免跨用例污染"""
    m = get_metrics()
    m.reset()
    yield m
    m.reset()


@pytest.fixture
def graph_engine():
    """TaskGraphExecutionEngine：只打桩 _execute_task_and_handle_completion
    直接/间接消费的旁路（错误事件/状态写回/子任务查询），被测逻辑保持真实。"""
    from dawei.agentic.task_graph_excutor import TaskGraphExecutionEngine

    agent = MagicMock()
    agent.event_bus = MagicMock()
    engine = TaskGraphExecutionEngine(
        user_workspace=MagicMock(),
        message_processor=MagicMock(),
        llm_service=MagicMock(),
        tool_call_service=MagicMock(),
        config=SimpleNamespace(max_parallel_tasks=1),
        agent=agent,
    )
    engine._emit_error_event = AsyncMock()
    engine._update_task_status = AsyncMock()
    engine._emit_subtask_lifecycle_event = AsyncMock()
    engine._get_subtasks_with_grace = AsyncMock(return_value=[])
    engine._has_unconsumed_subtask_report = MagicMock(return_value=False)
    yield engine
    try:  # __init__ 把 self 注册为 run_task 全局活动引擎，测试后复位
        from dawei.tools.custom_tools.workflow_tools_fixed import set_active_execution_engine

        set_active_execution_engine(None)
    except Exception:  # noqa: BLE001
        pass


# ==================== C13: is_transient_llm_provider_error ====================


def test_c13_classifier_matches_transient_gateway_errors():
    from dawei.agentic.task_node_executor import is_transient_llm_provider_error

    # SSE 包装的网关 5xx（2026-09-22 事故 c5d42736：HTTP 200 + error 事件）
    assert is_transient_llm_provider_error("Provider error (504): gateway timeout after 300s")
    assert is_transient_llm_provider_error("Provider error(502): bad gateway")
    assert is_transient_llm_provider_error("provider ERROR ( 503 ) service unavailable")
    # 流中断 / 流卡死
    assert is_transient_llm_provider_error("LLM stream timeout after 120s")
    assert is_transient_llm_provider_error("Connection closed by peer")
    assert is_transient_llm_provider_error("Server disconnected")


def test_c13_classifier_rejects_non_transient_errors():
    from dawei.agentic.task_node_executor import is_transient_llm_provider_error

    assert not is_transient_llm_provider_error("Provider error (400): invalid request")
    assert not is_transient_llm_provider_error("Provider error (401): unauthorized")
    assert not is_transient_llm_provider_error("429 rate_limit_exceeded")
    assert not is_transient_llm_provider_error("Insufficient credits")
    assert not is_transient_llm_provider_error("")
    assert not is_transient_llm_provider_error(None)


# ==================== C13: node executor 不抢发致命前端错误 ====================


def _bare_node_executor(**attrs):
    """跳过 __init__ 的 TaskNodeExecutionEngine（只挂 process_message 消费的属性）"""
    from dawei.agentic.task_node_executor import TaskNodeExecutionEngine

    ex = TaskNodeExecutionEngine.__new__(TaskNodeExecutionEngine)
    ex.task_node = _FakeNode("sub-1", parent_id=None)  # parent_id None → 跳过共享会话指令注入
    ex._agent = None
    ex._conversation = None
    ex._user_workspace = SimpleNamespace(current_conversation=None, mode=None)
    ex._message_processor = MagicMock()
    ex._llm_service = MagicMock()
    ex._event_bus = MagicMock()
    ex._config = SimpleNamespace(enable_skills=False, enable_mcp=False)
    ex.logger = logging.getLogger("test-resilience")
    ex._tool_message_handler = MagicMock()
    ex._current_message_id = None
    ex._message_counter = 0
    ex._consecutive_truncated_rounds = 0
    ex._send_error_to_frontend = AsyncMock()
    ex._save_checkpoint = AsyncMock()
    ex._message_processor.build_messages = AsyncMock(return_value={"messages": [{"role": "user", "content": "hi"}], "tools": [{"type": "function", "function": {"name": "t"}}]})
    for k, v in attrs.items():
        setattr(ex, k, v)
    return ex


async def test_c13_transient_504_suppresses_fatal_frontend_error():
    """504 且服务端还会重试 → 静默上抛（不发 error 帧终止前端会话）"""
    ex = _bare_node_executor()
    ex._llm_service.get_current_provider = MagicMock(return_value="deepseek")
    ex._llm_service.create_message_with_callback = AsyncMock(side_effect=LLMError("openai", "Provider error (504): gateway timeout"))

    with pytest.raises(LLMError):
        await ex.process_message()

    ex._send_error_to_frontend.assert_not_awaited()


async def test_c13_non_transient_still_sends_frontend_error():
    """400 类永久错误 → 保持旧行为：致命 error 帧对用户可见"""
    ex = _bare_node_executor()
    ex._llm_service.get_current_provider = MagicMock(return_value="deepseek")
    ex._llm_service.create_message_with_callback = AsyncMock(side_effect=LLMError("openai", "Provider error (400): invalid request"))

    with pytest.raises(LLMError):
        await ex.process_message()

    ex._send_error_to_frontend.assert_awaited_once()


# ==================== C13: graph executor 同节点自动重试 ====================


async def test_c13_transient_504_retries_then_succeeds(graph_engine, metrics, monkeypatch):
    """504 → 同节点自动重试 → 第 2 次成功：COMPLETED + 命中率分子分母各 1"""

    async def _fast_sleep(_delay):  # 跳过指数退避的真实等待
        return None

    monkeypatch.setattr("dawei.agentic.task_graph_excutor.asyncio.sleep", _fast_sleep)

    node = _FakeNode()
    executor = _FlakyExecutor(node, failures=1, exc=LLMError("openai", "Provider error (504): gateway timeout"))
    graph_engine._get_or_create_executor = AsyncMock(return_value=executor)

    result = await graph_engine._execute_task_and_handle_completion(node, node.task_node_id, executor)

    assert result is TaskStatus.COMPLETED
    assert executor.calls == 2
    assert metrics.llm_retry_scheduled_total == 1
    assert metrics.llm_retry_success_total == 1


async def test_c13_transient_504_retry_exhaustion_fails(graph_engine, metrics, monkeypatch):
    """504 持续 → 重试耗尽（max_retries=3）→ FAILED + 错误事件，不再无脑烧 token"""

    async def _fast_sleep(_delay):
        return None

    monkeypatch.setattr("dawei.agentic.task_graph_excutor.asyncio.sleep", _fast_sleep)

    node = _FakeNode()
    executor = _FlakyExecutor(node, failures=99, exc=LLMError("openai", "Provider error (504): gateway timeout"))
    graph_engine._get_or_create_executor = AsyncMock(return_value=executor)

    result = await graph_engine._execute_task_and_handle_completion(node, node.task_node_id, executor)

    assert result is TaskStatus.FAILED
    assert executor.calls == 3  # max_retries=3
    assert metrics.llm_retry_scheduled_total == 2  # 3 次尝试之间 2 次重排
    assert metrics.llm_retry_success_total == 0
    graph_engine._emit_error_event.assert_awaited()


async def test_c13_non_transient_provider_error_fast_raises(graph_engine, metrics):
    """400 类永久错误 → 不进重试分类 → 立即上抛（FAST FAIL），无重试指标"""
    node = _FakeNode()
    executor = _FlakyExecutor(node, failures=99, exc=LLMError("openai", "Provider error (400): invalid request"))
    graph_engine._get_or_create_executor = AsyncMock(return_value=executor)

    with pytest.raises(LLMError):
        await graph_engine._execute_task_and_handle_completion(node, node.task_node_id, executor)

    assert executor.calls == 1
    assert metrics.llm_retry_scheduled_total == 0
    graph_engine._emit_error_event.assert_awaited()


# ==================== C14: 预算全局闸门默认值 ====================


def test_c14_default_budget_gates(monkeypatch):
    """默认 subtask_timeout=900 / subtask_token_budget=200_000（env 可覆盖为 -1 关闭）"""
    monkeypatch.delenv("AGENT_SUBTASK_TIMEOUT", raising=False)
    monkeypatch.delenv("AGENT_SUBTASK_TOKEN_BUDGET", raising=False)
    from dawei.config.settings import AgentExecutionConfig

    cfg = AgentExecutionConfig(_env_file="/nonexistent/.env")  # 隔离宿主 .env 漂移
    assert cfg.subtask_timeout == 900
    assert cfg.subtask_token_budget == 200_000


def test_c14_env_can_disable_gates(monkeypatch):
    """env 显式 -1 = 不限（关闭全局兜底，节点声明值语义不变）"""
    monkeypatch.setenv("AGENT_SUBTASK_TIMEOUT", "-1")
    monkeypatch.setenv("AGENT_SUBTASK_TOKEN_BUDGET", "-1")
    from dawei.config.settings import AgentExecutionConfig

    cfg = AgentExecutionConfig(_env_file="/nonexistent/.env")
    assert cfg.subtask_timeout == -1
    assert cfg.subtask_token_budget == -1


# ==================== C15: 指标计数与派生比率 ====================


def test_c15_metrics_counters_and_rates(metrics):
    metrics.record_granularity_rejected("R2")
    metrics.record_granularity_rejected("R2")
    metrics.record_granularity_rejected("R3")
    metrics.record_batch_dispatch(items=5, created=3, duplicate=1, error=1)
    metrics.record_subtask_terminal("completed", batch_item=True)
    metrics.record_subtask_terminal("failed", batch_item=True)
    metrics.record_subtask_terminal("completed", batch_item=False)
    metrics.record_llm_retry_scheduled()
    metrics.record_llm_retry_scheduled()
    metrics.record_llm_retry_success()

    s = metrics.get_summary()
    assert s["granularity_rejected_total"] == 3
    assert s["granularity_by_rule"] == {"R2": 2, "R3": 1}
    assert s["batch_dispatch_total"] == 1
    assert s["batch_items_total"] == 5
    assert s["batch_items_created"] == 3
    assert s["batch_items_duplicate"] == 1
    assert s["batch_items_error"] == 1
    assert s["batch_item_creation_rate"] == 0.6
    assert s["subtask_terminal_total"] == 3
    assert s["subtask_terminal_by_status"] == {"completed": 2, "failed": 1}
    assert s["batch_item_terminal_total"] == 2
    assert s["batch_item_failed_total"] == 1
    assert s["batch_item_failure_rate"] == 0.5
    assert s["llm_retry_scheduled_total"] == 2
    assert s["llm_retry_success_total"] == 1
    assert s["llm_retry_success_rate"] == 0.5

    metrics.reset()
    s2 = metrics.get_summary()
    assert s2["granularity_rejected_total"] == 0
    assert s2["batch_dispatch_total"] == 0
    assert s2["llm_retry_scheduled_total"] == 0


async def test_c15_terminal_metric_choke_point(graph_engine, metrics):
    """子任务终态转换 → 终态指标；根任务不计；重复终态写回不重复计数"""
    from dawei.agentic.task_graph_excutor import TaskGraphExecutionEngine

    graph_engine._update_task_status = TaskGraphExecutionEngine._update_task_status.__get__(graph_engine)

    sub_node = _FakeNode("sub-1", parent_id="root")
    sub_node.data.metadata = {"batch_id": "b1"}
    root_node = _FakeNode("root", parent_id=None)
    graph_engine._user_workspace = SimpleNamespace(
        task_graph=SimpleNamespace(
            update_task_status=AsyncMock(),
            get_task=AsyncMock(return_value=sub_node),
        ),
    )

    await graph_engine._update_task_status("sub-1", TaskStatus.RUNNING)  # 非终态不计数
    assert metrics.subtask_terminal_total == 0

    await graph_engine._update_task_status("sub-1", TaskStatus.FAILED)  # 批量条目失败
    assert metrics.subtask_terminal_total == 1
    assert metrics.subtask_terminal_by_status == {"failed": 1}
    assert metrics.batch_item_terminal_total == 1
    assert metrics.batch_item_failed_total == 1

    await graph_engine._update_task_status("sub-1", TaskStatus.FAILED)  # 重复写回不重复计数
    assert metrics.subtask_terminal_total == 1

    graph_engine._user_workspace.task_graph.get_task = AsyncMock(return_value=root_node)
    await graph_engine._update_task_status("root", TaskStatus.COMPLETED)  # 根任务不计
    assert metrics.subtask_terminal_total == 1


async def test_c15_batch_tool_records_granularity_and_dispatch(monkeypatch, metrics):
    """new_task_batch 逐项粒度熔断 → granularity 指标 + dispatch 派发分布指标"""
    from dawei.agentic.errors import SubtaskGranularityError
    from dawei.tools.custom_tools import workflow_tools_fixed as wtf

    async def _gran(_self, *_a, **_k):
        raise SubtaskGranularityError("R2", "6 files in one message", "split into N subtasks")

    monkeypatch.setattr(wtf.NewTaskTool, "_create_subtask", _gran)
    monkeypatch.setattr(
        wtf.NewTaskTool,
        "_load_available_modes",
        lambda _self: {"pdca": "PDCA 模式"},
    )
    monkeypatch.setattr(
        "dawei.mode.registry.get_registry",
        lambda _workspace_root=None: SimpleNamespace(can_delegate_to=lambda slug: slug != "orchestrator"),
    )

    class _Graph:
        async def get_root_task(self):
            return _FakeNode("root", parent_id=None)

        async def get_all_tasks(self):
            return []

        async def create_subtask(self, parent_id, data):
            return data

    tool = wtf.NewTaskBatchTool(task_graph=_Graph(), workspace_root=None)
    items = [wtf.BatchItem(identity=f"file-{i}", path=f"交付/{i}.docx") for i in range(2)]
    out = json.loads(
        await tool._run(
            mode="pdca",
            template="审查文件 {item.path}，出具审查意见",
            acceptance_template="{item.identity} 的审查报告包含 7 个章节",
            deliverable_template="交付/审查报告/{item.identity}.md",
            items=items,
        ),
    )

    assert out["status"] == "error"
    assert out["created_count"] == 0
    assert all(r["status"] == "error" and r.get("error") == "granularity_contract" for r in out["results"])

    assert metrics.granularity_rejected_total == 2
    assert metrics.granularity_by_rule == {"R2": 2}
    assert metrics.batch_dispatch_total == 1
    assert metrics.batch_items_total == 2
    assert metrics.batch_items_created == 0
    assert metrics.batch_items_error == 2
