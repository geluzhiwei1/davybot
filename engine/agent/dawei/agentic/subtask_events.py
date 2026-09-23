# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""子任务生命周期事件（P3-6 可观测性）

事件名 → TaskEventType 映射 + 统一 payload：
    subtask_id / parent_id / conversation_id / agent / depth / status

发布通道：Agent 的 event_bus（engine 持有；工具层经活动引擎注册表获取）。
全部发射点 fire-and-forget：事件失败绝不影响主流程。

§6.2 UI 协议：bus 发布后同步 fire-and-forget 广播 SubtaskLifecycleMessage 到
workspace 的 WS 连接（websocket_server.websocket_manager.broadcast，按
workspace_id 过滤）。workspace_id 解析顺序：显式参数 > 活动引擎的
_user_workspace.workspace_id；解析不到或 ws_server 不可用（TUI 模式为 None）→ 跳过。

C25 subtask_progress（§3.8 todo 步级进度，纯 UI 态不进会话历史）：
- contextvar `current_subtask` 在 TaskNodeExecutionEngine.execute_task 为子任务
  节点设置（父会话隔离后，worker 线程里的 update_todo_list 工具靠它识别"我
  属于哪个子任务"）；_schedule_on_main_loop 跨线程不携带 context，故工具层
  需在 _run 内先捕获再显式传参。
- emit_subtask_progress 带模块级去重缓存：todo 快照未变化不重复发射。
"""

from contextvars import ContextVar

from dawei.core.events import TaskEventType
from dawei.logg.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# C25：当前子任务上下文（contextvar）
# ---------------------------------------------------------------------------

# TaskNodeExecutionEngine.execute_task 设置；worker 线程（to_thread 复制 context）
# 中的工具可读取。值为 {"subtask_id","parent_id","batch_id","item_identity"} 子集。
_current_subtask: ContextVar[dict | None] = ContextVar("dawei_current_subtask", default=None)


def set_current_subtask(info: dict | None):
    """设置当前子任务上下文（execute_task 内调用，返回 token 供恢复）

    info 为空（根任务/无父子关系）返回 None，调用方 finally 传 None 即清空。
    """
    if not info:
        return None
    return _current_subtask.set(info)


def reset_current_subtask(token=None) -> None:
    """恢复当前子任务上下文（execute_task finally 中调用）"""
    try:
        if token is not None:
            _current_subtask.reset(token)
        else:
            _current_subtask.set(None)
    except Exception:  # noqa: BLE001 — context 恢复失败不影响执行
        logger.exception("Failed to reset current_subtask contextvar: ")


def get_current_subtask() -> dict | None:
    """读取当前子任务上下文（工具 worker 线程内调用）"""
    return _current_subtask.get()


# C25 进度去重缓存：subtask_id → (total, completed, current)。
# todo 快照未变化不重复发射（诚实语义：只报已发生的状态变化）。
_last_progress: dict[str, tuple[int, int, str]] = {}


def reset_progress_cache(subtask_id: str | None = None) -> None:
    """清除进度去重缓存（测试用；subtask_id 为空清除全部）"""
    if subtask_id:
        _last_progress.pop(subtask_id, None)
    else:
        _last_progress.clear()


# 生命周期名 → 事件类型（未知名直接返回 None，调用方跳过）
_LIFECYCLE_EVENT_MAP = {
    "created": TaskEventType.SUBTASK_CREATED,
    "started": TaskEventType.SUBTASK_STARTED,
    "completed": TaskEventType.SUBTASK_COMPLETED,
    "failed": TaskEventType.SUBTASK_FAILED,
    "aborted": TaskEventType.SUBTASK_ABORTED,
    "steered": TaskEventType.SUBTASK_STEERED,
}


def _resolve_engine():
    """取活动执行引擎（延迟导入避免循环依赖；失败返回 None）"""
    try:
        from dawei.tools.custom_tools.workflow_tools_fixed import get_active_execution_engine

        return get_active_execution_engine()
    except Exception:  # noqa: BLE001
        return None


def _resolve_bus(event_bus):
    """显式 bus 优先；否则从活动执行引擎取"""
    if event_bus is not None:
        return event_bus
    engine = _resolve_engine()
    return getattr(engine, "_event_bus", None) if engine else None


def _resolve_workspace_id(workspace_id: str | None, engine=None) -> str | None:
    """显式 workspace_id 优先；否则从活动引擎的 _user_workspace 解析"""
    if workspace_id:
        return workspace_id
    engine = engine or _resolve_engine()
    ws = getattr(engine, "_user_workspace", None) if engine else None
    return getattr(ws, "workspace_id", None) if ws else None


async def _broadcast_to_workspace(data: dict, workspace_id: str | None, extra: dict | None = None) -> None:
    """fire-and-forget 广播 subtask_lifecycle 到 workspace WS 连接（异常吞掉）"""
    if not workspace_id:
        return
    try:
        from dawei.websocket.protocol import SubtaskLifecycleMessage
        from dawei.websocket.ws_server import websocket_server

        if websocket_server is None:
            return  # TUI 模式无 WS 服务
        msg = SubtaskLifecycleMessage(
            session_id="",
            task_id=data.get("parent_id") or "",
            subtask_id=data["subtask_id"],
            event=data["event"],
            status=data.get("status"),
            parent_id=data.get("parent_id"),
            conversation_id=data.get("conversation_id"),
            agent=data.get("agent"),
            depth=data.get("depth"),
            metadata=extra or None,
        )
        await websocket_server.websocket_manager.broadcast(msg, workspace_id=workspace_id)
    except Exception:  # noqa: BLE001 — 广播失败不影响主流程
        logger.exception(f"Failed to broadcast subtask_lifecycle for {data.get('subtask_id')}: ")


async def emit_subtask_lifecycle(
    event_name: str,
    *,
    task_node_id: str,
    parent_id: str | None = None,
    conversation_id: str | None = None,
    agent: str | None = None,
    depth: int | None = None,
    status: str | None = None,
    event_bus=None,
    workspace_id: str | None = None,
    extra: dict | None = None,
) -> None:
    """发射子任务生命周期事件（fire-and-forget，异常吞掉只记日志）

    Args:
        event_name: created/started/completed/failed/aborted/steered
        task_node_id: 子任务节点 ID
        parent_id / conversation_id / agent / depth / status: §6 UI 协议要求的 payload 字段
        event_bus: 显式事件总线（engine 调用方传入；工具层留空走活动引擎）
        workspace_id: 显式工作区 ID（缺省从活动引擎解析；解析不到则跳过 WS 广播）
        extra: 附加字段（如 {"reason": ...} / {"resumed": True}）
    """
    event_type = _LIFECYCLE_EVENT_MAP.get(event_name)
    if event_type is None:
        logger.warning(f"Unknown subtask lifecycle event: {event_name}")
        return
    engine = _resolve_engine() if event_bus is None else None
    bus = _resolve_bus(event_bus)
    if bus is None:
        return  # 无可用总线（引擎未激活）→ 静默跳过（广播也依赖引擎解析 workspace，一并跳过）

    data: dict = {"event": event_name, "subtask_id": task_node_id}
    if parent_id is not None:
        data["parent_id"] = parent_id
    if conversation_id is not None:
        data["conversation_id"] = conversation_id
    if agent is not None:
        data["agent"] = agent
    if depth is not None:
        data["depth"] = depth
    if status is not None:
        data["status"] = status
    if extra:
        data.update(extra)

    try:
        await bus.publish(event_type, data, task_id=task_node_id, source="subtask")
    except Exception:  # noqa: BLE001 — 事件失败不影响主流程
        logger.exception(f"Failed to emit subtask lifecycle event '{event_name}' for {task_node_id}: ")

    await _broadcast_to_workspace(data, _resolve_workspace_id(workspace_id, engine), extra)


# ---------------------------------------------------------------------------
# C25：todo 步级进度事件（§3.8，纯 UI 态）
# ---------------------------------------------------------------------------


def _summarize_todos(todos: list) -> tuple[int, int, str]:
    """从 todo 列表提炼 (total, completed, current) 摘要

    兼容 TodoItem 对象（.content/.status）与 dict（content/status 键）。
    current = 首个 in_progress 项（无则首个未完成项），截断 40 字。
    """
    total = len(todos)
    completed = 0
    current = ""
    for item in todos:
        if isinstance(item, dict):
            content = str(item.get("content", ""))
            status = item.get("status", "")
        else:
            content = str(getattr(item, "content", ""))
            status = getattr(item, "status", "")
        status_val = str(getattr(status, "value", status)).lower()
        if status_val == "completed":
            completed += 1
    for item in todos:
        if isinstance(item, dict):
            content = str(item.get("content", ""))
            status = item.get("status", "")
        else:
            content = str(getattr(item, "content", ""))
            status = getattr(item, "status", "")
        status_val = str(getattr(status, "value", status)).lower()
        if status_val == "in_progress":
            current = content[:40]
            break
        if status_val != "completed" and not current:
            current = content[:40]
    return total, completed, current


async def emit_subtask_progress(
    *,
    subtask_id: str,
    parent_id: str | None = None,
    batch_id: str | None = None,
    item_identity: str | None = None,
    todos: list | None = None,
    event_bus=None,
    workspace_id: str | None = None,
) -> None:
    """发射子任务 todo 步级进度事件（fire-and-forget；快照未变化跳过）

    诚实语义：只报已发生的状态变化（todos 快照），不预测"即将完成"。
    纯 UI 态：不写入任何会话历史。
    """
    if not subtask_id or not todos:
        return

    total, completed, current = _summarize_todos(todos)
    key = (total, completed, current)
    if _last_progress.get(subtask_id) == key:
        return  # 去重：todo 快照未变化不重复发射
    _last_progress[subtask_id] = key

    data: dict = {
        "subtask_id": subtask_id,
        "todos": {"total": total, "completed": completed, "current": current},
    }
    if parent_id:
        data["parent_id"] = parent_id
    if batch_id:
        data["batch_id"] = batch_id
    if item_identity:
        data["item_identity"] = item_identity

    engine = _resolve_engine() if event_bus is None else None
    bus = _resolve_bus(event_bus)
    try:
        if bus is not None:
            await bus.publish(TaskEventType.SUBTASK_PROGRESS, data, task_id=parent_id or subtask_id, source="subtask")
    except Exception:  # noqa: BLE001 — 事件失败不影响主流程
        logger.exception(f"Failed to emit subtask_progress for {subtask_id}: ")

    await _broadcast_progress_to_workspace(data, _resolve_workspace_id(workspace_id, engine))


async def _broadcast_progress_to_workspace(data: dict, workspace_id: str | None) -> None:
    """fire-and-forget 广播 subtask_progress 到 workspace WS 连接（异常吞掉）"""
    if not workspace_id:
        return
    try:
        from dawei.websocket.protocol import SubtaskProgressMessage
        from dawei.websocket.ws_server import websocket_server

        if websocket_server is None:
            return  # TUI 模式无 WS 服务
        msg = SubtaskProgressMessage(
            session_id="",
            task_id=data.get("parent_id") or "",
            subtask_id=data["subtask_id"],
            parent_id=data.get("parent_id"),
            batch_id=data.get("batch_id"),
            item_identity=data.get("item_identity"),
            todos=data["todos"],
        )
        await websocket_server.websocket_manager.broadcast(msg, workspace_id=workspace_id)
    except Exception:  # noqa: BLE001 — 广播失败不影响主流程
        logger.exception(f"Failed to broadcast subtask_progress for {data.get('subtask_id')}: ")
