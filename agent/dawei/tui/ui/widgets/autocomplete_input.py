# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Autocomplete Input Box Widget

Enhanced input widget with Tab key autocomplete for @skill directives.
Features:
- Tab key completion for skill names
- Integration with SkillManager
- Visual feedback for matches
"""

import re
from pathlib import Path

from textual import events
from textual.keys import Keys
from textual.message import Message
from textual.widgets import Input


class AutocompleteInputBox(Input):
    """Input widget with Tab autocomplete for @skill directives"""

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

    def __init__(self, workspace_path: Path | None = None, *args, **kwargs):
        """Initialize autocomplete input box

        Args:
            workspace_path: Workspace path for skill discovery
            *args: Arguments to pass to Input
            **kwargs: Keyword arguments to pass to Input

        """
        super().__init__(*args, **kwargs)
        self.workspace_path = workspace_path or Path.cwd()
        self.available_skills: list[str] = []
        self._load_available_skills()

    def _load_available_skills(self) -> None:
        """Load available skills from SkillManager"""
        try:
            from dawei.tools.skill_manager import SkillManager

            # Build skills roots
            skills_roots = [self.workspace_path, Path.home()]

            # Create skill manager and discover skills
            skill_manager = SkillManager(skills_roots=skills_roots)
            skill_manager.discover_skills(force=True)

            # Get skill names using get_all_skills() method
            all_skills = skill_manager.get_all_skills(reload=False)
            # Extract unique skill names (remove duplicates)
            self.available_skills = list({skill.name for skill in all_skills})
            # Sort alphabetically for better UX
            self.available_skills.sort()

            # Log for debugging
            from dawei.logg.logging import get_logger

            logger = get_logger(__name__)
            logger.info(f"Loaded {len(self.available_skills)} skills for autocomplete")

        except (ImportError, AttributeError, OSError) as e:
            # Graceful degradation: UI widget should never crash system
            # Skills loading is optional for autocomplete functionality
            from dawei.logg.logging import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Failed to load skills for autocomplete: {e}", exc_info=True)
            self.available_skills = []

    def on_key(self, event: events.Key) -> None:
        """Handle key press events

        Args:
            event: Key event

        """
        from dawei.logg.logging import get_logger

        logger = get_logger(__name__)

        # FAST FAIL: Log all key events with maximum detail
        # Use print() to ensure visibility even if logging is misconfigured
        print(f"[DEBUG KEY] key={event.key!r}, char={event.character!r}, is_printable={event.is_printable}, aliases={event.aliases}")

        logger.info(f"[KEY_EVENT] key={event.key!r}, char={event.character!r}, is_printable={event.is_printable}, aliases={event.aliases}")

        # Forward Ctrl+H or F1 to app's show_help action (before any other handling)
        # PowerShell sends Ctrl+H as backspace character, so check both key and character
        is_help_key = event.key in ("ctrl+h", "f1", "F1", "ctrl+H", "Ctrl+H")

        if is_help_key:
            print("[DEBUG] Help key detected - calling action_show_help")
            logger.info(f"Help key detected: key={event.key}, char={event.character}, calling action_show_help")
            event.stop()
            if hasattr(self.app, "action_show_help"):
                self.app.action_show_help()
            return

        # Check for "?" key (when input is empty)
        if event.key == "?" and not self.value:
            print("[DEBUG] Help '?' key detected - calling action_show_help")
            logger.info("Help key '?' detected (empty input), calling action_show_help")
            event.stop()
            if hasattr(self.app, "action_show_help"):
                self.app.action_show_help()
            return

        # Check for Tab key
        if event.key == Keys.Tab:
            print("[DEBUG] Tab key detected - calling autocomplete")
            event.stop()
            # Call async method
            self.call_after_refresh(self._handle_tab_completion)
            return

        # For all other keys, DON'T call event.stop() - let Textual handle normal input
        # including Chinese IME characters automatically
        print("[DEBUG] Passing key to Textual's default handler")

    async def _handle_tab_completion(self) -> None:
        """Handle Tab key autocomplete for @skill directives"""
        try:
            # Get cursor position and text before cursor
            cursor_pos = self.cursor_position
            text_before = self.value[:cursor_pos]

            # Check if user is typing @skill:
            match = re.search(r"@skill:(\w*)$", text_before)

            if not match:
                # Not typing @skill:, ignore
                return

            partial_name = match.group(1)

            # Find matching skills
            matches = self._find_matching_skills(partial_name)

            if not matches:
                # No matches, ignore
                return

            if len(matches) == 1:
                # Single match, complete it
                skill_name = matches[0]
                await self._complete_skill(skill_name, match.start(), cursor_pos)
            else:
                # Multiple matches, show common prefix
                common_prefix = self._find_common_prefix(matches)
                if common_prefix and common_prefix != partial_name:
                    await self._complete_skill(common_prefix, match.start(), cursor_pos)
                else:
                    # No common prefix, show all matches in chat
                    await self._show_skill_matches(matches)

        except (AttributeError, ValueError, IndexError) as e:
            # Graceful degradation: UI widget should never crash system
            # Tab completion failure should not break input
            from dawei.logg.logging import get_logger

            logger = get_logger(__name__)
            logger.error(f"Error during tab completion: {e}", exc_info=True)

    def _find_matching_skills(self, partial: str) -> list[str]:
        """Find skills that match partial name

        Args:
            partial: Partial skill name

        Returns:
            List of matching skill names

        """
        if not partial:
            # Return all skills if no partial
            return self.available_skills

        # Find skills that start with partial
        return [skill for skill in self.available_skills if skill.lower().startswith(partial.lower())]

    def _find_common_prefix(self, strings: list[str]) -> str:
        """Find common prefix among strings

        Args:
            strings: List of strings

        Returns:
            Common prefix

        """
        if not strings:
            return ""

        if len(strings) == 1:
            return strings[0]

        # Find common prefix
        prefix = strings[0]
        for s in strings[1:]:
            # Find common prefix between current prefix and s
            i = 0
            while i < min(len(prefix), len(s)) and prefix[i] == s[i]:
                i += 1
            prefix = prefix[:i]

            if not prefix:
                break

        return prefix

    async def _complete_skill(self, skill_name: str, start_pos: int, end_pos: int) -> None:
        """Complete skill name in input

        Args:
            skill_name: Skill name to complete
            start_pos: Start position of @skill: prefix
            end_pos: End position (cursor position)

        """
        # Replace text from start_pos to end_pos with skill_name
        new_value = self.value[:start_pos] + f"@skill:{skill_name}" + self.value[end_pos:]

        self.value = new_value

        # Move cursor to end of completed skill
        new_cursor_pos = start_pos + len(f"@skill:{skill_name}")
        self.cursor_position = new_cursor_pos

    async def _show_skill_matches(self, matches: list[str]) -> None:
        """Show available skill matches

        Args:
            matches: List of matching skill names

        """
        # This would show a popup or inline suggestions
        # For now, we'll just log it
        from dawei.logg.logging import get_logger

        logger = get_logger(__name__)
        logger.info(f"Skill autocomplete matches: {', '.join(matches)}")

        # TODO: Implement popup suggestion list
        # For now, user can press Tab multiple times to cycle through matches

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission

        Args:
            event: Input submitted event

        """
        message = event.value.strip()

        if not message:
            return

        # Check for help commands (PowerShell-friendly)
        if message.lower() in ("/help", "?", "help"):
            # Clear input and show help
            self.value = ""
            if hasattr(self.app, "action_show_help"):
                self.app.action_show_help()
            return

        # Clear input
        self.value = ""

        # Emit message to app
        self.post_message(self.MessageSubmitted(message))


# Convenience alias
InputBox = AutocompleteInputBox
