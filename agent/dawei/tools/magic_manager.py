# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Magic Commands Manager

Registry and executor for magic commands.
Inspired by Jupyter Notebook's magic command system.
"""

import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .magic_parser import ParsedMagicCommand

logger = logging.getLogger(__name__)


@dataclass
class MagicContext:
    """Execution context for magic commands"""

    cwd: Path = field(default_factory=Path.cwd)
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    variables: dict[str, Any] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    captures: dict[str, Any] = field(default_factory=dict)
    agent_mode: str = "orchestrator"
    workspace: str = "default"

    def add_to_history(self, command: str):
        """Add command to history"""
        self.history.append(command)
        # Keep only last 1000 commands
        if len(self.history) > 1000:
            self.history = self.history[-1000:]

    def set_variable(self, name: str, value: Any):
        """Set a variable in context"""
        self.variables[name] = value

    def get_variable(self, name: str) -> Any | None:
        """Get a variable from context"""
        return self.variables.get(name)

    def reset_variables(self):
        """Clear all variables"""
        self.variables.clear()


class MagicCommandManager:
    """Registry and executor for magic commands.

    Manages line magics (%), cell magics (%%), and system commands (!).
    """

    def __init__(self):
        # Line magic registry: command_name -> function
        self.line_magics: dict[str, Callable] = {}

        # Cell magic registry: command_name -> function
        self.cell_magics: dict[str, Callable] = {}

        # Command aliases
        self.aliases: dict[str, str] = {}

        # Execution context
        self.context: MagicContext = MagicContext()

        # Register built-in magics
        self._register_builtin_magics()

    def _register_builtin_magics(self):
        """Register all built-in magic commands"""
        # File system magics
        self.register_line_magic("pwd", self._magic_pwd, aliases=["getcwd"])
        self.register_line_magic("cd", self._magic_cd)
        self.register_line_magic("ls", self._magic_ls, aliases=["dir"])
        self.register_line_magic("mkdir", self._magic_mkdir)
        self.register_cell_magic("writefile", self._magic_writefile)
        self.register_cell_magic("appendfile", self._magic_appendfile)
        self.register_line_magic("cat", self._magic_cat)
        self.register_line_magic("head", self._magic_head)
        self.register_line_magic("tail", self._magic_tail)

        # Environment magics
        self.register_line_magic("env", self._magic_env)

        # Code execution magics
        self.register_line_magic("run", self._magic_run)
        self.register_line_magic("time", self._magic_time)
        self.register_cell_magic("timeit", self._magic_cell_timeit)
        self.register_cell_magic("bash", self._magic_cell_bash)
        self.register_cell_magic("python", self._magic_cell_python)

        # Agent control magics
        self.register_line_magic("mode", self._magic_mode)
        self.register_line_magic("tokens", self._magic_tokens)

        # Context management magics
        self.register_line_magic("who", self._magic_who)
        self.register_line_magic("reset", self._magic_reset)
        self.register_line_magic("history", self._magic_history)

    def register_line_magic(
        self,
        name: str,
        func: Callable[[str, MagicContext], str],
        aliases: list[str] | None = None,
    ):
        """Register a line magic command.

        Args:
            name: Command name (without % prefix)
            func: Function that takes (args, context) and returns result
            aliases: Optional list of command aliases

        """
        self.line_magics[name] = func
        if aliases:
            for alias in aliases:
                self.aliases[alias] = name
        logger.debug(f"Registered line magic: %{name}")

    def register_cell_magic(self, name: str, func: Callable[[str, str, MagicContext], str]):
        """Register a cell magic command.

        Args:
            name: Command name (without %% prefix)
            func: Function that takes (args, content, context) and returns result

        """
        self.cell_magics[name] = func
        logger.debug(f"Registered cell magic: %%%{name}")

    def execute(self, parsed: ParsedMagicCommand) -> str:
        """Execute a parsed magic command.

        Args:
            parsed: Parsed magic command object

        Returns:
            Execution result as string

        Raises:
            ValidationError: If command validation fails
            CommandExecutionError: If command execution fails
            RuntimeError: For unexpected errors

        """
        # Add to history
        self.context.add_to_history(parsed.raw_input)

        if parsed.magic_type == "system":
            return self._execute_system_command(parsed.args)

        if parsed.magic_type == "line":
            return self._execute_line_magic(parsed.command, parsed.args)

        if parsed.magic_type == "cell":
            return self._execute_cell_magic(parsed.command, parsed.args, parsed.content or "")

        raise ValueError(f"Unknown magic command type: {parsed.magic_type}")

    def _execute_system_command(self, command: str) -> str:
        """Execute system shell command

        Note on cross-platform compatibility:
        - shell=True uses /bin/sh on Unix and cmd.exe on Windows
        - Commands may need to be adjusted for different platforms
        - Consider using platform detection for platform-specific commands

        Args:
            command: Shell command to execute

        Returns:
            Command output as string

        Raises:
            ValueError: If command is empty
            PermissionError: If execution is not permitted
            FileNotFoundError: If command not found
            RuntimeError: For other execution errors

        """
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")

        result = subprocess.run(
            command,
            shell=True,
            cwd=self.context.cwd,
            capture_output=True,
            text=True,
            env=self.context.env,
        )

        output = []
        if result.stdout:
            output.append(result.stdout)
        if result.stderr:
            output.append(f"STDERR: {result.stderr}")

        output.append(f"Exit code: {result.returncode}")

        return "\n".join(output)

    def _execute_line_magic(self, command: str, args: str) -> str:
        """Execute a line magic command

        Args:
            command: Magic command name
            args: Command arguments

        Returns:
            Execution result

        Raises:
            ValueError: If command is unknown
            RuntimeError: For execution errors

        """
        # Resolve aliases
        actual_command = self.aliases.get(command, command)

        if actual_command not in self.line_magics:
            available = ", ".join(self.line_magics.keys())
            raise ValueError(f"Unknown line magic: %{command}\nAvailable: {available}")

        # Fast Fail: 直接执行，让异常向上传播
        return self.line_magics[actual_command](args, self.context)

    def _execute_cell_magic(self, command: str, args: str, content: str) -> str:
        """Execute a cell magic command

        Args:
            command: Magic command name
            args: Command arguments
            content: Cell content

        Returns:
            Execution result

        Raises:
            ValueError: If command is unknown
            RuntimeError: For execution errors

        """
        if command not in self.cell_magics:
            available = ", ".join(self.cell_magics.keys())
            raise ValueError(f"Unknown cell magic: %%%{command}\nAvailable: {available}")

        # Fast Fail: 直接执行，让异常向上传播
        return self.cell_magics[command](args, content, self.context)

    # ========================================================================
    # Built-in Magic Commands Implementation
    # ========================================================================

    # ---------- File System Magics ----------

    def _magic_pwd(self, _args: str, context: MagicContext) -> str:
        """Print working directory"""
        return str(context.cwd)

    def _magic_cd(self, args: str, context: MagicContext) -> str:
        """Change directory"""
        if not args:
            return f"Current directory: {context.cwd}"

        new_path = Path(args).expanduser()
        if not new_path.is_absolute():
            new_path = context.cwd / new_path

        if not new_path.exists():
            return f"Directory not found: {args}"

        if not new_path.is_dir():
            return f"Not a directory: {args}"

        context.cwd = new_path
        return f"Changed directory to {new_path}"

    def _magic_ls(self, args: str, context: MagicContext) -> str:
        """List directory contents

        Args:
            args: Path argument (optional)
            context: Magic context

        Returns:
            Directory listing

        Raises:
            FileNotFoundError: If path not found
            PermissionError: If access denied

        """
        target_path = context.cwd / args if args else context.cwd

        if not target_path.exists():
            raise FileNotFoundError(f"Path not found: {args}")

        if target_path.is_file():
            return f"📄 {target_path.name}"

        # Fast Fail: 让文件系统异常向上传播
        items = sorted(target_path.iterdir())
        lines = []
        for item in items:
            icon = "📁 " if item.is_dir() else "📄 "
            size = f" ({item.stat().st_size} bytes)" if item.is_file() else ""
            lines.append(f"{icon}{item.name}{size}")
        return "\n".join(lines) if lines else "Empty directory"

    def _magic_mkdir(self, args: str, context: MagicContext) -> str:
        """Create directory

        Args:
            args: Directory path
            context: Magic context

        Returns:
            Success message

        Raises:
            ValueError: If args is empty
            FileExistsError: If path exists and is not a directory
            PermissionError: If creation failed

        """
        if not args:
            raise ValueError("Usage: %mkdir <directory>")

        new_path = Path(args).expanduser()
        if not new_path.is_absolute():
            new_path = context.cwd / new_path

        # Fast Fail: 让文件系统异常向上传播
        new_path.mkdir(parents=True, exist_ok=True)
        return f"Created directory: {new_path}"

    def _magic_writefile(self, args: str, content: str, context: MagicContext) -> str:
        """Write cell content to file

        Args:
            args: Filename
            content: Content to write
            context: Magic context

        Returns:
            Success message

        Raises:
            ValueError: If args is empty
            PermissionError: If write failed

        """
        if not args:
            raise ValueError("Usage: %%writefile <filename>")

        file_path = Path(args).expanduser()
        if not file_path.is_absolute():
            file_path = context.cwd / file_path

        # Fast Fail: 让文件系统异常向上传播
        file_path.write_text(content)
        return f"Wrote {len(content)} bytes to {file_path}"

    def _magic_appendfile(self, args: str, content: str, context: MagicContext) -> str:
        """Append cell content to file

        Args:
            args: Filename
            content: Content to append
            context: Magic context

        Returns:
            Success message

        Raises:
            ValueError: If args is empty
            PermissionError: If append failed

        """
        if not args:
            raise ValueError("Usage: %%appendfile <filename>")

        file_path = Path(args).expanduser()
        if not file_path.is_absolute():
            file_path = context.cwd / file_path

        # Fast Fail: 让文件系统异常向上传播
        with Path(file_path).open("a") as f:
            f.write(content)
        return f"Appended {len(content)} bytes to {file_path}"

    def _magic_cat(self, args: str, context: MagicContext) -> str:
        """Display file contents

        Args:
            args: Filename
            context: Magic context

        Returns:
            File contents

        Raises:
            ValueError: If args is empty
            FileNotFoundError: If file not found
            PermissionError: If read failed

        """
        if not args:
            raise ValueError("Usage: %cat <filename>")

        file_path = Path(args).expanduser()
        if not file_path.is_absolute():
            file_path = context.cwd / file_path

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {args}")

        # Fast Fail: 让文件系统异常向上传播
        return file_path.read_text()

    def _magic_head(self, args: str, context: MagicContext) -> str:
        """Show first n lines of file

        Args:
            args: [n] <filename>
            context: Magic context

        Returns:
            First n lines

        Raises:
            ValueError: If args invalid
            FileNotFoundError: If file not found

        """
        parts = args.split()
        n = 10  # default lines
        file_path = None

        if len(parts) >= 1:
            try:
                n = int(parts[0])
                file_path = parts[1] if len(parts) > 1 else None
            except ValueError:
                file_path = parts[0]
                if len(parts) > 1:
                    n = int(parts[1])

        if not file_path:
            raise ValueError("Usage: %head [n] <filename>")

        file_path = Path(file_path).expanduser()
        if not file_path.is_absolute():
            file_path = context.cwd / file_path

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Fast Fail: 让文件系统异常向上传播
        lines = file_path.read_text().split("\n")
        return "\n".join(lines[:n])

    def _magic_tail(self, args: str, context: MagicContext) -> str:
        """Show last n lines of file

        Args:
            args: [n] <filename>
            context: Magic context

        Returns:
            Last n lines

        Raises:
            ValueError: If args invalid
            FileNotFoundError: If file not found

        """
        parts = args.split()
        n = 10  # default lines
        file_path = None

        if len(parts) >= 1:
            try:
                n = int(parts[0])
                file_path = parts[1] if len(parts) > 1 else None
            except ValueError:
                file_path = parts[0]
                if len(parts) > 1:
                    n = int(parts[1])

        if not file_path:
            raise ValueError("Usage: %tail [n] <filename>")

        file_path = Path(file_path).expanduser()
        if not file_path.is_absolute():
            file_path = context.cwd / file_path

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Fast Fail: 让文件系统异常向上传播
        lines = file_path.read_text().split("\n")
        return "\n".join(lines[-n:])

    # ---------- Environment Magics ----------

    def _magic_env(self, args: str, context: MagicContext) -> str:
        """Get or set environment variables"""
        if not args:
            # List all environment variables (safe ones only)
            safe_vars = {k: v for k, v in context.env.items() if not any(sensitive in k.lower() for sensitive in ["password", "token", "secret", "key"])}
            return "\n".join([f"{k}={v}" for k, v in sorted(safe_vars.items())])

        if "=" in args:
            # Set environment variable
            key, value = args.split("=", 1)
            context.env[key] = value
            return f"Set {key}={value}"
        # Get specific variable
        value = context.env.get(args, "<not set>")
        return f"{args}={value}"

    # ---------- Code Execution Magics ----------

    def _magic_run(self, args: str, context: MagicContext) -> str:
        """Run Python script

        Args:
            args: Script path
            context: Magic context

        Returns:
            Execution output

        Raises:
            ValueError: If args is empty
            FileNotFoundError: If script not found

        """
        if not args:
            raise ValueError("Usage: %run <script.py>")

        script_path = Path(args).expanduser()
        if not script_path.is_absolute():
            script_path = context.cwd / script_path

        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {args}")

        # Fast Fail: 让子进程异常向上传播
        # 使用sys.executable确保跨平台兼容性（Windows可能是python.exe而非python3）
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=context.cwd,
            capture_output=True,
            text=True,
            env=context.env,
        )

        output = [f"Running: {script_path}"]
        if result.stdout:
            output.append(result.stdout)
        if result.stderr:
            output.append(f"STDERR:\n{result.stderr}")
        output.append(f"Exit code: {result.returncode}")

        return "\n".join(output)

    def _magic_time(self, args: str, context: MagicContext) -> str:
        """Time execution of a command

        Note on cross-platform compatibility:
        - shell=True uses /bin/sh on Unix and cmd.exe on Windows
        - Command syntax may need platform-specific adjustments
        """
        if not args:
            return "Usage: %time <command>"

        start = time.perf_counter()
        result = subprocess.run(
            args,
            shell=True,
            cwd=context.cwd,
            capture_output=True,
            text=True,
            env=context.env,
        )
        elapsed = time.perf_counter() - start

        output = [f"Execution time: {elapsed:.4f} seconds"]
        output.append(f"Exit code: {result.returncode}")
        if result.stdout:
            output.append(f"\nSTDOUT:\n{result.stdout}")
        if result.stderr:
            output.append(f"\nSTDERR:\n{result.stderr}")

        return "\n".join(output)

    def _magic_cell_timeit(self, args: str, content: str, _context: MagicContext) -> str:
        """Benchmark code block

        Args:
            args: [number] [repeat]
            content: Code to benchmark
            context: Magic context

        Returns:
            Benchmark results

        Raises:
            ValueError: If code invalid

        """
        number = 10
        repeat = 3

        # Parse args for custom number/repeat
        if args:
            parts = args.split()
            try:
                if len(parts) >= 1:
                    number = int(parts[0])
                if len(parts) >= 2:
                    repeat = int(parts[1])
            except ValueError:
                pass

        import timeit

        # Fast Fail: 让代码执行异常向上传播
        timer = timeit.Timer(stmt=content)
        results = timer.repeat(repeat, number)
        best = min(results)
        avg = sum(results) / len(results)

        output = f"{number} loops, best of {repeat}: {best * 1000:.4f} ms per loop\n"
        output += f"Average: {avg * 1000:.4f} ms per loop"

        return output

    def _magic_cell_bash(self, _args: str, content: str, context: MagicContext) -> str:
        """Execute bash code block

        Note on cross-platform compatibility:
        - This command is primarily designed for Unix/Linux systems
        - On Windows, requires WSL or Git Bash with sh in PATH
        - Consider using %%%writefile for cross-platform script creation

        Args:
            args: (ignored)
            content: Bash code
            context: Magic context

        Returns:
            Command output

        Raises:
            RuntimeError: For execution errors

        """
        # Fast Fail: 让子进程异常向上传播
        result = subprocess.run(
            content,
            shell=True,
            cwd=context.cwd,
            capture_output=True,
            text=True,
            env=context.env,
        )

        output = []
        if result.stdout:
            output.append(result.stdout)
        if result.stderr:
            output.append(f"STDERR:\n{result.stderr}")
        output.append(f"Exit code: {result.returncode}")

        return "\n".join(output)

    def _magic_cell_python(self, _args: str, content: str, context: MagicContext) -> str:
        """Execute Python code block

        Args:
            args: (ignored)
            content: Python code
            context: Magic context

        Returns:
            Execution output

        Raises:
            RuntimeError: For execution errors

        """
        # Capture output
        import sys
        from io import StringIO

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = StringIO()
        sys.stderr = StringIO()

        try:
            # Fast Fail: 让代码执行异常向上传播
            exec(content, {"context": context})
            stdout_value = sys.stdout.getvalue()
            stderr_value = sys.stderr.getvalue()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        output = []
        if stdout_value:
            output.append(stdout_value)
        if stderr_value:
            output.append(f"STDERR:\n{stderr_value}")

        return "\n".join(output) if output else "Code executed successfully (no output)"

    # ---------- Agent Control Magics ----------

    def _magic_mode(self, args: str, context: MagicContext) -> str:
        """Switch agent mode"""
        if not args:
            return f"Current mode: {context.agent_mode}"

        valid_modes = ["orchestrator", "plan", "do", "check", "act"]
        if args not in valid_modes:
            return f"Invalid mode. Valid modes: {', '.join(valid_modes)}"

        context.agent_mode = args
        return f"Switched to mode: {args}"

    def _magic_tokens(self, _args: str, context: MagicContext) -> str:
        """Show token usage information"""
        return f"Token usage information not yet implemented\nContext: {context}"

    # ---------- Context Management Magics ----------

    def _magic_who(self, _args: str, context: MagicContext) -> str:
        """List defined variables"""
        if not context.variables:
            return "No variables defined"

        lines = ["Variables:"]
        for name, value in sorted(context.variables.items()):
            value_type = type(value).__name__
            value_repr = repr(value)[:100]
            lines.append(f"  {name}: {value_type} = {value_repr}")

        return "\n".join(lines)

    def _magic_reset(self, _args: str, context: MagicContext) -> str:
        """Reset context (clear variables)"""
        context.reset_variables()
        return "Context reset (all variables cleared)"

    def _magic_history(self, args: str, context: MagicContext) -> str:
        """Show command history"""
        if args:
            try:
                n = int(args)
                history_slice = context.history[-n:]
            except ValueError:
                return "Usage: %history [n] - Show last n commands"
        else:
            history_slice = context.history[-20:]  # Show last 20 by default

        if not history_slice:
            return "No history yet"

        lines = [f"Command history ({len(history_slice)} most recent):"]
        for i, cmd in enumerate(history_slice, 1):
            lines.append(f"{i:3d}. {cmd}")

        return "\n".join(lines)


# Global singleton instance
_magic_manager: MagicCommandManager | None = None


def get_magic_manager() -> MagicCommandManager:
    """Get or create the global magic command manager"""
    global _magic_manager
    if _magic_manager is None:
        _magic_manager = MagicCommandManager()
    return _magic_manager
