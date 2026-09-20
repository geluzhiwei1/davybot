#!/usr/bin/env python3
"""
generate-update-manifest.py — 生成 Tauri v2 updater 所需的 latest.json

扫描构建产物目录，读取各平台安装包签名（.sig 文件），
生成符合 Tauri v2 updater 规范的 latest.json 清单。

用法:
    python scripts/generate-update-manifest.py \\
        --version 0.2.0 \\
        --channel community \\
        --artifacts-dir src-tauri/target/release/bundle/ \\
        --base-url https://releases.normnomos.com/desktop/ \\
        --output latest.json \\
        --notes "## v0.2.0 更新内容" \\
        --pub-date 2026-06-15T10:00:00Z

依赖: Python 3.10+ (stdlib only, no external deps)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ===================================================================
# Platform signatures: how to map platform+arch to Tauri target/arch
# ===================================================================

PLATFORM_KEY_MAP = {
    # (os_name, arch)  →  key in latest.json "platforms"
    ("linux", "x86_64"): "linux-x86_64",
    ("linux", "aarch64"): "linux-aarch64",
    ("darwin", "aarch64"): "darwin-aarch64",
    ("darwin", "x86_64"): "darwin-x86_64",
    ("windows", "x86_64"): "windows-x86_64",
    ("windows", "aarch64"): "windows-aarch64",
}

# Installer extensions per platform
INSTALLER_PATTERNS = {
    "linux-x86_64": (".AppImage.tar.gz", ".AppImage.tar.gz.sig"),
    "linux-aarch64": (".AppImage.tar.gz", ".AppImage.tar.gz.sig"),
    "darwin-aarch64": (".dmg.tar.gz", ".dmg.tar.gz.sig"),
    "darwin-x86_64": (".dmg.tar.gz", ".dmg.tar.gz.sig"),
    "windows-x86_64": (".nsis.zip", ".nsis.zip.sig"),
    "windows-aarch64": (".nsis.zip", ".nsis.zip.sig"),
}


# ===================================================================
# Helpers
# ===================================================================

def find_artifact(
    artifacts_dir: Path, platform_key: str, version: str
) -> tuple[Optional[Path], Optional[Path], Optional[int]]:
    """
    Find the installer file and signature file for a platform.

    Returns (artifact_path, sig_path, size_bytes).
    """
    suffix, sig_suffix = INSTALLER_PATTERNS.get(platform_key, ("", ""))

    # Search recursively for matching artifacts
    for root, _dirs, files in os.walk(artifacts_dir):
        for fname in files:
            if fname.endswith(suffix) and not fname.endswith(sig_suffix):
                artifact_path = Path(root) / fname
                sig_path = Path(root) / (fname + ".sig")
                if sig_path.exists() and artifact_path.exists():
                    return (
                        artifact_path,
                        sig_path,
                        artifact_path.stat().st_size,
                    )

    # Fallback: look for any artifact without signature
    for root, _dirs, files in os.walk(artifacts_dir):
        for fname in files:
            if fname.endswith(suffix) and not fname.endswith(sig_suffix):
                artifact_path = Path(root) / fname
                return (artifact_path, None, artifact_path.stat().st_size)

    return (None, None, None)


def guess_platforms(artifacts_dir: Path) -> list[str]:
    """Guess which platforms are available in the artifacts dir."""
    found = []
    for platform_key in PLATFORM_KEY_MAP.values():
        suffix, _ = INSTALLER_PATTERNS.get(platform_key, ("", ""))
        if not suffix:
            continue
        found_files = list(artifacts_dir.rglob(f"*{suffix}"))
        if found_files:
            found.append(platform_key)
    return found


# ===================================================================
# Manifest generation
# ===================================================================

def generate_manifest(
    version: str,
    channel: str,
    artifacts_dir: Path,
    base_url: str,
    notes: str = "",
    pub_date: str = "",
) -> dict:
    """Build the latest.json manifest dict."""
    if not pub_date:
        pub_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Make sure base_url ends with /version/channel/
    base_url = base_url.rstrip("/")

    manifest = {
        "version": version,
        "notes": notes,
        "pub_date": pub_date,
        "platforms": {},
    }

    platforms = guess_platforms(artifacts_dir)
    if not platforms:
        print(f"[warn] No platform artifacts found in {artifacts_dir}", file=sys.stderr)
        return manifest

    for platform_key in platforms:
        artifact, sig_file, size = find_artifact(artifacts_dir, platform_key, version)

        if artifact is None:
            print(f"[warn] No artifact for {platform_key}", file=sys.stderr)
            continue

        artifact_name = artifact.name
        url = f"{base_url}/{version}/{channel}/{artifact_name}"

        platform_entry: dict = {
            "url": url,
            "size": size or 0,
        }

        if sig_file and sig_file.exists():
            sig_content = sig_file.read_text(encoding="utf-8").strip()
            platform_entry["signature"] = sig_content

        manifest["platforms"][platform_key] = platform_entry
        print(f"  {platform_key}: {artifact_name} ({size} bytes)")

    return manifest


# ===================================================================
# CLI
# ===================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Tauri v2 update manifest (latest.json)"
    )
    parser.add_argument(
        "--version", required=True, help='Version string, e.g. "0.2.0"'
    )
    parser.add_argument(
        "--channel",
        default="community",
        choices=["community", "enterprise", "beta"],
        help="Update channel (default: community)",
    )
    parser.add_argument(
        "--artifacts-dir",
        required=True,
        help="Path to bundled artifacts directory",
    )
    parser.add_argument(
        "--base-url",
        default="https://releases.normnomos.com/desktop",
        help="Base URL for release downloads",
    )
    parser.add_argument(
        "--output", "-o", default="latest.json", help="Output file path"
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Release notes (plain text or Markdown)",
    )
    parser.add_argument(
        "--pub-date",
        default="",
        help='Publication date in ISO 8601 format (default: now), e.g. "2026-06-15T10:00:00Z"',
    )

    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    if not artifacts_dir.exists():
        print(f"Error: artifacts dir not found: {artifacts_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Generating latest.json for v{args.version} ({args.channel})")
    print(f"Artifacts dir: {artifacts_dir}")

    manifest = generate_manifest(
        version=args.version,
        channel=args.channel,
        artifacts_dir=artifacts_dir,
        base_url=args.base_url.rstrip("/"),
        notes=args.notes,
        pub_date=args.pub_date,
    )

    if not manifest.get("platforms"):
        print("[warn] No platform entries in manifest — upload may fail", file=sys.stderr)

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nWritten to: {output_path.resolve()}")


if __name__ == "__main__":
    main()
