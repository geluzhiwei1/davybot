# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""模式相关的实体定义"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModeConfig:
    """模式配置数据类 - 完全按照 orchestrator.yaml 字段定义"""

    slug: str
    name: str
    role_definition: str = ""
    when_to_use: str = ""
    description: str = ""
    groups: list[str | dict[str, Any]] = field(default_factory=list)
    source: str = ""
    custom_instructions: str = ""
    rules: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModeConfig":
        """从字典创建模式配置"""
        return cls(
            slug=data.get("slug", ""),
            name=data.get("name", ""),
            role_definition=data.get("roleDefinition", ""),
            when_to_use=data.get("whenToUse", ""),
            description=data.get("description", ""),
            groups=data.get("groups", []),
            source=data.get("source", ""),
            custom_instructions=data.get("customInstructions", ""),
            rules=data.get("rules", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "slug": self.slug,
            "name": self.name,
            "roleDefinition": self.role_definition,
            "whenToUse": self.when_to_use,
            "description": self.description,
            "groups": self.groups,
            "source": self.source,
            "customInstructions": self.custom_instructions,
            "rules": self.rules,
        }

    def merge_with(self, other: "ModeConfig") -> "ModeConfig":
        """与另一个配置合并，other 的值会覆盖当前值"""
        if not other:
            return self

        # 创建新的配置，other 的非空字段覆盖 self 的字段
        merged = ModeConfig.from_dict(self.to_dict())

        for key, value in other.to_dict().items():
            if value is not None and value not in ("", [], {}):
                setattr(merged, key, value)

        return merged
