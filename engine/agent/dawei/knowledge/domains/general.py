# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""General domain profile — default, compatible with existing behavior"""

from .base import DomainProfile


class GeneralProfile(DomainProfile):
    """General purpose profile — uses built-in tech-oriented defaults"""

    name = "general"
    display_name = "通用"
    description = "通用领域，使用内置的技术术语字典和默认提取策略"

    entity_types = {
        "PERSON": "人物",
        "ORG": "组织",
        "TECH": "技术",
        "CONCEPT": "概念",
        "LOCATION": "地点",
        "TIME": "时间",
        "OTHER": "其他",
    }

    relation_types = {
        "works_at": "工作于",
        "used_in": "用于",
        "cites": "引用",
        "is_a": "属于",
        "part_of": "部分",
        "similar_to": "类似",
        "co_occurs": "共现",
    }
