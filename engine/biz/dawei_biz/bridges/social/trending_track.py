"""热点采集轨客户端 —— 引擎侧 claim → 抓取 → 回报(与发布轨并行,独立循环)。

服务器(browser 型源到期)→ social_collect_task → 本客户端 claim(按引擎连接器
能力平台)→ trending_scraper(连接器 trending 段)→ result(条目入库,租户隔离)。

与 BrowserTrackClient 的差异:
  - claim 一次带 platforms 列表(采集按引擎能力领单;发布按单平台)
  - 无人工确认关卡(采集不发布内容;发布轨的 HumanGate 语义不适用)
  - 失败无重试语义(服务器 cadence 到期自动派新任务)
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from dawei_biz.bridges.social.browser_track import OUTCOME_ERROR_CLASS, _auth_headers
from dawei.tools.browser.browser_engine import get_execution_limiter

DEFAULT_ERROR_CLASS = "PLATFORM_REJECTED"
SCRAPE_HARD_TIMEOUT_S = 300.0  # 单任务抓取硬时限(Chrome 启动+页面+滚动;超时放弃回报 EXECUTOR_ERROR)


def collectable_platforms() -> list[str]:
    """本引擎可采集的平台:连接器 capability.trending==browser 且 trending.url 非空。"""
    from dawei_biz.bridges.social.browser_track import RECIPE_DIRS, load_recipe

    out: list[str] = []
    for root in RECIPE_DIRS:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            recipe = load_recipe(d.name)
            if not recipe:
                continue
            cap = (recipe.get("capability") or {}).get("trending")
            trending_url = str((recipe.get("trending") or {}).get("url") or "").strip()
            if cap == "browser" and trending_url:
                out.append(d.name)
    return sorted(set(out))


def default_collect_claim(platforms: list[str], limit: int = 3, *, tenant_id: str = "",
                          token: str = "", api_key: str = "",
                          executor_id: str = "", executor_type: str = "desktop_sidecar",
                          version: str = "") -> list[dict[str, Any]]:
    """控制面采集 claim(POST /trending/collect/claim,按租户隔离领单)。

    executor_id 非空时随 claim 续约 presence 心跳(执行端在线可见性,与发布轨同源)。
    """
    import httpx

    payload: dict[str, Any] = {"platforms": platforms, "limit": limit}
    if executor_id:
        payload["executor_id"] = executor_id
        payload["executor_type"] = executor_type
        payload["version"] = version
    base = os.getenv("SOCIAL_CONTROL_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("SOCIAL_CONTROL_URL 未设置：social 控制面集成默认关闭（显式配置后启用）")
    resp = httpx.post(f"{base}/api/v1/trending/collect/claim",
                      json=payload,
                      headers=_auth_headers(tenant_id, token=token, api_key=api_key),
                      timeout=15.0)
    resp.raise_for_status()
    return resp.json().get("tasks", [])


def default_collect_report(task_id: str, payload: dict[str, Any], *, tenant_id: str = "",
                           token: str = "", api_key: str = "") -> None:
    """控制面采集结果回报(ok=条目清单;失败=error_class 分类)。"""
    import httpx

    base = os.getenv("SOCIAL_CONTROL_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("SOCIAL_CONTROL_URL 未设置：social 控制面集成默认关闭（显式配置后启用）")
    resp = httpx.post(f"{base}/api/v1/trending/collect/{task_id}/result",
                      json=payload,
                      headers=_auth_headers(tenant_id, token=token, api_key=api_key),
                      timeout=15.0)
    resp.raise_for_status()


async def _default_scrape(task: dict[str, Any], *, headless: bool = True) -> dict[str, Any]:
    from dawei.tools.browser.trending_scraper import scrape_trending

    return await scrape_trending(task["platform"], headless=headless)


class TrendingCollectClient:
    """采集轨轮询:claim(能力平台)→ 抓取(worker 线程独立事件循环)→ 回报。"""

    def __init__(
        self,
        *,
        tenant_id: str = "default",
        platforms: list[str] | None = None,  # None = 每轮动态取连接器能力(装新包即生效)
        limit: int = 3,
        poll_interval: float = 60.0,
        headless: bool | None = None,
        claim=None,
        report=None,
        scrape=None,
        auth_token: str = "",
        api_key: str = "",
        limiter: Any | None = None,  # 与发布轨共享的执行限流器(BE-1/BE-2);缺省进程级单例
        executor_id: str = "",       # 执行端自报身份(claim 即心跳);缺省 host:pid
        executor_type: str = "desktop_sidecar",  # desktop_sidecar | light_app
    ):
        self.tenant_id = tenant_id
        self._platforms_cfg = platforms
        self.limit = limit
        self.poll_interval = poll_interval
        self._limiter = limiter if limiter is not None else get_execution_limiter()
        self.headless = headless if headless is not None else os.getenv("SOCIAL_BROWSER_HEADLESS", "1") != "0"
        import socket

        self.executor_id = executor_id or f"{socket.gethostname()}:pid{os.getpid()}"
        self.executor_type = executor_type
        tid = tenant_id
        if claim is not None:
            self.claim = claim
        else:
            eid, etype = self.executor_id, self.executor_type

            def _claim(platforms_: list[str], limit_: int = 3) -> list[dict[str, Any]]:
                return default_collect_claim(platforms_, limit_, tenant_id=tid,
                                             token=auth_token, api_key=api_key,
                                             executor_id=eid, executor_type=etype)
            self.claim = _claim
        if report is not None:
            self.report = report
        else:
            def _report(task_id: str, payload: dict[str, Any]) -> None:
                default_collect_report(task_id, payload, tenant_id=tid,
                                       token=auth_token, api_key=api_key)
            self.report = _report
        self._scrape = scrape or _default_scrape
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def platforms(self) -> list[str]:
        """采集平台面:显式配置优先;否则每轮按已安装连接器动态计算(热装即生效)。"""
        return self._platforms_cfg if self._platforms_cfg is not None else collectable_platforms()

    # -- 单轮 ---------------------------------------------------------

    async def _run_one(self, task: dict[str, Any]) -> dict[str, Any]:
        """单任务抓取(worker 线程新事件循环 + 整体超时,与主循环不互锁)→ result 载荷。

        BE-1/BE-2 限流与发布轨共享同一限流器:采集与发布同平台互斥、全局 Chrome
        并发 ≤2;拿不到 → executor_busy(RATE_LIMITED,服务器 cadence 到期重派)。
        """
        platform = str(task.get("platform", ""))
        if not self._limiter.acquire_nowait(platform):
            return {"task_id": task["id"], "ok": False, "items": [],
                    "error_class": OUTCOME_ERROR_CLASS["executor_busy"], "outcome": "executor_busy",
                    "error": f"platform {platform} busy or global limit reached"}
        try:
            import asyncio as _aio

            result = await asyncio.wait_for(
                asyncio.to_thread(_aio.run, self._scrape(task, headless=self.headless)),
                timeout=SCRAPE_HARD_TIMEOUT_S,
            )
        except TimeoutError:
            return {"task_id": task["id"], "ok": False, "items": [],
                    "error_class": "EXECUTOR_ERROR", "error": f"抓取超时(>{SCRAPE_HARD_TIMEOUT_S}s)"}
        except Exception as e:  # 浏览器崩溃等 → 分类回报,不抛出
            return {"task_id": task["id"], "ok": False, "items": [],
                    "error_class": "EXECUTOR_ERROR", "error": str(e)[:200]}
        finally:
            self._limiter.release(platform)
        if result.get("ok"):
            return {"task_id": task["id"], "ok": True,
                    "items": [{"platform": task["platform"], **it} for it in result.get("items", [])]}
        outcome = str(result.get("outcome", ""))
        return {"task_id": task["id"], "ok": False, "items": [],
                "error_class": OUTCOME_ERROR_CLASS.get(outcome, DEFAULT_ERROR_CLASS),
                "outcome": outcome, "error": str(result.get("error", ""))[:200]}

    async def poll_once(self) -> dict[str, int]:
        claimed = reported = 0
        platforms = self.platforms  # 动态能力面
        if not platforms:
            return {"claimed": 0, "reported": 0, "skipped": "no_collectable_platforms"}
        try:
            coro = self.claim(platforms, self.limit)
            if asyncio.iscoroutine(coro):
                tasks = await coro
            else:
                tasks = coro
        except Exception:
            return {"claimed": 0, "reported": 0, "error": "control_plane_unreachable"}
        for task in tasks or []:
            claimed += 1
            payload = await self._run_one(task)
            try:
                coro = self.report(task["id"], payload)
                if asyncio.iscoroutine(coro):
                    await coro
                reported += 1
            except Exception:
                pass  # 回报失败:服务器租约超时回收后重领
        return {"claimed": claimed, "reported": reported}

    # -- 常驻循环 ------------------------------------------------------

    async def run_forever(self) -> None:
        while self._running:
            try:
                await self.poll_once()
            except Exception:
                pass  # 防御性兜底:循环不退出
            await asyncio.sleep(self.poll_interval)

    def start(self) -> bool:
        if self._running:
            return False
        self._running = True
        self._task = asyncio.get_running_loop().create_task(self.run_forever())
        return True

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


_COLLECT: TrendingCollectClient | None = None


def shared_collect_client() -> TrendingCollectClient:
    global _COLLECT
    if _COLLECT is None:
        _COLLECT = TrendingCollectClient()
    return _COLLECT


__all__ = [
    "TrendingCollectClient", "shared_collect_client", "collectable_platforms",
    "default_collect_claim", "default_collect_report",
]
