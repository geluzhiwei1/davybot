#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copy resources script for Tauri bundling
Ensures Python environment and scripts are available for bundling
"""

import os
import shutil
import sys
from pathlib import Path

def copy_resources():
    """Copy resources to Tauri target directory"""

    # Force UTF-8 encoding for Windows
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    # Paths
    project_root = Path(__file__).parent.parent
    web_dir = project_root / "apps" / "web"
    tauri_dir = web_dir / "src-tauri"
    target_resources = tauri_dir / "target" / "release" / "resources"

    print("========================================")
    print("  Copying Resources for Bundling")
    print("========================================")
    print()

    # Ensure target resources directory exists
    target_resources.mkdir(parents=True, exist_ok=True)

    # Copy Python environment
    python_env_src = tauri_dir / "resources" / "python-env"
    python_env_dst = target_resources / "python-env"

    print("[1/3] Copying Python environment...")
    print(f"  Source: {python_env_src}")
    print(f"  Target: {python_env_dst}")

    if python_env_src.exists():
        if python_env_dst.exists():
            shutil.rmtree(python_env_dst)

        shutil.copytree(python_env_src, python_env_dst)

        # Calculate size
        size = sum(f.stat().st_size for f in python_env_dst.rglob('*') if f.is_file())
        size_mb = size / (1024 * 1024)

        print(f"  [OK] Copied {size_mb:.1f} MB")
    else:
        print(f"  [WARN] Source not found")

    # Copy backend scripts
    print()
    print("[2/3] Copying backend scripts...")

    scripts = [
        "start-backend.bat",
        "stop-backend.bat",
        "start-backend.sh",
        "stop-backend.sh"
    ]

    for script in scripts:
        src = tauri_dir / script
        dst = target_resources / script

        if src.exists():
            shutil.copy2(src, dst)
            print(f"  [OK] {script}")
        else:
            print(f"  [WARN] {script} not found")

    # Copy icon
    print()
    print("[3/3] Copying icon...")

    icon_src = tauri_dir / "icons" / "icon.ico"
    icon_dst = target_resources / "icon.ico"

    if icon_src.exists():
        shutil.copy2(icon_src, icon_dst)
        print(f"  [OK] icon.ico")
    else:
        print(f"  [WARN] icon.ico not found")

    print()
    print("========================================")
    print("  [OK] Resource Copy Complete")
    print("========================================")

    return 0

if __name__ == "__main__":
    try:
        sys.exit(copy_resources())
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
