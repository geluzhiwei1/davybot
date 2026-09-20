"""agent_stop 幂等性回归测试（bug: 任务页连点「停止」无效果）。

生产事故时间线（.dev-logs/nn-bot-backend.log 2026-09-18）：
- 08:28:14 第 1 次停止：agent.stop() 返回 2ms 后 handler 立即 del _active_agents，
  但协作式停止并未真正结束根协程（stop 返回后仍有 8s 的 LLM 流式调用在跑）
- 08:29:32–08:32:36 第 2–7 次停止：全部落入 "No active agent found" 空转分支，
  只回 AgentStoppedMessage("任务已经结束或完成")，无法停止残留工作

修复契约：stop 路径不再提前注销 agent——注销统一由自然完成路径的 finally 块
负责（AsyncTaskManager 超时 600s 强制取消兜底），重复 agent_stop 幂等地
重新执行 agent.stop()，可终止停止后仍在收尾的残留工作。

用 ChatHandler.__new__ 绕过重型 __init__（AsyncTaskManager/沙箱等），只装配
_process_agent_stop 触达的最小状态。
"""

import pytest

from dawei.websocket.handlers.chat import ChatHandler
from dawei.websocket.protocol import AgentStopMessage

TASK_ID = "task-0b7ce686"
CONV_ID = "conv-2bebf2c2"
SESSION_ID = "sess-test"


class _StubAgent:
    """最小 Agent 桩：只实现 stop 路径触达的接口。"""

    def __init__(self, fail: bool = False):
        self.stop_calls = 0
        self._fail = fail

    async def stop(self) -> str:
        self.stop_calls += 1
        if self._fail:
            raise RuntimeError("stop boom")
        return "Agent已停止"


def _make_handler(monkeypatch) -> tuple[ChatHandler, list]:
    handler = ChatHandler.__new__(ChatHandler)
    handler._active_agents = {}
    handler._task_to_conv_id_map = {}
    handler._task_llm_api_state = {}
    sent: list = []

    async def _send_message(session_id, message, **kwargs):  # noqa: ARG001
        sent.append(message)

    async def _send_error_message(session_id, code, message, **kwargs):  # noqa: ARG001
        sent.append(message)

    async def _noop_cleanup(task_id, agent=None):  # noqa: ARG001
        pass

    monkeypatch.setattr(handler, "send_message", _send_message)
    monkeypatch.setattr(handler, "send_error_message", _send_error_message)
    monkeypatch.setattr(handler, "_cleanup_event_handlers", _noop_cleanup)
    return handler, sent


async def _stop(handler: ChatHandler, task_id: str = TASK_ID):
    msg = AgentStopMessage(session_id=SESSION_ID, task_id=task_id, conversation_id=CONV_ID)
    return await handler._process_agent_stop(SESSION_ID, msg)


def _summaries(sent: list) -> list[str]:
    return [getattr(m, "result_summary", "") or "" for m in sent]


@pytest.mark.unit
async def test_repeated_stop_reinvokes_agent_stop(monkeypatch):
    """连点停止：第 2 次点击仍应重新执行 agent.stop()，而不是空转 ack。"""
    handler, sent = _make_handler(monkeypatch)
    agent = _StubAgent()
    handler._active_agents[TASK_ID] = agent

    await _stop(handler)
    assert TASK_ID in handler._active_agents, "stop 后不得提前注销（自然完成 finally 负责）"

    await _stop(handler)
    assert agent.stop_calls == 2, "重复 stop 必须再次触发 agent.stop()（终止残留工作）"
    assert TASK_ID in handler._active_agents
    # 两次都应收到真实停止确认，而不是"任务已经结束或完成"空转 ack
    assert all("已经结束" not in s for s in _summaries(sent)), _summaries(sent)


@pytest.mark.unit
async def test_stop_failure_keeps_agent_for_retry(monkeypatch):
    """agent.stop() 抛异常也保留注册，允许用户重试停止。"""
    handler, _sent = _make_handler(monkeypatch)
    agent = _StubAgent(fail=True)
    handler._active_agents[TASK_ID] = agent

    await _stop(handler)  # 异常路径内部已捕获，不向上抛
    assert TASK_ID in handler._active_agents, "停止失败后必须保留注册供重试"
    assert agent.stop_calls == 1
