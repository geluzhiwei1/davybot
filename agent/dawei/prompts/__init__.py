# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""重构后的提示词生成模块

基于模块化设计模式,提供可扩展的系统提示词生成功能.
重构后采用更简洁的架构,移除了冗余组件,提高了可维护性.
"""

from dawei.entity.mode import ModeConfig

from .core import (
    LanguageConfig,
    TemplateManager,
    TemplateRenderer,
    TemplateRenderError,
    UnifiedConfigManager,
)
from .llm_message_builder import EnhancedSystemBuilder
from .prompts_manager import PromptsManager

__all__ = [
    # 核心组件
    "EnhancedSystemBuilder",
    "UnifiedConfigManager",
    "TemplateManager",
    "TemplateRenderer",
    "TemplateRenderError",
    "PromptsManager",
    "ModeConfig",
    "LanguageConfig",
]

# 版本信息
__version__ = "2.0.0"
__author__ = "Dawei Team"
__description__ = "重构后的提示词生成模块,提供简洁高效的系统提示词生成功能"
