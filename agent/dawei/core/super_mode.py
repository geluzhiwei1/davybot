# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Super Mode Utilities

Provides functions to check if super mode is enabled and bypass security checks.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Environment variable name for super mode
SUPER_MODE_ENV_VAR = "GEWEI_SUPER_MODE"


def is_super_mode_enabled() -> bool:
    """Check if super mode is enabled.

    Super mode bypasses all security mechanisms including:
    - Path traversal checks
    - Command execution restrictions
    - File permission checks
    - Mode-based permission control

    Returns:
        bool: True if super mode is enabled, False otherwise

    """
    return os.environ.get(SUPER_MODE_ENV_VAR, "0") == "1"


def log_security_bypass(security_check: str, details: str = ""):
    """Log a security bypass event when in super mode.

    Args:
        security_check: Name of the security check being bypassed
        details: Additional details about what was bypassed

    """
    if is_super_mode_enabled():
        logger.warning(
            f"[SUPER MODE] Security check bypassed: {security_check}" + (f" - {details}" if details else ""),
        )


def warn_super_mode():
    """Log a warning message when super mode is detected.
    Call this at application startup to warn about super mode.
    """
    if is_super_mode_enabled():
        logger.warning("=" * 70)
        logger.warning("⚠️  SUPER MODE ENABLED - ALL SECURITY CHECKS DISABLED")
        logger.warning("=" * 70)
        logger.warning("This mode allows:")
        logger.warning("  • Unrestricted file access (can read/write any path)")
        logger.warning("  • Execution of dangerous commands (rm -rf, sudo, etc.)")
        logger.warning("  • Bypass of all permission checks")
        logger.warning("  • No workspace isolation")
        logger.warning("")
        logger.warning("Use with EXTREME CAUTION!")
        logger.warning("=" * 70)


# Decorator to bypass security checks in super mode
def bypass_in_super_mode(default_return=None):
    """Decorator that bypasses function execution in super mode.

    Args:
        default_return: Value to return when bypassing (default: None)

    Example:
        @bypass_in_super_mode(default_return=True)
        def check_path_allowed(path):
            # Security check logic
            return is_safe(path)

        # In super mode, this always returns True without checking

    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            if is_super_mode_enabled():
                log_security_bypass(f"{func.__name__}", f"args={args}, kwargs={kwargs}")
                return default_return if default_return is not None else True
            return func(*args, **kwargs)

        return wrapper

    return decorator
