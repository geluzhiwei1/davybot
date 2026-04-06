# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Market integration module for dawei agent system.

Provides integration with davybot-market-cli for managing
skills, agents, and plugins from the market.

Usage:
    from dawei.market import CliWrapper, MarketInstaller

    # Search resources
    cli = CliWrapper()
    results = cli.search_skills("web scraping")

    # Install resource
    installer = MarketInstaller(workspace="/path/to/workspace")
    installer.install("skill", "web-scraper")
"""

import sys
from pathlib import Path

from .cli_wrapper import CliExecutionError, CliNotFoundError, CliWrapper
from .installer import MarketInstaller
from .models import (
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

# Check if davybot-market-cli SDK is available
from .cli_wrapper import SDK_AVAILABLE as _SDK_AVAILABLE

# Always export MARKET_AVAILABLE flag based on SDK availability
MARKET_AVAILABLE = _SDK_AVAILABLE

__all__ = [
    "MARKET_AVAILABLE",
    "CliExecutionError",
    "CliNotFoundError",
    "CliWrapper",
    "InstallResult",
    "InstallationError",
    "MarketError",
    "MarketInstaller",
    "ResourceInfo",
    "ResourceNotFoundError",
    "ResourceType",
    "SearchResult",
]
