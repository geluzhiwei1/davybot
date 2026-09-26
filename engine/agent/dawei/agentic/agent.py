# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""重构后的 Agent 主类
通过 TaskGraphExecutionEngine 管理所有任务相关操作，简化 Agent 职责
"""

import asyncio
import uuid
from collections import deque
from datetime import datetime, timezone
from dawei.core.datetime_compat import UTC
from pathlib import Path
from typing import List, Dict, Any

from dawei.core.error_handler import handle_errors
from dawei.core.errors import (
    ConfigurationError,
)
from dawei.core.metrics import increment_counter
from dawei.core.utils import validate_and_create_config, workspace_config_to_agent_dict
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
    # override-or-inherit：读 effective（user 默认 + workspace 覆盖）
    return bool(_effective_memory_config(user_workspace).get("enabled", True))


def is_memory_read_enabled(user_workspace) -> bool:
    """Whether memories should be injected into context (read path)."""
    return bool(_effective_memory_config(user_workspace).get("read_enabled", True))


def is_memory_write_enabled(user_workspace) -> bool:
    """Whether memories should be extracted/written (write path)."""
    return bool(_effective_memory_config(user_workspace).get("write_enabled", True))


def is_knowledge_enabled(user_workspace) -> bool:
    """检查知识库系统是否启用（使用统一配置）

    Args:
        user_workspace: UserWorkspace instance

    Returns:
        True if knowledge system is enabled, False otherwise

    Raises:
        RuntimeError: If config is not loaded (Fast Fail)

    Examples:
        >>> ws = UserWorkspace("/path/to/workspace")
        >>> await ws.initialize()
        >>> is_knowledge_enabled(ws)
        True
    """
    config = user_workspace.get_config()  # Fast Fail if not loaded
    # override-or-inherit：读 effective（user 默认 + workspace 覆盖）
    return bool(_effective_knowledge_config(user_workspace).get("enabled", True))


def _effective_memory_config(user_workspace) -> dict:
    """override-or-inherit：合并 user memory 默认 + workspace memory 覆盖（ws 非 None 胜）。

    供 is_memory_enabled / _memory_default_energy / _init_memory_components / gardener 启动
    使用——让"用户级 memory 默认"成为基线，工作区可覆盖。失败时回退到 workspace raw。
    """
    try:
        from dawei.api.users.memory import load_user_memory

        user = load_user_memory(user_workspace.user_id)
        ws = user_workspace.get_config().memory.model_dump()
        return {**user, **{k: v for k, v in ws.items() if v is not None}}
    except Exception:
        return user_workspace.get_config().memory.model_dump()


def _effective_knowledge_config(user_workspace) -> dict:
    """override-or-inherit：合并 user knowledge 默认 + workspace knowledge 覆盖（ws 非 None 胜）。

    运行时真正生效的主要是 enabled；引擎参数由各 KB 实体的 kb.settings 驱动。
    失败时回退到 workspace raw。
    """
    try:
        from dawei.api.users.knowledge import load_user_knowledge

        user = load_user_knowledge(user_workspace.user_id)
        ws = user_workspace.get_config().knowledge.model_dump()
        return {**user, **{k: v for k, v in ws.items() if v is not None}}
    except Exception:
        return user_workspace.get_config().knowledge.model_dump()


def _memory_default_energy(user_workspace) -> float:
    """读取 effective memory default_energy（user 默认 + workspace 覆盖）；失败回退 1.0。"""
    try:
        return float(_effective_memory_config(user_workspace).get("default_energy", 1.0))
    except Exception:
        return 1.0


# Per-workspace MemoryGardener 注册表：避免每个 task-agent 各起一个 gardener 循环
# （多实例会在同一 memory.db 上重复 decay/archive）。进程级单例，按 workspace_id 去重。
# 注：无 stop-on-workspace-close 钩子，gardener 随进程生命周期存活（桌面单用户场景可接受）。
_WORKSPACE_GARDENERS: Dict[str, Any] = {}


class Agent:
    """重构后的 Agent 主类

    专注于协调各组件，通过 TaskGraphExecutionEngine 管理所有任务操作
    """

    def __init__(
        self,
        user_workspace: UserWorkspace,
        execution_engine: TaskGraphExecutionEngine,
        config: Any | Dict[str, Any] | None = None,
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

        # 全链路可观测性
        self._trace_id: str = str(uuid.uuid4())
        self._degraded_features: Dict[str, Dict[str, str]] = {}

        # 日志记录器（必须在使用前初始化）
        self.logger = get_logger(__name__)

        from dawei.core.events import SimpleEventBus

        self.event_bus = SimpleEventBus()
        self.logger.info(f"[AGENT] Agent created own event_bus (id={id(self.event_bus)})")

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
        self.user_memory_graph = None  # 用户级（跨工作区共享）
        self.virtual_context = None
        self._memory_gardeners: list = []  # MemoryGardener instances (workspace + user-level)
        self.memory_degraded = False  # Track memory system degradation state
        self._memory_retry_count = 0  # Track retry attempts for auto-recovery
        self._memory_retry_max = 3
        self._memory_retry_delay = 30.0  # seconds between retries
        if is_memory_enabled(self.user_workspace):
            self._init_memory_components()

        # 【新增】记忆提取调度器（定时+手动）
        self.memory_scheduler = None
        if is_memory_enabled(self.user_workspace) and self.memory_graph is not None:
            try:
                from dawei.memory.scheduler import MemoryExtractionScheduler

                llm_service = None
                if hasattr(self, "execution_engine") and hasattr(self.execution_engine, "llm_service"):
                    llm_service = self.execution_engine.llm_service

                self.memory_scheduler = MemoryExtractionScheduler(
                    workspace_path=str(self.user_workspace.absolute_path),
                    memory_graph=self.memory_graph,
                    llm_service=llm_service,
                    extraction_hour=0,  # 凌晨0点执行
                    extraction_minute=0,
                    user_memory_graph=self.user_memory_graph,
                    user_id=getattr(self.user_workspace, "user_id", "default_user"),
                )

                # 自动启动调度器
                import asyncio
                asyncio.create_task(self.memory_scheduler.start())

                self.logger.info("Memory extraction scheduler initialized and started")
            except Exception as e:
                self.logger.warning(f"Failed to initialize memory scheduler: {e}", exc_info=True)

        # 【新增】Plan Mode 工作流执行器
        self.plan_workflow = None
        if self.config.mode == "pdca":
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

        # 【新增】Knowledge 系统（可选）
        self.knowledge_base_id = None
        self.knowledge_degraded = False
        if is_knowledge_enabled(self.user_workspace):
            try:
                from dawei.knowledge.init import get_knowledge_base_manager

                # Get knowledge base manager and default base
                manager = get_knowledge_base_manager()
                default_base = manager.get_default_base()

                if default_base:
                    self.knowledge_base_id = default_base.id
                    self.logger.info(f"Knowledge system enabled, using default knowledge base: {default_base.id} ({default_base.name})")
                else:
                    # Create default knowledge base if it doesn't exist
                    from dawei.knowledge.base_models import KnowledgeBaseCreate

                    # 用用户级 knowledge 默认作为引擎参数模板（仅影响新建 KB）
                    try:
                        from dawei.knowledge.init import _user_knowledge_settings

                        kb_settings = _user_knowledge_settings() or {}
                    except Exception:
                        kb_settings = {}

                    default_base = manager.create_base(
                        KnowledgeBaseCreate(
                            name="默认知识库",
                            description="Agent 默认知识库",
                            is_default=True,
                            settings=kb_settings,
                        )
                    )
                    self.knowledge_base_id = default_base.id
                    self.logger.info(f"Created default knowledge base for Agent: {default_base.id}")

            except Exception as e:
                # Graceful degradation: Knowledge system is explicitly enabled but failed to initialize
                self.logger.error(
                    f"Knowledge system is enabled but failed to initialize: {e}. System will continue without knowledge capabilities.",
                    exc_info=True,
                )
                self.knowledge_degraded = True
                self.knowledge_base_id = None

        # 统计信息
        self.tool_usage: Dict[str, ToolUsage] = {}
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

    def _init_memory_components(self) -> None:
        """Initialize memory system components (MemoryGraph + VirtualContextManager).

        Attempts a single initialization. On failure, marks memory as degraded
        and records the reason in _degraded_features for user notification.
        The memory system can later be recovered via retry_memory_init().

        初始化两级 MemoryGraph:
        - workspace 级: {workspace}/.dawei/memory.db (工作区专属)
        - user 级: {DAWEI_HOME}/configs/{user_id}/memory.db (跨工作区共享)
        """
        from pathlib import Path as _Path

        # user 级 graph 初始为 None；初始化失败不影响 workspace 级
        self.user_memory_graph = None

        try:
            from dawei.memory.memory_graph import MemoryGraph
            from dawei.memory.virtual_context import VirtualContextManager

            workspace_path = str(self.user_workspace.absolute_path)
            memory_db = str(_Path(workspace_path) / ".dawei" / "memory.db")

            # Create EmbeddingManager for hybrid (keyword + semantic) memory search
            embedding_mgr = None
            try:
                from dawei.knowledge.embeddings.manager import EmbeddingManager

                embedding_mgr = EmbeddingManager()  # uses API backend by default
                self.logger.info(
                    f"EmbeddingManager ready for memory (backend={embedding_mgr.backend})"
                )
            except Exception as ee:
                self.logger.warning(
                    f"EmbeddingManager init failed — memory search will be keyword-only: {ee}"
                )

            # Initialize workspace-level MemoryGraph
            self.memory_graph = MemoryGraph(
                memory_db, self.event_bus, embedding_manager=embedding_mgr
            )

            # Initialize user-level MemoryGraph (跨工作区共享)
            try:
                from dawei.api.users.memory import _user_memory_db_path

                user_id = getattr(self.user_workspace, "user_id", "default_user")
                user_memory_db = _user_memory_db_path(user_id)
                self.user_memory_graph = MemoryGraph(
                    user_memory_db, self.event_bus, embedding_manager=embedding_mgr
                )
                self.logger.info(f"User-level memory graph initialized: {user_memory_db}")
            except Exception as ue:
                self.logger.warning(f"User-level memory graph init failed (non-fatal): {ue}")

            # 从 effective memory 配置读取调参（user 默认 + workspace 覆盖）
            try:
                mem_cfg = _effective_memory_config(self.user_workspace)
                page_size = mem_cfg.get("virtual_page_size", 2000)
                max_active_pages = mem_cfg.get("max_active_pages", 5)
            except Exception:
                page_size, max_active_pages = 2000, 5

            # Initialize VirtualContextManager
            self.virtual_context = VirtualContextManager(
                db_path=memory_db,
                page_size=page_size,
                max_active_pages=max_active_pages,
            )
            # Initialize MemoryGardener (energy decay + archival) for both levels
            # config.energy_decay_rate is a loss-rate (0.1 = remove 10% per cycle),
            # gardener.decay_rate is a multiplier (0.9 = keep 90%). Convert: 1 - loss.
            try:
                from dawei.memory.gardener import MemoryGardener

                decay_loss = mem_cfg.get("energy_decay_rate", 0.1)
                decay_multiplier = max(0.5, 1.0 - decay_loss)  # safety floor
                energy_threshold = mem_cfg.get("min_energy_threshold", 0.2)
                consolidation_enabled = mem_cfg.get("consolidation_enabled", False)

                llm_for_gardener = None
                if hasattr(self, "execution_engine") and hasattr(self.execution_engine, "llm_service"):
                    llm_for_gardener = self.execution_engine.llm_service

                ws_gardener = MemoryGardener(
                    memory_graph=self.memory_graph,
                    llm_provider=llm_for_gardener,
                    event_bus=self.event_bus,
                    decay_rate=decay_multiplier,
                    energy_threshold=energy_threshold,
                    consolidation_enabled=consolidation_enabled,
                )
                self._memory_gardeners.append(ws_gardener)

                if self.user_memory_graph:
                    user_gardener = MemoryGardener(
                        memory_graph=self.user_memory_graph,
                        llm_provider=llm_for_gardener,
                        event_bus=self.event_bus,
                        decay_rate=decay_multiplier,
                        energy_threshold=energy_threshold,
                        consolidation_enabled=consolidation_enabled,
                    )
                    self._memory_gardeners.append(user_gardener)

                # Start gardeners as background tasks
                for g in self._memory_gardeners:
                    asyncio.create_task(g.start())

                self.logger.info(
                    f"Memory Gardeners started ({len(self._memory_gardeners)} graphs, "
                    f"decay_rate={decay_multiplier:.2f}, threshold={energy_threshold})"
                )
            except Exception as ge:
                self.logger.warning(f"MemoryGardener init failed (non-fatal): {ge}")

            self.logger.info("Memory system initialized successfully")
        except Exception as e:
            self.logger.error(
                f"Memory system is enabled but failed to initialize: {e}. "
                f"System will continue without memory capabilities.",
                exc_info=True,
            )
            self.memory_degraded = True
            self.memory_graph = None
            self.virtual_context = None
            self._degraded_features["memory"] = {
                "reason": f"Memory system initialization failed: {str(e)[:200]}",
                "impact": "跨会话上下文保持、知识积累将不可用",
                "recoverable": "true",
            }

    async def retry_memory_init(self) -> bool:
        """Attempt to recover a degraded memory system with retries.

        Called before each new conversation to try re-initializing memory
        if it previously failed. Uses exponential backoff with configurable
        max retries and delay between attempts.

        Returns:
            True if memory was successfully recovered, False otherwise.
        """
        if not is_memory_enabled(self.user_workspace):
            return False
        if not self.memory_degraded:
            return True  # Already healthy

        memory_feature = self._degraded_features.get("memory", {})
        if memory_feature.get("recoverable") != "true":
            self.logger.info("Memory degradation is not recoverable, skipping retry")
            return False

        import asyncio

        while self._memory_retry_count < self._memory_retry_max:
            self._memory_retry_count += 1
            self.logger.info(
                f"Memory retry attempt {self._memory_retry_count}/{self._memory_retry_max}"
            )

            try:
                self._init_memory_components()

                if not self.memory_degraded:
                    # Success! Restore dependent components

                    # Re-initialize memory scheduler
                    try:
                        from dawei.memory.scheduler import MemoryExtractionScheduler
                        llm_service = None
                        if hasattr(self, "execution_engine") and hasattr(
                            self.execution_engine, "llm_service"
                        ):
                            llm_service = self.execution_engine.llm_service

                        self.memory_scheduler = MemoryExtractionScheduler(
                            workspace_path=str(self.user_workspace.absolute_path),
                            memory_graph=self.memory_graph,
                            llm_service=llm_service,
                            extraction_hour=0,
                            extraction_minute=0,
                            user_memory_graph=self.user_memory_graph,
                        )
                        asyncio.create_task(self.memory_scheduler.start())
                    except Exception as sched_e:
                        self.logger.warning(
                            f"Memory scheduler re-init failed (non-fatal): {sched_e}"
                        )

                    # Remove from degraded features
                    self._degraded_features.pop("memory", None)
                    self.logger.info(
                        f"Memory system recovered after {self._memory_retry_count} retries"
                    )

                    # Emit event for frontend notification
                    if self.event_bus:
                        from dawei.core.events import TaskEvent, TaskEventType
                        event = TaskEvent(
                            event_type=TaskEventType.MEMORY_READY,
                            data={"retry_count": self._memory_retry_count},
                        )
                        self.event_bus.emit(event)

                    return True
            except Exception as e:
                self.logger.warning(
                    f"Memory retry {self._memory_retry_count} failed: {e}",
                    exc_info=True,
                )

            if self._memory_retry_count < self._memory_retry_max:
                delay = self._memory_retry_delay * self._memory_retry_count
                self.logger.info(f"Waiting {delay:.1f}s before next memory retry...")
                await asyncio.sleep(delay)

        self.logger.error(
            f"Memory recovery failed after {self._memory_retry_max} attempts"
        )
        self._degraded_features["memory"] = {
            "reason": f"Memory recovery failed after {self._memory_retry_max} attempts",
            "impact": "跨会话上下文保持、知识积累将不可用",
            "recoverable": "false",
        }
        return False

    @classmethod
    async def create_with_default_engine(
        cls,
        user_workspace: UserWorkspace,
        config: Any | Dict[str, Any] | None = None,
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
        workspace_id = user_workspace.workspace_info.id if user_workspace.workspace_info else user_workspace.workspace_id
        logger.info(f"[AGENT_CREATE] Starting agent creation for workspace: {workspace_id}")

        # 配置处理 - 桥接 workspace config.json → AgentConfig
        # 优先级：AGENT_* env > 调用方 config > workspace config.json > Config 硬编码默认
        # （env 覆盖在 validate_and_create_config 内部最后应用，故现有 AGENT_* 部署不受影响）
        base: Dict[str, Any] = {}
        try:
            base = workspace_config_to_agent_dict(user_workspace.get_config())
            # override-or-inherit：skills.enabled 用 user 默认 + ws 覆盖的 effective 值
            # （workspace_config_to_agent_dict 是纯函数，无 user 级上下文，此处补 merge）
            try:
                from dawei.api.users.skills_tools import load_user_skills_tools

                _u = load_user_skills_tools(user_workspace.user_id).get("skills", {}) or {}
                _w = user_workspace.get_config().skills.model_dump()
                _eff = {**_u, **{k: v for k, v in _w.items() if v is not None}}
                base["enable_skills"] = bool(_eff.get("enabled", True))
            except Exception as e:
                logger.debug(f"[AGENT_CREATE] effective skills merge skipped: {e}")
        except Exception as e:
            logger.warning(
                f"[AGENT_CREATE] read workspace config failed, using defaults: {e}"
            )

        if isinstance(config, dict):
            merged = {**base, **config}  # 调用方键覆盖 workspace
            config_obj = validate_and_create_config(merged)
        elif config is None:
            config_obj = validate_and_create_config(base)
        else:
            # 已是 Config 实例：调用方显式构造，原样使用
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

            # 读取工作区 tools 段，用于工具层门控（config.json → 运行时桥接）
            # override-or-inherit：合并用户级 tools 默认 + 工作区覆盖
            ws_tools = None
            try:
                from dawei.api.users.skills_tools import load_user_skills_tools
                from dawei.workspace.models import ToolsConfig

                _u = load_user_skills_tools(user_workspace.user_id).get("tools", {}) or {}
                _w_raw = user_workspace.get_config().tools
                _w = _w_raw.model_dump() if _w_raw else {}
                _eff = {**_u, **{k: v for k, v in _w.items() if v is not None}}
                ws_tools = ToolsConfig(**_eff)
            except Exception as e:
                logger.warning(f"[AGENT_CREATE] read tools config failed: {e}")
                try:
                    ws_tools = user_workspace.get_config().tools
                except Exception:
                    ws_tools = None

            # 【修复】使用 WorkspaceToolManager 而不是 ToolManager
            # WorkspaceToolManager 会初始化 Skills 工具
            workspace_tool_manager = WorkspaceToolManager(
                workspace_root=user_workspace.absolute_path, user_id=user_workspace.user_id
            )
            await workspace_tool_manager.initialize()

            # 创建 ToolManager 传递给 ToolExecutor (向后兼容)
            tool_manager = ToolManager(
                workspace_root=user_workspace.absolute_path,
                tools_config=ws_tools,
                user_id=user_workspace.user_id,
            )

            tool_call_service = ToolExecutor(
                tool_manager=tool_manager,
                default_timeout=config_obj.tool_execution_timeout,
                max_concurrent=(
                    ws_tools.max_concurrent_executions if ws_tools is not None else 10
                ),
            )

            # 【新增】将 WorkspaceToolManager 的 skills 工具添加到 ToolExecutor
            if workspace_tool_manager._skills_tools:
                for skill_tool in workspace_tool_manager._skills_tools:
                    tool_call_service.tools[skill_tool.name] = skill_tool
                    logger.info(f"[AGENT_CREATE] Loaded skill tool: {skill_tool.name}")

            # Load knowledge tools
            try:
                from dawei.tools.custom_tools.knowledge_tool import KnowledgeSearchTool, KnowledgeRAGTool

                knowledge_tools = [
                    KnowledgeSearchTool(),
                    KnowledgeRAGTool(),
                ]

                for tool in knowledge_tools:
                    tool_call_service.tools[tool.name] = tool
                    logger.info(f"[AGENT_CREATE] Loaded knowledge tool: {tool.name}")

                logger.info(f"[AGENT_CREATE] Loaded {len(knowledge_tools)} knowledge tools")

            except ImportError as e:
                logger.warning(f"[AGENT_CREATE] Knowledge tools not available: {e}")
            except Exception as e:
                logger.error(f"[AGENT_CREATE] Failed to load knowledge tools: {e}", exc_info=True)

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
                workspace_id=task_id,
                event_bus=agent.event_bus,  # 使用 Agent 的 event_bus
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

            # 【2026-09-12 单一事实源】engine 同步挂载到 user_workspace：
            # 工具实例在 ToolManager 反射扫描期已创建（构造时 task_graph=None 冻结），
            # 运行期经 CustomBaseTool._resolve_execution_engine() 从这里解析，
            # 多工作区天然隔离（替代 workflow_tools_fixed 的模块级全局注册表竞态）。
            user_workspace.execution_engine = execution_engine

            # 【新增】设置 ToolExecutor 的 agent 引用（用于权限检查）
            tool_call_service._agent = agent

            # 设置 event_bus（用于发送工具事件）
            tool_call_service._event_bus = agent.event_bus

            # 启动 MemoryGardener（per-workspace 单例；config 驱动 decay/threshold）。
            # llm_provider=None → 只跑 decay+archive（廉价 SQL），不跑 LLM consolidation，
            # 零额外 LLM 成本，仅让 config.memory.energy_decay_rate / min_energy_threshold 生效。
            try:
                if getattr(agent, "memory_graph", None) and is_memory_enabled(user_workspace):
                    from dawei.memory.gardener import MemoryGardener

                    mem_cfg = _effective_memory_config(user_workspace)
                    g_id = (
                        user_workspace.workspace_info.id
                        if user_workspace.workspace_info
                        else user_workspace.workspace_id
                    )
                    existing = _WORKSPACE_GARDENERS.get(g_id)
                    if existing and getattr(existing, "_running", False):
                        agent.memory_gardener = existing
                    else:
                        gardener = MemoryGardener(
                            memory_graph=agent.memory_graph,
                            llm_provider=llm_service,
                            event_bus=agent.event_bus,
                            decay_rate=mem_cfg.get("energy_decay_rate", 0.95),
                            energy_threshold=mem_cfg.get("min_energy_threshold", 0.2),
                            consolidation_enabled=mem_cfg.get("consolidation_enabled", False),
                        )
                        await gardener.start()
                        _WORKSPACE_GARDENERS[g_id] = gardener
                        agent.memory_gardener = gardener
                        logger.info(
                            f"[AGENT_CREATE] MemoryGardener started "
                            f"(decay={mem_cfg.get('energy_decay_rate', 0.95)}, "
                            f"threshold={mem_cfg.get('min_energy_threshold', 0.2)})"
                        )
            except Exception as e:
                logger.warning(f"[AGENT_CREATE] MemoryGardener start failed (non-fatal): {e}")

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

        # Inject knowledge_base_id into tools if knowledge system is enabled
        if self.knowledge_base_id is not None:
            try:
                if hasattr(self.execution_engine, "tool_call_service"):
                    tool_call_service = self.execution_engine.tool_call_service
                    if hasattr(tool_call_service, "inject_knowledge_base_id"):
                        tool_call_service.inject_knowledge_base_id(self.knowledge_base_id)
                        self.logger.info(f"Knowledge base ID {self.knowledge_base_id} injected into tools")
            except Exception as e:
                self.logger.warning(
                    f"Failed to inject knowledge_base_id into tools: {e}",
                    exc_info=True,
                )

        # 【2026-09-14 资源接通】未显式指定 KB 时, 默认加载工作区安装的知识库。
        # install-v2 knowledge 路径写入 .dawei/knowledge_bases.json, 此前该文件无任何读者
        # (install_knowledge_bases 已实现但从未被调用 → 安装即空转)。
        if self.knowledge_base_id is None and self.user_workspace is not None:
            try:
                _kb_file = Path(self.user_workspace.absolute_path) / ".dawei" / "knowledge_bases.json"
                if _kb_file.exists():
                    import json as _json

                    _kbs = _json.loads(_kb_file.read_text(encoding="utf-8"))
                    _slugs = [
                        kb.get("slug")
                        for kb in _kbs
                        if isinstance(kb, dict) and kb.get("slug")
                    ]
                    if _slugs and hasattr(self.execution_engine, "tool_call_service"):
                        _tcs = self.execution_engine.tool_call_service
                        if hasattr(_tcs, "inject_knowledge_base_id"):
                            _tcs.inject_knowledge_base_id(_slugs)
                            # 注意: AgenticLogger 不支持 %-args, 必须用 f-string
                            self.logger.info(
                                f"Workspace-installed knowledge bases injected by default: {_slugs}"
                            )
            except Exception as e:
                # 注意: AgenticLogger 不支持 %-args, 必须用 f-string
                self.logger.warning(f"Failed to load workspace knowledge_bases.json: {e}")

        # Inject agent reference into tools that need it (e.g., ShowCostTool)
        try:
            if hasattr(self.execution_engine, "tool_call_service"):
                tool_call_service = self.execution_engine.tool_call_service
                if hasattr(tool_call_service, "inject_agent"):
                    tool_call_service.inject_agent(self)
        except Exception as e:
            self.logger.warning(
                f"Failed to inject agent into tools: {e}",
                exc_info=True,
            )

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

        # Process user-selected knowledge bases
        knowledge_base_ids = None
        if hasattr(message, "metadata") and message.metadata:
            knowledge_base_ids = message.metadata.get("knowledge_base_ids")
            if knowledge_base_ids and isinstance(knowledge_base_ids, list) and len(knowledge_base_ids) > 0:
                # Inject knowledge base IDs to tools
                try:
                    self.execution_engine.tool_call_service.inject_knowledge_base_id(knowledge_base_ids)
                    self.logger.debug(f"User-selected knowledge base IDs injected: {knowledge_base_ids}")
                except AttributeError:
                    self.logger.warning("Tool call service does not support knowledge base injection")
                except Exception as e:
                    self.logger.warning(f"Failed to inject knowledge base IDs: {e}", exc_info=True)

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
                from dawei import get_dawei_home

                # 构建技能管理器，包含工作区和用户技能目录
                # 【2026-09-14 崩溃修复】原代码传的是 get_dawei_home 函数对象（缺括号）,
                # SkillManager 遍历 skills_roots 时对函数取 / 运算 → TypeError, @skill 引用恒失败
                skills_roots = [Path(self.user_workspace.absolute_path), get_dawei_home()]
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

        # 【P0 修复】记忆注入：在调用 execution_engine 之前，检索相关记忆并注入系统提示
        await self._inject_memory_context(prompt)

        # 继续处理消息
        await self.execution_engine.process_message(message)
        await self.execution_engine.execute_task_graph()

        # 自动记忆提取：轻量级, 写入 auto-memory/ (非阻塞, 失败静默)
        try:
            await self._extract_auto_memories()
        except Exception:
            pass

        return

    async def _inject_memory_context(self, prompt: str) -> None:
        """读取 MD 记忆文件并注入 context（无检索，直接全文注入）。

        四层记忆, 显式标注作用域:
        - 用户记忆 (手写, 跨工作区): memory.md 全文
        - 工作区记忆 (手写, 仅当前项目): memory.md 全文
        - 自动记忆-用户级 (Agent 自写, 跨工作区): MEMORY.md 前 100 行
        - 自动记忆-工作区级 (Agent 自写, 仅当前项目): MEMORY.md 前 100 行
        """
        # 清理上一轮残留
        self.user_workspace._memory_context = None

        # Check read switch
        if not is_memory_read_enabled(self.user_workspace):
            return

        from dawei.memory.memory_file import (
            read_memory_md,
            user_memory_md_path,
            workspace_memory_md_path,
        )
        from dawei.memory.auto_memory import (
            user_auto_memory_dir,
            workspace_auto_memory_dir,
            read_auto_memory_index,
        )

        parts: list[str] = []

        # 1) 用户记忆 (手写, 跨工作区, 关于用户本人)
        try:
            user_md = read_memory_md(
                user_memory_md_path(self.user_workspace.user_id)
            )
            if user_md.strip():
                parts.append(
                    f"## 用户记忆（跨工作区，关于用户本人）\n{user_md.strip()}"
                )
        except Exception:
            pass

        # 2) 工作区记忆 (手写, 仅当前项目)
        try:
            ws_md = read_memory_md(
                workspace_memory_md_path(self.user_workspace.absolute_path)
            )
            if ws_md.strip():
                parts.append(
                    f"## 工作区记忆（仅当前项目）\n{ws_md.strip()}"
                )
        except Exception:
            pass

        # 3) 自动记忆-用户级 (Agent 从对话中学到的用户特征)
        try:
            user_auto = read_auto_memory_index(
                user_auto_memory_dir(self.user_workspace.user_id)
            )
            if user_auto.strip():
                parts.append(
                    f"## 自动记忆-用户级（Agent 从对话中学到的用户特征）\n{user_auto.strip()}"
                )
        except Exception:
            pass

        # 4) 自动记忆-工作区级 (Agent 从对话中学到的项目经验)
        try:
            ws_auto = read_auto_memory_index(
                workspace_auto_memory_dir(self.user_workspace.absolute_path)
            )
            if ws_auto.strip():
                parts.append(
                    f"## 自动记忆-工作区级（Agent 从对话中学到的项目经验）\n{ws_auto.strip()}"
                )
        except Exception:
            pass

        if parts:
            self.user_workspace._memory_context = "\n\n---\n\n".join(parts)
            self.logger.info(f"Injected memory context: {len(parts)} section(s)")

    async def _extract_memories_after_execution(self) -> None:
        """LLM 驱动的记忆提取 — 读取现有 memory.md + 新对话 → 更新 memory.md。

        用户级偏好写入 user memory.md；工作区相关写入 workspace memory.md。
        """
        if not is_memory_write_enabled(self.user_workspace):
            return

        if not hasattr(self.user_workspace, "current_conversation"):
            return
        conversation = self.user_workspace.current_conversation
        if not conversation or not hasattr(conversation, "messages"):
            return
        messages = conversation.messages
        if len(messages) < 2:
            return

        recent_messages = messages[-10:]
        messages_text = "\n".join(
            f"{str(msg.role)}: {msg.content[:500] if hasattr(msg, 'content') and msg.content else ''}"
            for msg in recent_messages if hasattr(msg, "content") and msg.content
        )
        if not messages_text.strip():
            return

        from dawei.memory.memory_file import (
            read_memory_md,
            write_memory_md,
            user_memory_md_path,
            workspace_memory_md_path,
        )
        from dawei.memory.redactor import redact_secrets

        user_md_path = user_memory_md_path(self.user_workspace.user_id)
        ws_md_path = workspace_memory_md_path(self.user_workspace.absolute_path)
        existing_user_md = read_memory_md(user_md_path)
        existing_ws_md = read_memory_md(ws_md_path)

        try:
            llm_service = self.execution_engine._llm_service
        except AttributeError:
            return

        prompt = f"""你是记忆管理助手。请根据对话内容更新记忆文件。

规则：
1. 保留现有记忆中仍然有效的条目
2. 添加新发现的重要信息（用户偏好、项目技术栈、工作习惯等）
3. 如果用户偏好有变化，更新对应条目（不要保留旧值）
4. 移除不再准确的条目
5. 使用简洁的 Markdown 列表格式
6. 按类别分组：## 用户偏好、## 项目信息、## 工作习惯、## 其他

现有用户级记忆：
{existing_user_md or "(空)"}

现有工作区记忆：
{existing_ws_md or "(空)"}

最新对话：
{messages_text}

请分别输出更新后的两个记忆文件内容。格式：
===USER===
（用户级记忆内容，包含跨工作区的偏好、习惯等）
===WORKSPACE===
（工作区级记忆内容，包含当前项目相关的信息）
如果某个文件无需更新，原样输出现有内容。"""

        try:
            from dawei.entity.lm_messages import UserMessage

            response = await llm_service.process_message(
                messages=[UserMessage(role="user", content=prompt)],
                max_tokens=800,
                temperature=0.3,
            )
            if not response or not response.get("content"):
                return

            raw = response["content"]
            # Parse ===USER=== and ===WORKSPACE=== sections
            import re as _re

            user_section = ""
            ws_section = ""

            user_match = _re.search(r"===USER===\s*\n(.*?)(?====WORKSPACE===|$)", raw, _re.DOTALL)
            ws_match = _re.search(r"===WORKSPACE===\s*\n(.*?)$", raw, _re.DOTALL)

            if user_match:
                user_section = user_match.group(1).strip()
            if ws_match:
                ws_section = ws_match.group(1).strip()

            # Fallback: if no markers, treat entire output as user-level
            if not user_section and not ws_section:
                user_section = raw.strip()

            # Apply secret redaction
            if user_section:
                user_section = redact_secrets(user_section)
            if ws_section:
                ws_section = redact_secrets(ws_section)

            # Write back only if changed
            changed = False
            if user_section and user_section != existing_user_md.strip():
                write_memory_md(user_md_path, user_section + "\n")
                changed = True
            if ws_section and ws_section != existing_ws_md.strip():
                write_memory_md(ws_md_path, ws_section + "\n")
                changed = True

            if changed:
                self.logger.info(f"Memory MD updated for conversation {conversation.id}")

        except (ConnectionError, TimeoutError, OSError) as e:
            self.logger.warning(f"LLM unavailable for memory extraction: {e}")
            await self._extract_memories_simple()
        except Exception as e:
            self.logger.error(f"Memory extraction failed: {e}", exc_info=True)

    async def _extract_memories_simple(self) -> None:
        """简单规则记忆提取（无 LLM）— 追加到 workspace memory.md。"""
        if not is_memory_write_enabled(self.user_workspace):
            return

        import re

        if not hasattr(self.user_workspace, "current_conversation"):
            return
        conversation = self.user_workspace.current_conversation
        if not conversation or not hasattr(conversation, "messages"):
            return
        messages = conversation.messages
        if len(messages) < 2:
            return

        from dawei.memory.memory_file import (
            append_memory_md,
            workspace_memory_md_path,
        )
        from dawei.memory.redactor import redact_secrets

        ws_md_path = workspace_memory_md_path(self.user_workspace.absolute_path)

        patterns = {
            r"我喜欢(.+)": "- 喜欢 {}",
            r"我偏好(.+)": "- 偏好 {}",
            r"我在做(.+)": "- 正在做: {}",
            r"我的项目是(.+)": "- 项目: {}",
        }

        appended = 0
        for msg in messages[-5:]:
            if not hasattr(msg, "content") or not msg.content:
                continue
            if str(msg.role) != "user":
                continue
            for pattern, template in patterns.items():
                matches = re.findall(pattern, msg.content)
                for match in matches:
                    line = template.format(match.strip())
                    line = redact_secrets(line)
                    append_memory_md(ws_md_path, line)
                    appended += 1

        if appended > 0:
            self.logger.info(f"Simple extraction: {appended} lines appended to memory.md")

    async def _extract_auto_memories(self) -> None:
        """轻量级 auto-memory 提取 — 从最近对话中提取值得记住的事实.

        与 _extract_memories_after_execution 不同:
        - 不修改手写 memory.md 文件
        - 写入 auto-memory/ 目录 (Agent 自主维护)
        - 使用轻量 LLM 调用, 只提取明确的事实
        - 失败静默, 不影响主流程
        """
        if not is_memory_write_enabled(self.user_workspace):
            return

        if not hasattr(self.user_workspace, "current_conversation"):
            return
        conversation = self.user_workspace.current_conversation
        if not conversation or not hasattr(conversation, "messages"):
            return
        messages = conversation.messages
        if len(messages) < 4:
            return

        # 只看最近 8 条消息, 控制成本
        recent = messages[-8:]
        messages_text = "\n".join(
            f"{msg.role}: {msg.content[:300] if hasattr(msg, 'content') and msg.content else ''}"
            for msg in recent if hasattr(msg, "content") and msg.content
        ).strip()
        if len(messages_text) < 50:
            return

        # 获取 LLM 服务
        try:
            llm_service = self.execution_engine._llm_service
        except AttributeError:
            return

        prompt = f"""Extract noteworthy memories from this conversation segment.
Only extract clear, concrete facts worth remembering for future conversations.
Skip vague or obvious things.

For each memory, output ONE line in this format:
scope|topic|summary
- scope: 'user' (about the user personally, cross-workspace) or 'workspace' (project-specific)
- topic: a short free-form label grouping related memories (no fixed list),
  e.g. '用户偏好', '项目规范', '客户要求', '操作经验'

Examples:
user|用户偏好|User prefers Chinese responses
workspace|项目规范|Project uses PostgreSQL 15 with pgvector
workspace|操作经验|Deploy with: npm build && scp && pm2 reload
user|饮食偏好|User is vegetarian

If nothing noteworthy, output exactly: NONE

Conversation:
{messages_text}

Memories:"""

        try:
            from dawei.entity.lm_messages import UserMessage

            response = await llm_service.process_message(
                messages=[UserMessage(role="user", content=prompt)],
                max_tokens=300,
                temperature=0.2,
            )
            if not response or not response.get("content"):
                return

            raw = response["content"].strip()
            if raw.upper() == "NONE" or not raw:
                return

            # 解析每行: scope|topic|summary
            from dawei.memory.auto_memory import (
                topic_slug,
                user_auto_memory_dir,
                workspace_auto_memory_dir,
                append_memory,
            )
            from dawei.memory.redactor import redact_secrets

            user_dir = user_auto_memory_dir(
                getattr(self.user_workspace, "user_id", "default_user")
            )
            ws_dir = workspace_auto_memory_dir(self.user_workspace.absolute_path)

            count = 0

            for line in raw.split("\n"):
                line = line.strip()
                if not line or line.count("|") < 2:
                    continue

                scope, topic, summary = (p.strip() for p in line.split("|", 2))

                # scope 非法默认工作区级; topic slug 非空才收
                if scope not in ("user", "workspace"):
                    scope = "workspace"
                if not topic_slug(topic):
                    continue

                summary = redact_secrets(summary)
                if len(summary) < 3:
                    continue

                target_dir = user_dir if scope == "user" else ws_dir

                try:
                    append_memory(
                        base_dir=target_dir,
                        topic=topic,
                        summary=summary,
                    )
                    count += 1
                except Exception:
                    pass

            if count:
                self.logger.info(f"Auto-memory extraction: {count} entries saved")

        except (ConnectionError, TimeoutError, OSError):
            pass  # LLM unavailable, skip silently
        except Exception as e:
            self.logger.debug(f"Auto-memory extraction skipped: {e}")

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

    # 【P3 pause/resume 下架 2026-09-17】Agent.pause_task/resume_task 已移除：
    # 它们委托给 execution_engine.pause/resume_task_execution —— 引擎从未实现
    # 这两个方法（AttributeError 被 @handle_errors 掩盖成静默失败），且
    # websocket 协议本无 TaskNodePause/Resume 消息、全仓零调用者。
    # 中止请用 abort_task / REST cancel / TASK_NODE_STOP；续跑用 message_task。

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
    async def get_task_statistics(self, task_id: str) -> Dict[str, Any]:
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

        # 停止 MemoryGardener 后台任务
        for gardener in self._memory_gardeners:
            try:
                await gardener.stop()
            except Exception:
                pass
        self._memory_gardeners.clear()

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
        keywords: List[str] | None = None,
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
    ) -> List[Any]:
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

    async def search_memories(self, query: str, limit: int = 50) -> List[Any]:
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

    async def get_memory_stats(self) -> Dict[str, Any] | None:
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

    async def extract_memories_from_conversation(self) -> Dict[str, Any]:
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
        entities: List[str],
        hops: int = 1,
        min_energy: float = 0.2,
    ) -> List[Any]:
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

    def get_compression_config(self) -> Dict[str, Any] | None:
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
