# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei A2UI Schema Utilities

Utilities for A2UI Schema manipulation and validation.
"""

import json
import logging
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)


def wrap_as_json_array(a2ui_schema: dict[str, Any]) -> dict[str, Any]:
    """Wrap the A2UI schema in an array object to support multiple parts.

    Args:
        a2ui_schema: The A2UI schema to wrap

    Returns:
        The wrapped A2UI schema object

    Raises:
        ValueError: If the A2UI schema is empty

    Example:
        >>> schema = {"type": "object", "properties": {...}}
        >>> wrapped = wrap_as_json_array(schema)
        >>> assert wrapped["type"] == "array"
    """
    if not a2ui_schema:
        raise ValueError("A2UI schema is empty")

    return {"type": "array", "items": a2ui_schema}


def create_a2ui_schema_from_components(component_types: list[str]) -> dict[str, Any]:
    """Create a JSON Schema from a list of component type names.

    Args:
        component_types: List of component type names (e.g., ["Button", "TextField"])

    Returns:
        JSON Schema dictionary for validation

    Example:
        >>> schema = create_a2ui_schema_from_components(["Button", "TextField"])
        >>> schema["items"]["properties"]["component"]["properties"]["type"]["enum"]
        ['Button', 'TextField']
    """
    component_schema = {
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
    }

    return wrap_as_json_array(component_schema)


def validate_a2ui_json(a2ui_json: str | dict[str, Any], schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate and parse A2UI JSON.

    Args:
        a2ui_json: JSON string or dictionary
        schema: JSON Schema for validation

    Returns:
        List of validated component dictionaries

    Raises:
        jsonschema.ValidationError: If validation fails
        ValueError: If JSON is invalid

    Example:
        >>> schema = create_a2ui_schema_from_components(["Button"])
        >>> json_str = '[{"id": "btn1", "component": {"type": "Button"}}]'
        >>> components = validate_a2ui_json(json_str, schema)
        >>> len(components)
        1
    """
    if isinstance(a2ui_json, str):
        try:
            data = json.loads(a2ui_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e
    else:
        data = a2ui_json

    # Auto-wrap single object in list
    if not isinstance(data, list):
        logger.info("Received a single JSON object, wrapping in a list for validation.")
        data = [data]

    jsonschema.validate(instance=data, schema=schema)

    return data


def merge_data_models(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Merge two A2UI data models.

    Args:
        base: Base data model
        update: Updates to apply (overrides base values)

    Returns:
        Merged data model

    Example:
        >>> base = {"/field1": "value1", "/field2": "value2"}
        >>> update = {"/field2": "new_value", "/field3": "value3"}
        >>> merged = merge_data_models(base, update)
        >>> assert merged["/field1"] == "value1"
        >>> assert merged["/field2"] == "new_value"
        >>> assert merged["/field3"] == "value3"
    """
    result = base.copy()
    result.update(update)
    return result


def extract_component_ids(components: list[dict[str, Any]]) -> list[str]:
    """Extract all component IDs from a list of components.

    Args:
        components: List of component dictionaries

    Returns:
        List of component IDs

    Example:
        >>> components = [
        ...     {"id": "btn1", "component": {...}},
        ...     {"id": "field1", "component": {...}}
        ... ]
        >>> ids = extract_component_ids(components)
        >>> set(ids) == {"btn1", "field1"}
        True
    """
    return [comp.get("id") for comp in components if "id" in comp]


def find_components_by_type(components: list[dict[str, Any]], component_type: str) -> list[dict[str, Any]]:
    """Find all components of a specific type.

    Args:
        components: List of component dictionaries
        component_type: Component type to filter by

    Returns:
        List of matching components

    Example:
        >>> components = [
        ...     {"id": "btn1", "component": {"type": "Button"}},
        ...     {"id": "field1", "component": {"type": "TextField"}}
        ... ]
        >>> buttons = find_components_by_type(components, "Button")
        >>> len(buttons)
        1
        >>> buttons[0]["id"]
        'btn1'
    """
    return [comp for comp in components if comp.get("component", {}).get("type") == component_type]
