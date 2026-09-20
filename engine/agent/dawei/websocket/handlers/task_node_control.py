# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务节点控制消息处理器
处理前端的任务节点停止（级联终结）请求

P1b ⑩：TASK_NODE_STOP 的真实级联终结逻辑自 ChatHandler 迁入并经
ws_server 注册接线。pause/resume 为历史占位代码已移除——协议层本就
没有 TaskNodePause/Resume 消息类，引擎亦无 pause/resume_task 实现；
待真实能力落地后再随消息类一并添加（FAST FAIL：不接线假成功回执）。
"""

from typing import Any

from dawei.entity.task_types import TaskStatus as GraphTaskStatus
from dawei.logg.logging import get_logger
from dawei.websocket.protocol import (
    MessageType,
    TaskNodeStopMessage,
    TaskNodeStoppedMessage,
)

from .base import AsyncMessageHandler

logger = get_logger(__name__)


class TaskNodeControlHandler(AsyncMessageHandler):
    """任务节点控制处理器

    处理前端发送的 TASK_NODE_STOP（用户终结任务节点）请求：
    BFS 级联终结整棵子树（CANCELLED 语义）并回执 TaskNodeStoppedMessage。
    """

    def __init__(self, task_graph_executor=None):
        """初始化处理器

        Args:
            task_graph_executor: TaskGraphExecutionEngine实例（可选，保留兼容；
                实际取消执行经各 agent 工作区的 execution_engine 解析）

        """
        super().__init__(max_concurrent_tasks=10)
        self.task_graph_executor = task_graph_executor
        logger.info("TaskNodeControlHandler initialized")

    def get_supported_types(self) -> list:
        """获取支持的消息类型（仅 TASK_NODE_STOP）"""
        return [
            MessageType.TASK_NODE_STOP,
        ]

    async def on_initialize(self):
        """初始化时的回调"""
        await super().on_initialize()
        logger.info("任务节点控制处理器已初始化")

    async def process_message(
        self,
        session_id: str,
        message,
        _message_id: str,
    ) -> dict[str, Any] | None:
        """处理任务节点控制消息

        Args:
            session_id: 会话ID
            message: WebSocket消息（TaskNodeStopMessage）
            message_id: 消息ID

        Returns:
            控制结果（可选）

        """
        try:
            if message.type == MessageType.TASK_NODE_STOP:
                return await self._handle_stop(session_id, message)

            logger.warning(f"不支持的消息类型: {message.type}")
            return None

        except (AttributeError, KeyError, ValueError, TypeError) as e:
            logger.error(f"处理任务节点控制消息失败: {e}", exc_info=True)
            # 返回错误消息
            return {
                "type": "error",
                "error": str(e),
                "task_node_id": getattr(message, "task_node_id", None),
            }

    async def _handle_stop(self, session_id: str, message: TaskNodeStopMessage) -> dict[str, Any]:
        """处理停止请求(P1b ⑩:真实级联终结逻辑自 ChatHandler._process_task_node_stop 迁入)

        幂等语义(镜像 AGENT_STOP 的"已结束不报错"处理):
        - 终态(COMPLETED/FAILED/ABORTED/CANCELLED)→ success 回执"已处于终态"
        - 非终态 → BFS 级联整棵子树:finalize_task(CANCELLED+原因,status/result 同笔)
          → engine.cancel_task_execution 停运行中执行(先落状态后停执行,
          终态锁定压制 CancelledError 路径的 ABORTED 改写,先到先得)
        - 节点不存在 → success 回执"任务不存在或已结束"

        方案: docs/子任务组织管理交互方案.md(F4/⑩) / docs/任务终结交互方案.md
        """
        if not isinstance(message, TaskNodeStopMessage):
            logger.error(f"Invalid message type for TASK_NODE_STOP: {type(message)}")
            await self.send_error_message(
                session_id,
                "INVALID_MESSAGE_TYPE",
                "Invalid message type for task node stop",
            )
            return {"type": "error", "error": "INVALID_MESSAGE_TYPE", "success": False}

        task_node_id = message.task_node_id
        reason = message.reason or "用户请求终结"
        logger.info(f"[{session_id}] TASK_NODE_STOP: task_node_id={task_node_id}, reason={reason}")

        stopped_reason = reason
        found = False
        _TERMINAL = (
            GraphTaskStatus.COMPLETED,
            GraphTaskStatus.FAILED,
            GraphTaskStatus.ABORTED,
            GraphTaskStatus.CANCELLED,
        )
        _ACTIVE = (
            GraphTaskStatus.RUNNING,
            GraphTaskStatus.WAITING_FOR_TOOL,
            GraphTaskStatus.INTERACTIVE,
        )
        # 遍历活跃 agent 定位包含该节点的图谱(task_node_id 为 uuid,跨工作区冲突概率≈0)
        for agent in list(self._active_agents_map().values()):
            ws = getattr(agent, "user_workspace", None)
            graph = getattr(ws, "task_graph", None)
            if graph is None:
                continue
            node = await graph.get_task(task_node_id)
            if node is None:
                continue
            found = True

            # 幂等:终态节点直接确认,不做任何变更
            if node.status in _TERMINAL:
                stopped_reason = f"任务已处于终态({node.status.value}),无需终结"
                break

            engine = getattr(ws, "execution_engine", None)

            # 级联:收集整棵非终态子树(BFS 防环,镜像 abort_task 的实现);
            # 运行中节点单独记录——finalize 后状态变为终态,不能再靠状态判定
            to_cancel: list = []
            active_ids: list = []
            visited: set = set()
            queue = [task_node_id]
            while queue:
                nid = queue.pop(0)
                if nid in visited:
                    continue
                visited.add(nid)
                n = await graph.get_task(nid)
                if n is None or n.status in _TERMINAL:
                    continue
                to_cancel.append(nid)
                if n.status in _ACTIVE:
                    active_ids.append(nid)
                queue.extend(getattr(n, "child_ids", []) or [])

            # P1a:先 finalize(CANCELLED+原因,status/result 同笔),再取消执行。
            # 顺序关键——终态锁定后 CancelledError 路径的 ABORTED 改写会被状态机拒绝,
            # 保证用户语义 CANCELLED 先到先得(不变量 6)
            for nid in to_cancel:
                per_node_reason = reason if nid == task_node_id else f"(随父节点终结: {reason})"
                # P2-B:终结原因审计 metadata(对齐 abort_task 的 aborted_* 键位)。
                # P2-B 补全:级联子树每个节点都写(此前仅目标节点);先于 finalize
                # 写——finalize 触发的 TASK_GRAPH_UPDATED 持久化会一并落盘审计键
                try:
                    from datetime import UTC, datetime

                    _n = await graph.get_task(nid)
                    _meta = getattr(getattr(_n, "data", None), "metadata", None) if _n is not None else None
                    if _meta is not None:
                        _meta["cancelled_by"] = (
                            "user(TASK_NODE_STOP)" if nid == task_node_id else "user(TASK_NODE_STOP,cascade)"
                        )
                        _meta["cancelled_reason"] = per_node_reason
                        _meta["cancelled_at"] = datetime.now(UTC).isoformat()
                except Exception:  # noqa: BLE001 — 审计写失败不阻断终结主流程
                    logger.exception(f"TASK_NODE_STOP: failed to write audit metadata for {nid}")
                try:
                    await graph.finalize_task(nid, GraphTaskStatus.CANCELLED, f"(用户终结: {per_node_reason})")
                except Exception as fin_err:  # noqa: BLE001 — 单节点失败不阻断其余
                    logger.warning(f"TASK_NODE_STOP: finalize failed for {nid}: {fin_err}")

            # 取消仍在运行的执行(状态已 CANCELLED,执行必须同步停止——⑥)
            for nid in active_ids:
                if engine is None:
                    logger.warning(f"TASK_NODE_STOP: no engine, running node {nid} cannot be cancelled")
                    continue
                try:
                    await engine.cancel_task_execution(nid)
                except Exception as cancel_err:  # noqa: BLE001
                    logger.warning(f"TASK_NODE_STOP: engine cancel failed for {nid}: {cancel_err}")

            stopped_reason = f"{reason}(级联 {len(to_cancel)} 个节点)"
            break

        if not found:
            # 幂等:节点不存在视为已结束(镜像 AGENT_STOP 语义)
            stopped_reason = "任务不存在或已结束"

        stopped_message = TaskNodeStoppedMessage(
            session_id=session_id,
            task_node_id=task_node_id,
            reason=stopped_reason,
        )
        await self.send_message(session_id, stopped_message)
        return {
            "type": "task_node_stopped",
            "task_node_id": task_node_id,
            "success": True,
            "reason": stopped_reason,
        }

    def _active_agents_map(self) -> dict[str, Any]:
        """活跃 Agent 注册表(经 ChatHandler 单例读取,ws_server.initialize 设置)。

        迁移自 ChatHandler._active_agents 的直接访问——独立 handler 不再
        持有该状态,与 ws_server 审批 publisher / manager.py 同一单例模式。
        """
        try:
            from dawei.websocket.handlers.chat import chat_handler_instance

            if chat_handler_instance is None:
                logger.warning("TASK_NODE_STOP: chat_handler_instance 未设置,无活跃 agent 可查")
                return {}
            return getattr(chat_handler_instance, "_active_agents", None) or {}
        except Exception:  # noqa: BLE001 — 单例解析失败不阻断 stop 回执
            logger.exception("TaskNodeControlHandler: 无法解析 chat_handler_instance")
            return {}

    def set_task_graph_executor(self, executor):
        """设置TaskGraphExecutor实例（保留兼容；实际取消走各工作区 execution_engine）"""
        self.task_graph_executor = executor
        logger.info("TaskGraphExecutor已设置")
