# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Enhanced Chat Area

Rich chat display with markdown rendering and syntax highlighting.
"""

from datetime import datetime, timezone

from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static

from dawei.tui.ui.widgets.markdown_renderer import ChatMarkdown


class MessageBubble(Static):
    """Individual message bubble"""

    def __init__(self, content: str, role: str = "user", **kwargs):
        """Initialize message bubble

        Args:
            content: Message content
            role: Message role (user/assistant/system/error)

        """
        super().__init__(**kwargs)
        self.content = content
        self.role = role

    def compose(self):
        """Compose message content"""
        if self.role == "user":
            yield Static(f"[bold blue]You:[/bold blue] {self.content}")
        elif self.role == "assistant":
            # Use markdown for assistant messages
            yield Static("[bold green]Assistant:[/bold green]")
            yield ChatMarkdown(self.content)
        elif self.role == "system":
            yield Static(f"[dim yellow]System:[/dim yellow] {self.content}")
        elif self.role == "error":
            yield Static(f"[bold red]Error:[/bold red] {self.content}")
        else:
            yield Static(self.content)


class EnhancedChatArea(Vertical):
    """Enhanced chat area with markdown support"""

    message_count = reactive(0)

    def __init__(self, max_messages: int = 1000, *args, **kwargs):
        """Initialize enhanced chat area

        Args:
            max_messages: Maximum number of messages to keep

        """
        super().__init__(*args, **kwargs)
        self.max_messages = max_messages
        self._messages = []

    def on_mount(self) -> None:
        """Initialize after mount"""
        self.border_title = "Chat"

    def add_user_message(self, message: str, _timestamp: datetime | None = None) -> None:
        """Add user message

        Args:
            message: User message text
            timestamp: Optional timestamp

        """
        self._add_message(message, "user")
        self.message_count += 1

    def add_assistant_message(self, content: str, _timestamp: datetime | None = None) -> None:
        """Add assistant message with markdown rendering

        Args:
            content: Assistant response content
            timestamp: Optional timestamp

        """
        self._add_message(content, "assistant")
        self.message_count += 1

    def add_system_message(self, message: str) -> None:
        """Add system message

        Args:
            message: System message

        """
        self._add_message(message, "system")
        self.message_count += 1

    def add_error(self, error: str, context: str | None = None) -> None:
        """Add error message

        Args:
            error: Error message
            context: Optional context

        """
        error_msg = f"Error ({context}): {error}" if context else f"Error: {error}"

        self._add_message(error_msg, "error")
        self.message_count += 1

    def add_info(self, info: str) -> None:
        """Add informational message

        Args:
            info: Info message

        """
        self._add_message(f"ℹ️ {info}", "system")
        self.message_count += 1

    def _add_message(self, content: str, role: str) -> None:
        """Add message to chat

        Args:
            content: Message content
            role: Message role

        """
        # Create message bubble
        bubble = MessageBubble(content, role=role)
        bubble.styles.margin = (0, 0, 1, 0)

        # Add to container
        self.mount(bubble)

        # Add to history
        self._messages.append({"content": content, "role": role, "timestamp": datetime.now(timezone.utc)})

        # Limit history
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages :]

        # Scroll to bottom
        self.scroll_end()

    def start_streaming(self) -> None:
        """Start streaming mode"""
        self._add_message("", "assistant")

    def append_streaming_content(self, chunk: str) -> None:
        """Append streaming content chunk

        Args:
            chunk: Content chunk to append

        """
        # Update last message if it's an assistant message
        if self._messages and self._messages[-1]["role"] == "assistant":
            # Append to last message
            self._messages[-1]["content"] += chunk

            # Update UI (remove last and re-add)
            last_child = self.children[-1]
            if isinstance(last_child, MessageBubble):
                last_child.remove()

            new_bubble = MessageBubble(self._messages[-1]["content"], "assistant")
            new_bubble.styles.margin = (0, 0, 1, 0)
            self.mount(new_bubble)
            self.scroll_end()

    def end_streaming(self) -> None:
        """End streaming mode"""
        self._add_message("\n" + "-" * 80 + "\n", "system")

    def get_history(self) -> list:
        """Get message history

        Returns:
            List of message dictionaries

        """
        return self._messages.copy()

    def clear_chat(self) -> None:
        """Clear all messages"""
        self._messages.clear()
        self.remove_children()
        self.message_count = 0

    def export_history(self) -> str:
        """Export chat history as markdown

        Returns:
            Markdown string of chat history

        """
        lines = []
        lines.append("# Chat History\n")
        lines.append(f"Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        lines.append("---\n\n")

        for msg in self._messages:
            role = msg["role"].capitalize()
            timestamp = msg["timestamp"].strftime("%H:%M:%S")
            content = msg["content"]

            if role == "User":
                lines.append(f"## [{timestamp}] You\n\n")
            elif role == "Assistant":
                lines.append(f"## [{timestamp}] Assistant\n\n")
            elif role == "System":
                lines.append(f"## [{timestamp}] System\n\n")
            elif role == "Error":
                lines.append(f"## [{timestamp}] Error\n\n")

            lines.append(f"{content}\n\n")
            lines.append("---\n\n")

        return "".join(lines)
