# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only
"""
统一插件配置系统 - 基于 JSON Schema 的动态配置

使用 JSON Schema Draft 7 标准，实现统一的插件配置管理。
所有插件通过 JSON Schema 定义其配置，前端自动生成表单，后端自动验证。

参考：
- JSON Schema: https://json-schema.org/draft-2020-12/schema
- Alpine.js settings: https://www.alpinejs.dev/plugins/settings
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import StrEnum
import json
import logging
from pathlib import Path

from dawei.core.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


# ============================================================================
# JSON Schema 类型映射
# ============================================================================

class JsonSchemaType(StrEnum):
    """JSON Schema 类型枚举"""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"
    NULL = "null"


# ============================================================================
# 插件配置模型
# ============================================================================

class PluginConfigField(BaseModel):
    """单个配置字段的定义"""
    name: str = Field(..., description="字段名称")
    type: JsonSchemaType = Field(..., description="JSON Schema 类型")
    description: str = Field("", description="字段描述")
    default: Any = Field(None, description="默认值")
    required: bool = Field(False, description="是否必填")
    enum: Optional[List[str]] = Field(None, description="枚举值列表")
    minimum: Optional[float] = Field(None, description="最小值（数字类型）")
    maximum: Optional[float] = Field(None, description="最大值（数字类型）")
    pattern: Optional[str] = Field(None, description="正则表达式（字符串类型）")
    format: Optional[str] = Field(None, description="格式（如 email、uri、date-time）")

    def to_schema(self) -> Dict[str, Any]:
        """转换为 JSON Schema 格式"""
        schema: Dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }

        if self.required:
            schema["required"] = True

        if self.default is not None:
            schema["default"] = self.default

        if self.enum:
            schema["enum"] = self.enum

        if self.minimum is not None:
            schema["minimum"] = self.minimum

        if self.maximum is not None:
            schema["maximum"] = self.maximum

        if self.pattern:
            schema["pattern"] = self.pattern

        if self.format:
            schema["format"] = self.format

        return schema


class PluginConfigManifest(BaseModel):
    """插件配置清单 - 完整的配置 schema"""

    schema_version: str = Field("1.0", description="Schema 版本")
    schema_type: str = Field(..., description="Schema 类型：object, array, or custom")
    title: str = Field(..., description="配置标题")
    description: str = Field("", description="配置描述")
    properties: List[PluginConfigField] = Field(
        default_factory=list,
        description="配置字段列表"
    )
    required: List[str] = Field(
        default_factory=list,
        description="必填字段名称列表"
    )

    def to_json_schema(self) -> Dict[str, Any]:
        """转换为完整的 JSON Schema"""
        schema: Dict[str, Any] = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": f"plugin_config_{self.schema_type}",
            "title": self.title,
            "description": self.description,
            "type": "object",
            "properties": {},
            "required": self.required,
        }

        # 添加所有字段
        for field in self.properties:
            schema["properties"][field.name] = field.to_schema()

        return schema

    def to_form_config(self) -> Dict[str, Any]:
        """转换为前端表单配置"""
        return {
            "schema": self.to_json_schema(),
            "uiConfig": {
                "title": self.title,
                "description": self.description,
                "submitLabel": "保存配置",
                "resetLabel": "重置为默认",
            }
        }


# ============================================================================
# 插件配置存储和加载
# ============================================================================

class PluginConfigManager:
    """插件配置管理器 - 统一的配置存储和加载

    支持二级插件机制：
    1. 工作区级插件：{workspace}/.dawei/plugins/{plugin_name}/
       配置文件：{workspace}/.dawei/plugins/{plugin_name}.json
    2. 用户级插件：~/.dawei/plugins/{plugin_name}/
       配置文件：~/.dawei/plugins/{plugin_name}.json
    """

    def __init__(self, workspace_path: Path | None = None):
        """初始化插件配置管理器

        Args:
            workspace_path: 工作区路径（可选）
                - 提供：工作区级插件配置
                - None：用户级插件配置（~/.dawei/plugins/）
        """
        self.workspace_path = workspace_path

        if workspace_path:
            # 工作区级插件：{workspace}/.dawei/plugins/
            self.config_dir = workspace_path / ".dawei" / "plugins"
        else:
            # 用户级插件：~/.dawei/plugins/
            home = Path.home()
            self.config_dir = home / ".dawei" / "plugins"

        self.config_dir.mkdir(parents=True, exist_ok=True)

    def get_config_file(self, plugin_id: str) -> Path:
        """获取插件配置文件路径

        Args:
            plugin_id: 插件ID（支持 name@version 格式）

        Returns:
            配置文件路径：{config_dir}/{plugin_id}.json
            例如：.dawei/plugins/feishu-channel@0.1.0.json
        """
        # 使用完整的 plugin_id 作为文件名（包含版本号）
        return self.config_dir / f"{plugin_id}.json"

    def load_plugin_config(self, plugin_id: str) -> Dict[str, Any]:
        """加载插件配置

        Args:
            plugin_id: 插件ID

        Returns:
            配置字典，如果文件不存在返回空字典

        Raises:
            ConfigurationError: 配置文件格式错误
        """
        config_file = self.get_config_file(plugin_id)

        if not config_file.exists():
            logger.debug(f"Plugin config not found: {config_file}")
            return {}

        try:
            with config_file.open("r", encoding="utf-8") as f:
                config = json.load(f)
                logger.info(f"Loaded plugin config: {config_file}")
                return config
        except (json.JSONDecodeError, IOError) as e:
            raise ConfigurationError(
                f"Invalid plugin config file {config_file}: {e}"
            )

    def save_plugin_config(self, plugin_id: str, config: Dict[str, Any]) -> None:
        """保存插件配置

        Args:
            plugin_id: 插件ID
            config: 配置字典

        Raises:
            ConfigurationError: 保存失败
        """
        config_file = self.get_config_file(plugin_id)

        try:
            # Ensure directory exists
            config_file.parent.mkdir(parents=True, exist_ok=True)

            with config_file.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved plugin config: {config_file}")
        except IOError as e:
            raise ConfigurationError(
                f"Failed to save plugin config {config_file}: {e}"
            )

    def delete_plugin_config(self, plugin_id: str) -> None:
        """删除插件配置（恢复默认）"""
        config_file = self.get_config_file(plugin_id)
        if config_file.exists():
            config_file.unlink()


# ============================================================================
# 辅助函数
# ============================================================================

def validate_config_against_schema(
    config: Dict[str, Any],
    schema: Dict[str, Any]
) -> bool:
    """
    验证配置是否符合 Schema

    Args:
        config: 用户提供的配置值
        schema: JSON Schema 定义

    Returns:
        True 如果验证通过，False 否则
    """
    try:
        # 简单验证：检查必填字段
        for field_name, field_def in schema.get("properties", {}).items():
            if field_name in schema.get("required", []):
                if field_name not in config:
                    return False

            # 类型验证
            field_type = field_def.get("type")
            if field_name in config:
                value = config[field_name]

                # 基本类型检查
                if field_type == JsonSchemaType.STRING:
                    if not isinstance(value, str):
                        return False
                elif field_type == JsonSchemaType.NUMBER:
                    if not isinstance(value, (int, float)):
                        return False
                elif field_type == JsonSchemaType.BOOLEAN:
                    if not isinstance(value, bool):
                        return False
                elif field_type == JsonSchemaType.INTEGER:
                    if not isinstance(value, int):
                        return False
                elif field_type == JsonSchemaType.ARRAY:
                    if not isinstance(value, list):
                        return False
                elif field_type == JsonSchemaType.OBJECT:
                    if not isinstance(value, dict):
                        return False

        return True

    except Exception:
        return False
