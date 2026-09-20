# DavyBot — License

Copyright 2025 格律至微 (GeLvZhiWei)

This repository is dual-licensed **by directory**. The license of a file is
determined by its location:

| Scope | License | SPDX | Full text |
|---|---|---|---|
| `engine/` (the `dawei` agent engine) | GNU Affero General Public License v3.0 only | `AGPL-3.0-only` | [engine/LICENSE](engine/LICENSE) |
| `app/` (frontend core shell + Tauri host) | Apache License 2.0 | `Apache-2.0` | [app/LICENSE](app/LICENSE) |
| `scripts/`, `.github/`, root-level files (incl. this file) | Apache License 2.0 | `Apache-2.0` | [app/LICENSE](app/LICENSE) |

Notes:

- The engine is licensed **AGPL-3.0-only** (no "or later" option). Section 13
  (network interaction) applies to modified versions offered over a network.
- The app core shell is deliberately permissive (Apache-2.0) so that separately
  licensed business UI modules may be assembled into the same SPA by the
  publisher — see [app/NOTICE](app/NOTICE).
- Code must not be copied from `engine/` into `app/`, `scripts/` or any
  Apache-2.0 scope (that would relicense AGPL-derived code). The Apache → AGPL
  direction is permitted.
- No CLA is required; contributions are accepted under the per-directory
  license (see [CONTRIBUTING.md](CONTRIBUTING.md)).
