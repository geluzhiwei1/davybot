# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared validators for DavyBot plugins.

This file is duplicated in services/agent-api/dawei/plugins/validators.py
for runtime use. Keep both files in sync.
"""

import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)


# Regex patterns
PLUGIN_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$")


class DependencySpec(BaseModel):
    """Plugin dependency specification"""

    pypi: list[str] = Field(default_factory=list)
    system: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)


class ConfigProperty(BaseModel):
    """Configuration schema property"""

    type: str
    default: Any | None = None
    description: str | None = None
    enum: list[Any] | None = None
    format: str | None = None
    pattern: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = None
    max_length: int | None = None


class ConfigSchema(BaseModel):
    """Configuration schema"""

    type: str = "object"
    properties: dict[str, ConfigProperty] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)
    additional_properties: bool = True


class PluginSettings(BaseModel):
    """Plugin settings"""

    enabled: bool = True
    priority: int = 50
    auto_activate: bool = False
    timeout: float = 30.0
    max_retries: int = 3


class PluginManifest(BaseModel):
    """Plugin manifest validator for plugin.yaml files.

    This validates the structure and content of plugin.yaml files.
    """

    api_version: str = Field(..., pattern=r"^\d+\.\d+$")
    name: str = Field(..., min_length=1, max_length=100)
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+")
    description: str = Field(..., min_length=1, max_length=500)
    author: str = Field(..., min_length=1, max_length=100)
    license: str = Field(default="MIT", min_length=1, max_length=50)
    python_version: str = Field(default=">=3.12")

    plugin_type: str = Field(..., alias="type")
    entry_point: str = Field(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_.]*:[A-Z][a-zA-Z0-9_]*$")

    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    config_schema: dict[str, Any] | str = Field(default_factory=dict)
    hooks: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Validate plugin name format"""
        if not PLUGIN_NAME_PATTERN.match(v):
            raise ValueError(
                f"Invalid plugin name '{v}'. Must be lowercase alphanumeric with hyphens, start and end with alphanumeric.",
            )
        return v

    @field_validator("plugin_type")
    @classmethod
    def validate_plugin_type(cls, v):
        """Validate plugin type"""
        valid_types = ["channel", "tool", "service", "memory"]
        if v not in valid_types:
            raise ValueError(f"Invalid plugin type '{v}'. Must be one of: {', '.join(valid_types)}")
        return v

    @field_validator("version")
    @classmethod
    def validate_version(cls, v):
        """Validate semantic version"""
        if not VERSION_PATTERN.match(v):
            raise ValueError(
                f"Invalid version '{v}'. Must follow semantic versioning: MAJOR.MINOR.PATCH",
            )
        return v

    @field_validator("python_version")
    @classmethod
    def validate_python_version(cls, v):
        """Validate Python version specifier"""
        if not v.startswith(">=") and not v.startswith("=="):
            raise ValueError(f"Invalid Python version '{v}'. Must start with '>=' or '=='")
        return v

    @field_validator("entry_point")
    @classmethod
    def validate_entry_point(cls, v):
        """Validate entry point format"""
        if ":" not in v:
            raise ValueError(f"Invalid entry point '{v}'. Must be in format 'module:ClassName'")
        return v

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, v):
        """Validate dependencies structure"""
        valid_keys = ["pypi", "system", "plugins"]
        for key in v:
            if key not in valid_keys:
                raise ValueError(
                    f"Invalid dependency type '{key}'. Must be one of: {', '.join(valid_keys)}",
                )

            if not isinstance(v[key], list):
                raise ValueError(f"Dependencies '{key}' must be a list")

        return v
    @field_validator("hooks")
    @classmethod
    def validate_hooks(cls, v):
        """Validate event hooks"""
        valid_hooks = [
            "before_tool_call",
            "after_tool_call",
            "on_task_start",
            "on_task_complete",
            "on_task_error",
            "on_agent_start",
            "on_agent_complete",
            "on_agent_error",
            "on_message_sent",
            "on_message_received",
            "on_error",
            "on_checkpoint",
        ]

        for hook in v:
            if hook not in valid_hooks:
                logger.warning(f"Unknown hook '{hook}'. Known hooks: {valid_hooks}")

        return v

    @field_validator("config_schema")
    @classmethod
    def validate_config_schema(cls, v):
        """Validate configuration schema.

        Supports two formats only:
        1. File path string: "./config_schema.json" - loaded by PluginLoader
        2. Standard JSON Schema (direct):
           config_schema:
             type: object
             properties: {...}
             required: [...]
             additionalProperties: boolean

        Old nested format (schema + ui_schema) is NOT supported.

        Note: String paths are validated here but loaded by PluginLoader.
        """
        # Skip validation for string paths (will be loaded by PluginLoader)
        if isinstance(v, str):
            # Basic validation: check if it looks like a file path
            if not (v.startswith("./") or v.startswith("../") or v.startswith("/")):
                logger.warning(f"config_schema path '{v}' should be a relative or absolute file path")
            return v

        # Accept empty schema
        if not v:
            return v

        # Reject old nested format (schema + ui_schema)
        if "schema" in v or "ui_schema" in v:
            raise ValueError(
                "Old nested config_schema format (schema + ui_schema) is no longer supported. "
                "Use standard JSON Schema format with type/properties/required, or reference a JSON file: config_schema: './config_schema.json'"
            )

        # Validate standard JSON Schema format (has 'type' directly)
        if "type" in v:
            if v["type"] != "object":
                raise ValueError("config_schema type must be 'object'")

            if "properties" in v and not isinstance(v["properties"], dict):
                raise ValueError("config_schema 'properties' must be a dictionary")

            if "required" in v and not isinstance(v["required"], list):
                raise ValueError("config_schema 'required' must be a list")

            # Additional properties are optional
            if "additionalProperties" in v and not isinstance(v["additionalProperties"], bool):
                raise ValueError("config_schema 'additionalProperties' must be a boolean")

            # Additional standard JSON Schema keys are allowed (title, description, $schema, etc.)
            return v

        # If we get here, format is invalid
        raise ValueError(
            "config_schema must be either:\n"
            "1. A file path string: './config_schema.json'\n"
            "2. Standard JSON Schema with 'type: object' at root\n"
            "Old nested format (schema + ui_schema) is NOT supported."
        )

    @field_validator("settings")
    @classmethod
    def validate_settings(cls, v):
        """Validate plugin settings"""
        if "enabled" in v and not isinstance(v["enabled"], bool):
            raise ValueError("setting 'enabled' must be a boolean")

        if "priority" in v:
            if not isinstance(v["priority"], int):
                raise ValueError("setting 'priority' must be an integer")
            if v["priority"] < 0 or v["priority"] > 100:
                raise ValueError("setting 'priority' must be between 0 and 100")

        if "auto_activate" in v and not isinstance(v["auto_activate"], bool):
            raise ValueError("setting 'auto_activate' must be a boolean")

        return v


class PluginConfigValidator:
    """Validate plugin configuration against schema."""

    @staticmethod
    def validate_config(config: dict[str, Any], schema: dict[str, Any]) -> bool:
        """Validate configuration against schema.

        Args:
            config: Configuration to validate
            schema: JSON schema

        Returns:
            True if valid

        Raises:
            ValueError: If configuration is invalid

        """
        if not schema:
            return True

        # Check required fields
        required = schema.get("required", [])
        for field in required:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")

        # Check each property
        properties = schema.get("properties", {})
        for field, value in config.items():
            if field not in properties:
                if not schema.get("additional_properties", True):
                    raise ValueError(f"Unexpected field: {field}")
                continue

            prop_schema = properties[field]
            PluginConfigValidator._validate_property(field, value, prop_schema)

        return True

    @staticmethod
    def _validate_property(field: str, value: Any, schema: dict[str, Any]) -> None:
        """Validate a single property against schema"""
        expected_type = schema.get("type")

        if expected_type == "string":
            if not isinstance(value, str):
                raise ValueError(f"Field '{field}' must be a string")

            # Check min/max length
            if "min_length" in schema and len(value) < schema["min_length"]:
                raise ValueError(
                    f"Field '{field}' must be at least {schema['min_length']} characters",
                )
            if "max_length" in schema and len(value) > schema["max_length"]:
                raise ValueError(
                    f"Field '{field}' must be at most {schema['max_length']} characters",
                )

            # Check pattern
            if "pattern" in schema:
                pattern = re.compile(schema["pattern"])
                if not pattern.match(value):
                    raise ValueError(f"Field '{field}' does not match required pattern")

            # Check format
            if "format" in schema and schema["format"] == "uri" and not value.startswith(("http://", "https://")):
                raise ValueError(f"Field '{field}' must be a valid URI")

            # Check enum
            if "enum" in schema and value not in schema["enum"]:
                raise ValueError(f"Field '{field}' must be one of: {schema['enum']}")

        elif expected_type == "integer":
            if not isinstance(value, int):
                raise ValueError(f"Field '{field}' must be an integer")

            if "minimum" in schema and value < schema["minimum"]:
                raise ValueError(f"Field '{field}' must be >= {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                raise ValueError(f"Field '{field}' must be <= {schema['maximum']}")

        elif expected_type == "number":
            if not isinstance(value, (int, float)):
                raise ValueError(f"Field '{field}' must be a number")

            if "minimum" in schema and value < schema["minimum"]:
                raise ValueError(f"Field '{field}' must be >= {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                raise ValueError(f"Field '{field}' must be <= {schema['maximum']}")

        elif expected_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"Field '{field}' must be a boolean")

        elif expected_type == "array":
            if not isinstance(value, list):
                raise ValueError(f"Field '{field}' must be an array")

        elif expected_type == "object":
            if not isinstance(value, dict):
                raise ValueError(f"Field '{field}' must be an object")


def validate_plugin_directory(plugin_dir: Path) -> tuple[bool, list[str]]:
    """Validate plugin directory structure.

    Args:
        plugin_dir: Path to plugin directory

    Returns:
        Tuple of (is_valid, error_messages)

    """
    errors = []
    warnings = []

    # Check directory exists
    if not plugin_dir.exists():
        errors.append(f"Plugin directory does not exist: {plugin_dir}")
        return False, errors

    # Check required files
    required_files = ["plugin.yaml", "plugin.py"]
    for filename in required_files:
        file_path = plugin_dir / filename
        if not file_path.exists():
            errors.append(f"Missing required file: {filename}")

    # Check README exists (recommended)
    readme_path = plugin_dir / "README.md"
    if not readme_path.exists():
        warnings.append("Missing recommended file: README.md")

    # Validate plugin.yaml
    yaml_path = plugin_dir / "plugin.yaml"
    if yaml_path.exists():
        try:
            from dawei.plugins.utils import load_yaml_file

            manifest_data = load_yaml_file(yaml_path)
            PluginManifest(**manifest_data)
        except ValidationError as e:
            errors.append(f"Invalid plugin.yaml: {e}")
        except Exception as e:
            errors.append(f"Error loading plugin.yaml: {e}")

    # Check tests directory (recommended, not required)
    tests_dir = plugin_dir / "tests"
    if not tests_dir.exists():
        warnings.append("Missing tests directory (recommended)")

    # Only log warnings, don't treat them as errors
    for warning in warnings:
        logger.warning(f"Plugin validation warning for {plugin_dir}: {warning}")

    # Plugin is valid if there are no critical errors
    is_valid = len(errors) == 0
    return is_valid, errors


def validate_plugin_yaml(yaml_path: Path) -> tuple[bool, PluginManifest, list[str]]:
    """Validate plugin.yaml file.

    Args:
        yaml_path: Path to plugin.yaml

    Returns:
        Tuple of (is_valid, manifest, error_messages)

    """
    errors = []

    if not yaml_path.exists():
        errors.append(f"plugin.yaml does not exist: {yaml_path}")
        return False, None, errors

    try:
        from dawei.plugins.utils import load_yaml_file

        manifest_data = load_yaml_file(yaml_path)
        manifest = PluginManifest(**manifest_data)
        return True, manifest, []
    except ValidationError as e:
        errors.append(f"Validation error: {e}")
        return False, None, errors
    except Exception as e:
        errors.append(f"Error loading plugin.yaml: {e}")
        return False, None, errors
