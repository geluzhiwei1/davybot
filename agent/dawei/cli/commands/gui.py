# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""GUI Command - Launch the Dawei desktop GUI application"""

import os
import platform
import subprocess
import sys
from pathlib import Path

import click


def _get_gui_executable() -> Path | None:
    """Locate the bundled dawei-gui binary for the current platform."""
    system = platform.system().lower()   # 'linux', 'darwin', 'windows'
    machine = platform.machine().lower() # 'x86_64', 'aarch64', 'arm64', 'amd64'

    # Normalise architecture naming
    if machine == "arm64":
        machine = "aarch64"
    elif machine == "amd64":
        machine = "x86_64"

    if system == "windows":
        exe_name = f"dawei-gui-windows-{machine}.exe"
    else:
        exe_name = f"dawei-gui-{system}-{machine}"

    # Search order:
    #   1. Bundled inside the installed package  (dawei/bin/<name>)
    #   2. Same directory as this Python executable (editable installs / dev)
    search_paths: list[Path] = [
        Path(__file__).parent.parent.parent / "bin" / exe_name,   # package bin/
        Path(sys.executable).parent / exe_name,                    # venv Scripts/ or bin/
    ]

    for candidate in search_paths:
        if candidate.is_file():
            return candidate

    return None


@click.command(name="gui", help="Launch the Dawei desktop GUI application")
@click.option("--no-server", is_flag=True, help="Do not start the backend server automatically")
@click.option(
    "--port",
    "-p",
    type=int,
    default=8465,
    show_default=True,
    help="Backend server port (passed to the GUI)",
)
def gui_cmd(no_server: bool, port: int) -> None:
    """Launch the bundled Dawei GUI (Tauri desktop application).

    The GUI binary is shipped inside the Python package at ``dawei/bin/``.
    On first launch the binary is made executable if necessary.
    """
    exe = _get_gui_executable()

    if exe is None:
        system = platform.system().lower()
        machine = platform.machine().lower()
        if machine == "arm64":
            machine = "aarch64"
        elif machine == "amd64":
            machine = "x86_64"
        expected = f"dawei-gui-{system}-{machine}" + (".exe" if system == "windows" else "")
        click.echo(
            click.style("❌ GUI binary not found.", fg="red", bold=True),
            err=True,
        )
        click.echo(
            f"   Expected binary name : {click.style(expected, fg='cyan')}",
            err=True,
        )
        click.echo(
            f"   Looked inside        : {click.style(str(Path(__file__).parent.parent.parent / 'bin'), fg='cyan')}",
            err=True,
        )
        click.echo(
            "   Make sure you installed the correct platform wheel or run from source.",
            err=True,
        )
        sys.exit(1)

    # Ensure executable bit is set (may be lost on some extraction paths)
    if sys.platform != "win32" and not os.access(exe, os.X_OK):
        try:
            exe.chmod(exe.stat().st_mode | 0o111)
        except OSError as exc:
            click.echo(
                click.style(f"⚠️  Could not set executable bit on {exe}: {exc}", fg="yellow"),
                err=True,
            )

    cmd: list[str] = [str(exe)]
    if no_server:
        cmd.append("--no-server")
    cmd += ["--port", str(port)]

    click.echo(click.style("🖥️  Launching Dawei GUI...", fg="green", bold=True))
    click.echo(f"   Binary : {exe}")
    click.echo(f"   Port   : {port}")
    click.echo()

    try:
        # Replace current process with the GUI on Unix; use Popen on Windows
        # so the terminal is freed immediately.
        if sys.platform == "win32":
            proc = subprocess.Popen(cmd, close_fds=True)
            sys.exit(proc.wait())
        else:
            os.execv(str(exe), cmd)
    except OSError as exc:
        click.echo(
            click.style(f"❌ Failed to launch GUI: {exc}", fg="red", bold=True),
            err=True,
        )
        sys.exit(1)


def main() -> None:
    """Standalone entry point: ``davybot-gui`` / ``dawei-gui-launcher``."""
    gui_cmd(standalone_mode=True)
