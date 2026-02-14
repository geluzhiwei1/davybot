# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""A2UI Surface Tool

Provides tools for creating and updating A2UI surfaces.
"""

import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field

from dawei.tools.custom_base_tool import CustomBaseTool

# For now, we'll define a simplified create_a2ui_part function
# TODO: Integrate official A2UI extension when a2a-sdk is installed


def create_a2ui_part(a2ui_data: dict[str, Any]) -> Any:
    """Create an A2UI part (simplified version)."""
    return {"data": a2ui_data, "mimeType": "application/json+a2ui"}


logger = logging.getLogger(__name__)


class CreateA2UISurfaceTool(CustomBaseTool):
    """Create an A2UI Surface - generates declarative UI components.

    This tool allows AI agents to create safe, cross-platform UI components
    using A2UI's JSON format.

    Example:
        create_a2ui_surface(
            title="User Registration Form",
            surface_type="form",
            components=[...],
            data_model={"username": "", "email": ""}
        )

    """

    name = "create_a2ui_surface"
    description = """Create a declarative UI surface using A2UI (Agent-to-User Interface).

    Use this tool when you need to:
    - Generate interactive forms (user input, surveys, etc.)
    - Create data visualizations (charts, tables, cards)
    - Display dashboards with controls
    - Show modal dialogs or tabs

    The UI is rendered on the client side using Element Plus components, ensuring
    a consistent, native look and feel with no code execution risks.

    Args:
        title: Surface title (shown in header)
        description: Optional surface description
        surface_type: Type of surface ('form', 'dashboard', 'visualization', 'custom')
        components: List of A2UI component definitions (flat adjacency list)
        data_model: Initial data model for the UI state
        root_component_id: ID of the root component (first component if not specified)
    """

    class Args(BaseModel):
        """Arguments for creating an A2UI surface."""

        title: str = Field(..., description="Surface title displayed in the UI header")
        description: str | None = Field(
            None,
            description="Optional description of the surface purpose",
        )
        surface_type: str = Field(
            "custom",
            description="Type of surface: 'form', 'dashboard', 'visualization', or 'custom'",
        )
        components: list[dict[str, Any]] = Field(
            ...,
            description="List of A2UI component definitions. Each component must have 'id', 'type', and 'component' properties with component-specific properties.",
        )
        data_model: dict[str, Any] = Field(
            default_factory=dict,
            description="Initial data model for UI state. Keys are JSON Pointer paths, values are the data.",
        )
        root_component_id: str | None = Field(
            None,
            description="ID of the root component. If not specified, uses the first component's ID.",
        )
        layout: str | None = Field(
            None,
            description="Layout direction: 'vertical', 'horizontal', or 'grid'",
        )

    def _run(self, **kwargs) -> str:
        """Execute the tool to create an A2UI surface."""
        try:
            args = self.Args(**kwargs)

            # Generate unique surface ID
            surface_id = f"surface_{uuid.uuid4().hex[:8]}"

            # Use first component as root if not specified
            root_id = args.root_component_id or (args.components[0]["id"] if args.components else "")

            # Build A2UI message (official format)
            a2ui_data = {
                "messages": [
                    # Begin rendering message
                    {
                        "beginRendering": {
                            "surfaceId": surface_id,
                            "root": root_id,
                            "styles": {},
                        },
                    },
                    # Surface update message (component tree)
                    {
                        "surfaceUpdate": {
                            "surfaceId": surface_id,
                            "components": args.components,
                        },
                    },
                    # Data model update message
                    {
                        "dataModelUpdate": {
                            "surfaceId": surface_id,
                            "contents": [{"key": k, "value": v} for k, v in args.data_model.items()],
                        },
                    },
                ],
                "metadata": {
                    "title": args.title,
                    "description": args.description,
                    "interactive": True,
                    "layout": args.layout or "vertical",
                },
            }

            # Return special A2UI marker format for tool executor to process
            # This format will be detected by tool_message_handler and sent via WebSocket
            return {
                "__a2ui__": True,  # Marker for A2UI data
                "surface_id": surface_id,
                "title": args.title,
                "description": args.description,
                "surface_type": args.surface_type,
                "a2ui_data": a2ui_data,  # Full A2UI data for WebSocket transmission
                "message": f"Created A2UI surface '{args.title}' with {len(args.components)} components",
            }

        except Exception as e:
            logger.error("[A2UI] Error creating surface:", exc_info=True)
            raise ValueError(f"Failed to create A2UI surface: {e!s}")


class UpdateA2UIDataTool(CustomBaseTool):
    """Update A2UI Data Model - updates the state of an existing surface.

    This tool allows you to update the data model of a previously created surface,
    triggering UI re-renders with the new data.

    Example:
        update_a2ui_data(
            surface_id="surface_abc123",
            path="/users/0/name",
            value="John Doe"
        )

    """

    name = "update_a2ui_data"
    description = """Update the data model of an existing A2UI surface.

    Use this tool to:
    - Update form field values
    - Refresh data in visualizations
    - Modify UI state based on user actions or backend processing

    The update uses JSON Pointer (RFC 6901) for precise path targeting.

    Args:
        surface_id: ID of the surface to update (returned by create_a2ui_surface)
        path: JSON Pointer path to update (e.g., '/users/0/name', '/form/username')
        value: New value to set at the path
    """

    class Args(BaseModel):
        """Arguments for updating A2UI data."""

        surface_id: str = Field(
            ...,
            description="ID of the surface to update (e.g., 'surface_abc123')",
        )
        path: str = Field(
            ...,
            description="JSON Pointer path to update (e.g., '/users/0/name', '/form/username')",
        )
        value: Any = Field(..., description="New value to set at the specified path")

    def _run(self, **kwargs) -> str:
        """Execute the tool to update A2UI data model."""
        try:
            args = self.Args(**kwargs)

            # Build A2UI data model update message
            a2ui_data = {
                "messages": [
                    {
                        "dataModelUpdate": {
                            "surfaceId": args.surface_id,
                            "path": args.path,
                            "contents": [{"key": args.path, "value": args.value}],
                        },
                    },
                ],
            }

            # Return special A2UI marker format for tool executor to process
            return {
                "__a2ui__": True,  # Marker for A2UI data
                "surface_id": args.surface_id,
                "update_type": "data_model",
                "a2ui_data": a2ui_data,  # Full A2UI data for WebSocket transmission
                "message": f"Updated A2UI surface '{args.surface_id}': {args.path} = {args.value}",
            }

        except Exception as e:
            logger.error("[A2UI] Error updating data model:", exc_info=True)
            raise ValueError(f"Failed to update A2UI data model: {e!s}")
