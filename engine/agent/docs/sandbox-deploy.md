# 沙箱系统部署指南 (v2)

> 对应文档: `project/docs/沙箱系统升级-v2.md` Phase 4 & Phase 5

## 目录

1. [部署模式选择](#1-部署模式选择)
2. [本地开发模式 (subprocess)](#2-本地开发模式-subprocess)
3. [Docker 隔离模式](#3-docker-隔离模式)
4. [CubeSandbox 生产部署 (e2b)](#4-cubesandbox-生产部署-e2b)
5. [配置项参考](#5-配置项参考)
6. [N5: 跨用户 .dawei/ 隔离边界](#6-n5-跨用户-dawei-隔离边界)
7. [验证与排障](#7-验证与排障)

---

## 1. 部署模式选择

| 模式 | 隔离级别 | 安全性 | 依赖 | 适用场景 |
|------|---------|--------|------|---------|
| `subprocess` | PROCESS | ★★☆ | 无 | 本地开发、单机桌面端 |
| `docker` | CONTAINER | ★★★ | Docker/Podman | 自托管服务器、CI/CD |
| `e2b` (CubeSandbox) | HARDWARE (KVM) | ★★★★ | CubeSandbox 集群 | SaaS 多租户、生产环境 |

**自动检测** (`auto`): Provider 工厂按优先级尝试 `e2b → docker → subprocess`。

### 快速选择

```bash
# 本地开发 — 零依赖
echo 'DAWEI_SANDBOX_PROVIDER=subprocess' >> .env

# 自托管服务器 — 需要已安装 Docker
echo 'DAWEI_SANDBOX_PROVIDER=docker' >> .env

# 生产 SaaS — 需要 CubeSandbox 集群
echo 'DAWEI_SANDBOX_PROVIDER=e2b' >> .env
```

---

## 2. 本地开发模式 (subprocess)

### 前提

- Python 3.12+
- 无额外系统依赖

### 配置

```bash
# .env
DAWEI_SANDBOX_PROVIDER=subprocess
DAWEI_WORKSPACE_ROOT_ALLOWLIST=/tmp:/home:/workspace:/srv
DAWEI_LOG_SALT=dev-only-not-for-production-12345
```

### 验证

```bash
cd agent && uv run python -c "
from dawei.sandbox import SandboxFacade, from_user_workspace
ctx = from_user_workspace('dev-user', '/tmp')
result = SandboxFacade.execute_command('echo sandbox_ok', ctx)
print(result.stdout)
SandboxFacade.reset()
"
```

预期输出: `sandbox_ok`

### 安全限制

- **进程级隔离**: 命令在主进程的子进程中执行, 共享文件系统
- **白名单**: 通过 `DAWEI_WORKSPACE_ROOT_ALLOWLIST` 限制可访问路径
- **无网络隔离**: 不提供 eBPF 网络策略
- **无资源配额**: 不提供 LRU 淘汰 / 内存限制

---

## 3. Docker 隔离模式

### 前提

- Docker Engine 24+ 或 Podman 4+
- `dockerd` 服务运行中

### 配置

```bash
# .env
DAWEI_SANDBOX_PROVIDER=docker
DAWEI_WORKSPACE_ROOT_ALLOWLIST=/tmp:/home:/workspace:/srv:/data
DAWEI_LOG_SALT=<32-char-random-string>
```

### 验证

```bash
# 确认 Docker 可用
docker info >/dev/null 2>&1 && echo "Docker OK" || echo "Docker not available"

# 验证沙箱
cd agent && uv run python -c "
from dawei.sandbox import SandboxFacade, from_user_workspace
ctx = from_user_workspace('dev-user', '/tmp')
result = SandboxFacade.execute_command('whoami', ctx)
print(result.stdout)
SandboxFacade.reset()
"
```

### 安全特性

- **容器级隔离**: 每个命令在独立容器中执行
- **读写分离**: `workspace_mount_mode=ro` 时拦截写命令 (N3)
- **资源限制**: CPU、内存、超时可配
- **无 KVM 隔离**: 与宿主共享内核

---

## 4. CubeSandbox 生产部署 (e2b)

### 4.1 前提

- 裸金属服务器或支持嵌套虚拟化的云主机
- KVM 可用 (`ls /dev/kvm`)
- Ubuntu 22.04+ / Debian 12+
- root 权限

### 4.2 一键部署

```bash
# 创建 XFS 镜像 (仅首次)
truncate -s 100G /home/dev007/cube-sandbox-data.img
docker run --rm --privileged -v /home/dev007:/host \
    ubuntu:22.04 mkfs.xfs -f /host/cube-sandbox-data.img

# 一键安装 CubeSandbox + 创建模板
sudo bash scripts/deploy-cubesandbox.sh
```

部署脚本完成后会输出:
```
API URL:     http://127.0.0.1:3000
Template:    code-interpreter
API Key:     <auto-extracted>
```

### 4.3 安装 Precheck 脚本到模板

将 `sandbox-precheck.sh` 注入 CubeSandbox 模板镜像:

```bash
# 方法 1: 构建自定义模板 (推荐)
cubemastercli tpl create-from-image \
    --image cube-sandbox-int.tencentcloudcr.com/cube-sandbox/sandbox-code:latest \
    --name dawei-code-interpreter \
    --post-start /opt/dawei/sandbox-precheck.sh

# 方法 2: 在 E2BProvider 配置中指定 precheck 路径
# (由 _create_with_virtiofs 内部自动调用, 无需手动操作)
```

### 4.4 配置

```bash
# .env
DAWEI_SANDBOX_PROVIDER=e2b
DAWEI_SANDBOX_API_URL=http://127.0.0.1:3000
DAWEI_SANDBOX_API_KEY=<key-from-deploy-output>
DAWEI_SANDBOX_TEMPLATE=code-interpreter
DAWEI_WORKSPACE_ROOT_ALLOWLIST=/data/workspaces:/home:/workspace:/srv
DAWEI_SANDBOX_NETWORK_POLICY=dawei/sandbox/dawei_sandbox_network_policy.yaml
DAWEI_LOG_SALT=<32-char-random-from-kms>
SANDBOX_ADMIN_TOKEN=<shared-jwt-secret-with-nn-user-system>
```

### 4.5 SaaS 多租户配置

SaaS 部署需要额外配置:

```bash
# nn-bot .env
DAWEI_SANDBOX_PROVIDER=e2b
SANDBOX_ADMIN_TOKEN=<32-byte-hex-shared-with-nn-user-system>

# nn-user-system .env (跨服务代理)
NN_BOT_API_URL=http://localhost:8010
NN_BOT_ADMIN_JWT_SECRET=<same-as-SANDBOX_ADMIN_TOKEN>
NN_BOT_API_TIMEOUT_S=5
```

### 4.6 安全验证

```bash
# 验证 CubeSandbox 健康
curl -sf http://127.0.0.1:3000/health && echo "CubeSandbox OK"

# 验证沙箱创建 + tmpfs 遮蔽
cd agent && uv run python -c "
from unittest.mock import patch, MagicMock
from dawei_biz.saas.e2b_provider import E2BProvider
from dawei.sandbox.base import from_user_workspace

provider = E2BProvider({})
ctx = from_user_workspace('verify-user', '/tmp')
print(f'Provider: {provider.__class__.__name__}')
print(f'Isolation: {provider.get_capabilities().isolation_level}')
print(f'Capabilities: {provider.get_capabilities()}')
"

# 运行红蓝对抗测试
cd agent && uv run pytest tests/unit/test_sandbox_v2.py -v
```

---

## 5. 配置项参考

| 环境变量 | 默认值 | 说明 | 必填 |
|---------|--------|------|------|
| `DAWEI_SANDBOX_PROVIDER` | `subprocess` | Provider 类型 | 是 |
| `DAWEI_SANDBOX_API_URL` | `http://127.0.0.1:3000` | CubeSandbox API 地址 | 仅 e2b |
| `DAWEI_SANDBOX_API_KEY` | `dummy` | CubeSandbox API Key | 仅 e2b |
| `DAWEI_SANDBOX_TEMPLATE` | `code-interpreter` | 沙箱模板 ID | 仅 e2b |
| `DAWEI_WORKSPACE_ROOT_ALLOWLIST` | `/tmp:/home:/workspace:/srv` | 路径白名单 (冒号分隔) | 是 |
| `DAWEI_SANDBOX_NETWORK_POLICY` | (空) | eBPF 网络策略 YAML 路径 | 否 |
| `DAWEI_LOG_SALT` | (弱默认值) | PII 日志脱敏 salt | 生产必填 |
| `SANDBOX_ADMIN_TOKEN` | — | Admin API JWT secret | SaaS 必填 |

---

## 6. N5: 跨用户 .dawei/ 隔离边界

### 6.1 设计原则

> **workspace 级共享, 沙箱级隔离**

```
~/.dawei/                          ← 宿主侧: 所有 workspace 共享
├── settings.json                  ← 全局配置 (所有 workspace 可读)
├── workspaces/
│   ├── ws-user-A/                 ← 用户 A 的 workspace
│   │   ├── .dawei/
│   │   │   ├── settings.json      ← workspace 级配置
│   │   │   ├── workspace.json
│   │   │   ├── chat-history/      ← 对话历史
│   │   │   └── sessions/          ← 会话状态
│   │   └── project/               ← 用户 A 的项目文件
│   └── ws-user-B/                 ← 用户 B 的 workspace (隔离)
│       ├── .dawei/
│       └── project/
```

### 6.2 隔离机制 (e2b 模式)

| 层 | 机制 | 说明 |
|----|------|------|
| **宿主文件系统** | per-workspace 目录 | `~/.dawei/workspaces/<ws-id>/` 每个用户独立目录 |
| **沙箱挂载** | virtiofs mount | 仅挂载当前用户的 workspace 到 `/workspace` |
| **.dawei/ 遮蔽** | tmpfs overlay | mount tmpfs 到 `/workspace/.dawei`, 遮蔽宿主配置文件 |
| **遮蔽验证** | fail-closed precheck | 沙箱启动后验证 tmpfs 已挂载, 失败则销毁沙箱 |
| **路径白名单** | F3 三层校验 | 仅允许 `DAWEI_WORKSPACE_ROOT_ALLOWLIST` 内路径 |

### 6.3 隔离机制 (docker 模式)

| 层 | 机制 | 说明 |
|----|------|------|
| **容器文件系统** | bind mount | 仅挂载当前用户的 workspace |
| **读写控制** | ro/rw mount mode | `workspace_mount_mode=ro` 时写命令被拦截 (N3) |
| **无 tmpfs 遮蔽** | — | Docker 模式不提供 .dawei/ 遮蔽 (由容器边界保证隔离) |

### 6.4 隔离机制 (subprocess 模式)

| 层 | 机制 | 说明 |
|----|------|------|
| **无隔离** | 共享文件系统 | subprocess 在主进程的子进程中执行 |
| **路径白名单** | F3 三层校验 | 仍通过白名单限制可访问路径 |
| **适用场景** | 单用户桌面端 | self-hosted 模式下用户即管理员, 无跨用户风险 |

### 6.5 安全边界总结

| 攻击场景 | subprocess | docker | e2b |
|---------|-----------|--------|-----|
| 读取他人 .dawei/ 配置 | 不适用 (单用户) | ✗ 容器隔离 | ✓ tmpfs 遮蔽 |
| 越界路径 (`/etc/passwd`) | ✓ 白名单 | ✓ 容器 | ✓ 白名单 + KVM |
| 内核提权 | 不适用 | ✗ 共享内核 | ✓ KVM 隔离 |
| 网络外泄 | 不适用 | ✗ 需额外配 | ✓ eBPF 策略 |
| 侧信道攻击 | 不适用 | ✗ | ✓ KVM 隔离 |

---

## 7. 验证与排障

### 7.1 健康检查

```bash
# Provider 健康检查
cd agent && uv run python -c "
from dawei.sandbox import SandboxFacade
healthy = SandboxFacade.health_check()
print(f'Sandbox health: {\"OK\" if healthy else \"FAIL\"}')"

# Provider 能力查询
cd agent && uv run python -c "
from dawei.sandbox import SandboxFacade
caps = SandboxFacade.get_capabilities()
print(f'Isolation: {caps.isolation_level}')
print(f'RO support: {caps.supports_ro_mount}')"
```

### 7.2 常见问题

#### Provider 启动失败

```
[SANDBOX_FACADE] Provider 已初始化: SubprocessProvider
```

如果期望 Docker/e2b 但显示 SubprocessProvider:
- 检查 `DAWEI_SANDBOX_PROVIDER` 环境变量
- Docker: 确认 `dockerd` 运行中
- e2b: 确认 CubeSandbox API 可达 (`curl http://127.0.0.1:3000/health`)

#### tmpfs 遮蔽失败 (e2b)

```
SandboxSecurityError: tmpfs 遮蔽失败 (exit=1): mount: permission denied
```

原因: CubeSandbox 模板内缺少 mount 权限。
解决: 使用带 root 权限的模板, 或检查 AppArmor / SELinux 策略。

#### 路径白名单拒绝

```
SandboxSecurityError: 路径 /data/my-project 不在白名单根目录中
```

解决: 将 `/data` 添加到 `DAWEI_WORKSPACE_ROOT_ALLOWLIST`。

#### PII 日志 salt 警告

```
WARNING - DAWEI_LOG_SALT using unsafe development default
```

解决: 设置 `DAWEI_LOG_SALT` 为 32+ 字符随机字符串。

### 7.3 日志位置

| 组件 | 位置 |
|------|------|
| 沙箱执行日志 | `~/.dawei/logs/sandbox-*.log` |
| PII 脱敏日志 | 同上 (由 PiiSafeLogger 包装) |
| WebSocket 生命周期 | `~/.dawei/logs/websocket-*.log` |
| CubeSandbox 日志 | `/data/cube/logs/` 或 `docker logs cube-api` |
| Admin API 日志 | `~/.dawei/logs/admin-*.log` |

### 7.4 全量测试

```bash
cd agent

# 单元测试 (55 tests)
uv run pytest tests/unit/test_sandbox_v2.py -v

# 集成测试 (需要 Docker)
DAWEI_SANDBOX_PROVIDER=docker uv run pytest tests/unit/test_sandbox_v2.py -v
```
