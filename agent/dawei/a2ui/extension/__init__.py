# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei A2UI Extension - Agent-to-User Interface support

This package provides A2UI (Agent-to-User Interface) functionality for Dawei agents,
enabling rich UI rendering without external dependencies.
"""

from dawei.a2ui.extension.a2ui_extension import (
    A2UI_MIME_TYPE,
    STANDARD_CATALOG_ID,
    create_a2ui_message,
    is_a2ui_message,
    validate_a2ui_schema,
)

__all__ = [
    "A2UI_MIME_TYPE",
    "STANDARD_CATALOG_ID",
    "create_a2ui_message",
    "is_a2ui_message",
    "validate_a2ui_schema",
]
