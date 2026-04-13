# Dawei Agent Instructions

## Project Structure

```
davybot-pro/
├── agent/           # Python backend (FastAPI, UV)
├── webui/           # Vue 3 frontend (pnpm, Tauri)
├── deps/            # External deps (drawio)
├── scripts/         # Build scripts
└── docs/            # Architecture & development docs
```

## Developer Commands

### Backend (Python)
```bash
cd agent

# Install deps
uv pip install -e ".[dev]"

# Run server (port 8465)
dawei server start --reload

# CLI alternatives
python -m dawei.cli.dawei server start

# Lint & type check (CI order)
ruff format --check dawei/
ruff check dawei/
mypy dawei/

# Tests (markers: unit, integration)
pytest -m unit -v
pytest -m integration -v
pytest tests/test_specific.py -v
```

### Frontend (Vue 3/TypeScript)
```bash
cd webui

# Install deps
pnpm install

# Dev server (port 5173)
pnpm dev

# Build (requires drawio preparation)
pnpm build
bash scripts/prepare-drawio.sh  # Must run before build/dev

# Lint & type check
pnpm lint
pnpm type-check

# Tests
pnpm test              # Vitest (unit)
pnpm test:coverage
pnpm test:e2e          # Playwright (requires install)
pnpm test:e2e:install
```

## Important Quirks

1. **drawio preparation**: `bash scripts/prepare-drawio.sh` must run before `pnpm dev` or `pnpm build` to copy resources from `deps/drawio/`

2. **Backend tests disabled in CI**: Tests are `if: false` in backend-ci.yml. Run manually with `pytest`.

3. **4-layer config priority** (highest to lowest):
   - `workspace/.dawei/` > `~/.dawei/` > `/etc/dawei/` > `dawei/`

4. **Python runtime**: Backend uses Python 3.12+ with UV embedded in standalone builds

5. **Tauri config**: `beforeDevCommand: "pnpm dev"` means Tauri dev waits for frontend dev server

## Architecture Notes

- **Entry points**: `dawei` CLI (`agent/dawei/cli/dawei.py`), FastAPI server (`server_app.py`)
- **Core modules**: `agentic/` (Agent), `task_graph/` (TaskEngine), `tools/` (60+ tools), `llm_api/` (multi-provider)
- **PDCA modes**: orchestrator → plan → do → check → act
- **Skills**: Markdown-based, lazy-loaded, stored in `.dawei/skills/`

## Key Files

- `agent/pyproject.toml` - Backend deps, ruff config, package setup
- `webui/package.json` - Frontend deps, pnpm scripts
- `webui/src-tauri/Cargo.toml` - Tauri/Rust deps
- `.env.example` - All environment variables
- `docs/architecture/README.md` - Full architecture docs

## CI Commands

Backend: `ruff format --check` → `mypy` → `pytest` (disabled)
Frontend: `pnpm lint` → `pnpm type-check` → `pnpm test`

## Style Conventions

- Python: Ruff (line-length 320, indent 4), no docstring requirements (D100-D107 ignored)
- Frontend: ESLint + Prettier, Vue 3 Composition API
