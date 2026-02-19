# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""TUI Configuration

Extends CLIConfig with TUI-specific settings.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dawei.config import get_workspaces_root

logger = logging.getLogger(__name__)


@dataclass
class TUIConfig:
    """TUI-specific configuration"""

    # Workspace settings
    workspace: str
    workspace_absolute: str = field(init=False)

    # Agent settings
    llm: str = ""  # Will be loaded from workspace config
    mode: str = ""  # Will be loaded from workspace config (empty = load from config)
    verbose: bool = False

    # TUI-specific settings
    refresh_rate: float = 0.1  # UI refresh rate (seconds)
    max_history: int = 1000  # Max chat history to display
    show_thinking: bool = True  # Show thinking process panel
    show_tools: bool = True  # Show tool execution panel
    theme: str = "default"  # Color theme
    language: str = ""  # UI language (en, zh_CN, zh_TW). Empty = auto-detect

    # Display settings
    max_thinking_lines: int = 10  # Max lines in thinking panel
    max_tool_lines: int = 5  # Max lines in tool panel
    enable_markdown: bool = True  # Enable markdown rendering
    enable_syntax_highlight: bool = True  # Enable code syntax highlighting

    def __post_init__(self):
        """Initialize derived fields"""
        workspace_path = Path(self.workspace).resolve()
        self.workspace_absolute = str(workspace_path)

        # Load LLM and mode from workspace config if not specified
        if not self.llm:
            self.llm = self._load_default_llm()

        if not self.mode:
            self.mode = self._load_default_mode()

        logger.info(f"TUI Config initialized: mode={self.mode}, llm={self.llm}")
        print(f"[CONFIG] TUI Config: mode={self.mode}, llm={self.llm}")

    def _load_default_llm(self) -> str:
        """Load default LLM from settings configuration

        Returns:
            Default LLM config name, or fallback if not found

        Priority:
            1. Workspace settings: {workspace}/.dawei/settings.json
            2. User settings: ~/.dawei/configs/settings.json
            3. Fallback: "glm"

        """
        try:
            # Try workspace settings first
            workspace_settings_file = Path(self.workspace_absolute) / ".dawei" / "settings.json"
            if workspace_settings_file.exists():
                with Path(workspace_settings_file).open() as f:
                    settings = json.load(f)
                current_llm = settings.get("providerProfiles", {}).get("currentApiConfigName")
                if current_llm:
                    logger.info(f"Loaded LLM from workspace settings.json: {current_llm}")
                    print(f"[CONFIG] Loaded LLM from workspace settings.json: {current_llm}")
                    return current_llm

            # Try user settings (DAWEI_HOME)
            user_settings_file = Path(get_workspaces_root()) / "configs" / "settings.json"
            if user_settings_file.exists():
                with Path(user_settings_file).open() as f:
                    settings = json.load(f)
                current_llm = settings.get("providerProfiles", {}).get("currentApiConfigName")
                if current_llm:
                    logger.info(f"Loaded LLM from user settings.json: {current_llm}")
                    print(f"[CONFIG] Loaded LLM from user settings.json: {current_llm}")
                    return current_llm

            # Fallback to default
            logger.info("No LLM in settings files, using default: glm")
            print("[CONFIG] No LLM in settings files, using default: glm")
            return "glm"

        except Exception as e:
            # Fallback to default on any error
            logger.warning(f"Failed to load LLM from settings: {e}, using default: glm")
            print(f"[CONFIG] Failed to load LLM from settings: {e}, using default: glm")
            return "glm"

    def _load_default_mode(self) -> str:
        """Load default mode from workspace configuration

        Returns:
            Default mode, or fallback if not found

        """
        # Valid AgentMode values (from dawei.agentic.agent_config.AgentMode)
        # Extended to support all agent modes
        valid_modes = ["plan", "build", "orchestrator", "code", "ask", "debug"]
        default_mode = "plan"

        try:
            workspace_config_file = Path(self.workspace_absolute) / ".dawei" / "workspace.json"

            if not workspace_config_file.exists():
                # Fallback to default if workspace config doesn't exist
                print(f"[CONFIG] No workspace.json found, using default mode: {default_mode}")
                return default_mode

            with Path(workspace_config_file).open() as f:
                workspace_config = json.load(f)

            # Get current mode from user_ui_context
            current_mode = workspace_config.get("user_ui_context", {}).get("current_mode")

            if current_mode:
                # Validate mode value
                if current_mode in valid_modes:
                    logger.info(f"Loaded mode from workspace config: {current_mode}")
                    print(f"[CONFIG] Loaded mode from workspace config: {current_mode}")
                    return current_mode
                logger.warning(f"Invalid mode in workspace config: '{current_mode}' (not in {valid_modes}), using default: {default_mode}")
                print(f"[CONFIG] Invalid mode '{current_mode}' in workspace config, using default: {default_mode}")
                return default_mode

            # Fallback to default
            logger.info(f"No mode in workspace config, using default: {default_mode}")
            print(f"[CONFIG] No mode in workspace config, using default: {default_mode}")
            return default_mode

        except Exception as e:
            # Fallback to default on any error
            logger.warning(f"Failed to load mode from workspace config: {e}, using default: {default_mode}")
            print(f"[CONFIG] Failed to load mode from workspace config: {e}, using default: {default_mode}")
            return default_mode

    def validate(self) -> tuple[bool, str | None]:
        """Validate configuration

        Returns:
            Tuple of (is_valid, error_message)

        """
        # Validate workspace path
        workspace_path = Path(self.workspace_absolute)
        if not workspace_path.exists():
            return False, f"Workspace path does not exist: {self.workspace_absolute}"

        # Validate mode (AgentMode values)
        # Extended to support all agent modes
        valid_modes = ["plan", "build", "orchestrator", "code", "ask", "debug"]
        if self.mode not in valid_modes:
            return False, f"Invalid mode: {self.mode}. Must be one of {valid_modes}"

        # Validate refresh rate
        if self.refresh_rate < 0.01 or self.refresh_rate > 1.0:
            return (
                False,
                f"Refresh rate must be between 0.01 and 1.0 seconds, got {self.refresh_rate}",
            )

        return True, None

    def ensure_workspace_initialized(self):
        """Ensure workspace directory structure exists"""
        workspace_path = Path(self.workspace_absolute)

        # Create .dawei directory if needed
        gewei_dir = workspace_path / ".dawei"
        gewei_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (gewei_dir / "tools").mkdir(exist_ok=True)
        (gewei_dir / "checkpoints").mkdir(exist_ok=True)
        (gewei_dir / "plan").mkdir(exist_ok=True)

    def get_tui_config_file(self) -> Path:
        """Get TUI config file path

        Returns:
            Path to TUI config file

        """
        return Path(self.workspace_absolute) / ".dawei" / "tui_config.json"

    def save_tui_config(self) -> None:
        """Save TUI settings to config file"""
        config_file = self.get_tui_config_file()

        # Create .dawei directory if needed
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Settings to save (exclude workspace and workspace_absolute)
        settings = {
            "refresh_rate": self.refresh_rate,
            "max_history": self.max_history,
            "show_thinking": self.show_thinking,
            "show_tools": self.show_tools,
            "theme": self.theme,
            "language": self.language,
            "max_thinking_lines": self.max_thinking_lines,
            "max_tool_lines": self.max_tool_lines,
            "enable_markdown": self.enable_markdown,
            "enable_syntax_highlight": self.enable_syntax_highlight,
        }

        with config_file.open("w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

    @classmethod
    def load_tui_settings(cls, workspace: str) -> dict:
        """Load TUI settings from config file

        Args:
            workspace: Workspace path

        Returns:
            Dictionary of TUI settings (empty dict if file doesn't exist)

        """
        config_file = Path(workspace).resolve() / ".dawei" / "tui_config.json"

        if not config_file.exists():
            return {}

        try:
            with Path(config_file).open(encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # Return empty dict on error
            return {}


def create_tui_config(
    workspace: str,
    llm: str = "",  # Empty means load from workspace config
    mode: str = "plan",
    verbose: bool = False,
    **kwargs,
) -> TUIConfig:
    """Create TUI configuration

    Args:
        workspace: Workspace path
        llm: LLM model to use (empty string to load from workspace config)
        mode: Agent mode
        verbose: Enable verbose logging
        **kwargs: Additional TUI settings

    Returns:
        TUIConfig instance

    """
    # Load saved TUI settings if they exist
    saved_settings = TUIConfig.load_tui_settings(workspace)

    # Merge: kwargs > saved_settings > defaults
    merged_kwargs = {}

    # Default TUI settings
    default_tui_settings = {
        "refresh_rate": 0.1,
        "max_history": 1000,
        "show_thinking": True,
        "show_tools": True,
        "theme": "default",
        "language": "",  # Empty means auto-detect
        "max_thinking_lines": 10,
        "max_tool_lines": 5,
        "enable_markdown": True,
        "enable_syntax_highlight": True,
    }

    # Apply defaults, then saved settings, then kwargs
    merged_kwargs.update(default_tui_settings)
    merged_kwargs.update(saved_settings)
    merged_kwargs.update(kwargs)

    return TUIConfig(workspace=workspace, llm=llm, mode=mode, verbose=verbose, **merged_kwargs)
