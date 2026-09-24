# DavyBot

[English](README.md) | [中文](README_CN.md)

DavyBot is an open-source **AI agent engine + desktop/web app core** for building
personal and professional AI assistants. This repository is a component monorepo:

| Path | What | License |
|---|---|---|
| [`engine/`](engine/) | **dawei** — the agent engine (Python 3.12, FastAPI): dialogue, 60+ tools, MCP, skills, TaskGraph orchestration, knowledge base, agent memory. No business logic. | AGPL-3.0-only |
| [`app/`](app/) | Frontend core shell + Tauri desktop host (React 19, Vite 7, Tauri 2.x). Business UI modules (`biz/`) live outside this repo and are assembled at build time. | Apache-2.0 |
| [`scripts/`](scripts/) | Cross-platform build orchestration (desktop / server binary). | Apache-2.0 |

The engine ships as the `davybot` PyPI package with the `dawei` CLI; the desktop
product built from this repo is **NormNomos**.

## Quick start (users)

Requires Python 3.12+:

```bash
pip install davybot        # add extras with: pip install "davybot[all]"
```

### Run modes

The `dawei` CLI supports four ways to run the agent. All of them boot **fully
local with zero cloud config** (local + relay mode, no API keys required).

| # | Mode | Command |
|---|---|---|
| 1 | Web server + Web UI | `dawei server start` |
| 2 | Terminal UI (TUI) | `dawei tui --workspace ./my-ws` |
| 3 | One-shot headless agent | `dawei agent run ./my-ws "your task"` |
| 4 | ACP agent over stdio | `dawei acp serve --workspace ./my-ws` |

#### 1. Web server + Web UI

```bash
dawei server start                    # default 0.0.0.0:8431, Ctrl+C to stop
dawei server start --host 127.0.0.1 --port 8010
dawei server start --password <pw>    # enable access-gate password
dawei server start -d                 # run as daemon

dawei server status                    # check running state
dawei server stop                      # stop the server
```

Open **http://localhost:8431/app-ui/**.

#### 2. Terminal UI

```bash
dawei tui --workspace ./my-ws          # workspace is created if missing
dawei tui -w ./my-ws --llm <model>     # override model (else workspace config)
dawei tui -w ./my-ws --theme dark      # themes: default | dark | light
```

Full-featured terminal interface: interactive chat with autocomplete, real-time
agent thinking display, tool execution tracking, settings, command palette (Ctrl+P).

#### 3. One-shot headless agent

Runs a task directly in-process, bypassing the web server — ideal for scripting
and CI:

```bash
dawei agent run ./my-ws "Create hello world"
dawei agent run ./my-ws "Design API" --mode plan      # modes: orchestrator|plan|do|check|act
dawei agent run ./my-ws "Write report" -o result.txt  # save result to file
dawei agent run ./my-ws "Improve this repo" --evolution   # full PDCA improvement cycle

dawei agent modes                      # list available agent modes
dawei agent validate ./my-ws           # validate workspace configuration
```

#### 4. ACP agent (Agent Client Protocol)

Serves dawei as an ACP agent over stdio for editor/client integration (e.g. Zed),
or calls external ACP-compatible agents:

```bash
dawei acp serve --workspace ./my-ws                    # dawei as ACP server (stdio)
dawei acp call --command codex --prompt "fix the bug"  # invoke external ACP agent
```

### Configuration & data

- Providers and behavior: copy `engine/agent/.env.example` to `.env`
  (4-layer priority: `workspace/.dawei/` > `~/.dawei/` > `/etc/dawei/` > defaults).
- Data home: `~/.normnomos/` (override with `DAWEI_HOME`).
- Releases: `v*` tags are published to PyPI as the `davybot` wheel
  (`pip install -U davybot`), smoke-tested before upload. Desktop/server-binary
  builds remain available locally via `scripts/`.
- Go deeper: [engine/README.md](engine/README.md) (skills/agents marketplace, IM
  integrations), user guides under [engine/docs/user/](engine/docs/user/).

## Quick start (developers)

Prerequisites: Python 3.12+, Node 20+, Rust toolchain (desktop only). Full setup,
test, and CI policy in [CONTRIBUTING.md](CONTRIBUTING.md).

**Engine** — `engine/agent/`:

```bash
cd engine/agent
uv pip install --system -e ".[dev]"       # or: pip install -e ".[dev]"

dawei server start --host 127.0.0.1 --port 8010 --reload

pytest -m unit -q                          # unit tests
ruff check dawei/ && mypy dawei/           # lint + types
```

**App** — `app/`:

```bash
cd app
npm ci
npm run dev            # web dev server, proxies to the engine
npm run dev:desktop    # Tauri desktop shell (needs Rust toolchain)
npm run ci             # lint + typecheck + vitest + core build
```

Production build for server-embedded mode: `npm run build:server`
(output staged into `engine/agent/dawei/frontend/`).

**Desktop / server binary builds**:

```bash
# Full desktop build (frontend + sidecar + Tauri), Linux/macOS:
bash scripts/build-desktop.sh all

# Windows:
powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1 all

# Standalone single-file server binary (PyInstaller):
bash scripts/build-server-binary.sh
```

Push-blocking gates (see CONTRIBUTING): cloud-default guard, tool-system gate,
app biz-isolation guard.

## CI

`.github/workflows/` runs a zero-external-service matrix on every push/PR:

- **engine**: cloud-default guard (fail on any hardcoded cloud endpoint), tool-system gate, unit tests
- **cli**: `dawei` / `server` / `tui` smoke
- **app**: lint + typecheck + vitest (incl. biz-isolation guard) + core build
- **server-smoke**: cold boot with **no cloud env** → must report `local` + `[relay]`

Tag builds (`v*`) publish the `davybot` wheel to PyPI ([pypi.yml](.github/workflows/pypi.yml)):
frontend build → wheel → zero-cloud smoke test → upload (existing `PYPI_API_TOKEN`) + GitHub Release.

## License

Dual license by directory — see [LICENSE.md](LICENSE.md):

- `engine/` → **AGPL-3.0-only** ([engine/LICENSE](engine/LICENSE))
- `app/`, `scripts/`, root files → **Apache-2.0** ([app/LICENSE](app/LICENSE))
