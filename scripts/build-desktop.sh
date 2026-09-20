#!/usr/bin/env bash
# Full NormNomos Desktop build: sidecar + Tauri + updater signing.
# Must run from repo root on the target platform (or use --target for explicit override).
#
# Usage:
#   bash scripts/build-desktop.sh                          # full build: frontend + sidecar + tauri (all targets)
#   bash scripts/build-desktop.sh --target aarch64-apple-darwin  # single target
#   bash scripts/build-desktop.sh sidecar                  # sidecar only
#   bash scripts/build-desktop.sh tauri                    # tauri only (assumes sidecar + frontend exist)
#   bash scripts/build-desktop.sh all                      # full build (frontend + sidecar + tauri, all targets)
#
# Environment variables (for CI signing):
#   TAURI_SIGNING_PRIVATE_KEY         Ed25519 private key for updater signing
#   TAURI_SIGNING_PRIVATE_KEY_PASSWORD Optional password for the key
#   APPLE_SIGNING_IDENTITY            macOS codesign identity (e.g. "Developer ID Application: ...")
#   APPLE_ID / APPLE_PASSWORD / APPLE_TEAM_ID  for notarization (optional)
set -euo pipefail

# Colors & logging helpers
C_RESET='\033[0m'; C_BOLD='\033[1m'; C_RED='\033[0;31m'; C_GREEN='\033[0;32m'; C_YELLOW='\033[1;33m'; C_BLUE='\033[0;34m'
info() { echo -e "     $*"; }
ok()   { echo -e "  ${C_GREEN}OK${C_RESET} $*"; }
warn() { echo -e "  ${C_YELLOW}WARN${C_RESET} $*"; }
err()  { echo -e "  ${C_RED}ERROR${C_RESET} $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"            # davybot/ (单仓: engine/ + app/ + scripts/)
TAURI_DIR="$REPO_ROOT/app"                           # app/ (前端核心壳)
BUNDLE_DIR="$TAURI_DIR/src-tauri/target/release/bundle"
AGENT_DIR="$REPO_ROOT/engine/agent"                  # engine/agent

# ---- Resolve version from setuptools_scm (single source of truth) ----
# Converts PEP 440 (Python) → semver (Cargo/Tauri):
#   0.3.0           → 0.3.0            (release)
#   0.3.0a1         → 0.3.0-alpha.1    (alpha)
#   0.3.0b2         → 0.3.0-beta.2     (beta)
#   0.3.0rc1        → 0.3.0-rc.1       (release candidate)
#   0.2.11.post1.dev37 → 0.2.11-post.1.dev.37  (converts post/dev to semver pre-release)
resolve_version() {
    local version
    # git describe: v0.2.11-44-g326ada4 → 0.2.11-post.1.dev.44
    #                v0.2.11-0-gxxx       → 0.2.11 (release, exact tag)
    version=$(cd "$AGENT_DIR" && git describe --tags --long 2>/dev/null | sed -E '
        s/^v//
        # exact tag: 0.2.11-0-gxxx → 0.2.11
        /-0-g[0-9a-f]+$/{ s/-0-g[0-9a-f]+$//; b }
        # dev: 0.2.11-44-gxxx → 0.2.11-post.1.dev.44
        s/-([0-9]+)-g[0-9a-f]+$/-post.1.dev.\1/
    ')

    if [[ -z "$version" ]]; then
        echo "WARN: Could not resolve version from git, using 0.0.0" >&2
        version="0.0.0"
    fi
    echo "$version"
}

# ---- Inject version into Tauri config files ----
# In-place injection with backup + restore-on-exit: the build sees the right
# version, but the working tree stays clean afterwards (no accidental version
# diffs or jq-reformatted JSON to commit). Same approach as mac-build-and-sign.sh.
# Portable sed -i: macOS needs '' argument, Linux doesn't
_sed_inplace() { sed -i '' "$@" 2>/dev/null || sed -i "$@"; }

inject_version() {
    local version="$1"
    echo "     Version: $version"

    local conf="$TAURI_DIR/src-tauri/tauri.conf.json"
    local cargo="$TAURI_DIR/src-tauri/Cargo.toml"

    # Backup originals once (kept if a previous run crashed); trap restores.
    local f
    for f in "$conf" "$cargo"; do
        [[ -f "$f.build-bak" ]] || cp "$f" "$f.build-bak"
    done

    # tauri.conf.json — prefer jq for safe JSON editing; mktemp (NOT a fixed
    # /tmp name — predictable temp files are a symlink/race hazard)
    if command -v jq &>/dev/null; then
        local tmp
        tmp=$(mktemp)
        jq --arg v "$version" '.version = $v' "$conf" > "$tmp" && mv "$tmp" "$conf"
    else
        _sed_inplace "s/\"version\": \"[^\"]*\"/\"version\": \"$version\"/" "$conf"
    fi

    # Cargo.toml — match version = "..." including pre-release suffixes
    _sed_inplace "s/^version = \"[^\"]*\"/version = \"$version\"/" "$cargo"

    echo "     Injected into tauri.conf.json, Cargo.toml (auto-restored on exit)"
}

restore_version_files() {
    local f
    for f in "$TAURI_DIR/src-tauri/tauri.conf.json" "$TAURI_DIR/src-tauri/Cargo.toml"; do
        [[ -f "$f.build-bak" ]] && mv "$f.build-bak" "$f"
    done
}
trap restore_version_files EXIT

# ---- Detect platform target triple ----
detect_target() {
    local os arch
    case "$(uname -s)" in
        Linux)   os="unknown-linux-gnu" ;;
        Darwin)  os="apple-darwin" ;;
        MINGW*|MSYS*|CYGWIN*) os="pc-windows-msvc" ;;
        *) err "unsupported OS: $(uname -s)"; exit 1 ;;
    esac
    arch="$(uname -m)"
    case "$arch" in
        x86_64|amd64) arch="x86_64" ;;
        aarch64|arm64) arch="aarch64" ;;
        *) err "unsupported arch: $arch"; exit 1 ;;
    esac
    echo "${arch}-${os}"
}

# ---- Resolve build command for target ----
resolve_build_cmd() {
    local target="$1"
    case "$target" in
        x86_64-unknown-linux-gnu)  echo "npm run package:linux" ;;
        aarch64-unknown-linux-gnu) echo "npm run package:linux" ;;
        aarch64-apple-darwin)      echo "npm run package:macos" ;;
        x86_64-apple-darwin)       echo "npm run package:macos-x86_64" ;;
        x86_64-pc-windows-msvc)    echo "npm run package:windows" ;;
        *) err "no package script for target: $target"; exit 1 ;;
    esac
}

# ---- Resolve all build targets (multi-platform on macOS) ----
resolve_targets() {
    if [[ -n "$TARGET_OVERRIDE" ]]; then
        echo "$TARGET_OVERRIDE"
        return
    fi
    case "$(uname -s)" in
        Darwin)
            # Build both Apple Silicon + Intel Mac by default
            case "$(uname -m)" in
                arm64|aarch64) echo "aarch64-apple-darwin x86_64-apple-darwin" ;;
                x86_64)        echo "x86_64-apple-darwin aarch64-apple-darwin" ;;
            esac
            ;;
        *)
            detect_target
            ;;
    esac
}

# ---- Check macOS build prerequisites ----
check_macos_prereqs() {
    local target="$1"
    if [[ "$target" != *apple-darwin* ]]; then
        return
    fi

    info "Checking macOS build prerequisites..."

    # Check Rust target is installed
    if ! rustup target list --installed 2>/dev/null | grep -q "$target"; then
        warn "Rust target '$target' not installed. Installing..."
        rustup target add "$target"
    fi
    ok "Rust target: $target"

    # Check codesign availability
    if [[ -n "${APPLE_SIGNING_IDENTITY:-}" ]]; then
        if security find-identity -v -p codesigning | grep -q "$APPLE_SIGNING_IDENTITY"; then
            ok "Codesign identity found: $APPLE_SIGNING_IDENTITY"
        else
            warn "APPLE_SIGNING_IDENTITY set but not found in keychain: $APPLE_SIGNING_IDENTITY"
        fi
    else
        warn "APPLE_SIGNING_IDENTITY not set — build will be unsigned"
    fi
}

# ---- Build frontend (nn-bot-app → dawei/frontend/) ----
build_frontend() {
    info "${C_BOLD}Building frontend (nn-bot-app web SPA)...${C_RESET}"
    cd "$TAURI_DIR"

    # Install deps if needed
    if [[ ! -d "node_modules" ]]; then
        info "Installing frontend dependencies..."
        npm install
    fi

    # Build pure web SPA for server-embedded mode (uses vite.config.ts, base: /app-ui/)
    # --mode server loads .env.server (empty API/WS URLs → runtime derives from window.location)
    npm run build:server

    local frontend_dist="$TAURI_DIR/dist"
    if [[ ! -d "$frontend_dist" ]]; then
        err "Frontend build failed: $frontend_dist not found"
        exit 1
    fi

    # Copy into dawei package so PyInstaller can bundle it
    local target_frontend="$AGENT_DIR/dawei/frontend"
    rm -rf "$target_frontend"
    cp -r "$frontend_dist" "$target_frontend"

    ok "Frontend bundled: $target_frontend ($(du -sh "$target_frontend" | cut -f1))"
}

# ---- Env 一致性校验 + 产物盖戳 (多模式统一方案 §L1, keep in sync with build-saas.sh) ----
# desktop 构建配了 saas/server 的 env 文件 → FAST FAIL。
check_runtime_mode_env() {
    local f="$1" want="$2" got
    [[ -f "$f" ]] || return 0
    got="$(grep -E '^[[:space:]]*DAWEI_RUNTIME_MODE[[:space:]]*=' "$f" | tail -1 | cut -d= -f2- || true)"
    if [[ -z "$got" ]]; then
        warn "$f 未声明 DAWEI_RUNTIME_MODE (建议补, 见 .env.desktop.*.example)"
        return 0
    fi
    got="${got%%#*}"
    got="${got//\"/}"
    got="${got//\'/}"
    got="$(echo "$got" | tr -d '[:space:]')"
    if [[ "$got" != "$want" ]]; then
        err "$f 声明 DAWEI_RUNTIME_MODE=$got, 与目标模式 '$want' 不符 (多模式统一方案 §L1)"
        exit 1
    fi
    ok "$f DAWEI_RUNTIME_MODE=$got"
}

check_mode_env() {
    info "${C_BOLD}Checking runtime-mode env consistency (desktop)...${C_RESET}"
    local f
    for f in .env.desktop .env.desktop.dev .env.desktop.prod; do
        check_runtime_mode_env "$AGENT_DIR/$f" desktop
    done
}

# ---- Build sidecar ----
build_sidecar() {
    local step_num="${1:-1}"
    info "[$step_num] ${C_BOLD}Building sidecar (PyInstaller)...${C_RESET}"
    cd "$AGENT_DIR"

    check_mode_env

    # Delegate to the canonical builder (same one build-desktop.ps1 /
    # mac-build-and-sign.sh / CI use): HIDDEN_IMPORTS + --collect-all dawei is a
    # strict superset of the bare-call --add-data list (verified via build TOC),
    # and picks up dawei/frontend/ automatically when build_frontend populated it.
    # --runtime-mode desktop: 产物盖戳 — 桌面包只允许 desktop 模式 (FAST FAIL)。
    uv run --python 3.12 --with pyinstaller python scripts/build-binary.py --clean --runtime-mode desktop

    local bin="$AGENT_DIR/dist/dawei"
    [[ -f "$bin.exe" ]] && bin="$bin.exe"
    ok "$bin ($(du -h "$bin" | cut -f1))"
}

# ---- Copy sidecar to Tauri binaries ----
copy_sidecar() {
    local target_triple="$1"
    local agent_dist="$AGENT_DIR/dist"
    local native_triple
    native_triple="$(detect_target)"

    # Pick the right binary: cross-arch if available, otherwise native
    local sidecar_bin=""
    if [[ "$target_triple" != "$native_triple" ]] && [[ "$target_triple" == *apple-darwin* ]]; then
        local cross_arch=""
        case "$target_triple" in
            x86_64-*) cross_arch="x86_64" ;;
            aarch64-*) cross_arch="arm64" ;;
        esac
        sidecar_bin="$agent_dist/dawei-${cross_arch}"
    fi

    # Fall back to native binary
    if [[ -z "$sidecar_bin" ]] || [[ ! -f "$sidecar_bin" ]]; then
        sidecar_bin="$agent_dist/dawei"
        [[ -f "$sidecar_bin.exe" ]] && sidecar_bin="$sidecar_bin.exe"
        if [[ "$target_triple" != "$native_triple" ]]; then
            warn "No cross-compiled sidecar for $target_triple — using native binary (won't run on real Intel Mac)"
        fi
    fi

    if [[ ! -f "$sidecar_bin" ]]; then
        err "Sidecar binary not found. Run 'bash scripts/build-server-binary.sh' first."
        exit 1
    fi

    local ext=""
    [[ "$target_triple" == *windows* ]] && ext=".exe"

    local dest="$TAURI_DIR/src-tauri/binaries/dawei-${target_triple}${ext}"
    mkdir -p "$(dirname "$dest")"

    info "[2/4] ${C_BOLD}Copying sidecar${C_RESET}: $(basename "$sidecar_bin") -> dawei-${target_triple}${ext}"
    cp "$sidecar_bin" "$dest"
    chmod +x "$dest" 2>/dev/null || true
    ok "$dest ($(du -h "$dest" | cut -f1))"
}

# ---- Cross-compile sidecar via Rosetta (macOS only) ----
build_sidecar_cross() {
    local target_triple="$1"
    local native_triple
    native_triple="$(detect_target)"

    [[ "$target_triple" == "$native_triple" ]] && return 0
    [[ "$target_triple" != *apple-darwin* ]] && return 0

    local cross_arch=""
    case "$target_triple" in
        x86_64-*) cross_arch="x86_64" ;;
        aarch64-*) cross_arch="arm64" ;;
    esac

    info "${C_BOLD}Cross-building sidecar for $cross_arch via Rosetta...${C_RESET}"

    if ! arch -"${cross_arch}" /usr/bin/true 2>/dev/null; then
        warn "Rosetta 2 not available for $cross_arch — install with: softwareupdate --install-rosetta --agree-to-license"
        return 1
    fi

    cd "$AGENT_DIR"
    arch -"${cross_arch}" uv run --python 3.12 --with pyinstaller python scripts/build-binary.py \
        --name "dawei-${cross_arch}" --workpath "build/dawei-${cross_arch}" --clean --runtime-mode desktop 2>&1 || {
        warn "Cross-build for $cross_arch failed — will use native sidecar as fallback"
        return 1
    }

    local bin="$AGENT_DIR/dist/dawei-${cross_arch}"
    if [[ -f "$bin" ]]; then
        ok "$bin ($(du -h "$bin" | cut -f1))"
    else
        warn "Cross-compiled binary not found: $bin"
        return 1
    fi
}

# ---- Build Tauri ----
build_tauri() {
    local target_triple="$1"
    local build_cmd
    build_cmd="$(resolve_build_cmd "$target_triple")"

    echo "==> [3/4] Building Tauri desktop app..."

    # Clean stale AppDir — linuxdeploy GTK plugin fails on re-runs with existing
    # symlinks (ln: File exists) and missing lib64 (chmod: No such file or directory)
    local bundle_base="$TAURI_DIR/src-tauri/target"
    local appdir_path="$bundle_base/$target_triple/release/bundle/appimage/NormNomos.AppDir"
    if [[ -d "$appdir_path" ]]; then
        info "Cleaning stale AppDir: $appdir_path"
        rm -rf "$appdir_path"
    fi

    cd "$TAURI_DIR"
    eval "$build_cmd"

    # Resolve actual bundle dir: Tauri uses target/<triple>/release/bundle/ with --target
    if [[ -d "$bundle_base/$target_triple/release/bundle" ]]; then
        BUNDLE_DIR="$bundle_base/$target_triple/release/bundle"
    else
        BUNDLE_DIR="$bundle_base/release/bundle"
    fi

    info "Desktop build complete."
    ok "Bundles: $BUNDLE_DIR"
}


# ---- Verify build artifacts ----
verify_artifacts() {
    local target_triple="$1"
    info "[4/4] ${C_BOLD}Verifying build artifacts...${C_RESET}"

    # Check signature files
    local sig_count
    sig_count=$(find "$BUNDLE_DIR" -name "*.sig" 2>/dev/null | wc -l | tr -d ' ')

    if [[ "$sig_count" -gt 0 ]]; then
        ok "Found $sig_count updater signature file(s)"
    elif [[ -n "${TAURI_SIGNING_PRIVATE_KEY:-}" ]]; then
        warn "TAURI_SIGNING_PRIVATE_KEY is set but no .sig files found"
    else
        warn "No .sig files (local/dev build — TAURI_SIGNING_PRIVATE_KEY not set)"
        echo "     For signed release builds, set TAURI_SIGNING_PRIVATE_KEY"
        echo "     Generate a key: cargo tauri signer generate -w ~/.normnomos/keys/enterprise.key"
    fi

    echo "Target: $target_triple"

    case "$target_triple" in
        *linux*)
            local deb_count appimage_count
            deb_count=$(find "$BUNDLE_DIR" -name "*.deb" 2>/dev/null | wc -l | tr -d ' ')
            appimage_count=$(find "$BUNDLE_DIR" -name "*.AppImage" 2>/dev/null | wc -l | tr -d ' ')
            [[ "$deb_count" -gt 0 ]] && ok "Found $deb_count .deb package(s)"
            [[ "$appimage_count" -gt 0 ]] && ok "Found $appimage_count AppImage(s)"
            ;;
        *darwin*)
            local dmg_count
            dmg_count=$(find "$BUNDLE_DIR" -name "*.dmg" 2>/dev/null | wc -l | tr -d ' ')
            [[ "$dmg_count" -gt 0 ]] && ok "Found $dmg_count .dmg disk image(s)"
            ;;
        *windows*)
            local nsis_count
            nsis_count=$(find "$BUNDLE_DIR" -name "*.exe" 2>/dev/null | wc -l | tr -d ' ')
            [[ "$nsis_count" -gt 0 ]] && ok "Found $nsis_count NSIS installer(s)"
            ;;
    esac
}

# ---- Parse arguments ----
TARGET_OVERRIDE=""
MODE="all"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target|-t)
            TARGET_OVERRIDE="$2"
            shift 2
            ;;
        --target=*)
            TARGET_OVERRIDE="${1#*=}"
            shift
            ;;
        sidecar|cli|tauri|all)
            MODE="$1"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS] [MODE]"
            echo ""
            echo "Modes:"
            echo "  sidecar    Build sidecar binary only (no frontend)"
            echo "  cli        Standalone CLI with embedded web UI (frontend + sidecar)"
            echo "  tauri      Build Tauri desktop app (assumes sidecar + frontend exist)"
            echo "  all        Full build: frontend + sidecar + Tauri (default)"
            echo ""
            echo "Options:"
            echo "  --target TRIPLE    Override auto-detected target triple"
            echo "                     e.g. aarch64-apple-darwin, x86_64-apple-darwin"
            echo ""
            echo "Examples:"
            echo "  $0                                    # build for current platform"
            echo "  $0 cli                                # standalone CLI with web UI"
            echo "  $0 --target aarch64-apple-darwin      # build for Apple Silicon"
            echo "  $0 --target x86_64-apple-darwin       # build for Intel Mac"
            echo "  $0 sidecar                            # sidecar only"
            exit 0
            ;;
        *)
            err "unknown argument: $1"
            echo "Run '$0 --help' for usage."
            exit 1
            ;;
    esac
done

# ---- Main ----
read -ra TARGETS <<< "$(resolve_targets)"

echo -e "${C_BOLD}NormNomos Desktop Build${C_RESET}"
echo "  Platform: $(uname -s) $(uname -m)"
echo "  Targets:  ${TARGETS[*]}"
echo "  Mode:     $MODE"
echo ""


case "$MODE" in
    sidecar)
        build_sidecar 1
        ;;
    cli)
        build_frontend
        build_sidecar 2
        info ""
        info "Standalone CLI binary ready: $AGENT_DIR/dist/dawei"
        info "Usage: ./dawei server start --host 0.0.0.0 --port 8431"
        info "Then open http://localhost:8431/app-ui/"
        ;;
    tauri)
        # Inject version before any build
        VERSION=$(resolve_version)
        inject_version "$VERSION"
        # Tauri-only: warn if the sidecar-embedded frontend is missing (the
        # sidecar bundles whatever sits in agent/dawei/frontend/).
        if [[ ! -f "$AGENT_DIR/dawei/frontend/index.html" ]]; then
            warn "agent/dawei/frontend/index.html missing — sidecar will embed a stale/absent web UI."
            warn "Run 'bash scripts/build-desktop.sh all' for a full build (frontend + sidecar + tauri)."
        fi
        for tgt in "${TARGETS[@]}"; do
            echo ""
            echo -e "${C_BOLD}--- Target: $tgt ---${C_RESET}"
            check_macos_prereqs "$tgt"
            copy_sidecar "$tgt"
            build_tauri "$tgt"
            verify_artifacts "$tgt"
        done
        ;;
    all)
        # Inject version before any build
        VERSION=$(resolve_version)
        inject_version "$VERSION"
        # Frontend FIRST: PyInstaller --collect-all dawei bundles whatever sits
        # in agent/dawei/frontend/, so it must be fresh before the sidecar build.
        build_frontend
        build_sidecar
        # Attempt cross-arch sidecar builds for other macOS targets
        for tgt in "${TARGETS[@]}"; do
            if [[ "$tgt" != "$(detect_target)" ]]; then
                build_sidecar_cross "$tgt" || true
            fi
        done
        # Build Tauri for each target
        for tgt in "${TARGETS[@]}"; do
            echo ""
            echo -e "${C_BOLD}--- Target: $tgt ---${C_RESET}"
            check_macos_prereqs "$tgt"
            copy_sidecar "$tgt"
            build_tauri "$tgt"
            verify_artifacts "$tgt"
        done
        ;;
esac

echo ""
info "${C_GREEN}Done.${C_RESET}"
