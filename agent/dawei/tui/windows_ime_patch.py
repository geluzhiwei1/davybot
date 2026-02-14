# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Chinese IME Support Patch for Textual on Windows

This module patches Textual's win32.py driver to fix Chinese IME input.
The issue is that Textual incorrectly filters out Chinese IME characters.

Apply this patch BEFORE importing any Textual modules.
"""

import sys


def apply_chinese_ime_patch():
    """Apply the Chinese IME fix to Textual's Windows driver.

    The bug: In textual.drivers.win32.EventMonitor.run(), lines 273-277:
        if (key_event.dwControlKeyState and key_event.wVirtualKeyCode == 0):
            continue  # ❌ This skips Chinese IME characters!

    The fix: Only skip if UnicodeChar is also empty:
        if (key_event.dwControlKeyState and key_event.wVirtualKeyCode == 0 and not key):
            continue  # ✅ Allow Chinese IME characters with UnicodeChar
    """
    if sys.platform != "win32":
        return  # Not Windows, no patch needed

    try:
        from ctypes import byref

        from textual.drivers import win32

        # Store the original run method

        def patched_run(self):
            """Patched EventMonitor.run() that supports Chinese IME"""

            from textual import constants
            from textual._xterm_parser import XTermParser

            exit_requested = self.exit_event.is_set
            parser = XTermParser(debug=constants.DEBUG)

            try:
                from ctypes.wintypes import DWORD

                read_count = DWORD(0)
                hIn = win32.GetStdHandle(win32.STD_INPUT_HANDLE)

                arrtype = win32.INPUT_RECORD * MAX_EVENTS
                input_records = arrtype()
                keys = []
                append_key = keys.append

                while not exit_requested():
                    for event in parser.tick():
                        self.process_event(event)

                    if win32.wait_for_handles([hIn], 100) is None:
                        continue

                    ReadConsoleInputW(hIn, byref(input_records), MAX_EVENTS, byref(read_count))
                    read_input_records = input_records[: read_count.value]

                    del keys[:]
                    new_size = None

                    for input_record in read_input_records:
                        event_type = input_record.EventType

                        if event_type == win32.KEY_EVENT:
                            key_event = input_record.Event.KeyEvent
                            key = key_event.uChar.UnicodeChar
                            if key_event.bKeyDown:
                                # *** CHINESE IME FIX ***
                                # Only skip if dwControlKeyState is set, wVirtualKeyCode==0
                                # AND UnicodeChar is empty (no character to process)
                                if (
                                    key_event.dwControlKeyState and key_event.wVirtualKeyCode == 0 and not key  # ✅ FIX: Check if UnicodeChar is empty
                                ):
                                    continue
                                append_key(key)
                        elif event_type == win32.WINDOW_BUFFER_SIZE_EVENT:
                            size = input_record.Event.WindowBufferSizeEvent.dwSize
                            new_size = (size.X, size.Y)

                    if keys:
                        for event in parser.feed("".join(keys).encode("utf-16", "surrogatepass").decode("utf-16")):
                            self.process_event(event)
                    if new_size is not None:
                        self.on_size_change(*new_size)

            except Exception as error:
                self.app.log.exception("EVENT MONITOR ERROR", error)

        # Apply the patch
        win32.EventMonitor.run = patched_run
        print("[PATCH] ✅ Chinese IME support enabled", file=sys.stderr, flush=True)

    except ImportError as e:
        print(
            f"[PATCH] ⚠️  Textual win32 driver not found: {e}",
            file=sys.stderr,
            flush=True,
        )
    except Exception as e:
        print(
            f"[PATCH] ❌ Failed to apply Chinese IME patch: {e}",
            file=sys.stderr,
            flush=True,
        )


# Auto-apply on import
apply_chinese_ime_patch()
