# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ACP SDK loader.

Loads ACP directly from repository-local ``deps/python-sdk/src`` as requested,
without requiring ``pip install agent-client-protocol``.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType


def _candidate_sdk_paths() -> list[Path]:
    """Build candidate paths for ACP SDK source directory."""
    env_path = os.environ.get("DAWEI_ACP_SDK_PATH")

    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())

    # /.../agent/dawei/acp/sdk_loader.py
    # parents[3] => repo root
    repo_root = Path(__file__).resolve().parents[3]
    candidates.append(repo_root / "deps" / "python-sdk" / "src")

    # Optional fallback when running from installed package with source checkout nearby
    agent_root = Path(__file__).resolve().parents[2]
    candidates.append(agent_root.parent / "deps" / "python-sdk" / "src")

    return candidates


def ensure_acp_sdk_path() -> Path:
    """Ensure ACP SDK source path is present in ``sys.path``.

    Returns:
        Path: The resolved ACP SDK source directory.

    Raises:
        RuntimeError: If ACP SDK source cannot be located.
    """
    for candidate in _candidate_sdk_paths():
        resolved = candidate.resolve()
        if not resolved.exists() or not resolved.is_dir():
            continue

        if str(resolved) not in sys.path:
            sys.path.insert(0, str(resolved))

        return resolved

    searched = "\n".join(str(path.resolve()) for path in _candidate_sdk_paths())
    raise RuntimeError(
        "ACP SDK not found. Expected deps/python-sdk/src.\n"
        f"Searched paths:\n{searched}\n"
        "You can override with DAWEI_ACP_SDK_PATH.",
    )


def import_acp() -> ModuleType:
    """Import and return ACP package from local SDK source."""
    ensure_acp_sdk_path()
    return importlib.import_module("acp")
