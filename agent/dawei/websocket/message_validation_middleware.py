# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WebSocket Message Validation Middleware

Provides security-focused message validation including:
- Rate limiting per session
- Message size limits
- Malicious pattern detection
- Content sanitization
"""

import logging
import re
import time
from collections import defaultdict, deque
from typing import Any, ClassVar

from dawei.websocket.protocol import BaseWebSocketMessage, MessageType

logger = logging.getLogger(__name__)


class MessageValidationMiddleware:
    """WebSocket message validation middleware for security.

    Features:
    - Rate limiting (messages per second per session)
    - Message size limits
    - Malicious pattern detection (SQL injection, XSS, etc.)
    - Session-based tracking
    """

    def __init__(
        self,
        max_message_size: ClassVar[int] = 1024 * 1024,  # 1MB default
        max_messages_per_second: ClassVar[int] = 100,
        max_burst_messages: ClassVar[int] = 200,
        enabled_checks: ClassVar[set[str] | None] = None,
    ):
        """Initialize validation middleware.

        Args:
            max_message_size: Maximum message size in bytes
            max_messages_per_second: Sustained rate limit
            max_burst_messages: Burst rate limit
            enabled_checks: Set of enabled validation checks.
                Options: 'rate_limit', 'size', 'patterns', 'all'
                Default: {'all'}

        """
        self.max_message_size = max_message_size
        self.max_messages_per_second = max_messages_per_second
        self.max_burst_messages = max_burst_messages

        # Default: enable all checks
        if enabled_checks is None:
            enabled_checks = {"all"}
        self.enabled_checks = enabled_checks

        # Session tracking: {session_id: {'timestamps': deque, 'count': int}}
        self.session_message_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.session_message_counts: dict[str, int] = defaultdict(int)
        self.session_last_reset: dict[str, float] = {}

        # Malicious patterns to detect
        self.malicious_patterns = {
            "sql_injection": [
                r"union\s+select",
                r"or\s+.*?=\s*.*?or",
                r"and\s+.*?=\s*.*?and",
                r";\s*drop\s+table",
                r";\s*delete\s+from",
                r"\bexec\b",
                r"'\s*;",
                r"1'\s*=\s*'1",
                r"admin'--",
                r"admin'#",
            ],
            "xss": [
                r"<script[^>]*>",
                r"</script>",
                r"javascript:",
                r"onerror\s*=",
                r"onload\s*=",
                r"onclick\s*=",
                r"<iframe",
                r"<object",
                r"<embed",
                r"fromCharCode",
                r"&#x",
                r"&#",
            ],
            "path_traversal": [
                r"\.\./.*\.\.",
                r"\.\.\\",
                r"%2e%2e",
                r"~",
                r"\.\.[a-zA-Z0-9]",
            ],
            "command_injection": [
                r";\s*(ls|cat|rm|wget|curl|nc|netcat|sh|bash|powershell)\s",
                r"\|\s*(ls|cat|rm|wget|curl|nc|netcat|sh|bash)\s",
                r"`.*`",
                r"\$\(.*\)",
                r">\s*/dev/",
                r"&&\s*\w+",
            ],
            "code_injection": [
                r"__import__",
                r"eval\s*\(",
                r"exec\s*\(",
                r"compile\s*\(",
                r"__globals__",
                r"__builtins__",
            ],
        }

        # Compile regex patterns for performance
        self.compiled_patterns = {}
        for category, patterns in self.malicious_patterns.items():
            self.compiled_patterns[category] = [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in patterns]

        logger.info(
            f"MessageValidationMiddleware initialized: max_size={max_message_size}, rate_limit={max_messages_per_second}/s, burst={max_burst_messages}",
        )

    def is_check_enabled(self, check_name: str) -> bool:
        """Check if a specific validation is enabled."""
        return "all" in self.enabled_checks or check_name in self.enabled_checks

    async def validate_message(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
        raw_data: ClassVar[str | None] = None,
    ) -> tuple[bool, str | None]:
        """Validate a WebSocket message.

        Args:
            session_id: Session identifier
            message: Parsed message object
            raw_data: Raw JSON string (for pattern matching)

        Returns:
            tuple[bool, Optional[str]]: (is_valid, error_message)

        Raises:
            ValueError: If validation fails with specific reason

        """
        try:
            # 1. Rate limiting check
            if self.is_check_enabled("rate_limit"):
                is_valid, error = self._check_rate_limit(session_id)
                if not is_valid:
                    logger.warning(f"Rate limit exceeded for session {session_id}")
                    return False, error

            # 2. Message size check
            if raw_data and self.is_check_enabled("size"):
                is_valid, error = self._check_message_size(raw_data)
                if not is_valid:
                    logger.warning(f"Message size exceeded for session {session_id}")
                    return False, error

            # 3. Malicious pattern detection
            if raw_data and self.is_check_enabled("patterns"):
                is_valid, error = self._check_malicious_patterns(raw_data, message)
                if not is_valid:
                    logger.warning(f"Malicious pattern detected in session {session_id}")
                    return False, error

            return True, None

        # The method returns a boolean tuple, so all errors are converted to validation failures.
        except Exception as e:
            logger.error(
                f"Unexpected validation error in middleware: {e.__class__.__name__}: {e}",
                exc_info=True,
            )
            return False, f"Validation system error: {e!s}"

    def _check_rate_limit(self, session_id: str) -> tuple[bool, str | None]:
        """Check rate limits for a session.

        Implements token bucket algorithm:
        - Sustained rate: max_messages_per_second
        - Burst capacity: max_burst_messages
        """
        current_time = time.time()

        # Initialize or get last reset time
        if session_id not in self.session_last_reset:
            self.session_last_reset[session_id] = current_time
            self.session_message_counts[session_id] = 0

        last_reset = self.session_last_reset[session_id]
        time_elapsed = current_time - last_reset

        # Reset counter if more than 1 second has passed
        if time_elapsed >= 1.0:
            self.session_message_counts[session_id] = 0
            self.session_last_reset[session_id] = current_time

        # Increment message count
        self.session_message_counts[session_id] += 1

        # Check sustained rate
        if self.session_message_counts[session_id] > self.max_messages_per_second:
            return False, (f"Rate limit exceeded: {self.session_message_counts[session_id]} messages in last second (limit: {self.max_messages_per_second}/s)")

        # Check burst rate using sliding window
        timestamps = self.session_message_history[session_id]
        timestamps.append(current_time)

        # Remove timestamps older than 1 second
        while timestamps and timestamps[0] < current_time - 1.0:
            timestamps.popleft()

        if len(timestamps) > self.max_burst_messages:
            return False, (f"Burst rate limit exceeded: {len(timestamps)} messages in 1 second window (limit: {self.max_burst_messages})")

        return True, None

    def _check_message_size(self, raw_data: str) -> tuple[bool, str | None]:
        """Check if message size exceeds limit."""
        size_bytes = len(raw_data.encode("utf-8"))

        if size_bytes > self.max_message_size:
            return False, (f"Message size {size_bytes} bytes exceeds limit of {self.max_message_size} bytes")

        return True, None

    def _check_malicious_patterns(
        self,
        raw_data: str,
        message: BaseWebSocketMessage,
    ) -> tuple[bool, str | None]:
        """Check for malicious patterns in message content.

        Args:
            raw_data: Raw JSON string
            message: Parsed message object

        Returns:
            tuple[bool, Optional[str]]: (is_safe, error_message)

        """
        # Check both raw data and message content fields
        content_to_check = [raw_data]

        # Also check specific message fields
        if hasattr(message, "content") and message.content:
            content_to_check.append(str(message.content))

        if hasattr(message, "message") and message.message:
            content_to_check.append(str(message.message))

        if hasattr(message, "query") and message.query:
            content_to_check.append(str(message.query))

        # Check each content piece against all patterns
        for content in content_to_check:
            for category, patterns in self.compiled_patterns.items():
                for pattern in patterns:
                    if pattern.search(content):
                        logger.warning(
                            f"Malicious pattern detected: category={category}, pattern={pattern.pattern}, session={message.session_id}",
                        )
                        return False, (f"Message contains potentially malicious content (category: {category})")

        return True, None

    def reset_session_limits(self, session_id: str):
        """Reset rate limits for a session.

        Useful for testing or administrative actions.
        """
        if session_id in self.session_message_history:
            self.session_message_history[session_id].clear()
        if session_id in self.session_message_counts:
            self.session_message_counts[session_id] = 0
        if session_id in self.session_last_reset:
            del self.session_last_reset[session_id]

        logger.info(f"Reset rate limits for session {session_id}")

    def get_session_stats(self, session_id: str) -> dict[str, Any]:
        """Get rate limit statistics for a session."""
        timestamps = self.session_message_history.get(session_id, deque())
        current_time = time.time()

        # Count messages in last second
        recent_messages = sum(1 for ts in timestamps if ts > current_time - 1.0)

        return {
            "session_id": session_id,
            "messages_last_second": recent_messages,
            "burst_limit": self.max_burst_messages,
            "sustained_rate": self.session_message_counts.get(session_id, 0),
            "sustained_limit": self.max_messages_per_second,
        }

    def cleanup_old_sessions(self, max_age_seconds: int = 3600):
        """Clean up session data for old sessions.

        Args:
            max_age_seconds: Remove sessions inactive for this long

        """
        current_time = time.time()
        sessions_to_remove = []

        for session_id, timestamps in self.session_message_history.items():
            if not timestamps:
                continue
            last_activity = timestamps[-1]
            if current_time - last_activity > max_age_seconds:
                sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            self.reset_session_limits(session_id)

        if sessions_to_remove:
            logger.info(
                f"Cleaned up {len(sessions_to_remove)} inactive sessions (older than {max_age_seconds}s)",
            )


class MessageSizeValidator:
    """Utility class for message size validation."""

    # Size limits for different message types (bytes)
    SIZE_LIMITS = {
        MessageType.USER_MESSAGE: 100 * 1024,  # 100KB
        MessageType.ASSISTANT_MESSAGE: 1024 * 1024,  # 1MB
        MessageType.STREAM_CONTENT: 10 * 1024,  # 10KB per chunk
        MessageType.TOOL_CALL_RESULT: 5 * 1024 * 1024,  # 5MB
        "default": 1024 * 1024,  # 1MB default
    }

    @classmethod
    def get_size_limit(cls, message_type: str) -> int:
        """Get size limit for a message type."""
        return cls.SIZE_LIMITS.get(message_type, cls.SIZE_LIMITS["default"])

    @classmethod
    def validate_size(cls, raw_data: str, message_type: str) -> tuple[bool, str | None]:
        """Validate message size against type-specific limits.

        Args:
            raw_data: Raw JSON string
            message_type: Type of message

        Returns:
            tuple[bool, Optional[str]]: (is_valid, error_message)

        """
        size_bytes = len(raw_data.encode("utf-8"))
        limit = cls.get_size_limit(message_type)

        if size_bytes > limit:
            return False, (f"Message size {size_bytes} bytes exceeds limit of {limit} bytes for type {message_type}")

        return True, None
