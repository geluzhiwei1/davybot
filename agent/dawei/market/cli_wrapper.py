# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""CLI wrapper for davybot-market-cli integration.

Provides a Python interface to execute davy CLI commands
and parse their JSON output.

IMPORTANT: This wrapper requires davybot-market-cli to be installed.
If the CLI is not available, operations will fail immediately (fast fail).
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from .models import CliExecutionError

logger = logging.getLogger(__name__)


class CliNotFoundError(Exception):
    """Raised when davy-market CLI is not found."""


class CliWrapper:
    """Wrapper for executing davybot-market-cli commands.

    Handles subprocess execution, JSON parsing, and error handling.

    IMPORTANT: Requires davybot-market-cli to be installed. Will fail fast if not found.
    """

    # Default Market API URL
    DEFAULT_API_URL = "http://www.davybot.com/market/api/v1"

    # Command timeout in seconds
    DEFAULT_TIMEOUT = 60

    def __init__(
        self,
        command: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_url: str | None = None,
    ):
        """Initialize CLI wrapper.

        Args:
            command: CLI command path (default: auto-detected)
            timeout: Command execution timeout in seconds
            api_url: Optional Market API URL (defaults to DEFAULT_API_URL)

        Raises:
            CliNotFoundError: If davy-market CLI cannot be found

        """
        # Auto-detect CLI path if not provided
        if command is None:
            command = self._detect_cli_path()

        self.command = command
        self.timeout = timeout
        self.api_url = api_url or self.DEFAULT_API_URL

        # Verify CLI is immediately available
        self._verify_cli_available()

    def _detect_cli_path(self) -> str:
        """Detect the path to davy-market CLI.

        Searches in the same directory as the Python interpreter,
        or falls back to Python module invocation.

        Returns:
            Path to CLI executable or Python module command

        Raises:
            CliNotFoundError: If CLI cannot be found

        """
        import sys

        # Try to find CLI executable in the same directory as the Python interpreter
        python_dir = Path(sys.executable).parent
        # Prefer davy-market over dawei/davy (older versions)
        for cli_name in ["davy-market", "dawei-market", "davy", "dawei"]:
            cli_path = python_dir / cli_name
            if cli_path.exists() and cli_path.is_file():
                logger.info(f"Found davy-market CLI at: {cli_path}")
                return str(cli_path)

        # Fallback to Python module invocation
        # Use uv run to ensure the environment is correct
        python_exe = sys.executable
        logger.info(f"Using Python module invocation: {python_exe} -m davybot_market_cli.cli")
        return f"{python_exe} -m davybot_market_cli.cli"

    def _verify_cli_available(self) -> None:
        """Verify that the davy CLI is available.

        Raises:
            CliNotFoundError: If CLI is not found or not executable

        """
        # Check if command is a Python module invocation
        if " -m " in self.command or "python" in self.command.lower():
            # It's a Python module invocation, verify by trying to import
            try:
                import davybot_market_cli

                logger.debug("CLI module available: davybot_market_cli")
                return
            except ImportError:
                raise CliNotFoundError("davybot-market-cli module not found.\nPlease install: pip install davybot-market-cli")

        # Otherwise check as executable file
        cli_path = Path(self.command)
        if not cli_path.exists():
            raise CliNotFoundError(f"davy-market CLI not found at: {self.command}\nPlease install davybot-market-cli: pip install davybot-market-cli")

        if not cli_path.is_file() or not os.access(cli_path, os.X_OK):
            raise CliNotFoundError(f"davy-market CLI exists but is not executable: {self.command}")

        logger.debug(f"CLI verified and executable: {self.command}")

    def _execute(
        self,
        args: list[str],
        capture_output: bool = True,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Execute a CLI command.

        Args:
            args: Command arguments
            capture_output: Whether to capture stdout/stderr
            check: Whether to raise error on non-zero exit

        Returns:
            Completed process result

        Raises:
            CliExecutionError: If command execution fails

        """
        # Check if command is a Python module invocation
        if " -m " in self.command:
            # Split Python executable and module
            parts = self.command.split(" -m ")
            cmd = [*parts[0].strip().split(), "-m", parts[1].strip(), *args]
        else:
            cmd = [self.command, *args]

        # Add API URL environment variable if configured
        env = None
        if self.api_url:
            env = os.environ.copy()
            env["DAVYBOT_API_URL"] = self.api_url

        logger.debug(f"Executing: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=self.timeout,
                env=env,
            )

            if check and result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(f"CLI command failed: {error_msg}")
                raise CliExecutionError(" ".join(cmd), result.returncode, error_msg)

            return result

        except subprocess.TimeoutExpired:
            logger.exception(f"CLI command timed out after {self.timeout}s")
            raise CliExecutionError(" ".join(cmd), -1, f"Command timed out after {self.timeout}s")
        except FileNotFoundError:
            logger.exception(f"CLI command not found: {self.command}")
            raise CliExecutionError(" ".join(cmd), -1, f"Command '{self.command}' not found")

    def _parse_json_output(self, stdout: str) -> dict[str, Any]:
        """Parse JSON output from CLI command.

        Args:
            stdout: Command stdout string

        Returns:
            Parsed JSON dictionary

        Raises:
            CliExecutionError: If JSON parsing fails

        """
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as e:
            logger.exception("Failed to parse JSON output: ")
            raise CliExecutionError(f"{self.command} (parse)", -1, f"Invalid JSON output: {e}")

    # ========================================================================
    # Plugin Commands
    # ========================================================================

    def plugin_list(self, workspace: str, plugin_type: str | None = None) -> dict[str, Any]:
        """List installed plugins in workspace.

        Args:
            workspace: Workspace path
            plugin_type: Plugin type filter

        Returns:
            Dictionary with installed plugins

        """
        args = ["plugin", "list", "--workspace", workspace, "--output", "json"]

        if plugin_type:
            args.extend(["--type", plugin_type])

        result = self._execute(args, check=False)
        # Plugin list may return empty results without error
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "plugins": self._parse_plugin_list_output(result.stdout),
        }

    def _parse_plugin_list_output(self, stdout: str) -> list[dict[str, Any]]:
        """Parse plugin list output."""
        try:
            data = json.loads(stdout)
            return data.get("plugins", [])
        except json.JSONDecodeError:
            # If not JSON, return empty list
            return []

    def plugin_uninstall(self, plugin_name: str, workspace: str) -> dict[str, Any]:
        """Uninstall a plugin from workspace.

        Args:
            plugin_name: Plugin name
            workspace: Workspace path

        Returns:
            Dictionary with uninstall result

        """
        args = ["plugin", "uninstall", plugin_name, "--workspace", workspace]

        result = self._execute(args, check=False)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def plugin_install(
        self,
        plugin_uri: str,
        workspace: str,
        _enable: bool = False,
        _force: bool = False,
    ) -> dict[str, Any]:
        """Install a plugin using the CLI install command.

        Args:
            plugin_uri: Plugin URI (e.g., plugin://feishu-channel or just feishu-channel)
            workspace: Workspace path
            enable: Whether to enable the plugin after installation
            force: Force reinstall if already exists

        Returns:
            Dictionary with installation result

        """
        # Build install command args
        args = ["install", plugin_uri, "--output", workspace]

        # Add enable flag if specified (not directly supported by CLI, but we can try)
        # Note: davy-market CLI doesn't have --enable flag, plugins need to be enabled separately

        result = self._execute(args, check=False)

        # Parse output to determine success
        success = result.returncode == 0

        # Try to parse stderr for error messages
        stderr = result.stderr.strip() if result.stderr else ""

        return {
            "success": success,
            "stdout": result.stdout,
            "stderr": stderr,
            "returncode": result.returncode,
        }
