# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""简化的模板渲染器

整合原有的模板渲染功能，提供更简洁的接口。
"""

import logging
from datetime import datetime, timezone
from typing import Any

import jinja2

logger = logging.getLogger(__name__)


class TemplateRenderError(Exception):
    """模板渲染错误"""


class TemplateRenderer:
    """简化的模板渲染器

    整合原有的模板渲染功能，提供更简洁的接口。
    """

    def __init__(self, debug_mode: bool = False, strict_undefined: bool = False):
        """初始化模板渲染器

        Args:
            debug_mode: 是否启用调试模式
            strict_undefined: 是否启用严格模式（未定义变量报错）

        """
        self.debug_mode = debug_mode
        self.strict_undefined = strict_undefined

        # 渲染统计
        self.render_count = 0
        self.error_count = 0
        self.render_history: list[dict[str, Any]] = []

    def render(self, template: jinja2.Template, context: dict[str, Any]) -> str:
        """渲染模板

        Args:
            template: Jinja模板对象
            context: 渲染上下文

        Returns:
            str: 渲染结果

        Raises:
            TemplateRenderError: 渲染失败时抛出

        """
        start_time = datetime.now(timezone.utc)

        try:
            # 准备渲染环境
            self._prepare_render_environment()

            # 验证上下文
            validated_context = self._validate_context(context)

            # 执行渲染
            result = template.render(**validated_context)

            # 后处理结果
            result = self._post_process_result(result)

            # 记录成功渲染
            self._record_render_success(
                template.name if hasattr(template, "name") else "unknown",
                start_time,
                len(result),
            )

            if self.debug_mode:
                logger.debug(f"Template rendered successfully, length: {len(result)}")

            return result

        except jinja2.TemplateError as e:
            # Jinja template rendering errors (syntax, undefined, etc.)
            self._record_render_error(str(template), start_time, str(e))
            raise TemplateRenderError(f"Template error: {e}")
        except (ValueError, TypeError) as e:
            # Context validation errors (wrong types, invalid values)
            self._record_render_error(str(template), start_time, str(e))
            raise TemplateRenderError(f"Invalid context: {e}")

    def render_string(self, template_string: str, context: dict[str, Any]) -> str:
        """渲染字符串模板

        Args:
            template_string: 模板字符串
            context: 渲染上下文

        Returns:
            str: 渲染结果

        Raises:
            TemplateRenderError: 渲染失败时抛出

        """
        start_time = datetime.now(timezone.utc)

        try:
            # 创建临时模板
            template = jinja2.Template(
                template_string,
                undefined=jinja2.StrictUndefined if self.strict_undefined else jinja2.Undefined,
            )

            # 验证上下文
            validated_context = self._validate_context(context)

            # 执行渲染
            result = template.render(**validated_context)

            # 后处理结果
            result = self._post_process_result(result)

            # 记录成功渲染
            self._record_render_success("string_template", start_time, len(result))

            return result

        except jinja2.TemplateSyntaxError as e:
            # Template syntax errors during parsing
            self._record_render_error("string_template", start_time, str(e))
            raise TemplateRenderError(
                f"Template syntax error at line {e.lineno}: {e.message}",
            )
        except jinja2.TemplateError as e:
            # Runtime template errors (undefined variables, etc.)
            self._record_render_error("string_template", start_time, str(e))
            raise TemplateRenderError(f"Template error: {e}")
        except (ValueError, TypeError) as e:
            # Context validation errors
            self._record_render_error("string_template", start_time, str(e))
            raise TemplateRenderError(f"Invalid context: {e}")

    def _prepare_render_environment(self) -> dict[str, Any]:
        """准备渲染环境

        Returns:
            Dict[str, Any]: 渲染环境配置

        """
        env = {}

        # 添加全局函数
        env.update(
            {
                "now": datetime.now,
                "format_datetime": self._format_datetime,
                "format_list": self._format_list,
                "format_dict": self._format_dict,
                "safe_default": self._safe_default,
                "conditional_include": self._conditional_include,
            },
        )

        return env

    def _validate_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """验证并清理上下文

        Args:
            context: 原始上下文

        Returns:
            Dict[str, Any]: 验证后的上下文

        """
        if not isinstance(context, dict):
            raise TemplateRenderError(f"Context must be a dict, got {type(context).__name__}")

        validated = {}

        for key, value in context.items():
            # 验证键
            if not isinstance(key, str):
                validated_key = str(key)
                logger.warning(f"Non-string context key '{key}' converted to '{validated_key}'")
            else:
                validated_key = key

            # 处理特殊值
            if value is None:
                validated[validated_key] = "" if not self.strict_undefined else None
            elif isinstance(value, (list, dict)):
                validated[validated_key] = value
            elif hasattr(value, "__dict__"):
                # 对象转换为字典
                try:
                    validated[validated_key] = vars(value)
                except TypeError:
                    # Intentional degradation: vars() doesn't support this type (e.g., built-in types, slots)
                    # Fallback to string representation for template rendering
                    validated[validated_key] = str(value)
                except (AttributeError, ValueError) as e:
                    # Object introspection failed (e.g., C extensions, special objects)
                    # Fallback to string representation - acceptable degradation for templates
                    logger.debug(f"Cannot introspect object {type(value).__name__}: {e}")
                    validated[validated_key] = str(value)
            else:
                validated[validated_key] = value

        return validated

    def _post_process_result(self, result: str) -> str:
        """后处理渲染结果

        Args:
            result: 原始渲染结果

        Returns:
            str: 后处理结果

        """
        # 清理多余的空行
        lines = result.split("\n")
        cleaned_lines = []

        i = 0
        while i < len(lines):
            line = lines[i].rstrip()

            # 保留非空行
            if line:
                cleaned_lines.append(line)
            # 检查是否为连续空行
            elif i == 0 or i == len(lines) - 1 or lines[i + 1].strip():
                cleaned_lines.append("")

            i += 1

        return "\n".join(cleaned_lines)

    def _format_datetime(self, dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
        """格式化日期时间

        Args:
            dt: 日期时间对象
            format_str: 格式字符串

        Returns:
            str: 格式化后的字符串

        """
        if not isinstance(dt, datetime):
            logger.warning(f"Expected datetime object, got {type(dt).__name__}")
            return str(dt) if dt else ""

        try:
            return dt.strftime(format_str)
        except (AttributeError, TypeError) as fmt_error:
            # Expected: not a datetime object or doesn't support strftime
            logger.debug(f"Invalid datetime object: {fmt_error}")
            return str(dt) if dt else ""
        except ValueError as fmt_error:
            # Expected: invalid format string
            logger.debug(f"Invalid format string '{format_str}': {fmt_error}")
            return str(dt) if dt else ""

    def _format_list(self, items: list[Any], prefix: str = "- ", separator: str = "\n") -> str:
        """格式化列表

        Args:
            items: 列表项
            prefix: 前缀
            separator: 分隔符

        Returns:
            str: 格式化后的字符串

        """
        if not isinstance(items, list):
            logger.warning(f"Expected list, got {type(items).__name__}")
            return str(items) if items else ""

        if not items:
            return ""

        formatted_items = [f"{prefix}{item}" for item in items]
        return separator.join(formatted_items)

    def _format_dict(self, data: dict[str, Any], indent: int = 0) -> str:
        """格式化字典

        Args:
            data: 字典数据
            indent: 缩进级别

        Returns:
            str: 格式化后的字符串

        """
        if not isinstance(data, dict):
            logger.warning(f"Expected dict, got {type(data).__name__}")
            return str(data) if data else ""

        if not data:
            return ""

        lines = []
        prefix = "  " * indent

        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(self._format_dict(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    lines.append(f"{prefix}  - {item}")
            else:
                lines.append(f"{prefix}{key}: {value}")

        return "\n".join(lines)

    def _safe_default(self, value: Any, default: Any = "") -> Any:
        """安全获取默认值

        Args:
            value: 原始值
            default: 默认值

        Returns:
            Any: 值或默认值

        """
        if value is None:
            return default
        return value

    def _conditional_include(self, condition: bool, content: str) -> str:
        """条件包含内容

        Args:
            condition: 条件
            content: 内容

        Returns:
            str: 内容或空字符串

        """
        if not isinstance(condition, bool):
            logger.warning(f"Expected boolean condition, got {type(condition).__name__}")
            return ""

        return content if condition else ""

    def _record_render_success(
        self,
        template_name: str,
        start_time: datetime,
        result_length: int,
    ) -> None:
        """记录成功渲染

        Args:
            template_name: 模板名称
            start_time: 开始时间
            result_length: 结果长度

        """
        self.render_count += 1

        if self.debug_mode:
            render_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            record = {
                "template": template_name,
                "status": "success",
                "render_time": render_time,
                "result_length": result_length,
                "timestamp": start_time,
            }
            self.render_history.append(record)

            # 保持历史记录在合理范围内
            if len(self.render_history) > 100:
                self.render_history = self.render_history[-50:]

    def _record_render_error(self, template_name: str, start_time: datetime, error: str) -> None:
        """记录渲染错误

        Args:
            template_name: 模板名称
            start_time: 开始时间
            error: 错误信息

        """
        self.error_count += 1

        if self.debug_mode:
            render_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            record = {
                "template": template_name,
                "status": "error",
                "render_time": render_time,
                "error": error,
                "timestamp": start_time,
            }
            self.render_history.append(record)

            # 保持历史记录在合理范围内
            if len(self.render_history) > 100:
                self.render_history = self.render_history[-50:]

        logger.error(f"Template render error for {template_name}: {error}")

    def set_debug_mode(self, enabled: bool) -> None:
        """设置调试模式

        Args:
            enabled: 是否启用调试模式

        """
        self.debug_mode = enabled
        logger.info(f"Template renderer debug mode: {'enabled' if enabled else 'disabled'}")

    def get_render_stats(self) -> dict[str, Any]:
        """获取渲染统计信息

        Returns:
            Dict[str, Any]: 统计信息

        """
        return {
            "render_count": self.render_count,
            "error_count": self.error_count,
            "success_rate": (self.render_count - self.error_count) / max(self.render_count, 1),
            "debug_mode": self.debug_mode,
            "strict_undefined": self.strict_undefined,
        }

    def get_render_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取渲染历史

        Args:
            limit: 返回记录数量限制

        Returns:
            List[Dict[str, Any]]: 渲染历史记录

        """
        return self.render_history[-limit:] if self.render_history else []

    def clear_history(self) -> None:
        """清空渲染历史"""
        self.render_history.clear()
        logger.info("Render history cleared")

    def validate_template_syntax(self, template_string: str) -> list[str]:
        """验证模板语法

        Args:
            template_string: 模板字符串

        Returns:
            List[str]: 错误列表，空列表表示语法正确

        """
        errors = []

        try:
            # 尝试解析模板
            jinja2.Template(
                template_string,
                undefined=jinja2.StrictUndefined if self.strict_undefined else jinja2.Undefined,
            )
        except jinja2.TemplateSyntaxError as e:
            errors.append(f"Syntax error at line {e.lineno}: {e.message}")
        except jinja2.TemplateError as e:
            errors.append(f"Template error: {e}")
        except Exception as e:
            # Intentional tolerance: validation method collects ALL errors instead of raising
            # This allows caller to get complete error list for better UX
            errors.append(f"Unexpected error: {e}")

        return errors

    def extract_variables(self, template_string: str) -> list[str]:
        """提取模板中的变量

        Args:
            template_string: 模板字符串

        Returns:
            List[str]: 变量名列表

        """
        try:
            env = jinja2.Environment()
            ast = env.parse(template_string)
            variables = jinja2.meta.find_undeclared_variables(ast)
            return sorted(variables)
        except Exception:
            # Intentional tolerance: variable extraction is best-effort utility
            # Returning empty list is safe - caller will see no variables
            logger.exception("Failed to extract variables from template: ")
            return []
