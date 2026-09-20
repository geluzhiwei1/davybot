"""RealBrowserSession —— 真机 Chrome 会话(已验证路线:subprocess + CDP + playwright)。

设计对齐 PRD §11.4:每平台独立 user_data_dir(登录态持久)、Windows CDP 子进程、
孤儿回收;browser-use 路线保留为可选(其内部启动在本机验证不稳定,playwright
直连更轻)。headless 可配(平台风控敏感时用 headful)。

使用场景(重要):本模块只在本机"执行端"运行 ——
  1. 桌面端 dawei sidecar(nn-bot-app Tauri 内嵌引擎,Windows 为主);
  2. davy-light-app 壳的 Python 兼容路径(若启用)。
SaaS 云端引擎(DAWEI_DEPLOYMENT_MODE=saas)**从不执行本模块** —— 云端只编排,
真实浏览器操作经 nn-social-flow 控制面下发 claim,由上述本机执行端消费执行。
find_chrome() Windows 优先是桌面端主场景的刻意设计;Linux/macOS 桌面可用
DAWEI_CHROME_PATH 环境变量显式指定 Chrome 可执行文件;找不到时快速失败
("Chrome executable not found"),不在云端静默降级。
"""

from __future__ import annotations

import os
import socket
import subprocess
import urllib.request
from pathlib import Path


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def find_chrome() -> str | None:
    # 0) 显式环境变量优先(Linux/macOS 桌面执行端 / 非默认安装位置)
    env_path = os.environ.get("DAWEI_CHROME_PATH", "").strip()
    if env_path:
        return env_path if os.path.isfile(env_path) else None
    # 1) Windows 桌面端默认安装位置(主场景)
    for cand in (
        os.environ.get("PROGRAMFILES", r"C:\Program Files") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe",
    ):
        if os.path.isfile(cand):
            return cand
    # 2) Linux/macOS 桌面执行端常见位置
    for cand in (
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/usr/local/bin/google-chrome",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ):
        if os.path.isfile(cand):
            return cand
    return None


def kill_profile_chrome(user_data_dir: str) -> None:
    """按 profile 目录回收孤儿 Chrome(幂等)。Windows 走 PowerShell,POSIX 走 pgrep/pkill。"""
    if os.name != "nt":
        # Linux/macOS 执行端:按命令行含 user_data_dir 精确匹配,避免误杀用户自己的 Chrome
        try:
            import subprocess as _sp

            _sp.run(
                ["pkill", "-f", f"user-data-dir={user_data_dir}"],
                capture_output=True, timeout=15,
            )
        except Exception:
            pass
        return
    try:
        import tempfile

        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
            f"Where-Object {{$_.CommandLine -like '*{user_data_dir.replace(chr(39), chr(39)*2)}*'}} | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass
    finally:
        _ = tempfile  # noqa


class RealBrowserSession:
    """单平台真机会话:启动/连接/取页/关闭。async 上下文管理器用法。"""

    def __init__(self, platform: str, *, headless: bool = True, profile_root: str | None = None,
                 chrome_path: str | None = None):
        self.platform = platform
        self.headless = headless
        from dawei import get_dawei_home

        root = profile_root or (str(Path(get_dawei_home()) / "browser-profiles"))
        self.user_data_dir = str(Path(root) / platform)
        self.chrome_path = chrome_path or find_chrome()
        self._proc: subprocess.Popen | None = None
        self.port = 0
        self._pw = None
        self._browser = None
        self.page = None

    async def __aenter__(self) -> RealBrowserSession:
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def start(self) -> RealBrowserSession:
        if not self.chrome_path:
            raise RuntimeError("Chrome executable not found")
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)
        kill_profile_chrome(self.user_data_dir)  # 孤儿回收(幂等)
        import asyncio

        for attempt in range(2):
            if attempt:
                # profile 锁竞态重试:刚杀的旧 Chrome 未完全退出时,新实例握锁失败会静默退出
                kill_profile_chrome(self.user_data_dir)
                await asyncio.sleep(2.0)
            self.port = _free_port()
            cmd = [
                self.chrome_path,
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.user_data_dir}",
                "--no-first-run", "--no-default-browser-check",
            ]
            if self.headless:
                cmd.append("--headless=new")
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(20):  # CDP 就绪等待
                await asyncio.sleep(1)
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=2)
                    break
                except Exception:
                    pass
            else:
                continue  # 本次未就绪 → 重试一次
            break
        else:
            raise TimeoutError(f"Chrome CDP not ready (profile={self.platform})")

        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
        ctx = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
        self.page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        return self

    async def close(self) -> None:
        for closer in (
            lambda: self._browser.close() if self._browser else None,
            lambda: self._pw.stop() if self._pw else None,
        ):
            try:
                if closer():
                    pass
            except Exception:
                pass
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        kill_profile_chrome(self.user_data_dir)
        self._browser = self._pw = self.page = None


__all__ = ["RealBrowserSession", "find_chrome", "kill_profile_chrome"]
