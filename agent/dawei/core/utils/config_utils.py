# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Configuration utility functions"""

from typing import Any

from dawei.agentic.agent_config import Config
from dawei.core.errors import ValidationError


def validate_and_create_config(config: Config | dict[str, Any] | None = None) -> Config:
    """Validate and create a Config object from various input types.

    Args:
        config: Configuration object, dictionary, or None

    Returns:
        Validated Config object

    Raises:
        ValidationError: If config type is invalid

    """
    if config is None:
        config_obj = Config()
    elif isinstance(config, dict):
        config_obj = Config(config)
    elif isinstance(config, Config):
        config_obj = config
    else:
        raise ValidationError("config", str(type(config)), "must be None, dict, or Config")

    # Apply environment variable overrides
    config_obj.apply_env_overrides()

    return config_obj
