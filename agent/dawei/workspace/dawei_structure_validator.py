# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

""".dawei Directory Structure Validator

Validates the directory structure and file format legality of .dawei workspace directories.
Follows Fast Fail principle - raises exceptions immediately on validation failure.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from dawei.config import get_dawei_home


class DaweiStructureValidationError(Exception):
    """Base exception for .dawei structure validation errors."""

    def __init__(self, message: str, path: Path | None = None):
        self.path = path
        if path:
            message = f"{path}: {message}"
        super().__init__(message)


class WorkspaceJsonError(DaweiStructureValidationError):
    """workspace.json format or content error."""


class DirectoryStructureError(DaweiStructureValidationError):
    """Directory structure error."""


class DaweiStructureValidator:
    """Validator for .dawei directory structure and file formats."""

    # Required subdirectories in .dawei/
    # 注意：checkpoints 和 sessions 已移到全局 DAWEI_HOME 级别
    REQUIRED_DIRECTORIES = [
        "scheduled_tasks",
        "task_graphs",
        "task_nodes",
    ]

    # Required fields in workspace.json
    REQUIRED_WORKSPACE_FIELDS = [
        "id",
        "name",
        "display_name",
        "created_at",
        "is_active",
    ]

    # Optional but validated fields in workspace.json
    OPTIONAL_WORKSPACE_FIELDS = [
        "description",
        "files_list",
        "system_environments",
        "user_ui_environments",
        "user_ui_context",
    ]

    @staticmethod
    def validate_workspace_json(workspace_json_path: Path) -> dict:
        """Validate workspace.json file format and content.

        Args:
            workspace_json_path: Path to workspace.json file

        Returns:
            dict: Parsed workspace.json content

        Raises:
            WorkspaceJsonError: If file format or content is invalid
        """
        # Check file exists
        if not workspace_json_path.exists():
            raise WorkspaceJsonError(
                "workspace.json not found",
                path=workspace_json_path.parent,
            )

        # Check file is readable
        if not workspace_json_path.is_file():
            raise WorkspaceJsonError(
                "workspace.json is not a file",
                path=workspace_json_path,
            )

        # Try to read and parse JSON
        try:
            with workspace_json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise WorkspaceJsonError(
                f"Invalid JSON format: {e}",
                path=workspace_json_path,
            )
        except Exception as e:
            raise WorkspaceJsonError(
                f"Failed to read file: {e}",
                path=workspace_json_path,
            )

        # Validate required fields
        missing_fields = [field for field in DaweiStructureValidator.REQUIRED_WORKSPACE_FIELDS if field not in data]
        if missing_fields:
            raise WorkspaceJsonError(
                f"Missing required fields: {', '.join(missing_fields)}",
                path=workspace_json_path,
            )

        # Validate field types
        try:
            # id must be a valid UUID
            uuid.UUID(data["id"])

            # name and display_name must be non-empty strings
            if not isinstance(data["name"], str) or not data["name"].strip():
                raise WorkspaceJsonError(
                    "'name' must be a non-empty string",
                    path=workspace_json_path,
                )

            if not isinstance(data["display_name"], str) or not data["display_name"].strip():
                raise WorkspaceJsonError(
                    "'display_name' must be a non-empty string",
                    path=workspace_json_path,
                )

            # created_at must be a valid ISO 8601 datetime string
            datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))

            # is_active must be a boolean
            if not isinstance(data["is_active"], bool):
                raise WorkspaceJsonError(
                    "'is_active' must be a boolean",
                    path=workspace_json_path,
                )

        except (ValueError, AttributeError) as e:
            raise WorkspaceJsonError(
                f"Field validation error: {e}",
                path=workspace_json_path,
            )

        return data

    @staticmethod
    def validate_directory_structure(dawei_path: Path) -> None:
        """Validate .dawei directory structure.

        Args:
            dawei_path: Path to .dawei directory

        Raises:
            DirectoryStructureError: If directory structure is invalid
        """
        # Check .dawei directory exists
        if not dawei_path.exists():
            raise DirectoryStructureError(
                ".dawei directory does not exist",
                path=dawei_path,
            )

        if not dawei_path.is_dir():
            raise DirectoryStructureError(
                ".dawei is not a directory",
                path=dawei_path,
            )

        # Check workspace.json exists
        workspace_json = dawei_path / "workspace.json"
        if not workspace_json.exists():
            raise DirectoryStructureError(
                "workspace.json not found",
                path=dawei_path,
            )

        # Check required subdirectories exist
        missing_dirs = []
        for dir_name in DaweiStructureValidator.REQUIRED_DIRECTORIES:
            dir_path = dawei_path / dir_name
            if not dir_path.exists():
                missing_dirs.append(dir_name)
            elif not dir_path.is_dir():
                raise DirectoryStructureError(
                    f"'{dir_name}' exists but is not a directory",
                    path=dir_path,
                )

        if missing_dirs:
            raise DirectoryStructureError(
                f"Missing required directories: {', '.join(missing_dirs)}",
                path=dawei_path,
            )

        # Check snapshots subdirectories
        snapshots_dir = dawei_path / "snapshots"
        snapshots_subdirs = ["files", "index", "locks"]
        for subdir in snapshots_subdirs:
            subdir_path = snapshots_dir / subdir
            if not subdir_path.exists():
                missing_dirs.append(f"snapshots/{subdir}")
            elif not subdir_path.is_dir():
                raise DirectoryStructureError(
                    f"snapshots/{subdir} exists but is not a directory",
                    path=subdir_path,
                )

    @staticmethod
    def validate_jsonl_files(dawei_path: Path) -> list[str]:
        """Validate JSONL files in persistence_failures directory.

        Args:
            dawei_path: Path to .dawei directory

        Returns:
            list[str]: List of validation warnings (non-critical issues)

        Raises:
            WorkspaceJsonError: If JSONL file format is invalid
        """
        warnings = []
        persistence_dir = dawei_path / "persistence_failures"

        if not persistence_dir.exists():
            return warnings

        # Find all .jsonl files
        jsonl_files = list(persistence_dir.glob("*.jsonl"))

        for jsonl_file in jsonl_files:
            try:
                line_number = 0
                with jsonl_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        line_number += 1
                        line = line.strip()
                        if not line:
                            continue  # Skip empty lines

                        try:
                            json.loads(line)
                        except json.JSONDecodeError as e:
                            raise WorkspaceJsonError(
                                f"Invalid JSONL at line {line_number}: {e}",
                                path=jsonl_file,
                            )

            except WorkspaceJsonError:
                raise  # Re-raise validation errors
            except Exception as e:
                warnings.append(f"Warning: Could not validate {jsonl_file.name}: {e}")

        return warnings

    @classmethod
    def validate_dawei_structure(cls, dawei_path: Path) -> dict:
        """Validate complete .dawei directory structure and file formats.

        Args:
            dawei_path: Path to .dawei directory

        Returns:
            dict: Validation result with keys:
                - valid (bool): True if validation passed
                - workspace_data (dict): Parsed workspace.json content
                - warnings (list[str]): List of non-critical warnings

        Raises:
            DaweiStructureValidationError: If validation fails (Fast Fail)
        """
        # Fast Fail: Validate directory structure first
        cls.validate_directory_structure(dawei_path)

        # Fast Fail: Validate workspace.json format and content
        workspace_json = dawei_path / "workspace.json"
        workspace_data = cls.validate_workspace_json(workspace_json)

        # Check JSONL files (non-critical, collect warnings)
        warnings = cls.validate_jsonl_files(dawei_path)

        return {
            "valid": True,
            "workspace_data": workspace_data,
            "warnings": warnings,
        }

    @classmethod
    def validate_all_workspaces(cls, workspaces_root: Path) -> dict:
        """Validate all workspace .dawei directories.

        Args:
            workspaces_root: Path to workspaces root directory

        Returns:
            dict: Validation result with keys:
                - total (int): Total number of workspaces
                - valid (int): Number of valid workspaces
                - invalid (int): Number of invalid workspaces
                - errors (list[dict]): List of validation errors
                - workspace_details (list[dict]): Details for each workspace
        """
        if not workspaces_root.exists():
            raise DirectoryStructureError(
                f"Workspaces root directory does not exist: {workspaces_root}",
                path=workspaces_root,
            )

        result = {
            "total": 0,
            "valid": 0,
            "invalid": 0,
            "errors": [],
            "workspace_details": [],
        }

        # Iterate through all workspace directories
        for workspace_dir in workspaces_root.iterdir():
            if not workspace_dir.is_dir():
                continue

            result["total"] += 1
            dawei_path = workspace_dir / ".dawei"

            workspace_detail = {
                "workspace_name": workspace_dir.name,
                "path": str(dawei_path),
                "valid": False,
                "error": None,
                "warnings": [],
            }

            try:
                # Validate this workspace
                validation_result = cls.validate_dawei_structure(dawei_path)
                workspace_detail["valid"] = True
                workspace_detail["warnings"] = validation_result.get("warnings", [])
                workspace_detail["workspace_data"] = validation_result.get("workspace_data", {})
                result["valid"] += 1

            except DaweiStructureValidationError as e:
                workspace_detail["error"] = str(e)
                result["invalid"] += 1
                result["errors"].append(
                    {
                        "workspace": workspace_dir.name,
                        "path": str(dawei_path),
                        "error": str(e),
                    }
                )

            result["workspace_details"].append(workspace_detail)

        return result


def validate_dawei_on_startup(dawei_home: Path | None = None) -> None:
    """Validate .dawei structure during server startup.

    This function is designed to be called during server startup.
    It will log validation results and raise an exception if critical errors are found.

    Args:
        dawei_home: Path to DAWEI_HOME directory.
            Defaults to DAWEI_HOME env var or "~/.dawei"

    Raises:
        DaweiStructureValidationError: If critical validation errors are found

    """
    import logging

    logger = logging.getLogger(__name__)

    # Get DAWEI_HOME
    if dawei_home is None:
        dawei_home = Path(get_dawei_home())

    logger.info("=== Validating .dawei directory structure ===")
    logger.info(f"DAWEI_HOME: {dawei_home}")

    try:
        # Check if DAWEI_HOME exists
        if not dawei_home.exists():
            logger.warning(f"DAWEI_HOME does not exist: {dawei_home}")
            logger.info("Skipping .dawei validation (no DAWEI_HOME yet)")
            return

        # Read workspaces.json to get workspace paths
        workspaces_file = dawei_home / "workspaces.json"
        if not workspaces_file.exists():
            logger.warning(f"workspaces.json not found: {workspaces_file}")
            logger.info("Skipping .dawei validation (no workspaces defined yet)")
            return

        # Parse workspaces.json
        try:
            with workspaces_file.open(encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise DaweiStructureValidationError(
                f"Invalid workspaces.json format: {e}",
                path=workspaces_file,
            )

        workspaces = data.get("workspaces", [])
        logger.info(f"Found {len(workspaces)} workspace(s) in workspaces.json")

        # Validate each workspace listed in workspaces.json
        result = {
            "total": len(workspaces),
            "valid": 0,
            "invalid": 0,
            "errors": [],
            "workspace_details": [],
        }

        for workspace in workspaces:
            workspace_name = workspace.get("name", "unknown")
            workspace_path = workspace.get("path", "")

            if not workspace_path:
                error = f"Workspace '{workspace_name}' has no path defined"
                logger.error(f"  - {workspace_name}: {error}")
                result["invalid"] += 1
                result["errors"].append({"workspace": workspace_name, "error": error})
                continue

            # Resolve workspace path
            ws_path = Path(workspace_path)
            if not ws_path.is_absolute():
                # If relative path, resolve relative to DAWEI_HOME
                ws_path = dawei_home / ws_path
            ws_path = ws_path.resolve()

            dawei_path = ws_path / ".dawei"

            workspace_detail = {
                "workspace_name": workspace_name,
                "path": str(ws_path),
                "dawei_path": str(dawei_path),
                "valid": False,
                "error": None,
                "warnings": [],
            }

            try:
                # Validate this workspace
                validation_result = DaweiStructureValidator.validate_dawei_structure(dawei_path)
                workspace_detail["valid"] = True
                workspace_detail["warnings"] = validation_result.get("warnings", [])
                result["valid"] += 1
                logger.info(f"  ✓ {workspace_name}: validated successfully")

            except DaweiStructureValidationError as e:
                workspace_detail["error"] = str(e)
                result["invalid"] += 1
                result["errors"].append({"workspace": workspace_name, "error": str(e)})
                logger.error(f"  ✗ {workspace_name}: {e}")

            result["workspace_details"].append(workspace_detail)

        # Log summary
        logger.info("Validation complete:")
        logger.info(f"  Total workspaces: {result['total']}")
        logger.info(f"  Valid: {result['valid']}")
        logger.info(f"  Invalid: {result['invalid']}")

        # Log errors if any
        if result["errors"]:
            logger.error(f"Found {len(result['errors'])} validation error(s):")
            for error in result["errors"]:
                logger.error(f"  - {error['workspace']}: {error['error']}")

            # Fast Fail: Raise exception if there are critical errors
            raise DaweiStructureValidationError(f"Found {result['invalid']} invalid workspace(s). Check logs for details.")

        # Log warnings if any
        total_warnings = sum(len(detail.get("warnings", [])) for detail in result["workspace_details"])
        if total_warnings > 0:
            logger.warning(f"Found {total_warnings} validation warning(s):")
            for detail in result["workspace_details"]:
                for warning in detail.get("warnings", []):
                    logger.warning(f"  - {detail['workspace_name']}: {warning}")

        # Success message
        if result["valid"] > 0:
            logger.info("✅ All .dawei directory structures validated successfully")

    except DaweiStructureValidationError:
        # Re-raise validation errors
        raise
    except Exception as e:
        # Fast Fail: Log unexpected errors and raise
        logger.error(f"Unexpected error during .dawei validation: {e}", exc_info=True)
        raise DaweiStructureValidationError(f"Unexpected error during validation: {e}") from e


__all__ = [
    "DaweiStructureValidator",
    "DaweiStructureValidationError",
    "WorkspaceJsonError",
    "DirectoryStructureError",
    "validate_dawei_on_startup",
]
