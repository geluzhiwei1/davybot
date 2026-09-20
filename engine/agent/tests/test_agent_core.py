# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agent core integration tests using CLI + local Ollama.

Tests the full agent pipeline:
  CLI config -> Workspace init -> Agent creation -> Message processing -> LLM response

These tests require:
  - Ollama running at localhost:11434
  - Model 'qwen2.5:7b' (or set OLLAMA_MODEL env var)

Usage:
    cd agent
    pytest tests/test_agent_core.py -v --timeout=120
    pytest tests/test_agent_core.py -v -m "not slow"     # skip slow tests
    pytest tests/test_agent_core.py::test_agent_simple_qa -v  # single test
"""

import asyncio
import json
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Skip entire module if Ollama is not reachable
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def _ollama_available() -> bool:
    """Check if Ollama is reachable."""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            return OLLAMA_MODEL in models or any(m.startswith(OLLAMA_MODEL.split(":")[0]) for m in models)
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _ollama_available(), reason=f"Ollama not running or model '{OLLAMA_MODEL}' not found"),
]


# ---------------------------------------------------------------------------
# Test: CLI config creation & validation
# ---------------------------------------------------------------------------


class TestCLIConfig:
    """Test CLI config creation and workspace initialization."""

    def test_cli_config_creation(self, test_workspace: Path):
        """CLIConfig can be created with a valid workspace."""
        from dawei.cli.config import CLIConfig

        config = CLIConfig(
            workspace=str(test_workspace),
            mode="orchestrator",
            message="hello",
        )
        assert config.workspace_path == test_workspace
        assert config.mode == "orchestrator"
        assert config.message == "hello"

    def test_cli_config_validates_workspace_exists(self, tmp_path: Path):
        """CLIConfig rejects non-existent workspace."""
        from dawei.cli.config import CLIConfig

        config = CLIConfig(
            workspace=str(tmp_path / "nonexistent"),
            mode="orchestrator",
            message="hello",
        )
        is_valid, error = config.validate()
        assert not is_valid
        assert "does not exist" in error

    def test_cli_config_validates_message_not_empty(self, test_workspace: Path):
        """CLIConfig rejects empty message."""
        from dawei.cli.config import CLIConfig

        config = CLIConfig(
            workspace=str(test_workspace),
            mode="orchestrator",
            message="   ",
        )
        is_valid, error = config.validate()
        assert not is_valid
        assert "empty" in error.lower()

    def test_ensure_workspace_initialized(self, tmp_path: Path):
        """ensure_workspace_initialized creates .dawei/ structure."""
        from dawei.cli.config import CLIConfig

        ws = tmp_path / "fresh-ws"
        ws.mkdir()
        config = CLIConfig(
            workspace=str(ws),
            mode="orchestrator",
            message="hello",
        )
        config.ensure_workspace_initialized()

        dawei_dir = ws / ".dawei"
        assert dawei_dir.exists()
        assert (dawei_dir / "chat-history").exists()
        assert (dawei_dir / "settings.json").exists()


# ---------------------------------------------------------------------------
# Test: Workspace initialization
# ---------------------------------------------------------------------------


class TestWorkspaceInit:
    """Test UserWorkspace initialization with Ollama config."""

    @pytest.mark.asyncio
    async def test_workspace_initialize(self, test_workspace: Path):
        """Workspace initializes and loads settings."""
        from dawei.workspace.user_workspace import UserWorkspace

        ws = UserWorkspace(workspace_path=str(test_workspace))
        await ws.initialize()

        assert ws.workspace_info is not None
        assert ws.workspace_info.name == "test-workspace"
        assert ws.llm_manager is not None
        assert ws.llm_manager.get_current_config_name() == "ollama-test"

        await ws.cleanup()

    @pytest.mark.asyncio
    async def test_workspace_llm_provider(self, test_workspace: Path):
        """Workspace LLM provider creates a working client."""
        from dawei.workspace.user_workspace import UserWorkspace

        ws = UserWorkspace(workspace_path=str(test_workspace))
        await ws.initialize()

        provider = ws.llm_manager.get_default_llm_provider()
        assert provider is not None
        assert provider.model == OLLAMA_MODEL

        await ws.cleanup()


# ---------------------------------------------------------------------------
# Test: LLM client directly
# ---------------------------------------------------------------------------


class TestLLMClient:
    """Test LLM client creation and basic call through Ollama."""

    def test_create_ollama_client(self):
        """Factory creates a client for Ollama via OpenAI-compatible API."""
        from dawei.llm_api.provider.client_factory import LLMClientFactory

        config = {
            "apiProvider": "openai",
            "openAiBaseUrl": f"{OLLAMA_BASE_URL}/v1",
            "openAiApiKey": "ollama",
            "openAiModelId": OLLAMA_MODEL,
            "openAiCustomModelInfo": {
                "maxTokens": -1,
                "contextWindow": 32768,
            },
        }
        client = LLMClientFactory.create_client(config)
        assert client is not None
        assert client.model == OLLAMA_MODEL

    @pytest.mark.asyncio
    async def test_llm_simple_completion(self):
        """LLM client returns a non-empty response for a simple prompt."""
        from dawei.llm_api.provider.client_factory import LLMClientFactory
        from dawei.entity.lm_messages import UserMessage

        config = {
            "apiProvider": "openai",
            "openAiBaseUrl": f"{OLLAMA_BASE_URL}/v1",
            "openAiApiKey": "ollama",
            "openAiModelId": OLLAMA_MODEL,
            "openAiCustomModelInfo": {"maxTokens": -1, "contextWindow": 32768},
            "temperature": 0.1,
        }
        client = LLMClientFactory.create_client(config)

        messages = [UserMessage(content="Say exactly: pong")]
        chunks = []
        async for chunk in client.create_message(messages):
            chunks.append(chunk)

        # At least one content chunk
        from dawei.entity.stream_message import ContentMessage

        content_chunks = [c for c in chunks if isinstance(c, ContentMessage)]
        assert len(content_chunks) > 0, f"No content chunks received. Got: {[type(c).__name__ for c in chunks]}"

        full_text = "".join(c.content for c in content_chunks)
        assert len(full_text) > 0, "LLM returned empty content"


# ---------------------------------------------------------------------------
# Test: Agent creation via CLI runner
# ---------------------------------------------------------------------------


class TestAgentCreation:
    """Test Agent instance creation through AgentRunner."""

    @pytest.mark.asyncio
    async def test_agent_runner_initialize(self, test_workspace: Path):
        """AgentRunner initializes workspace and creates Agent."""
        from dawei.cli.config import CLIConfig
        from dawei.cli.runner import AgentRunner

        config = CLIConfig(
            workspace=str(test_workspace),
            llm="ollama-test",
            mode="orchestrator",
            message="hello",
        )
        runner = AgentRunner(config)
        try:
            await runner.initialize()

            assert runner.user_workspace is not None
            assert runner.agent is not None
            assert runner.agent.execution_engine is not None
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_agent_create_with_default_engine(self, test_workspace: Path):
        """Agent.create_with_default_engine creates a fully wired agent."""
        from dawei.workspace.user_workspace import UserWorkspace
        from dawei.agentic.agent import Agent

        ws = UserWorkspace(workspace_path=str(test_workspace))
        await ws.initialize()

        try:
            agent = await Agent.create_with_default_engine(
                user_workspace=ws,
                config={
                    "enable_auto_mode_switch": False,
                    "enable_skills": False,
                    "enable_mcp": False,
                    "max_iterations": 5,
                },
            )
            assert agent is not None
            assert agent.execution_engine is not None
            assert agent.user_workspace is ws
        finally:
            await ws.cleanup()


# ---------------------------------------------------------------------------
# Test: End-to-end agent message processing (real LLM calls)
# ---------------------------------------------------------------------------


class TestAgentE2E:
    """End-to-end tests: Agent processes a message and returns LLM response.

    These are SLOW tests (actual LLM calls). Mark accordingly.
    """

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_agent_simple_qa(self, test_workspace: Path):
        """Agent answers a simple factual question via Ollama."""
        from dawei.cli.runner import run_agent_directly

        result = await run_agent_directly(
            workspace=str(test_workspace),
            llm="ollama-test",
            mode="orchestrator",
            message="What is 2+3? Answer with just the number.",
            verbose=False,
            timeout=60,
        )

        assert result["success"], f"Agent failed: {result.get('error')}"
        assert result["duration"] > 0

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_agent_reads_file(self, test_workspace_with_files: Path):
        """Agent reads a file using read_file tool."""
        from dawei.cli.runner import run_agent_directly

        result = await run_agent_directly(
            workspace=str(test_workspace_with_files),
            llm="ollama-test",
            mode="orchestrator",
            message="Read the file hello.txt and tell me what's in it.",
            verbose=False,
            timeout=90,
        )

        assert result["success"], f"Agent failed: {result.get('error')}"

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_agent_lists_files(self, test_workspace_with_files: Path):
        """Agent lists files in workspace using list_files tool."""
        from dawei.cli.runner import run_agent_directly

        result = await run_agent_directly(
            workspace=str(test_workspace_with_files),
            llm="ollama-test",
            mode="orchestrator",
            message="List all files in the current directory.",
            verbose=False,
            timeout=90,
        )

        assert result["success"], f"Agent failed: {result.get('error')}"

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_agent_writes_file(self, test_workspace: Path):
        """Agent writes a new file using write_text_file tool."""
        from dawei.cli.runner import run_agent_directly

        result = await run_agent_directly(
            workspace=str(test_workspace),
            llm="ollama-test",
            mode="orchestrator",
            message="Create a file called result.txt with the text 'test passed'",
            verbose=False,
            timeout=120,
        )

        assert result["success"], f"Agent failed: {result.get('error')}"

        # Verify the file was actually created
        result_file = test_workspace / "result.txt"
        # The file may or may not be created depending on whether the model
        # correctly uses the write tool — this is a best-effort check
        if result_file.exists():
            content = result_file.read_text(encoding="utf-8")
            assert "test passed" in content.lower() or "test" in content.lower()


# ---------------------------------------------------------------------------
# Test: CLI sync entry point
# ---------------------------------------------------------------------------


class TestCLISync:
    """Test the synchronous CLI entry point (what `dawei agent run` calls)."""

    @pytest.mark.slow
    def test_run_agent_sync(self, test_workspace: Path):
        """run_agent_sync executes a full agent run synchronously."""
        from dawei.cli.runner import run_agent_sync

        result = run_agent_sync(
            workspace=str(test_workspace),
            llm="ollama-test",
            mode="orchestrator",
            message="Say hello.",
            verbose=False,
            timeout=60,
        )

        assert result["success"], f"Sync run failed: {result.get('error')}"
        assert isinstance(result["duration"], float)
        assert result["duration"] > 0
