# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ModeRegistry — 每 workspace 单例的 mode 唯一读入口（project/docs/mode统一管理.md §4.4/§4.5）

职责：
- 持有 ModeManager（现 ModeConfigLoader 角色）加载结果，构建唯一内存事实源；
- 框架模式保护：workspace 层不可覆盖 framework slug（§4.3；user 层已删除）；
- ModeResolver 显式兜底链：explicit > task > mention > orchestrator > pdca；
- 未知 slug 抛 ModeNotFoundError（P8：不再静默合成默认值）。

aliases 已退役（mode工具解耦方案 D2）：别名是纯兼容物，存量数据经
scripts/migrate_mode_decoupling.py 直接改写，不再有归一路径。

禁止再 ad-hoc `ModeManager(...)`（P6）：一律经 get_registry(workspace_path)。
"""

import logging
import threading
from dataclasses import dataclass

from dawei.entity.mode import FRAMEWORK_SLUGS, KIND_FRAMEWORK, ModeConfig

logger = logging.getLogger(__name__)


class ModeNotFoundError(KeyError):
    """未知 mode slug（FAST FAIL：不再合成默认 ModeConfig）"""

    def __init__(self, slug: str, available: list[str] | None = None):
        self.slug = slug
        self.available = available or []
        hint = f" (available: {', '.join(self.available[:20])})" if self.available else ""
        super().__init__(f"Unknown mode slug: {slug!r}{hint}")


@dataclass
class ModeSelectionContext:
    """ModeResolver 选择链输入（§4.5：高 → 低，前者命中即止）"""

    explicit_slug: str | None = None  # 用户 UI 选择 / switch_mode / new_task(mode=...)
    task_mode: str | None = None      # TaskGraph 节点声明的 mode
    mention_slug: str | None = None   # @-expert 机制


class ModeRegistry:
    """per-workspace mode 注册表（唯一读入口）"""

    def __init__(self, workspace_path: str | None = None):
        self.workspace_path = workspace_path
        # 延迟导入避免与 mode_manager 的潜在循环依赖
        from dawei.mode.mode_manager import ModeManager

        self._manager = ModeManager(workspace_path=workspace_path)
        self._modes: dict[str, ModeConfig] = {}
        self._naming_violations: list[str] = []

        self._apply_framework_protection()
        self._validate_naming()
        self._run_startup_invariants()

        fw = sorted(self.framework_slugs)
        logger.info(
            "ModeRegistry[%s] initialized: %d modes, framework=%s, %d naming warning(s)",
            workspace_path or "<builtin>",
            len(self._modes),
            fw,
            len(self._naming_violations),
        )

    # ------------------------------------------------------------------ load

    def _apply_framework_protection(self) -> None:
        """§4.3 合并规则：framework slug 只认 builtin 源，非 builtin 定义一律拒绝（保护 + 告警）"""
        for layer_name, layer in (
            ("workspace", self._manager._workspace_modes),  # noqa: SLF001
        ):
            for slug in list(layer.keys()):
                if slug in FRAMEWORK_SLUGS:
                    del layer[slug]
                    logger.warning(
                        "ModeRegistry: framework slug '%s' defined in %s layer — removed (framework modes cannot be overridden; builtin wins)",
                        slug,
                        layer_name,
                    )

        # 重新合并（保护后的层级；user 层已删除 — Phase 4/P9）
        merged = {}
        merged.update(self._manager._builtin_modes)      # noqa: SLF001
        merged.update(self._manager._workspace_modes)    # noqa: SLF001
        self._modes = merged

    def _validate_naming(self) -> None:
        """§4.8 命名规范内容级校验：Phase 1 仅告警（deprecation），Phase 3 升级 FAIL"""
        self._naming_violations = []
        for mode in self._modes.values():
            self._naming_violations.extend(mode.validation_issues())
        for issue in self._naming_violations:
            logger.warning("ModeRegistry naming (deprecation): %s", issue)

    def _run_startup_invariants(self) -> None:
        """启动断言（§4.6 INV-1..5）。Phase 2 起由 tool_manager 提供；未就绪时跳过。"""
        try:
            from dawei.tools.tool_manager import assert_mode_invariants  # 延迟导入避免循环
        except ImportError:
            return
        violations = assert_mode_invariants(self)
        if violations:
            raise ValueError(
                "Mode invariant violations (refusing registry): " + "; ".join(violations)
            )

    # ------------------------------------------------------------------ read

    def find(self, slug: str) -> ModeConfig | None:
        return self._modes.get(slug)

    def get(self, slug: str) -> ModeConfig:
        mode = self.find(slug)
        if mode is None:
            raise ModeNotFoundError(slug, sorted(self._modes.keys()))
        return mode

    def all(self, kind: str | None = None) -> list[ModeConfig]:
        """全部模式，按 priority 降序（§4.5 用途 a：排序与建议次序）"""
        modes = [m for m in self._modes.values() if kind is None or m.kind == kind]
        return sorted(modes, key=lambda m: (-m.priority, m.slug))

    @property
    def framework_slugs(self) -> set[str]:
        return {m.slug for m in self._modes.values() if m.kind == KIND_FRAMEWORK}

    def is_valid(self, slug: str) -> bool:
        return self.find(slug) is not None

    def config_sources(self, slug: str) -> dict[str, bool]:
        """层级归属查询（API 列表 source 标签用；user 层已删除，仅 builtin/workspace）"""
        return self._manager.get_config_sources(slug)

    def can_delegate_to(self, slug: str) -> bool:
        """§4.5 用途 b：can_delegate=false 的模式不可作为子任务目标（new_task 校验）"""
        return self.get(slug).can_delegate

    @property
    def naming_violations(self) -> list[str]:
        return list(self._naming_violations)

    @property
    def manager(self):
        """持有的加载器/管理器（供 UserWorkspace.mode_manager 等存量消费方委托，
        invalidate 后随新 Registry 实例自动跟随 — Phase 4 invalidate 挂钩）"""
        return self._manager

    # --------------------------------------------------------------- resolve

    def resolve(self, ctx: ModeSelectionContext) -> str:
        """显式兜底链（§4.5）：explicit > task > mention > orchestrator > pdca。

        链上显式来源的 slug 必须已注册：未注册时告警并继续下一级（会话不中断，
        入口方 switch_mode/new_task 应自行 get() 校验并给用户报错）。
        """
        for attr, label in (
            (ctx.explicit_slug, "explicit"),
            (ctx.task_mode, "task"),
            (ctx.mention_slug, "mention"),
        ):
            if not attr:
                continue
            mode = self.find(attr)
            if mode is not None:
                return mode.slug
            logger.warning("ModeResolver: %s slug %r not registered — falling through", label, attr)

        if "orchestrator" in self._modes:
            return "orchestrator"
        if "pdca" in self._modes:
            logger.warning("ModeResolver: orchestrator missing — falling back to pdca")
            return "pdca"
        raise ModeNotFoundError("orchestrator", sorted(self._modes.keys()))


# ------------------------------------------------------------------ 单例管理（P6：禁止 ad-hoc ModeManager）

_registries: dict[str, ModeRegistry] = {}
_registry_lock = threading.Lock()


def _registry_key(workspace_path: str | None) -> str:
    return (workspace_path or "").rstrip("/")


def get_registry(workspace_path: str | None = None) -> ModeRegistry:
    """获取（或创建）per-workspace ModeRegistry 单例"""
    key = _registry_key(workspace_path)
    registry = _registries.get(key)
    if registry is not None:
        return registry
    with _registry_lock:
        registry = _registries.get(key)
        if registry is None:
            registry = ModeRegistry(workspace_path=workspace_path or None)
            _registries[key] = registry
        return registry


def invalidate_registry(workspace_path: str | None = None) -> None:
    """安装/卸载 agent 后由 resource_installer / market API 显式调用（消除 300s 陈旧窗口）"""
    with _registry_lock:
        if workspace_path is None:
            _registries.clear()
        else:
            _registries.pop(_registry_key(workspace_path), None)
    logger.info("ModeRegistry invalidated for %s", workspace_path or "<all>")


def builtin_framework_slugs() -> set[str]:
    """builtin 定义的 framework slug（供 API 层动态取值，替代硬编码 FRAMEWORK_MODE_SLUGS 中的实体部分）"""
    return set(FRAMEWORK_SLUGS)
