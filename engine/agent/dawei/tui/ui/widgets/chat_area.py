# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ChatArea Widget

Displays chat history with user and assistant messages.
Supports streaming content display.
"""

import logging
from typing import ClassVar

from rich.text import Text
from textual.widgets import RichLog

from dawei.tui.i18n import _

logger = logging.getLogger(__name__)


class ChatArea(RichLog):
    """Chat history display widget"""

    # Add bindings for copy functionality
    BINDINGS = [
        ("ctrl+c", "copy_selection", "Copy"),
        ("ctrl+shift+c", "copy_selection", "Copy"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.wrap = True
        self.markdown = True
        self.auto_scroll = True
        # allow_select is True by default (inherited from Widget)
        # No need to set it manually
        # Set min_height to ensure ChatArea gets space
        self.min_height = 10
        # Ensure RichLog is visible
        self.visible = True
        # Explicitly set background to override any defaults
        self.background = "#2b2b2b"  # $surface color
        logger.info(f"ChatArea initialized with background: {self.background}")

    def on_mount(self) -> None:
        """Initialize after mount"""
        self.border_title = f"💬 {_('Chat Output')}"
        self.border_subtitle = _("Messages")
        # Log current background color for debugging
        logger.info(f"ChatArea mounted with background: {self.background}")
        logger.info(f"ChatArea computed style: {self.styles.background}")
        # Write a test message to verify visibility (using Text object)
        test_msg = Text()
        test_msg.append(f"{_('Chat Area initialized!')}", style="bold cyan")
        self.write(test_msg)
        dim_msg = Text()
        dim_msg.append(f"{_('Messages will appear here...')}", style="dim")
        self.write(dim_msg)
        self.scroll_end()

    def add_user_message(self, message: str) -> None:
        """Add user message to chat

        Args:
            message: User message text

        """
        self.write("")
        # Use Text object for label to bypass markdown
        label = Text()
        label.append(f"{_('You')}:", style="bold blue")
        self.write(label)
        self.write(message)  # Write message as-is (may contain markdown)
        self.write("")
        self.scroll_end()

    def add_assistant_message(self, content: str) -> None:
        """Add assistant response to chat

        Args:
            content: Assistant response content

        """
        self.write("")
        # Use Text object for label to bypass markdown
        label = Text()
        label.append(f"{_('Assistant')}:", style="bold green")
        self.write(label)
        self.write(content)  # Write content as-is (may contain markdown)
        self.write("")
        self.scroll_end()

    def append_streaming_content(self, chunk: str) -> None:
        """Append streaming content chunk

        Args:
            chunk: Content chunk to append

        """
        self.write(chunk, expand=True)
        self.scroll_end()

    def start_streaming(self) -> None:
        """Start streaming mode"""
        # Use Text object to bypass markdown parsing
        label = Text()
        label.append(f"{_('Assistant')}:", style="bold green")
        self.write(label)

    def end_streaming(self) -> None:
        """End streaming mode"""
        self.write("")
        self.write("-" * 80)
        self.write("")

    def add_error(self, error: str) -> None:
        """Add error message to chat

        Args:
            error: Error message

        """
        self.write("")
        # Use Text object to bypass markdown parsing and render Rich markup correctly
        error_text = Text()
        error_text.append("Error: ", style="bold red")
        error_text.append(error)
        self.write(error_text)
        self.write("")
        self.scroll_end()

    def add_info(self, info: str) -> None:
        """Add informational message

        Args:
            info: Info message

        """
        self.write("")
        # Use Text object to bypass markdown parsing
        info_text = Text()
        info_text.append(info, style="dim cyan")
        self.write(info_text)
        self.write("")

    def add_system_message(self, message: str) -> None:
        """Add system message

        Args:
            message: System message

        """
        self.write("")
        # Use Text object to bypass markdown parsing
        sys_text = Text()
        sys_text.append(f"{_('System')}:", style="dim yellow")
        sys_text.append(f" {message}")
        self.write(sys_text)
        self.write("")

    def clear_chat(self) -> None:
        """Clear all chat history"""
        self.clear()

    def add_skill_loading_message(
        self,
        skill_name: str,
        char_count: int,
        success: ClassVar[bool] = True,
    ) -> None:
        """Add a skill loading status message

        Args:
            skill_name: Name of the skill being loaded
            char_count: Number of characters in skill content
            success: Whether the skill loaded successfully

        """
        if success:
            icon = "✅"
            status = _("Loaded skill '{skill_name}' to context ({char_count} chars)").format(skill_name=skill_name, char_count=f"{char_count:,}")
            style = "bold green"  # Success color
        else:
            icon = "❌"
            status = _("Failed to load skill '{skill_name}'").format(skill_name=skill_name)
            style = "bold red"  # Error color

        self.write("")
        # Use Text object to bypass markdown parsing
        status_text = Text()
        status_text.append(f"{icon} {status}", style=style)
        self.write(status_text)
        self.write("")
        self.scroll_end()

    def add_skills_loaded_summary(self, skill_names: list, total_count: int) -> None:
        """Add a summary message for multiple loaded skills

        Args:
            skill_names: List of skill names that were loaded
            total_count: Total number of skills loaded

        """
        skills_str = ", ".join(skill_names)
        self.write("")
        # Use Text object to bypass markdown parsing
        summary_text = Text()
        summary_text.append(f"📚 {_('Skills Loaded:')} ", style="bold cyan")
        summary_text.append(f"{total_count} skill(s): {skills_str}")
        self.write(summary_text)
        self.write("")
        self.scroll_end()

    def action_copy_selection(self) -> None:
        """Copy selected text to clipboard

        This action is bound to Ctrl+C when ChatArea is focused
        """
        try:
            import pyperclip

            # In Textual 0.80.0+, get_selection() requires a Selection parameter
            # Returns tuple of (text, ending) or None
            if self.selection is not None:
                selection = self.get_selection(self.selection)
                if selection:
                    text, _ending = selection  # selection is a tuple of (text, ending)
                    pyperclip.copy(text)
                    self.app.bell()
                    logger.info(f"Copied {len(text)} characters to clipboard")
                else:
                    logger.warning("No text content in selection")
            else:
                logger.warning("No text selected to copy")
        except ImportError:
            logger.exception("pyperclip not installed. Cannot copy to clipboard.")
            logger.info("Install with: pip install pyperclip")
        except Exception:
            logger.exception("Failed to copy selection: ")
