# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei TUI Application

Main Textual application class for the Dawei TUI.
This is the entry point for the terminal UI.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, ClassVar

# ============================================================================
# CRITICAL FIX: Chinese IME support on Windows
# ============================================================================
# Textual's win32.py driver incorrectly filters out Chinese IME characters.
# This monkey patch fixes the issue at import time.
# ============================================================================
if sys.platform == "win32":
    try:
        import textual.drivers.win32 as win32_drivers

        # Get the original run method
        original_run = win32_drivers.EventMonitor.run

        def patched_run(self):
            """Patched EventMonitor.run() that supports Chinese IME"""
            from ctypes import byref

            from textual import constants
            from textual._xterm_parser import XTermParser

            # Import required components
            kernel32 = win32_drivers.kernel32
            std_input_handle = win32_drivers.std_input_handle
            key_event = 0x0001
            input_record = win32_drivers.input_record
            wait_for_handles = win32_drivers.wait_for_handles

            exit_requested = self.exit_event.is_set
            parser = XTermParser(debug=constants.DEBUG)

            try:
                from ctypes.wintypes import DWORD

                read_count = DWORD(0)
                hIn = kernel32.GetStdHandle(std_input_handle)

                max_events = 1024
                arrtype = input_record * max_events
                input_records = arrtype()
                readconsoleinputw = kernel32.readconsoleinputw
                keys = []
                append_key = keys.append

                while not exit_requested():
                    for event in parser.tick():
                        self.process_event(event)

                    if wait_for_handles([hIn], 100) is None:
                        continue

                    readconsoleinputw(hIn, byref(input_records), max_events, byref(read_count))
                    read_input_records = input_records[: read_count.value]

                    del keys[:]
                    new_size = None

                    for input_record in read_input_records:
                        event_type = input_record.EventType

                        if event_type == KEY_EVENT:
                            key_event = input_record.Event.KeyEvent
                            key = key_event.uChar.UnicodeChar
                            if key_event.bKeyDown:
                                # *** CHINESE IME FIX ***
                                # Only skip if: dwControlKeyState is set AND wVirtualKeyCode==0
                                # AND UnicodeChar is empty (no character to process)
                                # This allows Chinese IME characters to pass through
                                if (
                                    key_event.dwControlKeyState and key_event.wVirtualKeyCode == 0 and not key  # ✅ FIX: Check if UnicodeChar is empty
                                ):
                                    continue
                                append_key(key)
                        elif event_type == WINDOW_BUFFER_SIZE_EVENT:
                            size = input_record.Event.WindowBufferSizeEvent.dwSize
                            new_size = (size.X, size.Y)

                    if keys:
                        for event in parser.feed("".join(keys).encode("utf-16", "surrogatepass").decode("utf-16")):
                            self.process_event(event)
                    if new_size is not None:
                        self.on_size_change(*new_size)

            except Exception as error:
                self.app.log.exception("EVENT MONITOR ERROR", error)

        # Apply the monkey patch
        win32_drivers.EventMonitor.run = patched_run
        print(
            "[PATCH] ✅ Applied Chinese IME fix to Textual Windows driver",
            file=sys.stderr,
            flush=True,
        )
    except Exception as e:
        print(
            f"[PATCH] ⚠️  Failed to apply Chinese IME fix: {e}",
            file=sys.stderr,
            flush=True,
        )
# ============================================================================
# END OF PATCH
# ============================================================================

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer

from dawei.core.events import TaskEventType
from dawei.core.local_context import set_message_id
from dawei.tui.agent_bridge import AgentBridge
from dawei.tui.config import TUIConfig
from dawei.tui.i18n import _, get_current_language, get_system_language, set_language
from dawei.tui.session_manager import SessionManager
from dawei.tui.ui.screens.help_screen import HelpScreen
from dawei.tui.ui.screens.history_screen import SessionHistoryScreen
from dawei.tui.ui.screens.settings_screen import SettingsScreen, TUISettings
from dawei.tui.ui.widgets.autocomplete_input import AutocompleteInputBox
from dawei.tui.ui.widgets.chat_area import ChatArea
from dawei.tui.ui.widgets.command_palette import CommandPalette, get_default_commands
from dawei.tui.ui.widgets.custom_header import CustomHeader
from dawei.tui.ui.widgets.pdca_panel import PDCAPanel
from dawei.tui.ui.widgets.status_bar import StatusBar
from dawei.tui.ui.widgets.thinking_panel import ThinkingPanel
from dawei.tui.ui.widgets.toast_notifications import ToastManager
from dawei.tui.ui.widgets.tool_panel import ToolPanel

logger = logging.getLogger(__name__)

# i18n will be initialized after config is loaded
# This is deferred to allow config-based language selection


class GeweiTUIApp(App):
    """Main TUI Application for Dawei Agent"""

    # CSS 路径 - 使用绝对路径，基于当前文件位置计算
    # 这样可以避免 Textual 在 Windows 上的路径重复问题
    # __file__ = dawei/tui/app.py, 所以 parent 就是 dawei/tui/
    CSS_PATH = str(Path(__file__).parent / "ui" / "themes" / "default.css")

    # Note: BINDINGS are kept in English as they are technical terms
    # and footer space is limited. The UI uses i18n for other elements.
    BINDINGS = [
        # Removed ctrl+c to allow text copying (ctrl+c copies text to clipboard)
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+h", "show_help", "Help"),
        ("f1", "show_help", "Help"),
        ("ctrl+p", "show_command_palette", "Commands"),
        ("ctrl+comma", "show_settings", "Settings"),
        ("ctrl+s", "save_session", "Save Session"),
        ("ctrl+alt+l", "switch_language", "Language"),  # 切换语言
        ("ctrl+alt+t", "toggle_theme", "Theme"),  # 切换主题
        ("ctrl+l", "clear_chat", "Clear Chat"),
        ("ctrl+r", "show_history", "History"),
        ("?", "show_help", "Help"),
    ]

    # Title and subtitle will be set in __init__ after i18n is configured
    TITLE = "Dawei TUI - Agent Terminal Interface"
    SUB_TITLE = "Agent"

    # Event handler registry - maps event types to handler methods
    EVENT_HANDLERS: ClassVar[dict[TaskEventType, str]] = {
        TaskEventType.CONTENT_STREAM: "_handle_content_stream",
        TaskEventType.REASONING: "_handle_reasoning",
        TaskEventType.TOOL_CALL_START: "_handle_tool_start",
        TaskEventType.TOOL_CALL_PROGRESS: "_handle_tool_progress",
        TaskEventType.TOOL_CALL_RESULT: "_handle_tool_result",
        TaskEventType.TASK_STARTED: "_handle_task_started",
        TaskEventType.TASK_COMPLETED: "_handle_task_completed",
        TaskEventType.MODE_SWITCHED: "_handle_mode_switched",
        TaskEventType.ERROR_OCCURRED: "_handle_error",
        TaskEventType.MODEL_SELECTED: "_handle_model_selected",
        TaskEventType.FOLLOWUP_QUESTION: "_handle_followup_question",
        TaskEventType.SKILLS_LOADED: "_handle_skills_loaded",
        TaskEventType.PDCA_CYCLE_STARTED: "_handle_pdca_cycle_started",
        TaskEventType.PDCA_PHASE_ADVANCED: "_handle_pdca_phase_advanced",
        TaskEventType.PDCA_CYCLE_COMPLETED: "_handle_pdca_cycle_completed",
        TaskEventType.PDCA_DOMAIN_DETECTED: "_handle_pdca_domain_detected",
    }

    # Command handler registry - maps command actions to handler methods
    COMMAND_HANDLERS: ClassVar[dict[str, str]] = {
        "pdca.status": "_show_pdca_status",
        "pdca.disable": "_toggle_pdca_off",
        "pdca.enable": "_toggle_pdca_on",
        "nav.chat": "_focus_chat",
        "nav.input": "_focus_input",
        "nav.thinking": "_focus_thinking",
        "nav.tools": "_focus_tools",
        "nav.pdca": "_focus_pdca",
        "view.clear_chat": "action_clear_chat",
        "session.save": "action_save_session",
        "session.load": "action_show_history",
        "settings.open": "action_show_settings",
        "help.show": "action_show_help",
        "agent.stop": "_stop_agent",
    }

    def __init__(self, config: TUIConfig):
        """Initialize Dawei TUI App

        Args:
            config: TUI configuration

        """
        super().__init__()

        # Initialize i18n language from config or auto-detect
        language = config.language if config.language else get_system_language()
        set_language(language)

        # Set translated title and subtitle (after i18n is configured)
        self.TITLE = _("Dawei TUI - Agent Terminal Interface")
        self.SUB_TITLE = _("Agent")

        self.config = config
        self.agent_bridge: AgentBridge | None = None
        self.event_queue: asyncio.Queue | None = None
        self._is_streaming = False

        # Session management
        self.session_manager = SessionManager(config.workspace_absolute)
        self.session_manager.create_session()

        # Settings
        self.settings = TUISettings(
            refresh_rate=config.refresh_rate,
            max_history=config.max_history,
            show_thinking=config.show_thinking,
            show_tools=config.show_tools,
            enable_markdown=config.enable_markdown,
            enable_syntax_highlight=config.enable_syntax_highlight,
        )

        # Toast notification manager (initialized after mount)
        self.toast_manager: ToastManager | None = None

    def compose(self) -> ComposeResult:
        """Compose UI layout"""
        yield CustomHeader()

        # Get workspace path
        workspace_path = Path(self.config.workspace_absolute)

        # Main content area - split horizontally
        yield Horizontal(
            # Left panel (70%): Chat area + Input box
            Vertical(
                ChatArea(id="chat_area"),
                AutocompleteInputBox(
                    id="input_box",
                    placeholder="Type @skill:name or message... (Tab to autocomplete, Enter to send)",
                    workspace_path=workspace_path,
                ),
                id="left_panel",
            ),
            # Right panel (30%): Status + Info
            Vertical(
                StatusBar(id="status_bar"),
                PDCAPanel(id="pdca_panel"),
                ThinkingPanel(id="thinking_panel"),
                ToolPanel(id="tool_panel"),
                id="right_panel",
            ),
            id="main_container",
        )

        yield Footer()

    async def on_mount(self) -> None:
        """Initialize after mount"""
        logger.info("GeweiTUIApp mounted, initializing...")
        logger.info(f"CSS_PATH: {self.CSS_PATH}")

        # Initialize toast notification manager
        self.toast_manager = ToastManager(self)

        # Create event queue for Agent events
        self.event_queue = asyncio.Queue()

        # Create Agent bridge
        logger.info("Creating AgentBridge...")
        try:
            self.agent_bridge = AgentBridge(
                workspace_path=self.config.workspace_absolute,
                llm_model=self.config.llm,
                mode=self.config.mode,
                ui_update_queue=self.event_queue,
            )

            # Initialize Agent and workspace
            logger.info("Initializing Agent and workspace...")
            await self.agent_bridge.initialize()

            # Subscribe to events
            logger.info("Subscribing to Agent events...")
            await self.agent_bridge.subscribe_to_events()
        except Exception as e:
            logger.critical(f"Failed to initialize AgentBridge: {e}", exc_info=True)
            self.toast_manager.error(f"Failed to initialize agent: {e}")
            # Continue anyway - TUI can run without agent

        # Start event polling
        logger.info("Starting event polling...")
        self.set_interval(self.config.refresh_rate, self.poll_agent_events)

        # Update initial status
        self._update_initial_status()

        # Update header connection status
        self._update_header_connection_status()

        # Show welcome message
        self._show_welcome_message()

        # Set focus to input box
        try:
            input_box = self.query_one("#input_box")
            input_box.focus()
            logger.info("Input box focused and ready for input")
        except Exception as e:
            logger.warning(f"Failed to set focus to input box: {e}", exc_info=True)

        logger.info("GeweiTUIApp initialization complete")

    def _update_initial_status(self) -> None:
        """Update initial status bar with mode and model"""
        status_bar = self.query_one("#status_bar", StatusBar)
        status_bar.set_status("Ready")

        logger.info(f"_update_initial_status: mode={self.config.mode}, llm={self.config.llm}")

        status_bar.set_mode(self.config.mode)
        status_bar.set_model(self.config.llm)

    def _update_header_connection_status(self) -> None:
        """Update header connection status"""
        try:
            header = self.query_one(CustomHeader)

            # 根据AgentBridge状态设置连接状态
            if self.agent_bridge:
                # 假设AgentBridge初始化成功就是"Connected"状态
                header.update_status("Connected", "connected")
            else:
                header.update_status("No Agent", "disconnected")

            logger.info("Header connection status updated")
        except Exception as e:
            logger.warning(f"Failed to update header connection status: {e}")

    def _show_welcome_message(self) -> None:
        """Display welcome message to user"""
        chat_area = self.query_one("#chat_area", ChatArea)
        chat_area.add_system_message(
            f"Welcome to Dawei TUI!\nWorkspace: {self.config.workspace_absolute}\nMode: {self.config.mode}\nModel: {self.config.llm}\n\nType your message and press Enter to send.\nType '/help' or '?' to see available commands.\nPress Ctrl+C or Ctrl+Q to quit.",
        )

    async def poll_agent_events(self) -> None:
        """Poll for Agent events and update UI

        This method is called periodically by the event loop
        to check for new events from the Agent.
        """
        try:
            while not self.event_queue.empty():
                event = await asyncio.wait_for(self.event_queue.get(), timeout=0.01)
                self.handle_agent_event(event)
        except TimeoutError:
            # Timeout is expected and normal behavior, don't log
            pass
        except Exception as e:
            # Fast Fail: Critical polling error should stop the application
            logger.critical(f"Fatal error in event polling: {e}", exc_info=True)
            raise RuntimeError("Fatal error in event polling: TUI cannot continue")

    def handle_agent_event(self, event: dict) -> None:
        """Route event to appropriate UI component using event registry

        Args:
            event: Event dictionary with keys:
                - event_type: TaskEventType
                - data: Event data (can be dict or object)
                - task_id: Task ID
                - timestamp: Event timestamp

        """
        try:
            # Validate event structure
            if not isinstance(event, dict):
                raise ValueError(f"Invalid event format: expected dict, got {type(event)}")

            event_type = event.get("event_type")
            data = event.get("data", {})

            if event_type is None:
                raise ValueError("Event missing required 'event_type' field")

            # Debug: Log all events
            logger.info(f"[EVENT] Received event type: {event_type}, data type: {type(data).__name__}")

            # Route to handler using registry
            handler_name = self.EVENT_HANDLERS.get(event_type)
            if handler_name:
                logger.info(f"[EVENT] Routing to handler: {handler_name}")
                handler = getattr(self, handler_name)
                # ✅ 修复：直接传递data对象，不假设它是字典
                handler(data)
            else:
                logger.warning(f"Unknown event type: {event_type}")

        except Exception as e:
            # Fast Fail: Critical event handling errors should propagate
            logger.error(
                f"Fatal error handling event {event.get('event_type', 'unknown')}: {e}",
                exc_info=True,
            )
            # Try to show error to user, then re-raise
            try:
                chat_area = self.query_one("#chat_area", ChatArea)
                chat_area.add_error(f"Event processing error: {e}")
            except Exception:
                pass  # UI might be broken
            # Re-raise to fail fast for critical errors
            raise

    def _get_attr(self, obj: Any, key: str, default: Any = None) -> Any:
        """Helper to get attribute from both dict and object

        Args:
            obj: Dict or object
            key: Attribute/key name
            default: Default value if not found

        Returns:
            Attribute value or default

        """
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _handle_content_stream(self, data: Any) -> None:
        """Handle content stream event

        Args:
            data: Event data with content chunk (dict or object)

        """
        logger.info(f"[CONTENT_STREAM] Handling content stream event: {type(data).__name__}")
        chat_area = self.query_one("#chat_area", ChatArea)

        if not self._is_streaming:
            logger.info("[CONTENT_STREAM] Starting streaming mode")
            self._is_streaming = True
            chat_area.start_streaming()
            status_bar = self.query_one("#status_bar", StatusBar)
            status_bar.set_status("Processing...")

        chunk = self._get_attr(data, "content", "")
        if chunk:
            logger.debug(f"[CONTENT_STREAM] Appending chunk: {chunk[:100]!r}")
            chat_area.append_streaming_content(chunk)

    def _handle_reasoning(self, data: Any) -> None:
        """Handle reasoning/thinking event

        Args:
            data: Event data with reasoning content (dict or object)

        """
        thinking_panel = self.query_one("#thinking_panel", ThinkingPanel)
        reasoning = self._get_attr(data, "content", "") or self._get_attr(data, "reasoning", "")
        if reasoning:
            thinking_panel.add_thinking(reasoning)

    def _handle_tool_start(self, data: Any) -> None:
        """Handle tool call start event

        Args:
            data: Event data with tool info (dict or object)

        """
        tool_panel = self.query_one("#tool_panel", ToolPanel)
        tool_name = self._get_attr(data, "tool_name", "unknown")
        params = self._get_attr(data, "parameters", {})
        tool_panel.start_tool(tool_name, params)

    def _handle_tool_progress(self, data: Any) -> None:
        """Handle tool execution progress event

        Args:
            data: Event data with progress info

        """
        tool_panel = self.query_one("#tool_panel", ToolPanel)
        progress = self._get_attr(data, "progress", "")
        if progress:
            tool_panel.add_tool_info(f"  {progress}")

    def _handle_tool_result(self, data: Any) -> None:
        """Handle tool execution result event

        Args:
            data: Event data with tool result

        """
        tool_panel = self.query_one("#tool_panel", ToolPanel)
        tool_name = self._get_attr(data, "tool_name", "unknown")
        self._get_attr(data, "result", {})
        error = self._get_attr(data, "error")

        success = error is None
        tool_panel.complete_tool(tool_name, success)

        # If there was an error, show it
        if error:
            chat_area = self.query_one("#chat_area", ChatArea)
            chat_area.add_error(f"Tool {tool_name} failed: {error}")

    def _handle_task_started(self, data: Any) -> None:
        """Handle task started event

        Args:
            data: Event data with task info

        """
        status_bar = self.query_one("#status_bar", StatusBar)
        status_bar.set_status("Running")

        task_id = self._get_attr(data, "task_id", "")
        if task_id:
            chat_area = self.query_one("#chat_area", ChatArea)
            chat_area.add_info(f"Task started: {task_id}")

    def _handle_task_completed(self, _data: Any) -> None:
        """Handle task completed event

        Args:
            data: Event data with completion info

        """
        status_bar = self.query_one("#status_bar", StatusBar)
        status_bar.set_status("Idle")

        # End streaming if active
        if self._is_streaming:
            self._is_streaming = False
            chat_area = self.query_one("#chat_area", ChatArea)
            chat_area.end_streaming()

    def _handle_mode_switched(self, data: Any) -> None:
        """Handle mode switched event

        Args:
            data: Event data with new mode

        """
        status_bar = self.query_one("#status_bar", StatusBar)
        new_mode = self._get_attr(data, "new_mode", "")
        if new_mode:
            status_bar.set_mode(new_mode)
            chat_area = self.query_one("#chat_area", ChatArea)
            chat_area.add_info(f"Switched to {new_mode} mode")

    def _handle_error(self, data: Any) -> None:
        """Handle error event

        Args:
            data: Event data with error info

        """
        chat_area = self.query_one("#chat_area", ChatArea)
        error = self._get_attr(data, "error", "Unknown error")
        context = self._get_attr(data, "context", "")
        error_msg = f"Error: {error}"
        if context:
            error_msg += f" (context: {context})"
        chat_area.add_error(error_msg)

        status_bar = self.query_one("#status_bar", StatusBar)
        status_bar.set_status("Error")

    def _handle_model_selected(self, data: Any) -> None:
        """Handle model selected event

        Args:
            data: Event data with model selection

        """
        model = self._get_attr(data, "model", "")
        if model:
            status_bar = self.query_one("#status_bar", StatusBar)
            status_bar.set_model(model)

            chat_area = self.query_one("#chat_area", ChatArea)
            reason = self._get_attr(data, "reason", "")
            chat_area.add_info(f"Model selected: {model} ({reason})")

    def _handle_followup_question(self, data: Any) -> None:
        """Handle followup question event

        Args:
            data: Event data with question

        """
        chat_area = self.query_one("#chat_area", ChatArea)
        question = self._get_attr(data, "question", "")
        if question:
            chat_area.add_system_message(f"Question: {question}")

    def _handle_skills_loaded(self, data: Any) -> None:
        """Handle skills loaded event

        Args:
            data: Event data containing skills list and metadata

        """
        # Validate input data
        if not isinstance(data, dict):
            logger.error("Invalid skills loaded event data: expected dict")
            return

        try:
            skills = self._get_attr(data, "skills", [])
            total_skills = self._get_attr(data, "total_skills", len(skills))

            if not isinstance(skills, list):
                logger.error(f"Invalid skills data: expected list, got {type(skills)}")
                return

            if not skills:
                logger.debug("SKILLS_LOADED event with no skills")
                return

            # Validate chat area exists before trying to use it
            chat_area = self.query_one("#chat_area", ChatArea)

            # Add summary message for all loaded skills
            chat_area.add_skills_loaded_summary(skills, total_skills)

            logger.info(f"Displayed {total_skills} skill(s) loaded in TUI")

        except Exception as e:
            logger.error(f"Error handling skills loaded event: {e}", exc_info=True)
            # Don't crash TUI for skills loading errors

    def _handle_pdca_cycle_started(self, data: Any) -> None:
        """Handle PDCA cycle started event

        Args:
            data: Event data with cycle info

        """
        pdca_panel = self.query_one("#pdca_panel", PDCAPanel)
        status_bar = self.query_one("#status_bar", StatusBar)

        # Update panel
        pdca_panel.set_pdca_active(True)
        pdca_panel.set_domain(self._get_attr(data, "domain", ""))
        pdca_panel.set_current_phase("plan")  # Starts at plan
        pdca_panel.set_cycle_count(0)

        # Update status bar
        status_bar.set_pdca_active(True)
        status_bar.set_pdca_domain(self._get_attr(data, "domain", ""))
        status_bar.set_pdca_phase("plan")

        # Add info message to chat
        chat_area = self.query_one("#chat_area", ChatArea)
        domain = self._get_attr(data, "domain", "unknown")
        self._get_attr(data, "task_description", "")
        chat_area.add_info(f"🔄 PDCA cycle started for {domain.upper()} domain")

        logger.info(f"PDCA cycle started: {self._get_attr(data, 'cycle_id')}")

    def _handle_pdca_phase_advanced(self, data: Any) -> None:
        """Handle PDCA phase advanced event

        Args:
            data: Event data with phase transition info

        """
        pdca_panel = self.query_one("#pdca_panel", PDCAPanel)
        status_bar = self.query_one("#status_bar", StatusBar)

        previous_phase = self._get_attr(data, "previous_phase", "")
        current_phase = self._get_attr(data, "current_phase", "")
        cycle_count = self._get_attr(data, "cycle_count", 0)
        completion = self._get_attr(data, "completion_percentage", 0)

        # Update panel
        pdca_panel.set_current_phase(current_phase)
        pdca_panel.set_cycle_count(cycle_count)
        pdca_panel.set_completion_percentage(completion)

        # Update status bar
        status_bar.set_pdca_phase(current_phase)
        status_bar.set_pdca_completion(completion)

        # Add transition message to chat
        chat_area = self.query_one("#chat_area", ChatArea)
        chat_area.add_info(
            f"🔄 PDCA: {previous_phase.upper()} → {current_phase.upper()} (Cycle {cycle_count}, {completion:.0f}%)",
        )

        logger.info(f"PDCA phase advanced: {previous_phase} -> {current_phase}")

    def _handle_pdca_cycle_completed(self, data: Any) -> None:
        """Handle PDCA cycle completed event

        Args:
            data: Event data with completion report

        """
        pdca_panel = self.query_one("#pdca_panel", PDCAPanel)
        self.query_one("#status_bar", StatusBar)

        # Update panel
        pdca_panel.set_completion_percentage(100)

        # Add completion message to chat
        chat_area = self.query_one("#chat_area", ChatArea)
        cycle_count = self._get_attr(data, "cycle_count", 0)
        self._get_attr(data, "domain", "unknown")
        artifacts = self._get_attr(data, "artifacts", [])
        issues = self._get_attr(data, "issues", [])

        chat_area.add_info(f"✅ PDCA cycle completed after {cycle_count} cycle(s)")

        if artifacts:
            chat_area.add_info(f"Artifacts: {', '.join(artifacts)}")

        if issues:
            chat_area.add_info(f"Issues recorded: {len(issues)}")

        logger.info(f"PDCA cycle completed: {self._get_attr(data, 'cycle_id')}")

    def _handle_pdca_domain_detected(self, data: Any) -> None:
        """Handle PDCA domain detected event

        Args:
            data: Event data with domain info

        """
        domain = self._get_attr(data, "domain", "unknown")
        logger.info(f"PDCA domain detected: {domain}")

        # Optionally show in chat for debugging
        chat_area = self.query_one("#chat_area", ChatArea)
        chat_area.add_system_message(f"Domain detected: {domain.upper()}")

    def on_key(self, event) -> None:
        """FAST FAIL: Intercept ALL key events for debugging Chinese input

        This method is called BEFORE any widget-specific handlers.
        We log everything to diagnose Chinese input issues.

        Args:
            event: Key event from Textual
        """
        # FAST FAIL: Use print() to ensure visibility - don't rely on logging config
        print(f"[APP KEY] key={event.key!r}, char={event.character!r}, is_printable={event.is_printable}")

        # Also log to logger for persistence
        logger.info(f"[APP_KEY_EVENT] key={event.key!r}, char={event.character!r}, is_printable={event.is_printable}, aliases={event.aliases}")

        # Special handling for Chinese characters (non-ASCII printable)
        if event.character and ord(event.character[0]) > 127:
            print(f"[APP KEY] *** NON-ASCII CHARACTER DETECTED ***: {event.character!r} (U+{ord(event.character[0]):04X})")
            logger.warning(f"[CHINESE INPUT] Detected non-ASCII character: {event.character!r} (U+{ord(event.character[0]):04X})")

    async def on_autocomplete_input_box_message_submitted(self, message: AutocompleteInputBox.MessageSubmitted) -> None:
        """Handle user input submission from AutocompleteInputBox

        Args:
            message: Submitted message event

        Note:
            Textual routes Message events by converting the class name to snake_case.
            AutocompleteInputBox.MessageSubmitted -> on_autocomplete_input_box_message_submitted

        """
        logger.info(f"[INPUT] Message submitted: {message.message}")  # DEBUG

        # Validate message input
        if not hasattr(message, "message") or not message.message:
            logger.error("Invalid input message: missing message field")
            return

        user_text = message.message
        if not isinstance(user_text, str) or not user_text.strip():
            logger.error("Invalid input message: empty or non-string")
            return

        logger.info(f"[INPUT] Processing user message: {user_text}")  # DEBUG

        try:
            # Add user message to chat
            chat_area = self.query_one("#chat_area", ChatArea)
            chat_area.add_user_message(user_text)

            # Update status
            status_bar = self.query_one("#status_bar", StatusBar)
            status_bar.set_status("Sending...")

            # Send to Agent - Fast Fail on critical errors
            try:
                logger.info("[INPUT] Sending to AgentBridge...")  # DEBUG
                await self.send_user_message(user_text)
                logger.info("[INPUT] Sent successfully")  # DEBUG
            except Exception as e:
                logger.error(f"Error sending message: {e}", exc_info=True)
                chat_area.add_error(f"Failed to send message: {e}")
                status_bar.set_status("Error")
                return  # Don't continue after sending error

        except Exception as e:
            logger.error(f"Fatal error in input handling: {e}", exc_info=True)
            try:
                chat_area = self.query_one("#chat_area", ChatArea)
                chat_area.add_error(f"Input handling error: {e}")
            except Exception:
                pass  # UI might be broken

    async def send_user_message(self, message: str) -> None:
        """Send user message to Agent

        Args:
            message: User message text

        """
        if self.agent_bridge is None:
            raise RuntimeError("AgentBridge not initialized")

        # Generate message ID for tracking
        import uuid

        message_id = str(uuid.uuid4())[:8]
        set_message_id(message_id)

        logger.info(f"Sending user message (message_id={message_id})")

        await self.agent_bridge.send_message(message)

        # Add to session
        self.session_manager.add_message("user", message)

        # Clear message context after processing
        set_message_id(None)

    def action_show_help(self) -> None:
        """Show help screen"""
        self.push_screen(HelpScreen())

    def action_show_command_palette(self) -> None:
        """Show command palette"""
        commands = get_default_commands()

        def handle_command_result(result: str | None) -> None:
            """Handle command execution result

            Args:
                result: Command action string or None

            """
            if result:
                self._execute_command_action(result)

        self.push_screen(CommandPalette(commands, callback=handle_command_result))

    def _execute_command_action(self, action: str) -> None:
        """Execute command action using command registry

        Args:
            action: Action string (e.g., "mode.plan", "pdca.status")

        """
        # Handle special cases with parameters
        if action.startswith("mode."):
            mode = action.split(".", 1)[1]
            self._switch_mode(mode)
            return

        # Look up handler in registry
        handler_name = self.COMMAND_HANDLERS.get(action)
        if handler_name:
            handler = getattr(self, handler_name)
            # Check if it's a callable method
            if callable(handler):
                handler()
        else:
            logger.warning(f"Unknown command action: {action}")

    def _switch_mode(self, mode: str) -> None:
        """Switch agent mode

        Args:
            mode: Mode to switch to

        """
        # Update status bar
        status_bar = self.query_one("#status_bar", StatusBar)
        status_bar.set_mode(mode)

        # Add info message
        chat_area = self.query_one("#chat_area", ChatArea)
        chat_area.add_info(f"Switched to {mode.upper()} mode")

        # Note: Actual mode switching is handled by Agent internally
        # This is just a visual indication for the user

    def _toggle_pdca_off(self) -> None:
        """Toggle PDCA off"""
        self._toggle_pdca(False)

    def _toggle_pdca_on(self) -> None:
        """Toggle PDCA on"""
        self._toggle_pdca(True)

    def _focus_chat(self) -> None:
        """Focus chat area"""
        chat_area = self.query_one("#chat_area", ChatArea)
        chat_area.focus()

    def _focus_input(self) -> None:
        """Focus input box"""
        input_box = self.query_one("#input_box")
        input_box.focus()

    def _focus_thinking(self) -> None:
        """Focus thinking panel"""
        thinking_panel = self.query_one("#thinking_panel", ThinkingPanel)
        thinking_panel.focus()

    def _focus_tools(self) -> None:
        """Focus tool panel"""
        tool_panel = self.query_one("#tool_panel", ToolPanel)
        tool_panel.focus()

    def _focus_pdca(self) -> None:
        """Focus PDCA panel"""
        pdca_panel = self.query_one("#pdca_panel", PDCAPanel)
        pdca_panel.focus()

    def _show_pdca_status(self) -> None:
        """Show PDCA status in chat"""
        if self.agent_bridge:
            pdca_status = self.agent_bridge.get_pdca_status()
            chat_area = self.query_one("#chat_area", ChatArea)

            if pdca_status and pdca_status.get("active"):
                summary = pdca_status.get("summary", {})
                chat_area.add_info(
                    f"PDCA Status:\n  Phase: {summary.get('current_phase', 'unknown').upper()}\n  Domain: {summary.get('domain', 'unknown').upper()}\n  Cycle: {summary.get('cycle_count', 0)}\n  Completion: {summary.get('completion_percentage', 0):.0f}%",
                )
            else:
                chat_area.add_info("PDCA cycle is not active")

    def _toggle_pdca(self, enabled: bool) -> None:
        """Toggle PDCA on/off

        Args:
            enabled: Whether to enable PDCA

        """
        if self.agent_bridge and self.agent_bridge.pdca_extension:
            if enabled:
                self.agent_bridge.pdca_extension.enable_pdca()
                chat_area = self.query_one("#chat_area", ChatArea)
                chat_area.add_info("PDCA enabled")
            else:
                self.agent_bridge.pdca_extension.disable_pdca()
                chat_area = self.query_one("#chat_area", ChatArea)
                chat_area.add_info("PDCA disabled")
        else:
            chat_area = self.query_one("#chat_area", ChatArea)
            chat_area.add_error("PDCA extension not available")

    def _stop_agent(self) -> None:
        """Stop agent execution"""
        if self.agent_bridge:
            asyncio.create_task(self.agent_bridge.stop_agent())

    async def action_show_settings(self) -> None:
        """Show settings screen"""
        result = await self.push_screen_wait(SettingsScreen(self.settings))

        # If user saved settings (result is not None)
        if result is not None:
            # Update settings from result
            self.settings = result

            # Update config with new settings
            self.config.refresh_rate = result.refresh_rate
            self.config.max_history = result.max_history
            self.config.show_thinking = result.show_thinking
            self.config.show_tools = result.show_tools
            self.config.enable_markdown = result.enable_markdown
            self.config.enable_syntax_highlight = result.enable_syntax_highlight
            self.config.max_thinking_lines = result.max_thinking_lines
            self.config.max_tool_lines = result.max_tool_lines

            # Get language from language selector widget
            try:
                language_selector = self.query_one("#language_selector")
                if hasattr(language_selector, "value"):
                    new_language = language_selector.value
                    old_language = get_current_language()

                    # Only update if language changed
                    if new_language != old_language:
                        self.config.language = new_language
                        set_language(new_language)

                        # Update title/subtitle with new language
                        self.TITLE = _("Dawei TUI - Agent Terminal Interface")
                        self.SUB_TITLE = _("Agent")

                        # Show notification
                        if self.toast_manager:
                            lang_name = {
                                "en": "English",
                                "zh_CN": "简体中文",
                                "zh_TW": "繁體中文",
                            }.get(new_language, new_language)
                            self.toast_manager.success(f"Language changed to {lang_name}")
            except Exception:
                # Language selector might not be in the result screen
                pass

            # Save config to file
            self.config.save_tui_config()

            logger.info(f"Settings saved: {result}")

    async def action_save_session(self) -> None:
        """Save current session"""
        success = self.session_manager.save_session()
        if success:
            self.toast_manager.success("Session saved successfully")
            chat_area = self.query_one("#chat_area", ChatArea)
            chat_area.add_info("Session saved")
        else:
            self.toast_manager.error("Failed to save session")
            chat_area = self.query_one("#chat_area", ChatArea)
            chat_area.add_error("Failed to save session")

    def action_clear_chat(self) -> None:
        """Clear chat history"""
        chat_area = self.query_one("#chat_area", ChatArea)
        chat_area.clear_chat()
        self.toast_manager.info("Chat cleared", duration=2.0)
        chat_area.add_info("Chat cleared")

    async def action_show_history(self) -> None:
        """Show session history"""
        logger.info("Showing session history...")
        logger.info(f"Sessions directory: {self.session_manager.sessions_dir}")
        logger.info(f"Directory exists: {self.session_manager.sessions_dir.exists()}")

        sessions = self.session_manager.list_sessions()

        logger.info(f"Found {len(sessions)} session(s)")

        if not sessions:
            logger.warning("No sessions found to display!")
            if self.toast_manager:
                self.toast_manager.warning("No historical sessions found")
            return

        logger.info(f"Creating SessionHistoryScreen with {len(sessions)} sessions")

        # Push screen - SessionHistoryScreen will handle load/delete directly
        self.push_screen(SessionHistoryScreen(sessions))

    async def action_load_session(self, session_id: str) -> None:
        """Load a historical session

        Args:
            session_id: Session ID to load
        """
        logger.info(f"[LOAD] action_load_session called with session_id: {session_id}")

        try:
            logger.info("[LOAD] Loading session from SessionManager...")
            session = self.session_manager.load_session(session_id)

            if not session:
                logger.warning("[LOAD] Session not found!")
                logger.warning(f"Session not found: {session_id}")
                if self.toast_manager:
                    self.toast_manager.error(f"Session not found: {session_id[:8]}...")
                return

            logger.info(f"[LOAD] Session loaded, has {len(session.messages)} messages")

            # Restore messages to chat area
            logger.info("[LOAD] Querying ChatArea...")
            try:
                chat_area = self.query_one("#chat_area", ChatArea)
                logger.info(f"[LOAD] ChatArea found: {chat_area}")
            except Exception:
                logger.exception("[LOAD] ERROR finding ChatArea: ")
                logger.exception("Error finding ChatArea: ")
                return

            chat_area.clear_chat()
            logger.info("[LOAD] Chat cleared")

            for i, msg in enumerate(session.messages):
                logger.info(f"[LOAD] Adding message {i + 1}/{len(session.messages)}: role={msg.role}")
                if msg.role == "user":
                    chat_area.add_user_message(msg.content)
                elif msg.role == "assistant":
                    chat_area.add_assistant_message(msg.content)
                elif msg.role == "system":
                    chat_area.add_system_message(msg.content)
                elif msg.role == "error":
                    chat_area.add_error(msg.content)

            logger.info("[LOAD] All messages added to chat")

            # CRITICAL: Scroll to end to show latest messages
            chat_area.scroll_end()
            logger.info("[LOAD] Scrolled to end")

            # Refresh the chat area
            chat_area.refresh()
            logger.info("[LOAD] ChatArea refreshed")

            if self.toast_manager:
                self.toast_manager.success(f"Session loaded: {session_id[:8]}...")
                logger.info("[LOAD] Toast shown")

            logger.info(f"Session loaded successfully: {session_id}")

        except Exception as e:
            logger.exception("[LOAD] ERROR in action_load_session: ")
            logger.error(f"Error loading session {session_id}: {e}", exc_info=True)
            if self.toast_manager:
                self.toast_manager.error(f"Failed to load session: {e}")

    async def action_delete_session(self, session_id: str) -> None:
        """Delete a historical session

        Args:
            session_id: Session ID to delete
        """
        logger.info(f"Deleting session: {session_id}")

        try:
            success = self.session_manager.delete_session(session_id)

            if success:
                if self.toast_manager:
                    self.toast_manager.success(f"Session deleted: {session_id[:8]}...")
                logger.info(f"Session deleted successfully: {session_id}")
            else:
                if self.toast_manager:
                    self.toast_manager.warning(f"Session not found: {session_id[:8]}...")
                logger.warning(f"Session not found: {session_id}")

        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}", exc_info=True)
            if self.toast_manager:
                self.toast_manager.error(f"Failed to delete session: {e}")

    def action_switch_language(self) -> None:
        """Switch to next available language (Ctrl+Alt+L)"""
        try:
            header = self.query_one(CustomHeader)
            header.switch_language()

            # 显示通知
            if self.toast_manager:
                from dawei.tui.i18n import get_current_language, get_supported_languages

                lang_name = get_supported_languages().get(get_current_language(), get_current_language())
                self.toast_manager.success(f"Language: {lang_name}")

        except Exception as e:
            logger.error(f"Error switching language: {e}", exc_info=True)
            if self.toast_manager:
                self.toast_manager.error(f"Failed to switch language: {e}")

    def action_toggle_theme(self) -> None:
        """Toggle between light and dark theme (Ctrl+Alt+T)"""
        try:
            header = self.query_one(CustomHeader)
            header.toggle_theme()

            # 显示通知
            if self.toast_manager:
                theme_name = "Light" if header.theme == "light" else "Dark"
                self.toast_manager.success(f"Theme: {theme_name}")

        except Exception as e:
            logger.error(f"Error toggling theme: {e}", exc_info=True)
            if self.toast_manager:
                self.toast_manager.error(f"Failed to toggle theme: {e}")

    def on_resize(self, event) -> None:
        """Handle terminal resize events"""
        logger.info("[RESIZE EVENT] Terminal resized!")
        logger.info(f"[RESIZE EVENT] New size: {event.size}")
        logger.info(f"[RESIZE EVENT] Container size: {event.container_size}")
        logger.info("[RESIZE EVENT] Widget tree will re-layout automatically")

        # Log current terminal size
        import shutil

        terminal_size = shutil.get_terminal_size()
        logger.info(f"[RESIZE EVENT] Actual terminal size from shutil: {terminal_size.columns}x{terminal_size.lines}")

    async def on_unmount(self) -> None:
        """Cleanup on app unmount"""
        logger.info("GeweiTUIApp unmounting, cleaning up...")

        # Cleanup AgentBridge with proper error handling
        if self.agent_bridge:
            try:
                logger.info("Cleaning up AgentBridge...")
                await self.agent_bridge.cleanup()
                logger.info("AgentBridge cleanup completed successfully")
            except Exception as e:
                logger.error(f"Error cleaning up AgentBridge: {e}", exc_info=True)
                # Don't raise during cleanup - we're exiting anyway

        # Cleanup event queue
        if self.event_queue:
            try:
                logger.info("Cleaning up event queue...")
                self.event_queue.put_nowait(None)  # Signal to stop polling
            except Exception as e:
                logger.error(f"Error cleaning up event queue: {e}", exc_info=True)

        logger.info("GeweiTUIApp cleanup complete")
