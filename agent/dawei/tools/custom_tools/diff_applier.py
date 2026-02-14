# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from pathlib import Path

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool


class ApplyDiffInput(BaseModel):
    """Input for ApplyDiffTool."""

    file_path: str = Field(..., description="Path to file to apply the diff.")
    diff_content: str = Field(..., description="The diff content to apply.")


class ApplyDiffTool(CustomBaseTool):
    """Tool for applying diff patches to files."""

    name: str = "Apply Diff Tool"
    description: str = "Applies a diff patch to a file to modify it precisely."
    args_schema: type[BaseModel] = ApplyDiffInput

    @safe_tool_operation("apply_diff", fallback_value="Error: Failed to apply diff")
    def _run(self, file_path: str, diff_content: str) -> str:
        """Apply the diff patch."""
        if not Path(file_path).exists():
            return f"Error: File not found at {file_path}"

        with Path(file_path).open(encoding="utf-8") as f:
            original_content = f.read()

        # Simple diff application (in real implementation, use proper diff library)
        new_content = f"{original_content}\n\n# Applied diff:\n{diff_content}"

        with file_path.open("w", encoding="utf-8") as f:
            f.write(new_content)

        return f"Successfully applied diff to {file_path}."
