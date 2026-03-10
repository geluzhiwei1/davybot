# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agent 执行服务

提供统一的 Agent 执行接口，供 ChatHandler 和 SchedulerEngine 使用。
确保 UI 发起任务和定时任务使用完全一致的执行流程。
"""

import uuid
from datetime import datetime
from dawei.core.datetime_compat import UTC
from typing import List, Dict, Any

from dawei.agentic.agent import Agent
from dawei.conversation.conversation import Conversation
from dawei.core.exceptions import AgentInitializationError, ConfigurationError, LLMError, ValidationError
from dawei.entity.lm_messages import AssistantMessage, UserMessage
from dawei.logg.logging import get_logger
from dawei.workspace.user_workspace import UserWorkspace

logger = get_logger(__name__)


class AgentExecutionService:
    """Agent 执行服务

    核心原则:
    - UI 发起任务和定时任务使用完全相同的执行流程
    - 统一的 Agent 创建、配置、执行逻辑
    - 统一的 conversation 保存逻辑
    - 唯一区别是来源标识 (task_type: user vs scheduled)

    执行流程:
    1. 验证 workspace 和设置
    2. 创建 Agent 实例
    3. 配置 PDCA 模式
    4. 创建/更新 conversation
    5. 执行 agent.run()
    6. 保存对话历史
    """

    @staticmethod
    async def execute_agent_task(
        workspace: UserWorkspace,
        message: str,
        session_id: str,
        task_id: str,
        task_type: str = "user",
        source_task_id: str | None = None,
        repeat_count: int = 0,
        title: str | None = None,
        llm: str | None = None,
        mode: str | None = None,
        event_callback: Any | None = None,
    ) -> Dict[str, Any]:
        """执行 Agent 任务（统一入口）

        这是 UI 任务和定时任务共用的核心执行逻辑。
        确保两种任务使用完全相同的流程。

        Args:
            workspace: UserWorkspace 实例
            message: 用户消息内容
            session_id: 会话 ID
            task_id: 任务 ID
            task_type: 任务类型 ("user" | "scheduled")
            source_task_id: 源定时任务 ID (仅定时任务)
            repeat_count: 重复次数 (仅定时任务)
            title: 对话标题 (可选)
            llm: 覆盖默认 LLM 模型 (可选)
            mode: 覆盖默认 Agent 模式 (可选)
            event_callback: 事件回调函数 (UI 任务提供，定时任务为 None)

        Returns:
            执行结果字典

        Raises:
            ValidationError: 输入验证失败
            ConfigurationError: 配置错误
            LLMError: LLM 调用失败
            AgentInitializationError: Agent 初始化失败
        """
        logger.info(f"[AGENT_EXECUTION] Starting task: {task_id}\n  Type: {task_type}\n  Session: {session_id}\n  Message: {message[:100]}...")

        agent = None
        conversation = None

        try:
            # 1. 加载 workspace 设置
            settings = await workspace.get_settings()
            llm_model = llm or settings.get("llm_model", "deepseek/deepseek-chat")
            agent_mode = mode or settings.get("agent_mode", "orchestrator")

            logger.info(f"[AGENT_EXECUTION] Config: LLM={llm_model}, Mode={agent_mode} {'(override)' if llm or mode else '(workspace default)'}")

            # 2. 创建 Agent 实例（使用正确的 API）
            config = {
                "llm_model": llm_model,
                "agent_mode": agent_mode,
            }
            agent = await Agent.create_with_default_engine(workspace, config=config)

            # 3. 初始化 Agent
            await agent.initialize()

            # 4. 设置事件回调（如果有）
            # UI 任务会提供 WebSocket 事件推送回调
            # 定时任务没有回调（event_callback=None）
            if event_callback:
                agent.set_event_callback(event_callback)

            # 5. 创建或加载 conversation
            if task_type == "scheduled":
                # 定时任务：创建新 conversation
                conversation = Conversation(
                    id=session_id,
                    title=title or f"📅 {message[:50]} (第{repeat_count + 1}次)",
                    task_type="scheduled",
                    source_task_id=source_task_id,
                    agent_mode=agent_mode,
                    llm_model=llm_model,
                    messages=[],
                    metadata={
                        "scheduled_task_id": source_task_id,
                        "repeat_count": repeat_count,
                        "triggered_at": datetime.now(UTC).isoformat(),
                    },
                )
            else:
                # UI 任务：尝试加载现有 conversation 或创建新的
                conversation = await workspace.load_conversation(session_id)
                if not conversation:
                    conversation = Conversation(
                        id=session_id,
                        title=title or message[:50],
                        task_type="user",
                        agent_mode=agent_mode,
                        llm_model=llm_model,
                        messages=[],
                    )

            # 6. 创建用户消息
            user_message = UserMessage(
                id=str(uuid.uuid4()),
                content=message,
                timestamp=datetime.now(UTC),
            )

            conversation.messages.append(user_message)
            conversation.message_count = len(conversation.messages)

            # 保存用户消息到 conversation（使用 save_current_conversation）
            workspace.current_conversation = conversation
            await workspace.save_current_conversation()

            logger.info(f"[AGENT_EXECUTION] Conversation: {session_id}, Message count: {conversation.message_count}")

            # 7. 执行 Agent（核心逻辑）
            logger.info(f"[AGENT_EXECUTION] Running agent: {task_id}")

            result = await agent.run(
                user_message=user_message,
                session_id=session_id,
            )

            # 8. 添加助手回复到 conversation
            final_output = result.get("final_output", "")

            if final_output:
                assistant_message = AssistantMessage(
                    id=str(uuid.uuid4()),
                    content=final_output,
                    timestamp=datetime.now(UTC),
                )

                conversation.messages.append(assistant_message)
                conversation.message_count = len(conversation.messages)
                conversation.updated_at = datetime.now(UTC)

                # 保存完整的 conversation（使用 save_current_conversation）
                workspace.current_conversation = conversation
                await workspace.save_current_conversation()

            logger.info(f"[AGENT_EXECUTION] Task {task_id} completed successfully\n  Messages: {conversation.message_count}\n  Conversation: {session_id}")

            return {
                "success": True,
                "task_id": task_id,
                "session_id": session_id,
                "conversation_id": conversation.id,
                "result": result,
                "final_output": final_output,
                "message_count": conversation.message_count,
            }

        except LLMError as e:
            logger.error(f"[AGENT_EXECUTION] LLM error: {e}")
            raise
        except ConfigurationError as e:
            logger.error(f"[AGENT_EXECUTION] Configuration error: {e}")
            raise
        except AgentInitializationError as e:
            logger.error(f"[AGENT_EXECUTION] Agent initialization error: {e}")
            raise
        except ValidationError as e:
            logger.error(f"[AGENT_EXECUTION] Validation error: {e}")
            raise
        except Exception as e:
            logger.error(
                f"[AGENT_EXECUTION] Unexpected error: {e}",
                exc_info=True,
            )
            raise


# 全局单例
agent_execution_service = AgentExecutionService()


__all__ = [
    "AgentExecutionService",
    "agent_execution_service",
]
