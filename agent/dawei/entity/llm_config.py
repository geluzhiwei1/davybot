# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM 配置相关的实体类"""

from dataclasses import dataclass, field
from typing import Any


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
    custom_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "LLMConfig":
        """从字典创建LLM配置"""
        return cls(
            apiProvider=config_dict.get("apiProvider", "openai"),
            model_id=config_dict.get("openAiModelId", config_dict.get("apiModelId", "")),
            api_key=config_dict.get("openAiApiKey", config_dict.get("deepSeekApiKey", "")),
            base_url=config_dict.get("openAiBaseUrl", ""),
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
        )


@dataclass
class LLMProviderConfig:
    """LLM 提供者配置数据类"""

    name: str
    config: LLMConfig
    source: str = "user"  # system/user/workspace
    priority: int = 50
    is_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "config": self.config.__dict__,
            "source": self.source,
            "priority": self.priority,
            "is_default": self.is_default,
        }
