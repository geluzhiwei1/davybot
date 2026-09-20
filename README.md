# DavyBot

[English](README.md) | [中文](#中文导览)

DavyBot is an open-source **AI agent engine + desktop/web app core** for building
personal and professional AI assistants. This repository is a component monorepo:

| Path | What | License |
|---|---|---|
| [`engine/`](engine/) | **dawei** — the agent engine (Python 3.12, FastAPI): dialogue, 60+ tools, MCP, skills, TaskGraph orchestration, knowledge base, agent memory. No business logic. | AGPL-3.0-only |
| [`app/`](app/) | Frontend core shell + Tauri desktop host (React 19, Vite 7, Tauri 2.x). Business UI modules (`biz/`) live outside this repo and are assembled at build time. | Apache-2.0 |
| [`scripts/`](scripts/) | Cross-platform build orchestration (desktop / server binary). | Apache-2.0 |

The engine ships as the `davybot` PyPI package with the `dawei` CLI; the desktop
product built from this repo is **NormNomos**.

## Quick start (engine)

```bash
cd engine/agent
uv pip install --system -e ".[dev]"   # or: pip install -e ".[dev]"

dawei server start --host 127.0.0.1 --port 8010
# Web UI: http://localhost:8010/app-ui/
```

The server boots **fully local** with zero cloud configuration (no API keys
required for the relay-capable local mode). Copy `engine/agent/.env.example`
to `.env` to configure providers.

## Quick start (app)

```bash
cd app
npm ci
npm run dev            # Vite dev server, proxies to the engine
npm run dev:desktop    # Tauri desktop shell (needs Rust toolchain)
```

Production build for server-embedded mode: `npm run build:server`
(output staged into `engine/agent/dawei/frontend/`).

## Desktop / server binary builds

```bash
# Full desktop build (frontend + sidecar + Tauri), Linux/macOS:
bash scripts/build-desktop.sh all

# Windows:
powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1 all

# Standalone single-file server binary (PyInstaller):
bash scripts/build-server-binary.sh
```

## CI

`.github/workflows/` runs a zero-external-service matrix on every push/PR:

- **engine**: cloud-default guard (fail on any hardcoded cloud endpoint), tool-system gate, unit tests
- **cli**: `dawei` / `server` / `tui` smoke
- **app**: lint + typecheck + vitest (incl. biz-isolation guard) + core build
- **server-smoke**: cold boot with **no cloud env** → must report `local` + `[relay]`

Tag builds (`v*`) additionally produce desktop installers and the server binary.

## License

Dual license by directory — see [LICENSE.md](LICENSE.md):

- `engine/` → **AGPL-3.0-only** ([engine/LICENSE](engine/LICENSE))
- `app/`, `scripts/`, root files → **Apache-2.0** ([app/LICENSE](app/LICENSE))

---

## 中文导览

DavyBot = 开源 AI Agent 引擎（`engine/`，AGPL-3.0）+ 桌面/Web 前端核心壳（`app/`，Apache-2.0）。

- 引擎快速启动：`cd engine/agent && uv pip install --system -e ".[dev]" && dawei server start`
- 前端开发：`cd app && npm ci && npm run dev`
- 桌面打包：`bash scripts/build-desktop.sh all`（Windows 用 `scripts/build-desktop.ps1`）
- 引擎详细文档见 [engine/README_CN.md](engine/README_CN.md)；参与贡献见 [CONTRIBUTING.md](CONTRIBUTING.md)

服务器零云配置即可冷启（本地 + relay 模式）；CI 对「代码内出现云默认地址」直接判负。
