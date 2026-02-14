# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from pathlib import Path

from pydantic import BaseModel, Field

from dawei.tools.custom_base_tool import CustomBaseTool


class GenerateDiagramInput(BaseModel):
    """Input for GenerateDiagramTool."""

    description: str = Field(
        ...,
        description="A detailed description of the diagram to be generated.",
    )
    output_path: str = Field(
        ...,
        description="The file path where the generated diagram should be saved.",
    )
    diagram_type: str = Field(
        default="flowchart",
        description="Type of diagram: flowchart, system, process, schematic.",
    )
    width: int = Field(default=800, description="Diagram width in pixels.")
    height: int = Field(default=600, description="Diagram height in pixels.")


class GenerateDiagramTool(CustomBaseTool):
    """Tool for generating technical diagrams."""

    name: str = "Generate Diagram Tool"
    description: str = "Generates technical diagrams using DALL-E 3 or creates basic flowcharts programmatically."
    args_schema: type[BaseModel] = GenerateDiagramInput

    def _run(
        self,
        description: str,
        output_path: str,
        diagram_type: str = "flowchart",
        _width: int = 800,
        _height: int = 600,
    ) -> str:
        """Generate a technical diagram."""
        print(f"Generating {diagram_type} diagram: '{description}' -> '{output_path}'")

        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Mock implementation for demo
        return f"""
✅ Successfully generated diagram programmatically: {output_path}

Description: {description}
Diagram Type: {diagram_type}

This is a mock implementation. In production, this would use DALL-E 3 or other diagram generation services.
"""
