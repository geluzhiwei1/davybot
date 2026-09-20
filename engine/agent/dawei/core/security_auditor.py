# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Security audit logger — append-only JSONL trail of security-relevant events.

Phase 0 (P0) scope: infrastructure + policy-change audit. Enforcement-point
hooks (command/sandbox/tool allow-deny decisions, approval prompts) are added in
P2-P3 as those execution layers are touched.

Design
------
- Append-only JSONL at ``{DAWEI_HOME}/logs/security_audit.jsonl``
- Thread-safe (lock); **never raises** — audit must not break execution
- Redacts sensitive argument values (passwords, tokens, secrets, …)
- UTC ISO-8601 timestamps

Record shape::

    {"ts": "2026-06-16T12:00:00+00:00", "event": "security.policy.change",
     "user_id": "u123", "scope": "workspace", "workspace_id": "ws-abc",
     "settings": {"enableCommandWhitelist": true, ...}}

Usage::

    from dawei.core.security_auditor import security_auditor
    security_auditor.log("security.policy.change", user_id=uid, scope="workspace",
                         workspace_id=wid, settings=normalized)
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dawei import get_dawei_home

logger = logging.getLogger(__name__)

_AUDIT_LOG_REL = "logs/security_audit.jsonl"

# Keys whose VALUES are redacted wherever they appear (recursively) in the payload.
_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|authorization|cookie|credential|jwt)",
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


def _redact(value: Any) -> Any:
    """Recursively redact values under sensitive-looking keys."""
    if isinstance(value, dict):
        return {
            k: (_REDACTED if _SENSITIVE_KEY_RE.search(str(k)) else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, tuple):
        return [_redact(v) for v in value]
    return value


class SecurityAuditor:
    """Append-only JSONL security audit logger (singleton-friendly)."""

    def __init__(self, log_path: Path | None = None, enabled: bool = True) -> None:
        self._log_path: Path = log_path or (get_dawei_home() / _AUDIT_LOG_REL)
        self._enabled: bool = enabled
        self._lock = threading.Lock()
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # pragma: no cover - best effort
            logger.warning(f"SecurityAuditor: cannot create log dir {self._log_path.parent}: {e}")

    @property
    def log_path(self) -> Path:
        return self._log_path

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def log(self, event: str, **fields: Any) -> None:
        """Append one audit record. Silently no-ops when disabled or on I/O error."""
        if not self._enabled:
            return
        record: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **_redact(fields),
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            try:
                with self._log_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception as e:  # pragma: no cover - must not raise
                logger.warning(f"SecurityAuditor: failed to write audit record ({event}): {e}")


# Module-level singleton. Tests may construct their own SecurityAuditor(log_path=...).
security_auditor = SecurityAuditor()
