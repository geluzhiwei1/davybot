# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Message Formatter

Format messages for TUI display with colors and styling.
"""

from datetime import datetime
from typing import Any


class MessageFormatter:
    """Format messages for TUI display"""

    @staticmethod
    def format_user_message(message: str, timestamp: datetime | None = None) -> str:
        """Format user message

        Args:
            message: User message text
            timestamp: Optional timestamp

        Returns:
            Formatted message string

        """
        time_str = timestamp.strftime("%H:%M:%S") if timestamp else ""
        time_display = f" [{time_str}]" if time_str else ""

        return f"[bold blue]You{time_display}:[/bold blue]\n{message}"

    @staticmethod
    def format_assistant_message(content: str, timestamp: datetime | None = None) -> str:
        """Format assistant message

        Args:
            content: Assistant response content
            timestamp: Optional timestamp

        Returns:
            Formatted message string

        """
        time_str = timestamp.strftime("%H:%M:%S") if timestamp else ""
        time_display = f" [{time_str}]" if time_str else ""

        return f"[bold green]Assistant{time_display}:[/bold green]\n{content}"

    @staticmethod
    def format_system_message(message: str) -> str:
        """Format system message

        Args:
            message: System message text

        Returns:
            Formatted message string

        """
        return f"[dim yellow]System:[/dim yellow] {message}"

    @staticmethod
    def format_error_message(error: str, context: str | None = None) -> str:
        """Format error message

        Args:
            error: Error message
            context: Optional context

        Returns:
            Formatted error string

        """
        if context:
            return f"[bold red]Error ({context}):[/bold red] {error}"
        return f"[bold red]Error:[/bold red] {error}"

    @staticmethod
    def format_info_message(info: str) -> str:
        """Format informational message

        Args:
            info: Info message

        Returns:
            Formatted info string

        """
        return f"[dim cyan]ℹ️ {info}[/dim cyan]"

    @staticmethod
    def format_tool_call(tool_name: str, params: dict[str, Any]) -> str:
        """Format tool call information

        Args:
            tool_name: Tool name
            params: Tool parameters

        Returns:
            Formatted tool call string

        """
        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
        return f"[bold yellow]→ {tool_name}[/bold yellow] ({params_str})"

    @staticmethod
    def format_tool_result(tool_name: str, success: bool, duration: float | None = None) -> str:
        """Format tool execution result

        Args:
            tool_name: Tool name
            success: Whether execution succeeded
            duration: Optional duration in seconds

        Returns:
            Formatted result string

        """
        status = "[bold green]✓[/bold green]" if success else "[bold red]✗[/bold red]"
        duration_str = f" ({duration:.2f}s)" if duration else ""
        return f"{status} {tool_name}{duration_str}"

    @staticmethod
    def format_thinking(content: str) -> str:
        """Format thinking/reasoning content

        Args:
            content: Thinking content

        Returns:
            Formatted thinking string

        """
        return f"[bold cyan]Thinking:[/bold cyan] {content}"

    @staticmethod
    def format_mode_switch(old_mode: str, new_mode: str) -> str:
        """Format mode switch message

        Args:
            old_mode: Old mode
            new_mode: New mode

        Returns:
            Formatted mode switch string

        """
        return f"[bold yellow]Mode switched:[/bold yellow] {old_mode} → [bold green]{new_mode}[/bold green]"

    @staticmethod
    def format_model_selection(model: str, reason: str, confidence: float | None = None) -> str:
        """Format model selection message

        Args:
            model: Selected model
            reason: Selection reason
            confidence: Optional confidence score

        Returns:
            Formatted model selection string

        """
        confidence_str = f" ({confidence:.1%})" if confidence else ""
        return f"[bold cyan]Model:[/bold cyan] {model}{confidence_str}\n[dim]Reason: {reason}[/dim]"

    @staticmethod
    def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
        """Truncate text to max length

        Args:
            text: Text to truncate
            max_length: Maximum length
            suffix: Suffix to add if truncated

        Returns:
            Truncated text

        """
        if len(text) <= max_length:
            return text
        return text[: max_length - len(suffix)] + suffix

    @staticmethod
    def format_code_block(code: str, language: str = "") -> str:
        """Format code block

        Args:
            code: Code content
            language: Programming language

        Returns:
            Formatted code block

        """
        lang_suffix = f" {language}" if language else ""
        return f"```{lang_suffix}\n{code}\n```"

    @staticmethod
    def format_file_reference(file_path: str, line_range: tuple | None = None) -> str:
        """Format file reference

        Args:
            file_path: File path
            line_range: Optional (start, end) line range

        Returns:
            Formatted file reference

        """
        if line_range:
            start, end = line_range
            if start == end:
                return f"[bold cyan]{file_path}[/bold cyan]:[dim]{start}[/dim]"
            return f"[bold cyan]{file_path}[/bold cyan]:[dim]{start}-{end}[/dim]"
        return f"[bold cyan]{file_path}[/bold cyan]"
