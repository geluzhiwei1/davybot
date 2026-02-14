# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Enhanced Input Box

User input widget with command history support.
"""

from textual.message import Message
from textual.widgets import Input


class EnhancedInputBox(Input):
    """Enhanced user input widget with history support"""

    class MessageSubmitted(Message):
        """Message emitted when user submits input"""

        def __init__(self, message: str):
            super().__init__()
            self.message = message

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._history_index: int = -1

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission

        Args:
            event: Input submitted event

        """
        message = event.value.strip()

        if not message:
            return

        # Add to history (skip duplicates)
        if not self._history or self._history[-1] != message:
            self._history.append(message)

        # Reset history index
        self._history_index = -1

        # Clear input
        self.value = ""

        # Emit message to app
        self.post_message(self.MessageSubmitted(message))

    def on_key(self, event) -> None:
        """Handle key press for history navigation

        Args:
            event: Key event

        """
        # Handle Up Arrow - previous command
        if event.key == "up":
            self._navigate_history(-1)
            event.stop()
            return

        # Handle Down Arrow - next command
        if event.key == "down":
            self._navigate_history(1)
            event.stop()
            return

        # Default handling
        super().on_key(event)

    def _navigate_history(self, direction: int) -> None:
        """Navigate command history

        Args:
            direction: -1 for up (previous), 1 for down (next)

        """
        if not self._history:
            return

        # Calculate new index
        if direction == -1:  # Up arrow - go back
            if self._history_index == -1:
                # Start from most recent
                self._history_index = len(self._history) - 1
            elif self._history_index > 0:
                self._history_index -= 1
        elif self._history_index != -1:
            self._history_index += 1
            if self._history_index >= len(self._history):
                self._history_index = -1

        # Update input value
        if self._history_index == -1:
            self.value = ""
        else:
            self.value = self._history[self._history_index]

        # Move cursor to end
        self.cursor_position = len(self.value)

    def get_history(self) -> list[str]:
        """Get command history

        Returns:
            List of commands in history

        """
        return self._history.copy()

    def clear_history(self) -> None:
        """Clear command history"""
        self._history.clear()
        self._history_index = -1
