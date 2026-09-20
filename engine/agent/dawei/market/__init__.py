# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Market integration module — token-only HTTP client for the agent market API.

Usage:
    from dawei.market import MarketClient

    cli = MarketClient(token=user_jwt)
    results = cli.list(resource_type="skill", search="docx")
"""

from .client import MarketClient
from .models import (
    CliExecutionError,
    InstallationError,
    InstalledResource,
    InstallResult,
    MarketError,
    MarketSettings,
    ResourceInfo,
    ResourceNotFoundError,
    ResourceType,
    SearchResult,
)

MARKET_AVAILABLE = True

__all__ = [
    "MARKET_AVAILABLE",
    "CliExecutionError",
    "MarketClient",
    "InstallResult",
    "InstallationError",
    "MarketError",
    "ResourceInfo",
    "ResourceNotFoundError",
    "ResourceType",
    "SearchResult",
]
