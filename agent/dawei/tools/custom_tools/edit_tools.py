# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import logging
import re
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

    name: str = "insert_content"
    description: str = "Adds new lines of content into a file without modifying existing content."
    args_schema: type[BaseModel] = InsertContentInput

    @safe_tool_operation("insert_content", fallback_value="Error: Failed to insert content")
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
                # Allow common file extensions
                allowed_extensions: set[str] = {
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
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".svg",
                    ".pdf",
                    ".doc",
                    ".docx",
                }
                path = safe_path_join(
                    workspace_dir,
                    path,
                    allow_absolute=False,
                    allowed_extensions=allowed_extensions,
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

    name: str = "write_to_file"
    description: str = """Creates new files or completely rewrites existing files with the provided content. All file paths are relative to the current workspace directory.

⚠️ **CRITICAL WARNING - Large Files:**
For files larger than 200 lines (especially HTML/CSS/JS), use **smart_file_edit** or **apply_diff** instead to avoid response truncation!

**When to use write_to_file:**
- Creating new files with <200 lines
- Completely replacing small files (<100 lines)
- Writing simple configuration files

**When NOT to use write_to_file:**
❌ Large HTML files (>500 lines) → Use smart_file_edit
❌ Large code files (>200 lines) → Use apply_diff or smart_file_edit
❌ Making partial edits → Use apply_diff

**For large files, use:**
- smart_file_edit: Multiple edits to different sections
- apply_diff: Single focused edit using SEARCH/REPLACE format"""
    args_schema: type[BaseModel] = WriteToFileInput

    @safe_tool_operation("write_to_file", fallback_value="Error: Failed to write file")
    def _run(self, path: str, content: str, _line_count: int | None = None) -> str:
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
                # Allow common file extensions for code files
                allowed_extensions: set[str] = {
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
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".svg",
                    ".pdf",
                    ".doc",
                    ".docx",
                }
                path = safe_path_join(
                    workspace_dir,
                    path,
                    allow_absolute=False,
                    allowed_extensions=allowed_extensions,
                )
            except (PathTraversalError, ValueError) as e:
                logger.exception("Path validation failed: ")
                return f"Error: Invalid file path - {e!s}"

        # Ensure content ends with newline if not empty
        if content and not content.endswith("\n"):
            content += "\n"

        # Create directory if it doesn't exist
        # Handle case where path is a filename in the root directory
        path_obj = Path(path)
        dir_name = path_obj.parent
        if dir_name != Path():
            dir_name.mkdir(parents=True, exist_ok=True)

        # Write content to file
        path_obj.write_text(content, encoding="utf-8")

        # Calculate actual lines written
        content.count("\n")

        "overwrote" if path_obj.exists() else "created"
        return f"File '{path_obj.name}' has been successfully written with the specified content."


# Enhanced Apply Diff Tool (improved version)
class ApplyDiffInput(BaseModel):
    """Input for ApplyDiffTool."""

    file_path: str = Field(..., description="Path to file to apply the diff.")
    diff: str = Field(
        ...,
        description="The diff content in either SEARCH/REPLACE format or git unified diff format. Both are auto-detected and supported.",
    )
    verify: bool = Field(
        False,
        description="Verify the diff was applied correctly by checking the file content.",
    )


class ApplyDiffTool(CustomBaseTool):
    """Tool for applying precise diff patches to files."""

    name: str = "apply_diff"
    description: str = """Makes precise, surgical changes to files using diff format.

**IMPORTANT - For Large Files:**
When editing files larger than 100 lines, split changes into multiple smaller diffs:
- Each diff should modify one specific section (10-50 lines)
- Apply diffs sequentially, waiting for confirmation before next
- This prevents response truncation and ensures accuracy

**Supported Formats (auto-detected):**

**1. Git Unified Diff Format (Recommended for compatibility):**
```diff
--- a/file.txt
+++ b/file.txt
@@ -line,count +line,count @@
 context line
-old line to remove
+new line to add
 another context
```

**2. SEARCH/REPLACE Format (Simpler for LLMs):**
```
<<<<<<< SEARCH
[exact content to find]
=======
[replacement content]
>>>>>>> REPLACE
```

**Best Practices:**
- Include enough context for unique matching (3-5 lines)
- Keep changes focused and minimal
- For large HTML/code files, use apply_diff instead of write_to_file"""
    args_schema: type[BaseModel] = ApplyDiffInput

    @safe_tool_operation("apply_diff", fallback_value="Error: Failed to apply diff")
    def _run(self, file_path: str, diff: str, verify: bool = False) -> str:
        """Apply diff patch to file."""
        # Get workspace directory from context
        workspace_dir = None
        if hasattr(self, "context") and self.context is not None:
            workspace_dir = getattr(self.context, "cwd", None)

        # Sanitize filename to prevent directory traversal
        sanitized_filename = sanitize_filename(Path(file_path).name)

        # Reconstruct path with sanitized filename
        path_obj = Path(file_path)
        dir_name = path_obj.parent
        file_path = str(dir_name / sanitized_filename) if dir_name != Path() else sanitized_filename

        # If we have a workspace directory, use safe path joining
        if workspace_dir:
            try:
                # Allow common file extensions
                allowed_extensions: set[str] = {
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
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".svg",
                    ".pdf",
                    ".doc",
                    ".docx",
                }
                file_path = safe_path_join(
                    workspace_dir,
                    file_path,
                    allow_absolute=False,
                    allowed_extensions=allowed_extensions,
                )
            except (PathTraversalError, ValueError) as e:
                logger.exception("Path validation failed: ")
                return f"Error: Invalid file path - {e!s}"

        path_obj = Path(file_path)
        if not path_obj.exists():
            return f"Error: File not found at {path_obj.name}"

        # Read original file
        original_content = path_obj.read_text(encoding="utf-8")
        original_lines = original_content.count("\n") + 1

        # Parse diff blocks
        diff_blocks = self._parse_diff(diff)

        if not diff_blocks:
            return "Error: No valid diff blocks found. Make sure your diff follows either SEARCH/REPLACE or git unified diff format."

        # Apply each diff block
        modified_content = original_content
        success_count = 0
        failed_blocks = []

        for i, block in enumerate(diff_blocks, 1):
            search_snippet = block["search"][:100]
            result = self._apply_diff_block(modified_content, block)

            if result is None:
                failed_blocks.append(
                    {
                        "block_num": i,
                        "search_preview": search_snippet,
                        "line_number": self._find_line_number(
                            modified_content,
                            block["search"][:50],
                        ),
                    },
                )
            else:
                modified_content = result
                success_count += 1

        # Check if all blocks succeeded
        if failed_blocks:
            error_msg = f"Applied {success_count}/{len(diff_blocks)} diffs successfully. Failed blocks:\n"
            for failed in failed_blocks:
                error_msg += f"\n  Block {failed['block_num']}: Search content not found near line {failed['line_number']}"
                error_msg += f"\n    Preview: {failed['search_preview']}"
            return error_msg

        # Write modified content back
        path_obj.write_text(modified_content, encoding="utf-8")

        # Calculate stats
        new_lines = modified_content.count("\n") + 1
        lines_added = max(0, new_lines - original_lines)
        lines_removed = max(0, original_lines - new_lines)

        result_msg = f"Successfully applied {success_count} diff block(s) to {path_obj.name}"
        if lines_added or lines_removed:
            result_msg += f" (Lines: +{lines_added}, -{lines_removed})"

        # Verify if requested
        if verify:
            verification = self._verify_diff(file_path, diff_blocks)
            result_msg += f"\n\nVerification: {verification}"

        return result_msg

    def _find_line_number(self, content: str, search_snippet: str) -> int:
        """Find approximate line number for a search snippet."""
        lines = content.split("\n")
        snippet_lower = search_snippet.lower()[:50]

        for i, line in enumerate(lines, 1):
            if snippet_lower in line.lower():
                return i

        return -1

    def _verify_diff(self, file_path: str, diff_blocks: list[dict]) -> str:
        """Verify that all diffs were applied correctly."""
        try:
            path_obj = Path(file_path)
            content = path_obj.read_text(encoding="utf-8")

            verified_count = 0
            for block in diff_blocks:
                # Check if replacement text exists in file
                if block["replace"].rstrip("\n") in content:
                    verified_count += 1

            if verified_count == len(diff_blocks):
                return f"All {verified_count} changes verified successfully"
            return f"{verified_count}/{len(diff_blocks)} changes verified"

        except FileNotFoundError:
            return f"Verification failed: File not found at {file_path}"
        except OSError as e:
            return f"Verification failed: Unable to read file - {e!s}"
        except (KeyError, AttributeError) as e:
            # Diff block structure error
            return f"Verification failed: Invalid diff block structure - {e!s}"

    def _parse_diff(self, diff: str) -> list[dict]:
        """Parse diff content into blocks. Supports both SEARCH/REPLACE and git unified diff formats."""
        # Auto-detect format
        if "<<<<<<< SEARCH" in diff or "<<<<<<< SEARCH" in diff:
            return self._parse_search_replace(diff)
        if re.search(r"^--- a/", diff, re.MULTILINE) or re.search(
            r"^@@ -\d+,\d+ \+\d+,\d+ @@",
            diff,
            re.MULTILINE,
        ):
            return self._parse_unified_diff(diff)
        # Try unified diff first as fallback
        logger.warning("Unable to detect diff format, trying unified diff parser")
        return self._parse_unified_diff(diff)

    def _parse_search_replace(self, diff: str) -> list[dict]:
        """Parse SEARCH/REPLACE format diff."""
        blocks = []
        current_block = None

        lines = diff.split("\n")
        for line in lines:
            if line.startswith("<<<<<<< SEARCH"):
                if current_block:
                    blocks.append(current_block)
                current_block = {"search": "", "replace": ""}
            elif line.startswith("======="):
                if current_block:
                    current_block["mode"] = "replace"
            elif line.startswith(">>>>>>> REPLACE"):
                if current_block:
                    blocks.append(current_block)
                current_block = None
            elif current_block:
                if "mode" not in current_block:
                    current_block["search"] += line + "\n"
                else:
                    current_block["replace"] += line + "\n"

        return blocks

    def _parse_unified_diff(self, diff: str) -> list[dict]:
        """Parse git unified diff format."""
        blocks = []
        lines = diff.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Look for hunk header @@ -old_start,old_count +new_start,new_count @@
            hunk_match = re.match(r"^@@ -(\d+),?(\d+)? \+(\d+),?(\d+)? @@", line)
            if hunk_match:
                int(hunk_match.group(1))
                int(hunk_match.group(2) or 1)
                int(hunk_match.group(3))
                int(hunk_match.group(4) or 1)

                # Collect hunk content
                context_lines = []
                old_lines = []
                new_lines = []
                j = i + 1

                while j < len(lines):
                    hunk_line = lines[j]

                    # Stop at next hunk or file header
                    if hunk_line.startswith(("@@", "---", "+++")):
                        break

                    # Parse hunk lines
                    if hunk_line.startswith(" ") or not hunk_line:
                        # Context line
                        context_lines.append(
                            hunk_line.removeprefix(" "),
                        )
                        old_lines.append(hunk_line.removeprefix(" "))
                        new_lines.append(hunk_line.removeprefix(" "))
                    elif hunk_line.startswith("-"):
                        # Removed line
                        old_lines.append(hunk_line[1:])
                    elif hunk_line.startswith("+"):
                        # Added line
                        new_lines.append(hunk_line[1:])

                    j += 1

                # Create search/replace block from hunk
                search_text = "\n".join(old_lines).rstrip("\n")
                replace_text = "\n".join(new_lines).rstrip("\n")

                if search_text or replace_text:
                    blocks.append(
                        {
                            "search": search_text + "\n" if search_text else "",
                            "replace": replace_text + "\n" if replace_text else "",
                        },
                    )

                i = j - 1  # Will increment to j in loop

            i += 1

        return blocks

    def _apply_diff_block(self, content: str, block: dict) -> str | None:
        """Apply a single diff block to content."""
        search_text = block["search"].rstrip("\n")
        replace_text = block["replace"].rstrip("\n")

        # First try exact match
        if search_text in content:
            return content.replace(search_text, replace_text, 1)

        # Try with trailing newline variations
        variations = [
            search_text + "\n",
            search_text + "\r\n",
            search_text.rstrip("\n"),
        ]

        for variation in variations:
            if variation in content:
                return content.replace(variation, replace_text, 1)

        # If not found, provide helpful context
        lines = content.split("\n")
        search_lines = search_text.split("\n")

        # Try to find partial match for context
        for i in range(len(lines) - len(search_lines) + 1):
            window = "\n".join(lines[i : i + len(search_lines)])
            similarity = self._calculate_similarity(search_text[:100], window[:100])

            if similarity > 0.5:
                return None  # Indicate potential match with context

        return None

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate simple similarity ratio between two strings."""
        if not str1 or not str2:
            return 0.0

        set1 = set(str1.lower().split())
        set2 = set(str2.lower().split())

        if not set1 or not set2:
            return 0.0

        intersection = set1.intersection(set2)
        union = set1.union(set2)

        return len(intersection) / len(union) if union else 0.0
