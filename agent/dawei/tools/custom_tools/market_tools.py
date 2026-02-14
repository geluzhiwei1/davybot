# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Market slash command tools.

Provides slash commands for managing skills, agents, and plugins
from the davybot market.
"""

import json

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool

try:
    from dawei.market import (
        CliWrapper,
        InstallResult,
        MarketClient,
        MarketError,
        MarketInstaller,
        ResourceType,
        SearchResult,
    )

    MARKET_AVAILABLE = True
except ImportError:
    MARKET_AVAILABLE = False
    # Create stubs for when market module is not available
    MarketClient = None
    MarketInstaller = None
    CliWrapper = None
    ResourceType = None
    SearchResult = None
    InstallResult = None
    MarketError = Exception


class MarketNotAvailableError(ImportError):
    """Raised when davy-market CLI is not available."""


# ============================================================================
# Skill Commands
# ============================================================================


class SkillSearchInput(BaseModel):
    """Input schema for /skill search command."""

    query: str = Field(..., description="Search query string")
    limit: int = Field(20, description="Maximum number of results")


class SkillSearchTool(CustomBaseTool):
    """Tool for searching skills in the market."""

    name: str = "skill_search"
    description: str = "Search for skills in the davybot market. Use this to discover available skills that can be installed."
    args_schema: type[BaseModel] = SkillSearchInput

    def __init__(self, workspace: str | None = None):
        super().__init__()
        self.workspace = workspace
        self.client = MarketClient()

    @safe_tool_operation(
        "skill_search",
        fallback_value='{"status": "error", "message": "Search failed"}',
    )
    def _run(self, query: str, limit: int = 20) -> str:
        """Search for skills in the market.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            JSON string with search results

        """
        try:
            results = self.client.search_skills(query, limit)

            return json.dumps(
                {
                    "status": "success",
                    "query": query,
                    "total": len(results),
                    "results": [r.to_dict() for r in results],
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"status": "error", "message": f"Search failed: {e}"}, indent=2)


class SkillInstallInput(BaseModel):
    """Input schema for /skill install command."""

    name: str = Field(
        ...,
        description="Skill name or URI (e.g., web-scraper or skill://web-scraper)",
    )
    force: bool = Field(False, description="Force reinstall if already exists")


class SkillInstallTool(CustomBaseTool):
    """Tool for installing skills from the market."""

    name: str = "skill_install"
    description: str = "Install a skill from the davybot market to the workspace. After installation, the skill will be available for use."
    args_schema: type[BaseModel] = SkillInstallInput

    def __init__(self, workspace: str):
        super().__init__()
        if not MARKET_AVAILABLE:
            raise MarketNotAvailableError("davy-market CLI is not available. Install it with: pip install davybot-market-cli")
        self.workspace = workspace
        self.installer = MarketInstaller(workspace)

    @safe_tool_operation(
        "skill_install",
        fallback_value='{"status": "error", "message": "Installation failed"}',
    )
    def _run(self, name: str, force: bool = False) -> str:
        """Install a skill from the market.

        Args:
            name: Skill name or URI
            force: Force reinstall

        Returns:
            JSON string with installation result

        """
        try:
            result = self.installer.install("skill", name, force=force)

            return json.dumps(result.to_dict(), indent=2)

        except Exception as e:
            return json.dumps({"status": "error", "message": f"Installation failed: {e}"}, indent=2)


class SkillListInput(BaseModel):
    """Input schema for /skill list command."""

    # Empty schema - no parameters required


class SkillListTool(CustomBaseTool):
    """Tool for listing installed skills."""

    name: str = "skill_list"
    description: str = "List all skills installed in the workspace"
    args_schema: type[BaseModel] = SkillListInput

    def __init__(self, workspace: str):
        super().__init__()
        if not MARKET_AVAILABLE:
            raise MarketNotAvailableError("davy-market CLI is not available. Install it with: pip install davybot-market-cli")
        self.workspace = workspace
        self.installer = MarketInstaller(workspace)

    @safe_tool_operation(
        "skill_list",
        fallback_value='{"status": "error", "message": "List failed"}',
    )
    def _run(self) -> str:
        """List installed skills.

        Returns:
            JSON string with installed skills

        """
        try:
            installed = self.installer.list_installed("skill")

            return json.dumps(
                {
                    "status": "success",
                    "total": len(installed),
                    "skills": [s.to_dict() for s in installed],
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"status": "error", "message": f"List failed: {e}"}, indent=2)


# ============================================================================
# Agent Commands
# ============================================================================


class AgentSearchInput(BaseModel):
    """Input schema for /agent search command."""

    query: str = Field(..., description="Search query string")
    limit: int = Field(20, description="Maximum number of results")


class AgentSearchTool(CustomBaseTool):
    """Tool for searching agents in the market."""

    name: str = "agent_search"
    description: str = "Search for agents in the davybot market. Use this to discover available agents that can be installed."
    args_schema: type[BaseModel] = AgentSearchInput

    def __init__(self, workspace: str | None = None):
        super().__init__()
        self.workspace = workspace
        self.client = MarketClient()

    @safe_tool_operation(
        "agent_search",
        fallback_value='{"status": "error", "message": "Search failed"}',
    )
    def _run(self, query: str, limit: int = 20) -> str:
        """Search for agents in the market.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            JSON string with search results

        """
        try:
            results = self.client.search_agents(query, limit)

            return json.dumps(
                {
                    "status": "success",
                    "query": query,
                    "total": len(results),
                    "results": [r.to_dict() for r in results],
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"status": "error", "message": f"Search failed: {e}"}, indent=2)


class AgentInstallInput(BaseModel):
    """Input schema for /agent install command."""

    name: str = Field(..., description="Agent name or URI (e.g., coder-v2 or agent://coder-v2)")
    force: bool = Field(False, description="Force reinstall if already exists")


class AgentUninstallInput(BaseModel):
    """Input schema for /agent uninstall command."""

    name: str = Field(..., description="Agent name")


class AgentInstallTool(CustomBaseTool):
    """Tool for installing agents from the market."""

    name: str = "agent_install"
    description: str = "Install an agent from the davybot market to the workspace. After installation, the agent template will be available."
    args_schema: type[BaseModel] = AgentInstallInput

    def __init__(self, workspace: str):
        super().__init__()
        if not MARKET_AVAILABLE:
            raise MarketNotAvailableError("davy-market CLI is not available. Install it with: pip install davybot-market-cli")
        self.workspace = workspace
        self.installer = MarketInstaller(workspace)

    @safe_tool_operation(
        "agent_install",
        fallback_value='{"status": "error", "message": "Installation failed"}',
    )
    def _run(self, name: str, force: bool = False) -> str:
        """Install an agent from the market.

        Args:
            name: Agent name or URI
            force: Force reinstall

        Returns:
            JSON string with installation result

        """
        try:
            result = self.installer.install("agent", name, force=force)

            return json.dumps(result.to_dict(), indent=2)

        except Exception as e:
            return json.dumps({"status": "error", "message": f"Installation failed: {e}"}, indent=2)


class AgentListInput(BaseModel):
    """Input schema for /agent list command."""

    # Empty schema - no parameters required


class AgentListTool(CustomBaseTool):
    """Tool for listing installed agents."""

    name: str = "agent_list"
    description: str = "List all agents installed in the workspace"
    args_schema: type[BaseModel] = AgentListInput

    def __init__(self, workspace: str):
        super().__init__()
        if not MARKET_AVAILABLE:
            raise MarketNotAvailableError("davy-market CLI is not available. Install it with: pip install davybot-market-cli")
        self.workspace = workspace
        self.installer = MarketInstaller(workspace)

    @safe_tool_operation(
        "agent_list",
        fallback_value='{"status": "error", "message": "List failed"}',
    )
    def _run(self) -> str:
        """List installed agents.

        Returns:
            JSON string with installed agents

        """
        try:
            installed = self.installer.list_installed("agent")

            return json.dumps(
                {
                    "status": "success",
                    "total": len(installed),
                    "agents": [a.to_dict() for a in installed],
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"status": "error", "message": f"List failed: {e}"}, indent=2)


class AgentUninstallTool(CustomBaseTool):
    """Tool for uninstalling agents from the workspace."""

    name: str = "agent_uninstall"
    description: str = "Uninstall an agent from the workspace"
    args_schema: type[BaseModel] = AgentUninstallInput

    def __init__(self, workspace: str):
        super().__init__()
        if not MARKET_AVAILABLE:
            raise MarketNotAvailableError("davy-market CLI is not available. Install it with: pip install davybot-market-cli")
        self.workspace = workspace
        self.installer = MarketInstaller(workspace)

    @safe_tool_operation(
        "agent_uninstall",
        fallback_value='{"status": "error", "message": "Uninstall failed"}',
    )
    def _run(self, name: str) -> str:
        """Uninstall an agent.

        Args:
            name: Agent name

        Returns:
            JSON string with uninstall result

        """
        try:
            result = self.installer.uninstall("agent", name)

            return json.dumps(result.to_dict(), indent=2)

        except Exception as e:
            return json.dumps({"status": "error", "message": f"Uninstall failed: {e}"}, indent=2)


# ============================================================================
# Plugin Commands
# ============================================================================


class PluginSearchInput(BaseModel):
    """Input schema for /plugin search command."""

    query: str = Field(..., description="Search query string")
    plugin_type: str | None = Field(
        None,
        description="Filter by plugin type (channel, tool, service, memory)",
    )
    limit: int = Field(20, description="Maximum number of results")


class PluginSearchTool(CustomBaseTool):
    """Tool for searching plugins in the market."""

    name: str = "plugin_search"
    description: str = "Search for plugins in the davybot market. Use this to discover available plugins that can be installed."
    args_schema: type[BaseModel] = PluginSearchInput

    def __init__(self, workspace: str | None = None):
        super().__init__()
        self.workspace = workspace
        self.client = MarketClient()

    @safe_tool_operation(
        "plugin_search",
        fallback_value='{"status": "error", "message": "Search failed"}',
    )
    def _run(self, query: str, plugin_type: str | None = None, limit: int = 20) -> str:
        """Search for plugins in the market.

        Args:
            query: Search query string
            plugin_type: Plugin type filter
            limit: Maximum number of results

        Returns:
            JSON string with search results

        """
        try:
            results = self.client.search_plugins(query, limit)

            # Filter by type if specified
            if plugin_type:
                results = [r for r in results if r.raw_data.get("type") == plugin_type]

            return json.dumps(
                {
                    "status": "success",
                    "query": query,
                    "plugin_type": plugin_type,
                    "total": len(results),
                    "results": [r.to_dict() for r in results],
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"status": "error", "message": f"Search failed: {e}"}, indent=2)


class PluginInstallInput(BaseModel):
    """Input schema for /plugin install command."""

    name: str = Field(
        ...,
        description="Plugin name or URI (e.g., slack-channel or plugin://slack-channel)",
    )
    force: bool = Field(False, description="Force reinstall if already exists")


class PluginInstallTool(CustomBaseTool):
    """Tool for installing plugins from the market."""

    name: str = "plugin_install"
    description: str = "Install a plugin from the davybot market to the workspace. After installation, the plugin will be loaded on next restart."
    args_schema: type[BaseModel] = PluginInstallInput

    def __init__(self, workspace: str):
        super().__init__()
        if not MARKET_AVAILABLE:
            raise MarketNotAvailableError("davy-market CLI is not available. Install it with: pip install davybot-market-cli")
        self.workspace = workspace
        self.installer = MarketInstaller(workspace)

    @safe_tool_operation(
        "plugin_install",
        fallback_value='{"status": "error", "message": "Installation failed"}',
    )
    def _run(self, name: str, force: bool = False) -> str:
        """Install a plugin from the market.

        Args:
            name: Plugin name or URI
            force: Force reinstall

        Returns:
            JSON string with installation result

        """
        try:
            result = self.installer.install("plugin", name, force=force)

            return json.dumps(result.to_dict(), indent=2)

        except Exception as e:
            return json.dumps({"status": "error", "message": f"Installation failed: {e}"}, indent=2)


class PluginListInput(BaseModel):
    """Input schema for /plugin list command."""

    # Empty schema - no parameters required


class PluginListTool(CustomBaseTool):
    """Tool for listing installed plugins."""

    name: str = "plugin_list"
    description: str = "List all plugins installed in the workspace"
    args_schema: type[BaseModel] = PluginListInput

    def __init__(self, workspace: str):
        super().__init__()
        if not MARKET_AVAILABLE:
            raise MarketNotAvailableError("davy-market CLI is not available. Install it with: pip install davybot-market-cli")
        self.workspace = workspace
        self.installer = MarketInstaller(workspace)

    @safe_tool_operation(
        "plugin_list",
        fallback_value='{"status": "error", "message": "List failed"}',
    )
    def _run(self) -> str:
        """List installed plugins.

        Returns:
            JSON string with installed plugins

        """
        try:
            installed = self.installer.list_plugins()

            return json.dumps(
                {"status": "success", "total": len(installed), "plugins": installed},
                indent=2,
            )

        except Exception as e:
            return json.dumps({"status": "error", "message": f"List failed: {e}"}, indent=2)


class PluginUninstallInput(BaseModel):
    """Input schema for /plugin uninstall command."""

    name: str = Field(..., description="Plugin name to uninstall")


class PluginUninstallTool(CustomBaseTool):
    """Tool for uninstalling plugins."""

    name: str = "plugin_uninstall"
    description: str = "Uninstall a plugin from the workspace"
    args_schema: type[BaseModel] = PluginUninstallInput

    def __init__(self, workspace: str):
        super().__init__()
        if not MARKET_AVAILABLE:
            raise MarketNotAvailableError("davy-market CLI is not available. Install it with: pip install davybot-market-cli")
        self.workspace = workspace
        self.installer = MarketInstaller(workspace)

    @safe_tool_operation(
        "plugin_uninstall",
        fallback_value='{"status": "error", "message": "Uninstall failed"}',
    )
    def _run(self, name: str) -> str:
        """Uninstall a plugin.

        Args:
            name: Plugin name

        Returns:
            JSON string with uninstall result

        """
        try:
            result = self.installer.uninstall("plugin", name)

            return json.dumps(result.to_dict(), indent=2)

        except Exception as e:
            return json.dumps({"status": "error", "message": f"Uninstall failed: {e}"}, indent=2)


# ============================================================================
# Combined Market Command Tool
# ============================================================================


class MarketSlashCommandInput(BaseModel):
    """Input schema for market slash commands."""

    command: str = Field(..., description="Full slash command (e.g., '/skill search web')")
    args: str | None = Field(None, description="Optional command arguments")


class MarketSlashCommandsTool(CustomBaseTool):
    """Combined market slash command tool.

    Handles all market-related slash commands:
    - /skill search <query>
    - /skill install <name>
    - /skill list
    - /agent search <query>
    - /agent install <name>
    - /agent list
    - /agent uninstall <name>
    - /plugin search <query>
    - /plugin install <name>
    - /plugin list
    - /plugin uninstall <name>
    """

    name: str = "market_slash_command"
    description: str = "Execute market resource management commands. Supports /skill, /agent, and /plugin commands with search, install, list, and uninstall operations."
    args_schema: type[BaseModel] = MarketSlashCommandInput

    def __init__(self, workspace: str):
        super().__init__()
        if not MARKET_AVAILABLE:
            raise MarketNotAvailableError("davy-market CLI is not available. Install it with: pip install davybot-market-cli")
        self.workspace = workspace

        # Initialize sub-tools
        self.skill_search = SkillSearchTool(workspace)
        self.skill_install = SkillInstallTool(workspace)
        self.skill_list = SkillListTool(workspace)

        self.agent_search = AgentSearchTool(workspace)
        self.agent_install = AgentInstallTool(workspace)
        self.agent_list = AgentListTool(workspace)
        self.agent_uninstall = AgentUninstallTool(workspace)

        self.plugin_search = PluginSearchTool(workspace)
        self.plugin_install = PluginInstallTool(workspace)
        self.plugin_list = PluginListTool(workspace)
        self.plugin_uninstall = PluginUninstallTool(workspace)

    def _parse_command(self, command: str) -> tuple:
        """Parse slash command into components.

        Args:
            command: Command string (e.g., '/skill search web')

        Returns:
            Tuple of (resource_type, action, args)

        """
        # Remove leading slash and split
        parts = command.strip().lstrip("/").split()

        if len(parts) < 2:
            raise ValueError(f"Invalid command format: {command}")

        resource_type = parts[0].lower()  # skill, agent, plugin
        action = parts[1].lower()  # search, install, list, uninstall
        args = " ".join(parts[2:]) if len(parts) > 2 else ""

        return resource_type, action, args

    @safe_tool_operation(
        "market_slash_command",
        fallback_value='{"status": "error", "message": "Command execution failed"}',
    )
    def _run(self, command: str, args: str | None = None) -> str:
        """Execute a market slash command.

        Args:
            command: Full slash command
            args: Optional additional arguments

        Returns:
            JSON string with execution result

        """
        try:
            resource_type, action, cmd_args = self._parse_command(command)

            # Append additional args if provided
            if args:
                cmd_args = f"{cmd_args} {args}".strip()

            # Route to appropriate handler
            if resource_type == "skill":
                return self._handle_skill(action, cmd_args)
            if resource_type == "agent":
                return self._handle_agent(action, cmd_args)
            if resource_type == "plugin":
                return self._handle_plugin(action, cmd_args)
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Unknown resource type: {resource_type}. Use skill, agent, or plugin.",
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps(
                {"status": "error", "message": f"Command execution failed: {e}"},
                indent=2,
            )

    def _handle_skill(self, action: str, args: str) -> str:
        """Handle skill commands."""
        if action == "search":
            return self.skill_search._run(query=args)
        if action == "install":
            # Parse: install <name> [--force]
            parts = args.split()
            name = parts[0] if parts else ""
            force = "--force" in parts or "-f" in parts
            return self.skill_install._run(name=name, force=force)
        if action == "list":
            return self.skill_list._run()
        return json.dumps(
            {
                "status": "error",
                "message": f"Unknown skill action: {action}. Use search, install, or list.",
            },
            indent=2,
        )

    def _handle_agent(self, action: str, args: str) -> str:
        """Handle agent commands."""
        if action == "search":
            return self.agent_search._run(query=args)
        if action == "install":
            parts = args.split()
            name = parts[0] if parts else ""
            force = "--force" in parts or "-f" in parts
            return self.agent_install._run(name=name, force=force)
        if action == "list":
            return self.agent_list._run()
        if action == "uninstall":
            return self.agent_uninstall._run(name=args)
        return json.dumps(
            {
                "status": "error",
                "message": f"Unknown agent action: {action}. Use search, install, list, or uninstall.",
            },
            indent=2,
        )

    def _handle_plugin(self, action: str, args: str) -> str:
        """Handle plugin commands."""
        if action == "search":
            # Parse: search <query> [--type <type>]
            parts = args.split()
            query = parts[0] if parts else ""
            plugin_type = None
            if "--type" in parts or "-t" in parts:
                try:
                    type_idx = parts.index("--type") if "--type" in parts else parts.index("-t")
                    plugin_type = parts[type_idx + 1] if type_idx + 1 < len(parts) else None
                except ValueError:
                    pass
            return self.plugin_search._run(query=query, plugin_type=plugin_type)
        if action == "install":
            parts = args.split()
            name = parts[0] if parts else ""
            force = "--force" in parts or "-f" in parts
            return self.plugin_install._run(name=name, force=force)
        if action == "list":
            return self.plugin_list._run()
        if action == "uninstall":
            return self.plugin_uninstall._run(name=args)
        return json.dumps(
            {
                "status": "error",
                "message": f"Unknown plugin action: {action}. Use search, install, list, or uninstall.",
            },
            indent=2,
        )
