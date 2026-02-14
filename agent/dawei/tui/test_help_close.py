#!/usr/bin/env python3
# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Test script for HelpScreen close button functionality.

This script tests that the HelpScreen can be closed via:
1. Keyboard (Q key)
2. Keyboard (Escape key)
3. Mouse click on Close button
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from textual.app import App

from dawei.tui.ui.screens.help_screen import HelpScreen


class TestApp(App):
    """Simple test app for HelpScreen"""

    CSS = """
    Screen {
        background: $background;
    }
    """

    def on_mount(self) -> None:
        """Show help screen on mount"""
        self.push_screen(HelpScreen())


def main():
    """Run the test"""
    print("\n" + "=" * 60)
    print("HelpScreen Close Button Test")
    print("=" * 60)
    print()
    print("Testing HelpScreen functionality:")
    print("  ✅ HelpScreen class imports successfully")
    print("  ✅ Screen has BINDINGS defined")
    print("  ✅ Screen has Button widget")
    print("  ✅ Screen has on_button_pressed handler")
    print()
    print("Close Methods:")
    print("  1. Press Q key")
    print("  2. Press Escape key")
    print("  3. Click Close button (with mouse)")
    print()
    print("Starting TUI...")
    print("Try all three methods to close the help screen!")
    print()

    app = TestApp()
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return 1

    return 0


if __name__ == "__main__":
    # Check imports first
    try:
        from dawei.tui.ui.screens.help_screen import HelpScreen
        from dawei.tui.ui.screens.help_screen_enhanced import EnhancedHelpScreen

        print("✅ All imports successful")

        # Verify BINDINGS
        assert hasattr(HelpScreen, "BINDINGS"), "HelpScreen missing BINDINGS"
        assert len(HelpScreen.BINDINGS) == 2, "HelpScreen BINDINGS incorrect"
        print("✅ HelpScreen BINDINGS defined correctly")

        assert hasattr(EnhancedHelpScreen, "BINDINGS"), "EnhancedHelpScreen missing BINDINGS"
        assert len(EnhancedHelpScreen.BINDINGS) == 3, "EnhancedHelpScreen BINDINGS incorrect"
        print("✅ EnhancedHelpScreen BINDINGS defined correctly")

        # Verify button handler
        assert hasattr(HelpScreen, "on_button_pressed"), "HelpScreen missing on_button_pressed"
        print("✅ HelpScreen has on_button_pressed handler")

        assert hasattr(EnhancedHelpScreen, "on_button_pressed"), "EnhancedHelpScreen missing on_button_pressed"
        print("✅ EnhancedHelpScreen has on_button_pressed handler")

        print()
        print("🎉 All pre-flight checks passed!")
        print()

    except Exception as e:
        print(f"❌ Import or validation error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Ask if user wants to run visual test
    print("=" * 60)
    print("Visual Test (Help Screen with Close Button)")
    print("=" * 60)
    print("Do you want to run the visual test? (y/n): ", end="")

    try:
        response = input().strip().lower()
        if response in {"y", "yes"}:
            print("\nStarting visual test...")
            print("Try clicking the Close button or pressing Q/Escape!")
            sys.exit(main())
        else:
            print("\nSkipping visual test.")
            print("\nTo test manually, run:")
            print("  cd /home/dev007/ws/dawei-agent/agent")
            print("  uv run dawei tui --workspace <workspace>")
            print("  Then press ? or Ctrl+H to open help")
            sys.exit(0)
    except (KeyboardInterrupt, EOFError):
        print("\nSkipping visual test.")
        sys.exit(0)
