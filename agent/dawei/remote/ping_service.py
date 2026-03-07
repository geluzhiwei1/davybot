"""
Remote Ping Service
远程Ping服务 - 定期向Support System发送心跳包，保持智能体在线状态
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from dawei import get_dawei_home


logger = logging.getLogger(__name__)


class PingService:
    """
    Ping服务类

    功能：
    1. 每5分钟向Support System发送ping请求
    2. 携带智能体信息和运行状态
    3. 处理响应和错误
    4. 支持启动、停止和状态查询
    """

    def __init__(
        self,
        support_system_url: Optional[str] = None,
        ping_interval: int = 300,  # 5分钟 = 300秒
        agent_id: Optional[str] = None
    ):
        """
        初始化Ping服务

        Args:
            support_system_url: Support System的URL
            ping_interval: Ping间隔（秒），默认5分钟
            agent_id: 智能体ID（自动生成）
        """
        self.support_system_url = support_system_url or os.getenv(
            "SUPPORT_SYSTEM_URL",
            "http://localhost:8766"
        )
        self.ping_interval = ping_interval
        self.agent_id = agent_id or self._get_or_create_agent_id()

        self._running = False
        self._ping_task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None

        logger.info(f"PingService initialized: agent_id={self.agent_id}, "
                   f"support_system={self.support_system_url}, "
                   f"interval={ping_interval}s")

    def _get_or_create_agent_id(self) -> str:
        """
        获取或创建智能体ID

        从本地文件读取，如果不存在则生成新的

        Returns:
            str: 智能体ID
        """
        agent_id_file = get_dawei_home() / "agent_id.txt"

        if agent_id_file.exists():
            try:
                with open(agent_id_file, 'r', encoding='utf-8') as f:
                    agent_id = f.read().strip()
                if agent_id:
                    return agent_id
            except Exception as e:
                logger.warning(f"Failed to read agent_id file: {e}")

        # 生成新的agent_id
        import uuid
        agent_id = f"davybot-{uuid.uuid4().hex[:16]}"

        # 保存到文件
        try:
            agent_id_file.parent.mkdir(parents=True, exist_ok=True)
            with open(agent_id_file, 'w', encoding='utf-8') as f:
                f.write(agent_id)
            logger.info(f"Generated new agent_id: {agent_id}")
        except Exception as e:
            logger.error(f"Failed to save agent_id file: {e}")

        return agent_id

    async def start(self) -> None:
        """启动Ping服务"""
        if self._running:
            logger.warning("PingService is already running")
            return

        self._running = True

        # 创建 HTTP 客户端（支持自签名证书）
        # 如果设置了 SUPPORT_SYSTEM_VERIFY_SSL=false，则禁用 SSL 验证
        # 用于支持自签名证书的开发/测试环境
        verify_ssl = os.getenv("SUPPORT_SYSTEM_VERIFY_SSL", "true").lower() == "true"

        self._client = httpx.AsyncClient(
            timeout=30.0,
            verify=verify_ssl  # False 表示禁用 SSL 验证（用于自签名证书）
        )

        # 启动ping任务
        self._ping_task = asyncio.create_task(self._ping_loop())

        logger.info("PingService started")

    async def stop(self) -> None:
        """停止Ping服务"""
        if not self._running:
            return

        self._running = False

        # 取消ping任务
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        # 关闭HTTP客户端
        if self._client:
            await self._client.aclose()

        logger.info("PingService stopped")

    async def _ping_loop(self) -> None:
        """Ping循环"""
        logger.info("Ping loop started")

        while self._running:
            try:
                # 立即发送一次ping
                await self._send_ping()

                # 等待下一次ping
                await asyncio.sleep(self.ping_interval)

            except asyncio.CancelledError:
                logger.info("Ping loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in ping loop: {e}")
                # 发生错误时等待较短时间后重试
                await asyncio.sleep(60)  # 1分钟后重试

    async def _send_ping(self) -> None:
        """
        发送ping请求到Support System

        发送的数据包括：
        - agent_id: 智能体ID
        - agent_type: 智能体类型
        - hostname: 主机名
        - timestamp: 时间戳
        - status: 运行状态
        - version: DavyBot版本信息
        - system_info: 详细的系统信息
        - environment_info: 环境信息
        """
        if not self._client:
            logger.warning("HTTP client not initialized")
            return

        # 准备ping数据（包含更详细的系统信息）
        ping_data = {
            "agent_id": self.agent_id,
            "agent_type": "davybot",
            "hostname": self._get_hostname(),
            "timestamp": datetime.utcnow().isoformat(),
            "status": "online",
            "version": self._get_version(),

            # 详细的系统信息
            "system_info": self._get_system_info(),

            # 环境信息
            "environment_info": self._get_environment_info()
        }

        try:
            # 发送ping请求
            url = f"{self.support_system_url}/api/remote/ping"
            response = await self._client.post(url, json=ping_data)

            if response.status_code == 200:
                logger.debug(f"Ping successful: {ping_data['agent_id']} - "
                           f"OS: {ping_data['system_info']['os_name']} "
                           f"({ping_data['system_info']['os_version']})")
            else:
                logger.warning(f"Ping failed with status {response.status_code}: "
                            f"{response.text}")

        except httpx.ConnectError as e:
            logger.warning(f"Failed to connect to Support System: {e}")
        except httpx.TimeoutException:
            logger.warning("Ping request timed out")
        except Exception as e:
            logger.error(f"Unexpected error sending ping: {e}")

    def _get_hostname(self) -> str:
        """获取主机名"""
        import socket
        try:
            return socket.gethostname()
        except:
            return "unknown"

    def _get_version(self) -> str:
        """获取DavyBot版本"""
        try:
            from dawei import __version__
            return __version__
        except:
            return "0.0.0"

    def _get_system_info(self) -> dict:
        """
        获取详细的系统信息

        Returns:
            dict: 包含操作系统、架构、版本等信息的字典
        """
        import platform
        import sys

        system_info = {
            # 操作系统信息
            "os_name": platform.system(),          # Linux, Windows, Darwin
            "os_version": platform.release(),      # 版本号
            "os_version_full": platform.version(),  # 完整版本信息

            # 系统架构
            "machine": platform.machine(),        # x86_64, ARM64, etc.
            "processor": platform.processor(),    # 处理器信息

            # Python信息
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "python_compiler": platform.python_compiler(),

            # 平台详细信息
            "platform": platform.platform(),      # 综合平台信息
        }

        # 添加Linux发行版信息（如果是Linux）
        if system_info["os_name"] == "Linux":
            try:
                # 尝试读取 /etc/os-release
                if os.path.exists("/etc/os-release"):
                    import configparser
                    config = configparser.ConfigParser()
                    # 读取文件前需要添加section header
                    with open("/etc/os-release", "r") as f:
                        content = f"[DEFAULT]\n{f.read()}"
                    config.read_string(content)

                    system_info["linux_dist"] = config.get("DEFAULT", "NAME", "Unknown")
                    system_info["linux_dist_version"] = config.get("DEFAULT", "VERSION_ID", "")
            except Exception as e:
                logger.debug(f"Failed to read Linux distribution info: {e}")

        # 添加Windows版本信息（如果是Windows）
        elif system_info["os_name"] == "Windows":
            try:
                import winreg
                # 读取Windows版本号
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                   r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
                system_info["windows_display_version"] = winreg.QueryValueEx(key, "DisplayVersion")[0]
                system_info["windows_build_number"] = winreg.QueryValueEx(key, "CurrentBuild")[0]
                winreg.CloseKey(key)
            except Exception as e:
                logger.debug(f"Failed to read Windows version info: {e}")

        # 添加macOS版本信息（如果是Darwin）
        elif system_info["os_name"] == "Darwin":
            try:
                # 使用sw_vers命令获取macOS版本
                import subprocess
                result = subprocess.run(["sw_vers", "-productVersion"],
                                        capture_output=True, text=True)
                if result.returncode == 0:
                    system_info["macos_version"] = result.stdout.strip()
            except Exception as e:
                logger.debug(f"Failed to read macOS version info: {e}")

        return system_info

    def _get_environment_info(self) -> dict:
        """
        获取环境信息

        Returns:
            dict: 包含运行环境信息的字典
        """
        environment_info = {
            # Python环境
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "python_executable": sys.executable,

            # 工作目录
            "working_directory": os.getcwd(),

            # 用户信息
            "user": os.getenv("USER") or os.getenv("USERNAME") or os.getenv("LOGNAME"),

            # Shell信息
            "shell": os.getenv("SHELL"),

            # 语言环境
            "language": os.getenv("LANG") or os.getenv("LC_ALL"),

            # 终端信息
            "terminal": os.getenv("TERM") or os.getenv("TERM_PROGRAM"),

            # 虚拟环境信息
            "is_venv": hasattr(sys, "real_prefix") or (
                hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
            ),
        }

        # 添加虚拟环境路径（如果存在）
        if environment_info["is_venv"]:
            environment_info["venv_prefix"] = sys.prefix

        return environment_info

    @property
    def is_running(self) -> bool:
        """检查服务是否正在运行"""
        return self._running

    @property
    def agent_identifier(self) -> str:
        """获取智能体标识符"""
        return self.agent_id


# 全局单例
_ping_service: Optional[PingService] = None


def get_ping_service() -> PingService:
    """
    获取全局Ping服务单例

    Returns:
        PingService: Ping服务实例
    """
    global _ping_service

    if _ping_service is None:
        _ping_service = PingService()

    return _ping_service


async def start_ping_service() -> None:
    """启动全局Ping服务"""
    service = get_ping_service()
    await service.start()


async def stop_ping_service() -> None:
    """停止全局Ping服务"""
    global _ping_service

    if _ping_service:
        await _ping_service.stop()
