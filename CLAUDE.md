# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Dawei (davybot) is an AI personal assistant with a Python/FastAPI backend and Vue 3/Tauri frontend. It features a PDCA-mode agent system (orchestrator → plan → do → check → act), 60+ custom tools, 61 WebSocket message types, and a skills marketplace.

## Repository Layout

- `agent/` — Python backend (`dawei` package), FastAPI server, CLI entry point
- `webui/` — Vue 3 frontend with Tauri 2.x desktop shell
- `deps/` — External dependencies (drawio assets)
- `scripts/` — Build scripts for all platforms
- `docs/` — Architecture and user documentation

## Development Commands

### Backend (from `agent/` directory)

```bash
uv pip install -e ".[dev]"          # Install with dev dependencies
dawei server start --reload         # Run server on port 8465
python -m dawei.cli.dawei server start  # Alternative entry point

# Linting & type checking (CI runs these in order)
ruff format --check dawei/
ruff check dawei/
mypy dawei/

# Testing (pytest with markers: unit, integration)
pytest -m unit -v                   # Unit tests only
pytest -m integration -v            # Integration tests only
pytest tests/test_specific.py -v    # Single test file
```

### Frontend (from `webui/` directory)

```bash
pnpm install                        # Install dependencies
bash scripts/prepare-drawio.sh      # MUST run before dev or build
pnpm dev                            # Dev server on port 5173
pnpm build                          # Production build

# Linting & type checking
pnpm lint
pnpm type-check

# Testing
pnpm test                           # Vitest unit tests
pnpm test:coverage
pnpm test:e2e                       # Playwright (run pnpm test:e2e:install first)
```

## Architecture

7-layer system: UI → Communication → Agent → Tool → LLM → Data → Infrastructure.

**Backend core modules** (`agent/dawei/`):
- `agentic/` — Core Agent class and task orchestration
- `task_graph/` — TaskGraph engine for multi-step workflows
- `tools/` — 60+ tool classes organized in 4 layers (builtin → system → user → workspace)
- `llm_api/` — Multi-provider LLM support with model routing and circuit breaker
- `mode/` — PDCA mode system (orchestrator, plan, do, check, act)
- `workspace/` — User workspace and project management
- `conversation/` — Conversation state management
- `knowledge/` — Knowledge base with embeddings, retrieval, and graph
- `channels/` — IM integrations (Feishu, WeChat, Slack, Telegram, Discord, etc.)
- `websocket/` — Real-time communication (61 message types)
- `memory/` — Agent memory system
- `storage/` — Storage abstraction layer
- `market/` — Skills and agent marketplace integration
- `plugins/` — Plugin system (ToolPlugin, ServicePlugin base classes)

**Entry points**: CLI at `agent/dawei/cli/dawei.py`, server at `agent/dawei/server_app.py`.

**Frontend**: Vue 3 Composition API with Element Plus UI, CodeMirror editor, auto-imports for Vue APIs/components.

## Key Patterns

- **Skills**: Markdown-based, lazy-loaded, stored in `.dawei/skills/`. Marketplace at davybot.com/market/skills.
- **4-layer config priority** (highest → lowest): `workspace/.dawei/` > `~/.dawei/` > `/etc/dawei/` > package defaults
- **Lazy imports**: Common pattern to avoid circular dependencies — many modules import at function scope
- **Versioning**: `setuptools_scm` with git tags (scheme: `no-guess-dev`, fallback: `0.1.3`)

## Code Style

- **Python**: Ruff with line-length 320, indent 4, target py312. No docstring requirements (D100-D107 ignored). Many ruff rules suppressed for legacy/complex code — see `pyproject.toml [tool.ruff.lint.ignore]`.
- **Frontend**: ESLint + Prettier, Vue 3 Composition API with `<script setup lang="ts">`
- **Language**: Code comments and UI strings use both English and Chinese (primary audience is Chinese-speaking)

## CI Notes

- Backend tests are **disabled** in CI (`if: false` in backend-ci.yml) — run manually
- Frontend CI: lint → type-check → test
- Tauri builds target Linux x86_64, macOS (x86_64 + aarch64), Windows x86_64
- Python 3.12+ required (standalone builds use UV embedded runtime)
