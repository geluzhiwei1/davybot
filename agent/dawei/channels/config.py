"""Base configuration for all channel implementations.

 Subclass this for channel-specific configs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BaseChannelConfig:
    """Common configuration fields for all channels.

    Subclass this for channel-specific configs.
    """

    allowed_senders: set[str] | None = None
    allowed_channels: set[str] | None = None
    text_chunk_limit: int = 4096
    proxy: str | None = None
    include_attachments: bool = True
