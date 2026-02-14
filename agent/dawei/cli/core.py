# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""CLI Core Module - Main entry point using Click"""

import sys

import click

from dawei.cli import __version__

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    import codecs

    # Only wrap if stdout/stderr have buffer attribute (avoid double-wrapping)
    if hasattr(sys.stdout, "buffer") and not isinstance(sys.stdout, codecs.StreamWriter):
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    if hasattr(sys.stderr, "buffer") and not isinstance(sys.stderr, codecs.StreamWriter):
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Import command groups to register them
# Import after definition to avoid circular imports
from dawei.cli.commands.agent import agent_cmd
from dawei.cli.commands.server import server_cmd
from dawei.cli.commands.tui import tui_cmd


@click.group(
    name="dawei",
    help="Dawei AI Assistant Platform - Unified CLI",
    epilog="""
Examples:
  dawei server start --port 8465
  dawei server stop --port 8465
  dawei tui --workspace ./my-ws
  dawei agent run ./my-ws "Create hello world"

For more information on a command:
  dawei <command> --help
  dawei <command> <subcommand> --help
    """,
)
@click.version_option(version=__version__, prog_name="dawei")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--config", type=click.Path(exists=True), help="Path to configuration file")
@click.option(
    "--super",
    is_flag=True,
    help="⚠️  ENABLE SUPER MODE - Bypass all security mechanisms (DANGEROUS!)",
)
@click.pass_context
def cli(ctx, verbose, config, super):
    """Dawei AI Assistant Platform - Unified Command Line Interface

    This CLI provides access to all Dawei functionality including:
    - Web server with WebSocket support
    - Terminal User Interface (TUI)
    - Direct agent execution
    """
    # Ensure ctx.obj exists and is a dict
    ctx.ensure_object(dict)

    # Store common options in context
    ctx.obj["verbose"] = verbose
    ctx.obj["config"] = config
    ctx.obj["super"] = super

    # Show super mode warning
    if super:
        click.echo()
        click.echo(click.style("⚠️  WARNING: SUPER MODE ENABLED", fg="yellow", bold=True))
        click.echo(
            click.style("   All security mechanisms will be BYPASSED!", fg="yellow", bold=True),
        )
        click.echo()
        click.echo(click.style("   This mode allows:", fg="red"))
        click.echo(click.style("   • Unrestricted file access (can read/write any path)", fg="red"))
        click.echo(
            click.style("   • Execution of dangerous commands (rm -rf, sudo, etc.)", fg="red"),
        )
        click.echo(click.style("   • Bypass of all permission checks", fg="red"))
        click.echo()
        click.echo(click.style("   Use with EXTREME CAUTION!", fg="red", bold=True))
        click.echo()

    # Configure logging if verbose
    if verbose:
        import logging

        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(sys.stderr)],
        )


# Register command groups with the CLI
cli.add_command(server_cmd)
cli.add_command(tui_cmd)
cli.add_command(agent_cmd)


if __name__ == "__main__":
    cli()
