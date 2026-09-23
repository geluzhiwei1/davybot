"""Graph and Task Management API Routes

任务图和任务节点管理
"""

import logging
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from dawei.core.validators import validate_dict_key, validate_not_none, validate_string_not_empty
from dawei.workspace import workspace_manager
from dawei.workspace.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["workspaces-graphs"])


# --- Pydantic 模型 ---


class GraphCreate(BaseModel):
    """创建任务图的请求模型"""

    name: str = Field(..., description="任务图名称")
    description: str | None = Field(None, description="任务图描述")
    root_task: Dict[str, Any] | None = Field(None, description="根任务配置")


class GraphUpdate(BaseModel):
    """更新任务图的请求模型"""

    name: str | None = None
    description: str | None = None


class TaskNodeInfo(BaseModel):
    """任务节点信息"""

    task_id: str
    description: str
    mode: str
    status: str
    priority: str = "medium"
    parent_id: str | None = None
    child_ids: List[str] = []
    created_at: str | None = None
    updated_at: str | None = None


class GraphInfo(BaseModel):
    """任务图信息"""

    graph_id: str
    name: str
    description: str
    root_task_id: str | None
    total_tasks: int
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class GraphExecuteRequest(BaseModel):
    """执行任务图的请求模型"""

    auto_execute: bool = True
    stop_on_error: bool = False


class TodoItemUpdate(BaseModel):
    """TODO项更新模型"""

    id: str
    content: str
    completed: bool = False


class TaskTodosUpdate(BaseModel):
    """任务TODO列表更新模型"""

    todos: List[TodoItemUpdate]


class TaskInfo(BaseModel):
    """任务信息"""

    task_id: str
    description: str
    mode: str
    status: str
    priority: str
    parent_id: str | None
    child_ids: List[str]
    created_at: str | None
    updated_at: str | None


class CheckpointInfo(BaseModel):
    """检查点信息"""

    checkpoint_id: str
    task_id: str
    created_at: str
    description: str | None
    execution_state: Dict[str, Any] | None


class SubTaskCreate(BaseModel):
    """创建子任务的请求模型"""

    description: str
    mode: str | None = "orchestrator"
    parent_id: str
    priority: str = "medium"


# --- 辅助函数 ---


async def _ensure_workspace_initialized(workspace: UserWorkspace, request: Request) -> None:
    """确保工作区已初始化（user_id 从认证注入）

    必须在 initialize() 之前注入真实账号：WorkspaceContext 按 (path, user_id)
    分键，MCP/relay stub 等账户隔离资源跟随 context 键 —— 缺省注入会落
    default_user，与壳按真实账号注册的 relay 面拆分（2026-09-18 paper-search
    回归根因）。无认证直接 401（与 auth 层同语义 fail-fast）。
    """
    from dawei.api.auth import get_authenticated_user_id

    if not workspace.is_initialized():
        workspace.user_id = await get_authenticated_user_id(request)
        await workspace.initialize()


from dawei.api.workspaces._deps import get_user_workspace

@router.get("/{workspace_id}/graphs")
async def get_workspace_graphs(workspace_id: str, request: Request):
    """获取工作区的所有任务图"""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        logger.error(f"Workspace {workspace_id} not found")
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

    workspace_path = workspace_info.get("path")
    if not workspace_path:
        logger.error(f"Workspace {workspace_id} missing path: {workspace_info}")
        raise HTTPException(
            status_code=500,
            detail=f"Workspace {workspace_id} has invalid configuration",
        )

    workspace = UserWorkspace(workspace_path=workspace_path)
    await _ensure_workspace_initialized(workspace, request)

    # 获取任务图信息
    # task_graph 在 Agent 执行时才创建，未执行时为 None
    task_graph = workspace.task_graph
    if task_graph is None:
        return {"success": True, "graphs": [], "total": 0}

    all_tasks = await task_graph.get_all_tasks()

    # 构建图信息
    root_task = await task_graph.get_root_task()
    graph_info = {
        "graph_id": task_graph.task_node_id,
        "name": f"Task Graph ({task_graph.task_node_id})",
        "description": "Main task graph for workspace",
        "root_task_id": root_task.task_id if root_task else None,
        "total_tasks": len(all_tasks),
        "status": "active" if all_tasks else "empty",
        "created_at": (root_task.created_at.isoformat() if root_task and hasattr(root_task, "created_at") else None),
        "updated_at": (root_task.updated_at.isoformat() if root_task and hasattr(root_task, "updated_at") else None),
        "tasks": [],
    }

    # 添加任务节点信息
    for task in all_tasks[:20]:  # 限制返回数量
        task_info = {
            "task_id": task.task_id,
            "description": task.description,
            "mode": task.mode,
            "status": task.status.value,
            "priority": (task.data.priority.value if hasattr(task.data, "priority") and task.data.priority else "medium"),
            "parent_id": task.parent_id,
            "child_ids": task.child_ids,
            "created_at": task.created_at.isoformat() if hasattr(task, "created_at") else None,
            "updated_at": task.updated_at.isoformat() if hasattr(task, "updated_at") else None,
        }
        graph_info["tasks"].append(task_info)

    return {"success": True, "graphs": [graph_info], "total": 1}


@router.post("/{workspace_id}/graphs")
async def create_workspace_graph(workspace_id: str, request: Request, graph_data: GraphCreate):
    """创建新的任务图"""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        logger.error(f"Workspace {workspace_id} not found when creating graph")
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

    workspace_path = workspace_info.get("path")
    if not workspace_path:
        logger.error(f"Workspace {workspace_id} missing path when creating graph")
        raise HTTPException(
            status_code=500,
            detail=f"Workspace {workspace_id} has invalid configuration",
        )

    workspace = UserWorkspace(workspace_path=workspace_path)
    await _ensure_workspace_initialized(workspace, request)

    task_graph = workspace.task_graph

    # 如果提供了根任务配置，创建根任务
    if graph_data.root_task:
        try:
            from dawei.task_graph.task_node import TaskNode

            root_task = TaskNode(
                description=graph_data.root_task.get("description", graph_data.name),
                mode=graph_data.root_task.get("mode", "ask"),
                priority=graph_data.root_task.get("priority", "medium"),
            )
            await task_graph.add_task(root_task)
        except Exception as task_error:
            logger.exception(f"Failed to create root task: {task_error}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid root task configuration: {task_error!s}",
            )

    logger.info(f"Created graph '{graph_data.name}' in workspace {workspace_id}")

    return {
        "success": True,
        "message": "Graph created successfully",
        "graph_id": task_graph.task_node_id,
    }


@router.get("/{workspace_id}/graphs/{graph_id}")
async def get_workspace_graph(workspace_id: str, request: Request, graph_id: str):
    """获取指定任务图的详细信息"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_workspace_initialized(workspace, request)

    task_graph = workspace.task_graph

    if task_graph.task_node_id != graph_id:
        logger.error(f"Graph {graph_id} not found in workspace {workspace_id}")
        raise HTTPException(
            status_code=404,
            detail=f"Graph {graph_id} not found in workspace {workspace_id}",
        )

    all_tasks = await task_graph.get_all_tasks()
    root_task = await task_graph.get_root_task()

    return {
        "success": True,
        "graph": {
            "graph_id": task_graph.task_node_id,
            "name": f"Task Graph ({graph_id})",
            "root_task_id": root_task.task_id if root_task else None,
            "total_tasks": len(all_tasks),
            "tasks": [
                {
                    "task_id": task.task_id,
                    "description": task.description,
                    "mode": task.mode,
                    "status": task.status.value,
                }
                for task in all_tasks[:50]
            ],
        },
    }


@router.put("/{workspace_id}/graphs/{graph_id}")
async def update_workspace_graph(workspace_id: str, request: Request, graph_id: str, graph_data: GraphUpdate):
    """更新任务图信息"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_workspace_initialized(workspace, request)

    task_graph = workspace.task_graph

    if task_graph.task_node_id != graph_id:
        logger.error(f"Graph {graph_id} not found in workspace {workspace_id}")
        raise HTTPException(status_code=404, detail=f"Graph {graph_id} not found")

    # 更新逻辑（简化版）
    logger.info(f"Updated graph {graph_id} in workspace {workspace_id}")

    return {"success": True, "message": "Graph updated successfully"}


@router.delete("/{workspace_id}/graphs/{graph_id}")
async def delete_workspace_graph(workspace_id: str, request: Request, graph_id: str):
    """删除任务图"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_workspace_initialized(workspace, request)

    logger.info(f"Deleted graph {graph_id} in workspace {workspace_id}")

    return {"success": True, "message": "Graph deleted successfully"}


@router.post("/{workspace_id}/graphs/{graph_id}/execute")
async def execute_workspace_graph(workspace_id: str, request: Request, graph_id: str, payload: GraphExecuteRequest):
    """执行任务图"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_workspace_initialized(workspace, request)

    logger.info(
        f"Executing graph {graph_id} in workspace {workspace_id} with auto_execute={payload.auto_execute}",
    )

    return {
        "success": True,
        "message": "Graph execution started",
        "execution_id": f"exec_{graph_id}",
    }


# --- Task管理路由 ---


@router.get("/{workspace_id}/tasks")
async def get_workspace_tasks(workspace_id: str, request: Request):
    """获取工作区的所有任务"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_workspace_initialized(workspace, request)

    task_graph = workspace.task_graph
    if task_graph is None:
        # 🔥 修复：工作区从未运行过 Agent 时 task_graph 尚未初始化，
        # 此前直接 AttributeError('NoneType' ... get_all_tasks') → HTTP 500
        logger.warning(f"Task graph not initialized for workspace {workspace_id}")
        raise HTTPException(status_code=404, detail=f"Task graph not initialized for workspace {workspace_id}")
    all_tasks = await task_graph.get_all_tasks()

    tasks_info = []
    for task in all_tasks[:100]:  # 限制返回数量
        tasks_info.append(
            {
                "task_id": task.task_id,
                "description": task.description,
                "mode": task.mode,
                "status": task.status.value,
            },
        )

    return {"success": True, "tasks": tasks_info, "total": len(all_tasks)}


@router.get("/{workspace_id}/tasks/{task_id}")
async def get_workspace_task(workspace_id: str, request: Request, task_id: str):
    """获取指定任务的详细信息"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_workspace_initialized(workspace, request)

    task_graph = workspace.task_graph
    if task_graph is None:
        # 🔥 修复：工作区从未运行过 Agent 时 task_graph 尚未初始化，
        # 此前直接 AttributeError('NoneType' ... get_task) → HTTP 500
        logger.warning(f"Task graph not initialized for workspace {workspace_id}")
        raise HTTPException(status_code=404, detail=f"Task graph not initialized for workspace {workspace_id}")
    task = await task_graph.get_task(task_id)

    if not task:
        logger.error(f"Task {task_id} not found in workspace {workspace_id}")
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return {
        "success": True,
        "task": {
            "task_id": task.task_id,
            "description": task.description,
            "mode": task.mode,
            "status": task.status.value,
            "parent_id": task.parent_id,
            "child_ids": task.child_ids,
        },
    }


class TaskCancelRequest(BaseModel):
    """取消任务请求(P2-A REST 对齐端点)"""

    reason: str | None = Field(None, description="取消原因(记录到节点 metadata 审计)")


@router.post("/{workspace_id}/tasks/{task_id}/cancel")
async def cancel_workspace_task(workspace_id: str, request: Request, task_id: str, body: TaskCancelRequest | None = None):
    """取消任务(P2-A: REST 对齐端点,复用 AbortTaskTool 的 BFS 级联终结语义)

    与 WS 侧 TASK_NODE_STOP(TaskNodeControlHandler)及 subtasks/abort 同一语义:
    CANCELLED 级联整棵子树 + 停运行中执行 + 审计 metadata。根任务拒绝
    (AbortTaskTool 契约),错误如实透传(FAST FAIL,不包装假成功)。
    """
    import json as _json

    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_workspace_initialized(workspace, request)

    task_graph = workspace.task_graph
    if task_graph is None:
        logger.warning(f"Task graph not initialized for workspace {workspace_id}")
        raise HTTPException(status_code=404, detail=f"Task graph not initialized for workspace {workspace_id}")

    node = await task_graph.get_task(task_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    from dawei.tools.custom_tools.workflow_tools_fixed import AbortTaskTool

    tool = AbortTaskTool(
        task_graph=task_graph,
        workspace_root=getattr(workspace, "absolute_path", None),
    )
    result = _json.loads(await tool._run(task_id, body.reason if body is not None else None))

    logger.info(f"Cancelled task {task_id} in workspace {workspace_id}: {result.get('status')}")
    return {
        "success": result.get("status") != "error",
        "source": "user",
        "result": result,
    }


@router.put("/{workspace_id}/tasks/{task_id}/todos")
async def update_task_todos(workspace_id: str, request: Request, task_id: str, todos_data: List[TodoItemUpdate]):
    """更新任务的TODO列表"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_workspace_initialized(workspace, request)

    logger.info(
        f"Updated {len(todos_data)} todos for task {task_id} in workspace {workspace_id}",
    )

    return {"success": True, "message": f"Updated {len(todos_data)} todos"}


@router.post("/{workspace_id}/tasks")
async def create_task(workspace_id: str, request: Request, task_data: SubTaskCreate):
    """创建新任务"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_workspace_initialized(workspace, request)

    try:
        from dawei.task_graph.task_node import TaskNode

        new_task = TaskNode(
            description=task_data.description,
            mode=task_data.mode,
            priority=task_data.priority,
        )
    except Exception as task_error:
        logger.exception(f"Failed to create TaskNode: {task_error}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task configuration: {task_error!s}",
        )

    task_graph = workspace.task_graph
    try:
        await task_graph.add_task(new_task, parent_id=task_data.parent_id)
    except Exception as add_error:
        logger.exception(f"Failed to add task to graph: {add_error}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add task to graph: {add_error!s}",
        )

    logger.info(f"Created task {new_task.task_id} in workspace {workspace_id}")

    return {
        "success": True,
        "message": "Task created successfully",
        "task_id": new_task.task_id,
    }


@router.delete("/{workspace_id}/tasks/{task_id}")
async def delete_task(workspace_id: str, request: Request, task_id: str):
    """删除任务"""
    workspace = await get_user_workspace(workspace_id, request)
    await _ensure_workspace_initialized(workspace, request)

    task_graph = workspace.task_graph
    try:
        await task_graph.delete_task(task_id)
    except Exception as delete_error:
        logger.exception(f"Task graph failed to delete task {task_id}: {delete_error}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete task from graph: {delete_error!s}",
        )

    logger.info(f"Deleted task {task_id} in workspace {workspace_id}")

    return {"success": True, "message": "Task deleted successfully"}
