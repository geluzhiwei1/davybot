# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ChatArea Widget

Claude-Code style chat transcript:
- Each message is its own Markdown widget (proper GFM rendering, CJK-safe wrapping).
- System/error/info lines are plain Static(Text) widgets (markup-injection safe).
- Streaming chunks are buffered and coalesced into a full Markdown re-render per
  frame, so half-finished syntax (e.g. an open ``**``) still renders correctly.

Replaces the old RichLog-based implementation whose `min_width=78` writes inside
a narrow panel caused one-CJK-char-per-line collapse and raw markdown leakage.
"""

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import LoadingIndicator, Markdown, Static

from dawei.tui.i18n import _


class ChatArea(VerticalScroll):
    """Chat history display widget (Markdown transcript)."""

    BINDINGS = [
        ("ctrl+c", "copy_last_reply", "Copy"),
        ("ctrl+shift+c", "copy_last_reply", "Copy"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stream_md: Markdown | None = None
        self._stream_buffer: list[str] = []
        self._stream_render_scheduled: bool = False
        self._last_assistant_content: str = ""
        self._placeholder: Static | None = None
        self._stream_label: Static | None = None
        self._stream_pending: LoadingIndicator | None = None

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _autoscroll(self) -> None:
        """Scroll to the bottom on the next refresh (after layout settles)."""
        self.call_after_refresh(self.scroll_end, animate=False)

    def _remove_placeholder(self) -> None:
        if self._placeholder is not None:
            self._placeholder.remove()
            self._placeholder = None

    def _remove_stream_pending(self) -> None:
        """Remove the 'waiting' spinner (called when real content arrives or stream ends)."""
        if self._stream_pending is not None:
            try:
                self._stream_pending.remove()
            except Exception:
                pass  # already removed with the parent
            self._stream_pending = None

    def _mount_note(self, note: Text, css_class: str) -> None:
        self._remove_placeholder()
        self.mount(Static(note, classes=css_class))
        self._autoscroll()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._placeholder = Static(
            Text(_("Messages will appear here..."), style="dim"),
            classes="chat-placeholder",
        )
        self.mount(self._placeholder)

    # ------------------------------------------------------------------
    # public API (preserved from the RichLog version)
    # ------------------------------------------------------------------

    def add_user_message(self, message: str) -> None:
        """Add user message to chat (rendered as Markdown)."""
        self._remove_placeholder()
        self.mount(
            # Warm orange, theme accent — readable on the dark chat background
            Static(Text(f"{_('You')}:", style="bold rgb(255,166,87)"), classes="chat-label-user"),
            Markdown(message, classes="chat-message"),
        )
        self._autoscroll()

    def add_assistant_message(self, content: str) -> None:
        """Add a complete assistant response (rendered as Markdown)."""
        self._remove_placeholder()
        self._last_assistant_content = content
        self.mount(
            Static(
                Text(f"{_('Assistant')}:", style="bold green"),
                classes="chat-label-assistant",
            ),
            Markdown(content, classes="chat-message"),
        )
        self._autoscroll()

    def start_streaming(self) -> None:
        """Start streaming mode: assistant label + 'thinking' spinner, buffer chunks.

        Called as soon as the user sends a message, so there is immediate
        feedback before the first token arrives.
        """
        if self._stream_md is not None or self._stream_label is not None:
            # previous stream never ended — finalize it first
            self.end_streaming()
        self._remove_placeholder()
        self._stream_label = Static(
            Text(f"{_('Assistant')}:", style="bold green"),
            classes="chat-label-assistant",
        )
        self._stream_pending = LoadingIndicator(classes="chat-pending")
        self.mount(self._stream_label, self._stream_pending)
        self._stream_buffer = []
        self._stream_md = None
        self._autoscroll()

    def append_streaming_content(self, chunk: str) -> None:
        """Buffer a streaming chunk; re-render at most once per refresh cycle."""
        if not chunk:
            return
        self._stream_buffer.append(chunk)
        if not self._stream_render_scheduled:
            self._stream_render_scheduled = True
            self.call_after_refresh(self._flush_stream)

    def _flush_stream(self) -> None:
        """Coalesced render of the streaming buffer (full Markdown re-parse)."""
        self._stream_render_scheduled = False
        if not self._stream_buffer:
            return
        self._remove_stream_pending()  # first real content — stop the spinner
        content = "".join(self._stream_buffer)
        if self._stream_md is None:
            self._stream_md = Markdown(content, classes="chat-message")
            self.mount(self._stream_md)
        elif self._stream_md.is_mounted:
            self._stream_md.update(content)
        self._autoscroll()

    def end_streaming(self) -> None:
        """End streaming mode: final render, remember content for copy."""
        self._remove_stream_pending()
        if self._stream_buffer:
            content = "".join(self._stream_buffer)
            if self._stream_md is None:
                self._stream_md = Markdown(content, classes="chat-message")
                self.mount(self._stream_md)
            elif self._stream_md.is_mounted:
                self._stream_md.update(content)
            self._last_assistant_content = content
            self._autoscroll()
        elif self._stream_label is not None:
            # No text ever arrived (error / tool-only turn) — drop the empty
            # "Assistant:" turn instead of leaving an orphaned label.
            try:
                self._stream_label.remove()
            except Exception:
                pass
        self._stream_md = None
        self._stream_label = None
        self._stream_buffer = []

    def add_error(self, error: str) -> None:
        """Add error message to chat."""
        note = Text("Error: ", style="bold red")
        note.append(error)
        self._mount_note(note, "chat-error")

    def add_info(self, info: str) -> None:
        """Add informational message."""
        self._mount_note(Text(info, style="dim cyan"), "chat-note")

    def add_system_message(self, message: str) -> None:
        """Add system message."""
        note = Text(f"{_('System')}:", style="dim yellow")
        note.append(f" {message}")
        self._mount_note(note, "chat-system")

    def clear_chat(self) -> None:
        """Clear all chat history."""
        self._stream_md = None
        self._stream_label = None
        self._stream_pending = None
        self._stream_buffer = []
        self._stream_render_scheduled = False
        self._last_assistant_content = ""
        self._placeholder = None
        for child in list(self.children):
            child.remove()
        self.on_mount()

    def add_skill_loading_message(self, skill_name: str, char_count: int, success: bool = True) -> None:
        """Add a skill loading status message."""
        if success:
            note = Text(
                "✅ "
                + _("Loaded skill '{skill_name}' to context ({char_count} chars)").format(
                    skill_name=skill_name, char_count=f"{char_count:,}"
                ),
                style="bold green",
            )
        else:
            note = Text(
                "❌ " + _("Failed to load skill '{skill_name}'").format(skill_name=skill_name),
                style="bold red",
            )
        self._mount_note(note, "chat-note")

    def add_skills_loaded_summary(self, skill_names: list, total_count: int) -> None:
        """Add a summary message for multiple loaded skills."""
        note = Text(f"📚 {_('Skills Loaded:')} ", style="bold cyan")
        note.append(f"{total_count} skill(s): {', '.join(skill_names)}")
        self._mount_note(note, "chat-note")

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------

    def action_copy_last_reply(self) -> None:
        """Copy the last assistant reply to clipboard (Ctrl+C when focused)."""
        if not self._last_assistant_content:
            self.app.notify(_("No assistant reply to copy yet"), severity="warning")
            return
        try:
            import pyperclip

            pyperclip.copy(self._last_assistant_content)
            self.app.notify(_("Copied last reply to clipboard"))
        except ImportError:
            self.app.notify("pyperclip not installed. Install with: pip install pyperclip", severity="error")
        except Exception as e:  # noqa: BLE001 — notify, never crash the UI
            self.app.notify(f"Copy failed: {e}", severity="error")

    def action_copy_selection(self) -> None:
        """Backwards-compatible alias for the copy action."""
        self.action_copy_last_reply()
