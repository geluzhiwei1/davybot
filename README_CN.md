# DavyBot

[English](README.md) | [中文](README_CN.md)

DavyBot 是一个开源的 **AI Agent 引擎 + 桌面/Web 应用核心**,用于构建个人与专业
AI 助手。本仓库为组件型 monorepo:

| 路径 | 内容 | 许可证 |
|---|---|---|
| [`engine/`](engine/) | **dawei** — Agent 引擎(Python 3.12、FastAPI):对话、60+ 工具、MCP、技能、TaskGraph 编排、知识库、Agent 记忆。不含业务逻辑。 | AGPL-3.0-only |
| [`app/`](app/) | 前端核心壳 + Tauri 桌面宿主(React 19、Vite 7、Tauri 2.x)。业务 UI 模块(`biz/`)不在本仓库,构建时装配。 | Apache-2.0 |
| [`scripts/`](scripts/) | 跨平台构建编排(桌面 / 服务器二进制)。 | Apache-2.0 |

引擎以 `davybot` PyPI 包发布,附带 `dawei` CLI;由本仓库构建的桌面产品为
**NormNomos**。

## 快速开始(用户)

要求 Python 3.12+:

```bash
pip install davybot        # 完整本地能力: pip install "davybot[all]"
```

### 运行模式

`dawei` CLI 共支持四种运行方式,全部支持**零云配置全本地冷启**(本地 + relay
模式,无需任何 API Key)。

| # | 模式 | 命令 |
|---|---|---|
| 1 | Web 服务器 + Web UI | `dawei server start` |
| 2 | 终端 UI(TUI) | `dawei tui --workspace ./my-ws` |
| 3 | 单次无头 Agent | `dawei agent run ./my-ws "你的任务"` |
| 4 | stdio ACP Agent | `dawei acp serve --workspace ./my-ws` |

#### 1. Web 服务器 + Web UI

```bash
dawei server start                    # 默认 0.0.0.0:8431,Ctrl+C 退出
dawei server start --host 127.0.0.1 --port 8010
dawei server start --password <pw>    # 启用访问口令
dawei server start -d                 # 守护进程方式运行

dawei server status                    # 查看运行状态
dawei server stop                      # 停止服务器
```

打开 **http://localhost:8431/app-ui/**。

#### 2. 终端 UI

```bash
dawei tui --workspace ./my-ws          # 工作区不存在则自动创建
dawei tui -w ./my-ws --llm <model>     # 指定模型(缺省用工作区配置)
dawei tui -w ./my-ws --theme dark      # 主题: default | dark | light
```

功能完整的终端界面:交互式对话(带自动补全)、实时思维过程展示、工具执行
跟踪、设置管理、命令面板(Ctrl+P)。

#### 3. 单次无头 Agent

在当前进程内直接执行任务,绕过 Web 服务器 —— 适合脚本化与 CI:

```bash
dawei agent run ./my-ws "Create hello world"
dawei agent run ./my-ws "设计 API" --mode plan       # 模式: orchestrator|plan|do|check|act
dawei agent run ./my-ws "写报告" -o result.txt        # 结果保存到文件
dawei agent run ./my-ws "改进这个仓库" --evolution     # 完整 PDCA 改进循环

dawei agent modes                      # 列出可用 Agent 模式
dawei agent validate ./my-ws           # 校验工作区配置
```

#### 4. ACP Agent(Agent Client Protocol)

以 stdio 方式把 dawei 作为 ACP Agent 提供给外部客户端(如编辑器集成),
也可调用外部 ACP 兼容 Agent:

```bash
dawei acp serve --workspace ./my-ws                    # dawei 作为 ACP 服务端(stdio)
dawei acp call --command codex --prompt "修复这个 bug"  # 调用外部 ACP Agent
```

### 配置与数据

- 模型供应商与行为:复制 `engine/agent/.env.example` 为 `.env`(四层配置
  优先级:`workspace/.dawei/` > `~/.dawei/` > `/etc/dawei/` > 包内默认)。
- 数据目录:`~/.normnomos/`(可用 `DAWEI_HOME` 覆盖)。
- 发布通道:`v*` 标签构建发布 `davybot` wheel 到 PyPI(`pip install -U davybot`),
  上传前先过零云冒烟;桌面/服务器二进制仍可用 `scripts/` 本地构建。
- 延伸阅读:[engine/README_CN.md](engine/README_CN.md)(技能/Agent 市场、IM
  集成),用户指南见 [engine/docs/user/](engine/docs/user/)。

## 快速开始(开发者)

前置依赖:Python 3.12+、Node 20+、Rust 工具链(仅桌面端)。完整环境搭建、
测试与 CI 策略见 [CONTRIBUTING.md](CONTRIBUTING.md)。

**引擎** — `engine/agent/`:

```bash
cd engine/agent
uv pip install --system -e ".[dev]"       # 或: pip install -e ".[dev]"

dawei server start --host 127.0.0.1 --port 8010 --reload

pytest -m unit -q                          # 单元测试
ruff check dawei/ && mypy dawei/           # 代码检查 + 类型检查
```

**前端** — `app/`:

```bash
cd app
npm ci
npm run dev            # Web 开发服务器,代理到引擎
npm run dev:desktop    # Tauri 桌面壳(需要 Rust 工具链)
npm run ci             # lint + typecheck + vitest + 核心构建
```

服务器嵌入模式的生产构建:`npm run build:server`(产物装配到
`engine/agent/dawei/frontend/`)。

**桌面 / 服务器二进制打包**:

```bash
# 完整桌面构建(前端 + sidecar + Tauri),Linux/macOS:
bash scripts/build-desktop.sh all

# Windows:
powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1 all

# 独立单文件服务器二进制(PyInstaller):
bash scripts/build-server-binary.sh
```

Push 阻断门禁(详见 CONTRIBUTING):云默认地址守卫、工具系统门禁、
前端 biz 隔离守卫。

## CI

`.github/workflows/` 在每次 push/PR 上运行零外部服务依赖的矩阵:

- **engine**:云默认守卫(出现任何硬编码云端点即判负)、工具系统门禁、单元测试
- **cli**:`dawei` / `server` / `tui` 冒烟
- **app**:lint + typecheck + vitest(含 biz 隔离守卫)+ 核心构建
- **server-smoke**:**无任何云环境变量**冷启 → 必须上报 `local` + `[relay]`

`v*` 标签构建将 `davybot` wheel 发布到 PyPI([pypi.yml](.github/workflows/pypi.yml)):
前端构建 → wheel → 零云冒烟 → 上传(沿用已有 `PYPI_API_TOKEN`)并同步建 GitHub Release。

## 许可证

按目录双重许可 — 详见 [LICENSE.md](LICENSE.md):

- `engine/` → **AGPL-3.0-only**([engine/LICENSE](engine/LICENSE))
- `app/`、`scripts/`、根目录文件 → **Apache-2.0**([app/LICENSE](app/LICENSE))
