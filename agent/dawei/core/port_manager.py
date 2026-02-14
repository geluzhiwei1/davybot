# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Port Manager - Check and manage port usage

Provides cross-platform functionality to:
- Check if a port is in use
- Find process using a port
- Kill process using a port
"""

import socket
import subprocess
import sys

import click


def is_port_in_use(port: int, host: str = "0.0.0.0") -> bool:
    """Check if a port is already in use.

    Args:
        port: Port number to check
        host: Host address (default: 0.0.0.0)

    Returns:
        True if port is in use, False otherwise

    """
    try:
        # Try to bind to the port WITHOUT SO_REUSEADDR
        # This will fail if the port is already in use
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # Note: We don't set SO_REUSEADDR here because it allows
            # multiple binds to the same address (especially on Windows)
            s.bind((host, port))
            return False  # Successfully bound, so port was free
    except OSError:
        return True  # Failed to bind, so port is in use
    except Exception as e:
        # Log unexpected errors for debugging
        import logging
        logging.getLogger(__name__).warning(f"Unexpected error checking port {port}: {e}", exc_info=True)
        return False  # Assume port is free on unexpected errors


def find_process_using_port(port: int) -> tuple[int, str] | None:
    """Find the process using the specified port.

    Args:
        port: Port number to check

    Returns:
        Tuple of (pid, process_name) if found, None otherwise

    """
    try:
        if sys.platform == "win32":
            # Windows: use netstat
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, check=True)

            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    # Format: Proto  Local Address          Foreign Address        State           PID
                    local_address = parts[1]
                    pid = parts[-1]

                    if f":{port}" in local_address:
                        # Found the port, get process name
                        try:
                            task_result = subprocess.run(
                                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                                capture_output=True,
                                text=True,
                                check=True,
                            )
                            lines = task_result.stdout.splitlines()
                            if len(lines) > 1:
                                # Parse CSV line
                                process_name = lines[1].split(",")[0].strip('"')
                                return (int(pid), process_name)
                        except Exception as e:
                            # Log subprocess failure but still return PID
                            import logging
                            logging.getLogger(__name__).warning(f"Failed to get process name for PID {pid}: {e}", exc_info=True)
                            return (int(pid), "unknown")

        else:
            # Linux/macOS: use lsof
            result = subprocess.run(
                ["lsof", "-i", f":{port}", "-P", "-n"],
                capture_output=True,
                text=True,
                check=False,  # lsof returns non-zero if nothing found
            )

            if result.returncode == 0 and result.stdout:
                lines = result.stdout.splitlines()
                if len(lines) > 1:
                    # Skip header, parse first result
                    # Format: COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME
                    parts = lines[1].split()
                    if len(parts) >= 2:
                        process_name = parts[0]
                        pid = int(parts[1])
                        return (pid, process_name)

    except Exception as e:
        click.echo(click.style(f"⚠️  Warning: Failed to check port: {e}", fg="yellow"), err=True)

    return None


def kill_process_using_port(port: int, force: bool = False) -> bool:
    """Kill the process using the specified port.

    Args:
        port: Port number
        force: If True, force kill without asking

    Returns:
        True if successful, False otherwise

    """
    process_info = find_process_using_port(port)

    if not process_info:
        click.echo(click.style(f"✅ Port {port} is free", fg="green"))
        return True

    pid, process_name = process_info

    click.echo()
    click.echo(click.style(f"⚠️  Port {port} is in use", fg="yellow"))
    click.echo(f"   Process: {process_name} (PID: {pid})")

    if not force:
        # Ask user for confirmation
        click.echo()
        if not click.confirm(
            click.style("Do you want to kill this process?", fg="yellow"),
            default=True,
        ):
            click.echo(click.style("❌ Aborted. Port is still in use.", fg="red"))
            return False

    try:
        if sys.platform == "win32":
            # Windows: use taskkill
            result = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
                check=True,
            )
            if result.returncode == 0:
                click.echo(
                    click.style(
                        f"✅ Successfully killed process {pid} ({process_name})",
                        fg="green",
                    ),
                )
                return True

        else:
            # Linux/macOS: use kill
            result = subprocess.run(
                ["kill", "-9", str(pid)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                click.echo(
                    click.style(
                        f"✅ Successfully killed process {pid} ({process_name})",
                        fg="green",
                    ),
                )
                return True

        click.echo(click.style(f"❌ Failed to kill process {pid}", fg="red"), err=True)
        return False

    except Exception as e:
        click.echo(click.style(f"❌ Error killing process: {e}", fg="red"), err=True)
        return False


def kill_all_processes_on_port(port: int) -> int:
    """Kill all processes using the specified port (sometimes multiple processes bind to same port).

    Args:
        port: Port number

    Returns:
        Number of processes killed

    """
    killed_count = 0

    # Try multiple times in case there are multiple processes
    max_attempts = 5
    for _ in range(max_attempts):
        process_info = find_process_using_port(port)
        if not process_info:
            break

        if kill_process_using_port(port, force=True):
            killed_count += 1
        else:
            break

    return killed_count
