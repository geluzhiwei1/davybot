"""MarketingAgent 编队状态广播 —— 测试即规格(设计:project/MarkkeAgent-prd.md §11.2)。

F1 消息契约:MarketAgentStatusMessage 字段/类型/registry 注册
F2 note_market_tool_call:market-team mode → tool 态 + 记录活跃 expert;非 market mode 不广播
F3 mark_workspace_idle:活跃 expert 归位 idle;无活跃时 no-op
F4 tool_executor 钩子:execute_tool 入口对 market_* 工具触发广播(mock websocket_server)
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dawei_biz.bridges import market_fleet as mf


@pytest.fixture(autouse=True)
def _clean_active():
    mf._active_expert.clear()
    yield
    mf._active_expert.clear()


@pytest.fixture
def broadcasts(monkeypatch):
    """捕获 broadcast 调用(不发 WS)。"""
    sent: list[dict] = []

    async def fake_broadcast(msg, workspace_id=None, exclude_sessions=None):
        sent.append(
            {
                "workspace_id": workspace_id,
                "type": msg.type.value if hasattr(msg.type, "value") else str(msg.type),
                "expert_id": msg.expert_id,
                "status": msg.status,
                "last_action": msg.last_action,
                # 前端契约(monitoring-ws.ts 读 msg.data)——双写必须一致
                "data": dict(msg.data or {}),
            }
        )

    server = SimpleNamespace(websocket_manager=SimpleNamespace(broadcast=fake_broadcast))
    monkeypatch.setattr("dawei.websocket.ws_server.websocket_server", server)
    return sent


@pytest.mark.unit
class TestF1Contract:
    def test_message_fields_and_registry(self):
        from dawei.websocket.protocol import MarketAgentStatusMessage, MessageType

        msg = MarketAgentStatusMessage(session_id="s1", expert_id="mkt-radar-scout", status="tool", last_action="market_dashboard")
        assert msg.type is MessageType.MARKET_AGENT_STATUS
        assert msg.to_dict()

    def test_enum_value(self):
        from dawei.websocket.protocol import MessageType

        assert MessageType.MARKET_AGENT_STATUS.value == "market_agent_status"


@pytest.mark.unit
class TestF2ToolCall:
    async def test_market_mode_lights_up(self, broadcasts):
        await mf.note_market_tool_call("ws-1", "mkt-visibility-scout", "market_geo_checks")
        assert broadcasts == [
            {
                "workspace_id": "ws-1",
                "type": "market_agent_status",
                "expert_id": "mkt-visibility-scout",
                "status": "tool",
                "last_action": "market_geo_checks",
                "data": {"expert_id": "mkt-visibility-scout", "status": "tool", "last_action": "market_geo_checks"},
            }
        ]
        assert mf._active_expert["ws-1"] == "mkt-visibility-scout"

    async def test_non_market_mode_silent(self, broadcasts):
        await mf.note_market_tool_call("ws-1", "orchestrator", "market_dashboard")
        await mf.note_market_tool_call("ws-1", "case-agent", "market_list_events")
        assert broadcasts == []
        assert "ws-1" not in mf._active_expert

    async def test_empty_workspace_silent(self, broadcasts):
        await mf.note_market_tool_call("", "mkt-radar-scout", "market_dashboard")
        assert broadcasts == []


@pytest.mark.unit
class TestF3Idle:
    async def test_idle_restores_active_expert(self, broadcasts):
        await mf.note_market_tool_call("ws-1", "mkt-report-scribe", "market_calibration")
        await mf.mark_workspace_idle("ws-1", session_id="s1")
        assert len(broadcasts) == 2
        assert broadcasts[1]["status"] == "idle"
        assert broadcasts[1]["expert_id"] == "mkt-report-scribe"
        assert "ws-1" not in mf._active_expert  # 归位后清除

    async def test_idle_noop_without_active(self, broadcasts):
        await mf.mark_workspace_idle("ws-1")
        assert broadcasts == []
