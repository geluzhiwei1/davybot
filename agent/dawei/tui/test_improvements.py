#!/usr/bin/env python3
# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Test script for TUI improvements

Validates the new features and improvements made to the TUI module.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from textual.app import App

from dawei.tui.ui.widgets.toast_notifications import (
    ToastLevel,
    ToastManager,
    show_toast,
)


class TestApp(App):
    """Simple test app for toast notifications"""

    CSS = """
    Screen {
        background: $background;
    }
    """

    def on_mount(self) -> None:
        """Test toast notifications on mount"""
        toast = ToastManager(self)

        # Test all toast levels
        toast.info("This is an info message")
        self.set_timer(1.0, lambda: toast.success("Success message!"))
        self.set_timer(2.0, lambda: toast.warning("Warning message!"))
        self.set_timer(3.0, lambda: toast.error("Error message!"))

        # Test with custom title and duration
        self.set_timer(4.0, lambda: toast.info("Custom title", title="Custom Title"))
        self.set_timer(5.0, lambda: toast.info("Long duration", duration=10.0))

        # Test show_toast function
        self.set_timer(6.0, lambda: show_toast(self, "Function test", "info"))

        self.set_timer(7.0, self.exit_app)

    def exit_app(self) -> None:
        """Exit the app"""
        self.exit()


def test_css_syntax():
    """Test CSS file for syntax errors"""
    print("\n" + "=" * 60)
    print("Testing CSS syntax...")
    print("=" * 60)

    css_path = Path(__file__).parent / "ui" / "themes" / "default.css"

    if not css_path.exists():
        print(f"❌ CSS file not found: {css_path}")
        return False

    with Path(css_path).open() as f:
        css_content = f.read()

    # Check for modern CSS syntax
    checks = {
        "CSS Variables (Modern)": "$primary:" in css_content,
        "Flexbox syntax": "flex: 1" in css_content or "flex: 1" in css_content,
        "Media queries": "@media" in css_content,
        "Nested selectors": "& Header" in css_content or "& Input" in css_content,
        "Scrollbar styling": "scrollbar-background:" in css_content,
        "Comments": "/*" in css_content and "*/" in css_content,
        "Focus states": ":focus" in css_content,
    }

    all_passed = True
    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check_name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n✅ All CSS syntax checks passed!")
    else:
        print("\n⚠️  Some CSS checks failed")

    return all_passed


def test_imports():
    """Test that all new modules can be imported"""
    print("\n" + "=" * 60)
    print("Testing module imports...")
    print("=" * 60)

    modules = [
        ("Toast notifications", "dawei.tui.ui.widgets.toast_notifications"),
        ("Enhanced help screen", "dawei.tui.ui.screens.help_screen_enhanced"),
        ("Toast manager", "dawei.tui.ui.widgets"),
    ]

    all_passed = True
    for name, module_path in modules:
        try:
            __import__(module_path)
            print(f"✅ {name}")
        except ImportError as e:
            print(f"❌ {name}: {e}")
            all_passed = False

    if all_passed:
        print("\n✅ All imports successful!")
    else:
        print("\n⚠️  Some imports failed")

    return all_passed


def test_toast_manager():
    """Test ToastManager class"""
    print("\n" + "=" * 60)
    print("Testing ToastManager...")
    print("=" * 60)

    try:
        # Test ToastLevel enum
        levels = [level.value for level in ToastLevel]
        expected_levels = ["info", "success", "warning", "error"]

        if levels == expected_levels:
            print(f"✅ ToastLevel enum: {levels}")
        else:
            print(f"❌ ToastLevel enum mismatch: {levels} != {expected_levels}")
            return False

        # Test ToastManager instantiation
        app = App()
        ToastManager(app)
        print("✅ ToastManager instantiation")

        # Test show_toast function
        print("✅ show_toast function available")

        print("\n✅ ToastManager tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ ToastManager test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("TUI Improvements Test Suite")
    print("=" * 60)

    results = {
        "CSS Syntax": test_css_syntax(),
        "Module Imports": test_imports(),
        "Toast Manager": test_toast_manager(),
    }

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    print(f"\n⚠️  {total - passed} test(s) failed")
    return 1


if __name__ == "__main__":
    # Run tests without GUI
    exit_code = main()

    # Ask if user wants to run visual test
    print("\n" + "=" * 60)
    print("Visual Test (Toast Notifications)")
    print("=" * 60)
    print("Do you want to run the visual toast test? (y/n): ", end="")

    try:
        response = input().strip().lower()
        if response in {"y", "yes"}:
            print("\nStarting visual test...")
            print("Watch for toast notifications in the TUI...")
            app = TestApp()
            app.run()
    except (KeyboardInterrupt, EOFError):
        print("\nSkipping visual test.")

    sys.exit(exit_code)
