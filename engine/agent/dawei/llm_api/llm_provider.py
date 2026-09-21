# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM Provider 简化管理器 (KISS Principle)
从1062行简化为目标 <800行
移除复杂的缓存逻辑，简化配置加载

重构说明：
- 移除 LLMConfigLoader 类（复杂缓存逻辑）
- 从2层简化为直接加载：user + workspace
- 使用 functools.lru_cache 替代手动缓存（如需要）
- Fast Fail: 配置错误立即抛出异常
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import List, Dict, Any

from dawei import get_dawei_home
from dawei.core.exceptions import ConfigurationError
from dawei.entity.llm_config import LLMConfig, LLMProviderConfig
from dawei.entity.lm_messages import LLMMessage
from dawei.entity.stream_message import (
    CompleteMessage,
    ContentMessage,
    ReasoningMessage,
    StreamMessages,
    ToolCallMessage,
    UsageMessage,
)
from dawei.interfaces.llm_service import ILLMService

from .base_llm_api import LlmApi

# 从 provider 子模块导入拆分的组件
from .provider import LLMClientFactory, ParserCache, StreamState

logger = logging.getLogger(__name__)


def _load_settings_file(settings_file: Path, source: str) -> Dict[str, LLMProviderConfig]:
    """加载 settings.json 文件（简化版）

    Args:
        settings_file: 配置文件路径
        source: 来源 (user/workspace)

    Returns:
        LLM配置字典

    Raises:
        RuntimeError: 如果文件存在但加载失败

    """
    if not settings_file.exists():
        logger.debug(f"Settings file not found: {settings_file}")
        return {}, {}

    try:
        with Path(settings_file).open(encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, PermissionError, OSError) as e:
        # Fast Fail: 文件存在但无法读取
        logger.error(f"Failed to load settings from {settings_file}: {e}", exc_info=True)
        raise RuntimeError(f"Cannot load LLM settings: {e}")

    # 加载全局代理配置（从 globalSettings）
    global_proxy_config = {}
    if data and "globalSettings" in data:
        global_settings = data.get("globalSettings", {})
        global_proxy_config = {
            "httpProxy": global_settings.get("httpProxy", ""),
            "httpsProxy": global_settings.get("httpsProxy", ""),
            "noProxy": global_settings.get("noProxy", ""),
        }
        if any(global_proxy_config.values()):
            logger.info(f"Loaded proxy config from globalSettings: {global_proxy_config}")

    configs = {}
    if data and "providerProfiles" in data:
        provider_profiles = data["providerProfiles"]
        api_configs = provider_profiles.get("apiConfigs", {})
        current_config_name = provider_profiles.get("currentApiConfigName")
        mode_api_configs = provider_profiles.get("modeApiConfigs", {})

        for config_name, config_data in api_configs.items():
            # 合并全局代理配置到每个 LLM 配置
            # 如果 LLM 配置本身没有设置代理，则使用全局代理
            merged_config = {**config_data}
            if global_proxy_config and not config_data.get("httpProxy"):
                merged_config.update(global_proxy_config)

            llm_config = LLMConfig.from_dict(merged_config)
            provider_config = LLMProviderConfig(
                name=config_name,
                config=llm_config,
                source=source,
                is_default=(config_name == current_config_name),
                raw_config=merged_config,  # 保存合并后的完整配置
            )
            configs[config_name] = provider_config

        logger.debug(f"Loaded {len(configs)} LLM configs from {settings_file}")

    return configs, mode_api_configs


def _safe_uid(user_id: str | None) -> str:
    """user_id → 安全的目录名（对齐 security 的 sanitization）。"""
    uid = user_id or "default_user"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in uid)


def _load_user_llm_configs(
    user_id: str = "default_user",
) -> tuple[Dict[str, LLMProviderConfig], Dict[str, str]]:
    """加载用户级LLM配置（per-user：configs/{user_id}/settings.json，不迁移旧全局文件）。

    Returns:
        (配置字典, 模式配置字典)

    """
    settings_file = get_dawei_home() / "configs" / _safe_uid(user_id) / "settings.json"
    configs, mode_configs = _load_settings_file(settings_file, "user")
    logger.info(f"Loaded {len(configs)} user LLM configs (user={user_id})")
    return configs, mode_configs


def _load_workspace_llm_configs(
    workspace_root: str,
) -> tuple[Dict[str, LLMProviderConfig], Dict[str, str]]:
    """加载工作区级LLM配置

    Args:
        workspace_root: 工作区路径

    Returns:
        (配置字典, 模式配置字典)

    """
    workspace_dir = Path(workspace_root)
    settings_file = workspace_dir / ".dawei" / "settings.json"
    configs, mode_configs = _load_settings_file(settings_file, "workspace")
    logger.info(f"Loaded {len(configs)} workspace LLM configs")
    return configs, mode_configs


class LLMProvider(ILLMService):
    """简化的LLM管理器 (KISS Principle)

    2层配置加载：user + workspace
    移除复杂的缓存逻辑
    Fast Fail: 配置错误立即抛出异常

    """

    def __init__(self, workspace_root: str | None = None, user_id: str = "default_user"):
        """初始化 LLM 管理器

        Args:
            workspace_root: 工作区路径（必需）
            user_id: 用户 ID（多租户：决定加载哪个用户的用户级 LLM 配置）

        Raises:
            RuntimeError: 如果必需的配置加载失败
            ValueError: 如果 workspace_root 未提供

        """
        if not workspace_root:
            raise ValueError("workspace_root is required for LLMProvider")
        self.workspace_root = workspace_root
        self.user_id = user_id or "default_user"

        # 配置字典
        self._configs: Dict[str, LLMProviderConfig] = {}
        self._current_config_name: str | None = None

        # 模式特定的 LLM 配置
        self._mode_llm_configs: Dict[str, str] = {}

        # 活跃的 LLM 客户端实例列表，用于清理
        self._active_llm_clients: List[LlmApi] = []

        # Gateway 用户认证 token（从前端透传）
        self._gateway_auth_token: str | None = None

        # StreamState 和 ParserCache 实例
        self._stream_state: StreamState = StreamState()
        self._parser_cache: ParserCache = ParserCache()

        # 一次性加载所有配置
        self._load_all_configs()

    def _load_all_configs(self):
        """一次性加载所有配置（2层）"""
        # 1. 加载用户配置（per-user）
        try:
            user_configs, user_mode_configs = _load_user_llm_configs(self.user_id)
            self._configs.update(user_configs)
            self._mode_llm_configs.update(user_mode_configs)
        except Exception as e:
            # Fast Fail: 用户配置加载失败应立即抛出
            logger.error(f"Failed to load user LLM configs: {e}", exc_info=True)
            raise RuntimeError(f"Cannot load user LLM configs: {e}")

        # 2. 如果有工作区，应用工作区覆盖（简单更新）
        if self.workspace_root:
            try:
                workspace_configs, workspace_mode_configs = _load_workspace_llm_configs(self.workspace_root)
                override_count = 0
                for name, config in workspace_configs.items():
                    if name in self._configs:
                        override_count += 1
                        logger.debug(f"Overriding LLM config '{name}' with workspace config")
                    self._configs[name] = config

                self._mode_llm_configs.update(workspace_mode_configs)
                logger.info(
                    f"Applied {len(workspace_configs)} workspace LLM configs ({override_count} overrides)",
                )
            except Exception as e:
                # 工作区配置加载失败不应阻止系统启动
                logger.warning(f"Failed to load workspace LLM configs (continuing): {e}")

        # 3. 设置当前配置
        self._set_current_config()

        logger.info(f"LLMProvider initialized with {len(self._configs)} total configs")

    def _set_current_config(self):
        """设置当前配置"""
        # 优先查找标记为默认的配置
        for name, config in self._configs.items():
            if config.is_default:
                self._current_config_name = name
                logger.info(f"Set current LLM config to default: {name}")
                return

        # 如果没有默认配置，使用第一个配置
        if self._configs:
            self._current_config_name = next(iter(self._configs))
            logger.info(f"Set current LLM config to first available: {self._current_config_name}")
        else:
            logger.warning("No LLM configurations available")

    # 实现 ILLMService 接口的方法
    def get_available_providers(self) -> List[str]:
        """获取可用的 LLM 提供者列表（实现 ILLMService 接口）

        Returns:
            提供者名称列表

        """
        config_names = self.get_config_names()
        logger.debug(f"Available providers: {config_names}")
        return config_names

    def get_current_provider(self) -> str | None:
        """获取当前 LLM 提供者（实现 ILLMService 接口）

        Returns:
            当前提供者名称

        """
        current_config = self.get_current_config_name()
        logger.debug(f"Current provider: {current_config}")
        return current_config

    def set_provider(self, provider_name: str) -> bool:
        """设置 LLM 提供者（实现 ILLMService 接口）

        Args:
            provider_name: 配置名称 (e.g., "my-openai-config")

        Returns:
            是否设置成功

        """
        logger.debug(f"Setting provider to: {provider_name}")

        success = self.set_current_config(provider_name)

        if success:
            logger.info(f"Provider set successfully to: {provider_name}")
        else:
            logger.warning(f"Failed to set provider to: {provider_name}")

        return success

    def get_provider_config(self, provider_name: str) -> Dict[str, Any] | None:
        """获取提供者配置（实现 ILLMService 接口）

        Args:
            provider_name: 提供者名称

        Returns:
            提供者配置字典

        """
        config = self.get_llm_config_by_name(provider_name)
        logger.debug(f"Retrieved config for provider: {provider_name}")
        return config

    def update_provider_config(self, provider_name: str, config: Dict[str, Any]) -> bool:
        """更新提供者配置（实现 ILLMService 接口）

        Args:
            provider_name: 提供者名称
            config: 新配置

        Returns:
            是否更新成功

        """
        logger.debug(f"Updating config for provider: {provider_name}")

        # 获取现有配置
        existing_config = self.get_config(provider_name)
        if not existing_config:
            logger.warning(f"Provider not found: {provider_name}")
            return False

        # 更新配置
        updated_llm_config = LLMConfig.from_dict(config)

        # 移除旧配置并添加新配置
        self.remove_config(provider_name)
        success = self.add_config(
            provider_name,
            updated_llm_config,
            existing_config.source,
            existing_config.is_default,
        )

        if success:
            logger.info(f"Provider config updated successfully: {provider_name}")
        else:
            logger.warning(f"Failed to update provider config: {provider_name}")

        return success

    def get_model_info(self, provider_name: str | None = None) -> Dict[str, Any]:
        """获取模型信息（实现 ILLMService 接口）

        Args:
            provider_name: 提供者名称，为 None 时使用当前提供者

        Returns:
            模型信息字典

        """
        config = self.get_llm_config_by_name(provider_name) if provider_name else self.get_default_llm_config()

        if not config:
            return {"error": "Provider not found"}

        model_info = {
            "provider_name": provider_name or self.get_current_provider(),
            "model_id": config.get("model_id", ""),
            "api_provider": config.get("apiProvider", ""),
            "base_url": config.get("base_url", ""),
            "max_tokens": config.get("max_tokens", -1),
            "context_window": config.get("context_window", 128000),
            "supports_images": config.get("supports_images", False),
            "supports_prompt_cache": config.get("supports_prompt_cache", False),
            "input_price": config.get("input_price", 0.0),
            "output_price": config.get("output_price", 0.0),
            "reasoning_effort": config.get("reasoning_effort"),
        }

        logger.debug(f"Retrieved model info for: {model_info['provider_name']}")
        return model_info

    async def test_connection(self, provider_name: str | None = None) -> bool:
        """测试提供者连接（实现 ILLMService 接口）

        Args:
            provider_name: 提供者名称，为 None 时使用当前提供者

        Returns:
            是否连接成功

        """
        logger.debug(f"Testing connection for provider: {provider_name or 'current'}")

        # 创建 LLM 实例
        llm_instance = self.create_llm_provider(provider_name) if provider_name else self.get_default_llm_provider()

        if not llm_instance:
            logger.error("No LLM instance available for connection test")
            return False

        # 尝试简单的连接测试
        # 这里可以发送一个简单的测试消息
        test_messages = [{"role": "user", "content": "test"}]

        # 尝试获取响应（不等待完整流）
        stream_response = await llm_instance.astream_chat_completion(
            messages=test_messages,
            max_tokens=1,
        )

        # 尝试获取第一个块
        async for _chunk in stream_response:
            # 如果能获取到任何响应，说明连接成功
            logger.info("Connection test successful")
            return True

        logger.info("Connection test completed")
        return True

    # 将 InternalStreamManager 的功能直接合并到 LLMProvider 中
    # 移除 _get_stream_manager 方法，直接在 LLMProvider 中管理 StreamState 和 ParserCache

    async def process_message(self, messages: List[LLMMessage], **kwargs) -> Dict[str, Any]:
        """处理消息并返回完整结果（实现 ILLMService 接口）

        Args:
            messages: 消息列表
            **kwargs: 其他参数（如 tools、temperature 等）

        Returns:
            包含完整内容和工具调用的字典

        """
        logger.debug(f"Processing message with {len(messages)} messages")

        # 获取默认的 LLM 提供者实例
        llm_instance = self.get_default_llm_provider()

        if not llm_instance:
            raise RuntimeError("No LLM provider available")

        self._stream_state.reset()
        self._stream_state.is_processing = True
        self._stream_state.is_streaming = True

        full_content = ""
        all_tool_calls = []

        # 调用 LLM 实例的流式方法
        stream_response = llm_instance.astream_chat_completion(messages=messages, **kwargs)

        async for message in stream_response:
            # stream_response 已经是解析后的 StreamMessages 对象，无需再次解析
            if isinstance(message, ContentMessage):
                full_content += message.content
            elif isinstance(message, ToolCallMessage):
                all_tool_calls = message.all_tool_calls
            elif isinstance(message, UsageMessage):
                self._stream_state.token_usage = message.data
            elif isinstance(message, CompleteMessage):
                break

        self._stream_state.current_content = full_content
        self._stream_state.current_tool_calls = {tc.tool_call_id: tc for tc in all_tool_calls}

        result = {
            "content": full_content or None,
            "tool_calls": all_tool_calls or None,
        }

        self._stream_state.is_processing = False
        self._stream_state.is_streaming = False

        logger.debug("Message processed successfully")
        return result

    async def complete(self, messages: List[LLMMessage], **kwargs) -> Dict[str, Any]:
        """非流式处理消息，直接返回完整结果（实现 ILLMService 接口）

        适用于批处理、知识图谱构建等不需要流式输出的场景。
        不涉及 StreamState，不产生流式拼接开销。

        Args:
            messages: 消息列表
            **kwargs: 其他参数（如 tools、temperature 等）

        Returns:
            包含完整内容和工具调用的字典

        """
        logger.debug(f"Non-streaming complete with {len(messages)} messages")

        llm_instance = self.get_default_llm_provider()
        if not llm_instance:
            raise RuntimeError("No LLM provider available")

        # 优先使用底层客户端的 chat_completion 方法（非流式）
        if hasattr(llm_instance, "chat_completion"):
            result = await llm_instance.chat_completion(messages=messages, **kwargs)
            logger.debug("Non-streaming complete succeeded")
            return result

        # fallback: 如果底层客户端没有 chat_completion，退化为流式收集
        logger.warning("LLM client has no chat_completion(), falling back to streaming")
        return await self.process_message(messages, **kwargs)

    async def create_message_with_callback(
        self,
        messages: List[LLMMessage],
        callback: Callable[[StreamMessages], Awaitable[None]],
        **kwargs,
    ) -> Dict[str, Any]:
        """创建消息并通过回调函数处理流式响应（实现 ILLMService 接口）

        Args:
            messages: 消息列表
            callback: 流式消息回调函数
            **kwargs: 其他参数（如 tools、temperature 等）

        Returns:
            包含完整内容和工具调用的字典

        """
        logger.debug(f"Creating message with callback for {len(messages)} messages")

        # 获取默认的 LLM 提供者实例
        llm_instance = self.get_default_llm_provider()

        if not llm_instance:
            raise RuntimeError("No LLM provider available")

        self._stream_state.reset()
        self._stream_state.is_processing = True
        self._stream_state.is_streaming = True

        full_content = ""
        full_reasoning = ""
        all_tool_calls = []
        saw_complete = False

        # 调用 LLM 实例的流式方法
        stream_response = llm_instance.astream_chat_completion(messages=messages, **kwargs)

        async for message in stream_response:
            # stream_response 已经是解析后的 StreamMessages 对象，无需再次解析
            await callback(message)

            if isinstance(message, ContentMessage):
                full_content += message.content
                self._stream_state.current_content = full_content

                # 注意：不需要在这里发射事件，因为task_node_executor已经发射了CONTENT_STREAM事件
                # 避免重复发射导致TUI显示重复内容
            elif isinstance(message, ToolCallMessage):
                all_tool_calls = message.all_tool_calls
                for tool_call_obj in all_tool_calls:
                    self._stream_state.current_tool_calls[tool_call_obj.tool_call_id] = tool_call_obj
            elif isinstance(message, UsageMessage):
                self._stream_state.token_usage = message.data
            elif isinstance(message, ReasoningMessage):
                full_reasoning += message.content
            elif isinstance(message, CompleteMessage):
                saw_complete = True
                break

        # 【关键修复】流式响应被截断时（未收到 CompleteMessage，如网络中断/超时），
        # 合成兜底完成消息，确保最终 AssistantMessage 仍会被持久化，
        # 避免任务结束时无最终回复、UI 显示"已停止"
        if not saw_complete:
            logger.warning(
                "LLM stream ended without CompleteMessage (truncated?), synthesizing fallback: "
                "content=%d chars, reasoning=%d chars, tool_calls=%d",
                len(full_content),
                len(full_reasoning),
                len(all_tool_calls),
            )
            await callback(
                CompleteMessage(
                    reasoning_content=full_reasoning or None,
                    content=full_content or None,
                    tool_calls=all_tool_calls,
                    finish_reason="stopped",
                )
            )

        result = {
            "content": full_content or None,
            "tool_calls": all_tool_calls or None,
        }

        self._stream_state.is_processing = False
        self._stream_state.is_streaming = False

        return result

    # 原有的方法保持不变
    def set_workspace_root(self, workspace_root: str):
        """设置工作区路径并重新加载配置"""
        self.workspace_root = workspace_root
        # 重新加载配置
        self._configs.clear()
        self._mode_llm_configs.clear()
        self._load_all_configs()
        logger.info(f"Workspace root set to {workspace_root}, LLM configs reloaded")

    def get_all_configs(self) -> Dict[str, LLMProviderConfig]:
        """获取所有可用的 LLM 配置"""
        return self._configs.copy()

    def get_config(self, config_name: str) -> LLMProviderConfig | None:
        """获取指定名称的 LLM 配置"""
        return self._configs.get(config_name)

    def get_current_config(self) -> LLMProviderConfig | None:
        """获取当前 LLM 配置"""
        if self._current_config_name:
            return self._configs.get(self._current_config_name)
        return None

    def set_current_config(self, config_name: str) -> bool:
        """设置当前 LLM 配置

        config_name 由调用方按用户 UI 选择明确指定：
        - 本地模型：传 provider 配置名（_configs 的 key，如 local-deekseel-flash）→ 直接命中本地配置
        - 官方模型：传 model id（不在 _configs 中）→ 动态注册到官方网关

        不做任何 model id 反查/猜测，路由由调用方（chat handler 据 current_llm_source）决定。
        WARNING: 此方法是同步的，不能用 await。Gateway 注册使用缓存的 token。
        """
        if config_name not in self._configs:
            # 本地无此配置，尝试动态注册 gateway 模型
            if self._register_gateway_config(config_name):
                self._current_config_name = config_name
                logger.info(f"Set current LLM config to gateway model: {config_name}")
                return True
            logger.error(f"LLM config not found: {config_name}")
            return False

        # 如果已有配置是 gateway 来源，且当前有新的 auth_token，则重新注册以更新 token
        existing = self._configs.get(config_name)
        if existing and getattr(existing, "source", None) == "gateway" and self._gateway_auth_token:
            old_key = existing.raw_config.get("openAiApiKey", "")
            new_key = self._gateway_auth_token
            if old_key != new_key:
                logger.info(f"[GATEWAY] Refreshing gateway config '{config_name}' with updated auth token")
                self._register_gateway_config(config_name)

        self._current_config_name = config_name
        logger.info(f"Set current LLM config to: {config_name}")
        return True

    async def set_current_config_async(self, config_name: str) -> bool:
        """异步版本：支持自动获取 gateway token"""
        if config_name not in self._configs:
            if await self._register_gateway_config_async(config_name):
                self._current_config_name = config_name
                logger.info(f"Set current LLM config to gateway model: {config_name}")
                return True
            logger.error(f"LLM config not found: {config_name}")
            return False

        self._current_config_name = config_name
        logger.info(f"Set current LLM config to: {config_name}")
        return True

    # ==================== P3-0b/F3: 按子任务模型路由（请求级覆盖，用后还原） ====================

    def set_model_override(self, model: str | None, reasoning_effort: str | None = None) -> bool:
        """临时把当前配置切到指定 model（本地配置名或 gateway model id）。

        覆盖共享的 provider 状态，调用方在请求完成后必须调用 clear_model_override()
        还原（task_node_executor.process_message 在 finally 中还原）。
        更推荐使用 model_override() 上下文管理器（异常安全）。

        reasoning_effort 尽力而为：写入目标配置 raw_config 的 reasoning_effort 键，
        clear 时还原由调用方负责（共享 dict 不做深拷贝快照，KISS）。

        Returns:
            model 为空：False（无需覆盖）；覆盖成功：True；model 未知：False（保留原配置）。
        """
        if not model:
            return False
        saved_name = self._current_config_name
        saved_cfg = self.get_current_config()
        if not self.set_current_config(model):
            logger.error(f"set_model_override: unknown model '{model}', keep '{saved_name}'")
            return False
        # 还原信息只保留一层（嵌套覆盖视为调用方错误，FAST FAIL 记日志）
        if getattr(self, "_override_saved", None) is not None:
            logger.warning("set_model_override: previous override not cleared, overwriting restore point")
        self._override_saved = (saved_name, saved_cfg)
        if reasoning_effort:
            raw = getattr(self.get_current_config(), "raw_config", None)
            if isinstance(raw, dict):
                raw["reasoning_effort"] = reasoning_effort
        logger.info(f"set_model_override: '{saved_name}' -> '{model}' (effort={reasoning_effort})")
        return True

    def clear_model_override(self) -> None:
        """还原 set_model_override 的覆盖（幂等）"""
        saved = getattr(self, "_override_saved", None)
        if saved is None:
            return
        saved_name, _saved_cfg = saved
        self._override_saved = None
        if saved_name and saved_name in self._configs:
            self._current_config_name = saved_name
            logger.info(f"clear_model_override: restored '{saved_name}'")
        else:
            logger.warning(f"clear_model_override: saved config '{saved_name}' no longer exists, keep current")

    def model_override(self, model: str | None, reasoning_effort: str | None = None):
        """set/clear_model_override 的异常安全上下文管理器"""
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            applied = self.set_model_override(model, reasoning_effort)
            try:
                yield applied
            finally:
                if applied:
                    self.clear_model_override()

        return _cm()

    def _register_gateway_config(self, model_id: str) -> bool:
        """为系统 gateway 模型动态注册 LLM 配置（同步版本，使用已缓存的 token）。

        当用户选择的模型不在本地配置中时（如 moonshot/kimi-k2-0711-preview），
        自动创建一个指向 fast_llm_gateway 的 OpenAI 兼容配置。
        Gateway 端点: POST {SUPPORT_SYSTEM_URL}/api/v1/llm/chat/completions
        """
        try:
            from dawei.config.settings import get_settings
            from dawei.entity.llm_config import LLMConfig, LLMProviderConfig

            support_url = get_settings().support_system.url.rstrip("/")
            if not support_url:
                # E1 无云端缺省: 未配置 SUPPORT_SYSTEM_URL 时禁用网关注册,
                # 避免拼出相对 base_url "/api/v1/llm" 在 create_client 才炸出难懂的 pydantic 校验错
                logger.error(
                    f"[GATEWAY] SUPPORT_SYSTEM_URL not configured; cannot register gateway model {model_id}"
                )
                return False
            gateway_base_url = f"{support_url}/api/v1/llm"

            # 使用已缓存的 JWT token 作为 gateway 认证
            # OpenaiCompatibleClient 会将其作为 Bearer token 发送给 gateway
            auth_token = self._gateway_auth_token or "gateway-no-auth"

            if auth_token != "gateway-no-auth":
                self._check_jwt_expiry(auth_token)

            raw_config = {
                "apiProvider": "openai",
                "openAiModelId": model_id,
                "openAiBaseUrl": gateway_base_url,
                "openAiApiKey": auth_token,
                # aiohttp 超时必须 > gateway 的 GATEWAY_STREAM_TIMEOUT(300s)，
                # 否则 agent→gateway 的连接会在 gateway→provider 之前断开
                "timeout": 600,
                "openAiCustomModelInfo": {
                    # 2026-09-16 实测网关:缺省 max_tokens 已不再触发 zai 1210(流式/非流式均正常),
                    # 但缺省时 provider 默认输出上限仅 4096(finish_reason=length 截断);
                    # 故显式传模型文档上限 131072(zai 合法区间 [1,131072]),不设人工瓶颈,
                    # 模型自然结束时自行 stop(实测 13599 tokens finish=stop)。
                    "maxTokens": 131072,
                    # openai_compatible 客户端读 snake 键 max_output_tokens(camel 键
                    # 历史上从未被读过=never sent)—— 双键齐写确保真正下传
                    "max_output_tokens": 131072,
                    "contextWindow": 128000,
                },
            }

            llm_config = LLMConfig.from_dict(raw_config)
            provider_config = LLMProviderConfig(
                name=model_id,
                config=llm_config,
                source="gateway",
                is_default=False,
                raw_config=raw_config,
            )

            self._configs[model_id] = provider_config
            logger.info(f"[GATEWAY] Registered gateway LLM config: {model_id} → {gateway_base_url} (auth={'token' if self._gateway_auth_token else 'none'})")
            return True
        except Exception as e:
            logger.warning(f"[GATEWAY] Failed to register gateway config for {model_id}: {e}")
            return False

    async def _register_gateway_config_async(self, model_id: str) -> bool:
        """异步版本：尝试多源获取 token，用于非 WebSocket 路径"""
        try:
            from dawei.config.settings import get_settings
            from dawei.entity.llm_config import LLMConfig, LLMProviderConfig

            support_url = get_settings().support_system.url.rstrip("/")
            if not support_url:
                # E1 无云端缺省: 未配置 SUPPORT_SYSTEM_URL 时禁用网关注册,
                # 避免拼出相对 base_url "/api/v1/llm" 在 create_client 才炸出难懂的 pydantic 校验错
                logger.error(
                    f"[GATEWAY] SUPPORT_SYSTEM_URL not configured; cannot register gateway model {model_id}"
                )
                return False
            gateway_base_url = f"{support_url}/api/v1/llm"

            # 尝试多源获取 token
            auth_token = await self._get_or_refresh_gateway_token()
            if not auth_token:
                logger.warning(f"[GATEWAY] No auth token available for gateway model {model_id}")
                return False

            self._check_jwt_expiry(auth_token)

            raw_config = {
                "apiProvider": "openai",
                "openAiModelId": model_id,
                "openAiBaseUrl": gateway_base_url,
                "openAiApiKey": auth_token,
                # aiohttp 超时必须 > gateway 的 GATEWAY_STREAM_TIMEOUT(300s)，
                # 否则 agent→gateway 的连接会在 gateway→provider 之前断开
                "timeout": 600,
                "openAiCustomModelInfo": {
                    # 2026-09-16 实测网关:缺省 max_tokens 已不再触发 zai 1210(流式/非流式均正常),
                    # 但缺省时 provider 默认输出上限仅 4096(finish_reason=length 截断);
                    # 故显式传模型文档上限 131072(zai 合法区间 [1,131072]),不设人工瓶颈,
                    # 模型自然结束时自行 stop(实测 13599 tokens finish=stop)。
                    "maxTokens": 131072,
                    # openai_compatible 客户端读 snake 键 max_output_tokens(camel 键
                    # 历史上从未被读过=never sent)—— 双键齐写确保真正下传
                    "max_output_tokens": 131072,
                    "contextWindow": 128000,
                },
            }

            llm_config = LLMConfig.from_dict(raw_config)
            provider_config = LLMProviderConfig(
                name=model_id,
                config=llm_config,
                source="gateway",
                is_default=False,
                raw_config=raw_config,
            )

            self._configs[model_id] = provider_config
            logger.info(f"[GATEWAY] Registered gateway LLM config (async): {model_id} → {gateway_base_url}")
            return True
        except Exception as e:
            logger.warning(f"[GATEWAY] Failed to register gateway config for {model_id}: {e}")
            return False

    def set_gateway_token(self, token: str | None) -> None:
        """设置 gateway 用户认证 token（从前端透传）"""
        self._gateway_auth_token = token

    async def _get_or_refresh_gateway_token(self) -> str | None:
        """多源尝试获取 gateway 认证 token

        优先级:
        1. WebSocket 手动设置的 token (set_gateway_token)
        2. local_context 中的 auth_token (适用于后台任务)
        3. 尝试 OAuth client_credentials 获取 system token
        """
        # 1. WebSocket 手动设置的 token
        if self._gateway_auth_token:
            return self._gateway_auth_token

        # 2. 从 local_context 获取
        try:
            from dawei.core import local_context
            ctx_token = local_context.get("auth_token")
            if ctx_token:
                return ctx_token
        except Exception:
            pass

        # 3. 尝试 OAuth client_credentials system token
        try:
            return await self._acquire_system_token()
        except Exception:
            pass

        return None

    async def _acquire_system_token(self) -> str | None:
        """通过 OAuth client_credentials 获取系统级 token (无用户上下文)"""
        from dawei.config.settings import get_settings
        import httpx

        settings = get_settings()
        support_url = settings.support_system.url.rstrip("/")
        token_url = f"{support_url}/api/oauth/token"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": settings.support_system.oauth_client_id,
                        "client_secret": settings.support_system.oauth_client_secret,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    token = data.get("access_token")
                    if token:
                        self._gateway_auth_token = token
                        logger.info("[GATEWAY] Acquired system token via client_credentials")
                        return token
        except Exception as e:
            logger.debug(f"[GATEWAY] Failed to acquire system token: {e}")
        return None

    def _check_jwt_expiry(self, token: str) -> None:
        """检查 JWT token 是否即将过期，提前告警"""
        import base64
        import json
        import time

        try:
            parts = token.split(".")
            if len(parts) < 3:
                return
            # URL-safe base64 解码 payload
            payload_b64 = parts[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = payload.get("exp", 0)
            if exp:
                remaining = exp - time.time()
                if remaining < 300:
                    logger.warning(
                        f"[GATEWAY] JWT token expires in {int(remaining)}s — "
                        "LLM requests may fail soon for long-running tasks"
                    )
                elif remaining < 600:
                    logger.info(
                        f"[GATEWAY] JWT token expires in {int(remaining/60)}min"
                    )
        except Exception:
            pass

    def get_current_config_name(self) -> str | None:
        """获取当前配置名称"""
        return self._current_config_name

    def get_config_names(self) -> List[str]:
        """获取所有配置名称"""
        return list(self._configs.keys())

    def get_config_by_provider(self, provider: str) -> List[LLMProviderConfig]:
        """根据提供商类型获取配置"""
        configs = []
        for config in self._configs.values():
            if config.config.apiProvider == provider:
                configs.append(config)
        return configs

    def get_mode_config(self, mode: str) -> LLMProviderConfig | None:
        """获取模式特定的 LLM 配置"""
        # 首先检查是否有模式特定的配置
        if mode in self._mode_llm_configs:
            mode_config_name = self._mode_llm_configs[mode]
            if mode_config_name in self._configs:
                return self._configs[mode_config_name]

        # 如果没有模式特定配置，返回当前配置
        return self.get_current_config()

    def set_mode_config(self, mode: str, config_name: str) -> bool:
        """设置模式特定的 LLM 配置"""
        if config_name not in self._configs:
            logger.error(f"LLM config not found for mode {mode}: {config_name}")
            return False

        self._mode_llm_configs[mode] = config_name
        logger.info(f"Set LLM config for mode {mode}: {config_name}")
        return True

    def get_mode_configs(self) -> Dict[str, str]:
        """获取所有模式特定的配置"""
        return self._mode_llm_configs.copy()

    def add_config(
        self,
        config_name: str,
        llm_config: LLMConfig,
        source: str = "user",
        is_default: bool = False,
    ) -> bool:
        """添加新的 LLM 配置"""
        provider_config = LLMProviderConfig(
            name=config_name,
            config=llm_config,
            source=source,
            is_default=is_default,
        )

        # 添加到配置字典
        self._configs[config_name] = provider_config

        # 如果设置为默认，更新当前配置
        if is_default:
            self._current_config_name = config_name

        logger.info(f"Added LLM config: {config_name} from {source}")
        return True

    def remove_config(self, config_name: str) -> bool:
        """移除 LLM 配置"""
        if config_name in self._configs:
            del self._configs[config_name]

            # 如果移除的是当前配置，重新设置当前配置
            if self._current_config_name == config_name:
                self._set_current_config()

            logger.info(f"Removed LLM config: {config_name}")
            return True
        logger.warning(f"LLM config not found: {config_name}")
        return False

    def get_config_sources(self, config_name: str) -> Dict[str, bool]:
        """获取配置来源信息"""
        config = self._configs.get(config_name)
        if not config:
            return {"user": False, "workspace": False}

        return {
            "user": config.source == "user",
            "workspace": config.source == "workspace",
        }

    def get_config_by_level(self, config_name: str, level: str) -> LLMProviderConfig | None:
        """获取指定级别的配置"""
        config = self._configs.get(config_name)
        if not config:
            return None

        # 返回配置如果来源匹配
        if config.source == level:
            return config

        return None

    def reload_configs(self):
        """重新加载所有配置并清理现有客户端"""
        # 清理所有活跃的客户端，强制下次使用新配置创建新实例
        if self._active_llm_clients:
            logger.info(f"Cleaning up {len(self._active_llm_clients)} active LLM clients before reload...")
            # 直接清空列表，让旧客户端被垃圾回收
            # 注意：旧客户端的 HTTP session 会在下次使用时自动创建新实例
            self._active_llm_clients.clear()
            logger.info("All active LLM clients cleared")

        # 重新加载配置
        self._configs.clear()
        self._mode_llm_configs.clear()
        self._load_all_configs()

        # 清理流管理器缓存，因为配置可能已更改
        self._parser_cache.clear_cache()
        logger.info("All LLM configurations reloaded")

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        user_configs = sum(1 for c in self._configs.values() if c.source == "user")
        workspace_configs = sum(1 for c in self._configs.values() if c.source == "workspace")

        return {
            "total_configs": len(self._configs),
            "user_configs": user_configs,
            "workspace_configs": workspace_configs,
            "current_config": self._current_config_name,
            "mode_configs": len(self._mode_llm_configs),
            "config_names": list(self._configs.keys()),
            "providers": list(
                {config.config.apiProvider for config in self._configs.values()},
            ),
        }

    def get_all_configs_with_source(self) -> Dict[str, Any]:
        """获取所有配置及其来源信息

        统一返回全部有效配置（与 get_all_configs 一致），避免
        /llms 与 /llm-settings-all 两类接口结果不一致：
        - user / workspace: 可编辑，来自对应 settings.json
        - gateway / 其他来源: 运行时注入（如 LLM 网关模型），只读展示
        """
        user_configs_list = []
        workspace_configs_list = []
        other_configs_list = []

        for name, config in self._configs.items():
            config_dict = {
                "name": name,
                "source": config.source,
                "is_default": config.is_default,
                "config": config.to_dict(),
            }

            if config.source == "user":
                user_configs_list.append(config_dict)
            elif config.source == "workspace":
                workspace_configs_list.append(config_dict)
            else:
                other_configs_list.append(config_dict)

        return {
            "user": user_configs_list,
            "workspace": workspace_configs_list,
            "other": other_configs_list,
            "current_config": self._current_config_name,
            "mode_configs": self._mode_llm_configs.copy(),
        }

    def export_configs(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """导出配置"""
        exported = {
            "providerProfiles": {
                "apiConfigs": {},
                "currentApiConfigName": self._current_config_name,
                "modeApiConfigs": self._mode_llm_configs,
            },
        }

        for name, config in self._configs.items():
            config_dict = config.config.__dict__.copy()

            # 如果不包含敏感信息，移除 API 密钥
            if not include_sensitive:
                config_dict.pop("api_key", None)
                config_dict.pop("custom_headers", None)

            exported["providerProfiles"]["apiConfigs"][name] = config_dict

        return exported

    def import_configs(self, configs: Dict[str, Any], source: str = "user") -> bool:
        """导入配置"""
        if "providerProfiles" not in configs:
            logger.error("Invalid config format: missing providerProfiles")
            return False

        provider_profiles = configs["providerProfiles"]
        api_configs = provider_profiles.get("apiConfigs", {})
        current_config_name = provider_profiles.get("currentApiConfigName")
        mode_configs = provider_profiles.get("modeApiConfigs", {})

        # 导入 API 配置
        for config_name, config_data in api_configs.items():
            llm_config = LLMConfig.from_dict(config_data)
            is_default = config_name == current_config_name
            self.add_config(config_name, llm_config, source, is_default)

        # 导入模式配置
        for mode, config_name in mode_configs.items():
            self.set_mode_config(mode, config_name)

        logger.info(f"Imported {len(api_configs)} LLM configs from {source}")
        return True

    def create_llm_provider(self, config_name: str | None = None) -> LlmApi:
        """创建 LLM 提供者实例

        Args:
            config_name: 配置名称，如果为 None 则使用当前配置

        Returns:
            LlmApi 实例

        Raises:
            ConfigurationError: 配置不存在或无效

        """
        # 快速失败：配置检查
        config_name = config_name or self._current_config_name

        if not config_name:
            raise ConfigurationError("No LLM config specified and no current config available")

        provider_config = self.get_config(config_name)
        if not provider_config:
            raise ConfigurationError(
                f"LLM config not found: {config_name}. Available configs: {list(self._configs.keys())}",
            )

        if provider_config.raw_config:
            llm_config = provider_config.raw_config.copy()
        else:
            llm_config = provider_config.config.__dict__

        llm_config["workspace_root"] = self.workspace_root

        # 使用工厂创建客户端（KISS 原则：委托给专门的工厂）
        client = LLMClientFactory.create_client(llm_config)

        # 跟踪客户端以便后续清理
        self._active_llm_clients.append(client)
        logger.debug(f"Added {client.__class__.__name__} to active clients (total: {len(self._active_llm_clients)})")

        return client

    def get_default_llm_provider(self) -> LlmApi:
        """获取默认 LLM 提供者实例

        Returns:
            LlmApi 实例

        Raises:
            ConfigurationError: 配置不存在或无效

        """
        return self.create_llm_provider()

    def get_llm_provider_for_mode(self, mode: str) -> LlmApi | None:
        """获取模式特定的 LLM 提供者实例

        Args:
            mode: 模式名称

        Returns:
            LlmApi 实例，如果配置不存在则返回 None

        """
        mode_config = self.get_mode_config(mode)
        if mode_config:
            return self.create_llm_provider(mode_config.name)

        # 如果没有模式特定配置，使用默认配置
        return self.get_default_llm_provider()

    def get_default_llm(self) -> LlmApi:
        """获取默认 LLM 提供者实例的便捷方法

        Returns:
            LlmApi 实例

        Raises:
            ConfigurationError: 配置不存在或无效

        """
        return self.get_default_llm_provider()

    def get_llm_by_name(self, name: str) -> LlmApi:
        """根据名称获取 LLM 提供者实例的便捷方法

        Args:
            name: 配置名称

        Returns:
            LlmApi 实例

        Raises:
            ConfigurationError: 配置不存在或无效

        """
        return self.create_llm_provider(name)

    def get_default_llm_config(self) -> Dict[str, Any]:
        """获取默认 LLM 配置的便捷方法

        Returns:
            LLM配置字典

        Raises:
            ConfigurationError: 配置不存在

        """
        config = self.get_current_config()
        if not config:
            raise ConfigurationError(
                f"No current LLM config available. Available configs: {list(self._configs.keys())}",
            )
        return config.config.__dict__

    def get_llm_config_by_name(self, name: str) -> Dict[str, Any]:
        """根据名称获取 LLM 配置的便捷方法

        Args:
            name: 配置名称

        Returns:
            LLM配置字典

        Raises:
            ConfigurationError: 配置不存在

        """
        config = self.get_config(name)
        if not config:
            raise ConfigurationError(
                f"LLM config not found: {name}. Available configs: {list(self._configs.keys())}",
            )
        return config.config.__dict__

    # 移除 get_stream_manager, get_stream_statistics, reset_stream_state, clear_stream_cache
    # 这些功能将直接在 LLMProvider 内部实现或通过其公共方法间接提供

    async def cleanup(self):
        """清理所有活跃的 LLM 客户端会话"""
        for client in self._active_llm_clients:
            # Try to call the client's close() method first (BaseClient has this)
            if hasattr(client, "close"):
                try:
                    await client.close()
                    # Wait a bit for the session to fully close
                    await asyncio.sleep(0.1)
                    logger.debug(
                        f"Closed LLM client session: {client.__class__.__name__}",
                    )
                except Exception as e:
                    logger.warning(f"Error closing client {client.__class__.__name__}: {e}")
            # Fallback: try to close the session directly
            # Check for both _session (BaseClient) and _http_session (legacy)
            elif hasattr(client, "_session") and client._session:
                if not client._session.closed:
                    try:
                        await client._session.close()
                        await asyncio.sleep(0.1)
                        logger.debug(
                            f"Closed _session for LLM client: {client.__class__.__name__}",
                        )
                    except Exception as e:
                        logger.warning(f"Error closing _session: {e}")
            elif hasattr(client, "_http_session") and client._http_session and not client._http_session.closed:
                try:
                    await client._http_session.close()
                    await asyncio.sleep(0.1)
                    logger.debug(
                        f"Closed _http_session for LLM client: {client.__class__.__name__}",
                    )
                except Exception as e:
                    logger.warning(f"Error closing _http_session: {e}")
        self._active_llm_clients.clear()
        logger.info("All active LLM client sessions cleaned up.")
