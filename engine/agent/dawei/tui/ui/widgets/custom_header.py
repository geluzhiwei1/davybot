# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Custom Header Widget

Enhanced Header with connection status, language selector, and theme toggle.
All components support both mouse clicks and keyboard shortcuts.
"""

import contextlib
import logging

from textual.app import ComposeResult
from textual.events import Click
from textual.reactive import reactive
from textual.widgets import Static

from dawei.tui.i18n import get_current_language, get_supported_languages, set_language

logger = logging.getLogger(__name__)


class HeaderStatus(Static):
    """Display connection status in header"""

    DEFAULT_CSS = """
    HeaderStatus {
        dock: left;
        width: 15;
        padding: 0 1;
        content-align: left middle;
        text-style: bold;
    }

    HeaderStatus.connected {
        color: $success;
    }

    HeaderStatus.disconnected {
        color: $error;
    }

    HeaderStatus.connecting {
        color: $warning;
    }

    HeaderStatus:hover {
        background: $foreground 10%;
        text-style: bold underline;
    }
    """

    status = reactive("Ready")
    status_type = reactive("ready")  # ready, connected, disconnected, connecting

    def render(self) -> str:
        """Render status indicator"""
        icons = {
            "ready": "✓",
            "connected": "●",
            "disconnected": "●",
            "connecting": "○",
        }
        icon = icons.get(self.status_type, "•")
        return f"{icon} {self.status[:8]}"

    def on_click(self, event: Click) -> None:
        """Handle click on status - show status details"""
        event.stop()
        logger.info(f"Status clicked: {self.status} ({self.status_type})")

        # 触发一个App action来显示详细信息
        if self.app:
            with contextlib.suppress(Exception):
                self.app.action_show_help()


class HeaderTitle(Static):
    """Display title in header (subtitle removed to avoid duplication with language selector)"""

    DEFAULT_CSS = """
    HeaderTitle {
        text-wrap: nowrap;
        text-overflow: ellipsis;
        content-align: center middle;
        width: 100%;
        text-style: bold;
    }
    """

    def render(self) -> str:
        """Render title from app (without subtitle to avoid duplication)"""
        if self.app:
            return getattr(self.app, "title", "")
        return ""


class HeaderLanguage(Static):
    """Display language selector in header"""

    DEFAULT_CSS = """
    HeaderLanguage {
        dock: right;
        width: 25;
        padding: 0 1;
        content-align: right middle;
    }

    HeaderLanguage:hover {
        background: $foreground 10%;
        text-style: bold;
    }
    """

    current_lang = reactive("en")

    def render(self) -> str:
        """Render language display"""
        lang_name = get_supported_languages().get(self.current_lang, self.current_lang)
        return f"🌐 {lang_name.split()[0]}"

    def on_click(self, event: Click) -> None:
        """Handle click on language - switch to next language"""
        event.stop()

        # 触发语言切换action
        if self.app:
            try:
                self.app.action_switch_language()
            except Exception:
                logger.exception("Failed to switch language via click: ")


class HeaderTheme(Static):
    """Display theme toggle in header"""

    DEFAULT_CSS = """
    HeaderTheme {
        dock: right;
        width: 5;
        padding: 0 1;
        content-align: center middle;
    }

    HeaderTheme:hover {
        background: $foreground 10%;
    }

    HeaderTheme:focus {
        background: $foreground 15%;
        text-style: bold;
    }
    """

    theme = reactive("dark")  # dark or light

    def render(self) -> str:
        """Render theme icon"""
        return "☀️" if self.theme == "light" else "🌙"

    def on_click(self, event: Click) -> None:
        """Handle click on theme icon - toggle theme"""
        event.stop()

        # 触发主题切换action
        if self.app:
            try:
                self.app.action_toggle_theme()
            except Exception:
                logger.exception("Failed to toggle theme via click: ")


class CustomHeader(Static):
    """Custom Header with status, language, and theme

    All components support both mouse clicks and keyboard shortcuts:
    - Click status: Show help
    - Click language: Switch language (Ctrl+Alt+L)
    - Click theme: Toggle theme (Ctrl+Alt+T)
    """

    DEFAULT_CSS = """
    CustomHeader {
        height: 1;
        dock: top;
        width: 100%;
        background: $panel;
        color: $foreground;
    }
    """

    def __init__(self, *args, **kwargs):
        """Initialize custom header"""
        super().__init__(*args, **kwargs)

        # 获取当前语言
        self.current_language = get_current_language()

        # 主题状态（默认深色）
        self.theme = "dark"

    def compose(self) -> ComposeResult:
        """Compose header with custom components"""
        # 左侧：连接状态
        yield HeaderStatus(id="header_status")

        # 中间：标题
        yield HeaderTitle()

        # 右侧：语言 + 主题
        yield HeaderTheme(id="header_theme")
        yield HeaderLanguage(id="header_language")

    def on_mount(self) -> None:
        """Initialize after mount"""
        # 更新语言显示
        lang_component = self.query_one("#header_language", HeaderLanguage)
        lang_component.current_lang = get_current_language()

        # 更新主题显示
        theme_component = self.query_one("#header_theme", HeaderTheme)
        theme_component.theme = self.theme

        # 更新连接状态
        status_component = self.query_one("#header_status", HeaderStatus)
        status_component.status = "Ready"
        status_component.status_type = "ready"

        # 不再更新App的副标题，避免与HeaderTitle重复显示
        # 语言信息只显示在右上角的HeaderLanguage组件中

        logger.info("CustomHeader mounted with all components")

    def update_status(self, status: str, status_type: str = "ready") -> None:
        """Update connection status display

        Args:
            status: Status text (e.g., "Connected", "Disconnected")
            status_type: Status type for styling (ready/connected/disconnected/connecting)

        """
        try:
            # Check if widget is mounted before querying
            if not self.is_mounted:
                logger.debug("CustomHeader not mounted yet, skipping status update")
                return

            status_component = self.query_one("#header_status", HeaderStatus)
            status_component.status = status
            status_component.status_type = status_type
            logger.debug(f"Header status updated: {status} ({status_type})")
        except Exception as e:
            # Only log as debug to avoid spamming errors during startup
            logger.debug(f"Failed to update header status: {e}")

    def update_language(self, lang_code: str) -> None:
        """Update language display

        Args:
            lang_code: Language code (e.g., 'en', 'zh_CN')

        """
        try:
            # Check if widget is mounted before querying
            if not self.is_mounted:
                logger.debug("CustomHeader not mounted yet, skipping language update")
                return

            lang_component = self.query_one("#header_language", HeaderLanguage)
            lang_component.current_lang = lang_code
            self.current_language = lang_code

            # 语言信息只显示在右上角的HeaderLanguage组件中
            # 不再更新App的副标题，避免重复显示

            logger.debug(f"Header language updated: {lang_code}")
        except Exception as e:
            # Only log as debug to avoid spamming errors during startup
            logger.debug(f"Failed to update header language: {e}")

    def toggle_theme(self) -> None:
        """Toggle between light and dark theme"""
        old_theme = self.theme
        self.theme = "light" if self.theme == "dark" else "dark"

        try:
            # Check if widget is mounted before querying
            if not self.is_mounted:
                logger.debug("CustomHeader not mounted yet, skipping theme toggle")
                return

            theme_component = self.query_one("#header_theme", HeaderTheme)
            theme_component.theme = self.theme

            # TODO: 实际应用主题切换
            # 目前只是更新显示，未来可以调用 self.app.theme = self.theme

            logger.info(f"Theme toggled: {old_theme} → {self.theme}")
        except Exception:
            logger.exception("Failed to toggle theme: ")

    def switch_language(self) -> None:
        """Switch to next available language"""
        supported_langs = list(get_supported_languages().keys())
        current_lang = get_current_language()

        try:
            current_index = supported_langs.index(current_lang)
            next_index = (current_index + 1) % len(supported_langs)
            next_lang = supported_langs[next_index]

            set_language(next_lang)
            self.update_language(next_lang)

            logger.info(f"Language switched: {current_lang} → {next_lang}")

        except (ValueError, IndexError):
            if supported_langs:
                set_language(supported_langs[0])
                self.update_language(supported_langs[0])
                logger.info(f"Language reset to: {supported_langs[0]}")
