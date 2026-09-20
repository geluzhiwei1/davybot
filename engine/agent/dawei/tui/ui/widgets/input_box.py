# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""InputBox Widget

User input widget for sending messages to the Agent.
"""

from textual.message import Message
from textual.widgets import Input


class InputBox(Input):
    """User input widget with message submission"""

    # Override default Input binding to allow Ctrl+H and F1 to show help at app level
    BINDINGS = [
        ("ctrl+h", "app.show_help", "Help"),
        ("f1", "app.show_help", "Help"),
    ]

    class MessageSubmitted(Message):
        """Message emitted when user submits input"""

        def __init__(self, message: str):
            super().__init__()
            self.message = message

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission

        Args:
            event: Input submitted event

        """
        message = event.value.strip()

        if not message:
            return

        # Clear input
        self.value = ""

        # Emit message to app
        self.post_message(self.MessageSubmitted(message))
