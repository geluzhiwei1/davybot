# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Session History Screen

Display and manage chat session history.
"""

import logging
from datetime import datetime
from typing import Any

from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static


class SessionHistoryScreen(Screen):
    """Session history screen"""

    BINDINGS = [
        ("escape", "pop_screen", "Close"),
        ("enter", "load_selected", "Load"),
        ("d", "delete_selected", "Delete"),
    ]

    CSS = """
    SessionHistoryScreen {
        align: center middle;
    }

    #history_container {
        width: 90%;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }

    #sessions_table {
        height: 1fr;
    }

    .button-row {
        height: 3;
        dock: bottom;
    }

    #info_panel {
        height: 3;
        margin-top: 1;
        border-top: solid $primary;
        padding-top: 1;
    }
    """

    def __init__(self, sessions: list[dict[str, Any]], **kwargs):
        """Initialize session history screen

        Args:
            sessions: List of session summaries

        """
        super().__init__(**kwargs)
        self.sessions = sessions
        self.selected_session: dict[str, Any] | None = None

    def compose(self):
        """Compose history screen UI"""
        yield Header()

        with Vertical(id="history_container"):
            yield Static("[bold cyan]Chat Session History[/bold cyan]")
            yield Static(f"Found {len(self.sessions)} session(s)")

            yield DataTable(id="sessions_table")

            yield Static(id="info_panel")

            with Horizontal(classes="button-row"):
                yield Button("Load (Enter)", id="load_button", variant="primary")
                yield Button("Delete (D)", id="delete_button", variant="error")
                yield Button("Close (Esc)", id="close_button", variant="default")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize after mount"""
        table = self.query_one("#sessions_table", DataTable)

        # Add columns
        table.add_columns("Session ID", "Created", "Updated", "Messages")

        # Populate rows
        for session in self.sessions:
            created = self._format_date(session["created_at"])
            updated = self._format_date(session["updated_at"])

            table.add_row(
                session["session_id"],
                created,
                updated,
                str(session["message_count"]),
                key=session["session_id"],
            )

        # Focus table
        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection

        Args:
            event: Row selected event

        """
        table = event.data_table
        row_key = event.row_key if hasattr(event, "row_key") else event.row_key

        if row_key is not None:
            row_index = list(table.rows.keys()).index(row_key)
            if row_index < len(self.sessions):
                self.selected_session = self.sessions[row_index]
                self._update_info()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlight

        Args:
            event: Row highlighted event

        """
        table = event.data_table
        row_key = event.row_key

        if row_key is not None:
            row_index = list(table.rows.keys()).index(row_key)
            if row_index < len(self.sessions):
                self.selected_session = self.sessions[row_index]
                self._update_info()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press

        Args:
            event: Button pressed event

        """
        button_id = event.button.id

        if button_id == "load_button":
            self.action_load_selected()
        elif button_id == "delete_button":
            self.action_delete_selected()
        elif button_id == "close_button":
            self.dismiss(None)

    def action_load_selected(self) -> None:
        """Load selected session"""
        if self.selected_session:
            session_id = self.selected_session["session_id"]
            logger = logging.getLogger(__name__)
            logger.info(f"[LOAD] action_load_selected called with session_id: {session_id}")
            # Close the history screen first
            self.app.pop_screen()
            logger.info("[LOAD] Screen popped")
            # Then call the app's load action
            # We need to call this asynchronously after screen is closed
            self.app.call_after_refresh(self._trigger_load, session_id)
            logger.info("[LOAD] Scheduled _trigger_load")

    def _trigger_load(self, session_id: str) -> None:
        """Trigger load session action after screen is closed

        Args:
            session_id: Session ID to load
        """
        logger = logging.getLogger(__name__)
        logger.info(f"[LOAD] _trigger_load called with session_id: {session_id}")
        # Import to avoid circular dependency
        from asyncio import create_task

        # Get the app and call the async load action
        if hasattr(self.app, "action_load_session"):
            logger.info("[LOAD] Creating task for action_load_session")
            create_task(self.app.action_load_session(session_id))
        else:
            logger.error("[LOAD] ERROR: app does not have action_load_session!")

    def action_delete_selected(self) -> None:
        """Delete selected session"""
        if self.selected_session:
            session_id = self.selected_session["session_id"]
            # Close the history screen first
            self.app.pop_screen()
            # Then call the app's delete action
            # We need to call this asynchronously after screen is closed
            self.app.call_after_refresh(self._trigger_delete, session_id)

    def _trigger_delete(self, session_id: str) -> None:
        """Trigger delete session action after screen is closed

        Args:
            session_id: Session ID to delete
        """
        # Import to avoid circular dependency
        from asyncio import create_task

        # Get the app and call the async delete action
        if hasattr(self.app, "action_delete_session"):
            create_task(self.app.action_delete_session(session_id))

    def _format_date(self, date_str: str) -> str:
        """Format date string

        Args:
            date_str: ISO date string

        Returns:
            Formatted date

        """
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return date_str[:16]

    def _update_info(self) -> None:
        """Update info panel"""
        if not self.selected_session:
            return

        info = self.query_one("#info_panel", Static)

        session = self.selected_session
        text = f"[bold]Session:[/bold] {session['session_id']}\n"
        text += f"[dim]Created:[/dim] {self._format_date(session['created_at'])} | "
        text += f"[dim]Messages:[/dim] {session['message_count']}"

        info.update(text)
