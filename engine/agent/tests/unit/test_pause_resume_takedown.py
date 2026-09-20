# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""P3 pause/resume 下架回归守卫（docs/子任务组织管理交互方案.md §P3）

pause/resume 曾是三处互不连通的死代码：
- Agent.pause_task/resume_task 委托 execution_engine.pause/resume_task_execution
  —— 引擎从未实现这两个方法，AttributeError 被 @handle_errors 掩盖成静默失败；
- TaskNodeExecutionEngine 死 stub（pause_task_execution 只 log+False；
  resume_task_execution 签名不兼容且盲目重跑、违反 -> bool 契约）；
- interfaces.ITaskExecutor 抽象声明无任何实现类。
且 websocket 协议本无 TaskNodePause/Resume 消息，全仓零调用者。

本套件防止三处在「协议消息 + 引擎真实现」落地前被原样重新引入；
届时应删除/更新本守卫并补真实用例。
"""

import pytest

pytestmark = pytest.mark.unit


def test_agent_pause_resume_removed():
    from dawei.agentic.agent import Agent

    assert not hasattr(Agent, "pause_task"), (
        "Agent.pause_task 已下架：重新引入前须先落 TaskNodePause 协议消息 + 引擎真实现"
    )
    assert not hasattr(Agent, "resume_task"), (
        "Agent.resume_task 已下架：重新引入前须先落 TaskNodeResume 协议消息 + 引擎真实现"
    )


def test_node_executor_pause_resume_stubs_removed():
    from dawei.agentic.task_node_executor import TaskNodeExecutionEngine

    for name in ("pause_task", "pause_task_execution", "resume_task_execution"):
        assert not hasattr(TaskNodeExecutionEngine, name), (
            f"TaskNodeExecutionEngine.{name} 死代码已移除，不应在无协议支撑下回归"
        )


def test_interface_pause_resume_removed():
    from dawei.interfaces.task_executor import ITaskExecutor

    # dawei/interfaces 的 ITaskExecutor（async_task 子系统有独立接口，不在此列）
    assert not hasattr(ITaskExecutor, "pause_task")
    assert not hasattr(ITaskExecutor, "resume_task")


def test_websocket_protocol_has_no_pause_resume_messages():
    from dawei.websocket import protocol as ws_protocol

    names = [
        n
        for n in dir(ws_protocol)
        if ("PAUSE" in n.upper() or "RESUME" in n.upper()) and not n.startswith("_")
    ]
    assert names == [], (
        f"检测到 pause/resume 协议符号 {names}：若为有意新增，请同步实现引擎侧并更新本守卫"
    )
