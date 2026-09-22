#!/usr/bin/env bash
# NormNomos macOS one-shot: build → sign → notarize → staple.
#
# Automates the full release pipeline for both Apple Silicon (arm64)
# and Intel (x86_64) DMGs.
#
# Prerequisites:
#   - Xcode Command Line Tools + paid Apple Developer Program membership
#   - "Developer ID Application" certificate installed in Keychain
#   - App-specific password generated at appleid.apple.com
#   - Rust + cargo-tauri-cli, uv, npm
#
# Usage:
#   bash scripts/mac-build-and-sign.sh                              # full pipeline
#   bash scripts/mac-build-and-sign.sh --skip-notarize              # build + sign only
#   bash scripts/mac-build-and-sign.sh --target aarch64-apple-darwin  # single arch
#   bash scripts/mac-build-and-sign.sh --app-password xxxx-xxxx-xxxx-xxxx   # non-interactive
#
# Environment variables (override auto-detection):
#   APPLE_SIGNING_IDENTITY   codesign identity (auto-detected if unset)
#   APPLE_ID                 Apple ID email (auto-detected if unset)
#   APPLE_TEAM_ID            Team ID (auto-detected if unset)
#   APPLE_APP_PASSWORD       App-specific password (REQUIRED for notarization;
#                            no built-in default — generate at appleid.apple.com)
set -euo pipefail

# ── Colors & logging ──────────────────────────────────────────────
C_RESET='\033[0m'; C_BOLD='\033[1m'; C_RED='\033[0;31m'; C_GREEN='\033[0;32m'; C_YELLOW='\033[1;33m'; C_BLUE='\033[0;34m'
step() { echo -e "\n  ${C_BLUE}▶${C_RESET} ${C_BOLD}$*${C_RESET}"; }
info() { echo -e "     $*"; }
ok()   { echo -e "  ${C_GREEN}OK${C_RESET} $*"; }
warn() { echo -e "  ${C_YELLOW}WARN${C_RESET} $*"; }
die()  { echo -e "  ${C_RED}FATAL${C_RESET} $*" >&2; exit 1; }

# ── Paths ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"            # davybot/ (单仓: engine/ + app/ + scripts/)
TAURI_DIR="$REPO_ROOT/app"
AGENT_DIR="$REPO_ROOT/engine/agent"

# ── Env 一致性校验 (多模式统一方案 §L1, keep in sync with build-desktop.sh) ──
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
        die "$f 声明 DAWEI_RUNTIME_MODE=$got, 与目标模式 '$want' 不符 (多模式统一方案 §L1)"
    fi
    ok "$f DAWEI_RUNTIME_MODE=$got"
}

check_mode_env() {
    step "Env 一致性校验 (desktop)"
    local f
    for f in .env.desktop .env.desktop.dev .env.desktop.prod; do
        check_runtime_mode_env "$AGENT_DIR/$f" desktop
    done
}

# ── Defaults ───────────────────────────────────────────────────────
SKIP_NOTARIZE=false
SKIP_CLEAN=false
TARGET_OVERRIDE=""
# Credentials come from env / --app-password ONLY — never hardcode.
# (A previous revision shipped a built-in app-specific password here; it has
# been rotated. Any credential that ever touched the repo is considered burned.)
APP_PASSWORD="${APPLE_APP_PASSWORD:-}"

# ── Parse args ─────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-notarize)   SKIP_NOTARIZE=true; shift ;;
        --skip-clean)      SKIP_CLEAN=true; shift ;;
        --target|-t)       TARGET_OVERRIDE="$2"; shift 2 ;;
        --target=*)        TARGET_OVERRIDE="${1#*=}"; shift ;;
        --app-password)    APP_PASSWORD="$2"; shift 2 ;;
        --app-password=*)  APP_PASSWORD="${1#*=}"; shift ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-notarize         Skip notarization (sign only)"
            echo "  --skip-clean            Skip cleaning stale build artifacts"
            echo "  --target TRIPLE         Build single arch only"
            echo "  --app-password PW       Apple app-specific password"
            echo ""
            echo "Examples:"
            echo "  $0                                              # full pipeline, both archs"
            echo "  $0 --skip-notarize                              # build + sign only"
            echo "  $0 --target aarch64-apple-darwin                # Apple Silicon only"
            echo "  $0 --app-password xxxx-xxxx-xxxx-xxxx           # non-interactive"
            exit 0 ;;
        *) die "unknown argument: $1 (run --help)" ;;
    esac
done

# ── Auto-detect signing identity ───────────────────────────────────
detect_signing_identity() {
    if [[ -n "${APPLE_SIGNING_IDENTITY:-}" ]]; then
        echo "$APPLE_SIGNING_IDENTITY"
        return
    fi
    local id
    id=$(security find-identity -v -p codesigning 2>/dev/null \
        | grep "Developer ID Application" \
        | head -1 \
        | sed 's/.*"\(.*\)".*/\1/')
    echo "$id"
}

# ── Auto-detect Apple ID / Team ID ────────────────────────────────
detect_apple_id() {
    if [[ -n "${APPLE_ID:-}" ]]; then
        echo "$APPLE_ID"
        return
    fi
    # Extract from signing identity or keychain
    local id
    id=$(security find-identity -v -p codesigning 2>/dev/null \
        | grep "Developer ID Application" \
        | head -1 \
        | grep -oE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
    echo "${id:-}"
}

detect_team_id() {
    if [[ -n "${APPLE_TEAM_ID:-}" ]]; then
        echo "$APPLE_TEAM_ID"
        return
    fi
    local team
    team=$(security find-identity -v -p codesigning 2>/dev/null \
        | grep "Developer ID Application" \
        | head -1 \
        | grep -oE '\([A-Z0-9]+\)$' \
        | tr -d '()')
    echo "${team:-}"
}

# ── Resolve version (setuptools_scm → semver) ─────────────────────
resolve_version() {
    local version

    # Force setuptools_scm to rewrite dawei/_version.py from current git HEAD.
    # The file is frozen at install time, so without this a new git tag won't
    # take effect until dawei is reinstalled — DMG version drifts from git.
    (cd "$AGENT_DIR" && uv pip install -e . --no-deps --force-reinstall -q 2>/dev/null) \
        || warn "_version.py refresh failed — using cached version"

    version=$(cd "$AGENT_DIR" && uv run python -c "
from dawei._version import __version__
import re
v = __version__
v = re.sub(r'\.post(\d+)', r'-post.\1', v)
v = re.sub(r'\.dev(\d+)', r'.dev.\1', v)
v = re.sub(r'(\d+\.\d+\.\d+)a(\d+)',  lambda m: f'{m.group(1)}-alpha.{m.group(2)}', v)
v = re.sub(r'(\d+\.\d+\.\d+)b(\d+)',   lambda m: f'{m.group(1)}-beta.{m.group(2)}',  v)
v = re.sub(r'(\d+\.\d+\.\d+)rc(\d+)',  lambda m: f'{m.group(1)}-rc.{m.group(2)}',    v)
m = re.match(r'^\d+\.\d+\.\d+(-[a-zA-Z]+\.\d+(\.[a-zA-Z]+\.\d+)*)?$', v)
print(m.group(0) if m else v)
" 2>/dev/null | tail -1)
    echo "${version:-0.0.0}"
}

_sed_inplace() { sed -i '' "$@" 2>/dev/null || sed -i "$@"; }

# In-place injection with backup + restore-on-exit: the build sees the right
# version, but the working tree stays clean afterwards (no accidental version
# diffs or jq-reformatted JSON to commit). Same approach as build-desktop.sh.
inject_version() {
    local version="$1"
    info "Version: $version"

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

    # Cargo.toml
    _sed_inplace "s/^version = \"[^\"]*\"/version = \"$version\"/" "$cargo"

    ok "Version injected: $version (auto-restored on exit)"
}

restore_version_files() {
    local f
    for f in "$TAURI_DIR/src-tauri/tauri.conf.json" "$TAURI_DIR/src-tauri/Cargo.toml"; do
        [[ -f "$f.build-bak" ]] && mv "$f.build-bak" "$f"
    done
}
trap restore_version_files EXIT

# ── Resolve targets ────────────────────────────────────────────────
resolve_targets() {
    if [[ -n "$TARGET_OVERRIDE" ]]; then
        echo "$TARGET_OVERRIDE"
        return
    fi
    case "$(uname -m)" in
        arm64|aarch64) echo "aarch64-apple-darwin x86_64-apple-darwin" ;;
        x86_64)        echo "x86_64-apple-darwin aarch64-apple-darwin" ;;
        *)             die "Unsupported arch $(uname -m)" ;;
    esac
}

# ── Phase 0: Clean stale artifacts ─────────────────────────────────
# Ensures nn-bot sidecar and davybot-app bundle are rebuilt from current
# source on every run. Without this, prior build outputs survive and can
# be picked up by later steps (notably copy_sidecar's cross-binary
# fallback), shipping a DMG with outdated nn-bot code.
clean_artifacts() {
    step "Phase 0: Clean stale artifacts"

    # nn-bot sidecar: PyInstaller --clean only touches cache + workpath,
    # never dist/. Remove all dawei* binaries (native + cross-arch) so
    # a half-finished prior build can't leak through.
    info "Cleaning nn-bot sidecar: dist/ build/"
    rm -rf "$AGENT_DIR/dist/dawei"* 2>/dev/null || true
    rm -rf "$AGENT_DIR/build/dawei"* 2>/dev/null || true

    # davybot-app: wipe staged sidecar binaries so copy_sidecar can never
    # fall back to a stale dawei-<triple> from a previous run.
    info "Cleaning davybot-app sidecar: src-tauri/binaries/"
    rm -f "$TAURI_DIR/src-tauri/binaries/dawei-"* 2>/dev/null || true

    # davybot-app: drop prior bundle outputs per target. Keep cargo's
    # incremental compile cache (target/...) for speed; only the final
    # .app/.dmg stage is forced to regenerate.
    local tgt
    for tgt in "${TARGETS[@]}"; do
        info "Cleaning bundle: target/$tgt/release/bundle/"
        rm -rf "$TAURI_DIR/src-tauri/target/$tgt/release/bundle" 2>/dev/null || true
    done

    # Optional: clear Python bytecode caches so PyInstaller bundles the
    # current .py source even if a .pyc has a newer mtime.
    find "$AGENT_DIR/dawei" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

    ok "Stale artifacts removed"
}

# ── Phase 0.5: Build frontend (davybot-app SPA → agent/dawei/frontend/) ──
# PyInstaller --collect-all dawei bundles whatever currently sits in
# agent/dawei/frontend/, so the SPA must be rebuilt BEFORE the sidecar —
# otherwise the DMG ships whatever frontend a previous build left behind.
# Same command + flatten semantics as build-desktop.sh build_frontend.
build_frontend() {
    step "Phase 0.5: Build frontend (server-embedded SPA → agent/dawei/frontend/)"

    cd "$TAURI_DIR"
    if [[ ! -d "node_modules" ]]; then
        info "Installing frontend dependencies..."
        npm install
    fi

    # build:server → vite build --mode server (.env.server; empty API/WS URLs,
    # base /app-ui/) — the same-origin UI the sidecar serves.
    npm run build:server

    local frontend_dist="$TAURI_DIR/dist"
    [[ -d "$frontend_dist" ]] || die "Frontend build failed: $frontend_dist not found"

    rm -rf "$AGENT_DIR/dawei/frontend"
    cp -r "$frontend_dist" "$AGENT_DIR/dawei/frontend"
    ok "Frontend bundled: $AGENT_DIR/dawei/frontend ($(du -sh "$AGENT_DIR/dawei/frontend" | cut -f1))"
}

# ── Phase 1: Build sidecar ─────────────────────────────────────────
build_sidecar() {
    step "Phase 1/6: Build sidecar (build-binary.py / PyInstaller)"
    cd "$AGENT_DIR"
    # Delegate to the canonical builder (same one build-desktop.ps1 + CI use):
    # HIDDEN_IMPORTS + --collect-all dawei is a strict superset of the bare-call
    # --add-data list below (every locale/template/theme file is bundled — verified
    # via the build TOC), plus the UTF-8 runtime hook. Keeps the macOS release
    # sidecar identical to the Windows one.
    # --runtime-mode desktop: 产物盖戳 (多模式统一方案 §L1) — 桌面包只允许 desktop。
    check_mode_env
    uv run --with pyinstaller --python 3.12 python scripts/build-binary.py --clean --runtime-mode desktop

    local bin="$AGENT_DIR/dist/dawei"
    [[ -f "$bin.exe" ]] && bin="$bin.exe"
    [[ -f "$bin" ]] || die "Sidecar build failed: $bin not found"
    ok "$bin ($(du -h "$bin" | cut -f1))"
}

# ── Phase 1b: Cross-compile sidecar (Rosetta) ─────────────────────
build_sidecar_cross() {
    local target="$1"
    local native
    native="$(uname -m)"
    local cross_arch=""
    case "$target" in
        x86_64-*)  cross_arch="x86_64" ;;
        aarch64-*) cross_arch="arm64" ;;
    esac

    # Skip if same arch
    [[ "$cross_arch" == "$native" || "$cross_arch" == "aarch64" && "$native" == "arm64" ]] && return 0

    step "Phase 1b: Cross-compile sidecar for $cross_arch (Rosetta)"

    if ! arch -"${cross_arch}" /usr/bin/true 2>/dev/null; then
        warn "Rosetta 2 not available — skipping cross-compile. Install: softwareupdate --install-rosetta --agree-to-license"
        return 1
    fi

    cd "$AGENT_DIR"
    arch -"${cross_arch}" uv run --with pyinstaller --python 3.12 python scripts/build-binary.py \
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

# ── Detect platform target triple ─────────────────────────────────
# macOS-only variant of build-desktop.sh detect_target (pre-flight already
# enforces Darwin). Used by copy_sidecar to decide native vs cross binary.
detect_target() {
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64)        echo "x86_64-apple-darwin" ;;
        arm64|aarch64) echo "aarch64-apple-darwin" ;;
        *) die "unsupported arch: $arch" ;;
    esac
}

# ── Copy sidecar to Tauri binaries dir ─────────────────────────────
# Same selection logic as build-desktop.sh: prefer the cross-compiled binary
# for non-native targets. (The previous condition silently ignored
# dawei-arm64 on Intel Macs and shipped an x86_64 sidecar in the aarch64 DMG.)
copy_sidecar() {
    local target_triple="$1"
    local native_triple
    native_triple="$(detect_target)"

    local sidecar_bin=""
    if [[ "$target_triple" != "$native_triple" ]]; then
        local cross_arch=""
        case "$target_triple" in
            x86_64-*)  cross_arch="x86_64" ;;
            aarch64-*) cross_arch="arm64" ;;
        esac
        sidecar_bin="$AGENT_DIR/dist/dawei-${cross_arch}"
    fi

    # Fall back to native binary
    if [[ -z "$sidecar_bin" ]] || [[ ! -f "$sidecar_bin" ]]; then
        sidecar_bin="$AGENT_DIR/dist/dawei"
        [[ -f "$sidecar_bin.exe" ]] && sidecar_bin="$sidecar_bin.exe"
        if [[ "$target_triple" != "$native_triple" ]]; then
            warn "No cross-compiled sidecar for $target_triple — using native binary (needs Rosetta 2 on the target Mac)"
        fi
    fi

    [[ -f "$sidecar_bin" ]] || die "Sidecar binary not found"

    local dest="$TAURI_DIR/src-tauri/binaries/dawei-${target_triple}"
    mkdir -p "$(dirname "$dest")"
    cp "$sidecar_bin" "$dest"
    chmod +x "$dest"
    info "Sidecar → $dest ($(du -h "$dest" | cut -f1))"
}

# ── Phase 2: Build Tauri app (.app only) ───────────────────────────
build_tauri() {
    local target="$1"

    # Ensure Rust target is installed
    if ! rustup target list --installed 2>/dev/null | grep -q "$target"; then
        info "Installing Rust target: $target"
        rustup target add "$target"
    fi

    # Export signing identity so Tauri signs the .app with hardened runtime.
    # Build with --bundles app ONLY (not dmg). With --bundles dmg, Tauri
    # seals the DMG from the .app before we can apply sidecar entitlements,
    # so the shipped sidecar's extracted libpython3.12.dylib gets rejected
    # by Library Validation → 本地引擎启动失败. By building .app only, we
    # can sign it with entitlements, then create the DMG ourselves.
    export APPLE_SIGNING_IDENTITY="$SIGNING_IDENTITY"

    cd "$TAURI_DIR"
    info "Building Tauri (.app only): --target $target --bundles app"
    npx tauri build --config src-tauri/tauri.conf.json --target "$target" --bundles app
}

# ── Arch tag for DMG filename (matches Tauri's convention) ─────────
arch_tag() {
    case "$1" in
        aarch64-apple-darwin) echo "aarch64" ;;
        x86_64-apple-darwin)  echo "x64" ;;
        *) die "Unknown target: $1" ;;
    esac
}

# ── Phase 3a: Sign .app with entitlements ──────────────────────────
sign_app() {
    local app_bundle="$1"
    local identity="$2"

    local ent_dir="$SCRIPT_DIR/entitlements"
    local app_ent="$ent_dir/app.entitlements"
    local sidecar_ent="$ent_dir/sidecar.entitlements"

    info "Signing .app: $(basename "$app_bundle")"

    # Pass 1: whole-bundle sign with Hardened Runtime + app entitlements.
    # --deep covers the main executable + Tauri frameworks.
    codesign --sign "$identity" \
        --force \
        --deep \
        --options runtime \
        --entitlements "$app_ent" \
        --timestamp \
        "$app_bundle"

    # Pass 2: re-sign the PyInstaller sidecar with sidecar-specific
    # entitlements. disable-library-validation is load-bearing: without it
    # the extracted libpython3.12.dylib (ad-hoc signed, no Team ID) is
    # rejected by Library Validation ("different Team IDs") and the process
    # dies before uvicorn binds → 本地引擎启动失败.
    local sidecar_bin="$app_bundle/Contents/MacOS/dawei"
    if [[ -f "$sidecar_bin" ]]; then
        info "Re-signing sidecar with PyInstaller entitlements: dawei"
        codesign --sign "$identity" \
            --force \
            --options runtime \
            --entitlements "$sidecar_ent" \
            --timestamp \
            "$sidecar_bin"
    else
        die "Sidecar not found at $sidecar_bin — sidecar is required"
    fi

    codesign --verify --deep --strict "$app_bundle" 2>&1
    ok "Signed .app: $(basename "$app_bundle")"
}

# ── Phase 3b: Create DMG from the signed .app ──────────────────────
# This is the step that --bundles dmg skipped: we package the DMG AFTER
# entitlements are applied, so the .app inside the DMG carries them.
create_dmg() {
    local app_bundle="$1"
    local target="$2"

    local dmg_dir="$TAURI_DIR/src-tauri/target/$target/release/bundle/dmg"
    mkdir -p "$dmg_dir"
    local dmg="$dmg_dir/NormNomos_${VERSION}_$(arch_tag "$target").dmg"

    # NOTE: all diagnostics go to stderr (&2). This function "returns" the DMG
    # path via stdout (echo "$dmg"), and the caller captures it with
    # $(create_dmg ...). Any stdout here would corrupt that captured path.
    info "Creating DMG from signed .app: $(basename "$dmg")" >&2

    # Stage .app + Applications symlink, then build a compressed read-only DMG.
    local stage
    stage=$(mktemp -d)
    cp -R "$app_bundle" "$stage/"
    ln -s /Applications "$stage/Applications"

    rm -f "$dmg"
    hdiutil create \
        -volname "NormNomos" \
        -fs HFS+ \
        -srcfolder "$stage" \
        -ov \
        -format UDZO \
        -imagekey zlib-level=9 \
        "$dmg" >&2

    rm -rf "$stage"

    [[ -f "$dmg" ]] || die "DMG creation failed: $dmg"
    echo "$dmg"
}

# ── Phase 3c: Sign the DMG container ───────────────────────────────
sign_dmg() {
    local dmg="$1"
    local identity="$2"

    info "Signing DMG: $(basename "$dmg")"
    codesign --sign "$identity" \
        --force \
        --timestamp \
        "$dmg"

    codesign --verify --deep --strict "$dmg" 2>&1
    ok "Signed DMG: $(basename "$dmg")"
}

# ── Phase 3d: Updater signature (.sig) for the DMG ────────────────
# Tauri's automatic updater needs a .sig next to the artifact. Building with
# --bundles app + hand-rolled hdiutil (see build_tauri) skips Tauri's own
# updater-signing step, so generate it explicitly when the key is available —
# otherwise macOS DMGs silently lack auto-update support.
sign_updater() {
    local dmg="$1"
    if [[ -z "${TAURI_SIGNING_PRIVATE_KEY:-}" ]]; then
        warn "TAURI_SIGNING_PRIVATE_KEY not set — no updater .sig for $(basename "$dmg") (auto-update disabled for this build)"
        return 0
    fi
    info "Signing updater artifact: $(basename "$dmg").sig"
    local sign_args=(sign --private-key "$TAURI_SIGNING_PRIVATE_KEY")
    if [[ -n "${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:-}" ]]; then
        sign_args+=(--password "$TAURI_SIGNING_PRIVATE_KEY_PASSWORD")
    fi
    sign_args+=("$dmg")
    npx tauri signer "${sign_args[@]}"
    [[ -f "$dmg.sig" ]] || die "Updater signature not created: $dmg.sig"
    ok "Updater signature: $dmg.sig"
}

# ── Phase 4: Notarize DMG ──────────────────────────────────────────
notarize_dmg() {
    local dmg="$1"
    local apple_id="$2"
    local team_id="$3"
    local password="$4"

    info "Submitting for notarization: $(basename "$dmg")"
    local result
    result=$(xcrun notarytool submit "$dmg" \
        --apple-id "$apple_id" \
        --team-id "$team_id" \
        --password "$password" \
        --wait 2>&1)

    local status
    status=$(echo "$result" | grep "status:" | tail -1 | awk '{print $NF}')

    if [[ "$status" != "Accepted" ]]; then
        warn "Notarization result: $status"
        echo "$result"
        # Print log for debugging
        local submission_id
        submission_id=$(echo "$result" | grep "id:" | head -1 | awk '{print $NF}')
        if [[ -n "$submission_id" ]]; then
            info "Fetching notarization log..."
            xcrun notarytool log "$submission_id" \
                --apple-id "$apple_id" \
                --team-id "$team_id" \
                --password "$password" 2>&1 || true
        fi
        die "Notarization failed for $(basename "$dmg")"
    fi

    ok "Notarized: $(basename "$dmg")"
}

# ── Phase 5: Staple notarization ticket ────────────────────────────
staple_dmg() {
    local dmg="$1"
    info "Stapling: $(basename "$dmg")"
    # notarytool staple replaces the deprecated `xcrun stapler`
    xcrun notarytool staple "$dmg" 2>&1
    ok "Stapled: $(basename "$dmg")"
}

# ════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════

echo -e "${C_BOLD}╔══════════════════════════════════════════╗${C_RESET}"
echo -e "${C_BOLD}║  NormNomos macOS Build + Sign Pipeline  ║${C_RESET}"
echo -e "${C_BOLD}╚══════════════════════════════════════════╝${C_RESET}"
echo ""

# ── Pre-flight checks ──────────────────────────────────────────────
step "Pre-flight checks"

[[ "$(uname -s)" == "Darwin" ]] || die "This script is for macOS only"

SIGNING_IDENTITY=$(detect_signing_identity)
[[ -n "$SIGNING_IDENTITY" ]] || die "No 'Developer ID Application' certificate found in Keychain. Install from developer.apple.com"
ok "Signing identity: $SIGNING_IDENTITY"

# No hardcoded identity defaults — use the keychain auto-detectors above,
# then fail fast if anything required for notarization is missing.
APPLE_ID="${APPLE_ID:-$(detect_apple_id)}"
APPLE_TEAM_ID="${APPLE_TEAM_ID:-$(detect_team_id)}"

if [[ "$SKIP_NOTARIZE" == false ]]; then
    [[ -n "$APPLE_ID" ]] || die "Cannot detect Apple ID. Set APPLE_ID env var"
    [[ -n "$APPLE_TEAM_ID" ]] || die "Cannot detect Team ID. Set APPLE_TEAM_ID env var"

    if [[ -z "$APP_PASSWORD" ]]; then
        die "No app-specific password. Generate one at https://appleid.apple.com and set APPLE_APP_PASSWORD (or pass --app-password)"
    fi
    ok "Apple ID: $APPLE_ID"
    ok "Team ID: $APPLE_TEAM_ID"
fi

command -v uv &>/dev/null      || die "uv not found (install: https://docs.astral.sh/uv)"
command -v npm &>/dev/null     || die "npm not found"
command -v rustup &>/dev/null  || die "rustup not found (install: https://rustup.rs)"
command -v codesign &>/dev/null || die "codesign not found (install Xcode CLI tools)"

# Entitlements plists (app + PyInstaller sidecar). The sidecar file must
# carry disable-library-validation or the extracted libpython3.12.dylib is
# rejected by Hardened Runtime Library Validation → 本地引擎启动失败.
ENT_DIR="$SCRIPT_DIR/entitlements"
for _ent in app sidecar; do
    [[ -f "$ENT_DIR/${_ent}.entitlements" ]] \
        || die "Missing $ENT_DIR/${_ent}.entitlements — required for PyInstaller sidecar signing"
done
ok "Entitlements present: app + sidecar"

ok "All tools available"

# ── Resolve targets ────────────────────────────────────────────────
read -ra TARGETS <<< "$(resolve_targets)"
info "Targets: ${TARGETS[*]}"

# ── Phase 0: Clean stale artifacts ─────────────────────────────────
if [[ "$SKIP_CLEAN" == false ]]; then
    clean_artifacts
else
    step "Phase 0: Clean skipped (--skip-clean)"
    warn "Using cached artifacts — DMG may ship outdated code if source changed"
fi

# ── Resolve & inject version ──────────────────────────────────────
step "Resolving version"
VERSION=$(resolve_version)
inject_version "$VERSION"

# ── Phase 0.5 + Phase 1: Build frontend, then sidecar ─────────────
build_frontend
build_sidecar

# Cross-compile for other targets
for tgt in "${TARGETS[@]}"; do
    build_sidecar_cross "$tgt" || true
done

# ── Phase 2: Build Tauri for each target ───────────────────────────
SIGNED_DMGS=()

for tgt in "${TARGETS[@]}"; do
    step "Phase 2/6: Build Tauri — $tgt"
    copy_sidecar "$tgt"
    build_tauri "$tgt"

    app_bundle="$TAURI_DIR/src-tauri/target/$tgt/release/bundle/macos/NormNomos.app"
    [[ -d "$app_bundle" ]] || { warn "No .app for $tgt — skipping"; continue; }

    # ── Phase 3: Sign .app → create DMG → sign DMG ──────────────
    step "Phase 3/6: Sign + package — $tgt"
    sign_app "$app_bundle" "$SIGNING_IDENTITY"

    dmg=$(create_dmg "$app_bundle" "$tgt")
    ok "DMG: $dmg ($(du -h "$dmg" | cut -f1))"

    sign_dmg "$dmg" "$SIGNING_IDENTITY"
    sign_updater "$dmg"

    SIGNED_DMGS+=("$dmg")
done

# ── Phase 4 & 5: Notarize + Staple ────────────────────────────────
if [[ "$SKIP_NOTARIZE" == false ]] && [[ ${#SIGNED_DMGS[@]} -gt 0 ]]; then
    for dmg in "${SIGNED_DMGS[@]}"; do
        step "Phase 4/6: Notarize — $(basename "$dmg")"
        notarize_dmg "$dmg" "$APPLE_ID" "$APPLE_TEAM_ID" "$APP_PASSWORD"

        step "Phase 5/6: Staple — $(basename "$dmg")"
        staple_dmg "$dmg"
    done
else
    if [[ "$SKIP_NOTARIZE" == true ]]; then
        step "Phase 4-5: Skipped (--skip-notarize)"
    fi
fi

# ── Summary ────────────────────────────────────────────────────────
step "Phase 6/6: Summary"
echo ""
echo -e "  ${C_BOLD}Build complete!${C_RESET}"
echo ""
echo "  Version:  $VERSION"
echo "  Identity: $SIGNING_IDENTITY"
[[ "$SKIP_NOTARIZE" == false ]] && echo "  Notarized: Yes"
echo ""
echo "  Artifacts:"
for dmg in "${SIGNED_DMGS[@]}"; do
    local_arch=""
    case "$(dirname "$dmg")" in
        *aarch64*) local_arch="Apple Silicon (M1/M2/M3/M4)" ;;
        *x86_64*)  local_arch="Intel Mac" ;;
        *)         local_arch="$(basename "$(dirname "$(dirname "$(dirname "$(dirname "$dmg")")")")")" ;;
    esac
    echo "    $local_arch"
    echo "      $(basename "$dmg")  ($(du -h "$dmg" | cut -f1))"
    echo "      $dmg"
    echo ""
done

echo -e "  ${C_GREEN}Done.${C_RESET}  DMGs are ready for distribution."
