# Contributing to DavyBot

Thanks for contributing! This repo is a two-component monorepo with **different
licenses per directory** — read the license section below before submitting.

## Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.12 | engine |
| [uv](https://docs.astral.sh/uv/) | latest | engine env & binary builds |
| Node.js | 20.19.0 | app |
| Rust (stable) | — | Tauri desktop builds (optional) |

## Layout

```
engine/agent/   dawei — Python agent engine (FastAPI, CLI: dawei)
app/            React 19 core shell + Tauri host (no biz/ modules here)
scripts/        desktop / server-binary build orchestration
.github/        CI matrix (the only CI source of truth in this repo)
```

## Engine development (`engine/agent/`)

```bash
uv pip install --system -e ".[dev]"

ruff format --check dawei/ && ruff check dawei/   # lint (line-length 320)
mypy dawei/

pytest -m unit -q                                 # unit tests
pytest -m integration -v                          # needs a running server
dawei server start --host 127.0.0.1 --port 8010   # dev server
```

### Hard gates (CI-blocking)

1. **Cloud-default guard** — `tests/unit/test_no_cloud_defaults.py` fails if any
   cloud endpoint appears as a hardcoded default in code. The engine must boot
   fully local with zero cloud env.
2. **Tool system gate** — `tests/test_tool_contract.py`,
   `tests/test_tool_system_health.py`, `tests/test_smart_file_edit.py`.
3. `ruff format` / `mypy` / full unit suite currently run **non-blocking**
   (legacy environment-dependent failures are being triaged) — don't add new
   failures.

### Environment files

Never commit real `.env` values. Only `*.example` templates belong in git.
Configure via `engine/agent/.env.example` → `.env`.

## App development (`app/`)

```bash
npm ci
npm run dev              # web dev server
npm run dev:desktop      # Tauri shell
npm run ci:lint          # ESLint gate (same as CI)
npm run ci:typecheck     # tsc --noEmit
npm run ci:test          # vitest (includes biz-isolation guard)
npm run build:server     # production build for server-embedded mode
```

**biz-isolation guard**: `src/lib/biz-isolation.test.ts` fails if core code
imports from `biz/`. Business modules are assembled from outside this repo at
build time; the in-tree `biz-registry.ts` is intentionally an empty table.

## Desktop / binary builds

Use the canonical entry points — they handle frontend staging, mode stamping
(`DAWEI_RUNTIME_MODE`), version injection and smoke checks:

```bash
bash scripts/build-desktop.sh all        # frontend + sidecar + Tauri
bash scripts/build-server-binary.sh      # PyInstaller single-file server
```

## CI policy

See `.github/workflows/ci.yml`. In short: **blocking** = cloud-default guard,
tool-system gate, app lint/typecheck/test/build, zero-cloud server smoke;
**non-blocking** = full unit suite, ruff format, mypy.

## License

By submitting a contribution you agree it is licensed under the license of the
directory it modifies:

- `engine/` → **AGPL-3.0-only** — copyleft, including §13 network clause
- `app/`, `scripts/`, `.github/`, root files → **Apache-2.0**

See [LICENSE.md](LICENSE.md). Don't copy code between `engine/` and `app/`
without considering the license boundary (Apache → AGPL direction is fine;
the reverse is not).
