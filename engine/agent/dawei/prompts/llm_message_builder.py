# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""增强的系统构建器

重构后的核心组件，整合原有的 JinjaSystemBuilder 功能，
承担更多核心工作，提供更简洁的接口。
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from dawei.core.datetime_compat import UTC
from dawei.entity.lm_messages import AssistantMessage, ContentBlock, LLMMessage
from dawei.interfaces.message_processor import IMessageProcessor

from .core.template_manager import TemplateManager
from .core.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

# 占位 tool 结果内容：用于修复悬空 tool_calls（中断/压缩丢失结果）
_TOOL_RESULT_UNAVAILABLE = "[Tool result unavailable: execution was interrupted or the result was dropped during context compression]"


def sanitize_tool_call_pairs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """修复 tool_calls 与 tool 消息的配对关系（OpenAI API 硬性约束）。

    OpenAI 要求: assistant 消息携带 tool_calls 时，必须紧跟 role="tool" 的
    消息响应每一个 tool_call_id，否则 API 返回 400:
    "An assistant message with 'tool_calls' must be followed by tool messages
    responding to each 'tool_call_id'."

    对话压缩、任务中断后重放等场景可能破坏该配对。本函数在发送前做最后修复：
    - 未收到响应的 tool_call_id -> 紧跟注入占位 tool 消息
    - 无对应 tool_calls 的孤儿/重复 tool 消息 -> 丢弃

    Args:
        messages: OpenAI 格式消息列表

    Returns:
        修复后的消息列表（满足 tool_calls 配对约束）
    """
    result: list[dict[str, Any]] = []
    pending: dict[str, bool] = {}  # tool_call_id -> 是否已收到响应

    def _flush_placeholders() -> None:
        for tc_id, answered in pending.items():
            if not answered:
                logger.warning(f"Injecting placeholder tool result for unanswered tool_call_id={tc_id}")
                result.append({"role": "tool", "tool_call_id": tc_id, "content": _TOOL_RESULT_UNAVAILABLE})
        pending.clear()

    for msg in messages:
        if not isinstance(msg, dict):
            logger.warning(f"Skipping non-dict message in sanitize_tool_call_pairs: {type(msg).__name__}")
            continue
        role = msg.get("role")

        if role == "assistant" and msg.get("tool_calls"):
            # 下一个 assistant tool_calls 之前必须闭环上一个的响应
            _flush_placeholders()
            result.append(msg)
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id") or tc.get("tool_call_id") or ""
                if tc_id:
                    pending[tc_id] = False
            continue

        if role == "tool":
            tc_id = msg.get("tool_call_id") or ""
            if tc_id and pending.get(tc_id) is False:
                result.append(msg)
                pending[tc_id] = True
            else:
                logger.warning(f"Dropping orphan/duplicate tool message (tool_call_id={tc_id!r})")
            continue

        # 其他角色消息会隔断 tool_calls 与其响应，先补齐占位
        _flush_placeholders()
        result.append(msg)

    # 结尾悬空的 tool_calls（如中断后保存的 checkpoint）同样补占位
    _flush_placeholders()
    return result


class EnhancedSystemBuilder(IMessageProcessor):
    """增强的系统构建器

    重构后的核心组件，整合原有的 JinjaSystemBuilder 功能，
    承担更多核心工作，提供更简洁的接口。

    现在实现 IMessageProcessor 接口，直接作为消息处理器使用。
    """

    def __init__(
        self,
        user_workspace: Any,
        template_manager: TemplateManager | None = None,
        template_renderer: TemplateRenderer | None = None,
    ):
        """初始化增强系统构建器

        Args:
            user_workspace: 用户工作区实例
            template_manager: 模板管理器
            template_renderer: 模板渲染器

        """
        super().__init__(user_workspace)  # Call the __init__ of the parent class IMessageProcessor
        self.user_workspace = user_workspace
        # 初始化组件
        self.template_manager = template_manager or TemplateManager()
        self.template_renderer = template_renderer or TemplateRenderer()

        # 设置默认渲染器配置
        self.template_renderer.set_debug_mode(False)
        self.template_renderer.strict_undefined = False

        logger.info("EnhancedSystemBuilder initialized")

    def build_system_prompt(
        self,
        user_workspace,
        capabilities: list[str] | None = None,
        custom_instructions: str | None = None,
        additional_data: dict[str, Any] | None = None,
        conversation=None,  # P2-7: 子任务隔离会话（None = workspace.current_conversation）
    ) -> str:
        """构建系统提示词

        Args:
            user_workspace: 用户工作空间
            capabilities: 能力列表
            custom_instructions: 自定义指令
            additional_data: 附加数据
            conversation: 子任务隔离会话（可选，P2-7）

        Returns:
            str: 构建的系统提示词

        """
        # P2-7：隔离会话优先，未隔离回落 workspace 指针
        conv = conversation if conversation is not None else getattr(user_workspace, "current_conversation", None)

        # 从 user_workspace.workspace_info.user_ui_context.current_mode 获取当前模式
        current_mode = "orchestrator"  # 默认模式
        if user_workspace.workspace_info and hasattr(user_workspace.workspace_info, "user_ui_context") and user_workspace.workspace_info.user_ui_context:
            ui_ctx = user_workspace.workspace_info.user_ui_context
            ui_mode = ui_ctx.current_mode
            logger.info(f"[LLM_MESSAGE_BUILDER] UI context mode: {ui_mode}")
            # P0-1：ui_ctx 未设置时经 workspace.mode（ModeResolver 兜底链）解析，
            # 不再用字面量掩盖 None —— 自定义编排模式的 roleDefinition 才能激活
            current_mode = ui_mode or getattr(user_workspace, "mode", None) or "orchestrator"

            # 用户 @ 选择的专家直接覆盖 current_mode — 避免额外 LLM 调用
            experts = getattr(ui_ctx, "current_experts", None)
            if experts:
                expert_slug = experts[0] if isinstance(experts, list) else experts
                if user_workspace.mode_manager.is_valid_mode(expert_slug):
                    logger.info(f"[LLM_MESSAGE_BUILDER] Expert selected via @, switching mode: {expert_slug}")
                    current_mode = expert_slug

        logger.info(f"[LLM_MESSAGE_BUILDER] Final current_mode: {current_mode}")
        # 使用默认 task_node_id 或从其他地方获取
        task_node_id = getattr(conv, "id", "default_task") if conv else "default_task"

        # 【新增】Plan Mode: 从 user_workspace 获取 plan_workflow
        if additional_data is None:
            additional_data = {}
        if hasattr(user_workspace, "_plan_workflow") and user_workspace._plan_workflow is not None:
            additional_data["plan_workflow"] = user_workspace._plan_workflow
            logger.debug("Plan workflow found in user_workspace, adding to additional_data")

        # 1. 准备渲染上下文 - 直接使用 UserWorkspace 属性
        context = self._prepare_context(
            current_mode,
            task_node_id,
            user_workspace.workspace_info,
            conv,
            user_workspace.llm_manager,
            user_workspace.tool_manager,
            user_workspace.mode_manager,
            capabilities,
            custom_instructions,
            additional_data,
        )

        # 2. 选择合适的模板
        template_name = self._select_template(current_mode, context)

        # 3. 渲染模板
        result = self.template_manager.render_template(template_name, context, mode=current_mode)

        # 多租户业务工具：把当前用户可见的法律知识库 catalog 追加到系统提示（路由提示）。
        # 按用户 JWT 缓存（TTL 10 分钟）；失败绝不影响 prompt 构建。见 业务工具升级.md §5.6
        # 【mode-工具解耦 2026-09-19】原按 mode.groups 含 knowledge/sanctions 门控；
        # groups 退役后 knowledge 工具对全部 mode 可用（安装即所见），catalog 同步
        # 无条件注入——提示内容与工具面保持一致口径。
        try:
            from dawei.tools.custom_tools.knowledge_tool import get_cached_legal_kb_catalog_text

            _catalog = get_cached_legal_kb_catalog_text()
            if _catalog:
                result = f"{result}\n\n{_catalog}"
        except Exception:
            pass

        logger.debug(f"Built system prompt for mode {current_mode}, length: {len(result)}")
        return result

    def _prepare_context(
        self,
        current_mode: str,
        task_node_id: str,
        workspace_info,
        current_conversation,
        llm_manager,
        tool_manager,
        mode_manager,
        capabilities: list[str],
        custom_instructions: str | None,
        additional_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """准备渲染上下文

        Args:
            current_mode: 当前模式
            task_node_id: 任务ID
            workspace_info: 工作区信息
            current_conversation: 当前对话
            llm_manager: LLM管理器
            tool_manager: 工具管理器
            mode_manager: 模式管理器
            capabilities: 能力列表
            custom_instructions: 自定义指令
            additional_data: 附加数据

        Returns:
            Dict[str, Any]: 渲染上下文

        """
        # 基础上下文
        all_modes_list = list(mode_manager.get_all_modes().values())

        # 区分系统 mode (orchestrator/pdca) 和专家 mode (workspace 安装的 agents)
        _SYSTEM_SLUGS = {"orchestrator", "pdca"}
        system_modes = [m for m in all_modes_list if m.slug in _SYSTEM_SLUGS]
        expert_modes = [m for m in all_modes_list if m.slug not in _SYSTEM_SLUGS]

        # 从 user_ui_context 读取用户 @ 选择的专家
        user_selected_expert = None
        if workspace_info and hasattr(workspace_info, "user_ui_context") and workspace_info.user_ui_context:
            experts = getattr(workspace_info.user_ui_context, "current_experts", None)
            if experts:
                user_selected_expert = experts[0] if isinstance(experts, list) else experts

        context = {
            "current_mode": current_mode,
            "task_node_id": task_node_id,
            "workspace_info": workspace_info,
            "current_conversation": current_conversation,
            "llm_manager": llm_manager,
            "tool_manager": tool_manager,
            "mode_manager": mode_manager,
            "capabilities": capabilities,
            "custom_instructions": custom_instructions,
            "all_modes": all_modes_list,  # 兼容: 保留 all_modes
            "system_modes": system_modes,
            "expert_modes": expert_modes,
            "user_selected_expert": user_selected_expert,
        }

        # 【新增】从 current_conversation 或 additional_data 中提取 knowledge_base_ids
        knowledge_base_ids = None
        if additional_data and "knowledge_base_ids" in additional_data:
            knowledge_base_ids = additional_data["knowledge_base_ids"]
        elif current_conversation and hasattr(current_conversation, "messages"):
            # 从最近的用户消息中提取 knowledge_base_ids
            for msg in reversed(current_conversation.messages):
                if hasattr(msg, "metadata") and msg.metadata and "knowledge_base_ids" in msg.metadata:
                    knowledge_base_ids = msg.metadata["knowledge_base_ids"]
                    break

        if knowledge_base_ids:
            context["knowledge_base_ids"] = knowledge_base_ids
            logger.info(f"[LLM_MESSAGE_BUILDER] Found knowledge_base_ids: {knowledge_base_ids}")

        # 合并 additional_data 中的所有键值对到上下文中
        if additional_data:
            context.update(additional_data)

        # 【新增】PDCA Mode 工作流状态
        if current_mode == "pdca" and additional_data and "plan_workflow" in additional_data:
            plan_workflow = additional_data["plan_workflow"]
            if plan_workflow and hasattr(plan_workflow, "get_template_context"):
                # 获取工作流模板上下文并合并到主上下文
                plan_context = plan_workflow.get_template_context()
                context.update(plan_context)
                logger.debug(f"Added plan workflow context: {list(plan_context.keys())}")

        # 添加模式配置 - 使用 ModeManager 代替 config_manager
        # FAST FAIL（D1）：未知 slug 抛 ModeNotFoundError（附 available 清单），
        # 不再静默合成默认人设（conv d1eae353 事故根因）
        mode_info = mode_manager.get_mode_info(current_mode)

        if mode_info:
            context.update(
                {
                    "mode_name": getattr(mode_info, "name", ""),
                    "mode_description": getattr(mode_info, "description", ""),
                    "mode_slug": getattr(mode_info, "slug", ""),
                    "role_definition": getattr(mode_info, "role_definition", ""),
                    "whenToUse": getattr(mode_info, "when_to_use", ""),
                    "groups": getattr(mode_info, "groups", []),
                    "source": getattr(mode_info, "source", ""),
                    "custom_instructions": getattr(mode_info, "custom_instructions", ""),
                    "mode_rules": getattr(mode_info, "rules", {}),  # 添加 mode rules 字段
                },
            )

        # 添加工作空间信息
        if workspace_info:
            context["workspace_path"] = getattr(workspace_info, "absolute_path", "")
            # 将 user_ui_context 单独暴露给模板，方便 Jinja2 直接引用
            ui_ctx = getattr(workspace_info, "user_ui_context", None)
            if ui_ctx:
                context["user_ui_context"] = ui_ctx

        # 生成动态内容
        dynamic_content = self._generate_dynamic_content(context)
        context.update(dynamic_content)

        return context

    def _generate_dynamic_content(self, context: dict[str, Any]) -> dict[str, Any]:
        """生成动态内容

        Args:
            context: 基础上下文

        Returns:
            Dict[str, Any]: 动态内容

        """
        dynamic_content = {}

        # 生成段落内容
        sections = self._generate_sections(context)
        dynamic_content["sections"] = sections

        # 添加时间戳
        # 【cache-stable 2026-09-21】系统提示每次 LLM 调用都作为消息数组前缀
        # 重发；秒级时间戳会让服务端前缀缓存（DeepSeek auto prefix cache 等）
        # 永远无法命中，历史重放 token 全额计费（tui-review 实测 583 次调用
        # 放大 38.5×）。取整到小时：典型任务运行（<1h）内系统提示逐字节稳定。
        from datetime import datetime

        _now = datetime.now(UTC)
        dynamic_content["generation_timestamp"] = _now.replace(
            minute=0, second=0, microsecond=0
        ).isoformat()

        return dynamic_content

    def _generate_sections(self, context: dict[str, Any]) -> dict[str, Any]:
        """生成段落内容

        Args:
            context: 渲染上下文

        Returns:
            Dict[str, Any]: 段落内容

        """
        sections = {}

        # 能力段落
        if context.get("capabilities"):
            sections["capabilities"] = self._generate_capabilities_content(context)

        # 【新增】知识库段落 - 放在工具使用之前，强调其重要性
        sections["knowledge_base"] = self._generate_knowledge_base_content(context)

        # 规则段落
        sections["rules"] = self._generate_rules_content(context)

        # 响应长度限制段落（放在 RULES 之后，强调重要性）
        sections["response_limits"] = self._generate_response_limits_content(context)

        # 工具使用段落
        sections["tool_use"] = self._generate_tool_use_content(context)

        # Skills段落
        sections["skills"] = self._generate_skills_content(context)

        # Markdown 规则段落
        sections["markdown_rules"] = self._generate_markdown_rules_content(context)

        # 模式特定规则段落
        sections["mode_specific_rules"] = self._generate_mode_specific_rules_content(context)

        # 系统信息段落
        sections["system_information"] = self._generate_system_information_content(context)

        # 用户环境上下文段落（语言偏好、打开的文件、选中文本）
        sections["user_environment"] = self._generate_user_environment_content(context)

        # 目标段落
        sections["objective"] = self._generate_objective_content(context)

        # 记忆段落（从之前对话中提取的记忆）
        sections["memory"] = self._generate_memory_content(context)

        # 模式段落
        sections["modes"] = self._generate_modes_content(context)

        return sections

    def _generate_capabilities_content(self, context: dict[str, Any]) -> str:
        """生成能力段落内容

        Args:
            context: 渲染上下文

        Returns:
            str: 能力段落内容

        """
        # 使用模板文件代替硬编码规则
        template_path = "sections/capabilities.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_rules_content(self, context: dict[str, Any]) -> str:
        """生成规则内容

        Args:
            context: 渲染上下文

        Returns:
            str: 规则内容

        """
        # 使用模板文件代替硬编码规则
        template_path = "sections/rules.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_response_limits_content(self, context: dict[str, Any]) -> str:
        """生成响应长度限制内容

        Args:
            context: 渲染上下文

        Returns:
            str: 响应长度限制内容

        """
        template_path = "sections/response_limits.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_tool_use_content(self, context: dict[str, Any]) -> str:
        """生成工具使用内容

        Args:
            context: 渲染上下文

        Returns:
            str: 工具使用内容

        """
        # 使用模板文件代替硬编码规则
        template_path = "sections/tools.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_skills_content(self, context: dict[str, Any]) -> str:
        """生成Skills使用内容

        Args:
            context: 渲染上下文

        Returns:
            str: Skills使用内容

        """
        # 使用skills模板文件
        template_path = "sections/skills.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_markdown_rules_content(self, context: dict[str, Any]) -> str:
        """生成 Markdown 规则内容

        Args:
            context: 渲染上下文

        Returns:
            str: Markdown 规则内容

        Raises:
            TemplateRenderError: 模板渲染失败
            FileNotFoundError: 模板文件不存在

        """
        template_path = "sections/markdown_rules.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_mode_specific_rules_content(self, context: dict[str, Any]) -> str:
        """生成模式特定规则内容

        Args:
            context: 渲染上下文

        Returns:
            str: 模式特定规则内容

        Raises:
            TemplateRenderError: 模板渲染失败
            FileNotFoundError: 模板文件不存在

        """
        template_path = "sections/mode_specific_rules.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_system_information_content(self, context: dict[str, Any]) -> str:
        """生成系统信息内容

        Args:
            context: 渲染上下文

        Returns:
            str: 系统信息内容

        """
        # 使用模板文件代替硬编码规则
        template_path = "sections/system_information.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_user_environment_content(self, context: dict[str, Any]) -> str:
        """生成用户环境上下文内容（语言偏好、打开的文件、选中文本等）

        Args:
            context: 渲染上下文

        Returns:
            str: 用户环境上下文内容，无上下文时返回空字符串

        """
        template_path = "sections/user_environment.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_objective_content(self, context: dict[str, Any]) -> str:
        """生成目标内容

        Args:
            context: 渲染上下文

        Returns:
            str: 目标内容

        """
        # 使用模板文件代替硬编码规则
        template_path = "sections/objective.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_memory_content(self, context: dict[str, Any]) -> str:
        """生成记忆段落内容

        从 self.user_workspace._memory_context 读取 Agent 在 process_message 中
        预取的记忆，注入系统提示词。无记忆时返回空字符串。

        Args:
            context: 渲染上下文

        Returns:
            str: 记忆段落内容

        """
        memory_context = getattr(self.user_workspace, "_memory_context", None)
        if not memory_context:
            return ""
        context["memory_context"] = memory_context
        template_path = "sections/memory.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_modes_content(self, context: dict[str, Any]) -> str:
        """生成模式内容

        Args:
            context: 渲染上下文

        Returns:
            str: 模式内容

        """
        template_path = "sections/modes.j2"
        return self.template_manager.render_template(template_path, context)

    def _generate_knowledge_base_content(self, context: dict[str, Any]) -> str:
        """生成知识库内容

        Args:
            context: 渲染上下文

        Returns:
            str: 知识库内容

        """
        template_path = "sections/knowledge_base.j2"
        return self.template_manager.render_template(template_path, context)

    def _select_template(self, mode: str, context: dict[str, Any]) -> str:
        """选择合适的模板

        Args:
            mode: 模式名称
            context: 渲染上下文

        Returns:
            str: 模板名称

        """
        # 获取模式管理器
        mode_manager = context.get("mode_manager")
        if not mode_manager:
            # 使用默认模板
            return "base/system_prompt.j2"

        # 由于新的 ModeConfig 不再包含 template_overrides 和 language_overrides
        # 直接使用默认模板（mode 有效性校验在 _prepare_context FAST FAIL）
        return "base/system_prompt.j2"

    def build_prompt_with_sections(
        self,
        user_workspace,
        capabilities: list[str],
        enabled_sections: list[str] | None = None,
        disabled_sections: list[str] | None = None,
        custom_instructions: str | None = None,
        additional_data: dict[str, Any] | None = None,
    ) -> str:
        """构建指定段落的系统提示词

        Args:
            user_workspace: 用户工作空间
            capabilities: 能力列表
            enabled_sections: 启用的段落列表
            disabled_sections: 禁用的段落列表
            custom_instructions: 自定义指令
            additional_data: 附加数据

        Returns:
            str: 构建的系统提示词

        Raises:
            TemplateRenderError: 模板渲染失败
            AttributeError: user_workspace 缺少必要属性
            ValueError: 无效的配置参数

        """
        # 从 user_workspace.workspace_info.user_ui_context.current_mode 获取当前模式
        current_mode = "orchestrator"  # 默认模式
        if user_workspace.workspace_info and hasattr(user_workspace.workspace_info, "user_ui_context") and user_workspace.workspace_info.user_ui_context:
            ui_ctx = user_workspace.workspace_info.user_ui_context
            ui_mode = ui_ctx.current_mode
            logger.info(f"[LLM_MESSAGE_BUILDER] UI context mode: {ui_mode}")
            # P0-1：ui_ctx 未设置时经 workspace.mode（ModeResolver 兜底链）解析，
            # 不再用字面量掩盖 None —— 自定义编排模式的 roleDefinition 才能激活
            current_mode = ui_mode or getattr(user_workspace, "mode", None) or "orchestrator"

            # 用户 @ 选择的专家直接覆盖 current_mode — 避免额外 LLM 调用
            experts = getattr(ui_ctx, "current_experts", None)
            if experts:
                expert_slug = experts[0] if isinstance(experts, list) else experts
                if user_workspace.mode_manager.is_valid_mode(expert_slug):
                    logger.info(f"[LLM_MESSAGE_BUILDER] Expert selected via @, switching mode: {expert_slug}")
                    current_mode = expert_slug

        logger.info(f"[LLM_MESSAGE_BUILDER] Final current_mode: {current_mode}")
        # 使用默认 task_node_id 或从其他地方获取
        task_node_id = getattr(user_workspace.current_conversation, "id", "default_task") if user_workspace.current_conversation else "default_task"

        # 准备上下文 - 直接使用 UserWorkspace 属性
        context = self._prepare_context(
            current_mode,
            task_node_id,
            user_workspace.workspace_info,
            user_workspace.current_conversation,
            user_workspace.llm_manager,
            user_workspace.tool_manager,
            user_workspace.mode_manager,
            capabilities,
            custom_instructions,
            additional_data,
        )

        # 更新段落控制
        if enabled_sections:
            context["enabled_sections"] = enabled_sections
        if disabled_sections:
            context["disabled_sections"] = disabled_sections

        # 选择模板
        template_name = self._select_template(current_mode, context)

        # 渲染模板
        return self.template_manager.render_template(template_name, context, mode=current_mode)

    def get_available_templates(self) -> list[str]:
        """获取所有可用模板

        Returns:
            List[str]: 模板名称列表

        """
        return self.template_manager.get_available_templates()

    def get_template_variables(self, template_name: str) -> list[str]:
        """获取模板变量

        Args:
            template_name: 模板名称

        Returns:
            List[str]: 变量名列表

        Raises:
            FileNotFoundError: 模板文件不存在
            TemplateRenderError: 模板解析失败
            AttributeError: 模板缺少source属性

        """
        template = self.template_manager.get_template(template_name)
        if not template:
            raise FileNotFoundError(f"Template not found: {template_name}")

        if not hasattr(template, "source"):
            raise AttributeError(f"Template {template_name} missing 'source' attribute")

        return self.template_renderer.extract_variables(template.source)

    def validate_template(self, template_name: str) -> list[str]:
        """验证模板

        Args:
            template_name: 模板名称

        Returns:
            List[str]: 错误列表，空列表表示验证通过

        Raises:
            FileNotFoundError: 模板文件不存在
            TemplateRenderError: 模板语法验证失败
            IOError: 模板文件读取失败

        """
        template = self.template_manager.get_template(template_name)
        if not template:
            raise FileNotFoundError(f"Template not found: {template_name}")

        # 获取模板源代码
        template_source = getattr(template, "source", None)
        if template_source is None:
            # 如果没有source属性，尝试从文件读取
            template_path = self.template_manager.templates_path / template_name
            if not template_path.exists():
                raise FileNotFoundError(f"Template file not found: {template_name}")

            with Path(template_path).open(encoding="utf-8") as f:
                template_source = f.read()

        return self.template_renderer.validate_template_syntax(template_source)

    def get_render_stats(self) -> dict[str, Any]:
        """获取渲染统计信息

        Returns:
            Dict[str, Any]: 统计信息

        """
        return self.template_renderer.get_render_stats()

    def reload_templates(self) -> None:
        """重新加载模板"""
        self.template_manager.reload_templates()
        logger.info("Templates reloaded")

    def get_language_info(self, _language: str) -> dict[str, Any] | None:
        """获取语言信息

        Args:
            language: 语言代码

        Returns:
            Optional[Dict[str, Any]]: 语言信息

        """
        # 这个方法现在应该通过其他方式获取语言信息，而不是 config_manager
        # 但由于这个类没有直接访问语言配置，这里返回 None
        # 建议调用者使用其他方式获取语言信息
        logger.warning(
            "get_language_info() is deprecated, language config should be accessed differently",
        )
        return None

    # IMessageProcessor 接口实现

    async def build_messages(
        self,
        user_workspace: Any,
        capabilities: list[str],
        conversation=None,  # P2-7: 子任务隔离会话（None = workspace.current_conversation）
    ) -> dict[str, Any]:
        """构建消息列表

        Args:
            user_workspace: 用户工作区实例
            capabilities: 能力列表
            conversation: 子任务隔离会话（可选，P2-7）

        Returns:
            包含消息和工具的字典

        Raises:
            TemplateRenderError: 系统提示构建失败
            AttributeError: user_workspace 缺少必要属性
            ValueError: 无效的消息格式

        """
        logger.debug(f"Building messages for workspace with capabilities: {capabilities}")

        # P2-7：消息历史来源 — 隔离会话优先，未隔离回落 workspace 指针
        conv = conversation if conversation is not None else getattr(user_workspace, "current_conversation", None)

        # 构建消息列表
        messages = []

        # 构建系统提示
        system_prompt = self.build_system_prompt(user_workspace, capabilities, conversation=conversation)
        messages.append({"role": "system", "content": system_prompt})

        # 添加历史消息
        if conv and hasattr(conv, "messages"):
            conversation_messages = []
            for msg in conv.messages:
                # 将消息对象转换为字典格式（OpenAI格式）
                if hasattr(msg, "to_dict"):
                    msg_dict = msg.to_dict()
                elif hasattr(msg, "model_dump"):
                    msg_dict = msg.model_dump()
                else:
                    msg_dict = dict(msg)

                # 确保是有效的消息格式
                if isinstance(msg_dict, dict) and "role" in msg_dict:
                    conversation_messages.append(msg_dict)
                    # 【调试】添加日志验证 msg_dict 类型
                    logger.debug(
                        f"Added message to LLM request: type={type(msg_dict).__name__}, role={msg_dict.get('role')}, content_len={len(str(msg_dict.get('content', '')))}",
                    )
                else:
                    # 【调试】记录被跳过的消息类型
                    logger.warning(
                        f"Skipped invalid message format: original_type={type(msg).__name__}, converted_type={type(msg_dict).__name__}",
                    )

            # 【新增】对话压缩处理
            (
                compressed_messages,
                compression_stats,
            ) = await self._apply_conversation_compression(
                user_workspace,
                conversation_messages,
            )

            # 记录压缩统计
            if compression_stats.strategy_used != "none":
                logger.info(
                    f"Conversation compression applied: {compression_stats.strategy_used}, {compression_stats.original_count} -> {compression_stats.compressed_count} messages, {compression_stats.compression_ratio:.1%} reduction",
                )

            # 【400 修复】压缩/中断可能破坏 tool_calls 与 tool 消息配对，
            # 发送前强制修复，避免 "insufficient tool messages following tool_calls" 400
            messages.extend(sanitize_tool_call_pairs(compressed_messages))

        # 获取工具（含 SessionToolPool 过滤 + SchemaCompressor 压缩）
        openai_tools = await self._get_tools_for_llm(user_workspace)

        # 注入工具发现提示到系统消息（渐进式披露模式）
        # （mode-工具解耦 §4.4：提示中的工具数引用本轮实际绑定数（tools= 列表长度），
        #   不用池内计数——消灭"已激活 N 个"与实际绑定不一致的误导指纹）
        pool = getattr(user_workspace, "_session_tool_pool", None)
        if pool is not None and messages and messages[0].get("role") == "system":
            messages[0]["content"] = self._inject_tools_hint(messages[0]["content"], pool, len(openai_tools))

        result = {"messages": messages}
        if openai_tools:
            result["tools"] = openai_tools

        logger.debug(f"Messages built successfully: {len(result.get('messages', []))} messages")
        # 记录消息类型统计
        role_counts = {}
        for msg in result.get("messages", []):
            # 【调试】添加日志验证 msg 类型
            msg_type = type(msg).__name__
            logger.debug(f"Message type in role_counts: {msg_type}")

            # 安全获取 role，处理非字典类型
            if isinstance(msg, dict):
                role = msg.get("role", "unknown")
            else:
                # 如果是 Pydantic 模型，使用 getattr 获取属性
                role = getattr(msg, "role", None)
                if hasattr(role, "value"):
                    role = role.value
                elif role is not None:
                    role = str(role)
                else:
                    role = "unknown"

            role_counts[role] = role_counts.get(role, 0) + 1
        logger.debug(f"Message role distribution: {role_counts}")
        return result

    async def _apply_conversation_compression(
        self,
        user_workspace: Any,
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], Any]:
        """应用对话压缩

        Args:
            user_workspace: 用户工作区实例
            messages: 原始消息列表

        Returns:
            (压缩后的消息列表, 压缩统计信息)

        """
        from dawei.agentic.conversation_compressor import (
            CompressionStats,
            ConversationCompressor,
        )

        # 获取或创建压缩器
        compressor = getattr(user_workspace, "_conversation_compressor", None)

        # 检查是否需要启用压缩
        if compressor is None:
            try:
                # 使用配置系统检查是否启用压缩
                from dawei.config.settings import get_settings

                settings = get_settings()
                compression_config = settings.compression

                if not compression_config.enabled:
                    # 未启用压缩，直接返回
                    return messages, CompressionStats(
                        original_count=len(messages),
                        compressed_count=len(messages),
                        original_tokens=0,
                        compressed_tokens=0,
                        strategy_used="none",
                    )

                # 获取context_manager（从user_workspace或其他地方）
                context_manager = getattr(user_workspace, "context_manager", None)

                # 使用配置系统中的参数创建压缩器
                compressor = ConversationCompressor(
                    context_manager=context_manager,
                    preserve_recent=compression_config.preserve_recent,
                    max_tokens=compression_config.max_tokens,
                    compression_threshold=compression_config.compression_threshold,
                    aggressive_threshold=compression_config.aggressive_threshold,
                )

                # 缓存到user_workspace
                user_workspace._conversation_compressor = compressor

                logger.info(
                    f"Conversation compressor created from config: preserve_recent={compression_config.preserve_recent}, max_tokens={compression_config.max_tokens}",
                )

            except Exception as e:
                logger.warning(f"Failed to load compression config, skipping compression: {e}")
                return messages, CompressionStats(
                    original_count=len(messages),
                    compressed_count=len(messages),
                    original_tokens=0,
                    compressed_tokens=0,
                    strategy_used="none",
                )

        # 检查是否需要压缩
        if not compressor.should_compress(messages):
            return messages, CompressionStats(
                original_count=len(messages),
                compressed_count=len(messages),
                original_tokens=0,
                compressed_tokens=0,
                strategy_used="none",
            )

        # 计算实际可用于对话的 token 预算
        # = 模型上下文窗口 - (system_prompt + tools + skills + files + 安全余量)
        effective_target = None
        context_manager = getattr(user_workspace, "context_manager", None)
        if context_manager:
            ctx_stats = context_manager.get_stats()
            overhead = (
                ctx_stats.breakdown.system_prompt
                + ctx_stats.breakdown.tool_definitions
                + ctx_stats.breakdown.skills
                + ctx_stats.breakdown.workspace_files
                + 8000  # 安全余量，留给模型输出
            )
            effective_target = max(ctx_stats.total - overhead, 8000)
            logger.info(
                f"Effective compression budget: {effective_target} tokens "
                f"(total={ctx_stats.total}, overhead={overhead})",
            )

        # 应用压缩
        compressed, stats = compressor.compress_conversation(
            messages,
            target_tokens=effective_target,
        )

        return compressed, stats

    def build_user_message(self, task: str, images: list[str] | None = None) -> dict[str, Any]:
        """构建用户消息

        Args:
            task: 任务描述
            images: 可选的图片列表

        Returns:
            用户消息字典

        Raises:
            ValueError: task 为空或 images 格式无效
            TypeError: images 不是列表类型

        """
        if not task or not isinstance(task, str):
            raise ValueError("task must be a non-empty string")

        if images is not None and not isinstance(images, list):
            raise TypeError("images must be a list")

        logger.debug(f"Building user message for task: {task[:100]}...")

        # 构建用户消息
        message = {"role": "user", "content": task}

        if images:
            # 如果有图片，转换为多模态格式
            content = [{"type": "text", "text": task}]

            for image_path in images:
                if not isinstance(image_path, str):
                    raise TypeError(f"image_path must be string, got {type(image_path)}")
                content.append({"type": "image_url", "image_url": {"url": image_path}})

            message["content"] = content

        logger.debug("User message built successfully")
        return message

    def build_assistant_message(
        self,
        content: str | list[ContentBlock] | None,
        tool_calls: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> AssistantMessage:
        """构建助手消息

        Args:
            content: 消息内容
            tool_calls: 工具调用列表
            **kwargs: 其他参数

        Returns:
            助手消息对象

        Raises:
            ValueError: tool_calls 格式无效
            TypeError: tool_calls 不是列表类型

        """
        if tool_calls is not None and not isinstance(tool_calls, list):
            raise TypeError("tool_calls must be a list")

        logger.debug("Building assistant message")

        # 将 tool_calls 转换为 ToolCall 对象列表
        tool_call_objects = []
        if tool_calls:
            from dawei.entity.lm_messages import FunctionCall, ToolCall

            for tc_data in tool_calls:
                if not isinstance(tc_data, dict):
                    raise TypeError(f"tool_call must be dict, got {type(tc_data)}")

                function_data = tc_data.get("function", {})
                if not isinstance(function_data, dict):
                    raise ValueError(f"tool_call function must be dict, got {type(function_data)}")

                tool_call_objects.append(
                    ToolCall(
                        tool_call_id=tc_data.get("id", ""),
                        type=tc_data.get("type", "function"),
                        function=FunctionCall(
                            name=function_data.get("name", ""),
                            arguments=function_data.get("arguments", "{}"),
                        ),
                    ),
                )

        message = AssistantMessage(
            content=content,
            tool_calls=tool_call_objects or None,
            **kwargs,
        )

        logger.debug("Assistant message built successfully")
        return message

    async def add_message_to_conversation(self, task_node_id: str, message: LLMMessage) -> None:
        """将消息添加到对话中

        Args:
            task_node_id: 任务ID
            message: 消息对象

        """
        logger.debug(f"Adding message to conversation for task {task_node_id}")
        # 使用存储的 user_workspace
        if self.user_workspace.current_conversation:
            self.user_workspace.current_conversation.add_message(message)
            logger.debug(
                f"Message added to conversation {self.user_workspace.current_conversation.id}",
            )
        else:
            logger.warning(
                f"No current conversation found for task {task_node_id}, message not added.",
            )

    def _convert_tools_to_openai_format(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """转换工具为 OpenAI 格式

        Args:
            tools: 工具列表

        Returns:
            OpenAI 格式的工具列表

        Raises:
            TypeError: tools 不是列表或工具项不是字典
            ValueError: 工具缺少必要字段

        """
        if not isinstance(tools, list):
            raise TypeError(f"tools must be a list, got {type(tools)}")

        logger.debug(f"Converting {len(tools)} tools to OpenAI format")

        # 工具格式转换实现
        openai_tools = []

        for tool in tools:
            if not isinstance(tool, dict):
                raise TypeError(f"tool must be dict, got {type(tool)}")

            # 规范化 parameters：严格校验的提供商（Deepseek/GLM）要求 function 的
            # parameters 必须是 type="object" 的 JSON Schema；空 dict 或缺 type 会报
            # 400 "got 'type: null'"。这里兜底：确保总是 type=object，并保留原 properties/required。
            raw_params = tool.get("parameters")
            if isinstance(raw_params, dict) and raw_params:
                params = {
                    "type": "object",
                    "properties": raw_params.get("properties", {}),
                    "required": raw_params.get("required", []),
                }
                # 保留其他已知合法字段
                for extra in ("additionalProperties", "description", "$schema"):
                    if extra in raw_params:
                        params[extra] = raw_params[extra]
            else:
                params = {"type": "object", "properties": {}, "required": []}

            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": params,
                },
            }
            openai_tools.append(openai_tool)

        logger.debug(f"Tools converted successfully: {len(openai_tools)} OpenAI tools")
        return openai_tools

    def validate_message(self, message: dict[str, Any]) -> bool:
        """验证消息格式

        Args:
            message: 消息字典

        Returns:
            是否有效

        Raises:
            TypeError: message 不是字典类型

        """
        if not isinstance(message, dict):
            raise TypeError(f"message must be dict, got {type(message)}")

        # 基本的消息格式验证
        if "role" not in message:
            logger.warning("Message missing 'role' field")
            return False

        if "content" not in message:
            logger.warning("Message missing 'content' field")
            return False

        valid_roles = ["system", "user", "assistant", "tool"]
        if message["role"] not in valid_roles:
            logger.warning(f"Invalid message role: {message['role']}")
            return False

        logger.debug(f"Message validation passed for role: {message['role']}")
        return True

    def format_system_prompt(self, base_prompt: str, context: dict[str, Any]) -> str:
        """格式化系统提示

        Args:
            base_prompt: 基础提示
            context: 上下文信息

        Returns:
            格式化后的系统提示

        Raises:
            TypeError: base_prompt 不是字符串或 context 不是字典
            ValueError: context 包含无法转换的值

        """
        if not isinstance(base_prompt, str):
            raise TypeError(f"base_prompt must be string, got {type(base_prompt)}")

        if not isinstance(context, dict):
            raise TypeError(f"context must be dict, got {type(context)}")

        logger.debug("Formatting system prompt")

        # 简单的字符串替换
        formatted_prompt = base_prompt
        for key, value in context.items():
            placeholder = f"{{{key}}}"
            if placeholder in formatted_prompt:
                try:
                    str_value = str(value)
                except Exception as e:
                    raise ValueError(f"Cannot convert context value for key '{key}' to string: {e}")
                formatted_prompt = formatted_prompt.replace(placeholder, str_value)

        logger.debug("System prompt formatted successfully")
        return formatted_prompt

    async def _get_available_tools(self, user_workspace):
        """获取可用工具（mode-工具解耦 D8：装配与 mode 无关）

        Args:
            user_workspace: 用户工作空间实例

        Returns:
            List[Dict]: 工具列表

        Raises:
            AttributeError: user_workspace 缺少必要方法或属性

        """
        if user_workspace is None:
            raise AttributeError("user_workspace cannot be None")

        if not hasattr(user_workspace, "allowed_tools"):
            raise AttributeError("user_workspace missing 'allowed_tools' property")

        # mode-工具解耦（D8）：装配与 mode 无关——安装了什么（tool_manager +
        # skills + 已连接 MCP 一级工具），过 workspace settings 门控即所得。
        # mode 是纯 prompt 人设，不参与工具装配。
        return list(user_workspace.allowed_tools or [])

    # ========================================================================
    # Progressive Tool Disclosure 集成
    # ========================================================================

    async def _get_tools_for_llm(self, user_workspace) -> list[dict[str, Any]]:
        """返回注入 LLM 的工具 schema 列表（mode-工具解耦后的唯一装配路径）。

        流程：
        1. 安装面（mode 无关）→ _get_available_tools（tool_manager + skills + MCP 动态）
        2. SessionToolPool 过滤（渐进式披露）→ 只保留 Tier-0 CORE + 已激活工具
        3. Schema 压缩 → SchemaCompressor

        如果 SessionToolPool 不存在，回退到原有行为（全量注入）。
        CORE_TOOLS 恒在 → 空列表结构性不可能（消费方对 tools=[] 一律 FAST FAIL）。

        Args:
            user_workspace: 用户工作空间实例

        Returns:
            OpenAI 格式 + 压缩后的工具 schema 列表
        """
        # 1. 安装面（无 mode 参与）
        installed_tools = await self._get_available_tools(user_workspace)

        # 2. 转换为 OpenAI 格式
        openai_tools = self._convert_tools_to_openai_format(installed_tools)

        # 3. SessionToolPool 过滤（渐进式披露）
        pool = self._get_or_create_session_pool(user_workspace)
        if pool is not None:
            active = pool.get_active_tools()
            before = len(openai_tools)
            # mcp__ 前缀 = 一级 MCP 工具，视同 Tier-0 常驻（与 list_files
            # 同级默认可见，不依赖 search_tools 激活）
            openai_tools = [
                t
                for t in openai_tools
                if t.get("function", {}).get("name", "") in active
                or t.get("function", {}).get("name", "").startswith("mcp__")
            ]
            after = len(openai_tools)
            logger.info(f"[PROGRESSIVE_DISCLOSURE] Pool filter: {before} → {after} tools (active: {len(active)})")

            # 4. Schema 压缩（可配置）
            try:
                from dawei.config.settings import get_settings as _get_cfg

                _cfg = _get_cfg()
                _ptd = getattr(_cfg, "progressive_tool_disclosure", None)
                _compress_enabled = getattr(_ptd, "schema_compression", True) if _ptd else True
            except Exception:
                _compress_enabled = True

            if _compress_enabled:
                from dawei.tools.tool_discovery.schema_compressor import SchemaCompressor

                openai_tools = [SchemaCompressor.compress(t) for t in openai_tools]

        # 一级 MCP 工具增量入 ToolIndex（server 可能在会话中途连上,而索引
        # 一次成型 → 晚到的 mcp__ 工具 search_tools 永远搜不到;每请求 diff,
        # 稳定后空转）
        self._sync_mcp_tools_to_index(user_workspace, installed_tools)

        return openai_tools

    def _sync_mcp_tools_to_index(self, user_workspace, installed_tools: list[dict[str, Any]]) -> None:
        """把当前工具面的 mcp__ 工具增量注册进 ToolIndex（FAST FAIL,失败可见）。"""
        try:
            index = getattr(user_workspace, "_tool_index", None)
            if index is None:
                return
            current = {t["name"]: t for t in installed_tools if str(t.get("name", "")).startswith("mcp__")}
            if not current:
                return
            seen = getattr(user_workspace, "_tool_index_mcp_seen", None)
            if seen is None:
                seen = set()
                user_workspace._tool_index_mcp_seen = seen
            fresh = [name for name in current if name not in seen]
            if not fresh:
                return
            for name in fresh:
                desc = str(current[name].get("description") or name)
                index.register(
                    name=name,
                    description=desc,
                    brief_desc=desc[:80],
                    keywords=set(name.replace("__", " ").replace("-", " ").split()),
                    group="mcp",
                )
                seen.add(name)
            logger.info(f"[PROGRESSIVE_DISCLOSURE] ToolIndex +{len(fresh)} first-class MCP tools (total mcp={len(seen)})")
        except Exception:
            logger.warning("register first-class MCP tools into ToolIndex failed", exc_info=True)

    def _get_or_create_session_pool(self, user_workspace):
        """获取或创建 SessionToolPool。

        Pool 存储在 user_workspace._session_tool_pool 上（per-session 生命周期）。
        首次调用时按当前 mode 初始化 CORE_TOOLS + MODE_CORE_OVERRIDES。
        模式切换时自动更新 core tools（保留已激活的 Tier-1 工具）。

        Args:
            user_workspace: 用户工作空间

        Returns:
            SessionToolPool 实例，或 None（如果渐进式披露未启用）
        """
        # 获取当前 mode
        workspace_info = getattr(user_workspace, "workspace_info", None)
        current_mode = "orchestrator"
        if workspace_info is not None:
            user_ui_context = getattr(workspace_info, "user_ui_context", None)
            if user_ui_context is not None:
                current_mode = getattr(user_ui_context, "current_mode", None) or "orchestrator"

        existing = getattr(user_workspace, "_session_tool_pool", None)
        existing_mode = getattr(user_workspace, "_session_tool_pool_mode", None)

        # Pool 已存在且 mode 未变 → 直接返回
        if existing is not None and existing_mode == current_mode:
            return existing

        # Pool 已存在但 mode 变了 → 更新 core tools（保留已激活的 Tier-1）
        if existing is not None and existing_mode != current_mode:
            from dawei.tools.tool_discovery.core_tools import get_core_tools_for_mode

            new_core = get_core_tools_for_mode(current_mode)
            existing._core = new_core  # 更新 core，保留 _activated
            user_workspace._session_tool_pool_mode = current_mode
            logger.info(
                f"[PROGRESSIVE_DISCLOSURE] SessionToolPool mode changed: '{existing_mode}' → '{current_mode}', "
                f"core={len(new_core)} tools, activated={len(existing._activated)} preserved"
            )
            return existing

        # 检查是否启用渐进式披露
        try:
            from dawei.config.settings import get_settings

            settings = get_settings()
            enabled = getattr(settings, "progressive_tool_disclosure", None)
            if enabled is not None and not getattr(enabled, "enabled", True):
                return None
        except Exception as e:  # noqa: BLE001 — 配置不可用按默认启用,但必须可见
            logger.warning(f"progressive disclosure config unavailable, defaulting enabled: {e}")

        # 创建 pool
        from dawei.tools.tool_discovery.core_tools import get_core_tools_for_mode

        core_tools = get_core_tools_for_mode(current_mode)

        from dawei.tools.tool_discovery.session_pool import SessionToolPool

        pool = SessionToolPool(core_tools)
        user_workspace._session_tool_pool = pool
        user_workspace._session_tool_pool_mode = current_mode
        logger.info(f"[PROGRESSIVE_DISCLOSURE] SessionToolPool created for mode='{current_mode}', core={len(core_tools)} tools")

        # 同时初始化 ToolIndex
        self._init_tool_index(user_workspace, pool, current_mode)

        return pool

    def _init_tool_index(self, user_workspace, pool, current_mode: str) -> None:
        """初始化 ToolIndex 并注册所有可用工具。

        Args:
            user_workspace: 用户工作空间
            pool: SessionToolPool 实例
            current_mode: 当前模式
        """
        existing = getattr(user_workspace, "_tool_index", None)
        if existing is not None:
            return

        from dawei.tools.tool_discovery.tool_index import ToolIndex

        index = ToolIndex()

        # 从静态目录注册
        try:
            from dawei.tools.tool_catalog import get_catalog

            for entry in get_catalog():
                index.register(
                    name=entry.name,
                    description=entry.short_desc,
                    brief_desc=entry.short_desc,
                    keywords=set(entry.keywords),
                    group=entry.group,
                )
        except Exception as e:  # noqa: BLE001 — 静态目录缺失只降级搜索,失败可见
            logger.warning(f"Could not load tool_catalog entries: {e}")

        # 从 tool_executor 动态注册（如果可用）
        try:
            tool_executor = getattr(user_workspace, "tool_executor", None)
            if tool_executor is None:
                # 尝试从 agent 获取
                agent = getattr(user_workspace, "_agent", None)
                if agent is not None:
                    tool_executor = getattr(agent, "tool_call_service", None) or getattr(agent, "tool_executor", None)
            if tool_executor is not None:
                tools_dict = getattr(tool_executor, "tools", {})
                for name, tool_instance in tools_dict.items():
                    if name not in pool.get_active_tools():  # 只注册非核心工具
                        index.register_from_tool(tool_instance)
        except Exception as e:  # noqa: BLE001 — 动态注册失败只降级搜索,失败可见
            logger.warning(f"Could not register tools from tool_executor: {e}")

        user_workspace._tool_index = index
        logger.info(f"[PROGRESSIVE_DISCLOSURE] ToolIndex initialized with {len(index.list_all())} entries")

    def _inject_tools_hint(self, system_content: str, pool, bound_tool_count: int) -> str:
        """在系统提示尾部追加工具发现提示。

        Args:
            system_content: 原始系统提示内容
            pool: SessionToolPool 实例
            bound_tool_count: 本轮 LLM 请求实际绑定的工具数（tools= 列表长度）

        Returns:
            追加了工具提示的系统提示内容
        """
        stats = pool.get_stats()
        hint = (
            "\n\n## 工具发现（Progressive Tool Disclosure）\n"
            f"本轮请求实际绑定 **{bound_tool_count}** 个工具"
            f"（工具池：核心 {stats['core_count']} + 会话激活 {stats['activated_count']}）。\n"
            '如果需要的工具不在列表中，先调用 `search_tools(query="...")` 搜索并激活。\n'
            "搜索到的工具将在下一轮对话中自动可用。\n"
            '如果工具结果被截断，使用 `expand_tool_result(snapshot_id="...")` 获取完整数据。'
        )
        return system_content + hint

    def close(self) -> None:
        """关闭构建器，清理资源"""
        if self.template_manager:
            self.template_manager.close()

        logger.info("EnhancedSystemBuilder closed")
