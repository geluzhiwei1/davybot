# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Handler for client tool-approval responses (P2.2).

When the frontend replies to a ``tool_approval_request``, this resolves the
pending future inside ``approval_gate`` so the waiting tool execution proceeds
(approved) or raises PermissionError (denied).
"""

from __future__ import annotations

import logging
from typing import List

from dawei.core.approval_gate import approval_gate
from dawei.websocket.handlers.base import BaseWebSocketMessageHandler
from dawei.websocket.protocol import (
    BaseWebSocketMessage,
    MessageType,
    ToolApprovalResponseMessage,
)

logger = logging.getLogger(__name__)


class ToolApprovalHandler(BaseWebSocketMessageHandler):
    """Resolves pending tool-approval requests from the client."""

    async def handle(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        message_id: str,
    ) -> BaseWebSocketMessage | None:
        if not isinstance(message, ToolApprovalResponseMessage):
            return None
        resolved = approval_gate.resolve(message.request_id, message.approved)
        if not resolved:
            logger.warning(
                "ToolApprovalHandler: no pending request for request_id=%s "
                "(already resolved or timed out)",
                message.request_id,
            )
        # No direct reply — resolving the future unblocks the waiting tool.
        return None

    def get_supported_types(self) -> List[str]:
        return [MessageType.TOOL_APPROVAL_RESPONSE]
