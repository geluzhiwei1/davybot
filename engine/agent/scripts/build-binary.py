#!/usr/bin/env python3
"""PyInstaller build script for dawei sidecar --onefile binary.

Usage:
    cd engine/agent && python scripts/build-binary.py          # build for current platform
    cd engine/agent && python scripts/build-binary.py --clean  # clean + build
    cd engine/agent && python scripts/build-binary.py --no-upx # skip UPX compression
    cd engine/agent && python scripts/build-binary.py --runtime-mode desktop  # stamp artifact
    # Cross-arch (macOS Rosetta) — separate workpath so caches don't collide:
    arch -x86_64 uv run --with pyinstaller --python 3.12 python scripts/build-binary.py \
        --name dawei-x86_64 --workpath build/dawei-x86_64 --clean

This is the SINGLE source of truth for the server binary build (HIDDEN_IMPORTS,
--collect-all dawei, UTF-8 runtime hook, UPX control). Every caller delegates
here: build-desktop.ps1 (Windows), mac-build-and-sign.sh (macOS release),
build-server-binary.sh. Building the bare entry with raw `pyinstaller --onefile`
omits the hidden imports / collect-all and yields a broken binary.

Runtime-mode stamp (多模式统一方案 §L1 产物盖戳):
    --runtime-mode saas[,server,...]  writes dawei/_mode_ into the package
    before building (--collect-all dawei bundles it). At boot, runtime.py
    validate_environment() rejects modes outside the stamp (FAST FAIL —
    prevents a saas artifact from being booted as local/server and bypassing
    isolation guards). Omitted → no stamp → unrestricted (dev builds).

Output:
    dist/dawei            (Linux/macOS)
    dist/dawei.exe        (Windows)
    dist/dawei-<arch>     (cross-arch macOS, with --name)
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


AGENT_DIR = Path(__file__).resolve().parent.parent
ENTRY_POINT = "dawei/cli/dawei.py"
MODE_STAMP = AGENT_DIR / "dawei" / "_mode_"

# PyInstaller runtime hook that defaults text-mode open() to UTF-8. Without it
# the frozen sidecar crashes on zh-CN Windows (locale=GBK) the first time it
# reads a UTF-8 YAML/config without an explicit encoding — see scripts/utf8_runtime_hook.py.
RUNTIME_HOOK = AGENT_DIR / "scripts" / "utf8_runtime_hook.py"

# fmt: off
HIDDEN_IMPORTS = [
    # FastAPI + Uvicorn
    "fastapi", "uvicorn", "uvicorn.logging", "uvicorn.loops",
    "uvicorn.loops.auto", "uvicorn.protocols", "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan", "uvicorn.lifespan.on",
    # pydantic v1 compat (if any)
    "pydantic", "pydantic.v1",
    # Common hidden imports
    "aiofiles", "jinja2", "yaml", "click",
    "multiprocessing", "asyncio",
]

COLLECT_ALL = ["dawei"]

# Optional deps — collected ONLY when present in the build env (find_spec):
#   e2b — CubeSandbox/E2B SDK ([project.optional-dependencies].sandbox).
#   SaaS binaries execute ALL file/command tools inside CubeSandbox (fail-fast,
#   no fallback), so a saas artifact without e2b breaks every workspace tool
#   with "E2B SDK 不可用" (seen on demo.normnomos.com 2026-09-22). Desktop
#   (local mode) never imports it → build-server-binary.sh passes --with e2b;
#   desktop/local envs without it just skip (with a note).
import importlib.util as _ilu

# opentelemetry: e2b's transitive dep (opentelemetry-api) — its submodules load
# fully dynamically, so PyInstaller static analysis only found part of the tree;
# 'opentelemetry.propagate' was missing → ModuleNotFoundError in the frozen saas
# binary (demo.normnomos.com 2026-09-22 16:07). Only installed alongside e2b
# (--with e2b), so the find_spec guard keeps desktop builds unaffected.
#
# boto3/botocore/cryptography: WorkspaceStore SaaS 后端 ([workspace-store] extra,
# rustfs/minio/s3)。全部是函数内延迟 import (dawei/sandbox/workspace_store.py),
# 静态分析不可见 → 不打进二进制的话, SaaS 下 _init_workspace_store 拿到
# ImportError 只能回退 virtiofs host-mount = 原 130400 挂载炸弹 (2026-09-22)。
# botocore 的 endpoints JSON 按区域动态加载, 必须 collect-all 而非 hiddenimports。
# 同样走 find_spec 守卫: build-server-binary.sh 传 --with boto3 --with cryptography,
# desktop 构建环境没有 boto3 就自然跳过。
OPTIONAL_COLLECT = ["e2b", "opentelemetry", "boto3", "botocore", "cryptography"]

# No ADD_DATA: --collect-all dawei already bundles every submodule + data file
# under the package (templates, locales, configs). Re-adding the raw `dawei`
# tree as data duplicated the whole package and bloated the --onefile binary,
# slowing first-launch extraction.
# fmt: on


def detect_target_triple() -> str:
    """Detect Rust-style target triple from platform info."""
    arch = platform.machine()
    plat = sys.platform

    if plat == "linux":
        return f"{arch}-unknown-linux-gnu"
    elif plat == "darwin":
        # macOS arm64 → aarch64-apple-darwin
        arch_apple = "aarch64" if arch in ("arm64", "aarch64") else "x86_64"
        return f"{arch_apple}-apple-darwin"
    elif plat == "win32":
        return f"{arch}-pc-windows-msvc"
    else:
        raise RuntimeError(f"Unsupported platform: {plat}")


def find_upx() -> str | None:
    """Find UPX binary if available."""
    upx = shutil.which("upx")
    return upx


def write_mode_stamp(modes: list[str]) -> None:
    """Write dawei/_mode_ (allowed runtime modes) for --collect-all to bundle."""
    try:
        from dawei.runtime import RUNTIME_MODES
    except ImportError:
        RUNTIME_MODES = ("saas", "desktop", "server", "tui")
    invalid = [m for m in modes if m not in RUNTIME_MODES]
    if invalid:
        print(f"[build-binary] ERROR: invalid --runtime-mode values: {invalid} "
              f"(valid: {list(RUNTIME_MODES)})", file=sys.stderr)
        sys.exit(1)
    MODE_STAMP.write_text(",".join(modes) + "\n", encoding="utf-8")
    print(f"[build-binary] Runtime-mode stamp: {MODE_STAMP} -> {','.join(modes)}")


def build(clean: bool = False, use_upx: bool = True, name: str = "dawei",
          workpath: str | None = None, runtime_modes: list[str] | None = None):
    """Run PyInstaller build.

    name:          output binary name (override to "dawei-<arch>" for cross-arch builds).
    workpath:      PyInstaller work/cache dir (override to "build/dawei-<arch>" so the
                   cross-arch build's --clean doesn't wipe the native build's cache).
    runtime_modes: artifact mode stamp (多模式统一方案 §L1); None → no stamp.
    Both name/workpath default to the native single-binary build, so callers that
    pass neither (e.g. build-desktop.ps1: `build-binary.py --clean`) behave
    exactly as before.
    """
    os.chdir(AGENT_DIR)

    dist_dir = AGENT_DIR / "dist"
    build_dir = Path(workpath) if workpath else (AGENT_DIR / "build")

    if clean:
        for d in (dist_dir, build_dir):
            if d.exists():
                shutil.rmtree(d)
        for f in AGENT_DIR.glob("*.spec"):
            f.unlink()

    # Build cmd
    binary_name = f"{name}.exe" if sys.platform == "win32" else name

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", name,
        "--noconfirm",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(AGENT_DIR),
        "--clean" if clean else "",
    ]

    for hi in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", hi])

    for coll in COLLECT_ALL:
        cmd.extend(["--collect-all", coll])

    # Optional deps: collect when the build env provides them (see OPTIONAL_COLLECT).
    for pkg in OPTIONAL_COLLECT:
        if _ilu.find_spec(pkg):
            cmd.extend(["--collect-all", pkg])
            print(f"[build-binary] Collecting optional package: {pkg}")
        else:
            print(f"[build-binary] NOTE: optional '{pkg}' not in build env — skipped "
                  f"(saas/CubeSandbox binaries need it: add '--with {pkg}' to uv run)")

    # Force UTF-8 file I/O in the frozen app (zh-CN Windows defaults to GBK).
    if RUNTIME_HOOK.exists():
        cmd.extend(["--runtime-hook", str(RUNTIME_HOOK)])
    else:
        print(f"[build-binary] WARN: runtime hook not found at {RUNTIME_HOOK}", file=sys.stderr)

    # UPX
    upx = find_upx() if use_upx else None
    if upx:
        cmd.extend(["--upx-dir", str(Path(upx).parent)])
    else:
        cmd.append("--noupx")

    cmd = [c for c in cmd if c]  # remove empty strings
    cmd.append(ENTRY_POINT)

    print(f"[build-binary] Running: {' '.join(cmd)}")
    if runtime_modes:
        write_mode_stamp(runtime_modes)
    try:
        result = subprocess.run(cmd, cwd=AGENT_DIR)
    finally:
        # Stamp is build-time only — keep the source tree clean (unstamped
        # dev runs must stay unrestricted; the copy inside the bundle remains).
        if runtime_modes and MODE_STAMP.exists():
            MODE_STAMP.unlink()
    if result.returncode != 0:
        print("[build-binary] PyInstaller failed", file=sys.stderr)
        sys.exit(result.returncode)

    binary = dist_dir / binary_name
    if not binary.exists():
        print(f"[build-binary] Binary not found at {binary}", file=sys.stderr)
        sys.exit(1)

    size_mb = binary.stat().st_size / (1024 * 1024)
    print(f"[build-binary] Built: {binary} ({size_mb:.1f} MB)")
    print(f"[build-binary] Target: {detect_target_triple()}")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Build dawei sidecar binary with PyInstaller")
    p.add_argument("--clean", action="store_true", help="Clean dist/build before building")
    p.add_argument("--no-upx", action="store_true", help="Skip UPX compression")
    p.add_argument("--name", default="dawei", help="Output binary name (cross-arch: dawei-x86_64)")
    p.add_argument("--workpath", default=None, help="Override PyInstaller work/cache dir (cross-arch)")
    p.add_argument("--runtime-mode", default=None,
                   help="Mode stamp: comma-separated allowed runtime modes (saas,desktop,server,tui). "
                        "Omit for unrestricted dev builds.")
    args = p.parse_args()

    modes = None
    if args.runtime_mode:
        modes = [m.strip() for m in args.runtime_mode.split(",") if m.strip()]

    build(clean=args.clean, use_upx=not args.no_upx, name=args.name,
          workpath=args.workpath, runtime_modes=modes)
