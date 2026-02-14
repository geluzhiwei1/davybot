# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Toast Notifications Widget

Provides non-intrusive notification popups for user feedback.
Uses Textual's built-in notification system with custom styling.
"""

import logging
from enum import Enum

from textual.app import App

logger = logging.getLogger(__name__)


class ToastLevel(Enum):
    """Toast notification levels"""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class ToastManager:
    """Manager for showing toast notifications

    Provides a simple interface for displaying notifications
    with consistent styling and behavior.

    Example:
        ```python
        toast = ToastManager(app)
        toast.info("File saved successfully")
        toast.success("Operation completed")
        toast.warning("Low disk space")
        toast.error("Failed to connect")
        ```
    """

    def __init__(self, app: App):
        """Initialize ToastManager

        Args:
            app: Textual App instance
        """
        self.app = app

    def _show_toast(
        self,
        message: str,
        level: ToastLevel,
        title: str | None = None,
        duration: float | None = None,
    ) -> None:
        """Show a toast notification

        Args:
            message: Notification message
            level: Notification level (info, success, warning, error)
            title: Optional title
            duration: Duration in seconds (None for default)
        """
        try:
            # Set default durations based on level
            default_durations = {
                ToastLevel.INFO: 3.0,
                ToastLevel.SUCCESS: 2.5,
                ToastLevel.WARNING: 4.0,
                ToastLevel.ERROR: 5.0,
            }

            duration = duration or default_durations.get(level, 3.0)

            # Set default titles
            default_titles = {
                ToastLevel.INFO: "ℹ️ Info",
                ToastLevel.SUCCESS: "✓ Success",
                ToastLevel.WARNING: "⚠ Warning",
                ToastLevel.ERROR: "✗ Error",
            }

            title = title or default_titles.get(level, "Notification")

            # Map level to Toast severity
            severity_map = {
                ToastLevel.INFO: "information",
                ToastLevel.SUCCESS: "information",  # Toast doesn't have success level
                ToastLevel.WARNING: "warning",
                ToastLevel.ERROR: "error",
            }

            severity = severity_map.get(level, "information")

            # Show the toast
            self.app.notify(
                message,
                title=title,
                severity=severity,
                timeout=duration,
            )

            logger.debug(f"Shown toast: {level.value} - {message}")

        except Exception as e:
            # Toast failures should not crash the app
            logger.error(f"Failed to show toast notification: {e}", exc_info=True)

    def info(self, message: str, title: str | None = None, duration: float | None = None) -> None:
        """Show info notification

        Args:
            message: Notification message
            title: Optional title (default: "ℹ️ Info")
            duration: Duration in seconds (default: 3.0)
        """
        self._show_toast(message, ToastLevel.INFO, title, duration)

    def success(self, message: str, title: str | None = None, duration: float | None = None) -> None:
        """Show success notification

        Args:
            message: Notification message
            title: Optional title (default: "✓ Success")
            duration: Duration in seconds (default: 2.5)
        """
        self._show_toast(message, ToastLevel.SUCCESS, title, duration)

    def warning(self, message: str, title: str | None = None, duration: float | None = None) -> None:
        """Show warning notification

        Args:
            message: Notification message
            title: Optional title (default: "⚠ Warning")
            duration: Duration in seconds (default: 4.0)
        """
        self._show_toast(message, ToastLevel.WARNING, title, duration)

    def error(self, message: str, title: str | None = None, duration: float | None = None) -> None:
        """Show error notification

        Args:
            message: Notification message
            title: Optional title (default: "✗ Error")
            duration: Duration in seconds (default: 5.0)
        """
        self._show_toast(message, ToastLevel.ERROR, title, duration)


# Convenience function for quick access
def show_toast(
    app: App,
    message: str,
    level: str = "info",
    title: str | None = None,
    duration: float | None = None,
) -> None:
    """Quick function to show a toast notification

    Args:
        app: Textual App instance
        message: Notification message
        level: Notification level (info, success, warning, error)
        title: Optional title
        duration: Duration in seconds

    Example:
        ```python
        show_toast(app, "File saved", "success")
        show_toast(app, "Error occurred", "error", duration=10)
        ```
    """
    try:
        level_enum = ToastLevel(level.lower())
        manager = ToastManager(app)
        manager._show_toast(message, level_enum, title, duration)
    except ValueError:
        logger.warning(f"Invalid toast level: {level}, using 'info'")
        manager = ToastManager(app)
        manager.info(message, title, duration)
    except Exception as e:
        logger.error(f"Failed to show toast: {e}", exc_info=True)
