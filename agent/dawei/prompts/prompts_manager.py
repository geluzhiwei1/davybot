# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""提示词管理器

整合所有提示词相关功能，提供统一的管理接口。
协调模板管理、配置管理和消息构建等组件。
"""

import logging
from typing import Any

from dawei.entity.mode import ModeConfig

from .core.template_manager import TemplateManager
from .core.template_renderer import TemplateRenderer, TemplateRenderError
from .core.unified_config_manager import LanguageConfig, UnifiedConfigManager
from .llm_message_builder import EnhancedSystemBuilder

logger = logging.getLogger(__name__)


class PromptsManager:
    """提示词管理器

    整合所有提示词相关功能，提供统一的管理接口。
    """

    def __init__(
        self,
        templates_path: str | None = None,
        config_path: str | None = None,
        user_workspace: Any = None,
        cache_enabled: bool = True,
        cache_ttl: int = 3600,
    ):
        """初始化提示词管理器

        Args:
            templates_path: 模板文件目录路径
            config_path: 配置文件目录路径
            user_workspace: 用户工作区实例
            cache_enabled: 是否启用缓存
            cache_ttl: 缓存生存时间(秒)

        """
        # 初始化各个组件
        self.template_manager = TemplateManager(
            templates_path=templates_path,
            config_path=config_path,
            cache_enabled=cache_enabled,
            cache_ttl=cache_ttl,
        )

        self.template_renderer = TemplateRenderer()
        self.config_manager = UnifiedConfigManager(config_path=config_path)
        self.system_builder = EnhancedSystemBuilder(
            user_workspace=user_workspace,
            template_manager=self.template_manager,
            template_renderer=self.template_renderer,
        )

        # 缓存和状态管理
        self._initialized = False
        self._lock = None  # 懒加载锁

    def initialize(self) -> None:
        """初始化管理器"""
        if self._initialized:
            return

        try:
            # 验证配置
            config_errors = self.config_manager.validate_config()
            if config_errors:
                logger.warning(f"Configuration validation errors: {config_errors}")

            # 验证模板
            try:
                test_templates = self.template_manager.get_available_templates()
                logger.info(f"Available templates: {len(test_templates)}")
            except Exception:
                logger.exception("Template validation failed: ")

            self._initialized = True
            logger.info("PromptsManager initialized successfully")

        except Exception:
            logger.exception("Failed to initialize PromptsManager: ")
            raise

    def get_template(self, template_name: str, mode: str | None = None, language: str | None = None):
        """获取模板

        Args:
            template_name: 模板名称
            mode: 模式名称
            language: 语言代码

        Returns:
            jinja2.Template: 模板对象

        """
        if not self._initialized:
            self.initialize()

        try:
            return self.template_manager.get_template(template_name, mode, language)
        except Exception:
            logger.exception("Failed to get template {template_name}: ")
            raise

    def render_template(
        self,
        template_name: str,
        context: dict[str, Any],
        mode: str | None = None,
        language: str | None = None,
    ) -> str:
        """渲染模板

        Args:
            template_name: 模板名称
            context: 渲染上下文
            mode: 模式名称
            language: 语言代码

        Returns:
            str: 渲染结果

        """
        if not self._initialized:
            self.initialize()

        try:
            return self.template_manager.render_template(template_name, context, mode, language)
        except TemplateRenderError:
            raise
        except Exception as e:
            logger.exception("Failed to render template {template_name}: ")
            raise TemplateRenderError(f"Template rendering failed: {e}")

    def build_system_prompt(self, capabilities: list[str], _mode: str | None = None) -> dict[str, Any]:
        """构建系统提示

        Args:
            capabilities: 能力列表
            mode: 模式名称

        Returns:
            Dict[str, Any]: 构建结果

        """
        if not self._initialized:
            self.initialize()

        try:
            return self.system_builder.build_messages(capabilities)
        except Exception:
            logger.exception("Failed to build system prompt: ")
            raise

    def get_mode_config(self, mode: str) -> ModeConfig | None:
        """获取模式配置

        Args:
            mode: 模式名称

        Returns:
            Optional[ModeConfig]: 模式配置

        """
        if not self._initialized:
            self.initialize()

        return self.config_manager.get_mode_config(mode)

    def get_language_config(self, language: str) -> LanguageConfig | None:
        """获取语言配置

        Args:
            language: 语言代码

        Returns:
            Optional[LanguageConfig]: 语言配置

        """
        if not self._initialized:
            self.initialize()

        return self.config_manager.get_language_config(language)

    def get_available_modes(self) -> list[str]:
        """获取可用模式列表

        Returns:
            List[str]: 模式名称列表

        """
        if not self._initialized:
            self.initialize()

        return self.config_manager.get_all_modes()

    def get_available_languages(self) -> list[str]:
        """获取可用语言列表

        Returns:
            List[str]: 语言代码列表

        """
        if not self._initialized:
            self.initialize()

        return self.config_manager.get_all_languages()

    def get_available_templates(self) -> list[str]:
        """获取可用模板列表

        Returns:
            List[str]: 模板名称列表

        """
        if not self._initialized:
            self.initialize()

        return self.template_manager.get_available_templates()

    def reload_config(self) -> None:
        """重新加载配置"""
        try:
            self.config_manager.reload_config()
            if self._initialized:
                self.template_manager.reload_templates()
            logger.info("Configuration reloaded successfully")
        except Exception:
            logger.exception("Failed to reload configuration: ")
            raise

    def clear_cache(self) -> None:
        """清理缓存"""
        try:
            self.template_manager.invalidate_cache()
            logger.info("Cache cleared successfully")
        except Exception:
            logger.exception("Failed to clear cache: ")
            raise

    def validate_configuration(self) -> list[str]:
        """验证配置

        Returns:
            List[str]: 错误列表，空列表表示验证通过

        """
        if not self._initialized:
            self.initialize()

        return self.config_manager.validate_config()

    def close(self) -> None:
        """关闭管理器，清理资源"""
        try:
            self.template_manager.close()
            self.config_manager.close()
            self._initialized = False
            logger.info("PromptsManager closed successfully")
        except Exception:
            logger.exception("Failed to close PromptsManager: ")
            raise

    def __enter__(self):
        """上下文管理器入口"""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()

    @property
    def initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    @property
    def template_cache_info(self) -> dict[str, Any]:
        """获取模板缓存信息"""
        return {
            "cache_enabled": self.template_manager.cache_enabled,
            "cache_size": len(self.template_manager.template_cache),
            "cache_ttl": self.template_manager.cache_ttl,
        }

    @property
    def configuration_info(self) -> dict[str, Any]:
        """获取配置信息"""
        return {
            "modes_count": len(self.config_manager.get_all_modes()),
            "languages_count": len(self.config_manager.get_all_languages()),
            "templates_count": len(self.get_available_templates()),
        }
