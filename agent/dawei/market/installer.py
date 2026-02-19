# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Market resource installer.

Handles installation of skills, agents, and plugins from the market
to the workspace, including file management and configuration updates.
"""

import json
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Any, ClassVar

from .cli_wrapper import CliWrapper, CliExecutionError
from .models import (
    InstallationError,
    InstalledResource,
    InstallResult,
    MarketSettings,
    ResourceType,
)

logger = logging.getLogger(__name__)


class MarketInstaller:
    """Installer for market resources.

    Manages installation of skills, agents, and plugins from the market
    to the workspace directory structure.
    """

    # Resource type to directory mapping
    RESOURCE_DIRS = {
        ResourceType.SKILL: "skills",
        ResourceType.AGENT: "agents",
        ResourceType.PLUGIN: "plugins",
        ResourceType.MCP: "mcp_servers",
        ResourceType.KNOWLEDGE: "knowledge",
    }

    def __init__(self, workspace: str, cli_wrapper: CliWrapper | None = None):
        """Initialize installer.

        Args:
            workspace: Workspace directory path
            cli_wrapper: Optional CLI wrapper instance

        """
        self.workspace = Path(workspace).resolve()
        self.cli = cli_wrapper or CliWrapper()

        # Create market directory structure
        self.market_dir = self.workspace / ".dawei"
        self.market_dir.mkdir(parents=True, exist_ok=True)

        # Load market settings
        self.settings = self._load_settings()

    def _load_settings(self) -> MarketSettings:
        """Load market settings from workspace."""
        settings_file = self.market_dir / "market_settings.json"
        if settings_file.exists():
            try:
                with Path(settings_file).open(encoding="utf-8") as f:
                    data = json.load(f)
                    return MarketSettings.from_dict(data)
            except Exception as e:
                logger.warning(f"Failed to load market settings: {e}")
        return MarketSettings()

    def _save_settings(self) -> None:
        """Save market settings to workspace."""
        settings_file = self.market_dir / "market_settings.json"
        try:
            with settings_file.open("w", encoding="utf-8") as f:
                json.dump(self.settings.to_dict(), f, indent=2)
            logger.debug(f"Saved market settings to {settings_file}")
        except Exception:
            logger.exception("Failed to save market settings: ")

    def _resolve_resource_id(self, resource_type: ResourceType, resource_name: str) -> str:
        """Resolve resource name/ID for installation.

        Args:
            resource_type: Resource type (SKILL or AGENT)
            resource_name: Resource name or full ID

        Returns:
            Resource URI in format "type://id" suitable for CLI (e.g., "skill://github.com/anthropics/skills/skills/xlsx")
        """
        # If already a full ID (contains '/'), wrap with type:// prefix for CLI
        if "/" in resource_name:
            # Full ID like "github.com/anthropics/skills/skills/xlsx"
            # CLI needs format: "skill://github.com/anthropics/skills/skills/xlsx"
            return f"{resource_type.value}://{resource_name}"

        # For short names without "/", try to resolve via search
        logger.info(f"Resolving {resource_type.value} name '{resource_name}' to full ID...")

        try:
            # Search for the resource using CLI
            if resource_type == ResourceType.SKILL:
                search_result = self.cli.search_skills(resource_name, limit=5)
            elif resource_type == ResourceType.AGENT:
                search_result = self.cli.search_agents(resource_name, limit=5)
            else:
                return f"{resource_type.value}://{resource_name}"  # Return with prefix

            # CLI returns dict with 'results' key
            search_results = search_result.get("results", [])

            if not search_results:
                raise InstallationError(
                    f"Search returned no results for '{resource_name}'. "
                    f"Please check the resource name and try again."
                )

            # Find exact match by name or id
            for result in search_results:
                result_name = result.get("name", "")
                result_id = result.get("id", "")
                if result_name == resource_name or result_id.endswith(f"/{resource_name}"):
                    logger.info(f"Resolved '{resource_name}' to '{result_id}'")
                    return f"{resource_type.value}://{result_id}"

            # Use first result if no exact match
            if search_results:
                first_result = search_results[0]
                first_id = first_result.get("id", "")
                logger.info(f"Using '{first_id}' for '{resource_name}' (best match)")
                return f"{resource_type.value}://{first_id}"

        except CliExecutionError as e:
            raise InstallationError(
                f"Failed to search for '{resource_name}': {e.message}"
            ) from e
        except Exception as e:
            raise InstallationError(
                f"Failed to search for '{resource_name}': {e}"
            ) from e

    def _get_resource_dir(self, resource_type: ResourceType) -> Path:
        """Get installation directory for resource type."""
        dir_name = self.RESOURCE_DIRS.get(resource_type, resource_type.value)
        resource_dir = self.market_dir / dir_name
        resource_dir.mkdir(parents=True, exist_ok=True)
        return resource_dir

    def _extract_archive(self, archive_path: Path, dest_dir: Path) -> list[str]:
        """Extract archive file to destination directory.

        Args:
            archive_path: Path to archive file
            dest_dir: Destination directory

        Returns:
            List of extracted file paths

        """
        extracted_files = []

        if archive_path.suffix == ".zip":
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(dest_dir)
                extracted_files = zip_ref.namelist()
        elif archive_path.suffix in (".tar.gz", ".tgz"):
            import tarfile

            with tarfile.open(archive_path, "r:gz") as tar_ref:
                tar_ref.extractall(dest_dir)
                extracted_files = tar_ref.getnames()
        else:
            raise InstallationError(
                "archive",
                str(archive_path),
                f"Unsupported archive format: {archive_path.suffix}",
            )

        return extracted_files

    # ========================================================================
    # Installation Methods
    # ========================================================================

    def install(
        self,
        resource_type: str,
        resource_name: str,
        _version: ClassVar[str | None] = None,
        force: ClassVar[bool] = False,
    ) -> InstallResult:
        """Install a resource from the market.

        Args:
            resource_type: Resource type (skill, agent, plugin)
            resource_name: Resource name or URI
            version: Optional version to install
            force: Force reinstall if already exists

        Returns:
            InstallResult with installation status

        """
        try:
            # Parse resource type
            try:
                rtype = ResourceType(resource_type)
            except ValueError:
                return InstallResult(
                    success=False,
                    resource_type=ResourceType.SKILL,  # fallback
                    resource_name=resource_name,
                    error=f"Invalid resource type: {resource_type}",
                )

            # Check if already installed - verify both settings AND actual files
            if not force and self.settings.is_installed(resource_type, resource_name):
                # Verify installation directory actually exists
                install_dir = self._get_resource_dir(rtype)

                # For skills, extract skill name from resource ID
                # e.g., "github.com/anthropics/skills/skills/xlsx" -> "xlsx"
                if rtype == ResourceType.SKILL:
                    skill_name = resource_name.split("/")[-1] if "/" in resource_name else resource_name
                    skill_dir = install_dir / skill_name

                    if skill_dir.exists() and (skill_dir / "SKILL.md").exists():
                        logger.info(f"{resource_type} '{resource_name}' already installed")
                        return InstallResult(
                            success=True,
                            resource_type=rtype,
                            resource_name=resource_name,
                            message=f"{resource_type.capitalize()} '{resource_name}' is already installed",
                            requires_restart=False,
                        )
                    else:
                        # Settings say installed, but files don't exist - need to reinstall
                        logger.warning(
                            f"{resource_type} '{resource_name}' marked as installed but files missing. "
                            f"Reinstalling..."
                        )
                        # Remove from settings to allow reinstallation
                        self.settings.remove_installed(resource_type, resource_name)
                        self._save_settings()

                # For agents, also check if files exist
                elif rtype == ResourceType.AGENT:
                    agent_name = resource_name.split("/")[-1] if "/" in resource_name else resource_name
                    agent_dir = install_dir / agent_name

                    if agent_dir.exists() and any((agent_dir / f).exists() for f in ["custom.md", "rules.md", "agent.md"]):
                        logger.info(f"{resource_type} '{resource_name}' already installed")
                        return InstallResult(
                            success=True,
                            resource_type=rtype,
                            resource_name=resource_name,
                            message=f"{resource_type.capitalize()} '{resource_name}' is already installed. Use force=True to update.",
                            requires_restart=False,
                        )
                    else:
                        # Settings say installed, but files don't exist - need to reinstall
                        logger.warning(
                            f"{resource_type} '{resource_name}' marked as installed but files missing. "
                            f"Reinstalling..."
                        )
                        # Remove from settings to allow reinstallation
                        self.settings.remove_installed(resource_type, resource_name)
                        self._save_settings()

            # Get installation directory
            install_dir = self._get_resource_dir(rtype)

            # For skills/agents, resolve short name to full ID via search
            if rtype in (ResourceType.SKILL, ResourceType.AGENT):
                resource_uri = self._resolve_resource_id(rtype, resource_name)
            else:
                # Build resource URI for plugins
                resource_uri = f"{resource_type}://{resource_name}" if not resource_name.startswith(f"{resource_type}://") else resource_name

            # For plugins, use the dedicated plugin install command
            if rtype == ResourceType.PLUGIN:
                return self._install_plugin(resource_name, force)
            return self._install_resource(rtype, resource_uri, install_dir, force)

        except Exception as e:
            logger.exception(f"Installation failed for {resource_type}/{resource_name}")
            return InstallResult(
                success=False,
                resource_type=(ResourceType(resource_type) if resource_type in ResourceType.__members__ else ResourceType.SKILL),
                resource_name=resource_name,
                error=str(e),
            )

    def _install_resource(
        self,
        resource_type: ResourceType,
        resource_uri: str,
        install_dir: Path,
        _force: bool,
    ) -> InstallResult:
        """Install a non-plugin resource using CLI.

        Args:
            resource_type: Resource type enum
            resource_uri: Resource URI
            install_dir: Installation directory
            force: Force reinstall

        Returns:
            InstallResult

        """
        # Download using CLI
        logger.info(f"Installing {resource_uri} to {install_dir}")

        cli_result = self.cli.install(
            resource_uri=resource_uri,
            output_dir=str(install_dir),
            format="zip",
        )

        if not cli_result.get("success"):
            return InstallResult(
                success=False,
                resource_type=resource_type,
                resource_name=resource_uri,
                error=cli_result.get("stderr", "Installation failed"),
            )

        # Extract if downloaded as zip
        extracted_files = []
        zip_files = list(install_dir.glob("*.zip"))
        if zip_files:
            for zip_file in zip_files:
                extracted = self._extract_archive(zip_file, install_dir)
                extracted_files.extend(extracted)
                # Remove zip file after extraction
                zip_file.unlink()

        # Update settings
        self.settings.add_installed(resource_type.value, resource_uri.rsplit("://", maxsplit=1)[-1])
        self._save_settings()

        return InstallResult(
            success=True,
            resource_type=resource_type,
            resource_name=resource_uri.rsplit("://", maxsplit=1)[-1],
            install_path=str(install_dir),
            message=f"Successfully installed {resource_uri}",
            installed_files=extracted_files,
            requires_restart=resource_type in (ResourceType.PLUGIN, ResourceType.AGENT),
        )

    def _install_plugin(self, plugin_name: str, force: bool) -> InstallResult:
        """Install a plugin using direct HTTP download or CLI.

        Args:
            plugin_name: Plugin name
            force: Force reinstall

        Returns:
            InstallResult

        """
        logger.info(f"Installing plugin '{plugin_name}' to workspace {self.workspace}")

        try:
            # Try to use CLI if available
            cli_result = self.cli.plugin_install(
                plugin_uri=plugin_name,
                workspace=str(self.workspace),
                enable=True,
                force=force,
            )

            if cli_result.get("success"):
                # Update settings
                self.settings.add_installed("plugin", plugin_name)
                self._save_settings()

                install_dir = self.market_dir / "plugins" / plugin_name

                return InstallResult(
                    success=True,
                    resource_type=ResourceType.PLUGIN,
                    resource_name=plugin_name,
                    install_path=str(install_dir),
                    message=f"Successfully installed plugin '{plugin_name}'",
                    requires_restart=True,
                )
            # CLI failed, return error
            error_msg = cli_result.get("stderr", cli_result.get("error", "Plugin installation failed"))
            logger.error(f"CLI plugin install failed: {error_msg}")
            return InstallResult(
                success=False,
                resource_type=ResourceType.PLUGIN,
                resource_name=plugin_name,
                error=error_msg,
            )

        except AttributeError as e:
            # CLI doesn't have plugin_install method
            error_msg = f"CLI plugin_install method not available: {e}. Please install davybot-market-cli or implement direct HTTP download."
            logger.exception(error_msg)
            return InstallResult(
                success=False,
                resource_type=ResourceType.PLUGIN,
                resource_name=plugin_name,
                error=error_msg,
            )
        except Exception as e:
            logger.exception("Plugin installation failed: ")
            return InstallResult(
                success=False,
                resource_type=ResourceType.PLUGIN,
                resource_name=plugin_name,
                error=str(e),
            )

    # ========================================================================
    # Uninstallation Methods
    # ========================================================================

    def uninstall(self, resource_type: str, resource_name: str) -> InstallResult:
        """Uninstall a resource from the workspace.

        Args:
            resource_type: Resource type (skill, agent, plugin)
            resource_name: Resource name

        Returns:
            InstallResult with uninstall status

        """
        try:
            rtype = ResourceType(resource_type)
        except ValueError:
            return InstallResult(
                success=False,
                resource_type=ResourceType.SKILL,
                resource_name=resource_name,
                error=f"Invalid resource type: {resource_type}",
            )

        # For plugins, use CLI uninstall command
        if rtype == ResourceType.PLUGIN:
            return self._uninstall_plugin(resource_name)
        return self._uninstall_resource(rtype, resource_name)

    def _uninstall_plugin(self, plugin_name: str) -> InstallResult:
        """Uninstall a plugin."""
        logger.info(f"Uninstalling plugin '{plugin_name}'")

        # Direct file-based uninstall (no external CLI dependency)
        # This matches how other resources are uninstalled in _uninstall_resource
        try:
            # Use internal plugin directory
            plugins_dir = self._get_resource_dir(ResourceType.PLUGIN)
            plugin_path = plugins_dir / plugin_name

            if not plugin_path.exists():
                # Try market-specific directory structure
                alt_plugin_path = self.market_dir / "plugins" / plugin_name
                if alt_plugin_path.exists():
                    plugin_path = alt_plugin_path
                else:
                    return InstallResult(
                        success=False,
                        resource_type=ResourceType.PLUGIN,
                        resource_name=plugin_name,
                        error=f"Plugin '{plugin_name}' is not installed",
                    )

            # Remove plugin directory
            shutil.rmtree(plugin_path)
            logger.info(f"Removed plugin directory: {plugin_path}")

            # Update market settings
            self.settings.remove_installed("plugin", plugin_name)
            self._save_settings()

            return InstallResult(
                success=True,
                resource_type=ResourceType.PLUGIN,
                resource_name=plugin_name,
                message=f"Successfully uninstalled plugin '{plugin_name}'",
                requires_restart=True,
            )

        except Exception as e:
            logger.exception("Plugin uninstall failed: ")
            return InstallResult(
                success=False,
                resource_type=ResourceType.PLUGIN,
                resource_name=plugin_name,
                error=f"Failed to uninstall: {e}",
            )

    def _uninstall_resource(self, resource_type: ResourceType, resource_name: str) -> InstallResult:
        """Uninstall a non-plugin resource."""
        resource_dir = self._get_resource_dir(resource_type)
        install_path = resource_dir / resource_name

        if not install_path.exists():
            return InstallResult(
                success=False,
                resource_type=resource_type,
                resource_name=resource_name,
                error=f"{resource_type.capitalize()} '{resource_name}' is not installed",
            )

        try:
            # Remove directory
            shutil.rmtree(install_path)

            # Update settings
            self.settings.remove_installed(resource_type.value, resource_name)
            self._save_settings()

            return InstallResult(
                success=True,
                resource_type=resource_type,
                resource_name=resource_name,
                message=f"Successfully uninstalled {resource_type} '{resource_name}'",
            )

        except Exception as e:
            return InstallResult(
                success=False,
                resource_type=resource_type,
                resource_name=resource_name,
                error=f"Failed to uninstall: {e}",
            )

    # ========================================================================
    # List Methods
    # ========================================================================

    def list_installed(self, resource_type: str | None = None) -> list[InstalledResource]:
        """List installed resources in the workspace.

        Args:
            resource_type: Optional resource type filter

        Returns:
            List of InstalledResource objects

        """
        installed = []

        for rtype in ResourceType:
            if resource_type and rtype.value != resource_type:
                continue

            resource_dir = self._get_resource_dir(rtype)
            if not resource_dir.exists():
                continue

            for item in resource_dir.iterdir():
                if item.is_dir():
                    # Try to load metadata
                    metadata_file = item / "metadata.json"
                    metadata = {}
                    version = None

                    if metadata_file.exists():
                        try:
                            with Path(metadata_file).open() as f:
                                metadata = json.load(f)
                                version = metadata.get("version")
                        except Exception:
                            pass

                    installed.append(
                        InstalledResource(
                            name=item.name,
                            type=rtype,
                            version=version,
                            install_path=str(item),
                            enabled=True,
                            metadata=metadata,
                            scope="project",  # Installed via market, always workspace-level
                        ),
                    )

        return installed

    def list_plugins(self) -> list[dict[str, Any]]:
        """List installed plugins from local settings.

        Returns:
            List of plugin dictionaries

        """
        # Read from local market settings
        installed_plugins = self.settings.installed.get("plugins", [])

        # Convert to plugin dictionaries
        plugins = []
        for plugin_name in installed_plugins:
            plugins.append({
                "name": plugin_name,
                "type": "plugin",
                "install_path": f"{self.workspace}/.dawei/plugins/{plugin_name}",
                "scope": "workspace"
            })

        return plugins

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def is_installed(self, resource_type: str, resource_name: str) -> bool:
        """Check if a resource is installed."""
        return self.settings.is_installed(resource_type, resource_name)

    def get_install_path(self, resource_type: str, resource_name: str) -> str | None:
        """Get installation path for a resource."""
        try:
            rtype = ResourceType(resource_type)
            resource_dir = self._get_resource_dir(rtype)
            install_path = resource_dir / resource_name
            return str(install_path) if install_path.exists() else None
        except ValueError:
            return None
