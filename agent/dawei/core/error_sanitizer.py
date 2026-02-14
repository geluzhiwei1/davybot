# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Error Message Sanitization

Provides utilities to sanitize error messages and prevent information leakage.
Removes sensitive information like:
- File system paths
- Internal stack traces
- Database connection strings
- API keys and passwords
- System information
"""

import logging
import re
import traceback
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class ErrorSanitizer:
    """Sanitizes error messages to prevent information leakage.

    Features:
    - Removes file system paths
    - Sanitizes stack traces
    - Removes sensitive strings (passwords, keys, tokens)
    - Provides user-friendly error messages
    """

    # Patterns to detect and sanitize
    SANITIZATION_PATTERNS: ClassVar[dict[str, list]] = {
        # File paths (Unix and Windows)
        "file_path": [
            r"/[a-zA-Z0-9_\-\.\/]+",  # Unix paths
            r"[A-Z]:\\[a-zA-Z0-9_\-\.\\]+",  # Windows paths
            r"~/",  # Home directory
            r"\.\./",  # Parent directory
        ],
        # Sensitive data patterns
        "password": [
            r'password["\']?\s*[:=]\s*["\']?[^\s"\']+',
            r'pwd["\']?\s*[:=]\s*["\']?[^\s"\']+',
            r'passwd["\']?\s*[:=]\s*["\']?[^\s"\']+',
            r'pass\s*[:=]\s*["\']?[^\s"\']+',
            r":[^@:\s/]+@",  # Passwords in URLs (between : and @)
        ],
        "api_key": [
            r'api[_-]?key["\']?\s*[:=]\s*["\']?[^\s"\']+',
            r'apikey["\']?\s*[:=]\s*["\']?[^\s"\']+',
            r'access[_-]?token["\']?\s*[:=]\s*["\']?[^\s"\']+',
            r"sk-[a-zA-Z0-9]+",  # Stripe-style keys
            r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*",  # Bearer tokens
        ],
        "database_url": [
            r"[\w\-\+]+://[^\s]+",  # Any protocol URL (http, https, postgresql, mysql, etc.)
            r'host["\']?\s*[:=]\s*["\']?[^\s"\']+',
        ],
        # Stack traces
        "stack_trace": [
            r"Traceback \(most recent call last\):",
            r'File ".*?", line \d+',
            r"\[WARNING\|ERROR\|INFO\|DEBUG\]",
        ],
        # System information
        "system_info": [
            r"Python \d+\.\d+\.\d+",
            r"localhost:\d+",
            r"127\.0\.0\.1:\d+",
            r"0\.0\.0\.0:\d+",
        ],
    }

    # Compiled patterns
    COMPILED_PATTERNS = {}

    def __init__(self, enable_sanitization: bool = True):
        """Initialize error sanitizer.

        Args:
            enable_sanitization: Whether to enable sanitization (default: True)

        """
        self.enable_sanitization = enable_sanitization
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for performance."""
        if not self.COMPILED_PATTERNS:
            for category, patterns in self.SANITIZATION_PATTERNS.items():
                compiled_patterns = []
                for pattern in patterns:
                    try:
                        compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
                    except re.error as e:
                        logger.warning(
                            f"Failed to compile regex pattern '{pattern}' in category '{category}': {e}",
                        )
                        # Skip invalid patterns but continue processing others
                self.COMPILED_PATTERNS[category] = compiled_patterns

    def sanitize_error_message(
        self,
        error: Exception,
        include_type: ClassVar[bool] = True,
        max_length: ClassVar[int] = 500,
    ) -> str:
        """Sanitize an exception into a safe error message.

        Args:
            error: The exception to sanitize
            include_type: Whether to include exception type
            max_length: Maximum message length

        Returns:
            Sanitized error message safe for user display

        """
        if not self.enable_sanitization:
            return str(error)

        try:
            # Get basic error message
            error_message = str(error)
            error_type = type(error).__name__ if include_type else None

            # Sanitize the message
            sanitized = self._sanitize_string(error_message)

            # Add error type if requested
            if error_type:
                sanitized = f"{error_type}: {sanitized}"

            # Truncate if too long
            if len(sanitized) > max_length:
                sanitized = sanitized[:max_length] + "..."

            return sanitized

        except Exception:
            logger.exception("Error while sanitizing error message: ")
            # Return generic message if sanitization fails
            return "An error occurred. Please try again or contact support."

    def sanitize_traceback(
        self,
        exc_info: ClassVar[tuple | None] = None,
        include_error_message: ClassVar[bool] = True,
    ) -> str:
        """Sanitize traceback information.

        Args:
            exc_info: Exception info tuple (from sys.exc_info())
            include_error_message: Whether to include the error message

        Returns:
            Sanitized traceback (or generic message)

        """
        if not self.enable_sanitization:
            if exc_info:
                return "".join(traceback.format_exception(*exc_info))
            return "Error occurred"

        # For security, don't expose tracebacks to users
        if include_error_message and exc_info:
            error = exc_info[1]
            return self.sanitize_error_message(error)

        return "An internal error occurred. Please contact support if the problem persists."

    def _sanitize_string(self, text: str) -> str:
        """Sanitize a string by removing sensitive patterns.

        Args:
            text: String to sanitize

        Returns:
            Sanitized string

        """
        if not text:
            return text

        sanitized = text

        # Apply all sanitization patterns
        # Order matters: database URLs first (most comprehensive), then passwords, etc.
        for category, patterns in self.COMPILED_PATTERNS.items():
            for pattern in patterns:
                if pattern is None:
                    continue
                if category == "database_url":
                    # Replace entire database URLs first
                    sanitized = pattern.sub("[REDACTED]", sanitized)
                elif category == "password":
                    # Then any remaining passwords
                    sanitized = pattern.sub("[REDACTED]", sanitized)
                elif category == "api_key":
                    # Then API keys
                    sanitized = pattern.sub("[REDACTED]", sanitized)
                elif category == "file_path":
                    # Replace file paths with generic placeholder
                    sanitized = pattern.sub("[PATH]", sanitized)
                elif category == "stack_trace":
                    # Remove stack trace lines
                    sanitized = pattern.sub("", sanitized)
                elif category == "system_info":
                    # Replace system info with placeholder
                    sanitized = pattern.sub("[SYSTEM]", sanitized)

        # Clean up multiple whitespace
        sanitized = re.sub(r"\s+", " ", sanitized)
        return sanitized.strip()

    def sanitize_dict(
        self,
        data: dict[str, Any],
        sensitive_keys: ClassVar[set[str] | None] = None,
        recursive: ClassVar[bool] = True,
    ) -> dict[str, Any]:
        """Sanitize a dictionary by removing sensitive values.

        Args:
            data: Dictionary to sanitize
            sensitive_keys: Keys to redact (default: common sensitive keys)
            recursive: Whether to recursively sanitize nested dicts

        Returns:
            Sanitized dictionary

        """
        if sensitive_keys is None:
            sensitive_keys = {
                "password",
                "passwd",
                "pwd",
                "secret",
                "token",
                "api_key",
                "apikey",
                "access_token",
                "auth_token",
                "session_key",
                "private_key",
                "secret_key",
                "connection_string",
                "database_url",
                "db_url",
                "mongo_url",
                "redis_url",
                "key",  # Generic key term
            }

        sanitized = {}

        for key, value in data.items():
            # Check if key contains sensitive substring (case-insensitive)
            key_lower = key.lower()
            is_sensitive = any(sensitive_key in key_lower for sensitive_key in sensitive_keys)

            if is_sensitive:
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict) and recursive:
                sanitized[key] = self.sanitize_dict(value, sensitive_keys, recursive)
            elif isinstance(value, str):
                sanitized[key] = self._sanitize_string(value)
            else:
                sanitized[key] = value

        return sanitized

    def is_safe_to_display(self, error_message: str) -> bool:
        """Check if an error message is safe to display to users.

        Args:
            error_message: Error message to check

        Returns:
            True if safe, False otherwise

        """
        # Check for sensitive patterns
        for category, patterns in self.COMPILED_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(error_message):
                    logger.warning(f"Unsafe pattern detected in error message: {category}")
                    return False

        # Check length (very long messages might have dumps)
        if len(error_message) > 1000:
            logger.warning("Error message too long, might contain data dumps")
            return False

        return True


# Global singleton instance
_default_sanitizer = None


def get_sanitizer() -> ErrorSanitizer:
    """Get the global error sanitizer instance."""
    global _default_sanitizer
    if _default_sanitizer is None:
        _default_sanitizer = ErrorSanitizer()
    return _default_sanitizer


def safe_error_message(error: Exception, include_type: bool = True, max_length: int = 500) -> str:
    """Convenience function to get a sanitized error message.

    Args:
        error: The exception to sanitize
        include_type: Whether to include exception type
        max_length: Maximum message length

    Returns:
        Sanitized error message

    """
    return get_sanitizer().sanitize_error_message(error, include_type, max_length)


def safe_traceback(exc_info: tuple | None = None) -> str:
    """Convenience function to get a sanitized traceback.

    Args:
        exc_info: Exception info tuple

    Returns:
        Sanitized traceback

    """
    return get_sanitizer().sanitize_traceback(exc_info)
