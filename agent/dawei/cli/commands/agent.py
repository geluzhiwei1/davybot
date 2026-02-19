# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agent Command - Run agent directly bypassing HTTP/WebSocket"""

import sys
import time
from pathlib import Path

import click


from dotenv import find_dotenv, load_dotenv

env_path = find_dotenv()
if env_path:
    load_dotenv(env_path, override=True)


@click.group(name="agent", help="Agent operations (direct execution, bypass HTTP)")
def agent_cmd():
    """Agent command group"""


@agent_cmd.command(name="run", help="Run agent task directly")
@click.argument("workspace", type=click.Path(path_type=Path))
@click.argument("message", type=str)
@click.option(
    "--llm",
    "-l",
    default="deepseek/deepseek-chat",
    show_default=True,
    help="LLM model to use",
)
@click.option(
    "--mode",
    "-m",
    default="orchestrator",
    show_default=True,
    help="Agent mode (orchestrator, plan, do, check, act)",
)
@click.option(
    "--timeout",
    "-t",
    type=int,
    default=1800,
    show_default=True,
    help="Execution timeout in seconds (default: 1800, 30 minutes)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Save result to file")
@click.option("--super", is_flag=True, help="⚠️  Enable super mode (bypass all security)")
@click.pass_context
def agent_run(ctx, workspace, message, llm, mode, timeout, verbose, output, super):
    """Run an agent task directly without HTTP/WebSocket.

    This command executes the agent synchronously in the current process,
    bypassing the web server for faster execution.

    Examples:
        # Simple task
        dawei agent run ./my-ws "Create hello world"

        # With specific mode
        dawei agent run ./my-ws "Design API" --mode architect

        # With verbose output
        dawei agent run ./my-ws "Explain PDCA" --verbose

        # Save result to file
        dawei agent run ./my-ws "Write report" --output result.txt

        # With super mode (bypass security)
        dawei agent run ./my-ws "Dangerous task" --super

    """
    # Check if super mode is enabled globally or per-command
    super_mode = super or ctx.obj.get("super", False)

    # Create workspace directory if it doesn't exist
    if not workspace.exists():
        workspace.mkdir(parents=True, exist_ok=True)
        click.echo(click.style(f"✓ Created workspace directory: {workspace}", fg="green"))

    click.echo(click.style("🤖 Running Agent Task", fg="blue", bold=True))
    click.echo(f"   Workspace: {workspace}")
    click.echo(f"   LLM: {llm}")
    click.echo(f"   Mode: {mode}")
    click.echo(f"   Message: {message[:80]}{'...' if len(message) > 80 else ''}")
    click.echo(f"   Timeout: {timeout}s")

    if super_mode:
        click.echo()
        click.echo(click.style("⚠️  SUPER MODE ENABLED", fg="yellow", bold=True))
        click.echo(click.style("   Security checks DISABLED", fg="red", bold=True))

    click.echo()

    try:
        # Import runner
        import os

        from dawei.cli.runner import run_agent_sync

        # Set super mode environment variable
        if super_mode:
            os.environ["GEWEI_SUPER_MODE"] = "1"

        # Execute agent
        start_time = time.time()

        with click.progressbar(
            length=100,
            label="Executing",
            show_pos=True,
            fill_char=click.style("█", fg="blue"),
            empty_char="░",
        ) as bar:
            # This is a fake progress bar since we can't easily track real progress
            # In a real implementation, you'd want to hook into the agent's events
            result = run_agent_sync(
                workspace=str(workspace),
                llm=llm,
                mode=mode,
                message=message,
                verbose=verbose,
                timeout=timeout,
            )

            # Update progress bar to 100%
            bar.update(100)

        duration = time.time() - start_time

        # Display result
        click.echo()

        if result["success"]:
            click.echo(click.style("✅ Execution completed successfully", fg="green", bold=True))
            click.echo(f"   Duration: {duration:.2f} seconds")

            # Save output if requested
            if output:
                output.write_text(f"Execution completed in {duration:.2f}s\n")
                click.echo(f"   Output saved to: {output}")

            sys.exit(0)
        else:
            click.echo(click.style("❌ Execution failed", fg="red", bold=True))
            click.echo(f"   Message: {result['message']}")
            if result.get("error"):
                click.echo(f"   Error: {result['error']}")

            if output:
                output.write_text(f"Execution failed: {result.get('error', 'Unknown error')}\n")
                click.echo(f"   Output saved to: {output}")

            sys.exit(1)

    except FileNotFoundError as e:
        click.echo(click.style(f"❌ Error: {e}", fg="red"), err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(click.style(f"❌ Configuration error: {e}", fg="red"), err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo()
        click.echo(click.style("⚠️  Execution interrupted by user", fg="yellow"))
        sys.exit(130)
    except Exception as e:
        click.echo(click.style(f"❌ Error: {e}", fg="red"), err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@agent_cmd.command(name="modes", help="List available agent modes")
def agent_modes():
    """List all available agent modes with descriptions"""
    modes = {
        "orchestrator": "[PDCA] Intelligent coordinator for PDCA cycles - works across all domains",
        "plan": "[PDCA] Understand, explore, design, and plan - universal preparation phase",
        "do": "[PDCA] Execute the plan - universal implementation phase",
        "check": "[PDCA] Verify and validate results - universal quality assurance phase",
        "act": "[PDCA] Improve, standardize, and decide next steps - universal closure phase",
    }

    click.echo(click.style("Available Agent Modes", fg="cyan", bold=True))
    click.echo()

    for mode, description in modes.items():
        # Color mode name
        mode_colored = click.style(mode.ljust(15), fg="blue", bold=True)
        click.echo(f"{mode_colored} {description}")

    click.echo()
    click.echo("Usage: dawei agent run <workspace> <message> --mode <mode>")


@agent_cmd.command(name="validate", help="Validate workspace configuration")
@click.argument("workspace", type=click.Path(path_type=Path))
def agent_validate(workspace):
    """Validate workspace configuration and setup"""
    # Create workspace directory if it doesn't exist
    if not workspace.exists():
        workspace.mkdir(parents=True, exist_ok=True)
        click.echo(click.style(f"✓ Created workspace directory: {workspace}", fg="green"))

    click.echo(click.style("🔍 Validating Workspace", fg="cyan", bold=True))
    click.echo(f"   Path: {workspace}")
    click.echo()

    issues = []

    # Check .dawei directory
    dawei_dir = workspace / ".dawei"
    if not dawei_dir.exists():
        issues.append("Missing .dawei directory")
    else:
        click.echo(click.style("   ✅ .dawei directory exists", fg="green"))

        # Check subdirectories
        subdirs = ["chat-history", "checkpoints"]
        for subdir in subdirs:
            subdir_path = dawei_dir / subdir
            if subdir_path.exists():
                click.echo(click.style(f"   ✅ {subdir}/ exists", fg="green"))
            else:
                issues.append(f"Missing {subdir}/ directory")

    # Check .env file
    env_file = workspace / ".env"
    if not env_file.exists():
        issues.append("Missing .env file")
        click.echo(click.style("   ⚠️  No .env file found", fg="yellow"))
    else:
        click.echo(click.style("   ✅ .env file exists", fg="green"))

    # Check for settings.json
    settings_file = dawei_dir / "settings.json"
    if settings_file.exists():
        click.echo(click.style("   ✅ settings.json exists", fg="green"))
    else:
        click.echo(click.style("   ℹ️  No settings.json (will use defaults)", fg="blue"))

    click.echo()

    if issues:
        click.echo(click.style(f"⚠️  Found {len(issues)} issue(s):", fg="yellow"))
        for issue in issues:
            click.echo(f"   - {issue}")
        sys.exit(1)
    else:
        click.echo(click.style("✅ Workspace is properly configured!", fg="green", bold=True))
        sys.exit(0)
