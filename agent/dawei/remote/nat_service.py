"""
NAT Service
NAT隧道服务 - 管理NAT隧道连接，自动获取token并创建隧道
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx

from dawei import get_dawei_home
from dawei.config.settings import get_settings


logger = logging.getLogger(__name__)


class NATTunnelInfo:
    """NAT隧道信息"""

    def __init__(
        self,
        name: str,
        service_type: str,
        local_port: int,
        public_url: str,
        tunnel_id: str
    ):
        self.name = name
        self.service_type = service_type
        self.local_port = local_port
        self.public_url = public_url
        self.tunnel_id = tunnel_id
        self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "service_type": self.service_type,
            "local_port": self.local_port,
            "public_url": self.public_url,
            "tunnel_id": self.tunnel_id,
            "created_at": self.created_at.isoformat()
        }

    def __repr__(self) -> str:
        return f"NATTunnelInfo(name='{self.name}', type='{self.service_type}', url='{self.public_url}')"


class NATService:
    """
    NAT隧道服务类

    功能：
    1. 从 Support System 获取 NAT 客户端 token
    2. 使用 token 启动 NAT 客户端并创建隧道
    3. 管理隧道生命周期
    4. 支持启动、停止和状态查询
    """

    def __init__(
        self,
        support_system_url: Optional[str] = None,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        client_name: Optional[str] = None
    ):
        """
        初始化NAT服务

        Args:
            support_system_url: Support System的URL
            oauth_client_id: OAuth客户端ID
            oauth_client_secret: OAuth客户端密钥
            client_name: NAT客户端名称
        """
        # 从配置加载
        settings = get_settings()
        support_config = settings.support_system

        self.support_system_url = support_system_url or support_config.url
        self.oauth_client_id = oauth_client_id or support_config.oauth_client_id
        self.oauth_client_secret = oauth_client_secret or support_config.oauth_client_secret

        # NAT客户端名称
        self.client_name = client_name or self._get_or_create_client_name()

        # NAT客户端状态
        self._access_token: Optional[str] = None
        self._nat_token: Optional[str] = None
        self._client_id: Optional[str] = None
        self._tunnels: List[NATTunnelInfo] = []

        # NAT客户端实例（nat-client-py）
        self._nat_client = None
        self._running = False

        # HTTP客户端
        self._http_client: Optional[httpx.AsyncClient] = None

        logger.info(f"NATService initialized: client_name={self.client_name}, "
                   f"support_system={self.support_system_url}")

    def _get_or_create_client_name(self) -> str:
        """
        获取或创建NAT客户端名称

        Returns:
            str: 客户端名称
        """
        client_name_file = get_dawei_home() / "nat_client_name.txt"

        if client_name_file.exists():
            try:
                with open(client_name_file, 'r', encoding='utf-8') as f:
                    client_name = f.read().strip()
                if client_name:
                    return client_name
            except Exception as e:
                logger.warning(f"Failed to read client_name file: {e}")

        # 生成新的client_name
        import uuid
        import socket
        hostname = socket.gethostname()
        client_name = f"davybot-{hostname}-{uuid.uuid4().hex[:8]}"

        # 保存到文件
        try:
            client_name_file.parent.mkdir(parents=True, exist_ok=True)
            with open(client_name_file, 'w', encoding='utf-8') as f:
                f.write(client_name)
            logger.info(f"Generated new client_name: {client_name}")
        except Exception as e:
            logger.error(f"Failed to save client_name file: {e}")

        return client_name

    async def _get_oauth_token(self) -> str:
        """
        从Support System获取OAuth token

        Returns:
            str: OAuth access token

        Raises:
            RuntimeError: 获取token失败
        """
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        # 准备OAuth请求
        oauth_data = {
            "grant_type": "client_credentials",
            "client_id": self.oauth_client_id,
            "client_secret": self.oauth_client_secret,
            "scope": "nat_token"
        }

        try:
            url = f"{self.support_system_url}/api/auth/oauth/token"
            response = await self._http_client.post(url, data=oauth_data)

            if response.status_code != 200:
                raise RuntimeError(
                    f"Failed to get OAuth token: {response.status_code}, "
                    f"Response: {response.text}"
                )

            token_data = response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                raise RuntimeError("No access_token in OAuth response")

            logger.debug("OAuth token obtained successfully")
            return access_token

        except httpx.RequestError as e:
            raise RuntimeError(f"Failed to connect to Support System: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error getting OAuth token: {e}")

    async def _create_nat_token(self) -> Dict[str, Any]:
        """
        创建NAT客户端token

        Returns:
            Dict: Token信息

        Raises:
            RuntimeError: 创建token失败
        """
        if not self._access_token:
            raise RuntimeError("Access token not available")

        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        # 准备创建token请求
        token_request = {
            "client_name": self.client_name,
            "allowed_tunnels": ["web", "ssh", "tcp"],
            "expires_in_hours": 720  # 30天
        }

        try:
            url = f"{self.support_system_url}/support/api/nat/tokens/create"
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json"
            }

            response = await self._http_client.post(url, json=token_request, headers=headers)

            if response.status_code != 201:
                raise RuntimeError(
                    f"Failed to create NAT token: {response.status_code}, "
                    f"Response: {response.text}"
                )

            token_data = response.json()
            logger.info(f"NAT token created successfully: client_id={token_data.get('client_id')}")

            return token_data

        except httpx.RequestError as e:
            raise RuntimeError(f"Failed to connect to Support System: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error creating NAT token: {e}")

    async def _create_nat_client(self, server_addr: str, token: str) -> Any:
        """
        创建NAT客户端实例

        Args:
            server_addr: NAT服务器地址
            token: NAT客户端token

        Returns:
            NAT客户端实例

        Raises:
            RuntimeError: 创建客户端失败
        """
        try:
            # 导入nat-client-py
            from nat_client_py import Client

            # 创建客户端
            client = Client(
                server_addr=server_addr,
                token=token,
                client_id=self.client_name
            )

            logger.info(f"NAT client created: server={server_addr}, client_id={self.client_name}")
            return client

        except ImportError as e:
            raise RuntimeError(
                f"Failed to import nat_client_py: {e}. "
                "Please install nat-client-py: pip install nat-client-py"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create NAT client: {e}")

    async def start(
        self,
        nat_server_addr: str = "localhost:8888",
        services: Optional[List[Dict[str, Any]]] = None
    ) -> List[NATTunnelInfo]:
        """
        启动NAT服务

        Args:
            nat_server_addr: NAT服务器地址
            services: 要暴露的服务列表
                [{"name": "web", "type": "http", "local_port": 8080}, ...]

        Returns:
            List[NATTunnelInfo]: 创建的隧道列表

        Raises:
            RuntimeError: 启动失败
        """
        if self._running:
            logger.warning("NATService is already running")
            return self._tunnels

        try:
            # 1. 创建HTTP客户端
            verify_ssl = os.getenv("SUPPORT_SYSTEM_VERIFY_SSL", "true").lower() == "true"
            self._http_client = httpx.AsyncClient(timeout=30.0, verify=verify_ssl)

            # 2. 获取OAuth token
            logger.info("Getting OAuth token from Support System...")
            self._access_token = await self._get_oauth_token()

            # 3. 创建NAT token
            logger.info("Creating NAT client token...")
            token_data = await self._create_nat_token()
            self._nat_token = token_data["token"]
            self._client_id = token_data["client_id"]

            # 4. 创建NAT客户端
            logger.info("Creating NAT client...")
            self._nat_client = await self._create_nat_client(nat_server_addr, self._nat_token)

            # 5. 添加服务
            if services:
                logger.info(f"Adding {len(services)} services...")
                for service in services:
                    name = service["name"]
                    service_type = service["type"]
                    local_port = service["local_port"]
                    domain = service.get("domain")

                    self._nat_client.add_service(name, service_type, local_port, domain)
                    logger.info(f"Service added: {name} ({service_type}) -> {local_port}")

            # 6. 连接到NAT服务器
            logger.info("Connecting to NAT server...")
            tunnels = await self._connect_nat_client()

            # 7. 更新状态
            self._running = True
            logger.info(f"NATService started successfully with {len(tunnels)} tunnel(s)")

            return tunnels

        except Exception as e:
            logger.error(f"Failed to start NATService: {e}")
            await self.stop()
            raise

    async def _connect_nat_client(self) -> List[NATTunnelInfo]:
        """
        连接NAT客户端并获取隧道信息

        Returns:
            List[NATTunnelInfo]: 隧道信息列表
        """
        if not self._nat_client:
            raise RuntimeError("NAT client not initialized")

        try:
            # 异步连接（如果支持）
            if hasattr(self._nat_client, 'connect_async'):
                native_tunnels = await self._nat_client.connect_async()
            else:
                # 同步连接（在线程池中运行）
                import concurrent.futures
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    native_tunnels = await loop.run_in_executor(
                        pool,
                        self._nat_client.connect_sync
                    )

            # 转换为NATTunnelInfo
            self._tunnels = []
            for tunnel in native_tunnels:
                tunnel_info = NATTunnelInfo(
                    name=tunnel.name,
                    service_type=tunnel.service_type,
                    local_port=tunnel.local_port,
                    public_url=tunnel.public_url,
                    tunnel_id=tunnel.tunnel_id
                )
                self._tunnels.append(tunnel_info)
                logger.info(f"Tunnel created: {tunnel_info}")

            return self._tunnels

        except Exception as e:
            raise RuntimeError(f"Failed to connect NAT client: {e}")

    async def stop(self) -> None:
        """停止NAT服务"""
        if not self._running:
            return

        logger.info("Stopping NATService...")

        # 断开NAT客户端
        if self._nat_client:
            try:
                if hasattr(self._nat_client, 'disconnect'):
                    self._nat_client.disconnect()
                logger.info("NAT client disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting NAT client: {e}")

        # 关闭HTTP客户端
        if self._http_client:
            try:
                await self._http_client.aclose()
            except Exception as e:
                logger.warning(f"Error closing HTTP client: {e}")

        # 清理状态
        self._running = False
        self._nat_client = None
        self._http_client = None
        self._access_token = None
        self._nat_token = None
        self._tunnels = []

        logger.info("NATService stopped")

    async def add_service(
        self,
        name: str,
        service_type: str,
        local_port: int,
        domain: Optional[str] = None
    ) -> None:
        """
        添加服务到NAT客户端

        Args:
            name: 服务名称
            service_type: 服务类型 (http, https, ssh, tcp, udp)
            local_port: 本地端口
            domain: 自定义域名（可选）

        Raises:
            RuntimeError: 添加服务失败
        """
        if not self._nat_client:
            raise RuntimeError("NAT client not initialized")

        try:
            self._nat_client.add_service(name, service_type, local_port, domain)
            logger.info(f"Service added: {name} ({service_type}) -> {local_port}")
        except Exception as e:
            raise RuntimeError(f"Failed to add service: {e}")

    def get_tunnels(self) -> List[NATTunnelInfo]:
        """
        获取当前活动隧道列表

        Returns:
            List[NATTunnelInfo]: 隧道列表
        """
        return self._tunnels.copy()

    @property
    def is_running(self) -> bool:
        """检查服务是否正在运行"""
        return self._running

    @property
    def nat_token(self) -> Optional[str]:
        """获取NAT token"""
        return self._nat_token

    @property
    def client_identifier(self) -> Optional[str]:
        """获取客户端标识符"""
        return self._client_id


# ============================================================================
# 全局单例
# ============================================================================

_nat_service: Optional[NATService] = None


def get_nat_service() -> NATService:
    """
    获取全局NAT服务单例

    Returns:
        NATService: NAT服务实例
    """
    global _nat_service

    if _nat_service is None:
        _nat_service = NATService()

    return _nat_service


async def start_nat_service(
    nat_server_addr: str = "localhost:8888",
    services: Optional[List[Dict[str, Any]]] = None
) -> List[NATTunnelInfo]:
    """
    启动全局NAT服务

    Args:
        nat_server_addr: NAT服务器地址
        services: 要暴露的服务列表

    Returns:
        List[NATTunnelInfo]: 创建的隧道列表
    """
    service = get_nat_service()
    return await service.start(nat_server_addr, services)


async def stop_nat_service() -> None:
    """停止全局NAT服务"""
    global _nat_service

    if _nat_service:
        await _nat_service.stop()
