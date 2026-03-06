# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM 配置相关的实体类"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class LLMConfig:
    """LLM配置类"""

    apiProvider: str = "openai"
    model_id: str = ""
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = -1
    context_window: int = 128000
    supports_images: bool = False
    supports_prompt_cache: bool = False
    input_price: float = 0.0
    output_price: float = 0.0
    reasoning_effort: str = None
    custom_headers: Dict[str, str] = field(default_factory=dict)
    # 代理配置
    http_proxy: str = ""  # HTTP 代理 URL, 如 "http://127.0.0.1:7890"
    https_proxy: str = ""  # HTTPS 代理 URL
    no_proxy: str = ""  # 跳过代理的地址, 逗号分隔

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "LLMConfig":
        """从字典创建LLM配置 - 所有 OpenAI 兼容提供商使用统一字段"""
        api_provider = config_dict.get("apiProvider", "openai")
        model_id = config_dict.get("openAiModelId", config_dict.get("apiModelId", ""))
        base_url = config_dict.get("openAiBaseUrl", "")
        api_key = config_dict.get("openAiApiKey", "")

        return cls(
            apiProvider=api_provider,
            model_id=model_id,
            api_key=api_key,
            base_url=base_url,
            max_tokens=config_dict.get("openAiCustomModelInfo", {}).get("maxTokens", -1),
            context_window=config_dict.get("openAiCustomModelInfo", {}).get(
                "contextWindow",
                128000,
            ),
            supports_images=config_dict.get("openAiCustomModelInfo", {}).get(
                "supportsImages",
                False,
            ),
            supports_prompt_cache=config_dict.get("openAiCustomModelInfo", {}).get(
                "supportsPromptCache",
                False,
            ),
            input_price=config_dict.get("openAiCustomModelInfo", {}).get("inputPrice", 0.0),
            output_price=config_dict.get("openAiCustomModelInfo", {}).get("outputPrice", 0.0),
            reasoning_effort=config_dict.get("openAiCustomModelInfo", {}).get("reasoningEffort"),
            custom_headers=config_dict.get("openAiHeaders", {}),
            http_proxy=config_dict.get("httpProxy", ""),
            https_proxy=config_dict.get("httpsProxy", ""),
            no_proxy=config_dict.get("noProxy", ""),
        )


@dataclass
class LLMProviderConfig:
    """LLM 提供者配置数据类"""

    name: str
    config: LLMConfig
    source: str = "user"  # system/user/workspace
    priority: int = 50
    is_default: bool = False
    raw_config: Dict[str, Any] = field(default_factory=dict)  # 存储完整的原始配置数据

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典,返回完整的配置数据(包括所有字段)"""
        # 如果有原始配置,优先使用原始配置
        if self.raw_config:
            return {
                "name": self.name,
                "config": self.raw_config,  # 返回完整的原始配置
                "source": self.source,
                "priority": self.priority,
                "is_default": self.is_default,
            }
        # 兼容旧代码,如果没有原始配置则使用 config.__dict__
        return {
            "name": self.name,
            "config": self.config.__dict__,
            "source": self.source,
            "priority": self.priority,
            "is_default": self.is_default,
        }
