# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import inspect
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import BaseModel

from dawei.config import get_workspaces_root

# Configure logging
logger = logging.getLogger(__name__)


class ToolProvider(ABC):
    """An abstract base class for tool providers."""

    @abstractmethod
    def get_tools(self) -> list[dict[str, Any]]:
        """Returns a list of tools in a standardized format.
        Each tool is represented as a dictionary.
        """


class OpenAIToolProvider(ToolProvider):
    """Provides tools in OpenAI function call format."""

    def get_tools(self) -> list[dict[str, Any]]:
        """Returns a list of OpenAI-compatible tools.
        Currently includes mcp_call tool for multimodal capabilities.
        """
        logger.info("Loading tools from OpenAIToolProvider...")

        # Define mcp_call tool
        mcp_call_tool = {
            "name": "mcp_call",
            "description": "调用一个多模态能力代理(MCP)来执行需要视觉或其他非文本理解的任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "需要调用的具体多模态工具的名称",
                    },
                    "tool_input": {
                        "type": "object",
                        "description": "传递给该多模态工具的输入参数",
                    },
                },
                "required": ["tool_name", "tool_input"],
            },
            "callable": self._mcp_call_placeholder,
        }

        return [mcp_call_tool]

    def _mcp_call_placeholder(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Placeholder implementation for mcp_call.

        Args:
            tool_name: The name of the multimodal tool to call
            tool_input: The input parameters for the tool

        Returns:
            A mock success response

        """
        logger.info(f"[OpenAIToolProvider] mcp_call invoked with tool_name: {tool_name}")
        logger.debug(f"[OpenAIToolProvider] tool_input: {tool_input}")

        # Return a mock response
        return {
            "status": "success",
            "message": f"mcp_call tool '{tool_name}' was called successfully",
            "tool_name": tool_name,
            "result": f"Mock result for {tool_name} with input {tool_input}",
        }


class CustomToolProvider(ToolProvider):
    """Provides custom-defined tools."""

    def __init__(self, workspace_path: str | None = None):
        """Initialize CustomToolProvider.

        Args:
            workspace_path: Optional workspace path for loading workspace-specific skills

        """
        self.workspace_path = workspace_path

    def _instantiate_tool(self, tool_class, tool_name: str):
        """Instantiate a tool class with appropriate parameters.

        Args:
            tool_class: The tool class to instantiate
            tool_name: Name of the tool (for logging)

        Returns:
            Instantiated tool object

        Raises:
            TypeError: If tool instantiation fails

        """
        import inspect

        # Get the __init__ signature
        init_signature = inspect.signature(tool_class.__init__)
        parameters = init_signature.parameters

        # Check if 'workspace' is a required parameter
        if "workspace" in parameters:
            # Check if it's required (no default value)
            param = parameters["workspace"]
            if param.default == inspect.Parameter.empty:
                # workspace is required
                if not self.workspace_path:
                    raise TypeError(
                        f"Tool {tool_name} requires workspace_path but none was provided to CustomToolProvider",
                    )
                return tool_class(workspace=self.workspace_path)

        # Check if 'workspace' is an optional parameter
        if "workspace" in parameters and parameters["workspace"].default != inspect.Parameter.empty:
            # workspace is optional, provide it if we have it
            return tool_class(workspace=self.workspace_path)

        # Default: instantiate with no parameters
        return tool_class()

    def get_tools(self) -> list[dict[str, Any]]:
        """Load and parse tools from custom_tools package.

        Returns:
            List of tool dictionaries in standardized format.

        """
        tools = []

        try:
            # Import all tool modules explicitly to ensure they are loaded
            from . import a2ui_tools, custom_tools

            # workflow_tools are now imported directly in custom_tools.__init__.py from workflow_tools_fixed
            from .custom_base_tool import CustomBaseTool
            from .custom_tools import (
                browser_tools,
                command_tools,
                diagram_generator,
                diff_applier,
                document_parser,
                edit_tools,
                mcp_tools,
                mermaid_charting,
                read_tools,
                search_tools,
                timer_tools,
            )

            # Consolidate all modules to scan for tools
            tool_modules = [
                edit_tools,
                read_tools,
                search_tools,
                browser_tools,
                command_tools,
                mcp_tools,
                document_parser,
                diff_applier,
                diagram_generator,
                mermaid_charting,
                timer_tools,
                a2ui_tools,
            ]

            # Also check the top-level custom_tools __init__ for any directly defined/imported tools
            tool_modules.append(custom_tools)

            unique_tools = {}

            for module in tool_modules:
                for name in dir(module):
                    obj = getattr(module, name)

                    # Check if it's a class, a subclass of CustomBaseTool, and not the base class itself
                    if inspect.isclass(obj) and obj is not CustomBaseTool and issubclass(obj, CustomBaseTool):
                        # Avoid processing the same tool class twice
                        if name in unique_tools:
                            continue

                        try:
                            # Instantiate tool with workspace_path if needed
                            tool_instance = self._instantiate_tool(obj, name)

                            # Get tool information from instance
                            tool_name = getattr(tool_instance, "name", name)
                            tool_description = getattr(tool_instance, "description", "")

                            # Get args schema
                            tool_args_schema = getattr(tool_instance, "args_schema", None)
                            if tool_args_schema is None:
                                tool_args_schema = getattr(obj, "args_schema", None)

                            # Convert Pydantic schema to JSON Schema if available
                            parameters = {}
                            if tool_args_schema and inspect.isclass(tool_args_schema) and issubclass(tool_args_schema, BaseModel):
                                parameters = self._pydantic_to_json_schema(tool_args_schema)

                            # Create a tool dictionary
                            tool_dict = {
                                "name": tool_name,
                                "description": tool_description,
                                "parameters": parameters,
                                "callable": tool_instance,  # Pass the entire tool instance
                                "original_tool": tool_instance,  # Pass the original instance for correct type checking
                            }

                            unique_tools[name] = tool_dict
                            logger.info(f"Successfully loaded custom tool: {tool_name}")

                        except Exception as e:
                            # FAST FAIL: Log complete exception with stack trace
                            # Use WARNING level for optional dependencies (e.g., davy-market CLI)
                            from dawei.market.cli_wrapper import CliNotFoundError

                            # Check if this is an optional dependency error
                            is_optional = isinstance(e, (CliNotFoundError, ImportError))
                            # Also check for MarketNotAvailableError from market_tools
                            if not is_optional and type(e).__name__ == "MarketNotAvailableError":
                                is_optional = True

                            log_level = logging.WARNING if is_optional else logging.ERROR
                            logger.log(
                                log_level,
                                f"Error instantiating tool {name}: {e}",
                                exc_info=True,
                                extra={
                                    "session_id": getattr(self, "session_id", "N/A"),
                                    "message_id": "N/A",
                                },
                            )
                            continue

            tools = list(unique_tools.values())

            # Load skills tools if workspace_path is provided
            if self.workspace_path:
                try:
                    from pathlib import Path

                    from .custom_tools.skills_tool import create_skills_tools

                    # Build skills_roots with workspace and global paths
                    skills_roots = []
                    ws_path = Path(self.workspace_path)

                    # Level 1: Workspace (优先级最高)
                    ws_skills_dir = ws_path / ".dawei" / "skills"
                    logger.info(f"[Skills] Checking workspace skills: {ws_skills_dir}")
                    if ws_skills_dir.exists() and any(ws_skills_dir.iterdir()):
                        skills_roots.append(ws_path)
                        logger.info(f"[Skills] ✓ Found workspace skills at: {ws_skills_dir}")

                    # Level 2: Global user (DAWEI_HOME)
                    dawei_home = Path(get_workspaces_root())
                    global_skills_dir = dawei_home / "skills"
                    logger.info(f"[Skills] Checking global skills: {global_skills_dir}")
                    if global_skills_dir.exists() and any(global_skills_dir.iterdir()):
                        skills_roots.append(dawei_home)
                        logger.info(f"[Skills] ✓ Found global skills at: {global_skills_dir}")

                    if skills_roots:
                        # Create skills tools
                        skills_tools = create_skills_tools(skills_roots)
                        for skill_tool in skills_tools:
                            tool_dict = {
                                "name": skill_tool.name,
                                "description": skill_tool.description,
                                "parameters": {},  # Skills tools use their own parameter parsing
                                "callable": skill_tool,
                                "original_tool": skill_tool,
                            }
                            tools.append(tool_dict)
                            logger.info(f"Successfully loaded skills tool: {skill_tool.name}")

                except ImportError as e:
                    logger.warning(f"Failed to import skills_tool module: {e}")
                except Exception:
                    logger.exception("Error loading skills tools: ")

        except ImportError:
            logger.exception("Failed to import custom tools package: ")
            # 继续执行,不中断整个加载过程
        except Exception:
            logger.exception("Unexpected error loading custom tools: ")

        logger.info(f"Loaded {len(tools)} tools from CustomToolProvider")
        return tools

    def _pydantic_to_json_schema(self, schema_class: type[BaseModel]) -> dict[str, Any]:
        """Convert a Pydantic model to JSON Schema format.

        Args:
            schema_class: The Pydantic model class

        Returns:
            JSON Schema dictionary

        """
        try:
            # Get the schema from Pydantic (using model_json_schema for Pydantic v2)
            try:
                schema = schema_class.model_json_schema()
            except AttributeError:
                # Fallback to deprecated schema() method for older Pydantic
                schema = schema_class.schema()

            # Inline definitions: expand $refs to actual schemas
            properties = schema.get("properties", {})
            defs = schema.get("$defs", {})

            # Recursively resolve $refs in properties
            def resolve_refs(obj):
                if isinstance(obj, dict):
                    # Handle anyOf/oneOf/allOf - resolve refs inside the array
                    if "anyOf" in obj:
                        resolved_anyof = [resolve_refs(item) for item in obj["anyOf"]]
                        # If all items in anyOf are the same object (from $ref), simplify to object
                        if len(resolved_anyof) == 1:
                            return {**obj, "anyOf": resolved_anyof}
                        # If we have objects with type information, merge them
                        return {**obj, "anyOf": resolved_anyof}
                    if "oneOf" in obj:
                        return {
                            **obj,
                            "oneOf": [resolve_refs(item) for item in obj["oneOf"]],
                        }
                    if "allOf" in obj:
                        return {
                            **obj,
                            "allOf": [resolve_refs(item) for item in obj["allOf"]],
                        }

                    if "$ref" in obj:
                        # Get the reference path like "#/$defs/TimerSetInput"
                        ref_path = obj["$ref"]
                        # Extract the definition name
                        if ref_path.startswith("#/$defs/"):
                            def_name = ref_path[len("#/$defs/") :]
                            ref_def = defs.get(def_name, {})
                            # Recursively resolve refs in the referenced definition
                            return resolve_refs(ref_def)
                        return obj
                    # Recursively process dict values
                    return {k: resolve_refs(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [resolve_refs(item) for item in obj]
                return obj

            # Resolve all $refs in properties
            resolved_properties = resolve_refs(properties)

            # Convert to the format expected by most LLM providers
            return {
                "type": "object",
                "properties": resolved_properties,
                "required": schema.get("required", []),
            }

        except Exception:
            logger.exception("Error converting Pydantic schema to JSON Schema: ")
            return {"type": "object", "properties": {}, "required": []}

    def _parse_function_tool(self, func: callable, name: str) -> dict[str, Any]:
        """Parse a function decorated with @tool into a standard format.

        Args:
            func: The function to parse
            name: The name of the function

        Returns:
            Tool dictionary or None if parsing fails

        """
        try:
            # Get function signature
            sig = inspect.signature(func)

            # Get docstring for description
            description = inspect.getdoc(func) or f"Tool function: {name}"

            # Parse parameters
            parameters = {"type": "object", "properties": {}, "required": []}

            type_hints = get_type_hints(func)

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue

                param_info = {"type": "string"}  # Default type

                # Try to get type from type hints
                if param_name in type_hints:
                    param_type = type_hints[param_name]
                    if hasattr(param_type, "__origin__"):
                        # Handle generic types like List[str]
                        origin = param_type.__origin__
                        if origin is list:
                            param_info["type"] = "array"
                            if hasattr(param_type, "__args__") and param_type.__args__:
                                item_type = param_type.__args__[0]
                                if item_type is str:
                                    param_info["items"] = {"type": "string"}
                                elif item_type is int:
                                    param_info["items"] = {"type": "integer"}
                                elif item_type is float:
                                    param_info["items"] = {"type": "number"}
                                elif item_type is bool:
                                    param_info["items"] = {"type": "boolean"}
                    elif param_type is str:
                        param_info["type"] = "string"
                    elif param_type is int:
                        param_info["type"] = "integer"
                    elif param_type is float:
                        param_info["type"] = "number"
                    elif param_type is bool:
                        param_info["type"] = "boolean"

                # Check if parameter has a default value
                if param.default != inspect.Parameter.empty:
                    param_info["default"] = param.default
                else:
                    parameters["required"].append(param_name)

                # Add description from docstring if available
                # This is a simplified approach - in production, you might want more sophisticated parsing
                if ":" in description:
                    for line in description.split("\n"):
                        if line.strip().startswith(f"{param_name}:"):
                            param_info["description"] = line.split(":", 1)[1].strip()
                            break

                parameters["properties"][param_name] = param_info

            return {
                "name": getattr(func, "tool_name", name),
                "description": getattr(func, "tool_description", description),
                "parameters": parameters,
                "callable": func,
            }

        except Exception as e:
            logger.exception(f"Error parsing function tool {name}: {e}")
            return None
