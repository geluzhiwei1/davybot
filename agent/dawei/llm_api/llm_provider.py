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
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from dawei.core.exceptions import ConfigurationError
from dawei.entity.llm_config import LLMConfig, LLMProviderConfig
from dawei.entity.lm_messages import LLMMessage
from dawei.entity.stream_message import (
    CompleteMessage,
    ContentMessage,
    StreamMessages,
    ToolCallMessage,
    UsageMessage,
)
from dawei.interfaces.llm_service import ILLMService

from .base_llm_api import LlmApi

# 从 provider 子模块导入拆分的组件
from .provider import LLMClientFactory, ParserCache, StreamState

logger = logging.getLogger(__name__)


def _load_settings_file(settings_file: Path, source: str) -> dict[str, LLMProviderConfig]:
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

    configs = {}
    if data and "providerProfiles" in data:
        provider_profiles = data["providerProfiles"]
        api_configs = provider_profiles.get("apiConfigs", {})
        current_config_name = provider_profiles.get("currentApiConfigName")
        mode_api_configs = provider_profiles.get("modeApiConfigs", {})

        for config_name, config_data in api_configs.items():
            llm_config = LLMConfig.from_dict(config_data)
            provider_config = LLMProviderConfig(
                name=config_name,
                config=llm_config,
                source=source,
                is_default=(config_name == current_config_name),
            )
            configs[config_name] = provider_config

        logger.debug(f"Loaded {len(configs)} LLM configs from {settings_file}")

    return configs, mode_api_configs


def _load_user_llm_configs() -> tuple[dict[str, LLMProviderConfig], dict[str, str]]:
    """加载用户级LLM配置

    Returns:
        (配置字典, 模式配置字典)

    """
    user_home = Path.home()
    settings_file = user_home / ".dawei" / "configs" / "settings.json"
    configs, mode_configs = _load_settings_file(settings_file, "user")
    logger.info(f"Loaded {len(configs)} user LLM configs")
    return configs, mode_configs


def _load_workspace_llm_configs(
    workspace_path: str,
) -> tuple[dict[str, LLMProviderConfig], dict[str, str]]:
    """加载工作区级LLM配置

    Args:
        workspace_path: 工作区路径

    Returns:
        (配置字典, 模式配置字典)

    """
    workspace_dir = Path(workspace_path)
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

    def __init__(self, workspace_path: str | None = None):
        """初始化 LLM 管理器

        Args:
            workspace_path: 工作区路径（可选）

        Raises:
            RuntimeError: 如果必需的配置加载失败

        """
        self.workspace_path = workspace_path

        # 配置字典
        self._configs: dict[str, LLMProviderConfig] = {}
        self._current_config_name: str | None = None

        # 模式特定的 LLM 配置
        self._mode_llm_configs: dict[str, str] = {}

        # 活跃的 LLM 客户端实例列表，用于清理
        self._active_llm_clients: list[LlmApi] = []

        # StreamState 和 ParserCache 实例
        self._stream_state: StreamState = StreamState()
        self._parser_cache: ParserCache = ParserCache()

        # 一次性加载所有配置
        self._load_all_configs()

    def _load_all_configs(self):
        """一次性加载所有配置（2层）"""
        # 1. 加载用户配置
        try:
            user_configs, user_mode_configs = _load_user_llm_configs()
            self._configs.update(user_configs)
            self._mode_llm_configs.update(user_mode_configs)
        except Exception as e:
            # Fast Fail: 用户配置加载失败应立即抛出
            logger.error(f"Failed to load user LLM configs: {e}", exc_info=True)
            raise RuntimeError(f"Cannot load user LLM configs: {e}")

        # 2. 如果有工作区，应用工作区覆盖（简单更新）
        if self.workspace_path:
            try:
                workspace_configs, workspace_mode_configs = _load_workspace_llm_configs(self.workspace_path)
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

    def _create_dynamic_config(self, provider: str, model: str) -> dict[str, Any] | None:
        """创建动态配置字典

        Args:
            provider: 提供商名称 (e.g., "ollama", "openai")
            model: 模型名称 (e.g., "llama3.1", "gpt-4")

        Returns:
            配置字典，如果提供商不支持则返回 None

        """
        provider_lower = provider.lower()

        if provider_lower == "ollama":
            return {
                "apiProvider": "ollama",
                "ollamaBaseUrl": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                "ollamaModelId": model,
                "ollamaApiKey": os.getenv("OLLAMA_API_KEY", "ollama"),
                "model_id": model,
                "max_tokens": 2000,
                "temperature": 0.7,
            }
        if provider_lower == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not set for dynamic OpenAI config")
                return None
            return {
                "apiProvider": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": api_key,
                "model_id": model,
                "max_tokens": 2000,
                "temperature": 0.7,
            }
        if provider_lower == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                logger.warning("DEEPSEEK_API_KEY not set for dynamic DeepSeek config")
                return None
            return {
                "apiProvider": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": api_key,
                "model_id": model,
                "max_tokens": 2000,
                "temperature": 0.7,
            }
        logger.warning(f"Unsupported provider for dynamic config: {provider}")
        return None

    def _set_provider_from_string(self, provider_string: str) -> bool:
        """从 "provider/model" 格式的字符串创建并设置动态配置

        Args:
            provider_string: 提供商/模型字符串 (e.g., "ollama/llama3.1")

        Returns:
            是否设置成功

        """
        # 解析 provider/model 格式
        parts = provider_string.split("/", 1)
        if len(parts) != 2:
            logger.error(f"Invalid provider format: {provider_string}. Expected 'provider/model'")
            return False

        provider, model = parts

        # 创建动态配置
        config_dict = self._create_dynamic_config(provider, model)
        if not config_dict:
            logger.error(f"Failed to create dynamic config for: {provider_string}")
            return False

        # 创建LLMConfig对象
        llm_config = LLMConfig.from_dict(config_dict)

        # 生成配置名称（使用完整的provider_string作为配置名）
        config_name = provider_string

        # 添加到用户配置（动态配置优先级较高）
        provider_config = LLMProviderConfig(
            name=config_name,
            config=llm_config,
            source="user",
            is_default=False,
        )

        # 添加到配置字典
        self._configs[config_name] = provider_config

        logger.info(
            f"Created dynamic LLM config: {config_name} (provider={provider}, model={model})",
        )

        # 设置为当前配置
        return self.set_current_config(config_name)

    # 实现 ILLMService 接口的方法
    def get_available_providers(self) -> list[str]:
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
            provider_name: 提供者名称，支持两种格式：
                          - 配置名称 (e.g., "my-openai-config")
                          - provider/model 格式 (e.g., "ollama/llama3.1")

        Returns:
            是否设置成功

        """
        logger.debug(f"Setting provider to: {provider_name}")

        # 检查是否为 "provider/model" 格式
        if "/" in provider_name:
            logger.info(f"Detected provider/model format: {provider_name}")
            success = self._set_provider_from_string(provider_name)
        else:
            # 原有逻辑：直接查找配置
            success = self.set_current_config(provider_name)

        if success:
            logger.info(f"Provider set successfully to: {provider_name}")
        else:
            logger.warning(f"Failed to set provider to: {provider_name}")

        return success

    def get_provider_config(self, provider_name: str) -> dict[str, Any] | None:
        """获取提供者配置（实现 ILLMService 接口）

        Args:
            provider_name: 提供者名称

        Returns:
            提供者配置字典

        """
        config = self.get_llm_config_by_name(provider_name)
        logger.debug(f"Retrieved config for provider: {provider_name}")
        return config

    def update_provider_config(self, provider_name: str, config: dict[str, Any]) -> bool:
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

    def get_model_info(self, provider_name: str | None = None) -> dict[str, Any]:
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

    async def process_message(self, messages: list[LLMMessage], **kwargs) -> dict[str, Any]:
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

    async def create_message_with_callback(
        self,
        messages: list[LLMMessage],
        callback: Callable[[StreamMessages], Awaitable[None]],
        **kwargs,
    ) -> dict[str, Any]:
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
        all_tool_calls = []

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
            elif isinstance(message, CompleteMessage):
                break

        result = {
            "content": full_content or None,
            "tool_calls": all_tool_calls or None,
        }

        self._stream_state.is_processing = False
        self._stream_state.is_streaming = False

        return result

    # 原有的方法保持不变
    def set_workspace_path(self, workspace_path: str):
        """设置工作区路径并重新加载配置"""
        self.workspace_path = workspace_path
        # 重新加载配置
        self._configs.clear()
        self._mode_llm_configs.clear()
        self._load_all_configs()
        logger.info(f"Workspace path set to {workspace_path}, LLM configs reloaded")

    def get_all_configs(self) -> dict[str, LLMProviderConfig]:
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
        """设置当前 LLM 配置"""
        if config_name not in self._configs:
            logger.error(f"LLM config not found: {config_name}")
            return False

        self._current_config_name = config_name
        logger.info(f"Set current LLM config to: {config_name}")
        return True

    def get_current_config_name(self) -> str | None:
        """获取当前配置名称"""
        return self._current_config_name

    def get_config_names(self) -> list[str]:
        """获取所有配置名称"""
        return list(self._configs.keys())

    def get_config_by_provider(self, provider: str) -> list[LLMProviderConfig]:
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

    def get_mode_configs(self) -> dict[str, str]:
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

    def get_config_sources(self, config_name: str) -> dict[str, bool]:
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
        """重新加载所有配置"""
        self._configs.clear()
        self._mode_llm_configs.clear()
        self._load_all_configs()
        # 清理流管理器缓存，因为配置可能已更改
        self._parser_cache.clear_cache()
        logger.info("All LLM configurations reloaded")

    def get_statistics(self) -> dict[str, Any]:
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

    def get_all_configs_with_source(self) -> dict[str, Any]:
        """获取所有配置及其来源信息"""
        user_configs_list = []
        workspace_configs_list = []

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

        return {
            "user": user_configs_list,
            "workspace": workspace_configs_list,
            "current_config": self._current_config_name,
            "mode_configs": self._mode_llm_configs.copy(),
        }

    def export_configs(self, include_sensitive: bool = False) -> dict[str, Any]:
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

    def import_configs(self, configs: dict[str, Any], source: str = "user") -> bool:
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

        llm_config = provider_config.config.__dict__
        llm_config["workspace_path"] = self.workspace_path

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

    def get_default_llm_config(self) -> dict[str, Any]:
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

    def get_llm_config_by_name(self, name: str) -> dict[str, Any]:
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
