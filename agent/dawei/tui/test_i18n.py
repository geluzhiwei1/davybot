#!/usr/bin/env python3
# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Test script for TUI i18n functionality"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dawei.tui.i18n import (
    _,
    _n,
    get_current_language,
    get_supported_languages,
    set_language,
)


def test_i18n():
    """Test internationalization functionality"""

    print("=" * 60)
    print("Dawei TUI - i18n Test")
    print("=" * 60)

    # Show supported languages
    print("\n📋 Supported Languages:")
    for code, name in get_supported_languages().items():
        print(f"  - {code}: {name}")

    # Test each language
    for lang_code, lang_name in get_supported_languages().items():
        print("\n" + "=" * 60)
        print(f"Testing {lang_name} ({lang_code})")
        print("=" * 60)

        # Set language
        set_language(lang_code)
        print(f"Current language: {get_current_language()}")

        # Test basic translations
        print("\n🔤 Basic Translations:")
        test_strings = [
            "Quit",
            "Help",
            "Commands",
            "Settings",
            "Save Session",
            "Clear Chat",
            "History",
            "Dawei TUI - Agent Terminal Interface",
            "Agent",
            "Type @skill:name or message... (Tab to autocomplete, Enter to send)",
            "Chat Output",
            "Messages",
            "Status",
            "Thinking",
            "Tools",
        ]

        for s in test_strings:
            translated = _(s)
            status = "✓" if translated != s else "✗"
            print(f"  {status} {s}")
            if translated != s:
                print(f"    → {translated}")

        # Test plural forms
        print("\n🔢 Plural Translations:")
        for count in [0, 1, 2, 5]:
            text = _n("One file", "Multiple files", count)
            print(f"  {count}: {text}")

    print("\n" + "=" * 60)
    print("✓ i18n Test Complete")
    print("=" * 60)


def test_dynamic_switching():
    """Test dynamic language switching"""

    print("\n" + "=" * 60)
    print("Testing Dynamic Language Switching")
    print("=" * 60)

    test_messages = [
        ("en", "Hello"),
        ("zh_CN", "你好"),
        ("zh_TW", "你好"),
    ]

    for lang, _msg in test_messages:
        set_language(lang)
        print(f"\n[{lang}] Current: {get_current_language()}")
        print(f"  'Quit' → '{_('Quit')}'")
        print(f"  'Help' → '{_('Help')}'")


if __name__ == "__main__":
    test_i18n()
    test_dynamic_switching()
