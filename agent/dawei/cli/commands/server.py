# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Server Command - Start the FastAPI web server"""

import sys
import time

import click


@click.group(name="server", help="Server operations")
def server_cmd():
    """Server command group"""


@server_cmd.command(name="start", help="Start the FastAPI web server")
@click.option(
    "--host",
    "-h",
    default="0.0.0.0",
    show_default=True,
    help="Host to bind the server to",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=8465,
    show_default=True,
    help="Port to bind the server to",
)
@click.option("--reload", "-r", is_flag=True, help="Enable auto-reload for development")
@click.option(
    "--workers",
    "-w",
    type=int,
    default=1,
    show_default=True,
    help="Number of worker processes",
)
@click.option(
    "--log-level",
    type=click.Choice(["critical", "error", "warning", "info", "debug"]),
    default="info",
    show_default=True,
    help="Log level",
)
@click.option("--super", is_flag=True, help="⚠️  Enable super mode (bypass all security)")
@click.option("--force-kill", is_flag=True, help="Kill process using the port without asking")
@click.pass_context
def server_start(ctx, host, port, reload, workers, log_level, super, force_kill):
    """Start the Dawei web server with WebSocket support.

    This starts the FastAPI server with REST API and WebSocket endpoints.
    """
    verbose = ctx.obj.get("verbose", False)
    # Check if super mode is enabled globally or per-command
    super_mode = super or ctx.obj.get("super", False)

    click.echo(click.style("🚀 Starting Dawei Server", fg="green", bold=True))
    click.echo(f"   Host: {host}")
    click.echo(f"   Port: {port}")
    click.echo(f"   Reload: {'enabled' if reload else 'disabled'}")
    if workers > 1:
        click.echo(f"   Workers: {workers}")

    if super_mode:
        click.echo()
        click.echo(click.style("⚠️  SUPER MODE ENABLED", fg="yellow", bold=True))
        click.echo(click.style("   Security checks DISABLED", fg="red", bold=True))

    click.echo()

    # Check if port is in use before starting
    from dawei.core.port_manager import (
        find_process_using_port,
        is_port_in_use,
        kill_process_using_port,
    )

    if is_port_in_use(port, host):
        click.echo()
        click.echo(click.style(f"⚠️  Port {port} is already in use!", fg="yellow", bold=True))

        process_info = find_process_using_port(port)
        if process_info:
            pid, process_name = process_info
            click.echo(
                f"   Process: {click.style(process_name, fg='cyan')} (PID: {click.style(str(pid), fg='cyan')})",
            )

            # Auto-kill if --force-kill is specified, otherwise ask user
            should_kill = force_kill
            if not should_kill:
                click.echo()
                should_kill = click.confirm(
                    click.style("Do you want to kill the process and continue?", fg="yellow"),
                    default=True,
                )

            if should_kill:
                if kill_process_using_port(port, force=True):
                    click.echo()
                    click.echo(click.style("✅ Process killed successfully!", fg="green"))
                    click.echo(
                        click.style(
                            "⏳ Waiting 2 seconds for port to be released...",
                            fg="yellow",
                        ),
                    )
                    time.sleep(2)

                    # Double check
                    if is_port_in_use(port, host):
                        click.echo()
                        click.echo(
                            click.style(
                                "❌ Port is still in use. Please check manually.",
                                fg="red",
                            ),
                            err=True,
                        )
                        sys.exit(1)
                else:
                    click.echo()
                    click.echo(
                        click.style(
                            "❌ Failed to kill process. Please check manually.",
                            fg="red",
                        ),
                        err=True,
                    )
                    sys.exit(1)
            else:
                click.echo()
                click.echo(
                    click.style("❌ Aborted. Please free up the port and try again.", fg="red"),
                    err=True,
                )
                sys.exit(1)
        else:
            click.echo()
            click.echo(
                click.style("❌ Could not identify the process using the port.", fg="red"),
                err=True,
            )
            click.echo("   Please check manually and free up the port.")
            sys.exit(1)

    try:
        # Import server module
        import os

        import uvicorn

        from dawei.server import create_app, main

        # Set super mode environment variable
        if super_mode:
            os.environ["GEWEI_SUPER_MODE"] = "1"

        # Create FastAPI app
        app = create_app()

        # Configure uvicorn
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            reload=reload,
            workers=workers if not reload else 1,  # Reload doesn't support multiple workers
            log_level=log_level,
        )

        server = uvicorn.Server(config)

        # Print access URLs
        click.echo(click.style("✅ Server ready!", fg="green", bold=True))
        click.echo()
        click.echo("   🌐 Web UI:     ", nl=False)
        click.echo(click.style(f"http://localhost:{port}/app/", fg="blue", underline=True))
        click.echo("   📚 API Docs:  ", nl=False)
        click.echo(click.style(f"http://localhost:{port}/docs", fg="blue", underline=True))
        click.echo("   🔌 WebSocket: ", nl=False)
        click.echo(click.style(f"ws://localhost:{port}/ws", fg="blue", underline=True))
        click.echo()
        click.echo("Press Ctrl+C to stop the server")
        click.echo()

        # Run server
        server.run()

    except ImportError as e:
        click.echo(
            click.style(f"❌ Error: Failed to import server module: {e}", fg="red"),
            err=True,
        )
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo()
        click.echo(click.style("⚠️  Server stopped by user", fg="yellow"))
        sys.exit(0)
    except Exception as e:
        click.echo(click.style(f"❌ Error starting server: {e}", fg="red"), err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@server_cmd.command(name="stop", help="Stop the running server")
@click.option("--host", "-h", default="0.0.0.0", help="Server host (for port checking)")
@click.option("--port", "-p", type=int, default=8465, help="Server port")
@click.option("--force", "-f", is_flag=True, help="Force stop without confirmation")
def server_stop(host, port, force):
    """Stop the Dawei web server.

    This command will find and kill the process using the specified port.
    """
    from dawei.core.port_manager import (
        find_process_using_port,
        is_port_in_use,
        kill_process_using_port,
    )

    click.echo(click.style("🛑 Stopping Dawei Server", fg="yellow", bold=True))
    click.echo(f"   Host: {host}")
    click.echo(f"   Port: {port}")
    click.echo()

    # Check if port is in use
    if not is_port_in_use(port, host):
        click.echo(click.style(f"✅ No server is running on port {port}", fg="green"))
        return

    # Find process using the port
    process_info = find_process_using_port(port)
    if not process_info:
        click.echo(
            click.style(
                f"⚠️  Port {port} is in use but could not identify the process",
                fg="yellow",
            ),
            err=True,
        )
        return

    pid, process_name = process_info
    click.echo(f"   Found: {click.style(process_name, fg='cyan')} (PID: {click.style(str(pid), fg='cyan')})")
    click.echo()

    # Confirm before killing (unless --force is specified)
    if not force and not click.confirm(
        click.style("Do you want to stop this server?", fg="yellow"),
        default=True,
    ):
        click.echo(click.style("❌ Aborted. Server is still running.", fg="red"))
        return

    # Kill the process
    if kill_process_using_port(port, force=True):
        click.echo()
        click.echo(click.style("✅ Server stopped successfully!", fg="green", bold=True))
    else:
        click.echo()
        click.echo(click.style("❌ Failed to stop the server.", fg="red"), err=True)


@server_cmd.command(name="status", help="Check server status")
@click.option("--host", "-h", default="localhost", help="Server host")
@click.option("--port", "-p", type=int, default=8465, help="Server port")
def server_status(host, port):
    """Check if the server is running"""
    import requests

    url = f"http://{host}:{port}/api/health"

    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            click.echo(click.style("✅ Server is running", fg="green"))
            click.echo(f"   Status: {data.get('status', 'unknown')}")
            click.echo(f"   Service: {data.get('service', 'unknown')}")
            click.echo(f"   Version: {data.get('version', 'unknown')}")
        else:
            click.echo(
                click.style(f"⚠️  Server returned status {response.status_code}", fg="yellow"),
                err=True,
            )
    except requests.exceptions.ConnectionError:
        click.echo(
            click.style("❌ Server is not running or not accessible", fg="red"),
            err=True,
        )
    except Exception as e:
        click.echo(click.style(f"❌ Error checking server: {e}", fg="red"), err=True)
