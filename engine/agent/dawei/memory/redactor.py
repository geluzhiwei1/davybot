# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Secret redaction for memory system.

Scans text for credentials and replaces them with [REDACTED] before
persistence.  Inspired by Codex's built-in secret scrubbing.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern catalog — each entry: (compiled_regex, replacement, label)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    # --- API keys (vendor-specific prefixes) ---
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"gho_[a-zA-Z0-9]{36,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"glpat-[a-zA-Z0-9_-]{20,}"), "[REDACTED_GITLAB_TOKEN]"),
    (re.compile(r"xox[baprs]-[a-zA-Z0-9-]+"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "[REDACTED_GOOGLE_KEY]"),

    # --- Bearer / Authorization headers ---
    (re.compile(r"(?i)bearer\s+[a-zA-Z0-9_.\-/=]{20,}"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(?i)authorization\s*[:=]\s*[a-zA-Z0-9_.\-/=]{20,}"),
     "Authorization: [REDACTED]"),

    # --- Password assignments ---
    (re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"), r"\1: [REDACTED]"),
    (re.compile(r"(?i)(secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-./+]{8,}['\"]?"),
     r"\1: [REDACTED]"),

    # --- Connection strings with embedded credentials ---
    (re.compile(r"(://[^:\s]+:)([^@{\s]+)(@)"), r"\1[REDACTED]\3"),

    # --- Private key blocks ---
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"
                r"[\s\S]*?-----END (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
     "[REDACTED_PRIVATE_KEY]"),

    # --- JWT tokens (three base64 segments separated by dots) ---
    (re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"),
     "[REDACTED_JWT]"),
]


def redact_secrets(text: str) -> str:
    """Replace credential patterns in *text* with ``[REDACTED]`` placeholders.

    Args:
        text: Raw text that may contain secrets.

    Returns:
        Text with secrets replaced.  Original text is never modified.
    """
    if not text:
        return text

    result = text
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_memory_entry(subject: str, predicate: str, obj: str) -> tuple[str, str, str]:
    """Redact all three fields of a memory triple.

    Returns:
        (redacted_subject, redacted_predicate, redacted_object)
    """
    return (
        redact_secrets(subject),
        redact_secrets(predicate),
        redact_secrets(obj),
    )


def contains_secrets(text: str) -> bool:
    """Quick check whether *text* matches any secret pattern."""
    if not text:
        return False
    return any(p.search(text) for p, _ in _SECRET_PATTERNS)
