# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Union


@dataclass
class UserInputText:
    """用户通过ui输入的文本"""

    # 唯一id，用于关联用户输入和回复
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    task_node_id: str | None = None


UserInputMessage = Union[UserInputText]
