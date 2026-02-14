# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei A2UI Extension - Core A2UI functionality

This module provides core A2UI functionality without external dependencies:
- Create A2UI messages for WebSocket transmission
- Validate A2UI schema
- Parse and check A2UI content
"""

import json
import logging
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

# A2UI Protocol Constants
A2UI_EXTENSION_URI = "https://a2ui.org/dawei-extension/a2ui/v1.0"
A2UI_MIME_TYPE = "application/json+a2ui"
STANDARD_CATALOG_ID = "https://a2ui.org/specification/v1_0/standard_catalog_definition.json"


def create_a2ui_message(
    surface_id: str,
    components: list[dict[str, Any]],
    data_model: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an A2UI message for WebSocket transmission.

    Args:
        surface_id: Unique surface identifier
        components: List of A2UI component definitions
        data_model: Data model state for the surface
        metadata: Optional surface metadata (title, description, etc.)

    Returns:
        A2UI message dictionary ready for JSON serialization

    Example:
        >>> components = [{"id": "btn1", "component": {"type": "Button", ...}}]
        >>> data_model = {"/btn1": "clicked"}
        >>> msg = create_a2ui_message("surface1", components, data_model)
        >>> json.dumps(msg)
    """
    message = {
        "surface_id": surface_id,
        "components": components,
        "data_model": data_model,
        "mime_type": A2UI_MIME_TYPE,
    }

    if metadata:
        message["metadata"] = metadata

    return message


def is_a2ui_message(data: dict[str, Any]) -> bool:
    """Check if a dictionary contains A2UI data.

    Args:
        data: Dictionary to check

    Returns:
        True if the dictionary appears to be A2UI data

    """
    return (
        isinstance(data, dict)
        and data.get("mime_type") == A2UI_MIME_TYPE
        or "components" in data
        and "surface_id" in data
    )


def validate_a2ui_schema(
    schema: dict[str, Any],
    instance: dict[str, Any] | list[dict[str, Any]],
) -> bool:
    """Validate A2UI schema using JSON Schema validation.

    Args:
        schema: JSON Schema for validation
        instance: Data to validate (can be dict or list)

    Returns:
        True if validation passes

    Raises:
        jsonschema.ValidationError: If validation fails
        jsonschema.SchemaError: If schema is invalid

    Example:
        >>> schema = {
        ...     "type": "array",
        ...     "items": {
        ...         "type": "object",
        ...         "properties": {
        ...             "id": {"type": "string"},
        ...             "component": {"type": "object"}
        ...         }
        ...     }
        ... }
        >>> data = [{"id": "btn1", "component": {"type": "Button"}}]
        >>> validate_a2ui_schema(schema, data)
        True
    """
    try:
        jsonschema.validate(instance=instance, schema=schema)
        logger.info("A2UI schema validation passed")
        return True
    except jsonschema.ValidationError as e:
        logger.error(f"A2UI schema validation failed: {e.message}")
        raise
    except jsonschema.SchemaError as e:
        logger.error(f"A2UI schema is invalid: {e.message}")
        raise


def wrap_as_json_array(a2ui_schema: dict[str, Any]) -> dict[str, Any]:
    """Wrap A2UI schema in an array structure.

    This is useful when you want to support multiple components in a single schema.

    Args:
        a2ui_schema: The A2UI schema to wrap

    Returns:
        Wrapped schema with array type

    Raises:
        ValueError: If the schema is empty

    Example:
        >>> schema = {"type": "object", "properties": {...}}
        >>> wrapped = wrap_as_json_array(schema)
        >>> assert wrapped["type"] == "array"
    """
    if not a2ui_schema:
        raise ValueError("A2UI schema cannot be empty")

    return {"type": "array", "items": a2ui_schema}


def extract_surface_data(message: dict[str, Any]) -> dict[str, Any] | None:
    """Extract surface data from an A2UI message.

    Args:
        message: A2UI message dictionary

    Returns:
        Dictionary with surface_id, components, data_model, or None if invalid

    """
    if not is_a2ui_message(message):
        return None

    return {
        "surface_id": message.get("surface_id"),
        "components": message.get("components", []),
        "data_model": message.get("data_model", {}),
        "metadata": message.get("metadata", {}),
    }
