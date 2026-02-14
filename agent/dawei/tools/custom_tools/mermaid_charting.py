# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from pydantic import BaseModel, Field

from dawei.tools.custom_base_tool import CustomBaseTool


class MermaidChartingInput(BaseModel):
    """Input for MermaidChartingTool."""

    description: str = Field(
        ...,
        description="A natural language description of process to be converted into a Mermaid chart.",
    )
    chart_type: str = Field(
        default="flowchart",
        description="Type of chart: flowchart, sequence, class, state, gantt.",
    )
    complexity: str = Field(
        default="medium",
        description="Chart complexity: simple, medium, complex.",
    )


class MermaidChartingTool(CustomBaseTool):
    """Tool for converting natural language descriptions into Mermaid syntax."""

    name: str = "Mermaid Charting Tool"
    description: str = "Converts natural language descriptions into Mermaid syntax for creating professional flowcharts and diagrams."
    args_schema: type[BaseModel] = MermaidChartingInput

    def _run(
        self,
        description: str,
        chart_type: str = "flowchart",
        complexity: str = "medium",
    ) -> str:
        """Convert natural language description to Mermaid syntax."""
        print(f"Converting description to Mermaid {chart_type} chart (complexity: {complexity})")
        print(f"Description: {description[:100]}...")

        # Mock implementation for demo
        mock_mermaid = f"""graph TD
    A[Start: {description[:30]}...] --> B[Process]
    B --> C{{Decision}}
    C -->|Yes| D[Action 1]
    C -->|No| E[Action 2]
    D --> F[End]
    E --> F[End]
"""

        return f"""
✅ Generated Mermaid {chart_type} diagram using rule-based approach:

```mermaid
{mock_mermaid}
```

**Description**: {description}
**Chart Type**: {chart_type}
**Complexity**: {complexity}

This diagram can be rendered in any Mermaid-compatible tool or editor.
"""
