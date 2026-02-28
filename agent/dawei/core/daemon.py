# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-0-only

"""Daemon Manager - Process daemonization and PID file management

Provides cross-platform daemonization with proper PID file management.
"""

import os
import sys
from pathlib import Path


def get_pid_file_path(port: int, pid_dir: Path | None = None) -> Path:
    """Get the PID file path for a given port.

    Args:
        port: Server port number
        pid_dir: Custom PID directory (defaults to ~/.dawei/run)

    Returns:
        Path to PID file
    """
    if pid_dir is None:
        # Default to ~/.dawei/run
        home_dir = Path.home()
        pid_dir = home_dir / ".dawei" / "run"

    # Create directory if it doesn't exist
    pid_dir.mkdir(parents=True, exist_ok=True)

    return pid_dir / f"dawei-server-{port}.pid"


def write_pid_file(pid_file: Path, pid: int | None = None) -> None:
    """Write PID to file.

    Args:
        pid_file: Path to PID file
        pid: Process ID (defaults to current process)
    """
    if pid is None:
        pid = os.getpid()

    pid_file.write_text(str(pid))


def read_pid_file(pid_file: Path) -> int | None:
    """Read PID from file.

    Args:
        pid_file: Path to PID file

    Returns:
        PID if file exists and contains valid PID, None otherwise
    """
    if not pid_file.exists():
        return None

    try:
        pid_str = pid_file.read_text().strip()
        return int(pid_str)
    except (ValueError, IOError):
        return None


def remove_pid_file(pid_file: Path) -> bool:
    """Remove PID file.

    Args:
        pid_file: Path to PID file

    Returns:
        True if removed, False otherwise
    """
    try:
        if pid_file.exists():
            pid_file.unlink()
        return True
    except OSError:
        return False


def is_process_running(pid: int) -> bool:
    """Check if a process with given PID is running.

    Args:
        pid: Process ID

    Returns:
        True if process is running, False otherwise
    """
    if sys.platform == "win32":
        import ctypes

        SYNCHRONIZE = 0x100000
        PROCESS_QUERY_INFORMATION = 0x0400

        try:
            handle = ctypes.windll.kernel32.OpenProcess(
                SYNCHRONIZE | PROCESS_QUERY_INFORMATION, False, pid
            )
            if handle == 0:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    else:
        # Unix-like systems: send signal 0 to check
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def check_pid_file(pid_file: Path) -> tuple[bool, int | None]:
    """Check if PID file exists and process is running.

    Args:
        pid_file: Path to PID file

    Returns:
        Tuple of (is_running, pid)
    """
    pid = read_pid_file(pid_file)
    if pid is None:
        return (False, None)

    if is_process_running(pid):
        return (True, pid)
    else:
        # Stale PID file, remove it
        remove_pid_file(pid_file)
        return (False, None)


def daemonize(
    stdin: str = "/dev/null",
    stdout: str = "/dev/null",
    stderr: str = "/dev/null",
) -> None:
    """Daemonize the current process.

    This implements the Unix double-fork magic to ensure the daemon
    is completely detached from the parent process.

    Args:
        stdin: File to redirect stdin to
        stdout: File to redirect stdout to
        stderr: File to redirect stderr to

    Note:
        This function only works on Unix-like systems. On Windows,
        it will raise NotImplementedError.
    """
    if sys.platform == "win32":
        raise NotImplementedError(
            "Daemon mode is not supported on Windows. "
            "Use a service manager like NSSM or run as a background service."
        )

    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent exits
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"First fork failed: {e}\n")
        sys.exit(1)

    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent exits
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Second fork failed: {e}\n")
        sys.exit(1)

    # Redirect file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    si = open(stdin, "r")
    so = open(stdout, "a+")
    se = open(stderr, "a+")

    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


def create_log_file(log_dir: Path | None = None, port: int = 8465) -> Path:
    """Create log directory and return log file path.

    Args:
        log_dir: Custom log directory (defaults to ~/.dawei/logs)
        port: Server port for log file naming

    Returns:
        Path to log file
    """
    if log_dir is None:
        # Default to ~/.dawei/logs
        home_dir = Path.home()
        log_dir = home_dir / ".dawei" / "logs"

    # Create directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)

    return log_dir / f"dawei-server-{port}.log"
