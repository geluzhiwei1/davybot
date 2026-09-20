# nn-bot 集成测试设计方案（双套件 · 不 Mock · 含数据准备）

> **目标**：项目修改后自动回归 **nn-bot 后端核心功能**与 **前端↔后端契约**。两套测试都**直连真实运行中的 dawei 服务器（不 mock）**，并**在测试前准备好工作区等真实数据**。
>
> 覆盖结论（已探明）：
>
> - 后端核心 = Agent 引擎 + TaskGraph、60+ 工具、多 provider LLM、工作区、WebSocket（61 消息类型）、知识库（向量/全文/图谱/检索）、Memory、config 分层。
> - **聊天/agent 运行走 WebSocket**：客户端发 `USER_MESSAGE`，服务端流式回 `STREAM_REASONING/STREAM_CONTENT/STREAM_TOOL_CALL/STREAM_USAGE/STREAM_COMPLETE/STREAM_ERROR`。会话本身用 HTTP 文件持久化。
> - 已有范式：`agent/tests/integration/test_workspace_api.py` = `pytest + httpx` 直连活体服务器，文件级准备工作区数据（读写 `~/.normnomos/workspaces.json` + 建真实 `.dawei/` 目录，save→seed→restore）。

---

## 0. 两套测试的分工

|           | **Part A · 后端核心**                              | **Part B · 客户端契约**                                          |
| --------- | -------------------------------------------------- | ---------------------------------------------------------------- |
| 位置      | `engine/agent/tests/integration/`             | `app/tests/integration/`                             |
| 语言/框架 | Python · pytest + httpx + websockets               | TypeScript · vitest（真实 `fetch` + 前端 `api/*` + `ws-client`） |
| 驱动方式  | 直连 dawei HTTP/WS                                 | 用前端真实 API client 打活体后端                                 |
| 回归目标  | 后端核心逻辑（Agent/工具/知识库/TaskGraph/config） | 前端 client 与后端契约是否一致 + 客户端状态机                    |
| CI        | 后端仓库 CI（`pytest -m integration`）             | 前端仓库 CI（`npm run test:integration`）                        |
| 数据准备  | 文件级 seed 工作区（沿用现有 fixture 范式）        | HTTP 工作区创建 API + 清理                                       |

**两套互补**：A 直接验证后端能力正确；B 验证前端真实调用方式与后端契约吻合。同一功能在两侧都有 case 时，A 断言"后端做对了"，B 断言"前端这么调、能拿到对的结果"。

---

## 1. 拓扑与前置条件（两套共用）

| 项       | 值                                                               | 说明                                                                   |
| -------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------- |
| 后端端口 | **8431**（sidecar/本地默认）或 8010（独立 `dawei server start`） | 由 `INTEGRATION_TARGET` 指定                                           |
| 启动     | `cd engine/agent && uv run dawei server start --port 8431`  | 测试前需先起服务                                                       |
| 鉴权     | dev 下多数端点免鉴权（`workspaces/list` 实测无需 token）         | 若开启鉴权，用 `INTEGRATION_TOKEN` 注入 Bearer                         |
| LLM      | Agent 运行 / 聊天流式 / 知识库 embedding 需要 provider           | gate 在 `DAWEI_TEST_LLM=1`（或 Ollama 可达）；缺则 `skip`，**不 mock** |
| 环境     | `DAWEI_HOME`（默认 `~/.normnomos`）                              | 测试 workspace 写在此处，独立清理                                      |

**优雅降级**：服务未起 → 全部 `skip`（不报红）；LLM/embedding 缺 → 仅相关 case `skip`（标记 `slow`）。这是"前置条件不可用"，不属于 mock。

---

## 2. Part A · 后端核心（Python / `agent/tests/integration/`）

### 2.1 测试基础设施（扩展 `tests/conftest.py` + 新增 `integration/conftest.py`）

```python
# 关键 fixtures（设计要点，实现时落地）
live_base_url   # 读 INTEGRATION_TARGET，默认 http://localhost:8431；探活 /api/system 或 /api/workspaces/list，不可达则 skip 整个模块
async_client    # httpx.AsyncClient(base_url=live_base_url, timeout=30)
require_llm     # 读 DAWEI_TEST_LLM/OLLAMA 可达性；不可达 → pytest.skip
test_workspace  # 沿用现有：tmp_path 建真实 .dawei/ + settings.json(Ollama) + workspace.json + config.json
                #   并通过 workspaces/crud API 注册到 workspaces.json，yield id，finally 注销+删目录
seed_file       # 在工作区写 hello.txt / data.json / main.py 供工具测试
kb_doc          # 上传一份样本文档到测试知识库，等索引完成
ws_connect      # websockets.connect(live_ws_url/{workspace_id})，收集 STREAM_* 事件到队列
```

### 2.2 用例清单

**A1 · 工作区生命周期**（扩展 `test_workspace_api.py`，不重复其过滤用例）— P0

| ID   | 用例             | 关键断言                                                                                                                               |
| ---- | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| A1.1 | CRUD API 创建    | `POST /api/workspaces/...`（crud.py）创建 → 真实目录 + workspaces.json 入项；返回带 `id`/`workspace_category`                          |
| A1.2 | 列表/过滤一致性  | `GET /api/workspaces/list` 返回 seed 的工作区；`workspace_type`/`workspace_category`/`lifecycle` 过滤计数正确（衔接现有用例）          |
| A1.3 | 删除即清理       | 删除工作区 → 目录移除、workspaces.json 不再含该项                                                                                      |
| A1.4 | config effective | `GET /api/workspaces/{id}/config` 与 `.../skills-tools/effective`/`memory/effective`/`knowledge/effective` 返回结构正确（config 分层） |
| A1.5 | modes            | `GET/PUT /{id}/modes`、mode rules 读写                                                                                                 |

**A2 · 会话持久化**（HTTP 文件持久化）— P0

| ID   | 用例     | 关键断言                                                                                              |
| ---- | -------- | ----------------------------------------------------------------------------------------------------- |
| A2.1 | 增删查   | `POST /api/workspaces/{id}/conversations` 建 → `GET` 列表含 → `GET /{conv_id}` 取回 → `DELETE` 后消失 |
| A2.2 | 保存落盘 | `POST /{conv_id}` 保存对话 → `.dawei/chat-history/{conv_id}.json` 真实生成且内容一致                  |

**A3 · Agent 运行（WebSocket）—— 后端最核心** — P0（需 LLM）

| ID   | 用例         | 关键断言                                                                                                                  |
| ---- | ------------ | ------------------------------------------------------------------------------------------------------------------------- |
| A3.1 | 基本对话闭环 | 连 WS → 发 `USER_MESSAGE` → 收到 `STREAM_CONTENT`/`STREAM_REASONING` 序列 → 以 `STREAM_COMPLETE` 结束；assistant 文本非空 |
| A3.2 | 无错误       | 全程无 `STREAM_ERROR`；`STREAM_USAGE` 带 token 统计                                                                       |
| A3.3 | 工具调用流式 | 用需工具的 prompt → 收到 `STREAM_TOOL_CALL`，工具结果回流，最终 `STREAM_COMPLETE`                                         |
| A3.4 | 中断/abort   | 客户端中途断开 → 不留泄漏的流 / 定时器（衔接 STREAM_IDLE_TIMEOUT）                                                        |
| A3.5 | 多轮上下文   | 同一会话连发两条 → 第二条回答体现上文                                                                                     |

**A4 · 工具系统** — P1

| ID   | 用例         | 关键断言                                                                   |
| ---- | ------------ | -------------------------------------------------------------------------- |
| A4.1 | 命令清单     | `GET /api/tools/commands` 返回 builtin/system 工具集                       |
| A4.2 | 执行内置工具 | `POST /api/tools/commands/execute` 读 `seed_file`（如 Read）→ 返回正确内容 |
| A4.3 | reload       | `POST /api/tools/commands/reload` 不报错，工具集可再列出                   |

**A5 · 技能系统** — P1

| ID   | 用例      | 关键断言                                                                                               |
| ---- | --------- | ------------------------------------------------------------------------------------------------------ |
| A5.1 | 列表/搜索 | `GET /api/skills/list`、`/search/{q}` 返回结构                                                         |
| A5.2 | CRUD 往返 | `POST /api/skills/skill` 建技能 → `GET .../skill/{name}/content` → `PUT` 改 → `DELETE` 后 `/list` 不含 |
| A5.3 | 文件树    | `GET .../skill/{name}/tree`、`.../file` 读取                                                           |

**A6 · 知识库全生命周期（含删除清理回归）** — P0（近期修过删除 bug）

| ID   | 用例                                | 关键断言                                                                                                                     |
| ---- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| A6.1 | 建/列/默认                          | `POST /api/knowledge/bases` 建 → `GET` 列表含 → `/default` 可取                                                              |
| A6.2 | 上传+索引                           | `POST .../documents/upload` 上传 → 轮询 `.../documents` 直到索引完成                                                         |
| A6.3 | 检索四模式                          | `POST .../search` vector/fulltext/graph/hybrid 各返回带 `source` 的命中                                                      |
| A6.4 | 图谱                                | `.../graph/entities`、`/relations`、`/entities/{id}/sources` 结构                                                            |
| A6.5 | **删文档清 fulltext+graph**（回归） | `DELETE .../documents/{id}` 后：主文档 + 向量 chunk + FTS 行 + 图谱实体/关系 全部消失（直接查底层存储验证，不只看 API 返回） |
| A6.6 | 删库清理                            | `DELETE .../bases/{id}` → 该库全部数据清空                                                                                   |

**A7 · LLM 配置 / config 分层** — P1

| ID   | 用例           | 关键断言                                                                                                          |
| ---- | -------------- | ----------------------------------------------------------------------------------------------------------------- |
| A7.1 | 全局模型       | `GET /api/llms` → `{availableLLMs:[...]}`                                                                         |
| A7.2 | provider CRUD  | user 级 + workspace 级 provider create/update/delete 路径载荷                                                     |
| A7.3 | effective 合并 | `GET .../llm-providers/effective` override-or-inherit：effective 列表带 `source`/`user_overridden`，覆盖项标 true |
| A7.4 | settings 合并  | `.../llm-settings`(merged) 与 `.../llm-settings-all`(current_config+mode_configs) 一致                            |
| A7.5 | provider 测试  | `POST .../llm-providers/test?mode=` 返回 `{supported,model,message}`                                              |

**A8 · 其余核心（按需，P2）**：Memory（extract/scheduler）、MCP servers 配置、scheduled tasks、checklists、container runtime。

---

## 3. Part B · 客户端契约（TS / `nn-bot-app/tests/integration/`）

### 3.1 测试基础设施

```ts
// tests/integration/helpers/
//   live.ts     // 读 INTEGRATION_TARGET(默认 http://localhost:8431)；beforeAll 探活，不可达→describe.skip
//   auth.ts     // prime localStorage auth_token（INTEGRATION_TOKEN 或 dev 免鉴权）
//   workspace.ts// 通过 workspaceApi.create 建测试工作区，afterAll 清理
//   ws.ts       // 用真实 ws-client 连活体后端，收集 stream_* 事件
```

- `vitest.config.ts` 的 `include` 增 `tests/integration/**/*.test.ts`（或独立 `vitest.config.integration.ts` + `test:integration` 脚本）。
- 测试超时调大（流式/索引慢）；用 `vi.useFakeTimers` 仅在纯客户端状态机断言时。

### 3.2 用例清单（断言"前端真实调用 → 后端真实响应"一致）

**B1 · 工作区契约** — P0

| ID   | 用例                     | 关键断言                                                         |
| ---- | ------------------------ | ---------------------------------------------------------------- |
| B1.1 | `workspaceApi.list` 形状 | 返回 `{success,total,workspaces[]}`，每项含 `workspace_category` |
| B1.2 | create/delete 往返       | 真实建一个工作区 → list 含 → delete → list 不含                  |
| B1.3 | 过滤参数                 | `workspace_type`/`category` query 透传，结果与后端一致           |

**B2 · 知识库契约** — P0

| ID   | 用例                                | 关键断言                                                                                                 |
| ---- | ----------------------------------- | -------------------------------------------------------------------------------------------------------- |
| B2.1 | `knowledgeApi.listBases/createBase` | 形状 `{total,items}` / 返回 item                                                                         |
| B2.2 | upload + search                     | 上传文档 → `search(baseId,q,mode,topK)` 返回 `results`+`stats`，`source` 含 hybrid/vector/graph/fulltext |
| B2.3 | delete 清理一致性                   | `deleteDocument` 后 search 不再命中（与 A6.5 后端侧互补）                                                |
| B2.4 | deleteBase                          | 删库后 listBases 不含                                                                                    |

**B3 · LLM 契约 / config 分层** — P1

| ID   | 用例                      | 关键断言                                                              |
| ---- | ------------------------- | --------------------------------------------------------------------- |
| B3.1 | `llmApi.listGlobalModels` | 返回 `{availableLLMs[]}`，前端映射成 `source:local`                   |
| B3.2 | `listEffective`           | override-or-inherit 形状：effective 列表带 `source`/`user_overridden` |
| B3.3 | provider CRUD             | user/ws create/update/delete 路径与载荷正确                           |
| B3.4 | settings                  | `getSettings`/`listSettingsAll` 形状                                  |

**B4 · 模型合并（`store.fetchModels`）** — P0（近期 bug）

| ID   | 用例           | 关键断言                                                             |
| ---- | -------------- | -------------------------------------------------------------------- |
| B4.1 | 本地模型加载   | 后端 `/api/llms` 可达 → `models` 含本地项，`source:local`            |
| B4.2 | 网关不可达降级 | 网关 `listGatewayModels` 失败 → 不抛、官方为空、本地仍在、不强制登出 |
| B4.3 | 合并去重       | 本地与官方同 id → 本地优先                                           |

**B5 · 会话契约** — P1：list/create/save/delete 形状与后端一致。

**B6 · 聊天流式（真实 WS）—— 客户端最核心** — P0（需 LLM）

| ID   | 用例         | 关键断言                                                                                                                                            |
| ---- | ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| B6.1 | 发送→流式    | `wsClient.connect(ws)` + `sendMessage` → chat-store 收到 `stream_reasoning/content` → assistant 消息聚合 → `stream_complete` 后 `isStreaming=false` |
| B6.2 | 工具调用即显 | `stream_tool_call` → 工具在流式中可见                                                                                                               |
| B6.3 | 断线中断     | 服务端断开 → 活跃流 flush 为"已中断"，无 timer 泄漏                                                                                                 |

**B7 · 工具/技能契约** — P1：`tools` commands、`skills` list 形状与后端一致。

**B8 · HTTP 传输 live 行为** — P1

| ID   | 用例             | 关键断言                                                                |
| ---- | ---------------- | ----------------------------------------------------------------------- |
| B8.1 | ApiError 解析    | 打一个真实 404/422 → `apiErrorDetail` 提取后端 `{detail}`               |
| B8.2 | 超时             | `timeoutMs` 到点 → AbortError → "请求超时或网络中断"                    |
| B8.3 | 401 刷新（条件） | 需 support 系统；本地无则 skip。token 失效 → 刷新 → 重试成功 / 失败登出 |

---

## 4. 数据准备策略（两套）

- **Part A**：沿用 `conftest.py` 文件级范式 —— `tmp_path` 建真实工作区目录 + `.dawei/{settings,workspace,config}.json`，经 crud API 注册，yield id，finally 注销+删目录；知识库样本文档随建随删。模块级 `saved_index` fixture 备份/恢复 `workspaces.json`，保证不污染用户真实数据。
- **Part B**：HTTP 级 —— `beforeAll` 用 `workspaceApi.create` 建专属测试工作区（带可识别前缀如 `it-<ts>`），`afterAll` 删除；KB 同理。
- **隔离**：所有测试数据带统一前缀 + 时间戳，便于排查；CI 跑完无残留。

---

## 5. 实施分期

- **第 0 期 · 基础设施**：A 侧 `integration/conftest.py`（live 探活/工作区工厂/LLM gate/ws helper）+ 启动脚本；B 侧 vitest 配置 + `helpers/` + 启动/探活脚本。
- **第 1 期 · P0**：A1/A2/A3/A6 + B1/B2/B4/B6（工作区、会话、Agent/WS、知识库、模型合并）。
- **第 2 期 · P1**：A4/A5/A7 + B3/B5/B7/B8（工具、技能、LLM/config、契约细节）。
- **第 3 期 · P2**：A8 + 持续维护（后端契约变更即更新断言）。

---

## 6. 实现时需现场确认的点（非阻塞）

1. **工作区 CRUD 的精确路径**：`workspaces/crud.py` 的 create/delete 端点签名（设计阶段已确认路由文件，实现时读签名对齐载荷）。
2. **WS 连接 URL 与握手参数**：`/ws/{workspace_id}` 还是 query 参数；首条握手消息。
3. **LLM/embedding provider**：本地是否有可用 Ollama 模型（记忆提示此机缺 `qwen2.5:latest`）；据此定 `DAWEI_TEST_LLM` gate 与默认模型。
4. **鉴权**：dev 是否全程免鉴权；若否，如何拿测试 token（`INTEGRATION_TOKEN`）。
5. **vitest 运行隔离**：并入 `npm test` 还是独立 `test:integration`（独立更利于"后端没起就 skip"）。

---

## 7. 实施现状（2026-06-28，第 0+1 期 P0 已落地并活体验证）

### Part A · 后端核心（Python）— `engine/agent/tests/integration/`

- `conftest.py` — live 探活（不可达整组 autouse skip）、httpx async client、工作区工厂（`POST /api/workspaces/create-temp` + teardown）、`require_llm` gate、`WSRecorder`（懒导入 `websockets`，缺则 skip）、泄漏清理。
- `test_workspace_lifecycle.py`（A1）、`test_conversations.py`（A2）、`test_knowledge_lifecycle.py`（A6）、`test_agent_ws.py`（A3）。

### Part B · 客户端契约（TS）— `app/tests/integration/`

- `helpers/live.ts`（`probeLive` + `primeAuth` + `LLM_ENABLED`）、`workspace.contract.test.ts`（B1）、`knowledge.contract.test.ts`（B2）、`models-merge.integration.test.ts`（B4）。
- `vitest.config.integration.ts`（独立 config + 显式 `@→src` alias + 超时）、`.env.integration`（API/WS→localhost:8431，网关强制不可达以测降级）、`package.json: test:integration`。

### 运行方式

```bash
# ★ 推荐：一键脚本（仓库根目录）——自起 dawei 于 :8010（隔离 ~/.normnomos-integration，
#   不碰真实 ~/.normnomos），跑 Part A + Part B，结束自动停服务。复用已存在的 :8010 服务。
cd /d/ws/normnomos.com && bash run-integration-tests.sh
DAWEI_TEST_LLM=1 bash run-integration-tests.sh   # 顺带跑 LLM/embedding 用例（需 Ollama）

# —— 或手动分步 ——
# 起后端（端口 8010 = 既有 test_workspace_api.py 的约定端口；与整目录对齐）
cd engine/agent && .venv/Scripts/python.exe -m dawei.cli.dawei server start --port 8010 --host 127.0.0.1

# Part A（后端核心；整目录含既有 test_workspace_api.py，实测 41 passed / 5 skipped）
cd engine/agent && DAWEI_HOME=~/.normnomos-integration INTEGRATION_TARGET=http://localhost:8010 \
  .venv/Scripts/python.exe -m pytest tests/integration -q

# Part B（客户端契约；实测 23 passed / 3 skipped）—— 用 pnpm exec，勿用 npx
cd app && npm exec vitest run --mode integration --config vitest.config.integration.ts
```

> 端口统一 **8010**（既有 `test_workspace_api.py` 硬编码 8010 + CLAUDE.md 标准；8431 是 Tauri sidecar 端口，不用于独立集成测试）。服务端与测试进程须共用同一 `DAWEI_HOME`（脚本已处理），否则既有用例直接操纵 `workspaces.json` 会与服务端错配。

### 待办（第 2/3 期）

- ~~P1：A4 工具、A5 技能、A7 LLM/config；B3 LLM 契约、B5 会话、B7 工具/技能、B8 HTTP 传输（ApiError/超时/401）~~ ✅ 已完成（见 §8）
- ~~P2：A8 Memory/MCP/定时任务；B6 聊天流式（真 WS，需 LLM）~~ ✅ 已完成（见 §9）

---

## 9. 第 3 期 P2 已落地（2026-06-28）

### Part A（后端核心）`test_mcp_scheduled.py`（A8）— 4 pass

- MCP：`GET /api/workspaces/{id}/mcp-servers`（列表）+ `/mcp-servers/effective`（override-or-inherit 合并）。
- 定时任务：`GET /api/scheduled-tasks`（全局分页列表）+ 工作区作用域 create/list/delete 往返（`delay` + 远未来 `trigger_time`，不触发 LLM）。
- 注：独立 `/memory` 路由未在 server_app 挂载；memory 覆盖由 `test_workspace_lifecycle.py` 的 `/memory/effective` 承担。

### Part B（客户端契约）`chat-stream.e2e.test.ts`（B6）— 需 LLM，本地 skip

- `// @vitest-environment node`（jsdom 无真实 WebSocket；node 22 原生 WS）。
- 用真实 `WebSocketClient` 连活体后端，发 `USER_MESSAGE`，断言 `stream_content/reasoning` → `stream_complete`、无 `stream_error`。
- 工作区用裸 `fetch` 创建（node 无 localStorage，绕开 `request()`）；`RUN = LIVE && DAWEI_TEST_LLM=1`，否则整组 skip。

### 总览（全量活体）

| 套件   | 文件 | 实测             |
| ------ | ---- | ---------------- |
| Part A | 8    | 23 pass / 5 skip |
| Part B | 8    | 23 pass / 3 skip |

所有 skip 均为 LLM/embedding 后端 gate（此机无 Ollama，符合"不 mock"）。

### 已知（非本次引入，**已消解 2026-06-29**）

- 既有 `tests/integration/test_workspace_api.py`（非本方案所写）直接操纵 `DAWEI_HOME` 下 `workspaces.json` 并硬编码 `BASE_URL=http://localhost:8010`。此前与本方案的"临时 DAWEI_HOME + 端口 8431"冲突 → 整目录跑会 17 失败。
- **消解**：本方案端口统一改为 **8010**，并由 `run-integration-tests.sh` 保证服务端与测试进程共用同一持久隔离 home（`~/.normnomos-integration`）。现在 `pytest tests/integration/`（整目录）实测 **41 passed / 5 skipped**，既有用例一并绿。

---

## 8. 第 2 期 P1 已落地并活体验证（2026-06-28）

### Part A（后端核心）实测 18 passed / 5 skipped

- `test_tools.py`（A4）：`/api/tools/commands` 列表 + `/reload` + `/execute`（伪命令不 500）— 3 pass。
- `test_skills.py`（A5）：工作区技能 list/create/read-content/delete 往返 — 2 pass。
- `test_llm_config.py`（A7）：`/api/llms` 全局 + 工作区 `llm-providers/effective`、`llm-settings`、`llm-settings-all` — 4 pass。

### Part B（客户端契约）实测 23 passed / 2 skipped（7 文件全绿）

- `llm.contract.test.ts`（B3）：`listGlobalModels`/`listEffective`/`getSettings`/`listSettingsAll`。
- `conversation.contract.test.ts`（B5）：工作区作用域 create/list/get/delete。
- `tools-skills.contract.test.ts`（B7）：`/api/tools/commands`+`/reload` via `request`，`skillApi.list()`。
- `http-transport.contract.test.ts`（B8）：404→ApiError 解析后端 `{detail}`；`timeoutMs`→"请求超时或网络中断"；401 刷新 gated。

### 契约测试抓到的真实前端 bug（**已修 2026-06-28**）

- **`conversationApi.get(convId)` / `.delete(convId)` 打的是 `/api/conversations/{id}`，后端不存在该路由（404）**；后端只有工作区作用域 `/api/workspaces/{ws}/conversations/{id}`（`conversationApi.rename` 已正确用此路径）。
- **修复**：这两个方法为零调用点的死代码，且正确替代（`historyApi.getMessages`、`conversationApi.deleteScoped`，均工作区作用域）已存在 → 直接从 `src/lib/api/conversation.ts` 移除。B5 改为用真实客户端方法 `create/list/historyApi.getMessages/deleteScoped` 做回归（全绿）。单测 `api-client.test.ts` 8/8 不受影响。
- 附带发现并**已修 2026-06-28**：
  - `/api/skills/list` 不传 `workspace_id` 时旧的 `_auto_detect_workspace_id` 回退会调用不存在的 `WorkspaceManager.get_active_workspace` → 500。修复：`list_skills` 顶部加 `workspace_id` 必填守卫，缺失直接 `HTTPException(400)`，移除回退（`dawei/api/skills.py`）。回归用例 `test_skills_list_without_workspace_id_is_400` 守护。
  - `historyApi.getMessages` 的 TS 返回类型只声明顶层 `messages`，但后端实际嵌在 `conversation.messages` 下（运行时数据正确，类型不精确）。修复：更新类型声明为 `{success, conversation?:{messages?}, messages?, message?}`，与后端真实形状一致（`src/lib/api/conversation.ts`）；消费方 `chat-store` 本就兼容两种形状，无需改动。

### 落地踩到的坑（P1 增补）

- `/api/skills/list` 不传 `workspace_id` 时回退到不存在的 `get_active_workspace` → 500；A5 传 `workspace_id` 即正常（亦暴露后端一处健壮性缺口：应 400 而非 500）。
- `skillApi.list()`（前端）打的是市场技能 `/api/skills`，与后端工作区技能 `/api/skills/list` 是两套契约；本地无市场后端时按"解析为文档形状或干净 HTTP 错误"宽松断言。
