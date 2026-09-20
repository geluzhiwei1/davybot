# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""核心组件模块

包含重构后的核心组件：
- UnifiedConfigManager: 统一配置管理器
- TemplateManager: 简化的模板管理器
- TemplateRenderer: 简化的模板渲染器
- EnhancedSystemBuilder: 增强的系统构建器
"""

from dawei.entity.mode import ModeConfig

from .template_manager import TemplateManager
from .template_renderer import TemplateRenderer, TemplateRenderError
from .unified_config_manager import LanguageConfig, UnifiedConfigManager

__all__ = [
    "LanguageConfig",
    "ModeConfig",
    "TemplateManager",
    "TemplateRenderError",
    "TemplateRenderer",
    "UnifiedConfigManager",
]
