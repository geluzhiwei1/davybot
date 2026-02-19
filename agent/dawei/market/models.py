# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Data models for Market integration module.

Defines resource types, search results, and installation results.
"""

import contextlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ResourceType(StrEnum):
    """Resource types available in the market."""

    SKILL = "skill"
    AGENT = "agent"
    PLUGIN = "plugin"
    MCP = "mcp"
    KNOWLEDGE = "knowledge"


class MarketError(Exception):
    """Base exception for market operations."""

    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code or "market_error",
            "message": str(self),
            "details": self.details,
        }


class ResourceNotFoundError(MarketError):
    """Raised when a resource is not found."""

    def __init__(self, resource_type: str, identifier: str):
        super().__init__(
            f"{resource_type.capitalize()} '{identifier}' not found",
            code="resource_not_found",
            details={"type": resource_type, "identifier": identifier},
        )


class InstallationError(MarketError):
    """Raised when resource installation fails."""

    def __init__(self, resource_type: str, identifier: str, reason: str):
        super().__init__(
            f"Failed to install {resource_type} '{identifier}': {reason}",
            code="installation_failed",
            details={"type": resource_type, "identifier": identifier, "reason": reason},
        )


class CliExecutionError(MarketError):
    """Raised when CLI command execution fails."""

    def __init__(self, command: str, exit_code: int, stderr: str | None = None):
        super().__init__(
            f"CLI command failed: {command}",
            code="cli_execution_failed",
            details={"command": command, "exit_code": exit_code, "stderr": stderr},
        )


class NetworkError(MarketError):
    """Raised when network operations fail."""

    def __init__(self, message: str):
        super().__init__(message, code="network_error")


@dataclass
class SearchResult:
    """Represents a search result from the market."""

    id: str
    name: str
    type: ResourceType
    description: str
    author: str | None = None
    version: str | None = None
    tags: list[str] = field(default_factory=list)
    downloads: int = 0
    rating: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchResult":
        """Create SearchResult from API response dictionary."""
        # Parse dates
        created_at = None
        updated_at = None
        if data.get("created_at"):
            with contextlib.suppress(ValueError, AttributeError):
                created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        if data.get("updated_at"):
            with contextlib.suppress(ValueError, AttributeError):
                updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            type=ResourceType(data.get("type", "skill")),
            description=data.get("description", ""),
            author=data.get("author"),
            version=data.get("version"),
            tags=data.get("tags", []),
            downloads=data.get("downloads", 0),
            rating=data.get("rating"),
            created_at=created_at,
            updated_at=updated_at,
            raw_data=data,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "tags": self.tags,
            "downloads": self.downloads,
            "rating": self.rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class ResourceInfo:
    """Detailed information about a specific resource."""

    result: SearchResult
    readme: str | None = None
    license: str | None = None
    python_version: str | None = None
    dependencies: list[str] = field(default_factory=list)
    install_path: str | None = None
    similar_resources: list[SearchResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            **self.result.to_dict(),
            "readme": self.readme,
            "license": self.license,
            "python_version": self.python_version,
            "dependencies": self.dependencies,
            "install_path": self.install_path,
            "similar_resources": [r.to_dict() for r in self.similar_resources],
        }


@dataclass
class InstallResult:
    """Result of a resource installation operation."""

    success: bool
    resource_type: ResourceType
    resource_name: str
    install_path: str | None = None
    version: str | None = None
    message: str = ""
    error: str | None = None
    installed_files: list[str] = field(default_factory=list)
    requires_restart: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {
            "success": self.success,
            "resource_type": self.resource_type.value,
            "resource_name": self.resource_name,
            "message": self.message,
            "error": self.error,
            "installed_files": self.installed_files,
            "requires_restart": self.requires_restart,
        }
        if self.install_path:
            result["install_path"] = self.install_path
        if self.version:
            result["version"] = self.version
        return result


@dataclass
class InstalledResource:
    """Represents an installed resource in the workspace."""

    name: str
    type: ResourceType
    version: str | None = None
    install_path: str = ""
    installed_at: datetime | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    scope: str = "project"  # "project" for workspace-level, "global" for user-level

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InstalledResource":
        """Create InstalledResource from dictionary."""
        installed_at = None
        if data.get("installed_at"):
            with contextlib.suppress(ValueError, AttributeError):
                installed_at = datetime.fromisoformat(data["installed_at"])

        return cls(
            name=data.get("name", ""),
            type=ResourceType(data.get("type", "skill")),
            version=data.get("version"),
            install_path=data.get("install_path", ""),
            installed_at=installed_at,
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
            scope=data.get("scope", "project"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.type.value,
            "version": self.version,
            "install_path": self.install_path,
            "installed_at": self.installed_at.isoformat() if self.installed_at else None,
            "enabled": self.enabled,
            "metadata": self.metadata,
            "scope": self.scope,
        }


@dataclass
class MarketSettings:
    """Market configuration for a workspace."""

    installed: dict[str, list[str]] = field(default_factory=dict)
    registry: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize default values."""
        if "skills" not in self.installed:
            self.installed["skills"] = []
        if "agents" not in self.installed:
            self.installed["agents"] = []
        if "plugins" not in self.installed:
            self.installed["plugins"] = []

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MarketSettings":
        """Create MarketSettings from dictionary."""
        installed = data.get("installed", {})
        registry = data.get("registry", {})
        return cls(installed=installed, registry=registry)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {"installed": self.installed, "registry": self.registry}

    def add_installed(self, resource_type: str, name: str) -> None:
        """Add installed resource to settings."""
        type_key = f"{resource_type}s"
        if type_key not in self.installed:
            self.installed[type_key] = []
        if name not in self.installed[type_key]:
            self.installed[type_key].append(name)

    def remove_installed(self, resource_type: str, name: str) -> None:
        """Remove installed resource from settings."""
        type_key = f"{resource_type}s"
        if type_key in self.installed and name in self.installed[type_key]:
            self.installed[type_key].remove(name)

    def is_installed(self, resource_type: str, name: str) -> bool:
        """Check if resource is installed."""
        type_key = f"{resource_type}s"
        return type_key in self.installed and name in self.installed[type_key]
