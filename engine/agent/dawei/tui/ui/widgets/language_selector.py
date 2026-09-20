# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Language Selector Widget

A dropdown widget for selecting language in TUI settings.
"""

from textual.widgets import Select

from dawei.tui.i18n import get_current_language, get_supported_languages, set_language


class LanguageSelector(Select):
    """Language selector dropdown widget"""

    def __init__(self):
        """Initialize language selector"""
        # Get current language
        current_lang = get_current_language()

        # Create options
        options = []
        for code, name in get_supported_languages().items():
            options.append((code, name))

        super().__init__(
            options=options,
            value=current_lang,
            id="language_selector",
        )

    async def on_select(self, event) -> None:
        """Handle language selection

        Args:
            event: Select event
        """
        selected_lang = event.value
        if selected_lang != get_current_language():
            set_language(selected_lang)

            # Show notification (app needs to be mounted)

            app = self.app
            if hasattr(app, "toast_manager") and app.toast_manager:
                lang_name = get_supported_languages().get(selected_lang, selected_lang)
                app.toast_manager.success(f"Language changed to {lang_name}")

            # Trigger app restart or UI refresh if needed
            # For now, we just update the language - changes will take effect
            # for newly created widgets
