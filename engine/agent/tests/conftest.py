# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Test fixtures for agent core tests.

Creates isolated test workspaces with Ollama LLM provider config,
so each test gets a clean workspace with its own .dawei/ directory.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

# Ollama config for local testing
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def _write_settings_json(path: Path, model: str = OLLAMA_MODEL, base_url: str = OLLAMA_BASE_URL) -> None:
    """Write a settings.json with Ollama provider config."""
    settings = {
        "providerProfiles": {
            "apiConfigs": {
                "ollama-test": {
                    "apiProvider": "openai",
                    "openAiBaseUrl": f"{base_url}/v1",
                    "openAiApiKey": "ollama",
                    "openAiModelId": model,
                    "openAiCustomModelInfo": {
                        "maxTokens": -1,
                        "contextWindow": 32768,
                    },
                    "is_default": True,
                    "temperature": 0.3,
                },
            },
            "currentApiConfigName": "ollama-test",
            "modeApiConfigs": {},
        },
        "globalSettings": {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_workspace_json(path: Path, name: str = "test-workspace") -> None:
    """Write workspace.json metadata."""
    data = {
        "id": name,
        "name": name,
        "display_name": f"Test Workspace: {name}",
        "description": "Auto-created by test suite",
        "created_at": "2025-01-01T00:00:00Z",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_config_json(path: Path) -> None:
    """Write a minimal config.json with disabled features for fast tests."""
    config = {
        "agent": {
            "mode": "orchestrator",
            "plan_mode_confirm_required": False,
            "enable_auto_mode_switch": False,
            "auto_approve_tools": True,
            "max_concurrent_subtasks": 1,
        },
        "memory": {"enabled": False},
        "knowledge": {"enabled": False},
        "skills": {"enabled": False, "auto_discovery": False},
        "tools": {
            "builtin_tools_enabled": True,
            "system_tools_enabled": True,
            "user_tools_enabled": False,
            "workspace_tools_enabled": False,
            "default_timeout": 30,
        },
        "checkpoint": {"checkpoint_interval": 0, "max_checkpoints": 0},
        "compression": {"enabled": False},
        "logging": {"level": "WARNING", "console_output": False, "file_output": False},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def test_workspace(tmp_path: Path) -> Path:
    """Create a fully initialized test workspace with Ollama config.

    Structure:
        {tmp_path}/
          .dawei/
            settings.json       - Ollama provider profile
            workspace.json      - workspace metadata
            config.json         - agent config (memory/knowledge/skills disabled)
            chat-history/       - conversation storage
    """
    ws = tmp_path / "test-ws"
    ws.mkdir()

    dawei_dir = ws / ".dawei"
    _write_settings_json(dawei_dir / "settings.json")
    _write_workspace_json(dawei_dir / "workspace.json")
    _write_config_json(dawei_dir / "config.json")

    chat_dir = dawei_dir / "chat-history"
    chat_dir.mkdir()

    return ws


@pytest.fixture
def test_workspace_with_files(test_workspace: Path) -> Path:
    """Test workspace with some sample files for tool testing."""
    # Create sample files
    (test_workspace / "hello.txt").write_text("Hello, World!\n", encoding="utf-8")
    (test_workspace / "data.json").write_text(
        json.dumps({"key": "value", "count": 42}, indent=2),
        encoding="utf-8",
    )
    src_dir = test_workspace / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text(
        'def main():\n    print("hello from main")\n\nif __name__ == "__main__":\n    main()\n',
        encoding="utf-8",
    )
    return test_workspace
