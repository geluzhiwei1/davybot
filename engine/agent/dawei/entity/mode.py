# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""模式相关的实体定义

ModeConfig v2（project/docs/mode统一管理.md §4.2/§4.8）：
- kind（framework | business）、priority、can_delegate；
- priority 不再是死元数据：由 ModeRegistry/ModeResolver 消费；
- aliases 已退役（mode工具解耦方案 D2）：残留 yaml 仅告警；
  groups 为 Roo Code 兼容字段：静默忽略；
- 命名规范（§4.8）在 from_dict 时做 FAST FAIL 校验（slug 格式/framework 白名单），
  内容级规范（name 拟人化英文、business 前缀、priority 保留段）暂以
  validation_issues() 输出告警，Phase 3 起升级为 FAIL。
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

# 框架模式保留 slug 白名单（§4.8.1：无 team 前缀，仅 builtin 可定义）
FRAMEWORK_SLUGS = frozenset({"orchestrator", "pdca"})

logger = logging.getLogger(__name__)

# mode kind 常量
KIND_FRAMEWORK = "framework"
KIND_BUSINESS = "business"

# priority 保留段（§4.5）：framework ≥ 80；business ∈ [1, 79]；pdca=0 显式最低
PRIORITY_FRAMEWORK_MIN = 80
PRIORITY_PDCA = 0

# slug：小写 kebab-case，总长 ≤ 48（§4.8.1）
_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
_SLUG_MAX_LEN = 48

# name：英文 Title Case，≤ 32 字符，≤ 4 词（§4.8.2；emoji 前缀可选，校验前剥离）
_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9 ,.&'/-]*$")
_NAME_MAX_LEN = 32
_NAME_MAX_WORDS = 4
_EMOJI_PREFIX_RE = re.compile(r"^[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]+\s*")
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def strip_emoji_prefix(name: str) -> str:
    """剥离展示名前缀 emoji（如 '🪃 Mission Coordinator' → 'Mission Coordinator'）"""
    return _EMOJI_PREFIX_RE.sub("", name or "").strip()


@dataclass
class ModeConfig:
    """模式配置数据类 - 完全按照 modes.yaml 字段定义（v2）"""

    slug: str
    name: str
    kind: str = KIND_BUSINESS
    priority: int = 50
    can_delegate: bool = True
    role_definition: str = ""
    when_to_use: str = ""
    description: str = ""
    source: str = ""
    custom_instructions: str = ""
    rules: dict[str, str] = field(default_factory=dict)

    @property
    def is_framework(self) -> bool:
        return self.kind == KIND_FRAMEWORK

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: str = "") -> "ModeConfig":
        """从字典创建模式配置

        FAST FAIL（结构级，Phase 1 即生效）：
        - slug 缺失 / 格式违规（§4.8.1 正则、长度）；
        - framework 白名单外 slug 声明 kind=framework；
        - kind 非法取值。

        兼容（存量 yaml 无新字段）：kind 按 slug 推断（orchestrator/pdca → framework），
        priority 给保留段默认值（framework→80，business→50），can_delegate 默认 True。
        """
        slug = str(data.get("slug", "")).strip()
        if not slug:
            raise ValueError(f"ModeConfig: missing 'slug' in {data.get('source', source) or data!r:.200}")
        if len(slug) > _SLUG_MAX_LEN or not _SLUG_RE.match(slug):
            raise ValueError(
                f"ModeConfig: invalid slug '{slug}' (expected lowercase kebab-case, <= {_SLUG_MAX_LEN} chars)"
            )

        raw_kind = data.get("kind") or (KIND_FRAMEWORK if slug in FRAMEWORK_SLUGS else KIND_BUSINESS)
        if raw_kind not in (KIND_FRAMEWORK, KIND_BUSINESS):
            raise ValueError(f"ModeConfig: invalid kind '{raw_kind}' for slug '{slug}' (framework | business)")
        if raw_kind == KIND_FRAMEWORK and slug not in FRAMEWORK_SLUGS:
            raise ValueError(
                f"ModeConfig: slug '{slug}' declares kind=framework but is not in FRAMEWORK_SLUGS {sorted(FRAMEWORK_SLUGS)}"
            )

        default_priority = PRIORITY_FRAMEWORK_MIN if raw_kind == KIND_FRAMEWORK else 50
        try:
            priority = int(data.get("priority", default_priority))
        except (TypeError, ValueError):
            raise ValueError(f"ModeConfig: invalid priority {data.get('priority')!r} for slug '{slug}'")

        # mode-工具解耦（project/docs/mode工具解耦方案.md D2/D3）：aliases/groups
        # 字段已退役。aliases 残留 yaml 仅告警（纯清理，不 FAIL）；
        # groups 为 Roo Code 兼容字段（resources 侧统一携带），静默忽略。
        if data.get("aliases"):
            logger.warning(
                "ModeConfig: 'aliases' is deprecated and ignored (mode-tool decoupled) for slug '%s' — strip it from the yaml",
                slug,
            )

        return cls(
            slug=slug,
            name=str(data.get("name", "")),
            kind=raw_kind,
            priority=priority,
            can_delegate=bool(data.get("canDelegate", True)),
            role_definition=data.get("roleDefinition", ""),
            when_to_use=data.get("whenToUse", ""),
            description=data.get("description", ""),
            source=str(data.get("source", source)),
            custom_instructions=data.get("customInstructions", ""),
            rules=data.get("rules", {}) or {},
        )

    def validation_issues(self, known_team_codes: set[str] | None = None) -> list[str]:
        """命名规范（§4.8）内容级校验，返回问题清单（空 = 合规）。

        Phase 1 作为 deprecation warning 输出；Phase 3 起加载端升级为 FAIL。
        known_team_codes：已注册的 team_code 集合；None 时跳过前缀校验
        （market 扫描端与 Phase 3 迁移后传入）。
        """
        issues: list[str] = []

        # slug：business 必须 {team_code}- 前缀（Phase 3 起强制；未提供 team_codes 时跳过）
        if not self.is_framework and known_team_codes is not None:
            if not any(self.slug.startswith(f"{code}-") for code in known_team_codes):
                issues.append(
                    f"slug '{self.slug}': business slug should use '{{team_code}}-{{mode}}' prefix "
                    f"(registered codes: {sorted(known_team_codes)})"
                )

        # name：英文 Title Case、无中文、≤32 字符、≤4 词
        display = strip_emoji_prefix(self.name)
        if not display:
            issues.append(f"slug '{self.slug}': empty display name")
        else:
            if _CJK_RE.search(display):
                issues.append(f"slug '{self.slug}': name '{self.name}' contains CJK (use English, §4.8.2)")
            if len(display) > _NAME_MAX_LEN or not _NAME_RE.match(display):
                issues.append(
                    f"slug '{self.slug}': name '{self.name}' should be English Title Case, <= {_NAME_MAX_LEN} chars"
                )
            if len(display.split()) > _NAME_MAX_WORDS:
                issues.append(f"slug '{self.slug}': name '{self.name}' should be 2-{_NAME_MAX_WORDS} words (personified role)")

        # priority 保留段（pdca 显式 0 例外）
        if self.is_framework:
            if self.slug == "pdca":
                if self.priority != PRIORITY_PDCA:
                    issues.append(f"slug 'pdca': priority must be {PRIORITY_PDCA} (explicit lowest), got {self.priority}")
            elif not (PRIORITY_FRAMEWORK_MIN <= self.priority <= 100):
                issues.append(
                    f"slug '{self.slug}': framework priority must be >= {PRIORITY_FRAMEWORK_MIN}, got {self.priority}"
                )
        elif not (1 <= self.priority <= 79):
            issues.append(f"slug '{self.slug}': business priority must be in [1, 79], got {self.priority}")

        return issues

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "slug": self.slug,
            "name": self.name,
            "kind": self.kind,
            "priority": self.priority,
            "canDelegate": self.can_delegate,
            "roleDefinition": self.role_definition,
            "whenToUse": self.when_to_use,
            "description": self.description,
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
            camel_key = {"canDelegate": "can_delegate", "roleDefinition": "role_definition", "whenToUse": "when_to_use", "customInstructions": "custom_instructions"}.get(key, key)
            if value is not None and value not in ("", [], {}):
                setattr(merged, camel_key, value)

        return merged
