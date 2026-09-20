# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""SocialAgent 编队状态广播(social_agent_status WS 事件源)。

点亮前端 SocialAgentFleetBadge(monitoring-ws.ts 已路由 case)。设计:
镜像 market_fleet.py(MarketingAgent)同款纪律——真实可观测的状态
(诚实边界,不伪造):
- tool:social 工具组工具被调用(tool_executor.execute_tool;active expert = 当前 mode)
- idle:chat handler 的 agent 任务结束(成功/失败均归位)
thinking/online 无 LLM 流级钩子,不伪造——前端 DEV 演示按钮可模拟全态。

per-workspace 记录活跃 expert(idle 时精准归位);broadcast 按 workspace 过滤。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 与 mode/builtin/agents/social-team/modes.yaml 的 slug 严格对齐
# (前端 FLEET_ROSTER 见 social-agent-types.ts,expertId 一致;
#  2026-09-16 Phase 3 §4.8 重命名,旧 slug 作为 yaml aliases 兼容)
SOCIAL_TEAM_MODES = frozenset(
    {
        "soc-orchestrator",
        "soc-trending-scout",
        "soc-geo-scout",
        "soc-analytics-advisor",
        "soc-campaign-drafter",
        "soc-schedule-steward",
        "soc-approvals-guardian",
    }
)

# workspace_id -> 活跃 expert_id(进程内存;多 worker 进程各自局部,徽标取并集语义可接受)
_active_expert: dict[str, str] = {}


async def broadcast_social_status(
    workspace_id: str,
    expert_id: str,
    status: str,
    last_action: str | None = None,
    session_id: str = "",
) -> None:
    """广播一条 social_agent_status(失败仅告警,绝不影响主流程)。"""
    try:
        from dawei.websocket.protocol import SocialAgentStatusMessage
        from dawei.websocket.ws_server import websocket_server

        if websocket_server is None:
            return
        msg = SocialAgentStatusMessage(
            session_id=session_id,
            expert_id=expert_id,
            status=status,
            last_action=last_action,
            data={"expert_id": expert_id, "status": status, "last_action": last_action},
        )
        await websocket_server.websocket_manager.broadcast(msg, workspace_id=workspace_id)
        logger.debug("[SOCIAL_FLEET] %s %s %s (%s)", workspace_id[:8], expert_id, status, last_action or "")
    except Exception as e:  # noqa: BLE001 —— 可观测性失败不阻断工具/对话
        logger.warning("[SOCIAL_FLEET] broadcast failed: %s", e)


async def note_social_tool_call(workspace_id: str, current_mode: str | None, tool_name: str) -> None:
    """social 工具被调用 → 当前 mode 的子智能体进入 tool 态并记录活跃 expert。

    仅当 current_mode 属于 social-team 时生效(market/firm 及创作工坊
    social-tools 会话不受影响)。
    """
    if not workspace_id or current_mode not in SOCIAL_TEAM_MODES:
        return
    _active_expert[workspace_id] = current_mode
    await broadcast_social_status(workspace_id, current_mode, "tool", last_action=tool_name)


async def mark_social_workspace_idle(workspace_id: str, session_id: str = "") -> None:
    """agent 任务结束 → 该工作区活跃的 social 子智能体归位 idle。"""
    if not workspace_id:
        return
    expert = _active_expert.pop(workspace_id, None)
    if expert:
        await broadcast_social_status(workspace_id, expert, "idle", session_id=session_id)
