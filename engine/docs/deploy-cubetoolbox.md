# CubeSandbox (CubeToolbox) 生产环境部署指南

> 版本: v0.5.0-amd64 | 适用平台: Linux x86_64 (KVM) | 编写日期: 2026-07-10

本文档记录 CubeSandbox 的完整部署步骤，包括宿主机准备、一键部署、容器修复、模板构建、DNS 配置、以及 dawei agent 集成。

---

## 目录

1. [架构概览](#1-架构概览)
2. [宿主机要求](#2-宿主机要求)
3. [一键部署](#3-一键部署)
4. [容器修复（已知问题）](#4-容器修复已知问题)
5. [DNS 本地路由配置](#5-dns-本地路由配置)
6. [TLS 证书信任](#6-tls-证书信任)
7. [沙箱模板管理](#7-沙箱模板管理)
8. [自定义模板（预装 Python 库）](#8-自定义模板预装-python-库)
9. [dawei agent 集成](#9-dawei-agent-集成)
10. [运维命令速查](#10-运维命令速查)
11. [故障排查](#11-故障排查)

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│  宿主机 10.168.1.135                                         │
│                                                               │
│  ┌─────────── Docker Bridge: cubesandbox_cube-net ─────────┐ │
│  │  cube-api:3000    cube-cubemaster:8089                  │ │
│  │  cube-webui:80    cube-mysql:3306    cube-redis:6379   │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────── Host Network ────────────────────────────────┐ │
│  │  cube-coredns (169.254.254.53)   cube-proxy (443/80)   │ │
│  │  cube-egress                                            │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────── Host Processes (systemd) ────────────────────┐ │
│  │  cubelet (--config config.toml)                        │ │
│  │  network-agent (--cubelet-config config.toml)          │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  /dev/kvm (Intel VT-x)     /data (XFS reflink=1, 80G)      │
└─────────────────────────────────────────────────────────────┘
```

### 组件职责

| 组件 | 网络 | 端口 | 职责 |
|------|------|------|------|
| **cube-api** | bridge | 127.0.0.1:3000 | E2B-compatible REST API |
| **cube-cubemaster** | bridge | 127.0.0.1:8089 | 模板管理、沙箱调度、配额 |
| **cube-webui** | bridge | 0.0.0.0:12088 | Web 管理界面 |
| **cube-proxy** | host | 443, 80 | sandbox 流量代理 (TLS 终止) |
| **cube-mysql** | bridge | 127.0.0.1:3306 | 元数据存储 |
| **cube-redis** | bridge | 127.0.0.1:6380 | 代理端口映射缓存 |
| **cube-coredns** | host | 169.254.254.53 | `*.cube.app` 域名解析 |
| **cube-egress** | host | — | 沙箱出站网络网关 |
| **cubelet** | host process | 9999 (gRPC) | 节点级沙箱生命周期 (MicroVM 创建/销毁) |
| **network-agent** | host process | — | TAP 网络配置辅助 |

### 数据流

```
E2B SDK → cube-api:3000 (创建沙箱)
         → cubemaster:8089 (调度到节点)
           → cubelet (创建 KVM MicroVM, FICLONE rootfs)
             → cube-proxy (分配端口, 代理流量)
               → CoreDNS (*.cube.app → cube-proxy)

SDK → {port}-{sandbox_id}.code.cube.app → CoreDNS → cube-proxy → MicroVM
```

---

## 2. 宿主机要求

### 硬件

- **CPU**: x86_64, 支持硬件虚拟化 (Intel VT-x / AMD-V)
- **内存**: >= 8 GB (每个沙箱默认 2 GB)
- **磁盘**: >= 80 GB, **必须 XFS + reflink=1**

### 检查 KVM

```bash
ls -la /dev/kvm
# 预期: crw-rw----+ 1 root kvm 10, 232 ... /dev/kvm

lsmod | grep kvm
# 预期: kvm_intel / kvm_amd 模块已加载
```

如未加载:
```bash
sudo modprobe kvm_intel  # Intel
# 或
sudo modprobe kvm_amd    # AMD
```

### 检查/创建 XFS reflink 文件系统

CubeSandbox 的 copy-on-write 隔离依赖 XFS reflink (FICLONE ioctl)。

```bash
# 检查现有挂载
xfs_info /data | grep reflink
# 预期: reflink=1

# 如需新建 (在块设备或 loop 文件上)
sudo mkfs.xfs -m reflink=1 /dev/sdXN
sudo mount -o prjquota /dev/sdXN /data

# 持久化挂载
echo '/dev/sdXN /data xfs defaults,prjquota 0 0' | sudo tee -a /etc/fstab
```

### 网络

- 宿主机需要一块物理网卡用于 TAP 网络（默认 `eno2`，可改）
- 确保内网网段 `10.200.0.0/18` 不与现有网络冲突

---

## 3. 一键部署

### 3.1 下载 CubeToolbox

从腾讯云镜像下载发布包:

```bash
sudo mkdir -p /usr/local/services/cubetoolbox
cd /usr/local/services/cubetoolbox

# 下载 v0.5.0 发布包 (amd64)
# 实际部署时替换为官方下载地址
sudo wget -O cubetoolbox.tar.gz <download-url>
sudo tar xzf cubetoolbox.tar.gz --strip-components=1
```

### 3.2 配置一键部署参数

编辑 `/usr/local/services/cubetoolbox/.one-click.env`:

```bash
ONE_CLICK_DEPLOY_ROLE=control        # control=控制面+计算节点合一
CUBE_PVM_ENABLE=0                     # 0=使用标准 KVM, 1=使用 PVM
MIRROR=cn                             # 镜像源: cn=腾讯云国内, global=Docker Hub
CUBE_SANDBOX_NODE_IP=10.168.1.135     # 宿主机 IP
CUBE_SANDBOX_ETH_NAME=eno2            # 物理网卡名 (TAP 网络用)
CUBE_SANDBOX_NETWORK_CIDR=10.200.0.0/18  # 沙箱内网 CIDR
DATABASE_URL=mysql://cube:cube_pass@127.0.0.1:3306/cube_mvp
```

### 3.3 执行一键部署

```bash
cd /usr/local/services/cubetoolbox

# 方式 A: 一键全量部署 (推荐)
sudo bash scripts/one-click/up-with-deps.sh

# 方式 B: 分步部署
sudo bash scripts/one-click/up.sh           # 控制面 (MySQL, Redis, API, Cubemaster)
sudo bash scripts/one-click/up-compute.sh   # 计算节点 (Cubelet)
sudo bash scripts/one-click/up-dns.sh       # DNS (CoreDNS + resolved)
sudo bash scripts/one-click/up-cube-proxy.sh # 代理
sudo bash scripts/one-click/up-cube-egress.sh # 出站网关
sudo bash scripts/one-click/up-webui.sh     # Web UI
```

### 3.4 验证部署

```bash
# 健康检查
curl http://127.0.0.1:3000/health
# 预期: {"status":"ok","sandboxes":0}

# 节点状态
curl http://127.0.0.1:3000/nodes
# 预期: 节点 10.168.1.135 状态 RUNNING/HEALTHY

# Web UI
curl http://127.0.0.1:12088/
# 预期: HTTP 200
```

---

## 4. 容器修复（已知问题）

一键部署后可能遇到以下问题，需要手动修复。

### 4.1 cube-cubemaster 缺少 CA 证书

**症状**: 模板创建失败，TLS 证书验证错误。

**原因**: cubemaster 容器内缺少 `/etc/ssl/certs/ca-certificates.crt`。

**修复**: 重新创建容器，挂载宿主机 CA bundle:

```bash
sudo docker stop cube-cubemaster && sudo docker rm cube-cubemaster

sudo docker run -d \
  --name cube-cubemaster \
  --restart unless-stopped \
  --network cubesandbox_cube-net \
  --network-alias cubemaster \
  -p 127.0.0.1:8089:8089 \
  -v /usr/local/services/cubetoolbox/CubeMaster/bin/cubemaster:/usr/local/bin/cubemaster \
  -v /usr/local/services/cubetoolbox/CubeMaster/conf-container.yaml:/etc/cubesandbox/cubemaster-conf.yaml \
  -v /data/log/CubeMaster:/data/log/CubeMaster \
  -v /data/CubeMaster/storage:/data/CubeMaster/storage \
  -v /etc/ssl/certs/ca-certificates.crt:/etc/ssl/certs/ca-certificates.crt:ro \
  -e CUBEMASTER_ROOTFS_ARTIFACT_STORE_DIR=/data/CubeMaster/storage \
  -e CUBE_MASTER_CONFIG_PATH=/etc/cubesandbox/cubemaster-conf.yaml \
  ubuntu:22.04 /usr/local/bin/cubemaster
```

> **关键**: `--network-alias cubemaster` 确保 cube-api 可通过 `cubemaster:8089` 访问。

### 4.2 cube-api 缺少 URL scheme

**症状**: cube-api 日志报 `builder error for url (cubemaster:8089/...)`。

**原因**: `CUBE_MASTER_ADDR` 缺少 `http://` 前缀。

**修复**:

```bash
sudo docker stop cube-api && sudo docker rm cube-api

sudo docker run -d \
  --name cube-api \
  --restart unless-stopped \
  --network cubesandbox_cube-net \
  -p 127.0.0.1:3000:3000 \
  -v /data/log/CubeAPI:/data/log/CubeAPI \
  -v /etc/ssl/certs/ca-certificates.crt:/etc/ssl/certs/ca-certificates.crt:ro \
  -e CUBE_API_BIND=0.0.0.0:3000 \
  -e CUBE_API_SANDBOX_DOMAIN=cube.app \
  -e CUBE_MASTER_ADDR=http://cubemaster:8089 \
  ubuntu:22.04 /usr/local/bin/cube-api
```

> **关键**: `CUBE_MASTER_ADDR=http://cubemaster:8089` 必须有 `http://` scheme。

### 4.3 CubeEgress root CA 缺失

**症状**: 模板创建报 `with_cube_ca=true but CubeEgress root CA is missing at /etc/cube/ca/cube-root-ca.crt`。

**修复**: 创建模板时使用 `--with-cube-ca=false` 跳过 CA 注入:

```bash
sudo /usr/local/services/cubetoolbox/CubeMaster/bin/cubemastercli tpl create-from-image \
  --image <image-url> \
  --with-cube-ca=false \
  ...
```

---

## 5. DNS 本地路由配置

CubeSandbox 使用 `*.cube.app` 域名路由沙箱流量。默认 DNS 会将 `cube.app` 解析到公网，需要通过 systemd-resolved 将其路由到本地 CoreDNS。

### 5.1 创建 resolved drop-in

```bash
sudo mkdir -p /etc/systemd/resolved.conf.d
sudo tee /etc/systemd/resolved.conf.d/cube.conf << 'EOF'
[Resolve]
DNS=169.254.254.53
Domains=~cube.app
EOF

sudo systemctl restart systemd-resolved
```

### 5.2 验证

```bash
# 确认 cube.app 走 CoreDNS
resolvectl domain
# 预期: 含 ~cube.app 行

resolvectl status
# 预期: Link containing 169.254.254.53 with domain ~cube.app

# 测试解析 (需要先创建沙箱才有实际记录)
nslookup test.code.cube.app
# 预期: 解析到 10.168.1.135 (或对应宿主机 IP)
```

---

## 6. TLS 证书信任

cube-proxy 使用 mkcert 生成的本地开发证书。E2B SDK 和 httpx 客户端需要信任此 CA。

### 6.1 找到 mkcert root CA

```bash
sudo mkcert -CAROOT
# 输出: /root/.local/share/mkcert
sudo cat /root/.local/share/mkcert/rootCA.pem
```

### 6.2 加入系统信任库

```bash
sudo cp /root/.local/share/mkcert/rootCA.pem /usr/local/share/ca-certificates/mkcert-rootCA.crt
sudo update-ca-certificates
# 预期: 1 added, 0 removed; done.
```

### 6.3 验证

```bash
# Python 使用系统 CA
python3 -c "import ssl; print(ssl.get_default_verify_paths())"
# cafile 应指向 /etc/ssl/certs/ca-certificates.crt

# 测试 TLS 连接
echo | openssl s_client -connect 127.0.0.1:443 -servername code.cube.app 2>/dev/null | \
  openssl x509 -text -noout | head -10
```

---

## 7. 沙箱模板管理

### 7.1 列出模板

```bash
curl http://127.0.0.1:3000/templates
```

### 7.2 创建基础模板

从官方 code-interpreter 镜像创建:

```bash
sudo /usr/local/services/cubetoolbox/CubeMaster/bin/cubemastercli tpl create-from-image \
  --image cube-sandbox-cn.tencentcloudcr.com/cube-sandbox/sandbox-code:latest \
  --writable-layer-size 2G \
  --cpu 2000 \
  --memory 2000 \
  --with-cube-ca=false \
  --allow-internet-access
```

输出示例:
```
submitted template image job: job_id=xxx template_id=tpl-xxxxxxxxxxxx
[1/7] PULLING   progress=0%
[2/7] UNPACKING progress=20%
[5/7] DISTRIBUTING progress=70%
[7/7] READY     progress=100%
template image job succeeded
```

### 7.3 删除模板

```bash
curl -X DELETE http://127.0.0.1:3000/templates/<template_id>
```

### 7.4 查看模板详情

```bash
curl http://127.0.0.1:3000/templates/<template_id> | python3 -m json.tool
```

关键字段:
- `status`: READY / FAILED / BUILDING
- `replicas[].spec`: `cpu=2000m,mem=2000Mi`
- `replicas[].kernel_version`: MicroVM 内核版本
- `createRequest.containers[0].envs`: 环境变量 (PYTHON_VERSION 等)
- `createRequest.containers[0].resources`: CPU / 内存配额

---

## 8. 自定义模板（预装 Python 库）

dawei agent 需要沙箱内预装常用 Python 库（文档处理、数据科学、HTTP 客户端等）。

### 8.1 准备本地 Docker Registry

Cubelet 需要 HTTP 访问镜像，使用本地 registry:

```bash
sudo docker run -d \
  --name cube-registry \
  --restart unless-stopped \
  -p 5000:5000 \
  registry:2
```

### 8.2 构建 Dockerfile

Dockerfile 位于 `agent/docker/sandbox-template.Dockerfile`:

```dockerfile
FROM cube-sandbox-cn.tencentcloudcr.com/cube-sandbox/sandbox-code:latest

# 系统依赖 + 中文字体
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget git zip unzip \
    fontconfig fonts-liberation fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 文档处理库
RUN pip install --no-cache-dir \
    python-docx openpyxl reportlab PyMuPDF pypdfium2 markitdown

# 数据科学库
RUN pip install --no-cache-dir \
    numpy pandas matplotlib seaborn scipy scikit-learn

# HTTP / 工具库
RUN pip install --no-cache-dir \
    requests httpx aiohttp \
    PyYAML jinja2 jsonschema \
    python-dotenv python-frontmatter aiosqlite \
    beautifulsoup4 lxml Pillow

# 验证
RUN python3 -c "\
import docx, openpyxl, reportlab, fitz, pypdfium2; print('doc OK'); \
import numpy, pandas, matplotlib, scipy, sklearn; print('science OK'); \
import requests, httpx, aiohttp, yaml, jinja2, jsonschema; print('util OK'); \
print('ALL LIBRARIES INSTALLED')"
```

### 8.3 构建并推送

```bash
# 必须使用宿主机 IP，不能用 localhost (IPv6 解析问题)
HOST_IP=$(hostname -I | awk '{print $1}')

docker build -t ${HOST_IP}:5000/dawei-sandbox:latest \
  -f agent/docker/sandbox-template.Dockerfile agent/docker/

docker push ${HOST_IP}:5000/dawei-sandbox:latest
```

### 8.4 创建模板

```bash
sudo /usr/local/services/cubetoolbox/CubeMaster/bin/cubemastercli tpl create-from-image \
  --image ${HOST_IP}:5000/dawei-sandbox:latest \
  --writable-layer-size 2G \
  --cpu 2000 \
  --memory 2000 \
  --with-cube-ca=false \
  --allow-internet-access
```

### 8.5 更新 agent 配置

将新模板 ID 写入 `agent/.env`:

```bash
DAWEI_SANDBOX_TEMPLATE=tpl-<new-template-id>
```

### 8.6 模板更新流程

当需要增加/更新预装库时:

```bash
# 1. 编辑 Dockerfile
vim agent/docker/sandbox-template.Dockerfile

# 2. 构建推送
HOST_IP=$(hostname -I | awk '{print $1}')
docker build -t ${HOST_IP}:5000/dawei-sandbox:latest \
  -f agent/docker/sandbox-template.Dockerfile agent/docker/
docker push ${HOST_IP}:5000/dawei-sandbox:latest

# 3. 创建新模板 (会生成新 template_id)
sudo cubemastercli tpl create-from-image \
  --image ${HOST_IP}:5000/dawei-sandbox:latest \
  --writable-layer-size 2G --with-cube-ca=false --allow-internet-access

# 4. 更新 .env 中的 DAWEI_SANDBOX_TEMPLATE

# 5. (可选) 删除旧模板
curl -X DELETE http://127.0.0.1:3000/templates/<old-template-id>
```

---

## 9. dawei agent 集成

### 9.1 agent/.env 配置

```bash
# Provider 自动选择: 用户安全设置 > 环境变量 > 自动检测
DAWEI_SANDBOX_PROVIDER=auto

# CubeSandbox API
DAWEI_SANDBOX_API_URL=http://127.0.0.1:3000
DAWEI_SANDBOX_API_KEY=dummy

# E2B SDK 连接配置 (SDK 要求 e2b_ 前缀格式的 key)
E2B_API_URL=http://127.0.0.1:3000
E2B_DOMAIN=code.cube.app
E2B_API_KEY=e2b_0000000000000000000000000000000000000000

# 沙箱模板
DAWEI_SANDBOX_TEMPLATE=tpl-f070a779a70d4d258b026ed3

# 工作区路径白名单
DAWEI_WORKSPACE_ROOT_ALLOWLIST=/tmp:/home:/workspace:/srv:/data
```

### 9.2 关键环境变量说明

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `DAWEI_SANDBOX_PROVIDER` | Provider 选择 (auto/e2b/docker/subprocess) | auto |
| `E2B_API_URL` | E2B SDK API 端点 | https://api.e2b.app |
| `E2B_DOMAIN` | 沙箱域名后缀 | e2b.app |
| `E2B_API_KEY` | SDK 认证 key (需 `e2b_` 前缀，CubeSandbox auth 关闭时用占位符) | — |
| `DAWEI_SANDBOX_TEMPLATE` | 模板 ID | code-interpreter |

### 9.3 沙箱创建流程 (dawei → CubeSandbox)

```
1. dawei agent 调用 SandboxFacade.execute_command(cmd, ctx)
2. E2BProvider._get_or_create_session(ctx)
3. E2BSandbox.create(
     template=DAWEI_SANDBOX_TEMPLATE,
     api_key=E2B_API_KEY,
     metadata={
       "host-mount": json.dumps([{
         "hostPath": workspace_path,
         "mountPath": "/workspace",
         "readOnly": mount_mode == "ro"
       }])
     }
   )
4. CubeSandbox cube-api 收到请求 → cubemaster 调度 → cubelet 创建 MicroVM
5. cubelet 从模板 rootfs 做 FICLONE 快照 (XFS reflink, O(1))
6. cubelet 通过 virtio-fs 挂载 host-mount 指定的主机目录
7. cube-proxy 分配端口, CoreDNS 注册 DNS 记录
8. E2B SDK 连接 {port}-{sandbox_id}.code.cube.app → cube-proxy → MicroVM
```

---

## 10. 运维命令速查

### 服务管理

```bash
# systemd 服务 (cubelet + network-agent)
sudo systemctl status cube-sandbox-cubelet.service
sudo systemctl status cube-sandbox-network-agent.service
sudo systemctl restart cube-sandbox-cubelet.service

# Docker 容器
sudo docker restart cube-api cube-cubemaster
sudo docker logs -f --tail 50 cube-api
sudo docker logs -f --tail 50 cube-cubemaster

# 全量停止/启动
cd /usr/local/services/cubetoolbox
sudo bash scripts/one-click/down-with-deps.sh
sudo bash scripts/one-click/up-with-deps.sh
```

### 模板管理

```bash
# 列出
curl http://127.0.0.1:3000/templates

# 详情
curl http://127.0.0.1:3000/templates/<id> | python3 -m json.tool

# 删除
curl -X DELETE http://127.0.0.1:3000/templates/<id>

# 创建 (基础镜像)
sudo cubemastercli tpl create-from-image \
  --image <url> --with-cube-ca=false --allow-internet-access
```

### 节点/沙箱状态

```bash
# 节点列表
curl http://127.0.0.1:3000/nodes

# 活跃沙箱
curl http://127.0.0.1:3000/health

# 系统诊断
sudo bash /usr/local/services/cubetoolbox/scripts/one-click/quickcheck.sh
```

### DNS 验证

```bash
resolvectl domain
resolvectl query code.cube.app
dig @169.254.254.53 code.cube.app
```

### 磁盘使用

```bash
# /data 分区 (沙箱 rootfs 存储)
df -hT /data

# cubecow 卷列表
ls -la /data/cubelet/storage/cubecow-reflink/volumes/

# 清理未使用的模板镜像
sudo bash -c 'crictl rmi --prune'
```

---

## 11. 故障排查

### 沙箱创建失败

```bash
# 查看 cube-api 日志
sudo docker logs cube-api 2>&1 | tail -30

# 查看 cubemaster 日志
sudo docker logs cube-cubemaster 2>&1 | tail -30

# 查看 cubelet 日志
sudo journalctl -u cube-sandbox-cubelet.service --since "10 min ago" | tail -50
```

### E2B SDK SSL 错误

```
ssl.SSLCertVerificationError: certificate verify failed: unable to get local issuer certificate
```

**原因**: mkcert root CA 未加入系统信任库。

**修复**:
```bash
sudo cp /root/.local/share/mkcert/rootCA.pem \
  /usr/local/share/ca-certificates/mkcert-rootCA.crt
sudo update-ca-certificates
```

### E2B SDK API key 格式错误

```
AuthenticationException: Invalid API key format
```

**原因**: E2B SDK 要求 key 以 `e2b_` 开头 + hex 字符。

**修复**: 设置 `E2B_API_KEY=e2b_0000000000000000000000000000000000000000`。

### DNS 解析到公网 IP

```
nslookup code.cube.app → 8.210.70.146 (公网)
```

**原因**: systemd-resolved 未将 `~cube.app` 路由到 CoreDNS。

**修复**: 创建 `/etc/systemd/resolved.conf.d/cube.conf`，重启 systemd-resolved。

### cube-api 连接 cubemaster 失败

```
builder error for url (cubemaster:8089/...)
```

**原因**: `CUBE_MASTER_ADDR` 缺少 `http://` scheme，或 cubemaster 容器缺少 network alias。

**修复**: 见 [4. 容器修复](#4-容器修复已知问题)。

### 模板创建 TLS 失败

```
tls: failed to verify certificate: x509: certificate signed by unknown authority
```

**原因**: cubemaster 容器内缺少 CA bundle。

**修复**: 重建 cubemaster 容器时挂载 `/etc/ssl/certs/ca-certificates.crt:ro`。

### 沙箱无法访问外网

检查 cube-egress 容器状态:

```bash
sudo docker logs cube-egress 2>&1 | tail -30
sudo docker inspect cube-egress --format '{{.State.Status}}'
```

检查网络配置 (`config.toml` 中的 `network` 插件):
```bash
sudo cat /usr/local/services/cubetoolbox/Cubelet/config/config.toml | grep -A5 network
```

---

## 附录 A: 当前部署实例信息

| 项 | 值 |
|---|---|
| CubeToolbox 版本 | v0.5.0-amd64 (git: 30b4e25) |
| 宿主机 IP | 10.168.1.135 |
| 宿主机内核 | 6.8.0-124-generic |
| /data 文件系统 | XFS, 80G, reflink=1 |
| 物理网卡 | eno2 |
| 沙箱网段 | 10.200.0.0/18 |
| CoreDNS | 169.254.254.53 (host network) |
| cube-api | 127.0.0.1:3000 |
| cubemaster | 127.0.0.1:8089 |
| WebUI | 0.0.0.0:12088 |
| MySQL | 127.0.0.1:3306 (cube/cube_pass) |
| Redis | 127.0.0.1:6380 (pass: ceuhvu123) |
| 本地 Registry | 10.168.1.135:5000 |
| 当前模板 | tpl-f070a779a70d4d258b026ed3 (自定义, 预装 20 库) |
| Fallback 模板 | tpl-47a90d1c0dc5473fb87237ab (基础 code-interpreter) |

## 附录 B: 预装 Python 库清单

| 类别 | 库 | 用途 |
|------|-----|------|
| 文档处理 | python-docx | DOCX 读写 |
| | openpyxl | Excel 读写 |
| | reportlab | PDF 生成 |
| | PyMuPDF (fitz) | PDF 解析 |
| | pypdfium2 | PDF 渲染 |
| | markitdown | Markdown 转换 |
| 数据科学 | numpy | 数值计算 |
| | pandas | 数据分析 |
| | matplotlib | 图表绘制 |
| | seaborn | 统计可视化 |
| | scipy | 科学计算 |
| | scikit-learn | 机器学习 |
| HTTP/工具 | requests | HTTP 客户端 |
| | httpx | 异步 HTTP |
| | aiohttp | 异步 HTTP |
| | PyYAML | YAML 解析 |
| | jinja2 | 模板引擎 |
| | jsonschema | JSON 校验 |
| | python-dotenv | .env 解析 |
| | python-frontmatter | Markdown frontmatter |
| | aiosqlite | 异步 SQLite |
| 爬虫/图像 | beautifulsoup4 | HTML 解析 |
| | lxml | XML/HTML 解析 |
| | Pillow (PIL) | 图像处理 |
| 系统工具 | git, curl, wget, zip, fonts-noto-cjk | — |
