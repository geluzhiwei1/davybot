# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Smart File Editor - Specialized tool for editing large files using diff-based approach

This tool helps LLMs edit large files by:
1. Automatically detecting when a file is too large for single-pass editing
2. Splitting edits into multiple smaller diffs
3. Applying diffs incrementally with verification
4. Providing clear feedback on each edit step
"""

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


class SmartFileEditInput(BaseModel):
    """Input for SmartFileEditTool."""

    file_path: str = Field(..., description="Path to file to edit (relative to workspace).")
    edits: list[dict[str, str]] = Field(
        ...,
        description="List of edits to apply. Each edit should have 'search' and 'replace' fields.",
    )
    chunk_size: int = Field(
        50,
        description="Maximum number of lines to edit in a single operation (default: 50).",
    )


class SmartFileEditTool(CustomBaseTool):
    """Smart file editor for large files using diff-based approach.

    This tool automatically:
    - Splits large edits into manageable chunks
    - Applies diffs sequentially with verification
    - Provides detailed progress feedback
    - Prevents response truncation for large files

    **When to use:**
    - Editing HTML files with >500 lines
    - Modifying large code files (>200 lines)
    - Making multiple changes to the same file
    - Working with files that previously caused truncation issues

    **Format:**
    [
      {
        "search": "exact text to find (3-10 lines recommended)",
        "replace": "replacement text"
      },
      {
        "search": "another section to replace",
        "replace": "new content"
      }
    ]
    """

    name: str = "smart_file_edit"
    description: str = """Edits large files safely using diff-based approach. Automatically splits edits into chunks and applies them sequentially to prevent truncation.

**CRITICAL FOR LARGE FILES (>200 lines):**
Use this tool instead of write_to_file to avoid response truncation.

**How it works:**
1. Accepts multiple edits in a single call
2. Applies each edit as a separate diff
3. Verifies each edit before proceeding
4. Returns detailed progress report

**When to use:**
- HTML files >500 lines
- Code files >200 lines
- Multiple changes to same file
- Previous write_to_file calls failed

**Format:**
edits = [
  {"search": "old section", "replace": "new section"},
  {"search": "another old part", "replace": "new part"}
]

**Tips:**
- Include 3-5 unique lines in search for accuracy
- Keep each edit focused (10-50 lines)
- Order edits logically (top to bottom of file)"""
    args_schema: type[BaseModel] = SmartFileEditInput

    @safe_tool_operation("smart_file_edit", fallback_value="Error: Failed to edit file")
    def _run(self, file_path: str, edits: list[dict[str, str]], _chunk_size: int = 50) -> str:
        """Smart edit file using diff-based approach."""
        # Get workspace directory from context
        workspace_dir = None
        if hasattr(self, "context") and self.context is not None:
            workspace_dir = getattr(self.context, "cwd", None)

        # Sanitize filename
        file_path_obj = Path(file_path)
        sanitized_filename = sanitize_filename(file_path_obj.name)
        dir_name = file_path_obj.parent
        file_path = str(dir_name / sanitized_filename) if dir_name != Path() else sanitized_filename

        # Safe path joining
        if workspace_dir:
            try:
                allowed_extensions = {
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
                file_path = str(
                    safe_path_join(
                        Path(workspace_dir),
                        file_path,
                        allow_absolute=False,
                        allowed_extensions=allowed_extensions,
                    ),
                )
            except (PathTraversalError, ValueError) as e:
                return f"Error: Invalid file path - {e!s}"

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return f"Error: File '{file_path_obj.name}' not found"

        # Read file
        content = file_path_obj.read_text(encoding="utf-8")

        original_lines = content.count("\n") + 1
        logger.info(
            f"Smart editing {file_path_obj.name} ({original_lines} lines, {len(edits)} edits)",
        )

        # Validate edits
        if not edits:
            return "Error: No edits provided"

        for i, edit in enumerate(edits):
            if "search" not in edit or "replace" not in edit:
                return f"Error: Edit {i + 1} missing 'search' or 'replace' field"

        # Apply edits sequentially
        results = []
        modified_content = content

        for i, edit in enumerate(edits, 1):
            search_text = edit["search"]
            replace_text = edit["replace"]

            # Check if search text exists
            if search_text not in modified_content:
                # Try with newline variations
                found = False
                for variation in [search_text + "\n", search_text.rstrip("\n")]:
                    if variation in modified_content:
                        search_text = variation
                        found = True
                        break

                if not found:
                    # Find similar content for error message
                    line_num = self._find_approximate_line(modified_content, search_text[:50])
                    results.append(
                        f"❌ Edit {i}/{len(edits)}: Search content not found (near line {line_num})",
                    )
                    results.append(f"   Preview: {search_text[:100]}...")
                    continue

            # Apply edit
            modified_content = modified_content.replace(search_text, replace_text, 1)
            results.append(f"✅ Edit {i}/{len(edits)}: Applied successfully")

        # Write back
        Path(file_path).write_text(modified_content, encoding="utf-8")

        # Generate summary
        new_lines = modified_content.count("\n") + 1
        lines_changed = abs(new_lines - original_lines)

        summary = f"\n📝 Smart Edit Complete: {Path(file_path).name}\n"
        summary += f"   • {len(edits)} edits processed\n"
        summary += f"   • Lines changed: {original_lines} → {new_lines} ({lines_changed} diff)\n"
        summary += f"   • Success rate: {sum(1 for r in results if '✅' in r)}/{len(results)}\n"
        summary += "\nDetails:\n"
        summary += "\n".join(results)

        return summary

    def _find_approximate_line(self, content: str, search_snippet: str) -> int:
        """Find approximate line number for error messages."""
        lines = content.split("\n")
        snippet_lower = search_snippet.lower()[:50]

        for i, line in enumerate(lines, 1):
            if snippet_lower in line.lower():
                return i

        return -1
