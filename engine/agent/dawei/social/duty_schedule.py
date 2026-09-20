"""值班 Agent 定时器(PRD §6.10:按品牌策略定时执行 拉热点→选题→成稿→自检)。

值班运行在桌面本地引擎(桌面在线才跑,§11.1 第 2 层语义);
控制面不可达/LLM 故障 → 跳过本轮,循环不退出。runner 可注入(单测打桩)。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_MIN_INTERVAL_MIN = 1.0  # 防误配过密(最低 1 分钟)


def default_runner(brand_id: str, *, tenant_id: str = "default", draft_count: int = 0) -> dict:
    """默认值班执行体:复用 /api/social/duty 同一链路(draft_count>0 时续跑 L3 成稿)。"""
    from dawei.social import bridge, duty_orchestrator, service

    items = bridge.fetch_trending(tenant_id=tenant_id)
    brand_profile = {"brand_id": brand_id}
    ideas = duty_orchestrator.run_duty(items, brand_profile, llm_call=service.default_llm_call)
    created = 0
    for idea in ideas:
        try:
            bridge.post_idea(idea, brand_id=brand_id, tenant_id=tenant_id)
            created += 1
        except Exception:
            continue
    drafts = 0
    if draft_count > 0 and ideas:
        try:
            out = duty_orchestrator.run_duty_pipeline(
                items, brand_profile, llm_call=service.default_llm_call,
                brand_id=brand_id, tenant_id=tenant_id, max_drafts=draft_count,
            )
            drafts = out["created_drafts"]
        except Exception:
            drafts = 0  # 成稿失败不影响选题结果(选题已入库)
    return {"analyzed": len(items), "created": created, "created_drafts": drafts}


class DutyScheduler:
    """每品牌一个后台循环;set() 幂等(改 interval 重启该品牌循环)。"""

    def __init__(self, runner: Callable[..., Any] | None = None):
        self._runner = runner or default_runner
        self._tasks: dict[str, asyncio.Task] = {}
        self._config: dict[str, dict] = {}

    async def _loop(self, brand_id: str, interval_minutes: float,
                    tenant_id: str, draft_count: int) -> None:
        while True:
            try:
                self._runner(brand_id, tenant_id=tenant_id, draft_count=draft_count)
            except Exception:
                pass  # 单轮故障(控制面不可达/LLM 故障)不杀循环
            await asyncio.sleep(interval_minutes * 60)

    def set(self, brand_id: str, *, interval_minutes: float, enabled: bool,
            tenant_id: str = "default", draft_count: int = 0) -> dict:
        if interval_minutes <= 0:
            raise ValueError("interval_minutes 必须为正")
        old = self._tasks.pop(brand_id, None)
        if old is not None:
            old.cancel()
        if enabled:
            self._tasks[brand_id] = asyncio.get_running_loop().create_task(
                self._loop(brand_id, interval_minutes, tenant_id, draft_count))
            self._config[brand_id] = {"interval_minutes": interval_minutes, "enabled": True,
                                      "tenant_id": tenant_id, "draft_count": draft_count}
        else:
            self._config[brand_id] = {"interval_minutes": interval_minutes, "enabled": False,
                                      "tenant_id": tenant_id, "draft_count": draft_count}
        return self._config[brand_id]

    def status(self) -> list[dict]:
        return [{"brand_id": b, **cfg} for b, cfg in self._config.items()]

    async def stop_all(self) -> None:
        for t in self._tasks.values():
            t.cancel()
        self._tasks.clear()


_SCHED: DutyScheduler | None = None


def shared_scheduler() -> DutyScheduler:
    global _SCHED
    if _SCHED is None:
        _SCHED = DutyScheduler()
    return _SCHED


__all__ = ["DutyScheduler", "default_runner", "shared_scheduler"]
