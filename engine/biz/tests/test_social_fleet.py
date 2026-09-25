"""SocialAgent 编队状态广播 —— 测试即规格(镜像 test_market_fleet.py)。

S1 消息契约:SocialAgentStatusMessage 字段/类型/registry 注册
S2 note_social_tool_call:social-team mode → tool 态 + 记录活跃 expert;非 social mode 不广播
   (含创作工坊 social-tools 会话不受影响)
S3 mark_social_workspace_idle:活跃 expert 归位 idle;无活跃时 no-op
S4 编队对齐:SOCIAL_TEAM_MODES 与 modes.yaml slug / 前端 FLEET_ROSTER 一致
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dawei_biz.bridges import social_fleet as sf


@pytest.fixture(autouse=True)
def _clean_active():
    sf._active_expert.clear()
    yield
    sf._active_expert.clear()


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
class TestS1Contract:
    def test_message_fields_and_registry(self):
        from dawei.websocket.protocol import MessageType, SocialAgentStatusMessage

        msg = SocialAgentStatusMessage(session_id="s1", expert_id="soc-trending-scout", status="tool", last_action="social_lookup_trending")
        assert msg.type is MessageType.SOCIAL_AGENT_STATUS
        assert msg.to_dict()

    def test_enum_value(self):
        from dawei.websocket.protocol import MessageType

        assert MessageType.SOCIAL_AGENT_STATUS.value == "social_agent_status"

    def test_registry_registered(self):
        from dawei.websocket.protocol import MessageValidator, SocialAgentStatusMessage

        assert MessageValidator.get_message_class("social_agent_status") is SocialAgentStatusMessage


@pytest.mark.unit
class TestS2ToolCall:
    async def test_social_mode_lights_up(self, broadcasts):
        await sf.note_social_tool_call("ws-1", "soc-campaign-drafter", "social_rule_check")
        assert broadcasts == [
            {
                "workspace_id": "ws-1",
                "type": "social_agent_status",
                "expert_id": "soc-campaign-drafter",
                "status": "tool",
                "last_action": "social_rule_check",
                "data": {"expert_id": "soc-campaign-drafter", "status": "tool", "last_action": "social_rule_check"},
            }
        ]
        assert sf._active_expert["ws-1"] == "soc-campaign-drafter"

    async def test_non_social_mode_silent(self, broadcasts):
        # 创作工坊 social-tools 会话(soc-content-drafter 等)不点亮编队徽标
        await sf.note_social_tool_call("ws-1", "orchestrator", "social_rule_check")
        await sf.note_social_tool_call("ws-1", "soc-content-drafter", "social_read_draft")
        await sf.note_social_tool_call("ws-1", "mkt-orchestrator", "social_lookup_trending")
        assert broadcasts == []
        assert "ws-1" not in sf._active_expert

    async def test_empty_workspace_silent(self, broadcasts):
        await sf.note_social_tool_call("", "soc-trending-scout", "social_lookup_trending")
        assert broadcasts == []


@pytest.mark.unit
class TestS3Idle:
    async def test_idle_restores_active_expert(self, broadcasts):
        await sf.note_social_tool_call("ws-1", "soc-approvals-guardian", "social_rule_check")
        await sf.mark_social_workspace_idle("ws-1", session_id="s1")
        assert len(broadcasts) == 2
        assert broadcasts[1]["status"] == "idle"
        assert broadcasts[1]["expert_id"] == "soc-approvals-guardian"
        assert "ws-1" not in sf._active_expert  # 归位后清除

    async def test_idle_noop_without_active(self, broadcasts):
        await sf.mark_social_workspace_idle("ws-1")
        assert broadcasts == []


# 【S4 对齐锚点迁出 2026-09-16】social-team modes.yaml 的 SSOT 已移至
# normos-market-resources/resources/social-team/（§8 兜底目录移除），
# roster ↔ yaml 对齐校验随迁 market 仓（nn-user-system discovery 扫描端
# 8c32eb4 提供 slug 全局唯一/命名校验）；本文件 fleet 行为测试仍以
# sf.SOCIAL_TEAM_MODES 常量为锚。
