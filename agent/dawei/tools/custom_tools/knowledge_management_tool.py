# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge base management tools for document operations"""

import logging
from pathlib import Path
from typing import List, Dict, Any

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool

logger = logging.getLogger(__name__)
