# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Python 3.10 compatibility for datetime.UTC"""

from datetime import timezone

# Python 3.10 compatibility
try:
    from datetime import UTC  # type: ignore
except ImportError:
    UTC = timezone.utc  # type: ignore

__all__ = ["UTC"]
