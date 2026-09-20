# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""容器运行时检测 API"""

import logging
import os
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system/container-runtime", tags=["System"])


class RuntimeInfo(BaseModel):
    """运行时信息"""

    available: bool
    version: Optional[str] = None
    error: Optional[str] = None
    socket: Optional[str] = None


class DetectionResult(BaseModel):
    """检测结果"""

    docker: RuntimeInfo
    podman: RuntimeInfo


@router.get("/detect")
async def detect_container_runtime() -> DetectionResult:
    """检测系统中可用的容器运行时

    Returns:
        DetectionResult: 包含 Docker 和 Podman 的检测结果
    """
    result = DetectionResult(docker=RuntimeInfo(available=False), podman=RuntimeInfo(available=False))

    # 检测 Docker
    result.docker = await _detect_docker()

    # 检测 Podman
    result.podman = await _detect_podman()

    logger.info(f"容器运行时检测完成: Docker={'可用' if result.docker.available else '不可用'}, Podman={'可用' if result.podman.available else '不可用'}")

    return result


async def _detect_docker() -> RuntimeInfo:
    """检测 Docker 是否可用"""
    process = None
    client = None
    try:
        # 检查 docker 命令，添加5秒超时
        process = await asyncio.create_subprocess_exec("docker", "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return RuntimeInfo(available=False, error="Docker 命令超时")

        if process.returncode != 0:
            return RuntimeInfo(available=False, error=f"Docker 命令不可用: {stderr.decode('utf-8', errors='replace')}")

        version = stdout.decode("utf-8", errors="replace").strip()

        # 尝试连接 Docker daemon
        import docker

        try:
            client = docker.from_env()
            client.ping()
            api_version = client.version().get("Version", "unknown")
            return RuntimeInfo(available=True, version=f"{version} (API: {api_version})")
        except Exception as e:
            return RuntimeInfo(available=False, error=f"Docker daemon 不可用: {str(e)}")

    except FileNotFoundError:
        return RuntimeInfo(available=False, error="Docker 未安装")
    except Exception as e:
        logger.exception("检测 Docker 时出错")
        return RuntimeInfo(available=False, error=f"检测失败: {str(e)}")
    finally:
        # 确保 Docker client 被正确关闭
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


async def _detect_podman() -> RuntimeInfo:
    """检测 Podman 是否可用"""
    process = None
    client = None
    try:
        # 检查 podman 命令，添加5秒超时
        process = await asyncio.create_subprocess_exec("podman", "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return RuntimeInfo(available=False, error="Podman 命令超时")

        if process.returncode != 0:
            return RuntimeInfo(available=False, error=f"Podman 命令不可用: {stderr.decode('utf-8', errors='replace')}")

        version = stdout.decode("utf-8", errors="replace").strip()

        # 检查 Podman API socket
        socket_paths = ["/run/podman/podman.sock", f"/run/user/{os.getuid()}/podman/podman.sock", os.path.expanduser("~/.local/share/containers/podman.sock")]

        available_socket = None
        for sock_path in socket_paths:
            if os.path.exists(sock_path):
                available_socket = sock_path
                break

        if not available_socket:
            return RuntimeInfo(available=False, error=f"Podman 已安装 ({version}) 但 API socket 未找到。请启动 Podman 服务:\n  systemctl --user start podman.socket\n  或: sudo systemctl start podman.socket")

        # 尝试连接 Podman API - 使用 base_url 而不是设置环境变量
        try:
            import docker

            # 使用 base_url 直接连接 socket，避免污染全局环境变量
            client = docker.DockerClient(base_url=f"unix://{available_socket}")
            client.ping()
            return RuntimeInfo(available=True, version=version, socket=available_socket)
        except Exception as e:
            return RuntimeInfo(available=False, error=f"Podman API 不可用: {str(e)}")

    except FileNotFoundError:
        return RuntimeInfo(available=False, error="Podman 未安装")
    except Exception as e:
        logger.exception("检测 Podman 时出错")
        return RuntimeInfo(available=False, error=f"检测失败: {str(e)}")
    finally:
        # 确保 Docker client 被正确关闭
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
