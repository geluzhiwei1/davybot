# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""TUI Command - Start the Terminal User Interface"""

from pathlib import Path

import click


@click.command(name="tui", help="Start the Terminal User Interface")
@click.option(
    "--workspace",
    "-w",
    type=click.Path(path_type=Path),
    required=True,
    help="[REQUIRED] Path to workspace directory (will be created if it doesn't exist)",
)
@click.option(
    "--llm",
    "-l",
    default=None,  # None means load from workspace config
    show_default=False,  # No default shown, will be loaded from config
    help="[OPTIONAL] LLM model to use (if not specified, loaded from workspace config)",
)
@click.option(
    "--mode",
    "-m",
    default=None,  # None means load from workspace config
    show_default=False,  # No default shown, will be loaded from config
    help="[OPTIONAL] Agent mode: plan or build (if not specified, loaded from workspace config)",
)
@click.option(
    "--refresh-rate",
    type=float,
    default=0.1,
    show_default=True,
    help="UI refresh rate in seconds",
)
@click.option(
    "--theme",
    type=click.Choice(["default", "dark", "light"]),
    default="default",
    show_default=True,
    help="UI theme",
)
@click.option("--super", is_flag=True, help="⚠️  Enable super mode (bypass all security)")
@click.pass_context
def tui_cmd(ctx, workspace, llm, mode, refresh_rate, theme, super):
    """Start the Dawei Terminal User Interface (TUI).

    The TUI provides a full-featured terminal-based interface with:
    - Interactive chat with autocomplete
    - Real-time agent thinking display
    - Tool execution tracking
    - Settings management
    - Command palette (Ctrl+P)
    """
    verbose = ctx.obj.get("verbose", False)
    # Check if super mode is enabled globally or per-command
    super_mode = super or ctx.obj.get("super", False)

    # Create workspace directory if it doesn't exist
    if not workspace.exists():
        workspace.mkdir(parents=True, exist_ok=True)
        click.echo(click.style(f"✓ Created workspace directory: {workspace}", fg="green"))

    click.echo(click.style("🖥️  Starting Dawei TUI", fg="cyan", bold=True))
    click.echo(f"   Workspace: {workspace}")
    # Note: llm and mode might be None here, they'll be loaded from config
    if llm:
        click.echo(f"   LLM: {llm}")
    else:
        click.echo("   LLM: <from config>")
    if mode:
        click.echo(f"   Mode: {mode}")
    else:
        click.echo("   Mode: <from config>")
    click.echo(f"   Theme: {theme}")

    if super_mode:
        click.echo()
        click.echo(click.style("⚠️  SUPER MODE ENABLED", fg="yellow", bold=True))
        click.echo(click.style("   Security checks DISABLED", fg="red", bold=True))

    click.echo()

    try:
        # Import TUI module
        import os
        import sys

        from dawei.tui.__main__ import main as tui_main

        # Set super mode environment variable
        if super_mode:
            os.environ["GEWEI_SUPER_MODE"] = "1"

        # Prepare arguments for TUI
        # Build sys.argv with only the arguments that have values
        sys.argv = [
            "dawei-tui",
            "--workspace",
            str(workspace),
        ]

        # Only add --llm if specified (not None)
        if llm is not None:
            sys.argv.extend(["--llm", llm])

        # Only add --mode if specified (not None)
        if mode is not None:
            sys.argv.extend(["--mode", mode])

        # Add refresh rate
        sys.argv.extend(["--refresh-rate", str(refresh_rate)])

        if verbose:
            sys.argv.append("--verbose")
        if super_mode:
            sys.argv.append("--super")

        # Start TUI
        tui_main()

    except ImportError as e:
        click.echo(
            click.style(
                f"❌ Error: TUI module not found or dependencies missing\n   Details: {e}\n\n   To install TUI dependencies:\n   pip install 'dawei-agent[tui]'",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo()
        click.echo(click.style("⚠️  TUI closed by user", fg="yellow"))
        sys.exit(0)
    except Exception as e:
        click.echo(click.style(f"❌ Error starting TUI: {e}", fg="red"), err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)
