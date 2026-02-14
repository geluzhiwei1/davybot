# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""简化的模板管理器

整合原有的模板管理功能，提供更简洁的接口。
"""

import logging
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import jinja2

logger = logging.getLogger(__name__)


class TemplateManager:
    """简化的模板管理器

    整合原有的模板管理功能，提供更简洁的接口。
    """

    def __init__(
        self,
        templates_path: str | None = None,
        config_path: str | None = None,
        cache_enabled: bool = True,
        cache_ttl: int = 3600,
    ):
        """初始化模板管理器

        Args:
            templates_path: 模板文件目录路径
            config_path: 配置文件路径
            cache_enabled: 是否启用缓存
            cache_ttl: 缓存生存时间(秒)

        """
        # 获取默认路径
        base_path = Path(__file__).parent.parent.parent
        self.templates_path = Path(templates_path or base_path / "prompts" / "templates")
        self.config_path = Path(config_path or base_path / "prompts" / "config")

        # 缓存配置
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self.template_cache: dict[str, dict[str, Any]] = {}
        self.cache_timestamps: dict[str, datetime] = {}

        # Jinja环境
        self.jinja_env = None
        self._setup_jinja_environment()

        # 线程锁
        self._lock = threading.RLock()

        # 发现并加载模板
        self._discover_templates()

    def _setup_jinja_environment(self) -> None:
        """设置Jinja环境"""
        loader = jinja2.FileSystemLoader(
            [
                str(self.templates_path),
                str(self.templates_path / "base"),
                str(self.templates_path / "sections"),
                str(self.templates_path / "modes"),
                str(self.templates_path / "languages"),
            ],
        )

        self.jinja_env = jinja2.Environment(
            loader=loader,
            autoescape=jinja2.select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        # 添加自定义过滤器和函数
        self._add_custom_filters()

    def _add_custom_filters(self) -> None:
        """添加自定义Jinja过滤器"""

        def format_list_items(items: list[str], prefix: str = "- ") -> str:
            """格式化列表项"""
            return "\n".join(f"{prefix}{item}" for item in items)

        def upper_first(text: str) -> str:
            """首字母大写"""
            return text[:1].upper() + text[1:] if text else text

        def format_capability_list(capabilities: list[str]) -> str:
            """格式化能力列表"""
            if not capabilities:
                return ""
            return f"- Available capabilities: {', '.join(capabilities)}"

        # 注册过滤器
        self.jinja_env.filters["format_list_items"] = format_list_items
        self.jinja_env.filters["upper_first"] = upper_first
        self.jinja_env.filters["format_capability_list"] = format_capability_list

    def _discover_templates(self) -> None:
        """发现并加载所有模板文件"""
        with self._lock:
            try:
                # 扫描模板目录
                for template_file in self.templates_path.rglob("*.j2"):
                    rel_path = template_file.relative_to(self.templates_path)
                    template_name = str(rel_path).replace("\\", "/")

                    # 预加载模板到Jinja环境
                    try:
                        self.jinja_env.get_template(template_name)
                        logger.debug(f"Discovered template: {template_name}")
                    except jinja2.TemplateNotFound:
                        # Template not in Jinja search path - skip
                        logger.debug(f"Template not found in Jinja search path: {template_name}")
                    except jinja2.TemplateError as e:
                        # Invalid template syntax - log but continue
                        logger.warning(f"Failed to load template {template_name}: {e}")

                logger.info(f"Discovered templates in: {self.templates_path}")

            except (OSError, PermissionError) as e:
                # Filesystem error - fast fail
                logger.error(
                    f"Failed to discover templates due to filesystem error: {e}",
                    exc_info=True,
                )
                raise
            except ValueError as e:
                # Path calculation error - fast fail
                logger.error(
                    f"Failed to discover templates due to invalid path: {e}",
                    exc_info=True,
                )
                raise

    def get_template(
        self,
        template_name: str,
        mode: str | None = None,
        language: str | None = None,
    ) -> jinja2.Template | None:
        """获取指定模板

        Args:
            template_name: 模板名称
            mode: 模式名称
            language: 语言代码

        Returns:
            Optional[jinja2.Template]: Jinja模板对象

        """
        # 构建缓存键
        cache_key = self._build_cache_key(template_name, mode, language)

        # 检查缓存
        if self.cache_enabled:
            cached_template = self._get_from_cache(cache_key)
            if cached_template:
                return cached_template

        # 尝试加载模板
        template = self._load_template(template_name, mode, language)

        # 缓存模板
        if self.cache_enabled and template:
            self._cache_template(cache_key, template)

        return template

    def _build_cache_key(self, template_name: str, mode: str | None = None, language: str | None = None) -> str:
        """构建缓存键"""
        parts = [template_name]
        if mode:
            parts.append(f"mode:{mode}")
        if language:
            parts.append(f"lang:{language}")
        return "|".join(parts)

    def _load_template(
        self,
        template_name: str,
        mode: str | None = None,
        language: str | None = None,
    ) -> jinja2.Template | None:
        """加载模板

        Args:
            template_name: 模板名称
            mode: 模式名称
            language: 语言代码

        Returns:
            Optional[jinja2.Template]: 加载的模板，失败时返回None

        """
        try:
            # 尝试加载特定语言和模式的模板
            if language and mode:
                specific_template = f"languages/{language}/modes/{mode}/{template_name}"
                try:
                    return self.jinja_env.get_template(specific_template)
                except jinja2.TemplateNotFound:
                    pass

            # 尝试加载特定模式的模板
            if mode:
                mode_template = f"modes/{mode}/{template_name}"
                try:
                    return self.jinja_env.get_template(mode_template)
                except jinja2.TemplateNotFound:
                    pass

            # 尝试加载特定语言的模板
            if language:
                lang_template = f"languages/{language}/{template_name}"
                try:
                    return self.jinja_env.get_template(lang_template)
                except jinja2.TemplateNotFound:
                    pass

            # 加载基础模板
            return self.jinja_env.get_template(template_name)

        except jinja2.TemplateError:
            logger.exception("Failed to load template {template_name}: ")
            return None

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

        Raises:
            ValueError: If template not found or context is invalid
            jinja2.TemplateError: If template rendering fails

        """
        try:
            template = self.get_template(template_name, mode, language)
            if not template:
                raise ValueError(f"Template not found: {template_name}")

            # 添加全局上下文
            full_context = self._prepare_context(context, mode, language)

            # 渲染模板
            result = template.render(**full_context)

            logger.debug(f"Rendered template: {template_name}")
            return result

        except ValueError:
            # Re-raise ValueError (already logged in caller or self)
            raise
        except jinja2.TemplateError as e:
            # Jinja rendering error - fast fail with context
            logger.error(f"Failed to render template {template_name}: {e}", exc_info=True)
            raise ValueError(f"Template rendering failed for {template_name}: {e}")
        except (TypeError, AttributeError) as e:
            # Context preparation error - fast fail
            logger.error(f"Invalid context for template {template_name}: {e}", exc_info=True)
            raise ValueError(f"Invalid template context for {template_name}: {e}")

    def _prepare_context(
        self,
        context: dict[str, Any],
        mode: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """准备渲染上下文

        Args:
            context: 原始上下文
            mode: 模式名称
            language: 语言代码

        Returns:
            Dict[str, Any]: 完整的渲染上下文

        """
        full_context = context.copy()

        # 添加全局变量
        full_context.update(
            {
                "mode": mode,
                "language": language,
                "current_time": datetime.now(timezone.utc),
                "template_manager": self,
            },
        )

        return full_context

    def _get_from_cache(self, cache_key: str) -> jinja2.Template | None:
        """从缓存获取模板

        Args:
            cache_key: 缓存键

        Returns:
            Optional[jinja2.Template]: 缓存的模板，过期或不存在时返回None

        """
        if cache_key not in self.template_cache:
            return None

        # 检查缓存是否过期
        timestamp = self.cache_timestamps.get(cache_key)
        if timestamp and datetime.now(timezone.utc) - timestamp > timedelta(seconds=self.cache_ttl):
            self.invalidate_cache(cache_key)
            return None

        return self.template_cache[cache_key]["template"]

    def _cache_template(self, cache_key: str, template: jinja2.Template) -> None:
        """缓存模板

        Args:
            cache_key: 缓存键
            template: 要缓存的模板

        """
        self.template_cache[cache_key] = {
            "template": template,
            "cached_at": datetime.now(timezone.utc),
        }
        self.cache_timestamps[cache_key] = datetime.now(timezone.utc)

    def invalidate_cache(self, template_name: str | None = None) -> None:
        """清理缓存

        Args:
            template_name: 要清理的模板名称，None表示清理所有缓存

        """
        with self._lock:
            if template_name is None:
                # 清理所有缓存
                self.template_cache.clear()
                self.cache_timestamps.clear()
                logger.info("All template cache cleared")
            else:
                # 清理特定模板的缓存
                keys_to_remove = [key for key in self.template_cache if key.startswith(template_name)]
                for key in keys_to_remove:
                    del self.template_cache[key]
                    if key in self.cache_timestamps:
                        del self.cache_timestamps[key]
                logger.info(f"Cache cleared for template: {template_name}")

    def reload_templates(self) -> None:
        """重新加载所有模板

        Raises:
            OSError: If template directory cannot be accessed
            PermissionError: If lacks permissions
            RuntimeError: If Jinja environment setup fails

        """
        with self._lock:
            try:
                # 清理缓存
                self.invalidate_cache()

                # 重新设置Jinja环境
                self._setup_jinja_environment()

                # 重新发现模板
                self._discover_templates()

                logger.info("All templates reloaded successfully")

            except (OSError, PermissionError) as e:
                # Filesystem error - fast fail
                logger.error(
                    f"Failed to reload templates due to filesystem error: {e}",
                    exc_info=True,
                )
                raise
            except RuntimeError as e:
                # Jinja environment setup error - fast fail
                logger.error(
                    f"Failed to reload templates due to environment error: {e}",
                    exc_info=True,
                )
                raise

    def get_available_templates(self) -> list[str]:
        """获取所有可用模板列表

        Returns:
            List[str]: 模板名称列表

        Note:
            Swallows filesystem errors and returns partial results for graceful degradation

        """
        templates = []
        try:
            for template_file in self.templates_path.rglob("*.j2"):
                rel_path = template_file.relative_to(self.templates_path)
                template_name = str(rel_path).replace("\\", "/")
                templates.append(template_name)
        except (OSError, PermissionError) as e:
            # Filesystem error - log and return partial results (graceful degradation)
            logger.error(
                f"Failed to get available templates due to filesystem error: {e}",
                exc_info=True,
            )
        except ValueError as e:
            # Path calculation error - log and return partial results
            logger.error(f"Failed to calculate template paths: {e}", exc_info=True)

        return sorted(templates)

    def template_exists(self, template_name: str) -> bool:
        """检查模板是否存在

        Args:
            template_name: 模板名称

        Returns:
            bool: 模板是否存在

        """
        try:
            self.jinja_env.get_template(template_name)
            return True
        except jinja2.TemplateNotFound:
            return False

    def close(self) -> None:
        """关闭模板管理器，清理资源"""
        self.invalidate_cache()
        logger.info("Template manager closed")
