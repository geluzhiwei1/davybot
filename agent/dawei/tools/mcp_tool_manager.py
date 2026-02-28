# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""MCP 工具管理器 - 实现 user/workspace 二级加载和管理机制
支持同名覆盖，优先级：workspace > user

使用真实的MCP Python SDK实现客户端连接和工具调用。
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

from dawei.core.decorators import safe_system_operation

# Import MCP SDK (required dependency)
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    ClientSession = None  # type: ignore
    StdioServerParameters = None  # type: ignore
    stdio_client = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class MCPConfig:
    """MCP配置类 - 从 user_workspace.py 转移过来"""

    server_name: str
    command: str
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    always_allow: list[str] = field(default_factory=list)
    timeout: int = 300
    source_level: str = "user"  # user, workspace

    @classmethod
    def from_dict(
        cls,
        server_name: str,
        config_dict: dict[str, Any],
        source_level: str = "user",
    ) -> "MCPConfig":
        """从字典创建MCP配置"""
        return cls(
            server_name=server_name,
            command=config_dict.get("command", ""),
            args=config_dict.get("args", []),
            cwd=config_dict.get("cwd"),
            always_allow=config_dict.get("alwaysAllow", []),
            timeout=config_dict.get("timeout", 300),
            source_level=source_level,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "server_name": self.server_name,
            "command": self.command,
            "args": self.args,
            "cwd": self.cwd,
            "always_allow": self.always_allow,
            "timeout": self.timeout,
            "source_level": self.source_level,
        }

    def merge_with(self, other: "MCPConfig") -> "MCPConfig":
        """与另一个配置合并，other 的值会覆盖当前值"""
        if not other:
            return self

        # 创建新的配置，other 的非空字段覆盖 self 的字段
        merged = MCPConfig.from_dict(self.server_name, self.to_dict(), self.source_level)

        for key, value in other.to_dict().items():
            if key != "server_name" and value is not None and value not in ("", [], {}):
                setattr(merged, key, value)

        # 更新 source_level 为更高优先级的配置
        merged.source_level = other.source_level

        return merged


@dataclass
class MCPServerInfo:
    """MCP服务器信息"""

    name: str
    config: MCPConfig
    status: str = "disconnected"  # disconnected, connecting, connected, error
    last_error: str | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    connected_at: datetime | None = None
    session: Any = None  # ClientSession instance
    read_stream: Any = None  # Read stream for stdio_client
    write_stream: Any = None  # Write stream for stdio_client
    client_context: Any = None  # stdio_client context manager

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "config": self.config.to_dict(),
            "status": self.status,
            "last_error": self.last_error,
            "tools": self.tools,
            "resources": self.resources,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
        }


class MCPConfigLoader:
    """MCP配置加载器"""

    def __init__(self):
        self._cache: dict[str, dict[str, MCPConfig]] = {}
        self._cache_timestamps: dict[str, datetime] = {}
        self._cache_ttl = 300  # 5分钟缓存

    def _get_cache_key(self, level: str, path: str | None = None) -> str:
        """获取缓存键"""
        return f"mcp_{level}:{path or 'default'}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self._cache_timestamps:
            return False

        age = (datetime.now(UTC) - self._cache_timestamps[cache_key]).total_seconds()
        return age < self._cache_ttl

    def _set_cache(self, cache_key: str, configs: dict[str, MCPConfig]):
        """设置缓存"""
        self._cache[cache_key] = configs
        self._cache_timestamps[cache_key] = datetime.now(UTC)

    def _get_cache(self, cache_key: str) -> dict[str, MCPConfig] | None:
        """获取缓存"""
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key)
        return None

    @safe_system_operation("load_user_mcp_configs", fallback_value={})
    def load_user_mcp_configs(self) -> dict[str, MCPConfig]:
        """加载用户级MCP配置"""
        user_home = Path.home()
        user_config_dir = user_home / ".dawei" / "configs"

        if not user_config_dir.exists():
            logger.debug(f"User config directory not found: {user_config_dir}")
            return {}

        cache_key = self._get_cache_key("user", str(user_config_dir))
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        configs = {}
        mcp_config_file = user_config_dir / "mcp.json"

        if mcp_config_file.exists():
            with Path(mcp_config_file).open(encoding="utf-8") as f:
                config_data = json.load(f)

            if "mcpServers" in config_data:
                for server_name, server_config in config_data["mcpServers"].items():
                    configs[server_name] = MCPConfig.from_dict(server_name, server_config, "user")

            logger.info(f"Loaded {len(configs)} user MCP configs from {mcp_config_file}")

        self._set_cache(cache_key, configs)
        return configs

    @safe_system_operation("load_workspace_mcp_configs", fallback_value={})
    def load_workspace_mcp_configs(self, workspace_path: str) -> dict[str, MCPConfig]:
        """加载工作区级MCP配置"""
        workspace_dir = Path(workspace_path)
        # 保持与用户配置目录一致的路径结构
        user_config_dir = workspace_dir / ".dawei" / "configs"

        if not user_config_dir.exists():
            logger.debug(f"Workspace config directory not found: {user_config_dir}")
            return {}

        cache_key = self._get_cache_key("workspace", str(user_config_dir))
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        configs = {}
        # 使用与用户配置相同的路径结构：mcp.json
        mcp_config_file = user_config_dir / "mcp.json"

        if mcp_config_file.exists():
            with Path(mcp_config_file).open(encoding="utf-8") as f:
                config_data = json.load(f)

            if "mcpServers" in config_data:
                for server_name, server_config in config_data["mcpServers"].items():
                    configs[server_name] = MCPConfig.from_dict(
                        server_name,
                        server_config,
                        "workspace",
                    )

            logger.info(f"Loaded {len(configs)} workspace MCP configs from {mcp_config_file}")

        self._set_cache(cache_key, configs)
        return configs

    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("MCP config cache cleared")


class MCPToolManager:
    """MCP工具管理器 - 实现二级加载和管理机制 (user, workspace)"""

    def __init__(self, workspace_path: str | None = None):
        self.workspace_path = workspace_path
        self.loader = MCPConfigLoader()

        # 二级配置缓存
        self._user_configs: dict[str, MCPConfig] = {}
        self._workspace_configs: dict[str, MCPConfig] = {}

        # 合并后的配置
        self._merged_configs: dict[str, MCPConfig] = {}

        # 服务器信息
        self._servers: dict[str, MCPServerInfo] = {}

        # 初始化配置
        self._load_all_configs()

    @safe_system_operation("load_all_mcp_configs", log_errors=False)
    def _load_all_configs(self):
        """加载所有级别的配置"""
        # 按优先级顺序加载
        self._user_configs = self.loader.load_user_mcp_configs()

        if self.workspace_path:
            self._workspace_configs = self.loader.load_workspace_mcp_configs(self.workspace_path)

        # 合并配置
        self._merge_configs()

        # 初始化服务器信息
        self._initialize_servers()

        logger.info(f"MCPToolManager initialized with {len(self._merged_configs)} total servers")

    def _merge_configs(self):
        """合并二级配置，支持同名服务器的完全覆盖"""
        self._merged_configs.clear()

        # 按优先级顺序合并：user -> workspace
        # 后面的会完全覆盖前面的同名配置

        # 1. 从 user 开始
        for name, config in self._user_configs.items():
            self._merged_configs[name] = config
            logger.debug(f"Added user MCP config: {name}")

        # 2. 合并 workspace 配置（完全覆盖）
        for name, config in self._workspace_configs.items():
            if name in self._merged_configs:
                logger.debug(f"Overriding MCP config '{name}' with workspace config")
            else:
                logger.debug(f"Added workspace MCP config: {name}")
            self._merged_configs[name] = config

        # 统计覆盖情况
        override_count = 0
        for name in self._merged_configs:
            sources = self.get_config_sources(name)
            if sum(sources.values()) > 1:  # 如果配置存在于多个级别
                override_count += 1

        logger.info(
            f"Merged MCP configurations: {len(self._merged_configs)} servers, {override_count} overridden",
        )

    def _initialize_servers(self):
        """初始化服务器信息"""
        self._servers.clear()

        for name, config in self._merged_configs.items():
            self._servers[name] = MCPServerInfo(name=name, config=config, status="disconnected")

    def set_workspace_path(self, workspace_path: str):
        """设置工作区路径并重新加载配置"""
        self.workspace_path = workspace_path
        self._workspace_configs = self.loader.load_workspace_mcp_configs(workspace_path)
        self._merge_configs()
        self._initialize_servers()
        logger.info(f"Workspace path set to {workspace_path}, MCP configs reloaded")

    def get_all_configs(self) -> dict[str, MCPConfig]:
        """获取所有合并后的MCP配置"""
        return self._merged_configs.copy()

    def get_config(self, server_name: str) -> MCPConfig | None:
        """获取指定服务器的MCP配置"""
        return self._merged_configs.get(server_name)

    def get_config_sources(self, server_name: str) -> dict[str, bool]:
        """获取MCP配置来源信息"""
        return {
            "user": server_name in self._user_configs,
            "workspace": server_name in self._workspace_configs,
        }

    def get_config_override_info(self, server_name: str) -> dict[str, Any]:
        """获取MCP配置覆盖的详细信息"""
        sources = self.get_config_sources(server_name)
        active_source = None

        # 确定当前活跃的来源（按优先级）
        if sources["workspace"]:
            active_source = "workspace"
        elif sources["user"]:
            active_source = "user"

        # 获取各级配置
        configs = {}
        if sources["user"]:
            configs["user"] = self._user_configs[server_name].to_dict()
        if sources["workspace"]:
            configs["workspace"] = self._workspace_configs[server_name].to_dict()

        return {
            "server_name": server_name,
            "sources": sources,
            "active_source": active_source,
            "configs": configs,
            "is_overridden": sum(sources.values()) > 1,
        }

    def get_all_override_info(self) -> list[dict[str, Any]]:
        """获取所有MCP配置的覆盖信息"""
        override_info = []

        for server_name in self._merged_configs:
            info = self.get_config_override_info(server_name)
            if info["is_overridden"]:
                override_info.append(info)

        return override_info

    def get_server_info(self, server_name: str) -> MCPServerInfo | None:
        """获取服务器信息"""
        return self._servers.get(server_name)

    def get_all_servers(self) -> dict[str, MCPServerInfo]:
        """获取所有服务器信息"""
        return self._servers.copy()

    def get_servers_by_status(self, status: str) -> list[MCPServerInfo]:
        """按状态获取服务器"""
        return [server for server in self._servers.values() if server.status == status]

    @safe_system_operation("connect_mcp_server", fallback_value=False)
    async def connect_server(self, server_name: str) -> bool:
        """连接MCP服务器"""
        if not MCP_AVAILABLE:
            logger.error("MCP SDK is not installed. Install with: pip install mcp")
            return False

        if server_name not in self._servers:
            logger.error(f"Server '{server_name}' not found")
            return False

        server_info = self._servers[server_name]
        config = server_info.config

        logger.info(f"Connecting to MCP server: {server_name}")
        server_info.status = "connecting"
        server_info.last_error = None

        try:
            # Create stdio server parameters
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                cwd=config.cwd,
            )

            # Create stdio client context
            client_context = stdio_client(server_params)

            # Manually enter the context to keep streams alive
            read_stream, write_stream = await client_context.__aenter__()

            # Create client session
            session = ClientSession(read_stream, write_stream)

            # Initialize the session
            await session.initialize()

            # Store everything needed to keep connection alive
            server_info.client_context = client_context
            server_info.read_stream = read_stream
            server_info.write_stream = write_stream
            server_info.session = session
            server_info.status = "connected"
            server_info.connected_at = datetime.now(UTC)

            # List available tools
            tools_response = await session.list_tools()
            server_info.tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                }
                for tool in tools_response.tools
            ]

            # List available resources
            try:
                resources_response = await session.list_resources()
                server_info.resources = [
                    {
                        "uri": resource.uri,
                        "name": resource.name,
                        "description": resource.description,
                        "mime_type": resource.mimeType,
                    }
                    for resource in resources_response.resources
                ]
            except Exception as e:
                logger.warning(f"Failed to list resources for {server_name}: {e}")
                server_info.resources = []

            logger.info(
                f"Successfully connected to MCP server: {server_name} "
                f"({len(server_info.tools)} tools, {len(server_info.resources)} resources)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to connect to MCP server {server_name}: {e}", exc_info=True)
            server_info.status = "error"
            server_info.last_error = str(e)

            # Clean up on error
            if server_info.client_context:
                try:
                    await server_info.client_context.__aexit__(None, None, None)
                except Exception:
                    pass
            server_info.session = None
            server_info.read_stream = None
            server_info.write_stream = None
            server_info.client_context = None

            return False

    @safe_system_operation("disconnect_mcp_server", fallback_value=False)
    async def disconnect_server(self, server_name: str) -> bool:
        """断开MCP服务器连接"""
        if not MCP_AVAILABLE:
            logger.error("MCP SDK is not installed. Install with: pip install mcp")
            return False

        if server_name not in self._servers:
            logger.error(f"Server '{server_name}' not found")
            return False

        server_info = self._servers[server_name]

        logger.info(f"Disconnecting from MCP server: {server_name}")

        try:
            # Close the client context if it exists
            if server_info.client_context:
                await server_info.client_context.__aexit__(None, None, None)
                server_info.client_context = None

            # Clear streams and session
            server_info.read_stream = None
            server_info.write_stream = None
            server_info.session = None

            # Update status
            server_info.status = "disconnected"
            server_info.connected_at = None
            server_info.tools.clear()
            server_info.resources.clear()

            logger.info(f"Successfully disconnected from MCP server: {server_name}")
            return True

        except Exception as e:
            logger.error(f"Error disconnecting from MCP server {server_name}: {e}", exc_info=True)
            server_info.last_error = str(e)
            return False

    async def connect_all_servers(self) -> dict[str, bool]:
        """连接所有服务器"""
        results = {}

        for server_name in self._servers:
            results[server_name] = await self.connect_server(server_name)

        return results

    async def disconnect_all_servers(self) -> dict[str, bool]:
        """断开所有服务器连接"""
        results = {}

        for server_name in self._servers:
            results[server_name] = await self.disconnect_server(server_name)

        return results

    def reload_configs(self):
        """重新加载所有配置"""
        self.loader.clear_cache()
        self._load_all_configs()
        logger.info("All MCP configurations reloaded")

    def get_statistics(self) -> dict[str, Any]:
        """获取MCP统计信息"""
        # 统计覆盖情况
        override_info = self.get_all_override_info()
        overridden_configs = len(override_info)

        # 统计服务器状态
        status_counts = {}
        for server in self._servers.values():
            status = server.status
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_servers": len(self._merged_configs),
            "overridden_configs": overridden_configs,
            "by_source_level": {
                "user": len(self._user_configs),
                "workspace": len(self._workspace_configs),
            },
            "by_status": status_counts,
            "override_summary": {
                "total_overridden": overridden_configs,
                "override_details": override_info[:5],  # 只显示前5个覆盖详情
            },
        }

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """调用MCP工具

        Args:
            server_name: MCP服务器名称
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP SDK is not installed. Install with: pip install mcp")

        server_info = self.get_server_info(server_name)
        if not server_info:
            raise ValueError(f"MCP server '{server_name}' not found")

        if server_info.status != "connected":
            raise RuntimeError(f"MCP server '{server_name}' is not connected (status: {server_info.status})")

        if not server_info.session:
            raise RuntimeError(f"MCP server '{server_name}' has no active session")

        try:
            logger.info(f"Calling MCP tool: {server_name}.{tool_name} with arguments: {arguments}")

            # Call the tool
            result = await server_info.session.call_tool(tool_name, arguments)

            logger.info(f"MCP tool {server_name}.{tool_name} executed successfully")
            return {
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "status": "success",
                "result": result,
            }

        except Exception as e:
            logger.error(f"Failed to call MCP tool {server_name}.{tool_name}: {e}", exc_info=True)
            return {
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "status": "error",
                "error": str(e),
            }

    async def access_resource(self, server_name: str, uri: str) -> dict[str, Any]:
        """访问MCP资源

        Args:
            server_name: MCP服务器名称
            uri: 资源URI

        Returns:
            资源内容
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP SDK is not installed. Install with: pip install mcp")

        server_info = self.get_server_info(server_name)
        if not server_info:
            raise ValueError(f"MCP server '{server_name}' not found")

        if server_info.status != "connected":
            raise RuntimeError(f"MCP server '{server_name}' is not connected (status: {server_info.status})")

        if not server_info.session:
            raise RuntimeError(f"MCP server '{server_name}' has no active session")

        try:
            logger.info(f"Accessing MCP resource: {server_name}:{uri}")

            # Read the resource
            result = await server_info.session.read_resource(uri)

            logger.info(f"MCP resource {server_name}:{uri} accessed successfully")
            return {
                "server_name": server_name,
                "uri": uri,
                "status": "success",
                "resource": result,
            }

        except Exception as e:
            logger.error(f"Failed to access MCP resource {server_name}:{uri}: {e}", exc_info=True)
            return {
                "server_name": server_name,
                "uri": uri,
                "status": "error",
                "error": str(e),
            }

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "workspace_path": self.workspace_path,
            "configs": {name: config.to_dict() for name, config in self._merged_configs.items()},
            "servers": {name: server.to_dict() for name, server in self._servers.items()},
            "statistics": self.get_statistics(),
        }
