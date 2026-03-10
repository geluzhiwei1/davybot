# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""容器沙箱管理器 - 提供容器化的命令执行环境

该模块实现了基于容器（Docker/Podman）的命令隔离执行，包括：
- 容器创建和销毁
- 资源限制（CPU、内存、磁盘、网络）
- 安全配置（只读文件系统、capabilities降级）
- 审计日志
- 支持 Docker 和 Podman 运行时

依赖: docker-py (pip install docker)

运行时支持:
- Docker: 默认，通过 Docker daemon
- Podman: 兼容 Docker API，设置 DOCKER_HOST=unix:///run/podman/podman.sock
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Literal

import docker

from dawei.core.exceptions import (
    ConfigurationError,
    DockerConnectionError,
    ResourceLimitError,
    SandboxError,
    SandboxTimeoutError,
)
from dawei.logg.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SandboxConfig:
    """沙箱配置"""

    image: str = "alpine:latest"  # 基础镜像
    memory_limit: str = "512m"  # 内存限制
    cpu_quota: int = 100000  # CPU配额（100000 = 1个CPU）
    cpu_period: int = 100000  # CPU周期
    pids_limit: int = 100  # 进程数限制
    timeout: int = 30  # Execution timeout (seconds)
    network_disabled: bool = True  # Disable network (可通过sandbox_disable_network配置)
    read_only_root: bool = True  # Read-only root filesystem
    tmpfs_size: str = "100m"  # Temporary filesystem size

    # Workspace mount configuration
    workspace_mount_mode: str = "ro"  # ro = read-only, rw = read-write

    # === 容器运行时配置 ===
    container_runtime: Literal["docker", "podman", "auto"] = "auto"  # 容器运行时选择

    # === 细粒度安全控制 ===
    drop_all_capabilities: bool = True  # 是否移除所有capabilities
    no_new_privileges: bool = True  # 是否禁止获得新权限
    sandbox_disable_network: bool = True  # 是否禁用网络（与UserSecuritySettings保持一致）


class SandboxManager:
    """容器沙箱管理器 - 支持 Docker 和 Podman"""

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self.runtime = self._detect_runtime()
        self.client = self._init_client()

    def _detect_runtime(self) -> str:
        """检测可用的容器运行时"""
        if self.config.container_runtime != "auto":
            # 用户明确指定了运行时
            runtime = self.config.container_runtime
            if self._check_runtime_available(runtime):
                logger.info(f"[SANDBOX] 使用指定的运行时: {runtime}")
                return runtime
            else:
                logger.warning(f"[SANDBOX] 指定的运行时 {runtime} 不可用，尝试自动检测")
                # 继续自动检测

        # 自动检测：优先 Podman（更安全），其次 Docker
        for runtime in ["podman", "docker"]:
            if self._check_runtime_available(runtime):
                logger.info(f"[SANDBOX] 自动检测到运行时: {runtime}")
                return runtime

        # 都不可用，返回 docker（后续会在 _init_client 中报错）
        logger.warning("[SANDBOX] 未检测到可用的容器运行时")
        return "docker"

    def _check_runtime_available(self, runtime: str) -> bool:
        """检查运行时是否可用"""
        try:
            if runtime == "podman":
                # 检查 Podman
                result = subprocess.run(["podman", "--version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    # 检查 Podman API socket
                    socket_paths = ["/run/podman/podman.sock", "/run/user/{}/podman/podman.sock".format(os.getuid()), "~/.local/share/containers/podman.sock"]
                    for sock_path in socket_paths:
                        sock_path = os.path.expanduser(sock_path)
                        if os.path.exists(sock_path):
                            logger.debug(f"[SANDBOX] 找到 Podman socket: {sock_path}")
                            return True
                    logger.debug("[SANDBOX] Podman 已安装但未找到 socket")
                    return False
            elif runtime == "docker":
                # 检查 Docker
                result = subprocess.run(["docker", "--version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    # 检查 Docker daemon
                    client = docker.from_env()
                    client.ping()
                    logger.debug("[SANDBOX] Docker daemon 可用")
                    return True
        except (subprocess.TimeoutExpired, FileNotFoundError, docker.errors.DockerException):
            pass
        except Exception as e:
            logger.debug(f"[SANDBOX] 检查 {runtime} 时出错: {e}")

        return False

    def _init_client(self):
        """初始化容器客户端"""
        runtime = self.runtime

        if runtime == "podman":
            # 使用 Podman
            # Podman API socket 位置
            socket_paths = ["/run/podman/podman.sock", "/run/user/{}/podman/podman.sock".format(os.getuid()), os.path.expanduser("~/.local/share/containers/podman.sock")]

            podman_socket = None
            for sock_path in socket_paths:
                if os.path.exists(sock_path):
                    podman_socket = f"unix://{sock_path}"
                    break

            if not podman_socket:
                raise DockerConnectionError("Podman socket 未找到。请确保 Podman 服务正在运行:\n  systemctl start --user podman.socket\n  或: sudo systemctl start podman.socket")

            # 设置环境变量
            os.environ["DOCKER_HOST"] = podman_socket
            logger.info(f"[SANDBOX] 使用 Podman: {podman_socket}")

        try:
            client = docker.from_env()
            # 测试连接
            client.ping()

            # 获取版本信息以确认运行时
            try:
                version = client.version()
                if runtime == "podman" or "podman" in version.get("Components", [{}])[0].get("Name", "").lower():
                    logger.info(f"[SANDBOX] Podman 连接成功 (版本: {version.get('Version', 'unknown')})")
                else:
                    logger.info(f"[SANDBOX] Docker 连接成功 (版本: {version.get('Version', 'unknown')})")
            except Exception:
                logger.info(f"[SANDBOX] {runtime.capitalize()} 连接成功")

            return client

        except docker.errors.DockerException as e:
            logger.exception(f"[SANDBOX] {runtime.capitalize()} 连接失败: ")
            raise DockerConnectionError(f"{runtime.capitalize()} daemon 不可用: {e}\n请确保 {runtime} 已安装并正在运行。")
        except (OSError, ConnectionError) as e:
            logger.exception(f"[SANDBOX] {runtime.capitalize()} 连接错误: ")
            raise DockerConnectionError(f"无法连接到 {runtime}: {e}")

    def execute_command(
        self,
        command: str,
        workspace_path: Path,
        user_id: str = "unknown",
    ) -> Dict[str, Any]:
        """在沙箱中执行命令

        Args:
            command: 要执行的命令
            workspace_path: 工作区路径
            user_id: 用户ID（用于审计）

        Returns:
            执行结果字典

        """
        start_time = time.time()

        temp_mount = None

        try:
            # 1. Prepare mount point
            # Create temporary mount point to support potential write operations
            temp_mount = tempfile.mkdtemp(prefix="sandbox_mount_")

            # 2. Validate path security - Fix exception 1: Path doesn't exist or is inaccessible
            if not workspace_path.exists():
                raise ConfigurationError(f"工作区路径不存在: {workspace_path}")

            if not workspace_path.is_dir():
                raise ConfigurationError(f"工作区路径不是目录: {workspace_path}")

            workspace_resolved = workspace_path.resolve()
            logger.info(f"[SANDBOX] 工作区路径: {workspace_resolved}")

            # 检查路径长度和安全性
            if len(str(workspace_resolved)) > 4096:
                raise ConfigurationError(
                    f"工作区路径过长: {len(str(workspace_resolved))} characters",
                )

            # 3. 准备卷挂载 - 修复异常2: 路径过长或包含特殊字符
            # 验证挂载模式
            if self.config.workspace_mount_mode not in ("ro", "rw"):
                raise ConfigurationError(f"无效的挂载模式: {self.config.workspace_mount_mode}")

            volumes = {
                str(workspace_resolved): {
                    "bind": "/workspace",
                    "mode": self.config.workspace_mount_mode,
                },
                temp_mount: {"bind": "/tmp", "mode": "rw"},
            }

            # 4. 准备环境变量 (Docker容器内通常是Linux环境)
            environment = {
                "WORKSPACE": "/workspace",
                "HOME": "/tmp",
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",  # 容器内Linux路径
                "TERM": "xterm",
            }

            # 5. 创建容器并执行 - 修复异常3: 镜像不存在或timeout命令缺失
            logger.info(f"[SANDBOX] 执行命令: {command[:100]}")

            # 检查timeout命令是否可用
            timeout_cmd = "timeout"
            if self.config.timeout > 0:
                timeout_cmd = f"timeout {self.config.timeout}s"

            # 准备安全选项
            cap_drop_option = ["ALL"] if self.config.drop_all_capabilities else []
            security_opt = ["no-new-privileges"] if self.config.no_new_privileges else []

            # 网络配置：sandbox_disable_network 优先级高于 network_disabled
            network_disabled = self.config.sandbox_disable_network if hasattr(self.config, "sandbox_disable_network") else self.config.network_disabled

            # 使用run方法（自动删除容器）
            try:
                output = self.client.containers.run(
                    image=self.config.image,
                    command=["sh", "-c", f"{timeout_cmd} {command}"],
                    volumes=volumes,
                    environment=environment,
                    mem_limit=self.config.memory_limit,
                    cpu_quota=self.config.cpu_quota,
                    cpu_period=self.config.cpu_period,
                    pids_limit=self.config.pids_limit,
                    network_disabled=network_disabled,
                    read_only=self.config.read_only_root,
                    # 安全选项（根据配置动态设置）
                    cap_drop=cap_drop_option,  # 根据配置决定是否移除所有capabilities
                    security_opt=security_opt,  # 根据配置决定是否禁止获得新权限
                    # 自动删除容器
                    remove=True,
                    # 捕获输出
                    stdout=True,
                    stderr=True,
                    detach=False,
                    # 添加超时保护
                    # runtime_timeout=self.config.timeout + 10 if self.config.timeout > 0 else 60
                )
            except docker.errors.ImageNotFound:
                # 尝试拉取镜像
                logger.warning(f"[SANDBOX] 镜像不存在，尝试拉取: {self.config.image}")
                try:
                    self.client.images.pull(self.config.image)
                    # 重新尝试执行
                    output = self.client.containers.run(
                        image=self.config.image,
                        command=["sh", "-c", f"{timeout_cmd} {command}"],
                        volumes=volumes,
                        environment=environment,
                        mem_limit=self.config.memory_limit,
                        cpu_quota=self.config.cpu_quota,
                        cpu_period=self.config.cpu_period,
                        pids_limit=self.config.pids_limit,
                        network_disabled=network_disabled,
                        read_only=self.config.read_only_root,
                        cap_drop=cap_drop_option,  # 根据配置决定
                        security_opt=security_opt,  # 根据配置决定
                        remove=True,
                        stdout=True,
                        stderr=True,
                        detach=False,
                    )
                except docker.errors.ImageNotFound:
                    # 镜像拉取后仍然找不到
                    raise DockerConnectionError(f"镜像不存在且拉取失败: {self.config.image}")
                except docker.errors.APIError as e:
                    # Docker API错误（网络、权限等）
                    raise DockerConnectionError(f"Docker API错误（拉取镜像时）: {e}")
            except docker.errors.ContainerError as e:
                if "exit code: 137" in str(e) or "OOM" in str(e):
                    raise ResourceLimitError(f"容器因内存不足被终止: {e}")
                if "exit code: 124" in str(e):
                    raise SandboxTimeoutError(f"容器执行超时: {e}")
                raise SandboxError(f"容器执行失败: {e}")
            except docker.errors.APIError as e:
                raise SandboxError(f"Docker API错误: {e}")

            # 6. 解析输出
            # output是容器的stdout和stderr的组合
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            elif output is None:
                output = ""

            # 由于使用了detach=False和remove=True，容器已经被删除
            # 我们需要通过捕获的输出来判断结果
            exit_code = 0  # 如果没有抛出异常，假设成功
            stdout = output
            stderr = ""

            execution_time = int((time.time() - start_time) * 1000)

            # 7. 记录审计日志 - 修复异常4: 审计日志写入失败
            # LEGITIMATE TOLERANCE: 审计日志失败不应影响命令执行结果
            try:
                self._audit_log(
                    user_id=user_id,
                    command=command,
                    exit_code=exit_code,
                    execution_time=execution_time,
                )
            except OSError as audit_error:
                # 文件系统错误（权限、磁盘空间等）
                logger.warning(f"[SANDBOX] 审计日志记录失败（文件系统错误）: {audit_error}")
            except (TypeError, ValueError) as audit_error:
                # 日志数据格式错误
                logger.warning(f"[SANDBOX] 审计日志记录失败（数据格式错误）: {audit_error}")

            logger.info(f"[SANDBOX] 命令执行成功: exit_code={exit_code}, time={execution_time}ms")

            return {
                "success": True,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "execution_time": execution_time,
                "workspace": str(workspace_resolved),
            }

        except docker.errors.ContainerError as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception("[SANDBOX] 容器执行错误: ")

            # 尝试从错误中提取stderr
            stderr = str(e)
            stdout = ""

            return {
                "success": False,
                "error": str(e),
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": e.exit_status if hasattr(e, "exit_status") else -1,
                "execution_time": execution_time,
            }

        except (ConfigurationError, SandboxError, DockerConnectionError):
            # 自定义异常直接抛出（Fast Fail）
            raise
        except Exception as e:
            # 未知错误 - 记录详细信息并返回错误结果
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"[SANDBOX] 沙箱执行失败（未知错误）: {e}", exc_info=True)

            return {
                "success": False,
                "error": f"Sandbox execution failed: {e!s}",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }

        finally:
            # Clean up temporary mount point - Fix exception 5: Temporary directory cleanup failed
            # LEGITIMATE TOLERANCE: Cleanup failure should not affect command execution result
            if temp_mount and Path(temp_mount).exists():
                try:
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            shutil.rmtree(temp_mount)
                            logger.debug(f"[SANDBOX] Cleaned up temporary mount point: {temp_mount}")
                            break
                        except PermissionError as pe:
                            if attempt == max_retries - 1:
                                # 最后一次尝试仍然失败
                                logger.exception(f"[SANDBOX] 无法清理临时挂载点（权限不足）: {pe}")
                                # 尝试标记为待删除（见下方）
                                raise
                            logger.warning(f"[SANDBOX] 清理重试 {attempt + 1}/{max_retries}: {pe}")
                            time.sleep(1)
                        except OSError as ose:
                            # 文件系统错误（文件被占用、只读文件系统等）
                            logger.warning(f"[SANDBOX] 清理临时挂载点失败（文件系统错误）: {ose}")
                            break
                except Exception as e:
                    logger.warning(f"[SANDBOX] 无法清理临时挂载点 {temp_mount}: {e}")
                    # 标记为删除，下次启动时清理
                    try:
                        flag_path = Path(f"{temp_mount}.delete_flag")
                        with flag_path.open("w", encoding="utf-8") as f:
                            f.write(f"待删除目录: {temp_mount}")
                        logger.info(f"[SANDBOX] 标记临时挂载点待删除: {temp_mount}")
                    except OSError as flag_error:
                        # 标记文件创建失败也容忍
                        logger.exception(f"[SANDBOX] 无法创建删除标记: {flag_error}")

    def _audit_log(self, user_id: str, command: str, exit_code: int, execution_time: int):
        """记录审计日志"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "command": command[:1000],  # 限制长度
            "exit_code": exit_code,
            "execution_time_ms": execution_time,
            "sandbox_config": {
                "runtime": self.runtime,
                "image": self.config.image,
                "memory_limit": self.config.memory_limit,
                "timeout": self.config.timeout,
                "drop_all_capabilities": self.config.drop_all_capabilities,
                "no_new_privileges": self.config.no_new_privileges,
                "sandbox_disable_network": self.config.sandbox_disable_network if hasattr(self.config, "sandbox_disable_network") else self.config.network_disabled,
            },
        }

        # 写入审计日志文件 - 修复异常: 日志目录权限问题
        try:
            # 使用更安全的方式确定日志路径

            audit_log_path = Path("logs/sandbox_audit.log")

            # 确保日志目录存在且有正确的权限
            try:
                audit_log_path.parent.mkdir(exist_ok=True, mode=0o755)
                logger.debug(f"[SANDBOX] Log directory created/confirmed: {audit_log_path.parent}")
            except (PermissionError, OSError) as dir_error:
                # If standard log directory cannot be created, use temporary directory
                temp_log_dir = Path(tempfile.gettempdir()) / "dawei_logs" / "sandbox"
                try:
                    temp_log_dir.mkdir(exist_ok=True, mode=0o755)
                except (PermissionError, OSError):
                    # If temporary directory also cannot be created, use system temp directory
                    temp_log_dir = Path(tempfile.gettempdir())
                    logger.warning(f"[SANDBOX] Using system temp directory: {temp_log_dir}")
                audit_log_path = temp_log_dir / "sandbox_audit.log"
                logger.warning(
                    f"[SANDBOX] Using fallback log directory: {audit_log_path} (original directory error: {dir_error})",
                )

            # Write to log file, using append mode to ensure no data loss
            with Path(audit_log_path, "a").open(encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")

            logger.debug(f"[SANDBOX] Audit log written: {audit_log_path}")

        except (PermissionError, OSError) as pe:
            # File system error (permissions, disk space, etc.)
            logger.exception(f"[SANDBOX] Audit log file system error: {pe}")
            # Try writing to system temp directory as final attempt (cross-platform compatible)
            try:
                temp_dir = tempfile.gettempdir()
                temp_audit_path = Path(temp_dir) / "sandbox_audit.log"
                with Path(temp_audit_path, "a").open(encoding="utf-8") as f:
                    f.write(json.dumps(log_entry) + "\n")
                logger.info(f"[SANDBOX] 审计日志已写入系统临时文件: {temp_audit_path}")
            except (PermissionError, OSError) as temp_error:
                # 所有尝试都失败 - 只能记录到日志
                logger.exception(f"[SANDBOX] 所有审计日志写入尝试均失败: {temp_error}")
        except (TypeError, ValueError) as json_error:
            # JSON序列化错误（数据格式问题）
            logger.exception(f"[SANDBOX] 审计日志JSON序列化失败: {json_error}")

    async def execute_command_async(
        self,
        command: str,
        workspace_path: Path,
        user_id: str = "unknown",
    ) -> Dict[str, Any]:
        """异步执行命令"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.execute_command(command, workspace_path, user_id),
        )

    def health_check(self) -> bool:
        """健康检查"""
        try:
            self.client.ping()
            return True
        except docker.errors.DockerException as e:
            # Docker daemon 未运行或无法连接
            logger.warning(f"[SANDBOX] Docker daemon不可用: {e}")
            return False
        except (ConnectionError, OSError) as e:
            # 网络或操作系统级别错误
            logger.warning(f"[SANDBOX] Docker连接错误: {e}")
            return False
