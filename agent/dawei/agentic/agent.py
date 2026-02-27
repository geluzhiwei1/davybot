# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""重构后的 Agent 主类
通过 TaskGraphExecutionEngine 管理所有任务相关操作，简化 Agent 职责
"""

import asyncio
import uuid
from collections import deque
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

from dawei.core.error_handler import handle_errors
from dawei.core.errors import (
    ConfigurationError,
)
from dawei.core.metrics import increment_counter
from dawei.core.utils import validate_and_create_config
from dawei.entity.task_types import TaskStatus, TaskSummary, TokenUsage, ToolUsage
from dawei.entity.user_input_message import UserInputMessage
from dawei.llm_api.constants import SNAPSHOT
from dawei.llm_api.model_router import (
    ModelRouter,
    load_cost_config,
    load_model_router_config,
)
from dawei.logg.logging import get_logger, log_performance
from dawei.workspace.user_workspace import UserWorkspace

from .context_manager import ContextManager
from .cost_tracker import CostTracker
from .file_reference import FileReferenceParser, PathResolver
from .file_snapshot_manager import FileSnapshotManager
from .task_graph_excutor import TaskGraphExecutionEngine


def is_memory_enabled(user_workspace) -> bool:
    """检查内存系统是否启用（使用统一配置）

    Args:
        user_workspace: UserWorkspace instance

    Returns:
        True if memory system is enabled, False otherwise

    Raises:
        RuntimeError: If config is not loaded (Fast Fail)

    Examples:
        >>> ws = UserWorkspace("/path/to/workspace")
        >>> await ws.initialize()
        >>> is_memory_enabled(ws)
        True
    """
    config = user_workspace.get_config()  # Fast Fail if not loaded
    return config.memory.enabled


class Agent:
    """重构后的 Agent 主类

    专注于协调各组件，通过 TaskGraphExecutionEngine 管理所有任务操作
    """

    def __init__(
        self,
        user_workspace: UserWorkspace,
        execution_engine: TaskGraphExecutionEngine,
        config: Any | dict[str, Any] | None = None,
    ):
        """初始化 Agent
        Args:
            user_workspace: 用户工作区
            execution_engine: 任务执行引擎实例
            config: 配置实例或字典（可选）
        """
        # 基本属性
        self.user_workspace = user_workspace
        self.execution_engine = execution_engine

        # 日志记录器（必须在使用前初始化）
        self.logger = get_logger(__name__)

        from dawei.core.events import SimpleEventBus
        self.event_bus = SimpleEventBus()
        self.logger.info(
            f"[AGENT] Agent created own event_bus (id={id(self.event_bus)})"
        )

        # 【关键】设置execution_engine的agent引用，用于暂停检查
        if hasattr(execution_engine, "_agent"):
            execution_engine._agent = self

        # 配置处理 - 使用共享工具函数
        self.config = validate_and_create_config(config)

        # 【新增】多模型智能路由器（
        router_config = load_model_router_config(self.user_workspace.absolute_path)
        cost_config = load_cost_config()

        # 【修复】获取用户选择的 LLM，传递给 ModelRouter
        user_default_model = None
        if user_workspace.workspace_info.user_ui_context and user_workspace.workspace_info.user_ui_context.current_llm_id:
            user_default_model = user_workspace.workspace_info.user_ui_context.current_llm_id

        self.model_router = ModelRouter(
            router_config,
            cost_config,
            user_default_model=user_default_model,
        )

        # 【新增】上下文管理器（
        self.context_manager = ContextManager(max_tokens=200000)

        # 【新增】文件引用解析器（
        self.file_reference_parser = FileReferenceParser(self.user_workspace.absolute_path)
        self.path_resolver = PathResolver(self.user_workspace.absolute_path)

        # 【新增】成本追踪器（
        self.cost_tracker = CostTracker()

        # 【新增】文件快照管理器（
        self.file_snapshot_manager = FileSnapshotManager(
            workspace_path=str(self.user_workspace.absolute_path),
            max_snapshots_per_file=SNAPSHOT.MAX_SNAPSHOTS_PER_FILE,
            retention_days=SNAPSHOT.RETENTION_DAYS,
            enable_compression=True,
        )

        # 【新增】对话压缩器（长对话Token限制处理）
        self.conversation_compressor = None
        self._initialize_compression()

        # 【新增】Memory系统（可选）- 必须在conversation_memory_integration之前初始化
        self.memory_graph = None
        self.virtual_context = None
        self.memory_degraded = False  # Track memory system degradation state
        if is_memory_enabled(self.user_workspace):
            try:
                from dawei.memory.memory_graph import MemoryGraph
                from dawei.memory.virtual_context import VirtualContextManager

                workspace_path = str(self.user_workspace.absolute_path)
                memory_db = str(Path(workspace_path) / ".dawei" / "memory.db")

                # Initialize MemoryGraph
                self.memory_graph = MemoryGraph(memory_db, self.event_bus)

                # Initialize VirtualContextManager
                self.virtual_context = VirtualContextManager(
                    db_path=memory_db,
                    page_size=2000,
                    max_active_pages=5,
                )

                self.logger.info("Memory system initialized successfully")
            except Exception as e:
                # Fast Fail: Memory system is explicitly enabled but failed to initialize
                # This indicates a serious problem that should not be silently ignored
                self.logger.error(
                    f"Memory system is enabled but failed to initialize: {e}. System will continue without memory capabilities.",
                    exc_info=True,
                )
                self.memory_degraded = True
                self.memory_graph = None
                self.virtual_context = None

        # 【新增】对话-记忆集成器
        self.conversation_memory_integration = None
        if is_memory_enabled(self.user_workspace):
            from .conversation_memory_integration import ConversationMemoryIntegration

            self.conversation_memory_integration = ConversationMemoryIntegration(
                memory_graph=self.memory_graph,
                virtual_context=self.virtual_context,
                auto_extract=True,
                auto_store=True,
            )
            self.logger.info("Conversation-memory integration initialized")

        # 【新增】Plan Mode 工作流执行器
        self.plan_workflow = None
        if self.config.mode == "plan":
            try:
                from dawei.agentic.plan_workflow import PlanWorkflowExecutor

                self.plan_workflow = PlanWorkflowExecutor(
                    session_id=str(self.user_workspace.uuid),
                    workspace_root=str(self.user_workspace.absolute_path),
                )
                self.logger.info("Plan workflow initialized for plan mode")
            except ImportError as e:
                # Graceful degradation: Plan workflow is optional
                self.logger.warning(f"Failed to initialize plan workflow: {e}", exc_info=True)
                # Plan workflow is optional, continue without it

        # 统计信息
        self.tool_usage: dict[str, ToolUsage] = {}
        self.token_usage = TokenUsage()
        # 【内存优化】使用 deque 限制模型选择历史记录数量，防止无限增长
        self.selected_models: deque = deque(maxlen=1000)  # 保留最近1000条记录
        self._selected_models_max_age_seconds = 3600  # 1小时后清理历史记录

        # 【修复】记录用户选择的 LLM 模型（如果已设置）
        if user_default_model:
            self.logger.info(
                f"Agent initialized with user-selected default LLM: {user_default_model}",
            )

        # 初始化标志
        self._initialized = False

        # Agent控制状态
        self._stop_requested = False

    @classmethod
    async def create_with_default_engine(
        cls,
        user_workspace: UserWorkspace,
        config: Any | dict[str, Any] | None = None,
    ) -> "Agent":
        """使用默认执行引擎创建 Agent 实例

        Args:
            user_workspace: 用户工作区
            config: 配置实例或字典（可选）

        Returns:
            Agent 实例

        """
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"[AGENT_CREATE] Starting agent creation for workspace: {user_workspace.workspace_info.id}")

        # 配置处理 - 使用共享工具函数
        config_obj = validate_and_create_config(config)

        # 创建执行引擎，不使用依赖注入容器
        from dawei.llm_api.llm_provider import LLMProvider
        from dawei.prompts import EnhancedSystemBuilder
        from dawei.tools.tool_executor import ToolExecutor
        from dawei.tools.tool_manager import ToolManager
        from dawei.workspace.tool_manager_wrapper import WorkspaceToolManager

        try:
            logger.info("[AGENT_CREATE] Creating base services...")
            # 创建基础服务
            message_processor = EnhancedSystemBuilder(user_workspace=user_workspace)

            if not user_workspace.llm_manager:
                raise RuntimeError("Workspace LLM manager not initialized")
            llm_service = user_workspace.llm_manager
            logger.info("[AGENT_CREATE] Using workspace's LLMProvider")

            # 【修复】使用 WorkspaceToolManager 而不是 ToolManager
            # WorkspaceToolManager 会初始化 Skills 工具
            workspace_tool_manager = WorkspaceToolManager(workspace_path=user_workspace.absolute_path)
            await workspace_tool_manager.initialize()

            # 创建 ToolManager 传递给 ToolExecutor (向后兼容)
            tool_manager = ToolManager(workspace_path=user_workspace.absolute_path)

            tool_call_service = ToolExecutor(
                tool_manager=tool_manager,
            )

            # 【新增】将 WorkspaceToolManager 的 skills 工具添加到 ToolExecutor
            if workspace_tool_manager._skills_tools:
                for skill_tool in workspace_tool_manager._skills_tools:
                    tool_call_service.tools[skill_tool.name] = skill_tool
                    logger.info(f"[AGENT_CREATE] Loaded skill tool: {skill_tool.name}")

            # Initialize task manager callbacks (must be done before setting user workspace)
            await tool_call_service.async_initialize()

            # 设置工具执行器的工作区
            await tool_call_service.set_user_workspace(user_workspace)

            logger.info("[AGENT_CREATE] Creating Agent instance (first, to get event_bus)...")
            # 🔧 修复：先创建 Agent 实例(获取 event_bus)
            agent = cls(user_workspace, None, config_obj)

            logger.info("[AGENT_CREATE] Creating TaskGraph for workspace...")
            # 🔧 修复：创建 TaskGraph 并使用 Agent 的 event_bus
            from dawei.task_graph.task_graph import TaskGraph
            task_id = user_workspace.workspace_info.id if user_workspace.workspace_info else "default-task"
            user_workspace.task_graph = TaskGraph(
                task_id=task_id,
                event_bus=agent.event_bus  # 使用 Agent 的 event_bus
            )

            logger.info("[AGENT_CREATE] Creating execution engine...")
            # 创建执行引擎,传入 agent
            execution_engine = TaskGraphExecutionEngine(
                user_workspace=user_workspace,
                message_processor=message_processor,
                llm_service=llm_service,
                tool_call_service=tool_call_service,
                config=config_obj,
                agent=agent,  # 🔧 修复：传入 agent
            )

            # 🔧 修复：设置 Agent 的 execution_engine
            agent.execution_engine = execution_engine

            # 【新增】设置 ToolExecutor 的 agent 引用（用于权限检查）
            tool_call_service._agent = agent

            # 设置 event_bus（用于发送工具事件）
            tool_call_service._event_bus = agent.event_bus

            logger.info("[AGENT_CREATE] Agent created successfully")
            return agent
        except Exception as e:
            logger.error(f"[AGENT_CREATE] Error during agent creation: {e}", exc_info=True)
            raise

    @handle_errors(component="agent", operation="initialize")
    @log_performance("agent.initialize")
    async def initialize(self) -> bool:
        """初始化 Agent

        Returns:
            是否成功初始化

        """
        # 验证配置 - 直接抛出异常而不是返回False
        config_errors = self.config.validate()
        if config_errors:
            raise ConfigurationError(f"Configuration validation failed: {config_errors}")

        # 初始化执行引擎（如果需要）
        if hasattr(self.execution_engine, "initialize"):
            await self.execution_engine.initialize()

        # 标记为已初始化
        self._initialized = True

        self.logger.info("Agent initialized", context={"component": "agent"})
        increment_counter("agent.initialization", tags={"status": "success"})
        return True

    @handle_errors(component="agent", operation="process_message")
    @log_performance("agent.process_message")
    async def process_message(self, message: UserInputMessage) -> Any:
        """处理消息
        Args:
            message: 用户消息
        Returns:
            处理结果
        """
        # 获取消息内容
        prompt = message.content if hasattr(message, "content") else str(message)

        # 【新增】文件引用解析（
        parsed_refs = self.file_reference_parser.parse(prompt)
        if parsed_refs.references:
            # 解析文件路径
            parsed_refs = self.path_resolver.resolve_all(parsed_refs)

            # 【新增】处理技能引用
            from dawei.agentic.file_reference import ReferenceType

            skill_references = [ref for ref in parsed_refs.references if ref.reference_type == ReferenceType.SKILL and ref.is_valid]

            if skill_references:
                # 加载技能内容到上下文
                from pathlib import Path

                from dawei.tools.skill_manager import SkillManager

                # 构建技能管理器，包含工作区和用户技能目录
                skills_roots = [Path(self.user_workspace.absolute_path), Path.home()]
                skill_manager = SkillManager(skills_roots=skills_roots)
                skill_manager.discover_skills(force=True)

                skills_loaded = 0
                for skill_ref in skill_references:
                    # 提取技能名称（从 "@skill:xxx" 或 "skill:xxx" 中提取 "xxx"）
                    raw_path = skill_ref.raw_path
                    skill_name = raw_path.lstrip("@").replace("skill:", "")

                    # 获取技能内容
                    skill_content = skill_manager.get_skill_content(skill_name)

                    if skill_content:
                        # 将技能内容添加到上下文
                        self.context_manager.add_skill_context(skill_name, skill_content)
                        skills_loaded += 1
                        self.logger.info(
                            f"✅ Loaded skill '{skill_name}' to context ({len(skill_content)} chars)",
                        )
                    else:
                        self.logger.warning(
                            f"⚠️  Skill '{skill_name}' not found or could not be loaded",
                        )

                if skills_loaded > 0:
                    self.logger.info(f"✅ Successfully loaded {skills_loaded} skill(s) to context")

                    # 发布技能引用事件
                    from dawei.core.events import TaskEventType

                    await self.event_bus.publish(
                        TaskEventType.SKILLS_LOADED,
                        {
                            "skills": [skill_ref.raw_path.replace("skill:", "") for skill_ref in skill_references],
                            "total_skills": skills_loaded,
                        },
                    )

            # 自动添加文件到上下文
            files_added = 0
            for ref in parsed_refs.references:
                if ref.is_valid and ref.reference_type != ReferenceType.SKILL:
                    for file_path in ref.resolved_paths:
                        self.context_manager.add_file(file_path)
                        files_added += 1
                        self.logger.debug(f"Added file to context: {file_path}")

            if files_added > 0:
                self.logger.info(f"Added {files_added} file(s) to context from user message")

                # 发布文件引用事件
                from dawei.core.events import TaskEventType

                await self.event_bus.publish(
                    TaskEventType.FILES_REFERENCED,
                    {
                        "files": [
                            {
                                "path": ref.resolved_paths,
                                "type": ref.reference_type.value,
                            }
                            for ref in parsed_refs.references
                            if ref.is_valid and ref.reference_type != ReferenceType.SKILL
                        ],
                        "total_files": files_added,
                    },
                )

            # 使用清理后的消息（移除文件引用标记）
            prompt = parsed_refs.cleaned_message
            # 更新消息内容
            if hasattr(message, "content"):
                message.content = prompt

        # 【新增】智能模型选择（
        context_length = self._estimate_context_length()

        # 判断是否为关键任务
        is_critical = self._is_critical_task(prompt)

        # 选择最优模型
        model_selection = self.model_router.select_model(
            prompt=prompt,
            context_length=context_length,
            is_critical=is_critical,
        )

        # 记录模型选择
        self.selected_models.append(
            {
                "model": model_selection.model,
                "reason": model_selection.reason,
                "task_type": model_selection.task_type.value,
                "timestamp": model_selection.timestamp,
                "context_length": context_length,
            },
        )

        # 发布模型选择事件
        from dawei.core.events import TaskEventType

        await self.event_bus.publish(
            TaskEventType.MODEL_SELECTED,
            {
                "model": model_selection.model,
                "reason": model_selection.reason,
                "task_type": model_selection.task_type.value,
                "confidence": model_selection.confidence,
                "context_length": context_length,
                "is_critical": is_critical,
            },
        )

        self.logger.info(
            f"Selected model: {model_selection.model} (reason: {model_selection.reason}, task: {model_selection.task_type.value})",
        )

        # Plan Mode: Attach plan_workflow to user_workspace context
        if self.plan_workflow is not None:
            self.user_workspace._plan_workflow = self.plan_workflow
            self.logger.debug("Plan workflow attached to user_workspace context")
        else:
            self.user_workspace._plan_workflow = None

        # 继续处理消息
        await self.execution_engine.process_message(message)
        await self.execution_engine.execute_task_graph()

        # 【新增】执行完成后自动提取记忆
        # Fast fail: only catch expected errors, let unknown errors propagate
        if self.memory_graph is not None and not self.memory_degraded:
            try:
                await self._extract_memories_after_execution()
            except (ConnectionError, TimeoutError, OSError) as e:
                # Expected errors: network issues, timeouts, etc.
                self.logger.warning(f"Memory extraction failed due to connectivity issue: {e}")
            except Exception as e:
                # Unexpected errors should fail fast - log as error
                self.logger.error(f"Memory extraction failed unexpectedly: {e}", exc_info=True)
                raise

        return

    async def _extract_memories_after_execution(self) -> None:
        """从最近对话中提取结构化记忆

        在 Agent 执行完成后自动调用，从对话中提取：
        - 事实记忆 (facts)
        - 偏好记忆 (preferences)
        - 策略记忆 (strategies)
        """
        import uuid

        # 获取对话消息
        if not hasattr(self.user_workspace, "current_conversation"):
            return

        conversation = self.user_workspace.current_conversation
        if not conversation or not hasattr(conversation, "messages"):
            return

        messages = conversation.messages
        if len(messages) < 2:
            return  # 需要至少用户消息和助手回复

        # 获取最近的消息进行记忆提取
        recent_messages = messages[-10:]  # 最多取最近10条

        # 格式化为文本
        messages_text = "\n".join([f"{str(msg.role)}: {msg.content[:500] if hasattr(msg, 'content') and msg.content else ''}" for msg in recent_messages if hasattr(msg, "content") and msg.content])

        if not messages_text.strip():
            return

        # 使用 LLM 提取结构化记忆
        try:
            llm_service = self.execution_engine._llm_service

            extraction_prompt = f"""从以下对话中提取结构化事实。

要求：
1. 每行一个事实，格式为：[主体] [关系] [对象]
2. 只提取重要的事实、偏好和用户信息
3. 关系使用英文动词或短语：prefers, likes, uses, knows, works_on 等

示例：
- User prefers Python
- Project uses FastAPI
- User dislikes JavaScript
- User works_on software development

对话：
{messages_text}

提取的事实："""

            # Convert dict format to LLMMessage format
            from dawei.entity.lm_messages import UserMessage
            llm_messages = [UserMessage(role="user", content=extraction_prompt)]

            response = await llm_service.process_message(
                messages=llm_messages,
                max_tokens=500,
                temperature=0.3,
            )

            if not response or not response.get("content"):
                return

            # 解析并存储记忆
            from dawei.memory.memory_graph import MemoryEntry, MemoryType

            for line in response["content"].strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("-"):
                    line = line.lstrip("-").strip()

                parts = line.split(maxsplit=2)
                if len(parts) >= 3:
                    # 推断记忆类型
                    memory_type = MemoryType.FACT
                    predicate_lower = parts[1].lower()
                    if any(w in predicate_lower for w in ["prefers", "likes", "loves", "wants"]):
                        memory_type = MemoryType.PREFERENCE
                    elif any(w in predicate_lower for w in ["uses", "requires", "needs"]):
                        memory_type = MemoryType.PROCEDURE
                    elif any(w in predicate_lower for w in ["learned", "discovered"]):
                        memory_type = MemoryType.STRATEGY

                    # 提取关键词
                    keywords = []
                    for part in parts:
                        import re

                        keywords.extend(re.findall(r"\b[A-Z][a-z]+\b", part))

                    memory = MemoryEntry(
                        id=str(uuid.uuid4()),
                        subject=parts[0],
                        predicate=parts[1],
                        object=parts[2],
                        valid_start=datetime.now(UTC),
                        memory_type=memory_type,
                        confidence=0.7,
                        energy=1.0,
                        keywords=list(set(keywords))[:5],
                        metadata={
                            "source": "conversation_extraction",
                            "conversation_id": str(conversation.id),
                        },
                    )

                    await self.memory_graph.add_memory(memory)
                    self.logger.debug(f"Extracted memory: {parts[0]} {parts[1]} {parts[2]}")

            self.logger.info(f"Memory extraction completed for conversation {conversation.id}")

        except (ConnectionError, TimeoutError, OSError) as e:
            # Expected: network/connectivity issues - fall back to simple extraction
            self.logger.warning(f"LLM unavailable for memory extraction, using fallback: {e}")
            await self._extract_memories_simple()
        except Exception as e:
            # Unexpected: should fail fast - log as error with stack trace
            self.logger.error(f"LLM-based memory extraction failed unexpectedly: {e}", exc_info=True)
            # Still fall back to simple extraction but surface the error
            await self._extract_memories_simple()

    async def _extract_memories_simple(self) -> None:
        """简单的记忆提取（不依赖 LLM）

        使用规则匹配从对话中提取基本信息
        """
        import re
        import uuid

        if not hasattr(self.user_workspace, "current_conversation"):
            return

        conversation = self.user_workspace.current_conversation
        if not conversation or not hasattr(conversation, "messages"):
            return

        messages = conversation.messages
        if len(messages) < 2:
            return

        from dawei.memory.memory_graph import MemoryEntry, MemoryType

        # 简单模式匹配
        patterns = {
            r"我喜欢(.+)": ("User", "prefers", MemoryType.PREFERENCE),
            r"我偏好(.+)": ("User", "prefers", MemoryType.PREFERENCE),
            r"我在做(.+)": ("User", "works_on", MemoryType.CONTEXT),
            r"我的项目是(.+)": ("Project", "is", MemoryType.FACT),
        }

        extracted_count = 0
        for msg in messages[-5:]:
            if not hasattr(msg, "content") or not msg.content:
                continue

            content = msg.content
            if str(msg.role) != "user":
                continue

            for pattern, (subject, predicate, mem_type) in patterns.items():
                matches = re.findall(pattern, content)
                for match in matches:
                    memory = MemoryEntry(
                        id=str(uuid.uuid4()),
                        subject=subject,
                        predicate=predicate,
                        object=match.strip(),
                        valid_start=datetime.now(UTC),
                        memory_type=mem_type,
                        confidence=0.5,
                        energy=1.0,
                        keywords=[subject, predicate],
                        metadata={"source": "simple_extraction"},
                    )
                    await self.memory_graph.add_memory(memory)
                    extracted_count += 1

        if extracted_count > 0:
            self.logger.info(f"Simple extraction: {extracted_count} memories")

    def _estimate_context_length(self) -> int:
        """估算当前上下文长度（使用 ContextManager）"""
        stats = self.context_manager.get_stats()
        return stats.used

    def _is_critical_task(self, prompt: str) -> bool:
        """判断是否为关键任务"""
        critical_keywords = [
            "formal report",
            "正式报告",
            "production",
            "生产环境",
            "official",
            "官方",
            "critical",
            "重要",
        ]
        prompt_lower = prompt.lower()
        return any(kw in prompt_lower for kw in critical_keywords)

    @handle_errors(component="agent", operation="pause_task")
    @log_performance("agent.pause_task")
    async def pause_task(self, task_id: str) -> bool:
        """暂停任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功暂停

        """
        # 委托给执行引擎
        result = await self.execution_engine.pause_task_execution(task_id)

        self.logger.info("Task paused", context={"task_id": task_id, "component": "agent"})
        increment_counter("agent.tasks_paused", tags={"status": "success"})
        return result

    @handle_errors(component="agent", operation="resume_task")
    @log_performance("agent.resume_task")
    async def resume_task(self, task_id: str) -> bool:
        """恢复任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功恢复

        """
        # 委托给执行引擎
        result = await self.execution_engine.resume_task_execution(task_id)

        self.logger.info("Task resumed", context={"task_id": task_id, "component": "agent"})
        increment_counter("agent.tasks_resumed", tags={"status": "success"})
        return result

    @handle_errors(component="agent", operation="abort_task")
    @log_performance("agent.abort_task")
    async def abort_task(self, task_id: str, reason: str | None = None) -> bool:
        """中止任务

        Args:
            task_id: 任务ID
            reason: 中止原因（可选）

        Returns:
            是否成功中止

        """
        # 委托给执行引擎
        result = await self.execution_engine.cancel_task_execution(task_id)

        self.logger.info(
            "Task aborted",
            context={"task_id": task_id, "reason": reason, "component": "agent"},
        )
        increment_counter("agent.tasks_aborted", tags={"status": "success"})
        return result

    @handle_errors(component="agent", operation="complete_task")
    @log_performance("agent.complete_task")
    async def complete_task(self, task_id: str, result: str | None = None) -> bool:
        """完成任务

        Args:
            task_id: 任务ID
            result: 任务结果（可选）

        Returns:
            是否成功完成

        """
        status_info = await self.execution_engine.get_task_execution_status(task_id)

        # 如果任务正在执行，等待其完成
        if status_info.get("is_executing", False):
            self.logger.info(f"Task {task_id} is still executing, waiting for completion")

        # 记录任务结果
        if result:
            self.logger.info(f"Task {task_id} completed with result: {result}")

        increment_counter("agent.tasks_completed", tags={"status": "success"})
        return True

    @handle_errors(component="agent", operation="get_task_status")
    async def get_task_status(self, task_id: str) -> TaskStatus:
        """获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态

        """
        status_info = await self.execution_engine.get_task_execution_status(task_id)

        # 根据状态信息返回相应的TaskStatus
        if status_info.get("is_executing", False):
            return TaskStatus.RUNNING
        if status_info.get("execution_time", 0) > 0:
            return TaskStatus.COMPLETED
        return TaskStatus.PENDING

    @handle_errors(component="agent", operation="get_task_summary")
    async def get_task_summary(self, task_id: str) -> TaskSummary:
        """获取任务摘要

        Args:
            task_id: 任务ID

        Returns:
            任务摘要

        """
        # TaskGraphExecutionEngine needs to get task info through task graph
        task = None  # Requires more complex logic
        mode_history = await self.get_mode_history(task_id)

        # Calculate number of subtasks created
        subtasks_created = 0  # Subtask statistics to be implemented

        return TaskSummary(
            task_id=task_id,
            instance_id="",  # To be retrieved from configuration
            initial_mode=task.mode if task else "",
            final_mode=task.mode if task else "",
            mode_transitions=len(mode_history),
            skill_calls=0,  # Skill call statistics to be implemented
            mcp_requests=0,  # MCP request statistics to be implemented
            subtasks_created=subtasks_created,
            tool_usage={name: {"attempts": usage.attempts, "failures": usage.failures} for name, usage in self.tool_usage.items()},
            token_usage={
                "input_tokens": self.token_usage.input_tokens,
                "output_tokens": self.token_usage.output_tokens,
                "cache_write_tokens": self.token_usage.cache_write_tokens,
                "cache_read_tokens": self.token_usage.cache_read_tokens,
                "total_cost": self.token_usage.total_cost,
            },
        )

    @handle_errors(component="agent", operation="get_task_statistics")
    async def get_task_statistics(self, task_id: str) -> dict[str, Any]:
        """获取任务统计信息

        Args:
            task_id: 任务ID

        Returns:
            任务统计信息

        """
        # TaskGraphExecutionEngine needs to get task info through task graph
        task = None  # Requires more complex logic
        current_mode = await self.get_current_mode(task_id)
        mode_history = await self.get_mode_history(task_id)

        # Get execution status from execution engine
        execution_status = await self.execution_engine.get_task_execution_status(task_id)

        # Simplify message counting logic
        messages_count = 0
        if hasattr(self.user_workspace, "current_conversation") and self.user_workspace.current_conversation and hasattr(self.user_workspace.current_conversation, "messages"):
            messages_count = len(self.user_workspace.current_conversation.messages)

        return {
            "task_id": task_id,
            "instance_id": "",  # To be retrieved from configuration
            "status": (await self.get_task_status(task_id)).value,
            "initial_mode": task.mode if task else "",
            "current_mode": current_mode,
            "messages_count": messages_count,
            "tool_usage": {name: {"attempts": usage.attempts, "failures": usage.failures} for name, usage in self.tool_usage.items()},
            "token_usage": {
                "input_tokens": self.token_usage.input_tokens,
                "output_tokens": self.token_usage.output_tokens,
                "cache_write_tokens": self.token_usage.cache_write_tokens,
                "cache_read_tokens": self.token_usage.cache_read_tokens,
                "total_cost": self.token_usage.total_cost,
            },
            "mode_transitions": len(mode_history),
            "execution_status": execution_status,
        }

    def _cleanup_selected_models(self) -> int:
        """清理过期的模型选择记录

        Returns:
            清理的记录数量
        """
        if not self.selected_models:
            return 0

        cutoff_time = datetime.now(UTC).timestamp() - self._selected_models_max_age_seconds
        original_len = len(self.selected_models)

        # 过滤掉超时的记录
        self.selected_models = deque(
            (item for item in self.selected_models if item.get("timestamp", 0) > cutoff_time),
            maxlen=1000,
        )

        cleaned = original_len - len(self.selected_models)
        if cleaned > 0:
            self.logger.debug(f"Cleaned {cleaned} expired model selection records")

        return cleaned

    @handle_errors(component="agent", operation="cleanup")
    @log_performance("agent.cleanup")
    async def cleanup(self, _task_id: str | None = None) -> bool:
        """清理资源

        Args:
            task_id: 任务ID（可选）

        Returns:
            是否成功清理

        """
        # 定义需要清理的组件列表
        cleanup_targets = [
            ("execution_engine", None),
            ("_llm_service", "_http_session"),
            ("_tool_call_service", None),
            ("_event_bus", None),
            ("_message_processor", None),
        ]

        # 清理执行引擎
        await self.execution_engine.cleanup()

        # 清理各个组件
        for attr_name, session_attr in cleanup_targets:
            component = getattr(self.execution_engine, attr_name, None)
            if component:
                # 清理主组件
                if hasattr(component, "cleanup"):
                    await component.cleanup()

                # 关闭HTTP会话（如果存在）
                if session_attr and hasattr(component, session_attr):
                    session = getattr(component, session_attr)
                    if session:
                        await session.close()
                        setattr(component, session_attr, None)

        # 清理任务图
        task_graph = getattr(self.execution_engine, "task_graph", None)
        if task_graph and hasattr(task_graph, "cleanup"):
            await task_graph.cleanup()

        # 清理用户工作区
        if self.user_workspace and hasattr(self.user_workspace, "cleanup"):
            await self.user_workspace.cleanup()

        # 清理模型选择历史记录
        self._cleanup_selected_models()

        # 重置初始化标志
        self._initialized = False

        self.logger.info("Agent cleaned up successfully", context={"component": "agent"})
        increment_counter("agent.cleanup", tags={"status": "success"})

        return True  # ✅ Return True to indicate successful cleanup

    async def stop(self) -> str:
        """停止Agent执行

        Returns:
            str: 结果摘要

        """
        self.logger.info("Stopping agent execution", context={"component": "agent"})

        # 设置停止标志
        self._stop_requested = True

        # 尝试停止执行引擎
        result_summary = "Agent已停止"
        try:
            if hasattr(self.execution_engine, "stop"):
                result_summary = await self.execution_engine.stop()
            else:
                result_summary = "Agent执行已停止"
        except RuntimeError as e:
            # Expected error during shutdown
            self.logger.warning(f"Execution engine shutdown warning: {e}", exc_info=True)
            result_summary = f"Agent已停止: {e!s}"
        except Exception as e:
            # Unexpected errors should be logged but not crash the stop process
            self.logger.error(f"Error stopping execution engine: {e}", exc_info=True)
            result_summary = f"Agent停止时发生错误: {e!s}"
            # Re-raise to ensure caller is aware of the failure
            raise

        increment_counter("agent.stop", tags={"status": "success"})
        return result_summary

    def is_stop_requested(self) -> bool:
        """检查是否请求停止"""
        return self._stop_requested

    # ========================================================================
    # Memory System Methods
    # ========================================================================

    async def add_memory(
        self,
        subject: str,
        predicate: str,
        object_: str,
        memory_type: str = "fact",
        confidence: float = 0.8,
        energy: float = 1.0,
        keywords: list[str] | None = None,
    ) -> str | None:
        """Add a memory entry

        Args:
            subject: Subject entity
            predicate: Relationship/property
            object_: Object entity
            memory_type: Type of memory (fact, preference, strategy, episodic)
            confidence: Confidence score (0-1)
            energy: Energy score (0-1)
            keywords: Optional keywords for retrieval

        Returns:
            Memory ID if successful, None otherwise

        """
        if not self.memory_graph:
            self.logger.debug("Memory system not enabled, skipping add_memory")
            return None

        try:
            from dawei.memory.memory_graph import MemoryEntry, MemoryType

            memory = MemoryEntry(
                id=str(uuid.uuid4()),
                subject=subject,
                predicate=predicate,
                object=object_,
                valid_start=datetime.now(UTC),
                memory_type=MemoryType(memory_type),
                confidence=confidence,
                energy=energy,
                keywords=keywords or [],
                metadata={"source": "agent"},
            )

            memory_id = await self.memory_graph.add_memory(memory)
            self.logger.info(f"Memory added: {memory_id} ({subject} {predicate} {object_})")
            return memory_id
        except Exception as e:
            self.logger.error(f"Failed to add memory: {e}", exc_info=True)
            return None

    async def query_memory(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        object_: str | None = None,
        memory_type: str | None = None,
        only_valid: bool = True,
    ) -> list[Any]:
        """Query memories

        Args:
            subject: Filter by subject
            predicate: Filter by predicate
            object_: Filter by object
            memory_type: Filter by memory type
            only_valid: Only return currently valid memories

        Returns:
            List of memory entries

        """
        if not self.memory_graph:
            return []

        try:
            from dawei.memory.memory_graph import MemoryType

            mem_type = MemoryType(memory_type) if memory_type else None

            return await self.memory_graph.query_temporal(
                subject=subject,
                predicate=predicate,
                object=object_,
                memory_type=mem_type,
                only_valid=only_valid,
            )
        except Exception as e:
            self.logger.error(f"Failed to query memory: {e}", exc_info=True)
            return []

    async def search_memories(self, query: str, limit: int = 50) -> list[Any]:
        """Search memories by keyword

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching memories

        """
        if not self.memory_graph:
            return []

        try:
            return await self.memory_graph.search_memories(query, limit=limit)
        except Exception as e:
            self.logger.error(f"Failed to search memories: {e}", exc_info=True)
            return []

    async def get_memory_stats(self) -> dict[str, Any] | None:
        """Get memory statistics

        Returns:
            Memory statistics dict or None

        """
        if not self.memory_graph:
            return None

        try:
            stats = await self.memory_graph.get_stats()
            return {
                "total": stats.total,
                "by_type": stats.by_type,
                "avg_confidence": stats.avg_confidence,
                "avg_energy": stats.avg_energy,
            }
        except Exception as e:
            self.logger.error(f"Failed to get memory stats: {e}", exc_info=True)
            # Re-raise to ensure caller is aware of the failure
            raise

    async def extract_memories_from_conversation(self) -> dict[str, Any]:
        """手动触发从当前对话中提取记忆

        Returns:
            提取结果字典，包含提取的记忆数量

        """
        if not self.memory_graph:
            return {"extracted": 0, "error": "Memory system not enabled"}

        try:
            # 调用内部提取方法
            await self._extract_memories_after_execution()
            return {"extracted": 1, "message": "Memory extraction triggered"}
        except Exception as e:
            self.logger.error(f"Failed to extract memories: {e}", exc_info=True)
            return {"extracted": 0, "error": str(e)}

    async def retrieve_associative_memories(
        self,
        entities: list[str],
        hops: int = 1,
        min_energy: float = 0.2,
    ) -> list[Any]:
        """Retrieve memories via associative graph traversal

        Args:
            entities: List of entity names to start from
            hops: Number of hops to traverse
            min_energy: Minimum energy threshold

        Returns:
            List of related memories

        """
        if not self.memory_graph:
            return []

        try:
            return await self.memory_graph.retrieve_associative(
                query_entities=entities,
                hops=hops,
                min_energy=min_energy,
            )
        except Exception as e:
            self.logger.error(f"Failed to retrieve associative memories: {e}", exc_info=True)
            return []

    # ========================================================================
    # Conversation Compression Methods
    # ========================================================================

    def _initialize_compression(self):
        """初始化对话压缩器

        从配置系统读取压缩配置，而不是直接读取环境变量。
        支持通过配置文件、环境变量等方式配置。
        """
        try:
            from dawei.config.settings import get_settings

            from .conversation_compressor import ConversationCompressor

            settings = get_settings()
            compression_config = settings.compression

            if not compression_config.enabled:
                self.logger.debug("Conversation compression disabled by config")
                return

            self.conversation_compressor = ConversationCompressor(
                context_manager=self.context_manager,
                preserve_recent=compression_config.preserve_recent,
                max_tokens=compression_config.max_tokens,
                compression_threshold=compression_config.compression_threshold,
                aggressive_threshold=compression_config.aggressive_threshold,
            )

            self.logger.info(
                f"Conversation compressor initialized: preserve_recent={compression_config.preserve_recent}, max_tokens={compression_config.max_tokens}, thresholds={compression_config.compression_threshold:.0%}-{compression_config.aggressive_threshold:.0%}",
            )

        except Exception as e:
            self.logger.warning(f"Failed to initialize conversation compressor: {e}", exc_info=True)
            self.conversation_compressor = None

    def get_compression_config(self) -> dict[str, Any] | None:
        """获取当前压缩配置

        Returns:
            压缩配置字典，如果未启用则返回None

        """
        if not self.conversation_compressor:
            return None

        try:
            from dawei.config.settings import get_settings

            settings = get_settings()
            compression_config = settings.compression

            return {
                "enabled": compression_config.enabled,
                "preserve_recent": compression_config.preserve_recent,
                "max_tokens": compression_config.max_tokens,
                "compression_threshold": compression_config.compression_threshold,
                "aggressive_threshold": compression_config.aggressive_threshold,
                "page_size": compression_config.page_size,
                "max_active_pages": compression_config.max_active_pages,
                "memory_integration_enabled": compression_config.memory_integration_enabled,
            }
        except Exception as e:
            self.logger.error(f"Failed to get compression config: {e}", exc_info=True)
            return None

    async def reload_compression_config(self):
        """重新加载压缩配置

        当配置文件变更时调用此方法重新初始化压缩器。
        """
        self.logger.info("Reloading compression configuration...")
        self.conversation_compressor = None
        self._initialize_compression()
