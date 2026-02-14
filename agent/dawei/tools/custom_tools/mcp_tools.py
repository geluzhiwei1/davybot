# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import json
from typing import Any

from pydantic import BaseModel, Field

from dawei.tools.custom_base_tool import CustomBaseTool


# Use MCP Tool Tool
class UseMCPToolInput(BaseModel):
    """Input for UseMCPToolTool."""

    server_name: str = Field(..., description="Name of the MCP server providing the tool.")
    tool_name: str = Field(..., description="Name of the tool to execute.")
    arguments: dict[str, Any] = Field(
        ...,
        description="JSON object containing the tool's input parameters.",
    )


class UseMCPToolTool(CustomBaseTool):
    """Tool for using tools provided by MCP servers."""

    name: str = "use_mcp_tool"
    description: str = "Uses a tool provided by a connected MCP server with specified parameters."
    args_schema: type[BaseModel] = UseMCPToolInput

    def __init__(self):
        super().__init__()
        # Mock MCP server registry
        self.mcp_servers = {
            "weather-server": {
                "tools": ["get_forecast", "get_current_weather", "get_alerts"],
                "endpoint": "http://localhost:3001",
            },
            "database-server": {
                "tools": ["query", "insert", "update", "delete"],
                "endpoint": "http://localhost:3002",
            },
            "file-server": {
                "tools": ["read", "write", "list", "delete"],
                "endpoint": "http://localhost:3003",
            },
        }

    def _run(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Use MCP tool (mock implementation)."""
        try:
            # Check if server exists
            if server_name not in self.mcp_servers:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"MCP server '{server_name}' not found",
                        "available_servers": list(self.mcp_servers.keys()),
                    },
                    indent=2,
                )

            server_info = self.mcp_servers[server_name]

            # Check if tool exists
            if tool_name not in server_info["tools"]:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Tool '{tool_name}' not found in server '{server_name}'",
                        "available_tools": server_info["tools"],
                    },
                    indent=2,
                )

            # Mock execution based on tool name
            result = self._mock_tool_execution(server_name, tool_name, arguments)

            return json.dumps(
                {
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "status": "success",
                    "result": result,
                },
                indent=2,
            )

        # Input validation and serialization errors
        except (KeyError, TypeError, ValueError) as e:
            return json.dumps(
                {
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "status": "error",
                    "message": f"Invalid tool parameters or execution error: {e!s}",
                },
                indent=2,
            )

    def _mock_tool_execution(self, server_name: str, tool_name: str, arguments: dict) -> dict:
        """Mock execution of MCP tools."""
        if server_name == "weather-server":
            if tool_name == "get_forecast":
                city = arguments.get("city", "Unknown")
                days = arguments.get("days", 5)
                return {
                    "city": city,
                    "days": days,
                    "forecast": [{"day": i + 1, "temp": f"{20 + i}°C", "condition": "Sunny"} for i in range(days)],
                }
            if tool_name == "get_current_weather":
                city = arguments.get("city", "Unknown")
                return {
                    "city": city,
                    "temperature": "22°C",
                    "condition": "Partly Cloudy",
                    "humidity": "65%",
                }

        elif server_name == "database-server":
            if tool_name == "query":
                table = arguments.get("table", "unknown")
                return {
                    "table": table,
                    "query": f"SELECT * FROM {table}",
                    "results": [
                        {"id": 1, "name": "Sample Record 1"},
                        {"id": 2, "name": "Sample Record 2"},
                    ],
                    "count": 2,
                }
            if tool_name == "insert":
                table = arguments.get("table", "unknown")
                data = arguments.get("data", {})
                return {"table": table, "inserted_data": data, "inserted_id": 123}

        elif server_name == "file-server":
            if tool_name == "read":
                path = arguments.get("path", "unknown")
                return {
                    "path": path,
                    "content": f"Mock content of file: {path}",
                    "size": 1024,
                }
            if tool_name == "list":
                path = arguments.get("path", ".")
                return {"path": path, "files": ["file1.txt", "file2.py", "directory1/"]}

        return {"message": f"Mock execution of {tool_name} completed"}


# Access MCP Resource Tool
class AccessMCPResourceInput(BaseModel):
    """Input for AccessMCPResourceTool."""

    server_name: str = Field(..., description="Name of the MCP server providing the resource.")
    uri: str = Field(..., description="URI identifying the specific resource to access.")


class AccessMCPResourceTool(CustomBaseTool):
    """Tool for accessing resources provided by MCP servers."""

    name: str = "access_mcp_resource"
    description: str = "Accesses a resource provided by a connected MCP server using its URI."
    args_schema: type[BaseModel] = AccessMCPResourceInput

    def __init__(self):
        super().__init__()
        # Mock MCP server registry
        self.mcp_servers = {
            "weather-server": {
                "resources": [
                    "weather://san-francisco/current",
                    "weather://new-york/current",
                    "weather://london/current",
                ],
                "endpoint": "http://localhost:3001",
            },
            "database-server": {
                "resources": ["db://users/all", "db://products/all", "db://orders/all"],
                "endpoint": "http://localhost:3002",
            },
            "file-server": {
                "resources": [
                    "file://documents/report.pdf",
                    "file://images/logo.png",
                    "file://config/settings.json",
                ],
                "endpoint": "http://localhost:3003",
            },
        }

    def _run(self, server_name: str, uri: str) -> str:
        """Access MCP resource (mock implementation)."""
        try:
            # Check if server exists
            if server_name not in self.mcp_servers:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"MCP server '{server_name}' not found",
                        "available_servers": list(self.mcp_servers.keys()),
                    },
                    indent=2,
                )

            server_info = self.mcp_servers[server_name]

            # Check if resource exists (mock check)
            resource_found = any(uri.startswith(res.split("/")[0] + "://") for res in server_info["resources"])

            if not resource_found:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Resource '{uri}' not found in server '{server_name}'",
                        "available_resources": server_info["resources"],
                    },
                    indent=2,
                )

            # Mock resource access
            result = self._mock_resource_access(server_name, uri)

            return json.dumps(
                {
                    "server_name": server_name,
                    "uri": uri,
                    "status": "success",
                    "resource": result,
                },
                indent=2,
            )

        # Input validation and serialization errors
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            return json.dumps(
                {
                    "server_name": server_name,
                    "uri": uri,
                    "status": "error",
                    "message": f"Invalid resource parameters or access error: {e!s}",
                },
                indent=2,
            )

    def _mock_resource_access(self, server_name: str, uri: str) -> dict:
        """Mock access to MCP resources."""
        if server_name == "weather-server":
            if "current" in uri:
                city = uri.split("//")[1].split("/")[0].replace("-", " ").title()
                return {
                    "type": "current_weather",
                    "city": city,
                    "data": {
                        "temperature": "22°C",
                        "condition": "Partly Cloudy",
                        "humidity": "65%",
                        "wind_speed": "10 km/h",
                        "updated_at": "2024-01-01T12:00:00Z",
                    },
                }

        elif server_name == "database-server":
            if "users" in uri:
                return {
                    "type": "database_table",
                    "table": "users",
                    "data": [
                        {"id": 1, "name": "John Doe", "email": "john@example.com"},
                        {"id": 2, "name": "Jane Smith", "email": "jane@example.com"},
                    ],
                    "total_count": 2,
                }
            if "products" in uri:
                return {
                    "type": "database_table",
                    "table": "products",
                    "data": [
                        {"id": 1, "name": "Product A", "price": 99.99},
                        {"id": 2, "name": "Product B", "price": 149.99},
                    ],
                    "total_count": 2,
                }

        elif server_name == "file-server":
            if uri.endswith(".pdf"):
                return {
                    "type": "file",
                    "format": "pdf",
                    "size": 2048576,
                    "content": "Mock PDF content",
                    "metadata": {
                        "title": "Sample Report",
                        "author": "System",
                        "created": "2024-01-01",
                    },
                }
            if uri.endswith(".json"):
                return {
                    "type": "file",
                    "format": "json",
                    "size": 1024,
                    "content": {
                        "setting1": "value1",
                        "setting2": "value2",
                        "enabled": True,
                    },
                }

        return {"message": f"Mock resource access for {uri} completed"}


# List MCP Servers Tool
class ListMCPServersInput(BaseModel):
    """Input for ListMCPServersTool."""

    show_details: bool = Field(False, description="Whether to show detailed server information.")


class ListMCPServersTool(CustomBaseTool):
    """Tool for listing available MCP servers."""

    name: str = "list_mcp_servers"
    description: str = "Lists all available MCP servers and their tools/resources."
    args_schema: type[BaseModel] = ListMCPServersInput

    def __init__(self):
        super().__init__()
        # Mock MCP server registry
        self.mcp_servers = {
            "weather-server": {
                "tools": ["get_forecast", "get_current_weather", "get_alerts"],
                "resources": [
                    "weather://san-francisco/current",
                    "weather://new-york/current",
                    "weather://london/current",
                ],
                "endpoint": "http://localhost:3001",
                "status": "connected",
            },
            "database-server": {
                "tools": ["query", "insert", "update", "delete"],
                "resources": ["db://users/all", "db://products/all", "db://orders/all"],
                "endpoint": "http://localhost:3002",
                "status": "connected",
            },
            "file-server": {
                "tools": ["read", "write", "list", "delete"],
                "resources": [
                    "file://documents/report.pdf",
                    "file://images/logo.png",
                    "file://config/settings.json",
                ],
                "endpoint": "http://localhost:3003",
                "status": "connected",
            },
        }

    def _run(self, show_details: bool = False) -> str:
        """List MCP servers."""
        try:
            servers = []

            for name, info in self.mcp_servers.items():
                server_info = {"name": name, "status": info["status"]}

                if show_details:
                    server_info.update(
                        {
                            "endpoint": info["endpoint"],
                            "tools": info["tools"],
                            "resources": info["resources"],
                        },
                    )
                else:
                    server_info.update(
                        {
                            "tools_count": len(info["tools"]),
                            "resources_count": len(info["resources"]),
                        },
                    )

                servers.append(server_info)

            return json.dumps({"total_servers": len(servers), "servers": servers}, indent=2)

        # Input validation and serialization errors
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            return json.dumps(
                {"status": "error", "message": f"Error listing MCP servers: {e!s}"},
                indent=2,
            )
