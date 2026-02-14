#!/usr/bin/env python3
# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei TUI - Quick Start Script

Quick setup and launch for Dawei TUI.
"""

import argparse
import os
import sys
from pathlib import Path


def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import textual

        print(f"✓ Textual installed (version {textual.__version__})")
        return True
    except ImportError:
        print("✗ Textual not installed")
        print("\nPlease install Textual:")
        print("  uv pip install textual")
        return False


def setup_workspace(workspace_path: str) -> bool:
    """Setup workspace directory structure

    Args:
        workspace_path: Path to workspace

    Returns:
        True if successful

    """
    workspace = Path(workspace_path).resolve()

    try:
        # Create workspace directory
        workspace.mkdir(parents=True, exist_ok=True)
        print(f"✓ Workspace directory: {workspace}")

        # Create .dawei subdirectories
        gewei_dir = workspace / ".dawei"
        gewei_dir.mkdir(exist_ok=True)

        (gewei_dir / "tools").mkdir(exist_ok=True)
        (gewei_dir / "checkpoints").mkdir(exist_ok=True)
        (gewei_dir / "plan").mkdir(exist_ok=True)

        print("✓ .dawei structure created")

        # Create .gitkeep files
        (gewei_dir / "tools" / ".gitkeep").touch()
        (gewei_dir / "checkpoints" / ".gitkeep").touch()
        (gewei_dir / "plan" / ".gitkeep").touch()

        return True

    except (OSError, PermissionError) as e:
        print(f"✗ Failed to setup workspace: {e}")
        return False


def check_env_vars():
    """Check if required environment variables are set"""
    required_vars = []
    optional_vars = ["LITELLM_API_KEY", "LITELLM_MODEL"]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    optional_missing = [var for var in optional_vars if not os.getenv(var)]

    if missing_vars:
        print(f"✗ Missing required environment variables: {', '.join(missing_vars)}")
        return False

    if optional_missing:
        print(f"⚠ Optional environment variables not set: {', '.join(optional_missing)}")
        print("  You can set these in your .env file")

    return True


def main():
    """Main quick start function"""
    parser = argparse.ArgumentParser(
        description="Dawei TUI - Quick Start",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick start with default settings
  python quick_start.py

  # Specify workspace
  python quick_start.py --workspace ./my-project

  # Run with custom model
  python quick_start.py --llm openai/gpt-4 --mode architect
        """,
    )

    parser.add_argument(
        "--workspace",
        "-w",
        default="./dawei-workspace",
        help="Workspace path (default: ./dawei-workspace)",
    )

    parser.add_argument(
        "--mode",
        "-m",
        default="plan",
        choices=["plan", "build"],
        help="Agent mode (default: plan)",
    )

    parser.add_argument(
        "--llm",
        "-l",
        default="deepseek/deepseek-chat",
        help="LLM model (default: deepseek/deepseek-chat)",
    )

    parser.add_argument("--skip-checks", action="store_true", help="Skip dependency checks")

    args = parser.parse_args()

    print("=" * 60)
    print("Dawei TUI - Quick Start")
    print("=" * 60)

    # Check dependencies
    if not args.skip_checks:
        print("\n[1/3] Checking dependencies...")
        if not check_dependencies():
            sys.exit(1)

    # Setup workspace
    print("\n[2/3] Setting up workspace...")
    if not setup_workspace(args.workspace):
        sys.exit(1)

    # Check environment
    print("\n[3/3] Checking environment...")
    check_env_vars()

    # Launch TUI
    print("\n" + "=" * 60)
    print("Starting Dawei TUI...")
    print("=" * 60)
    print(f"  Workspace: {args.workspace}")
    print(f"  Mode: {args.mode}")
    print(f"  Model: {args.llm}")
    print("=" * 60)
    print("\nPress Ctrl+H in the TUI for help\n")

    # Import and run
    from dawei.tui.app import GeweiTUIApp
    from dawei.tui.config import create_tui_config

    config = create_tui_config(
        workspace=args.workspace,
        llm=args.llm,
        mode=args.mode,
        verbose=False,
    )

    app = GeweiTUIApp(config)
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        sys.exit(0)
    except (ImportError, FileNotFoundError, RuntimeError) as e:
        # Fast fail on specific expected errors
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        # Catch-all for unexpected errors
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
