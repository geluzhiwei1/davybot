# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Magic Commands Parser

Detects and parses magic commands from user input.
Supports line magics (%), cell magics (%%), and system commands (!).
"""

import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


MagicType = Literal["line", "cell", "system"] | None


@dataclass
class ParsedMagicCommand:
    """Represents a parsed magic command"""

    magic_type: MagicType
    command: str
    args: str
    content: str | None = None  # For cell magics
    raw_input: str = ""


class MagicCommandParser:
    """Parser for magic commands inspired by Jupyter Notebook.

    Supports:
    - Line magics: %command args
    - Cell magics: %%command args\nmulti-line content
    - System commands: !shell_command
    """

    # Pattern for detecting magic commands
    LINE_MAGIC_PATTERN = r"^%\s*(\w+)(?:\s+(.+))?"
    CELL_MAGIC_PATTERN = r"^%%\s*(\w+)(?:\s+(.+))?"
    SYSTEM_COMMAND_PATTERN = r"^!\s*(.+)$"

    @staticmethod
    def detect_magic_type(input: str) -> MagicType:
        """Detect if input is a magic command and its type.

        Args:
            input: User input string

        Returns:
            'line', 'cell', 'system', or None

        """
        if not input or not isinstance(input, str):
            return None

        stripped = input.strip()

        # Check for system command (!command) - must check before line magic
        if stripped.startswith("!"):
            return "system"

        # Check for cell magic (must be at start of input)
        if stripped.startswith("%%"):
            return "cell"

        # Check for line magic
        if stripped.startswith("%"):
            return "line"

        return None

    @staticmethod
    def parse(input: str) -> ParsedMagicCommand | None:
        """Parse magic command from input.

        Args:
            input: User input string

        Returns:
            ParsedMagicCommand object or None if not a magic command

        """
        if not input or not isinstance(input, str):
            return None

        magic_type = MagicCommandParser.detect_magic_type(input)

        if magic_type == "system":
            return MagicCommandParser._parse_system_command(input)
        if magic_type == "line":
            return MagicCommandParser._parse_line_magic(input)
        if magic_type == "cell":
            return MagicCommandParser._parse_cell_magic(input)

        return None

    @staticmethod
    def _parse_system_command(input: str) -> ParsedMagicCommand | None:
        """Parse system command (!command)"""
        match = re.match(MagicCommandParser.SYSTEM_COMMAND_PATTERN, input.strip())
        if match:
            command = match.group(1).strip()
            return ParsedMagicCommand(
                magic_type="system",
                command="shell",  # System commands are always 'shell'
                args=command,
                raw_input=input,
            )
        return None

    @staticmethod
    def _parse_line_magic(input: str) -> ParsedMagicCommand | None:
        """Parse line magic (%command args)"""
        match = re.match(MagicCommandParser.LINE_MAGIC_PATTERN, input.strip())
        if match:
            command = match.group(1)
            args = match.group(2) if match.group(2) else ""
            return ParsedMagicCommand(
                magic_type="line",
                command=command,
                args=args.strip() if args else "",
                raw_input=input,
            )
        return None

    @staticmethod
    def _parse_cell_magic(input: str) -> ParsedMagicCommand | None:
        """Parse cell magic (%%command args\ncontent)"""
        lines = input.split("\n")
        if len(lines) < 1:
            return None

        first_line = lines[0].strip()

        match = re.match(MagicCommandParser.CELL_MAGIC_PATTERN, first_line)
        if match:
            command = match.group(1)
            args = match.group(2) if match.group(2) else ""
            # Content is everything after the first line
            content = "\n".join(lines[1:]) if len(lines) > 1 else ""

            return ParsedMagicCommand(
                magic_type="cell",
                command=command,
                args=args.strip() if args else "",
                content=content,
                raw_input=input,
            )
        return None

    @staticmethod
    def is_magic_command(input: str) -> bool:
        """Quick check if input is any kind of magic command.

        Args:
            input: User input string

        Returns:
            True if input is a magic command

        """
        return MagicCommandParser.detect_magic_type(input) is not None

    @staticmethod
    def extract_normal_content(input: str) -> str:
        """Extract normal (non-magic) content from input.

        If input is not a magic command, returns it as-is.
        If input is a magic command, returns empty string.

        Args:
            input: User input string

        Returns:
            Normal content or empty string

        """
        if MagicCommandParser.is_magic_command(input):
            return ""
        return input


# Convenience functions
def detect_magic(input: str) -> MagicType:
    """Detect magic command type"""
    return MagicCommandParser.detect_magic_type(input)


def parse_magic(input: str) -> ParsedMagicCommand | None:
    """Parse magic command"""
    return MagicCommandParser.parse(input)


def is_magic(input: str) -> bool:
    """Check if input is a magic command"""
    return MagicCommandParser.is_magic_command(input)
