# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.core.path_security import (
    PathTraversalError,
    safe_path_join,
    sanitize_filename,
)
from dawei.tools.custom_base_tool import CustomBaseTool

logger = logging.getLogger(__name__)

# Text file extensions whitelist
TEXT_EXTENSIONS: set[str] = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".vue",
    ".html",
    ".css",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".csv",
    ".sql",
    ".sh",
    ".bat",
    ".ps1",
    ".toml",
    ".ini",
    ".cfg",
}


# Insert Content Tool
class InsertContentInput(BaseModel):
    """Input for InsertContentTool."""

    path: str = Field(..., description="File path to insert content into.")
    line: int = Field(
        ...,
        description="Line number where content will be inserted (1-based, 0 to append).",
    )
    content: str = Field(..., description="Content to insert at the specified line.")


class InsertContentTool(CustomBaseTool):
    """Tool for inserting content into files without modifying existing content."""

    name: str = "insert_text_content"
    description: str = "Adds new lines of content into a text file without modifying existing content."
    args_schema: type[BaseModel] = InsertContentInput

    @safe_tool_operation("insert_text_content", fallback_value="Error: Failed to insert content")
    def _run(self, path: str, line: int, content: str) -> str:
        """Insert content at specified line."""
        # Get workspace directory from context
        workspace_dir = None
        if hasattr(self, "context") and self.context is not None:
            workspace_dir = getattr(self.context, "cwd", None)

        # Sanitize filename to prevent directory traversal
        sanitized_filename = sanitize_filename(Path(path).name)

        # Reconstruct path with sanitized filename
        path_obj = Path(path)
        dir_name = path_obj.parent
        path = str(dir_name / sanitized_filename) if dir_name != Path() else sanitized_filename

        # If we have a workspace directory, use safe path joining
        if workspace_dir:
            try:
                path = safe_path_join(
                    workspace_dir,
                    path,
                    allow_absolute=False,
                    allowed_extensions=TEXT_EXTENSIONS,
                )
            except (PathTraversalError, ValueError) as e:
                logger.exception("Path validation failed: ")
                return f"Error: Invalid file path - {e!s}"

        # Read existing file
        path_obj = Path(path)
        if path_obj.exists():
            content_lines = path_obj.read_text(encoding="utf-8").splitlines(keepends=True)
        else:
            # Create new file if it doesn't exist
            content_lines = []

        # Prepare content to insert
        insert_lines = content.split("\n")
        if not insert_lines[-1].endswith("\n"):
            insert_lines[-1] += "\n"

        # Insert content
        if line == 0:  # Append to end
            content_lines.extend(insert_lines)
        else:
            # Convert to 0-based index
            insert_idx = min(line - 1, len(content_lines))
            content_lines[insert_idx:insert_idx] = insert_lines

        # Write back to file
        dir_name = path_obj.parent
        if dir_name != Path():
            dir_name.mkdir(parents=True, exist_ok=True)
        path_obj.write_text("".join(content_lines), encoding="utf-8")

        action = "appended to" if line == 0 else f"inserted at line {line}"
        return f"Successfully inserted content {action} in {path_obj.name}"


# Write to File Tool
class WriteToFileInput(BaseModel):
    """Input for WriteToFileTool."""

    path: str = Field(..., description="File path to write to, relative to workspace directory.")
    content: str = Field(..., description="Complete content to write to the file.")
    line_count: int | None = Field(
        None,
        description="Total number of lines in the content (optional, will be calculated if not provided).",
    )


class WriteToFileTool(CustomBaseTool):
    """Tool for creating new files or completely rewriting existing files."""

    name: str = "write_text_file"
    description: str = (
        "Creates new files or completely rewrites existing files with the provided content. "
        "Supports plain text files only. "
        "For DOCX files, use docx_edit. "
        "All file paths are relative to the current workspace directory."
    )
    args_schema: type[BaseModel] = WriteToFileInput

    @safe_tool_operation("write_text_file", fallback_value="Error: Failed to write file")
    def _run(self, path: str, content: str, line_count: int | None = None) -> str:
        """Write content to file."""
        # Get workspace directory from context
        workspace_dir = None
        if hasattr(self, "context") and self.context is not None:
            workspace_dir = getattr(self.context, "cwd", None)

        # Sanitize filename to prevent directory traversal
        sanitized_filename = sanitize_filename(Path(path).name)

        # Reconstruct path with sanitized filename
        path_obj = Path(path)
        dir_name = path_obj.parent
        path = str(dir_name / sanitized_filename) if dir_name != Path() else sanitized_filename

        # If we have a workspace directory, use safe path joining
        if workspace_dir:
            try:
                path = safe_path_join(
                    workspace_dir,
                    path,
                    allow_absolute=False,
                    allowed_extensions=TEXT_EXTENSIONS,
                )
            except (PathTraversalError, ValueError) as e:
                logger.exception("Path validation failed: ")
                return f"Error: Invalid file path - {e!s}"

        # Create directory if it doesn't exist
        path_obj = Path(path)
        dir_name = path_obj.parent
        if dir_name != Path():
            dir_name.mkdir(parents=True, exist_ok=True)

        # Write text file
        if content and not content.endswith("\n"):
            content += "\n"

        path_obj.write_text(content, encoding="utf-8")
        return f"File '{path_obj.name}' has been successfully written."
