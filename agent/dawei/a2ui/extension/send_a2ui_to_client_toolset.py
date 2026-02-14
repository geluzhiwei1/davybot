# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei A2UI Tool - Send A2UI to client tool

This module provides a tool for agents to send A2UI (Agent-to-User Interface)
JSON payloads to a client. It includes validation and WebSocket integration.

Key Components:
  * `SendA2uiToClientTool`: A tool that validates and sends A2UI JSON to the client
  * `create_a2ui_tool`: Factory function to create A2UI tool with custom schema

Usage Example:

    ```python
    from dawei.a2ui.extension import create_a2ui_tool, SendA2uiToClientTool

    # Create tool with default schema
    tool = SendA2uiToClientTool()

    # Or create with custom schema
    custom_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "component": {"type": "object"}
            }
        }
    }
    tool = create_a2ui_tool(a2ui_schema=custom_schema)

    # Use in agent tool execution
    result = await tool.run_async(
        args={"a2ui_json": '{"id": "btn1", "component": {"type": "Button"}}'},
        tool_context=context
    )
    ```
"""

import json
import logging
from typing import Any

import jsonschema

from dawei.a2ui.extension.a2ui_extension import A2UI_MIME_TYPE, create_a2ui_message
from dawei.a2ui.extension.a2ui_schema_utils import validate_a2ui_json, wrap_as_json_array

logger = logging.getLogger(__name__)


class SendA2uiToClientTool:
    """Tool for sending validated A2UI JSON to the client.

    This tool accepts A2UI JSON strings from the LLM, validates them against
    a schema, and returns them in a format suitable for WebSocket transmission.

    Attributes:
        a2ui_schema: JSON Schema for validation
        tool_name: Name of the tool (default: "send_a2ui_json_to_client")

    """

    TOOL_NAME = "send_a2ui_json_to_client"
    A2UI_JSON_ARG_NAME = "a2ui_json"
    VALIDATED_A2UI_JSON_KEY = "validated_a2ui_json"
    TOOL_ERROR_KEY = "error"

    def __init__(self, a2ui_schema: dict[str, Any] | None = None):
        """Initialize the A2UI tool.

        Args:
            a2ui_schema: Optional JSON Schema for validation.
                        If None, uses a basic component schema.

        """
        self._a2ui_schema = a2ui_schema or self._get_default_schema()

    def _get_default_schema(self) -> dict[str, Any]:
        """Get the default A2UI component schema.

        Returns:
            Default JSON Schema for basic A2UI components
        """
        component_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "component": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                    },
                    "required": ["type"],
                    "additionalProperties": True,
                },
            },
            "required": ["id", "component"],
            "additionalProperties": True,
        }
        return wrap_as_json_array(component_schema)

    def get_tool_definition(self) -> dict[str, Any]:
        """Get the tool definition for LLM function calling.

        Returns:
            Tool definition dictionary

        """
        return {
            "name": self.TOOL_NAME,
            "description": (
                "Sends A2UI JSON to the client to render rich UI for the user."
                " This tool can be called multiple times to render multiple UI surfaces.\n"
                f"Args:\n"
                f"  {self.A2UI_JSON_ARG_NAME}: Valid A2UI JSON string to send to client."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    self.A2UI_JSON_ARG_NAME: {
                        "type": "string",
                        "description": "Valid A2UI JSON string to send to client.",
                    },
                },
                "required": [self.A2UI_JSON_ARG_NAME],
            },
        }

    async def validate_and_parse(
        self,
        a2ui_json: str,
    ) -> list[dict[str, Any]]:
        """Validate and parse A2UI JSON.

        Args:
            a2ui_json: JSON string containing A2UI components

        Returns:
            List of validated component dictionaries

        Raises:
            ValueError: If JSON is invalid or validation fails
            jsonschema.ValidationError: If validation fails

        """
        try:
            components = validate_a2ui_json(a2ui_json, self._a2ui_schema)
            logger.info(f"Validated A2UI JSON with {len(components)} component(s)")
            return components
        except jsonschema.ValidationError as e:
            logger.error(f"A2UI validation failed: {e.message}")
            raise ValueError(f"A2UI validation failed: {e.message}") from e
        except ValueError as e:
            logger.error(f"Invalid A2UI JSON: {e}")
            raise

    async def run_async(
        self,
        args: dict[str, Any],
        tool_context: Any,  # Could be ToolContext or similar
    ) -> dict[str, Any]:
        """Execute the tool asynchronously.

        Args:
            args: Tool arguments from LLM
            tool_context: Tool execution context

        Returns:
            Dictionary with validated components or error

        """
        try:
            a2ui_json = args.get(self.A2UI_JSON_ARG_NAME)
            if not a2ui_json:
                raise ValueError(
                    f"Missing required argument: {self.A2UI_JSON_ARG_NAME}"
                )

            # Validate and parse
            components = await self.validate_and_parse(a2ui_json)

            # Return validated components
            return {self.VALIDATED_A2UI_JSON_KEY: components}

        except Exception as e:
            error_msg = f"Failed to call A2UI tool {self.TOOL_NAME}: {e}"
            logger.exception(error_msg)
            return {self.TOOL_ERROR_KEY: error_msg}

    def create_websocket_message(
        self,
        components: list[dict[str, Any]],
        surface_id: str,
        data_model: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a WebSocket message from validated components.

        Args:
            components: Validated A2UI component list
            surface_id: Surface identifier
            data_model: Optional data model state
            metadata: Optional surface metadata

        Returns:
            WebSocket message dictionary

        """
        return create_a2ui_message(
            surface_id=surface_id,
            components=components,
            data_model=data_model or {},
            metadata=metadata,
        )


def create_a2ui_tool(a2ui_schema: dict[str, Any] | None = None) -> SendA2uiToClientTool:
    """Factory function to create an A2UI tool with optional custom schema.

    Args:
        a2ui_schema: Optional custom JSON Schema for validation

    Returns:
        Configured SendA2uiToClientTool instance

    Example:
        >>> custom_schema = {
        ...     "type": "array",
        ...     "items": {
        ...         "type": "object",
        ...         "properties": {"id": {"type": "string"}}
        ...     }
        ... }
        >>> tool = create_a2ui_tool(a2ui_schema=custom_schema)
        >>> isinstance(tool, SendA2uiToClientTool)
        True
    """
    return SendA2uiToClientTool(a2ui_schema=a2ui_schema)


def get_a2ui_schema_with_instructions(
    component_types: list[str] | None = None,
) -> tuple[dict[str, Any], str]:
    """Get A2UI schema and LLM instructions.

    Args:
        component_types: Optional list of allowed component types.
                       If None, allows any component type.

    Returns:
        Tuple of (schema, instructions_string)

    Example:
        >>> schema, instructions = get_a2ui_schema_with_instructions(
        ...     component_types=["Button", "TextField"]
        ... )
        >>> schema["type"]
        'array'
        >>> "Button" in instructions
        True
    """
    if component_types:
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "component": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": component_types,
                            },
                        },
                        "required": ["type"],
                    },
                },
                "required": ["id", "component"],
            },
        }
        component_list = ", ".join(component_types)
        instructions = (
            f"Available A2UI component types: {component_list}.\n"
            "You can create rich UIs using these components.\n"
            "Each component must have an 'id' and a 'component' object with a 'type'."
        )
    else:
        schema = wrap_as_json_array(
            {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "component": {"type": "object"},
                },
                "required": ["id", "component"],
            }
        )
        instructions = (
            "You can create rich UIs using A2UI components.\n"
            "Each component must have an 'id' and a 'component' object with a 'type'."
        )

    return schema, instructions
