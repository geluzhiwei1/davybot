# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""子任务委派 API（§6.2 UI 协议层，服务 davybot-app 工作区可视化）

端点：
- GET  /api/workspaces/{ws}/subtasks                            树 bootstrap（parent_id/depth/agent/conversation_id）
- GET  /api/workspaces/{ws}/subtasks/{id}/conversation          子代理线程抽屉：会话完整历史（降级感知）
- GET  /api/workspaces/{ws}/agents/profiles                     Agent Profile 列表（P3-0 注册表直读）
- POST /api/workspaces/{ws}/subtasks/{id}/steer                 运行中操控（复用 MessageTaskTool / P3-2）
- POST /api/workspaces/{ws}/subtasks/{id}/abort                 主动取消（复用 AbortTaskTool / P3-2 级联）
- POST /api/workspaces/{ws}/subtasks/{id}/rerun                 原位重跑（复用 reset_task_for_rerun / P2-D）

设计偏离说明：steer/abort 控件走 REST POST 而非设计文档 §6.2 原定的 WS 出站消息——
请求/响应语义明确、免 WS 关联 ID 管线；通知侧仍由 subtask_lifecycle WS 广播承担。
"""

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from dawei.api.workspaces._deps import get_user_workspace
from dawei.logg.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["workspaces-subtasks"])


async def _ensure_initialized(workspace) -> None:
    """确保工作区已初始化（幂等）"""
    if not workspace.is_initialized():
        await workspace.initialize()


def _status_value(status) -> str | None:
    return getattr(status, "value", status)


# ==================== 子任务列表（树 bootstrap）====================


@router.get("/{workspace_id}/subtasks")
async def list_subtasks(workspace_id: str, request: Request):
    """列出图中全部子任务（根任务排除），带 UI-A 树面板所需字段"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_initialized(workspace)

    task_graph = workspace.task_graph
    if task_graph is None:
        return {"success": True, "subtasks": [], "total": 0}

    all_tasks = await task_graph.get_all_tasks()
    items = []
    for t in all_tasks:
        if getattr(t, "parent_id", None) is None:
            continue  # 根任务不进树面板
        d = getattr(t, "data", None)
        meta = getattr(d, "metadata", None) or {}
        items.append(
            {
                "task_id": getattr(t, "task_id", None) or getattr(t, "task_node_id", None),
                "parent_id": t.parent_id,
                "status": _status_value(getattr(t, "status", None)),
                "mode": getattr(d, "mode", None),
                "agent": meta.get("agent"),
                "model": meta.get("model"),
                "depth": getattr(d, "depth", None),
                "conversation_id": getattr(d, "conversation_id", None),
                "description": str(getattr(d, "description", "") or "")[:200],
                "child_ids": list(getattr(t, "child_ids", []) or []),
            }
        )

    return {"success": True, "subtasks": items, "total": len(items)}


# ==================== 子任务交付质量指标（§8 验收埋点）====================


@router.get("/{workspace_id}/subtasks/metrics")
async def get_subtask_metrics(workspace_id: str, request: Request):
    """子任务交付质量指标（进程级汇总，非单工作区数据——挂在 subtasks 路由下便于运维定位）

    对应 docs/子任务组织管理交互方案.md §8：占位率 / 扫描兜底命中率 /
    同父同目标重派率 / 广度闸拒绝。镜像 result_governance /governance/metrics 模式。
    """
    from dawei.agentic.subtask_metrics import get_metrics

    return {"success": True, "metrics": get_metrics().get_summary()}


@router.post("/{workspace_id}/subtasks/metrics/reset")
async def reset_subtask_metrics(workspace_id: str, request: Request):
    """清零子任务质量指标（验收观察期起始点）"""
    from dawei.agentic.subtask_metrics import get_metrics

    get_metrics().reset()
    return {"success": True, "metrics": get_metrics().get_summary()}


# ==================== 子任务会话历史（线程抽屉）====================


@router.get("/{workspace_id}/subtasks/{task_node_id}/conversation")
async def get_subtask_conversation(workspace_id: str, request: Request, task_node_id: str):
    """拉取子任务独立会话完整历史（P2-7）；无隔离会话时返回降级说明而非报错"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_initialized(workspace)

    task_graph = workspace.task_graph
    node = await task_graph.get_task(task_node_id) if task_graph else None
    if node is None:
        raise HTTPException(status_code=404, detail=f"Task {task_node_id} not found in workspace {workspace_id}")

    data = getattr(node, "data", None)
    conversation_id = getattr(data, "conversation_id", None)
    if not conversation_id:
        # P2-7 flag off（共享父对话）或子任务尚未起跑（会话未分配）
        return {
            "success": True,
            "task_node_id": task_node_id,
            "conversation": None,
            "degraded": True,
            "reason": "shared_conversation",
            "message": "Subtask shares the parent conversation (isolation flag off or not yet started); no dedicated thread to show.",
        }

    mgr = getattr(workspace, "conversation_history_manager", None)
    conversation = await mgr.get_by_id(conversation_id) if mgr else None
    if conversation is None:
        return {
            "success": True,
            "task_node_id": task_node_id,
            "conversation_id": conversation_id,
            "conversation": None,
            "degraded": True,
            "reason": "conversation_not_found",
            "message": f"Conversation {conversation_id} not found in workspace history (expired or never flushed).",
        }

    return {
        "success": True,
        "task_node_id": task_node_id,
        "conversation_id": conversation_id,
        "degraded": False,
        "conversation": conversation.to_dict(),
    }


# ==================== Agent Profiles（P3-0 注册表直读）====================


@router.get("/{workspace_id}/agents/profiles")
async def list_agent_profiles(workspace_id: str, request: Request):
    """列出可用 Agent Profile（内置 + workspace/.dawei/agents/*）"""
    workspace = await get_user_workspace(workspace_id, request)

    from dawei.agentic.agent_profile import load_all_profiles

    root = getattr(workspace, "absolute_path", None) or getattr(workspace, "workspace_path", None)
    profiles = load_all_profiles(root)
    items = []
    for p in profiles.values():
        item = p.to_metadata()
        item["description"] = p.description
        item["builtin"] = p.builtin
        items.append(item)

    return {"success": True, "profiles": items, "total": len(items)}


# ==================== steer / abort（复用 P3-2 工具逻辑）====================


class SteerRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Steering message for the subtask")


class AbortRequest(BaseModel):
    reason: str | None = Field(None, description="Reason for aborting (audit metadata)")


@router.post("/{workspace_id}/subtasks/{task_node_id}/steer")
async def steer_subtask(workspace_id: str, request: Request, task_node_id: str, body: SteerRequest):
    """向子任务发送中途指令（RUNNING 注入会话 / PENDING 追加描述 / COMPLETED 续跑）"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_initialized(workspace)

    from dawei.tools.custom_tools.workflow_tools_fixed import MessageTaskTool

    tool = MessageTaskTool(task_graph=workspace.task_graph, workspace_root=getattr(workspace, "absolute_path", None))
    result = json.loads(await tool._run(task_node_id, body.message))
    return {"success": result.get("status") != "error", "source": "user", "result": result}


@router.post("/{workspace_id}/subtasks/{task_node_id}/abort")
async def abort_subtask(workspace_id: str, request: Request, task_node_id: str, body: AbortRequest | None = None):
    """主动取消子任务（BFS 级联置整棵子树 ABORTED，幂等）"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_initialized(workspace)

    from dawei.tools.custom_tools.workflow_tools_fixed import AbortTaskTool

    reason = body.reason if body is not None else None
    tool = AbortTaskTool(task_graph=workspace.task_graph, workspace_root=getattr(workspace, "absolute_path", None))
    result = json.loads(await tool._run(task_node_id, reason))
    return {"success": result.get("status") != "error", "source": "user", "result": result}


# ==================== rerun（P2 重跑：原位重置再执行）====================


class RerunRequest(BaseModel):
    reason: str | None = Field(None, description="重跑原因(写入 metadata.rerun_reason 审计)")
    message: str | None = Field(None, description="可选重跑指令(经 MessageTaskTool PENDING 路径注入,起跑时可见)")


@router.post("/{workspace_id}/subtasks/{task_node_id}/rerun")
async def rerun_subtask(workspace_id: str, request: Request, task_node_id: str, body: RerunRequest | None = None):
    """重跑子任务（P2-D：COMPLETED/FAILED/ABORTED → 原位重置 PENDING）

    复用 TaskGraph.reset_task_for_rerun：stash 旧 result/tokens/completed_at 到
    metadata.prev_*（审计可追溯）+ 清空（防先到先得残值吞掉第二次执行结果）+
    retry 清零 + 状态机转 PENDING。重置后由父任务编排循环驱动再执行。

    与 steer 端点（MessageTaskTool COMPLETED→续跑）互补：本端点覆盖 FAILED/
    ABORTED 的显式重跑，且不要求子任务会话存活。
    FAST FAIL：RUNNING → 409（先 abort）；CANCELLED → 409（用户取消先到先得，
    不隐式复活）；根任务 → 400（与 message_task 同契约）。
    """
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_initialized(workspace)

    task_graph = workspace.task_graph
    if task_graph is None:
        logger.warning(f"Task graph not initialized for workspace {workspace_id}")
        raise HTTPException(status_code=404, detail=f"Task graph not initialized for workspace {workspace_id}")

    node = await task_graph.get_task(task_node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Task {task_node_id} not found in workspace {workspace_id}")
    if getattr(node, "parent_id", None) is None:
        raise HTTPException(status_code=400, detail="Refusing to rerun the root task")

    reason = body.reason if body is not None else None
    message = body.message if body is not None else None
    if message and not reason:
        reason = f"user rerun: {message[:100]}"

    reset_ok = await task_graph.reset_task_for_rerun(task_node_id, reason)
    if not reset_ok:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Task {task_node_id} not rerunnable (status={_status_value(getattr(node, 'status', None))}); "
                "RUNNING → abort first; CANCELLED stays cancelled (first-come-first-served)"
            ),
        )

    # 可选重跑指令：节点已 PENDING → MessageTaskTool PENDING 路径追加到描述
    # （子任务起跑时可见，共享/隔离会话两种模式行为一致）
    steer_result = None
    if message:
        from dawei.tools.custom_tools.workflow_tools_fixed import MessageTaskTool

        tool = MessageTaskTool(task_graph=task_graph, workspace_root=getattr(workspace, "absolute_path", None))
        steer_result = json.loads(await tool._run(task_node_id, message))

    logger.info(f"Rerun reset task {task_node_id} in workspace {workspace_id} (reason={reason!r})")
    return {
        "success": True,
        "task_node_id": task_node_id,
        "status": "pending",
        "steer": steer_result,
    }
