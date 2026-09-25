# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""MarketingAgent 编队状态广播(market_agent_status WS 事件源)。

点亮前端 MarketAgentFleetBadge(monitoring-ws.ts 已路由 case)。设计:
project/MarkkeAgent-prd.md §11.2(对齐 FirmAgent §13.6 调研的 firm_agent_status 契约)。

真实可观测的状态(诚实边界,不伪造):
- tool:market 工具组工具被调用(tool_executor.execute_tool;active expert = 当前 mode)
- idle:chat handler 的 agent 任务结束(成功/失败均归位)
thinking/online 无 LLM 流级钩子,不伪造——前端 DEV 演示按钮可模拟全态。

per-workspace 记录活跃 expert(idle 时精准归位);broadcast 按 workspace 过滤。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 与 mode/builtin/agents/market-team/modes.yaml 的 slug 严格对齐
# (2026-09-16 Phase 3 §4.8 重命名;旧 slug 作为 yaml aliases 兼容)
MARKET_TEAM_MODES = frozenset(
    {
        "mkt-orchestrator",
        "mkt-radar-scout",
        "mkt-visibility-scout",
        "mkt-competitor-analyst",
        "mkt-trend-analyst",
        "mkt-opportunity-advisor",
        "mkt-action-commander",
        "mkt-report-scribe",
    }
)

# workspace_id -> 活跃 expert_id(进程内存;多 worker 进程各自局部,徽标取并集语义可接受)
_active_expert: dict[str, str] = {}


async def broadcast_market_status(
    workspace_id: str,
    expert_id: str,
    status: str,
    last_action: str | None = None,
    session_id: str = "",
) -> None:
    """广播一条 market_agent_status(失败仅告警,绝不影响主流程)。"""
    try:
        from dawei.websocket.protocol import MarketAgentStatusMessage
        from dawei.websocket.ws_server import websocket_server

        if websocket_server is None:
            return
        msg = MarketAgentStatusMessage(
            session_id=session_id,
            expert_id=expert_id,
            status=status,
            last_action=last_action,
            data={"expert_id": expert_id, "status": status, "last_action": last_action},
        )
        await websocket_server.websocket_manager.broadcast(msg, workspace_id=workspace_id)
        logger.debug("[MARKET_FLEET] %s %s %s (%s)", workspace_id[:8], expert_id, status, last_action or "")
    except Exception as e:  # noqa: BLE001 —— 可观测性失败不阻断工具/对话
        logger.warning("[MARKET_FLEET] broadcast failed: %s", e)


async def note_market_tool_call(workspace_id: str, current_mode: str | None, tool_name: str) -> None:
    """market 工具被调用 → 当前 mode 的子智能体进入 tool 态并记录活跃 expert。

    仅当 current_mode 属于 market-team 时生效(firm/social 会话不受影响)。
    """
    if not workspace_id or current_mode not in MARKET_TEAM_MODES:
        return
    _active_expert[workspace_id] = current_mode
    await broadcast_market_status(workspace_id, current_mode, "tool", last_action=tool_name)


async def mark_workspace_idle(workspace_id: str, session_id: str = "") -> None:
    """agent 任务结束 → 该工作区活跃的 market 子智能体归位 idle。"""
    if not workspace_id:
        return
    expert = _active_expert.pop(workspace_id, None)
    if expert:
        await broadcast_market_status(workspace_id, expert, "idle", session_id=session_id)


# ── 阶段六 6a（拆库方案 §18.3-S5）：向核心扩展钩子注册表自注册 ──────────────
# 核心主链（chat.py / tool_executor.py）不再 import 本模块 —— 只调
# dawei.core.ext_hooks 的分发函数；本模块被 import 即完成注册（缺席=无行为）。
# 触发链：dawei → websocket → websocket/__init__.py 底部 fleet import；
# 6b 起随 dawei_biz 经 entry points 触发，本注册块原样随迁。
from dawei.core.ext_hooks import (
    register_task_idle_observer,
    register_tool_call_observer,
)


async def _observe_market_tool_call(workspace_id: str, current_mode: str | None, tool_name: str) -> None:
    """自门控：仅 market_ 前缀工具 → 当前 market-team 子智能体进入 tool 态。"""
    if not tool_name.startswith("market_"):
        return
    await note_market_tool_call(workspace_id, current_mode, tool_name)


register_tool_call_observer("market", _observe_market_tool_call)
register_task_idle_observer("market", mark_workspace_idle)
