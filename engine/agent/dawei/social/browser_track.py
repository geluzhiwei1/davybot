"""浏览器轨发布 —— 真机执行入口(social-control 下发 → Chrome → 回报)。

使用场景(重要):本模块只在本机"执行端"运行 ——
  1. 桌面端 dawei sidecar(davybot-app Tauri 内嵌引擎);
  2. davy-light-app 壳的 Python 兼容路径(原生路径为其 src-tauri/src/track/,协议同源)。
SaaS 云端引擎(DAWEI_DEPLOYMENT_MODE=saas)从不执行本模块:云端只把任务排进
nn-social-flow 控制面;router.py 对 /browser-track/start、/login* 端点在 saas
模式下 FAST FAIL(403)。本机执行权由 TrackLock(DAWEI_HOME/browser-track.lock)
在 sidecar 与壳之间互斥(壳 Rust 侧读写同一文件,见 方案.md §8 双 claim 风险)。

链路:拉取 due 浏览器轨任务 → RealBrowserSession(平台 profile)
→ BrowserPublishExecutor(recipe selectors,人工确认回调)→ 结果回报控制面。

闭环(PRD §11.2):
  HumanGate          人工关卡(确认/验证码):HTTP 可见待办 + resolve + 超时
  BrowserTrackClient 轮询 claim → 执行(默认人工确认)→ 结果分类回报
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from dawei.tools.browser.browser_engine import get_execution_limiter
from dawei.tools.browser.browser_executor import BrowserPublishExecutor
from dawei.tools.browser.real_session import RealBrowserSession

RECIPE_DIRS = [
    # 本地开发包(agent/market-packages/connectors);生产从市场通道(biz1)热载到 ~/.normnomos
    Path(__file__).resolve().parents[2] / "market-packages" / "connectors",
    Path.home() / ".normnomos" / "connectors",
]

# 执行器 outcome → 控制面 error_class(§11.2 差异点 4:错误分类驱动重试策略)
OUTCOME_ERROR_CLASS: dict[str, str] = {
    "selector_stale": "SELECTOR_STALE",
    "recipe_missing": "SELECTOR_STALE",
    "aborted_by_human": "ABORTED_BY_HUMAN",
    "verify_failed": "VERIFY_FAILED",
    "captcha_timeout": "CAPTCHA_REQUIRED",
    "login_required": "LOGIN_REQUIRED",  # 未登录:不可重试,死信回人工(扫码后重排)
    "executor_busy": "RATE_LIMITED",     # BE-1/BE-2 限流(同平台互斥/全局并发满):可重试,不进死信
}
DEFAULT_ERROR_CLASS = "PLATFORM_REJECTED"  # 未知失败按不可重试回人工(宁死信不重发)


# ============================================================
# TrackLock —— 本机浏览器轨执行权互斥(Gap:双 claim 防护)
# 桌面 sidecar(Python)与 davy-light-app 壳(Rust)竞争同一控制面任务流;
# 双方同时 claim 会同 profile 双开 Chrome(登录态/风控互踩)。锁文件为
# DAWEI_HOME/browser-track.lock,壳 Rust 侧 track/control 读写同一文件。
# ============================================================

class TrackLockHeldError(RuntimeError):
    """浏览器轨执行权已被其他活进程持有(sidecar ↔ 壳互斥)。"""

    def __init__(self, holder: dict[str, Any]):
        self.holder = holder
        super().__init__(
            f"browser-track lock held by pid={holder.get('pid')} "
            f"holder={holder.get('holder')} since={holder.get('started_at')}")


def _track_lock_path() -> Path:
    from dawei import get_dawei_home

    return Path(get_dawei_home()) / "browser-track.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 进程存在但属其他用户:视为存活,不夺锁
    except OSError:
        return False


def read_track_lock() -> dict[str, Any] | None:
    """读取当前执行权持有者信息;无锁/损坏返回 None。"""
    try:
        data = json.loads(_track_lock_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def acquire_track_lock(*, tenant_id: str = "", platforms: list[str] | None = None,
                       holder: str = "dawei-engine") -> None:
    """获取本机执行权;被活进程持有抛 TrackLockHeldError(FAST FAIL,不排队)。

    - 同进程重复获取:幂等放行(进程内重复 start 由 router/client.start 拒绝);
    - 持锁进程已死(崩溃残留):陈旧锁自动接管;
    - 写入走 tmp+rename 原子替换,防并发撕裂。
    """
    path = _track_lock_path()
    existing = read_track_lock()
    if existing:
        pid = int(existing.get("pid") or 0)
        if pid == os.getpid():
            return
        if pid and _pid_alive(pid):
            raise TrackLockHeldError(existing)
        # 陈旧锁(持有进程已死)→ 接管
    info: dict[str, Any] = {
        "pid": os.getpid(), "holder": holder, "tenant_id": tenant_id,
        "platforms": platforms or [], "started_at": time.time(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def release_track_lock() -> None:
    """释放执行权;仅当锁属本进程时删除(他人/陈旧锁不动)。"""
    path = _track_lock_path()
    existing = read_track_lock()
    if existing and int(existing.get("pid") or 0) == os.getpid():
        try:
            path.unlink()
        except OSError:
            pass


class HumanGate:
    """人工关卡 —— 确认/验证码的人机协同待办表(PRD §3.2 原则 3:发布永不无人监督)。

    执行侧 wait_confirm/wait_captcha 挂起等待;桌面 UI 经
    GET  /api/social/browser-track/pending          查看待办
    POST /api/social/browser-track/confirm/{id}     放行/终止
    POST /api/social/browser-track/captcha/{id}/solve 验证码已解决
    超时一律按"未放行"处理(终止),待办移出。
    """

    def __init__(self, confirm_timeout: float = 600.0):
        self.confirm_timeout = confirm_timeout
        self._pending: dict[str, dict[str, Any]] = {}
        self._futures: dict[str, asyncio.Future] = {}

    def _file(self, kind: str, *, task_id: str = "", platform: str = "",
              detail: dict[str, Any] | None = None) -> str:
        request_id = uuid.uuid4().hex[:12]
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = {
            "request_id": request_id, "kind": kind, "task_id": task_id,
            "platform": platform, "detail": detail or {}, "created_at": time.time(),
        }
        self._futures[request_id] = fut
        return request_id

    async def _await(self, request_id: str, timeout: float) -> bool:
        try:
            return await asyncio.wait_for(self._futures[request_id], timeout=timeout)
        except TimeoutError:
            return False
        finally:
            self._pending.pop(request_id, None)
            self._futures.pop(request_id, None)

    async def wait_confirm(self, task_id: str, platform: str, *,
                           timeout: float | None = None,
                           screenshot: str | None = None) -> bool:
        """发布前人工确认(默认开,§11.2 序列图"推送预览(截图+diff)")。"""
        rid = self._file("confirm", task_id=task_id, platform=platform,
                         detail={"screenshot": screenshot})
        return await self._await(rid, self.confirm_timeout if timeout is None else timeout)

    async def wait_captcha(self, platform: str, *, timeout: float | None = None) -> bool:
        """验证码人机协同:用户本机 Chrome 解决后放行。"""
        rid = self._file("captcha", platform=platform)
        return await self._await(rid, self.confirm_timeout if timeout is None else timeout)

    def resolve(self, request_id: str, approved: bool) -> bool:
        fut = self._futures.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(bool(approved))
            return True
        return False

    def pending(self) -> list[dict[str, Any]]:
        return list(self._pending.values())


async def _default_run(task: dict[str, Any], *, confirm_callback=None, headless=True,
                        auto_confirm=False, captcha_callback=None) -> dict[str, Any]:
    """默认执行体:task 字段 → run_browser_publish(平台/标题/正文/模式)。

    auto_confirm=True 时上层应传 confirm_callback=None —— run_browser_publish
    收到「无回调 + 显式放行」组合会内建恒真确认(云端审批为唯一人工关卡)。
    captcha_callback:验证码人机协同桥(BrowserTrackClient 注入);None 时执行器
    命中验证码即 captcha_timeout → CAPTCHA_REQUIRED(云端/壳 auto 路径)。
    """
    return await run_browser_publish(
        task["platform"], title=task.get("title", ""), body=task.get("body", ""),
        mode=task.get("mode", "draft_box"), confirm_callback=confirm_callback,
        auto_confirm=auto_confirm, headless=headless, captcha_callback=captcha_callback,
    )


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


def _auth_headers(tenant_id: str = "", *, token: str = "", api_key: str = "") -> dict[str, str]:
    """控制面鉴权头:prod(SC_AUTH_DEV=false)要求 Bearer/X-Api-Key,仅 X-Tenant-Id 会 401。

    优先级:X-Api-Key(服务账号,开放平台)> Bearer(桌面登录用户)。
    显式入参 > 环境变量(SOCIAL_API_KEY / SOCIAL_AUTH_TOKEN,由启动方注入,不落盘)。
    """
    h: dict[str, str] = {"X-Tenant-Id": tenant_id or os.getenv("SOCIAL_TENANT_ID", "default")}
    key = api_key or os.getenv("SOCIAL_API_KEY", "")
    tok = token or os.getenv("SOCIAL_AUTH_TOKEN", "")
    if key:
        h["X-Api-Key"] = key
    elif tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def default_claim(platform: str, limit: int = 5, *, tenant_id: str = "",
                  token: str = "", api_key: str = "",
                  executor_id: str = "", executor_type: str = "desktop_sidecar") -> list[dict[str, Any]]:
    """控制面 claim(POST 契约)。tenant_id 缺省回落 SOCIAL_TENANT_ID/default。

    executor_id 非空时随 claim 续约 presence 心跳(控制面壳在线可见性)。
    """
    import httpx

    payload: dict[str, Any] = {"platform": platform, "limit": limit}
    if executor_id:
        payload["executor_id"] = executor_id
        payload["executor_type"] = executor_type
    base = os.getenv("SOCIAL_CONTROL_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("SOCIAL_CONTROL_URL 未设置：social 控制面集成默认关闭（显式配置后启用）")
    resp = httpx.post(f"{base}/api/v1/browser-tasks/claim",
                      json=payload,
                      headers=_auth_headers(tenant_id, token=token, api_key=api_key),
                      timeout=15.0)
    resp.raise_for_status()
    return resp.json().get("tasks", [])


def default_report(payload: dict[str, Any], *, tenant_id: str = "",
                   token: str = "", api_key: str = "") -> None:
    """控制面结果回报(error_class 分类由控制面联动 schedule)。"""
    import httpx

    base = os.getenv("SOCIAL_CONTROL_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("SOCIAL_CONTROL_URL 未设置：social 控制面集成默认关闭（显式配置后启用）")
    resp = httpx.post(
        f"{base}/api/v1/browser-tasks/{payload['task_id']}/result",
        json={"ok": payload["ok"], "result_url": payload.get("result_url"),
              "result_detail": payload.get("result_detail", {})},
        headers=_auth_headers(tenant_id, token=token, api_key=api_key),
        timeout=15.0)
    resp.raise_for_status()


class BrowserTrackClient:
    """浏览器轨闭环客户端:claim → 执行(人工确认默认开)→ 分类回报。

    执行在 worker 线程跑(独立事件循环),confirm_callback 经
    run_coroutine_threadsafe 回到主循环等人工关卡 —— HTTP resolve 与执行并发不互锁。
    """

    def __init__(
        self,
        *,
        tenant_id: str = "default",
        platforms: list[str] | None = None,
        limit: int = 5,
        poll_interval: float = 15.0,
        headless: bool | None = None,  # None → SOCIAL_BROWSER_HEADLESS(默认 1;真机风控敏感建议 0)
        gate: HumanGate | None = None,
        claim: Callable[..., Any] | None = None,
        report: Callable[..., Any] | None = None,
        run: Callable[..., Any] | None = None,
        auth_token: str = "",  # 控制面 Bearer(桌面登录用户);空则回落 SOCIAL_AUTH_TOKEN
        api_key: str = "",     # 控制面服务账号;空则回落 SOCIAL_API_KEY(优先于 token)
        auto_confirm: bool = False,  # True:跳过本地人工确认(云端审批为唯一关卡;light-app 用)
        limiter: Any | None = None,  # 执行限流器(BE-1/BE-2);缺省进程级单例,测试可注入
        executor_id: str = "",       # 执行端自报身份(claim 即心跳);缺省 host:pid
        executor_type: str = "desktop_sidecar",  # desktop_sidecar | light_app
    ):
        self.tenant_id = tenant_id
        self.platforms = platforms or ["xiaohongshu"]
        self.limit = limit
        self.poll_interval = poll_interval
        self.auto_confirm = auto_confirm
        import socket

        self.executor_id = executor_id or f"{socket.gethostname()}:pid{os.getpid()}"
        self.executor_type = executor_type
        self.headless = headless if headless is not None else os.getenv("SOCIAL_BROWSER_HEADLESS", "1") != "0"
        self.gate = gate or shared_human_gate()
        if claim is not None:
            self.claim, self.report = claim, report or default_report
        else:  # 默认通道带上客户端租户(否则 X-Tenant-Id 不匹配领不到单)
            tid = tenant_id
            eid, etype = self.executor_id, self.executor_type

            def _claim(platform: str, limit: int = 5) -> list[dict[str, Any]]:
                return default_claim(platform, limit, tenant_id=tid,
                                     token=auth_token, api_key=api_key,
                                     executor_id=eid, executor_type=etype)

            def _report(payload: dict[str, Any]) -> None:
                default_report(payload, tenant_id=tid, token=auth_token, api_key=api_key)

            self.claim, self.report = _claim, report or _report
        self._run = run or _default_run
        self._default_run_path = run is None  # 注入式 run 回调签名固定,captcha 桥仅默认路径接
        self._limiter = limiter if limiter is not None else get_execution_limiter()
        self._running = False
        self._task: asyncio.Task | None = None

    # -- 单轮 ---------------------------------------------------------

    def _confirm_callback(self, task_id: str, platform: str, loop: asyncio.AbstractEventLoop) -> Callable[[str | None], bool]:
        gate, timeout = self.gate, self.gate.confirm_timeout

        def cb(shot: str | None) -> bool:
            fut = asyncio.run_coroutine_threadsafe(
                gate.wait_confirm(task_id, platform, screenshot=shot, timeout=timeout), loop)
            return bool(fut.result(timeout=timeout + 5.0))

        return cb

    def _captcha_callback(self, platform: str, loop: asyncio.AbstractEventLoop) -> Callable[[str | None], bool]:
        """验证码桥:worker 线程 → 主循环 HumanGate.wait_captcha → 本机解决后放行。"""
        gate, timeout = self.gate, self.gate.confirm_timeout

        def cb(_shot: str | None) -> bool:
            fut = asyncio.run_coroutine_threadsafe(
                gate.wait_captcha(platform, timeout=timeout), loop)
            return bool(fut.result(timeout=timeout + 5.0))

        return cb

    def _run_in_thread(self, task: dict[str, Any], loop: asyncio.AbstractEventLoop) -> dict[str, Any]:
        import asyncio as _aio

        # auto_confirm 仅在显式开启时才作为参数传给 run 回调:注入式回调的既有
        # 签名是 (task, *, confirm_callback, headless),恒传会 TypeError。
        if self.auto_confirm:
            return _aio.run(self._run(task, confirm_callback=None, headless=self.headless,
                                      auto_confirm=True))
        cb = self._confirm_callback(task["id"], task["platform"], loop)
        kwargs: dict[str, Any] = {"confirm_callback": cb, "headless": self.headless}
        if self._default_run_path:
            # 验证码人机协同仅默认执行体接线(桌面端);注入式回调签名不受影响
            kwargs["captcha_callback"] = self._captcha_callback(task["platform"], loop)
        return _aio.run(self._run(task, **kwargs))

    async def _run_one(self, task: dict[str, Any]) -> dict[str, Any]:
        platform = str(task.get("platform", ""))
        # BE-1/BE-2:同平台互斥 + 全局并发上限;拿不到 → 快速上报 executor_busy
        # (RATE_LIMITED,可重试)—— 不在执行端排队,重试节奏由控制面调度。
        if not self._limiter.acquire_nowait(platform):
            return {"task_id": task["id"], "ok": False, "result_url": None,
                    "result_detail": {"error_class": OUTCOME_ERROR_CLASS["executor_busy"],
                                      "outcome": "executor_busy",
                                      "error": f"platform {platform} busy or global limit reached"}}
        try:
            result = await asyncio.to_thread(self._run_in_thread, task, asyncio.get_running_loop())
        except Exception as e:  # 执行器崩溃(Chrome 崩溃等)→ 分类回报,不抛出
            return {"task_id": task["id"], "ok": False, "result_url": None,
                    "result_detail": {"error_class": "EXECUTOR_ERROR", "error": str(e)}}
        finally:
            self._limiter.release(platform)
        outcome = str(result.get("outcome", ""))
        if result.get("ok"):
            return {"task_id": task["id"], "ok": True,
                    "result_url": result.get("post_url"),
                    "result_detail": {"outcome": outcome}}
        # §11.2:执行 trace 全记录随任务回报(逐步截图/结果入审计,可回放定位)
        return {"task_id": task["id"], "ok": False,
                "result_url": result.get("post_url"),
                "result_detail": {"error_class": OUTCOME_ERROR_CLASS.get(outcome, DEFAULT_ERROR_CLASS),
                                  "outcome": outcome,
                                  "trace": result.get("trace", [])[-12:],
                                  "error": str(result.get("error", ""))[:200]}}

    async def poll_once(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for platform in self.platforms:
            claimed = reported = 0
            try:
                tasks = await _maybe_await(self.claim(platform, self.limit))
            except Exception:
                out[platform] = {"claimed": 0, "reported": 0, "error": "control_plane_unreachable"}
                continue
            for task in tasks or []:
                claimed += 1
                payload = await self._run_one(task)
                try:
                    await _maybe_await(self.report(payload))
                    reported += 1
                except Exception:
                    pass  # 回报失败:控制面 lease 超时回收后重领(可靠性由租约保证)
            out[platform] = {"claimed": claimed, "reported": reported}
        return out

    # -- 常驻循环 ------------------------------------------------------

    async def run_forever(self) -> None:
        while self._running:
            try:
                await self.poll_once()
            except Exception:
                pass  # poll_once 自身不应抛;防御性兜底
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


_GATE: HumanGate | None = None


def shared_human_gate() -> HumanGate:
    """进程级共享人工关卡(router 挂 HTTP 面;执行侧与 CaptchaGate 同源)。"""
    global _GATE
    if _GATE is None:
        _GATE = HumanGate()
    return _GATE


def load_recipe(platform: str) -> dict[str, Any] | None:
    """加载平台连接器包(单文件 connector.yml:capability/constraints/domains/publish/…)。"""
    for root in RECIPE_DIRS:
        f = root / platform / "connector.yml"
        if f.is_file():
            try:
                import yaml

                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else None
            except ImportError:
                return _mini_yaml(f.read_text(encoding="utf-8")) or None
    return None


def _mini_yaml(text: str) -> dict:
    import ast

    data: dict = {}
    stack: list[tuple[int, dict]] = [(-1, data)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            if value.startswith(("[", "{")):
                try:
                    value = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    try:  # 形如 [127.0.0.1] 的非字面量:按字符串元素解析
                        inner = value.strip("[]{}")
                        value = [v.strip().strip("'\"") for v in inner.split(",") if v.strip()]
                    except Exception:
                        pass
            parent[key] = value
    return data


async def run_browser_publish(
    platform: str,
    *,
    title: str,
    body: str,
    mode: str = "draft_box",
    media_paths: list[str] | None = None,
    confirm_callback: Callable[[str | None], bool] | None = None,
    auto_confirm: bool = False,
    headless: bool = True,
    recipe: dict[str, Any] | None = None,
    captcha_callback: Callable[[str | None], bool] | None = None,
) -> dict[str, Any]:
    """单次浏览器发布(低层入口;仅本机执行端调用,见模块头注释)。

    人工确认默认必须显式:confirm_callback 缺省且未 auto_confirm=True 时拒绝执行
    (PRD §3.2 原则 3:发布永不由 Agent 无监督执行)。
    captcha_callback 缺省时命中验证码即 captcha_timeout(→ CAPTCHA_REQUIRED 人工)。
    """
    if confirm_callback is None:
        if not auto_confirm:
            raise ValueError("必须提供 confirm_callback,或显式 auto_confirm=True(人工确认默认开)")
        def confirm_callback(_shot: str | None) -> bool:  # noqa: E731 显式豁免(调用方自担责任)
            return True

    recipe = recipe or load_recipe(platform)
    if not recipe:
        return {"ok": False, "outcome": "recipe_missing", "error": f"未找到 {platform} 的 selectors 包"}

    async with RealBrowserSession(platform, headless=headless) as session:
        executor = BrowserPublishExecutor(recipe, confirm_callback=confirm_callback,
                                          captcha_callback=captcha_callback)
        result = await executor.execute(
            session.page, title=title, body=body, media_paths=media_paths, mode=mode,
        )
    result["platform"] = platform
    result["trace"] = [t.__dict__ for t in result.get("trace", [])]
    return result


__all__ = [
    "run_browser_publish", "load_recipe", "RECIPE_DIRS", "RealBrowserSession",
    "HumanGate", "BrowserTrackClient", "shared_human_gate",
    "default_claim", "default_report", "_auth_headers", "OUTCOME_ERROR_CLASS",
    "acquire_track_lock", "release_track_lock", "read_track_lock", "TrackLockHeldError",
]
