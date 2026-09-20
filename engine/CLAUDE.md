# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**nn-bot (dawei) — AI Agent Engine for DavyBot Legal Agent OS.**

Pure Agent platform: dialogue, tool execution, MCP integration, skill management, and TaskGraph orchestration. **No business logic lives here** — contracts, regulatory intelligence, and AI governance belong in separate projects.

## Cross-Project Boundaries

| In this project | In sanctions-knowledge (external) | In legal-oa-system (Phase 2) |
|---|---|---|
| Agent engine + TaskGraph | Entity search/graph API | Contract CRUD + review |
| MCP tool integration | Data import + sync | Regulatory intelligence |
| Skill packs (SKILL.md) | Dashboard stats API | AI governance |
| Sanctions frontend pages | Screen endpoint | Negotiation workflow |
| Legal domain knowledge | CORS for this frontend | PostgreSQL + Vue 3 Web |

Frontend sanctions pages call `sanctions-knowledge API :8012` directly — no proxy through dawei.

## Development Commands

### Backend (from `agent/` directory)

```bash
uv pip install -e ".[dev]"          # Install with dev dependencies
dawei server start --reload         # Run server on port 8010
python -m dawei.cli.dawei server start  # Alternative entry point

# Linting & type checking
ruff format --check dawei/          # Format check (line-length 320)
ruff check dawei/                   # Lint
ruff check --fix dawei/             # Auto-fix
mypy dawei/                         # Type check

# Testing (pytest markers: unit, integration, slow)
pytest -m unit -v                   # Unit tests only
pytest -m integration -v            # Integration tests only
pytest -m slow -v                   # Slow tests (LLM calls, network)
pytest tests/test_specific.py -v    # Single test file
```

### Frontend (from `webui/` directory)

```bash
pnpm install                        # Install dependencies
bash scripts/prepare-drawio.sh      # MUST run before dev or build
pnpm dev                            # Dev server on port 5173 (strictPort)
pnpm build                          # Production build → src-tauri/resources/

# Linting & type checking
pnpm lint                           # ESLint (max-warnings 1000)
pnpm type-check                     # Vue TSC

# Testing
pnpm test                           # Vitest unit tests
pnpm test:coverage                  # With coverage (80% threshold)
pnpm test:e2e                       # Playwright (run pnpm test:e2e:install first)
```

## Architecture

7-layer system: UI -> Communication -> Agent -> Tool -> LLM -> Data -> Infrastructure.

### Backend modules (`agent/dawei/`)

| Module | Purpose |
|--------|---------|
| `agentic/` | Core Agent class, TaskGraphExecutor (DAG orchestration), TaskNodeExecutor |
| `task_graph/` | TaskGraph engine — TaskNode, TaskData, TaskValidator, persistence |
| `tools/` | 60+ tool classes in 4 layers (builtin -> system -> user -> workspace) |
| `llm_api/` | Multi-provider LLM with model routing, circuit breaker, rate limiter, request queue |
| `mode/` | PDCA mode system (orchestrator, plan, do, check, act) |
| `workspace/` | User workspace management (105KB — largest file: `user_workspace.py`) |
| `websocket/` | Real-time communication, 61 message types (protocol.py) |
| `knowledge/` | Knowledge base: embeddings (sqlite-vec), fulltext (SQLite FTS), graph, retrieval, domains |
| `channels/` | 9 IM integrations (Feishu, WeChat, QQ, DingTalk, Telegram, Discord, Slack, Signal, iMessage) |
| `memory/` | DaweiMem agent memory system |
| `config/` | 18+ Pydantic Settings classes aggregated into singleton `get_settings()` |
| `core/` | EventBus, DI container, ErrorHandler, SecurityManager |
| `plugins/` | Plugin system (ToolPlugin, ServicePlugin base classes) |
| `prompts/` | Jinja2 template system for LLM messages |
| `sandbox/` | Command whitelist validation for shell execution |

### Entry points

- **CLI**: `agent/dawei/cli/dawei.py` (Click-based: `server`, `tui`, `agent`, `gui`, `acp` commands)
- **Server**: `agent/dawei/server_app.py` — `create_app()` factory, FastAPI with 16 routers, frontend mounted at `/app`
- **Package init**: `agent/dawei/__init__.py` — `get_dawei_home()`, dotenv loading, version

### Tool system

4-layer discovery: `builtin -> system -> user -> workspace`. Key files:
- `tools/tool_manager.py` — Tool discovery and registration
- `tools/tool_executor.py` — Execution engine
- `tools/custom_tools/` — 22 tool classes (Read, Edit, Command, MCP, Workflow, Knowledge, Docx, Cost, Timer)
- `tools/mcp_tool_manager.py` — MCP integration using `mcp` Python SDK, 2-level config (workspace > user)
- `tools/magic_manager.py` — Jupyter-style magic commands (`!`, `%%bash`, `%time`)
- `tools/skill_manager.py` — Progressive skill loading (Discovery -> Instructions -> Resources)

### Frontend

Vue 3 Composition API + Element Plus + CodeMirror 6. Auto-imports for Vue APIs and Element Plus components via `unplugin-auto-import`. Vite config:
- Dev server on port **5173** (strictPort), proxies `/api` and `/ws` to backend `:8010`
- Manual chunk splitting for vendor libs (16 chunks)
- Drawio middleware for serving drawio files from `public/drawio/`

**ESLint rules**: `fetch` is blocked (must use `httpClient`), `axios` import blocked (must use `httpClient`), underscore-prefixed unused vars allowed as warnings.

## Key Patterns

- **DAWEI_HOME**: Default `~/.normnomos` (env var `DAWEI_HOME`). Subdirs: `checkpoints/`, `sessions/`, `logs/`, `configs/`
- **4-layer config priority** (highest -> lowest): `workspace/.dawei/` > `~/.dawei/` > `/etc/dawei/` > package defaults
- **Lazy imports**: Common pattern to avoid circular dependencies — many modules import at function scope
- **Versioning**: `setuptools_scm` with git tags (scheme: `no-guess-dev`, fallback: `0.1.3`)
- **Skills**: Markdown-based (SKILL.md with YAML frontmatter), lazy-loaded from `.dawei/skills/`

## Code Style

- **Python**: Ruff, line-length 320, indent 4, target py312. No docstring requirements (D100-D107, ANN all ignored). Many rules suppressed for legacy code — see `agent/pyproject.toml [tool.ruff.lint.ignore]`.
- **Frontend**: ESLint + Prettier (semi: false, singleQuote: true, printWidth: 100). TypeScript with relaxed config (`strict: false`, `noImplicitAny: false`).
- **Language**: Code comments and UI strings use both English and Chinese

## CI Notes

- Backend lint runs in CI but is **non-blocking** (`|| true`) — `ruff format --check` and `mypy` never fail CI
- Backend tests re-enabled (2026-09): **tool system gate is blocking** (`tests/test_tool_contract.py`, `tests/test_tool_system_health.py`, `tests/test_smart_file_edit.py`); full unit/integration suites run **non-blocking** (`|| true`) until legacy env-dependent failures are triaged
- Tool system diagnostics: `uv run python scripts/audit_tool_system.py` (from `agent/`, repeatable)
- Frontend CI: lint (max-warnings 1000) -> type-check -> test
- E2E test directory exists but is currently empty
- Tauri builds target Linux x86_64, macOS (x86_64 + aarch64), Windows x86_64
