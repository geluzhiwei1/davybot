# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""A2UI WebSocket Handlers

Handles A2UI-related WebSocket messages:
- a2ui_server_event: Server sends UI updates to client
- a2ui_user_action: Client sends user actions to server
"""

import logging
from typing import Any

from dawei.websocket.protocol import (
    A2UIServerEventMessage,
    A2UIUserActionMessage,
)

logger = logging.getLogger(__name__)


async def handle_a2ui_user_action(
    message: A2UIUserActionMessage,
    websocket,
    session_id: str,
) -> dict[str, Any]:
    """Handle A2UI user action message from client.

    Args:
        message: A2UIUserActionMessage instance
        websocket: WebSocket connection instance
        session_id: Current session ID

    Returns:
        Response dictionary

    """
    try:
        logger.info(
            f"[A2UI] User action: surface_id={message.surface_id}, component_id={message.component_id}, action={message.action_name}",
        )

        # Here you can:
        # 1. Route the action to the appropriate handler
        # 2. Execute business logic
        # 3. Send back updated UI state if needed

        # For now, just acknowledge the action
        response = {
            "status": "success",
            "surface_id": message.surface_id,
            "component_id": message.component_id,
            "action": message.action_name,
            "message": f"Action '{message.action_name}' received",
        }

        logger.info(f"[A2UI] User action processed: {response}")

        return response

    except Exception as e:
        logger.error("[A2UI] Error handling user action:", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to process user action",
        }


def send_a2ui_update(
    websocket,
    surface_id: str,
    components: list,
    data_model: dict[str, Any],
    metadata: dict[str, Any],
    session_id: str,
) -> None:
    """Send A2UI surface update to client.

    Args:
        websocket: WebSocket connection instance
        surface_id: Surface ID
        components: List of component definitions
        data_model: Data model state
        metadata: Surface metadata (title, description, etc.)
        session_id: Session ID

    """
    try:
        message = A2UIServerEventMessage(
            messages=[
                {
                    "beginRendering": {
                        "surfaceId": surface_id,
                        "root": components[0]["id"] if components else "",
                        "styles": {},
                    },
                },
                {
                    "surfaceUpdate": {
                        "surfaceId": surface_id,
                        "components": components,
                    },
                },
                {
                    "dataModelUpdate": {
                        "surfaceId": surface_id,
                        "contents": [{"key": k, "value": v} for k, v in data_model.items()],
                    },
                },
            ],
            metadata=metadata,
            session_id=session_id,
        )

        # Send via WebSocket
        websocket.send_json(message.to_dict())

        logger.info(f"[A2UI] Sent surface update: {surface_id}")

    except Exception:
        logger.error("[A2UI] Error sending update:", exc_info=True)
