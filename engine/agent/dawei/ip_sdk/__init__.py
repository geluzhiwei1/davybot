# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""DavyBot IP SDK — Python client for DavyBot IP Module REST API.

Minimal Python client wrapping the DavyBot IP HTTP API (8 modules).
Install from source: `pip install -e path/to/nn-bot/agent/`

Usage:
    from dawei.ip_sdk import IpClient

    client = IpClient("https://api.normnomos.com")

    # M1 — evaluate patentability
    task = client.idea_vault.evaluate(description="An AI-based scheduling algorithm")
    result = client.idea_vault.get_result(task.task_id)  # polls until complete

    # M3 — generate patent draft
    task = client.draft.generate(disclosure_id="...", target_country="US")
    result = client.draft.get_result(task.task_id)

    # M6 — FTO check
    task = client.infringement.fto_check(product_description="a cloud data processor")
    result = client.infringement.get_result(task.task_id)
"""

from .client import IpClient
from .models import (
    DisclosureResultResponse,
    DraftResultResponse,
    # Common
    ExportInfo,
    FileUploadResult,
    FilingResultResponse,
    # M1
    IdeaItem,
    IdeaResultResponse,
    InfringementResultResponse,
    # M2
    IpDisclosure,
    # M3
    IpDraft,
    # M4
    IpFiling,
    # M6
    IpInfringement,
    # M5
    IpOaRecord,
    # M7
    IpPortfolio,
    # M8
    IpTrademark,
    OaReplyResultResponse,
    PatentItem,
    PortfolioResultResponse,
    # Task
    TaskResponse,
    TrademarkItem,
    TrademarkResultResponse,
)

__all__ = [
    "IpClient",
    "TaskResponse",
    "IdeaItem",
    "IdeaResultResponse",
    "IpDisclosure",
    "DisclosureResultResponse",
    "IpDraft",
    "DraftResultResponse",
    "IpFiling",
    "FilingResultResponse",
    "IpOaRecord",
    "OaReplyResultResponse",
    "IpInfringement",
    "InfringementResultResponse",
    "IpPortfolio",
    "PatentItem",
    "TrademarkItem",
    "PortfolioResultResponse",
    "IpTrademark",
    "TrademarkResultResponse",
    "ExportInfo",
    "FileUploadResult",
]
