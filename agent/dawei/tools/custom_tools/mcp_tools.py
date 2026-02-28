# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""MCP (Model Context Protocol) Tools

提供真实的MCP工具调用和资源访问功能。
依赖MCP Python SDK和已配置的MCP服务器。
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.mcp_tool_manager import MCPToolManager


def _run_async(coro):
    """在现有事件循环中运行协程，或者创建新的事件循环

    Args:
        coro: 要运行的协程

    Returns:
        协程的返回值
    """
    try:
        asyncio.get_running_loop()
        # 已经在运行的事件循环中，创建 task 并等待
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # 没有运行的事件循环，使用 asyncio.run
        return asyncio.run(coro)


# Use MCP Tool
class UseMCPToolInput(BaseModel):
    """Input for UseMCPTool."""

    server_name: str = Field(..., description="Name of the MCP server providing the tool.")
    tool_name: str = Field(..., description="Name of the tool to execute.")
    arguments: dict[str, Any] = Field(
        ...,
        description="JSON object containing the tool's input parameters.",
    )


class UseMCPTool(CustomBaseTool):
    """Tool for using tools provided by MCP servers."""

    name: str = "use_mcp_tool"
    description: str = (
        "Uses a tool provided by a connected MCP server with specified parameters. "
        "Requires MCP server to be configured and connected."
    )
    args_schema: type[BaseModel] = UseMCPToolInput

    def __init__(self, workspace_path: str | None = None):
        super().__init__()
        self.mcp_manager = MCPToolManager(workspace_path=workspace_path)

    @safe_tool_operation(
        "use_mcp_tool",
        fallback_value='{"status": "error", "message": "Failed to execute MCP tool"}',
    )
    def _run(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Use MCP tool (real implementation using MCP SDK)."""
        try:
            # Execute tool call asynchronously
            result = _run_async(
                self.mcp_manager.call_tool(server_name, tool_name, arguments)
            )
            return json.dumps(result, indent=2, ensure_ascii=False)

        except Exception as e:
            return json.dumps(
                {
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "status": "error",
                    "message": f"Failed to execute MCP tool: {e!s}",
                },
                indent=2,
            )


# Access MCP Resource
class AccessMCPResourceInput(BaseModel):
    """Input for AccessMCPResource."""

    server_name: str = Field(..., description="Name of the MCP server providing the resource.")
    uri: str = Field(..., description="URI identifying the specific resource to access.")


class AccessMCPResource(CustomBaseTool):
    """Tool for accessing resources provided by MCP servers."""

    name: str = "access_mcp_resource"
    description: str = (
        "Accesses a resource provided by a connected MCP server using its URI. "
        "Requires MCP server to be configured and connected."
    )
    args_schema: type[BaseModel] = AccessMCPResourceInput

    def __init__(self, workspace_path: str | None = None):
        super().__init__()
        self.mcp_manager = MCPToolManager(workspace_path=workspace_path)

    @safe_tool_operation(
        "access_mcp_resource",
        fallback_value='{"status": "error", "message": "Failed to access MCP resource"}',
    )
    def _run(self, server_name: str, uri: str) -> str:
        """Access MCP resource (real implementation using MCP SDK)."""
        try:
            # Execute resource access asynchronously
            result = _run_async(self.mcp_manager.access_resource(server_name, uri))
            return json.dumps(result, indent=2, ensure_ascii=False)

        except Exception as e:
            return json.dumps(
                {
                    "server_name": server_name,
                    "uri": uri,
                    "status": "error",
                    "message": f"Failed to access MCP resource: {e!s}",
                },
                indent=2,
            )


# List MCP Servers
class ListMCPServersInput(BaseModel):
    """Input for ListMCPServers."""

    show_details: bool = Field(False, description="Whether to show detailed server information.")


class ListMCPServers(CustomBaseTool):
    """Tool for listing available MCP servers."""

    name: str = "list_mcp_servers"
    description: str = "Lists all configured MCP servers and their connection status."
    args_schema: type[BaseModel] = ListMCPServersInput

    def __init__(self, workspace_path: str | None = None):
        super().__init__()
        self.mcp_manager = MCPToolManager(workspace_path=workspace_path)

    @safe_tool_operation(
        "list_mcp_servers",
        fallback_value='{"status": "error", "message": "Failed to list MCP servers"}',
    )
    def _run(self, show_details: bool = False) -> str:
        """List MCP servers."""
        try:
            servers = []
            all_servers = self.mcp_manager.get_all_servers()

            for name, server_info in all_servers.items():
                server_dict = {
                    "name": name,
                    "status": server_info.status,
                    "connected_at": server_info.connected_at.isoformat() if server_info.connected_at else None,
                }

                if show_details:
                    config = server_info.config.to_dict()
                    server_dict.update(
                        {
                            "command": config.get("command"),
                            "args": config.get("args", []),
                            "tools_count": len(server_info.tools),
                            "resources_count": len(server_info.resources),
                            "tools": server_info.tools[:5],  # Show first 5 tools
                            "resources": server_info.resources[:5],  # Show first 5 resources
                        }
                    )
                else:
                    server_dict.update(
                        {
                            "tools_count": len(server_info.tools),
                            "resources_count": len(server_info.resources),
                        }
                    )

                servers.append(server_dict)

            return json.dumps(
                {
                    "total_servers": len(servers),
                    "servers": servers,
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps(
                {"status": "error", "message": f"Error listing MCP servers: {e!s}"},
                indent=2,
            )


# Connect MCP Server
class ConnectMCPServerInput(BaseModel):
    """Input for ConnectMCPServer."""

    server_name: str = Field(..., description="Name of the MCP server to connect.")


class ConnectMCPServer(CustomBaseTool):
    """Tool for connecting to an MCP server."""

    name: str = "connect_mcp_server"
    description: str = "Connects to a configured MCP server and initializes its tools/resources."
    args_schema: type[BaseModel] = ConnectMCPServerInput

    def __init__(self, workspace_path: str | None = None):
        super().__init__()
        self.mcp_manager = MCPToolManager(workspace_path=workspace_path)

    @safe_tool_operation(
        "connect_mcp_server",
        fallback_value='{"status": "error", "message": "Failed to connect to MCP server"}',
    )
    def _run(self, server_name: str) -> str:
        """Connect to MCP server."""
        try:
            # Execute connection asynchronously
            success = _run_async(self.mcp_manager.connect_server(server_name))

            if success:
                server_info = self.mcp_manager.get_server_info(server_name)
                return json.dumps(
                    {
                        "server_name": server_name,
                        "status": "connected",
                        "tools_count": len(server_info.tools) if server_info else 0,
                        "resources_count": len(server_info.resources) if server_info else 0,
                        "message": f"Successfully connected to MCP server: {server_name}",
                    },
                    indent=2,
                )
            server_info = self.mcp_manager.get_server_info(server_name)
            return json.dumps(
                {
                    "server_name": server_name,
                    "status": "error",
                    "message": server_info.last_error if server_info else "Unknown error",
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps(
                {
                    "server_name": server_name,
                    "status": "error",
                    "message": f"Failed to connect to MCP server: {e!s}",
                },
                indent=2,
            )


# Disconnect MCP Server
class DisconnectMCPServerInput(BaseModel):
    """Input for DisconnectMCPServer."""

    server_name: str = Field(..., description="Name of the MCP server to disconnect.")


class DisconnectMCPServer(CustomBaseTool):
    """Tool for disconnecting from an MCP server."""

    name: str = "disconnect_mcp_server"
    description: str = "Disconnects from a connected MCP server."
    args_schema: type[BaseModel] = DisconnectMCPServerInput

    def __init__(self, workspace_path: str | None = None):
        super().__init__()
        self.mcp_manager = MCPToolManager(workspace_path=workspace_path)

    @safe_tool_operation(
        "disconnect_mcp_server",
        fallback_value='{"status": "error", "message": "Failed to disconnect from MCP server"}',
    )
    def _run(self, server_name: str) -> str:
        """Disconnect from MCP server."""
        try:
            # Execute disconnection asynchronously
            success = _run_async(self.mcp_manager.disconnect_server(server_name))

            if success:
                return json.dumps(
                    {
                        "server_name": server_name,
                        "status": "disconnected",
                        "message": f"Successfully disconnected from MCP server: {server_name}",
                    },
                    indent=2,
                )
            return json.dumps(
                {
                    "server_name": server_name,
                    "status": "error",
                    "message": "Failed to disconnect from MCP server",
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps(
                {
                    "server_name": server_name,
                    "status": "error",
                    "message": f"Failed to disconnect from MCP server: {e!s}",
                },
                indent=2,
            )


__all__ = [
    "UseMCPTool",
    "AccessMCPResource",
    "ListMCPServers",
    "ConnectMCPServer",
    "DisconnectMCPServer",
]
