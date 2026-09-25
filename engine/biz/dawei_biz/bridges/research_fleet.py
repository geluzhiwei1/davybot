# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""GeluResearch 编队状态广播（research_agent_status WS 事件源）。

镜像 social_fleet.py / market_fleet.py 同款纪律——真实可观测的状态
（诚实边界，不伪造）：
- tool：research 工具组工具被调用（tool_executor.execute_tool；active expert = 当前 mode）
- idle：chat handler 的 agent 任务结束（成功/失败均归位）
thinking/online 无 LLM 流级钩子，不伪造——前端 DEV 演示按钮可模拟全态。

per-workspace 记录活跃 expert（idle 时精准归位）；broadcast 按 workspace 过滤。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 与 normos-market-resources/resources/gelu-research-team agents/*/modes.yaml 的
# slug 严格对齐（编队成员模式，仅用于前端编队状态观测；前端 FLEET_ROSTER expertId
# 一致。注：mode-工具解耦后无组准入，本表不代表"只有这些模式能调 research 工具"）。
RESEARCH_TEAM_MODES = frozenset(
    {
        "paper-orchestrator",
        "peer-review",
        "quality-gate",
        "quality-assurance",
        "submission-expert",
        "data-steward-expert",
    }
)

# workspace_id -> 活跃 expert_id（进程内存；多 worker 进程各自局部，徽标取并集语义可接受）
_active_expert: dict[str, str] = {}


async def broadcast_research_status(
    workspace_id: str,
    expert_id: str,
    status: str,
    last_action: str | None = None,
    session_id: str = "",
) -> None:
    """广播一条 research_agent_status（失败仅告警，绝不影响主流程）。"""
    try:
        from dawei.websocket.protocol import ResearchAgentStatusMessage
        from dawei.websocket.ws_server import websocket_server

        if websocket_server is None:
            return
        msg = ResearchAgentStatusMessage(
            session_id=session_id,
            expert_id=expert_id,
            status=status,
            last_action=last_action,
            data={"expert_id": expert_id, "status": status, "last_action": last_action},
        )
        await websocket_server.websocket_manager.broadcast(msg, workspace_id=workspace_id)
        logger.debug("[RESEARCH_FLEET] %s %s %s (%s)", workspace_id[:8], expert_id, status, last_action or "")
    except Exception as e:  # noqa: BLE001 —— 可观测性失败不阻断工具/对话
        logger.warning("[RESEARCH_FLEET] broadcast failed: %s", e)


async def note_research_tool_call(workspace_id: str, current_mode: str | None, tool_name: str) -> None:
    """research 工具被调用 → 当前 mode 的子智能体进入 tool 态并记录活跃 expert。

    仅当 current_mode 属于 gelu-research-team 编队（RESEARCH_TEAM_MODES）时生效。
    """
    if not workspace_id or current_mode not in RESEARCH_TEAM_MODES:
        return
    _active_expert[workspace_id] = current_mode
    await broadcast_research_status(workspace_id, current_mode, "tool", last_action=tool_name)


async def mark_research_workspace_idle(workspace_id: str, session_id: str = "") -> None:
    """agent 任务结束 → 该工作区活跃的 research 子智能体归位 idle。"""
    if not workspace_id:
        return
    expert = _active_expert.pop(workspace_id, None)
    if expert:
        await broadcast_research_status(workspace_id, expert, "idle", session_id=session_id)


# ── 阶段六 6a（拆库方案 §18.3-S5）：向核心扩展钩子注册表自注册 ──────────────
# 核心主链（chat.py / tool_executor.py）不再 import 本模块 —— 只调
# dawei.core.ext_hooks 的分发函数；本模块被 import 即完成注册（缺席=无行为）。
# 触发链：dawei → websocket → websocket/__init__.py 底部 fleet import；
# 6b 起随 dawei_biz 经 entry points 触发，本注册块原样随迁。
from dawei.core.ext_hooks import (
    register_task_idle_observer,
    register_tool_call_observer,
)


async def _observe_research_tool_call(workspace_id: str, current_mode: str | None, tool_name: str) -> None:
    """自门控：仅 research_ 前缀工具 → 当前 gelu-research-team 子智能体进入 tool 态。"""
    if not tool_name.startswith("research_"):
        return
    await note_research_tool_call(workspace_id, current_mode, tool_name)


register_tool_call_observer("research", _observe_research_tool_call)
register_task_idle_observer("research", mark_research_workspace_idle)
