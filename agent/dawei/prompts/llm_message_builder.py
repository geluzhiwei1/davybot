# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""增强的系统构建器

重构后的核心组件，整合原有的 JinjaSystemBuilder 功能，
承担更多核心工作，提供更简洁的接口。
"""

import logging
from datetime import UTC, datetime, timezone
from typing import Any

from dawei.entity.lm_messages import AssistantMessage, ContentBlock, LLMMessage
from dawei.interfaces.message_processor import IMessageProcessor

from .core.template_manager import TemplateManager
from .core.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


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
    ) -> str:
        """构建系统提示词

        Args:
            user_workspace: 用户工作空间
            capabilities: 能力列表
            custom_instructions: 自定义指令
            additional_data: 附加数据

        Returns:
            str: 构建的系统提示词

        """
        # 从 user_workspace.workspace_info.user_ui_context.current_mode 获取当前模式，确保 workspace_info 不为 None
        current_mode = "orchestrator"  # 默认模式 - 通用PDCA协调者
        if user_workspace.workspace_info and hasattr(user_workspace.workspace_info, "user_ui_context") and user_workspace.workspace_info.user_ui_context:
            ui_mode = user_workspace.workspace_info.user_ui_context.current_mode
            logger.info(f"[LLM_MESSAGE_BUILDER] UI context mode: {ui_mode}")
            current_mode = ui_mode or "orchestrator"
        logger.info(f"[LLM_MESSAGE_BUILDER] Final current_mode: {current_mode}")
        # 使用默认 task_node_id 或从其他地方获取
        task_node_id = getattr(user_workspace.current_conversation, "id", "default_task") if user_workspace.current_conversation else "default_task"

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
            user_workspace.current_conversation,
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
            "all_models": mode_manager.get_all_modes(),
        }

        # 合并 additional_data 中的所有键值对到上下文中
        if additional_data:
            context.update(additional_data)

        # 【新增】Plan Mode 工作流状态
        if current_mode == "plan" and additional_data and "plan_workflow" in additional_data:
            plan_workflow = additional_data["plan_workflow"]
            if plan_workflow and hasattr(plan_workflow, "get_template_context"):
                # 获取工作流模板上下文并合并到主上下文
                plan_context = plan_workflow.get_template_context()
                context.update(plan_context)
                logger.debug(f"Added plan workflow context: {list(plan_context.keys())}")

        # 添加模式配置 - 使用 ModeManager 代替 config_manager
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
        from datetime import datetime

        dynamic_content["generation_timestamp"] = datetime.now(UTC).isoformat()

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

        # 规则段落
        sections["rules"] = self._generate_rules_content(context)

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

        # 目标段落
        sections["objective"] = self._generate_objective_content(context)

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

    def _generate_modes_content(self, context: dict[str, Any]) -> str:
        """生成模式内容

        Args:
            context: 渲染上下文

        Returns:
            str: 模式内容

        """
        template_path = "sections/modes.j2"
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

        # 获取模式信息
        mode_manager.get_mode_info(mode)

        # 由于新的 ModeConfig 不再包含 template_overrides 和 language_overrides
        # 直接使用默认模板
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
        # 从 user_workspace.workspace_info.user_ui_context.current_mode 获取当前模式，确保 workspace_info 不为 None
        current_mode = "orchestrator"  # 默认模式 - 通用PDCA协调者
        if user_workspace.workspace_info and hasattr(user_workspace.workspace_info, "user_ui_context") and user_workspace.workspace_info.user_ui_context:
            ui_mode = user_workspace.workspace_info.user_ui_context.current_mode
            logger.info(f"[LLM_MESSAGE_BUILDER] UI context mode: {ui_mode}")
            current_mode = ui_mode or "orchestrator"
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

    async def build_messages(self, user_workspace: Any, capabilities: list[str]) -> dict[str, Any]:
        """构建消息列表

        Args:
            user_workspace: 用户工作区实例
            capabilities: 能力列表

        Returns:
            包含消息和工具的字典

        Raises:
            TemplateRenderError: 系统提示构建失败
            AttributeError: user_workspace 缺少必要属性
            ValueError: 无效的消息格式

        """
        logger.debug(f"Building messages for workspace with capabilities: {capabilities}")

        # 构建消息列表
        messages = []

        # 构建系统提示
        system_prompt = self.build_system_prompt(user_workspace, capabilities)
        messages.append({"role": "system", "content": system_prompt})

        # 添加历史消息
        if (hasattr(user_workspace, "current_conversation") and user_workspace.current_conversation) and hasattr(user_workspace.current_conversation, "messages"):
            conversation_messages = []
            for msg in user_workspace.current_conversation.messages:
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

            messages.extend(compressed_messages)

        # 获取工具
        tools = await self._get_available_tools(user_workspace)

        # 转换工具格式
        openai_tools = self._convert_tools_to_openai_format(tools)

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

        # 应用压缩
        compressed, stats = compressor.compress_conversation(messages)

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

            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
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
        """获取可用工具

        Args:
            user_workspace: 用户工作空间实例

        Returns:
            List[Dict]: 工具列表

        Raises:
            AttributeError: user_workspace 缺少必要方法或属性
            ValueError: 无法获取当前模式

        """
        if user_workspace is None:
            raise AttributeError("user_workspace cannot be None")

        if not hasattr(user_workspace, "get_mode_available_tools"):
            raise AttributeError("user_workspace missing 'get_mode_available_tools' method")

        workspace_info = getattr(user_workspace, "workspace_info", None)
        if workspace_info is None:
            current_mode = "orchestrator"
        else:
            user_ui_context = getattr(workspace_info, "user_ui_context", None)
            current_mode = "orchestrator" if user_ui_context is None else user_ui_context.current_mode or "orchestrator"

        # 添加诊断日志
        logger.debug(f"Getting available tools for mode: {current_mode}")
        logger.debug(f"Tool manager available: {hasattr(user_workspace, 'tool_manager')}")
        logger.debug(f"Tool manager value: {getattr(user_workspace, 'tool_manager', 'NOT_FOUND')}")

        tools_dict = user_workspace.get_mode_available_tools(current_mode)
        if tools_dict is None:
            logger.warning("get_mode_available_tools returned None, using empty list")
            return []

        return tools_dict.get("tools", [])

    def close(self) -> None:
        """关闭构建器，清理资源"""
        if self.template_manager:
            self.template_manager.close()

        logger.info("EnhancedSystemBuilder closed")
