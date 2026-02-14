# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Market integration module for dawei agent system.

Provides integration with davybot-market-cli for managing
skills, agents, and plugins from the market.

Usage:
    from dawei.market import MarketClient, MarketInstaller

    # Search resources
    client = MarketClient()
    results = client.search("web scraping", resource_type="skill")

    # Install resource
    installer = MarketInstaller(workspace="/path/to/workspace")
    installer.install("skill", "web-scraper")
"""

import sys
from pathlib import Path

from .cli_wrapper import CliWrapper
from .client import MarketClient
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

# Check if davybot-market-cli is available
try:
    import shutil

    MARKET_AVAILABLE_CLI = shutil.which("davy") is not None
except Exception:
    MARKET_AVAILABLE_CLI = False

# Always export MARKET_AVAILABLE flag - set to True if module can be imported
MARKET_AVAILABLE = True  # Set to True since module exists

__all__ = [
    "MARKET_AVAILABLE",
    "CliWrapper",
    "InstallResult",
    "InstallationError",
    "MarketClient",
    "MarketError",
    "MarketInstaller",
    "ResourceInfo",
    "ResourceNotFoundError",
    "ResourceType",
    "SearchResult",
]
