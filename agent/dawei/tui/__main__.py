# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei TUI - Entry Point

Main entry point for running the Dawei TUI.
Usage:
    python -m dawei.tui --workspace ./my-workspace --mode ask

Logging Strategy:
    ----------------
    TUI uses a two-phase logging configuration:

    Phase 1: Early Logging (before workspace initialization)
        - Purpose: Capture startup and configuration errors
        - Output: Console only (stderr)
        - Config: Simple format with level INFO
        - Location: This file (lines 33-38)

    Phase 2: Full Logging (after workspace initialization)
        - Purpose: Complete logging system with file output
        - Output: Console + File (DAWEI_HOME/logs/tui/)
        - Config: Rich format with session/message context
        - Location: setup_tui_logging() called in main()
        - Behavior: Replaces Phase 1 completely (clears handlers)

    Note: Any logs between Phase 1 and Phase 2 will only appear in console,
          not in log files. This is intentional to avoid file I/O before
          we know the workspace path.
"""

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

# 设置TUI模式标志，防止WebSocket服务器初始化
os.environ["DAWEI_TUI_MODE"] = "true"

# 设置全屏模式
os.environ["TEXTUAL_FULLSCREEN"] = "1"

from dawei.tui.app import GeweiTUIApp
from dawei.tui.config import create_tui_config

# ============================================================================
# Monkey-Patch LinuxDriver for proper terminal size handling
# ============================================================================
# The LinuxDriver._get_terminal_size() needs to:
# 1. Use initial size parameter for startup (self._size)
# 2. But also detect runtime terminal size changes for auto-resize
# 3. We track if this is the first call to use initial size, then use real detection
_patch_logger = logging.getLogger(f"{__name__}.patch")


def _patch_linux_driver():
    """Patch LinuxDriver to properly handle terminal size"""
    try:
        import shutil

        from textual.drivers.linux_driver import LinuxDriver

        # CRITICAL: Disable in-band window resize to force SIGWINCH usage
        # This ensures our _get_terminal_size() patch is called on terminal resize
        original_start = LinuxDriver.start_application_mode

        def patched_start_application_mode(self) -> None:
            """Patched start that disables in-band window resize"""
            _patch_logger.info("✓ Disabling in-band window resize to force SIGWINCH usage")
            # Call original start
            original_start(self)
            # Force disable in-band window resize
            if self._in_band_window_resize:
                _patch_logger.info("  - In-band resize was enabled, disabling now")
                self._disable_in_band_window_resize()
                self._in_band_window_resize = False

        LinuxDriver.start_application_mode = patched_start_application_mode

        original_get_terminal_size = LinuxDriver._get_terminal_size
        call_count = [0]  # Use list to allow modification in closure

        def patched_get_terminal_size(self) -> tuple[int, int]:
            """Get terminal size with adaptive resize support"""
            call_count[0] += 1
            call_num = call_count[0]

            # Debug: Log every call
            _patch_logger.debug(f"[PATCH CALL #{call_num}] _get_terminal_size called")
            _patch_logger.debug(f"[PATCH CALL #{call_num}] hasattr(self, '_size'): {hasattr(self, '_size')}")
            if hasattr(self, "_size"):
                _patch_logger.debug(f"[PATCH CALL #{call_num}] self._size: {self._size}")
            _patch_logger.debug(f"[PATCH CALL #{call_num}] hasattr(self, '_size_used'): {hasattr(self, '_size_used')}")

            # Use initial size parameter only on first call
            if hasattr(self, "_size") and self._size is not None and not hasattr(self, "_size_used"):
                self._size_used = True
                # First call - use initial size for proper startup
                _patch_logger.info(f"[PATCH CALL #{call_num}] FIRST CALL - Using initial size: {self._size}")
                return self._size

            # After first call, always detect actual terminal size for auto-resize
            # This ensures TUI adapts to terminal size changes during runtime
            try:
                width, height = shutil.get_terminal_size()
                if width and height:
                    _patch_logger.info(f"[PATCH CALL #{call_num}] Runtime detection - Real terminal size: {width}x{height}")
                    return width, height
            except (AttributeError, ValueError, OSError) as e:
                _patch_logger.warning(f"[PATCH CALL #{call_num}] Failed to detect terminal size: {e}")

            # Fallback to original behavior or defaults
            _patch_logger.warning(f"[PATCH CALL #{call_num}] Falling back to original implementation")
            result = original_get_terminal_size(self)
            _patch_logger.debug(f"[PATCH CALL #{call_num}] Original implementation returned: {result}")
            return result

        LinuxDriver._get_terminal_size = patched_get_terminal_size
        _patch_logger.info("✓ LinuxDriver._get_terminal_size patched successfully")
        _patch_logger.info("  - First call will use size parameter")
        _patch_logger.info("  - Subsequent calls will use real-time terminal size detection")
        _patch_logger.info("  - In-band window resize will be disabled to force SIGWINCH")
    except ImportError:
        _patch_logger.exception("Failed to import LinuxDriver: ")
    except Exception as e:
        _patch_logger.error(f"Unexpected error patching LinuxDriver: {e}", exc_info=True)


_patch_linux_driver()

# ============================================================================
# Phase 1: Early Logging Configuration
# ============================================================================
# Purpose: Capture startup messages before workspace is available
# Scope: Console output only (stderr)
# Note: This will be replaced by setup_tui_logging() in Phase 2
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
    force=True,  # Ensure clean configuration (Python 3.8+)
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for dawei.tui"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Dawei TUI - Terminal User Interface for Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (LLM and mode loaded from config)
  dawei tui --workspace ./my-workspace

  # Specify mode and model (optional)
  dawei tui --workspace ./my-workspace --mode build --llm glm

  # Verbose logging
  dawei tui --workspace ./my-workspace --verbose

Notes:
  --workspace is REQUIRED
  --llm and --mode are OPTIONAL (default: load from workspace config)
  Available modes: plan, build
        """,
    )

    parser.add_argument(
        "--workspace",
        "-w",
        required=True,
        help="Path to workspace directory (REQUIRED)",
    )

    parser.add_argument(
        "--llm",
        "-l",
        default="",
        help="LLM model to use (optional, default: load from workspace config)",
    )

    parser.add_argument(
        "--mode",
        "-m",
        default="",
        choices=["plan", "build"],
        help="Agent mode (optional, default: load from workspace config)",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    parser.add_argument(
        "--refresh-rate",
        type=float,
        default=0.1,
        help="UI refresh rate in seconds (default: 0.1)",
    )

    parser.add_argument(
        "--super",
        action="store_true",
        help="⚠️  Enable super mode (bypass all security checks)",
    )

    args = parser.parse_args()

    # Configure super mode if enabled
    if args.super:
        import os

        os.environ["GEWEI_SUPER_MODE"] = "1"
        print()
        print("⚠️  WARNING: SUPER MODE ENABLED")
        print("   All security checks will be BYPASSED!")
        print("   Use with EXTREME CAUTION!")
        print()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
        # Also enable DEBUG for patch logger
        logging.getLogger(f"{__name__}.patch").setLevel(logging.DEBUG)

    # Always set patch logger to at least INFO to see important messages
    patch_logger = logging.getLogger(f"{__name__}.patch")
    if args.verbose:
        patch_logger.setLevel(logging.DEBUG)
    else:
        patch_logger.setLevel(logging.INFO)

    # Create config
    logger.info("Creating TUI configuration...")
    config = create_tui_config(
        workspace=args.workspace,
        llm=args.llm,
        mode=args.mode,
        verbose=args.verbose,
        refresh_rate=args.refresh_rate,
    )

    # Validate config
    logger.info("Validating configuration...")
    is_valid, error_msg = config.validate()
    if not is_valid:
        logger.error(f"Configuration error: {error_msg}")
        print(f"❌ Configuration error: {error_msg}", file=sys.stderr)
        sys.exit(1)

    # Ensure workspace initialized
    logger.info("Ensuring workspace is initialized...")
    try:
        config.ensure_workspace_initialized()
    except (FileNotFoundError, PermissionError, OSError) as e:
        # File system errors - workspace path issues
        logger.error(f"Workspace file system error: {e}", exc_info=True)
        print(f"❌ Workspace error: {e}", file=sys.stderr)
        sys.exit(1)
    except (ValueError, TypeError) as e:
        # Configuration validation errors
        logger.error(f"Workspace configuration error: {e}", exc_info=True)
        print(f"❌ Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected workspace initialization error: {e}", exc_info=True)
        print(f"❌ Failed to initialize workspace: {e}", file=sys.stderr)
        sys.exit(1)

    # ============================================================================
    # Phase 2: Full Logging Configuration
    # ============================================================================
    # Now that workspace is available, setup complete logging system:
    # - Replaces Phase 1 early logging (clears all handlers)
    # - Adds UTF-8 console output with sensitive data filtering
    # - Adds file logging to workspace/.dawei/logs/ or DAWEI_HOME/logs/tui/
    # - Enables session/message context tracking
    # - Separate error log file for exceptions
    # ============================================================================
    logger.info("Setting up full TUI logging system...")
    try:
        from dawei.logg.tui_logging import setup_tui_logging

        workspace_path = Path(config.workspace).resolve()
        setup_tui_logging(
            workspace_path=workspace_path,
            verbose=args.verbose,
            log_to_file=True,
        )

        # Log the successful setup (now using the full logging system)
        from dawei.config.logging_config import get_tui_error_log_path, get_tui_log_path

        log_path = get_tui_log_path(workspace_path)
        error_log_path = get_tui_error_log_path(workspace_path)

        logger.info("✓ Full TUI logging system configured")
        logger.info(f"  Main log: {log_path}")
        logger.info(f"  Error log: {error_log_path}")

    except Exception as e:
        # If full logging setup fails, continue with Phase 1 early logging
        logger.warning(f"Failed to setup full logging: {e}")
        logger.warning("Continuing with early logging (console only)")
        logger.warning("Log files will not be created")

    # Run TUI app
    logger.info("Starting Dawei TUI...")
    try:
        app = GeweiTUIApp(config)
        # 设置为全屏（使用终端完整大小）
        terminal_size = shutil.get_terminal_size()
        logger.info(f"[INIT] Detected terminal size: {terminal_size.columns}x{terminal_size.lines}")
        logger.info(f"[INIT] Passing size to app.run(): ({terminal_size.columns}, {terminal_size.lines})")

        # Log patch logger status
        patch_logger = logging.getLogger(f"{__name__}.patch")
        logger.info(f"[INIT] Patch logger level: {patch_logger.level}")
        logger.info(f"[INIT] Root logger level: {logging.getLogger().level}")

        app.run(size=(terminal_size.columns, terminal_size.lines))
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down...")
        print("\n👋 Goodbye!")
    except (ImportError, ModuleNotFoundError) as e:
        # Missing dependencies - clear error message
        logger.error(f"TUI dependency error: {e}", exc_info=True)
        print(f"❌ Missing dependencies: {e}", file=sys.stderr)
        print("Please install required dependencies: pip install -e .", file=sys.stderr)
        sys.exit(1)
    except (ValueError, TypeError) as e:
        # Configuration/initialization errors
        logger.error(f"TUI initialization error: {e}", exc_info=True)
        print(f"❌ Initialization error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Unexpected errors - log with full trace
        logger.error(f"Unexpected error running TUI: {e}", exc_info=True)
        print(f"❌ Error running TUI: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
