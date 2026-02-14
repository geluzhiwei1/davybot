# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""API Error Codes for Internationalization

Defines standardized error codes that will be translated by the frontend.
This separates error identification from error messages, enabling i18n.

Error Code Format: {category}.{specific_error}

Categories:
- workspace: Workspace operations
- checkpoint: Checkpoint management
- llm_config: LLM provider configuration
- conversation: Conversation management
- plugin: Plugin operations
- skill: Skill operations
- market: Market operations
"""


class ErrorCodes:
    """Standardized error codes and their English messages."""

    # Workspace errors
    WORKSPACE = "workspace"
    WORKSPACE_MESSAGES = {
        f"{WORKSPACE}.not_found": "Workspace with ID '{workspace_id}' not found",
        f"{WORKSPACE}.path_not_found": "Workspace path '{path}' not found",
        f"{WORKSPACE}.not_directory": "Workspace path '{path}' is not a directory",
        f"{WORKSPACE}.load_failed": "Failed to load workspace: {error}",
        f"{WORKSPACE}.create_failed": "Failed to create workspace: {error}",
        f"{WORKSPACE}.update_failed": "Failed to update workspace: {error}",
        f"{WORKSPACE}.delete_failed": "Failed to delete workspace: {error}",
    }

    # Checkpoint errors
    CHECKPOINT = "checkpoint"
    CHECKPOINT_MESSAGES = {
        f"{CHECKPOINT}.not_available": "Checkpoint manager not available",
        f"{CHECKPOINT}.not_found": "Checkpoint '{checkpoint_id}' not found",
        f"{CHECKPOINT}.create_failed": "Failed to create checkpoint: {error}",
        f"{CHECKPOINT}.restore_failed": "Failed to restore checkpoint",
        f"{CHECKPOINT}.delete_failed": "Failed to delete checkpoint: {error}",
        f"{CHECKPOINT}.list_failed": "Failed to get checkpoints: {error}",
    }

    # LLM Configuration errors
    LLM_CONFIG = "llm_config"
    LLM_CONFIG_MESSAGES = {
        f"{LLM_CONFIG}.read_failed": "Failed to read LLM settings: {error}",
        f"{LLM_CONFIG}.read_all_failed": "Failed to read all LLM settings: {error}",
        f"{LLM_CONFIG}.update_failed": "Failed to update LLM settings: {error}",
        f"{LLM_CONFIG}.create_failed": "Failed to create LLM provider: {error}",
        f"{LLM_CONFIG}.delete_failed": "Failed to delete LLM provider: {error}",
        f"{LLM_CONFIG}.not_found": "Settings file not found",
    }

    # Conversation errors
    CONVERSATION = "conversation"
    CONVERSATION_MESSAGES = {
        f"{CONVERSATION}.not_found": "Conversation '{conversation_id}' not found",
        f"{CONVERSATION}.load_failed": "Failed to load conversation: {error}",
        f"{CONVERSATION}.create_failed": "Failed to create conversation: {error}",
        f"{CONVERSATION}.delete_failed": "Failed to delete conversation: {error}",
    }

    # Plugin errors
    PLUGIN = "plugin"
    PLUGIN_MESSAGES = {
        f"{PLUGIN}.not_found": "Plugin '{plugin_id}' not found",
        f"{PLUGIN}.load_failed": "Failed to load plugins: {error}",
        f"{PLUGIN}.activate_failed": "Failed to activate plugin '{plugin_id}'",
        f"{PLUGIN}.deactivate_failed": "Failed to deactivate plugin '{plugin_id}'",
        f"{PLUGIN}.config_invalid": "Plugin configuration is invalid: {error}",
        f"{PLUGIN}.schema_not_found": "Plugin config schema not found",
        f"{PLUGIN}.settings_update_failed": "Failed to update plugin settings: {error}",
    }

    # Skill errors
    SKILL = "skill"
    SKILL_MESSAGES = {
        f"{SKILL}.access_failed": "Failed to access skill directories: {error}",
        f"{SKILL}.search_failed": "Failed to search skills: {error}",
        f"{SKILL}.invalid_data": "Invalid skill data: {error}",
        f"{SKILL}.not_found": "Skill '{skill_name}' not found",
    }

    # Market errors
    MARKET = "market"
    MARKET_MESSAGES = {
        f"{MARKET}.invalid_type": "Invalid resource type: {type}. Use skill, agent, or plugin",
        f"{MARKET}.workspace_not_exist": "Workspace path does not exist: {workspace}",
        f"{MARKET}.workspace_not_directory": "Workspace path is not a directory: {workspace}",
        f"{MARKET}.install_failed": "Installation failed: {error}",
        f"{MARKET}.uninstall_failed": "Uninstallation failed: {error}",
        f"{MARKET}.info_failed": "Failed to get resource info: {error}",
        f"{MARKET}.search_failed": "Search failed: {error}",
    }

    # File operations
    FILE = "file"
    FILE_MESSAGES = {
        f"{FILE}.not_found": "File '{path}' not found",
        f"{FILE}.read_failed": "Failed to read file: {error}",
        f"{FILE}.write_failed": "Failed to write file: {error}",
        f"{FILE}.delete_failed": "Failed to delete file: {error}",
    }

    @classmethod
    def get_message(cls, code: str, **params) -> str:
        """Get error message by code with parameter substitution.

        Args:
            code: Error code (e.g., "workspace.not_found")
            **params: Parameters to substitute in message template

        Returns:
            Formatted error message, or code itself if not found

        """
        all_messages: dict[str, str] = {}
        all_messages.update(cls.WORKSPACE_MESSAGES)
        all_messages.update(cls.CHECKPOINT_MESSAGES)
        all_messages.update(cls.LLM_CONFIG_MESSAGES)
        all_messages.update(cls.CONVERSATION_MESSAGES)
        all_messages.update(cls.PLUGIN_MESSAGES)
        all_messages.update(cls.SKILL_MESSAGES)
        all_messages.update(cls.MARKET_MESSAGES)
        all_messages.update(cls.FILE_MESSAGES)

        template = all_messages.get(code, code)
        try:
            return template.format(**params)
        except (KeyError, ValueError):
            # If formatting fails, return template with params shown
            return f"{template} | Params: {params}"

    @classmethod
    def create_error_detail(cls, code: str, **params) -> dict[str, any]:
        """Create standardized error detail dictionary.

        Args:
            code: Error code
            **params: Parameters for the error message

        Returns:
            Dictionary with 'code' and 'message' keys

        """
        return {"code": code, "message": cls.get_message(code, **params), "params": params or {}}


# Convenience function for creating error details
def error_detail(code: str, **params) -> dict[str, any]:
    """Create error detail dictionary from error code.

    Args:
        code: Error code (e.g., "workspace.not_found")
        **params: Parameters for error message

    Returns:
        Dictionary suitable for HTTPException detail

    Example:
        raise HTTPException(
            status_code=404,
            detail=error_detail("workspace.not_found", workspace_id="123")
        )
    """
    return ErrorCodes.create_error_detail(code, **params)
