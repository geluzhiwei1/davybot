# 单代码库双目标架构 (Single Codebase, Dual Target)

> 目标: 一份前端代码, 同时产出 **Desktop (Tauri)** 和 **SaaS (Web)** 两个产品形态。

## 1. 背景与产品定义

NormNomos 前端 (`app/`) 同时支撑两个 SKU:

| 维度     | Desktop (Tauri)                      | SaaS (Web)      |
| -------- | ------------------------------------ | --------------- |
| 账号     | 必须登录                             | 必须登录        |
| 功能集   | 完全对等                             | 完全对等        |
| 代码执行 | 用户电脑 + 本地 docker/podman 沙箱   | 云端独立沙箱    |
| 文件驻留 | **所有文件不上传**, 留在本地磁盘     | 上传到云端存储  |
| 后端     | dawei sidecar (`localhost:动态端口`) | 远程 dawei 服务 |

**核心约束**: 只维护一份前端代码。

## 2. 现状分析

### 2.1 已有的双目标基础设施

项目已具备双入口雏形:

| 资产      | Web                  | Desktop                |
| --------- | -------------------- | ---------------------- |
| 入口 HTML | `index.html`         | `index.tauri.html`     |
| Vite 配置 | `vite.config.ts`     | `vite.config.tauri.ts` |
| 入口脚本  | `src/main.tauri.tsx` | 同一个                 |
| 路由基址  | `/app-ui/`           | `/`                    |
| 构建产物  | `dist/`              | `src-tauri/ui-dist/`   |
| 后端连接  | 远程 API (proxy)     | dawei sidecar          |

### 2.2 发现: 两条正交的轴 (且 B 轴空转)

代码里存在两条**互相独立**的运行时分支:

**轴 A — desktop vs web (生效中)**

- 检测: `"__TAURI__" in window`
- 用途: sidecar 端口解析、自动更新、启动遮罩、版本号读取

**轴 B — lite vs full (空转中, 死代码)**

- 检测: `window.__APP_MODE` + `?full=2084` URL 后门
- 关键发现:
  - `index.html:12` 和 `index.tauri.html:12` **都注入** `__APP_MODE = 'lite'`
  - `src/lib/sidebar-config.ts` 全文 288 行, **没有任何 item 设置 `modes: ["full"]`**
  - → 切换 lite/full **不改变任何菜单可见性**, 这条轴完全空转

### 2.3 业务决策结论

两个 SKU 的差异**不在功能可见性**, 而在**执行环境与数据驻留**。因此:

- 轴 B (lite/full) 应当**整个删除** — 它是基于"砍功能做档位"的旧思路, 与现行策略冲突
- 真正需要的是**执行后端与文件操作的平台抽象**

## 3. 平台抽象设计

### 3.1 构建期常量 (替代散落的运行时检测)

Vite `define` 注入, 可被 rollup tree-shake:

```ts
// vite.config.ts (web)
define: {
  __APP_TARGET__: JSON.stringify("web");
}

// vite.config.tauri.ts (desktop)
define: {
  __APP_TARGET__: JSON.stringify("desktop");
}
```

类型声明:

```ts
// src/lib/platform/env.d.ts
declare const __APP_TARGET__: "web" | "desktop";
export const IS_DESKTOP = __APP_TARGET__ === "desktop";
export const IS_WEB = !IS_DESKTOP;
```

**为什么用构建期常量而不是运行时 `isTauri()`**:
当前 4 处 `isTauri()` 都是 `if (!isTauri()) return` 形式, web 包里这些代码虽然不执行但仍被打包。
改用 `if (!IS_DESKTOP) return` 后, rollup 可整段 dead-code eliminate。
对于文件操作这种**两端都有实质代码**的场景, tree-shaking 尤其关键。

### 3.2 统一 platform 模块

收敛当前 4 处重复的 `isTauri()` 定义:

```
src/lib/platform.ts        # IS_DESKTOP / IS_WEB / isTauri() — 统一出口
src/lib/platform/files.ts  # selectFiles() + SelectedFile 类型
src/vite-env.d.ts          # __APP_TARGET__ 类型声明
```

> **实现说明**: 原设计提案为 `src/lib/platform/` 目录含 `index.ts`/`env.d.ts`/`backend.ts`/`desktop.ts`。
> 实际落地简化为两个文件 — `platform.ts` (常量+运行时检测) + `platform/files.ts` (文件选择抽象)。
> 后端连接 (`env.ts`) 已是正确出口无需包装, 桌面专属逻辑 (update/sidecar/overlay) 各自 `import("@tauri-apps/...")` 动态加载, 不需要聚合层。

### 3.3 文件操作抽象 (核心差异点)

前端唯一需要显著分支的地方。已实现三层抽象:

**① 选择层** — `src/lib/platform/files.ts`:

```ts
export interface SelectedFile {
  name: string;
  size: number;
  localPath?: string; // desktop only — Tauri dialog 返回的磁盘路径
  file?: File; // web only — <input type="file"> 的浏览器 File 对象
}

export async function selectFiles(opts?: SelectFilesOptions): Promise<SelectedFile[]>;
// desktop → @tauri-apps/plugin-dialog open() 返回路径
// web     → 隐藏 <input type="file"> 返回 File 对象
```

**② API 层** — `src/lib/api/file.ts`:

```ts
uploadByPath(workspaceId, sourcePath, destPath?)  // POST JSON → sidecar shutil.copy2()
upload(workspaceId, file: File, destPath?)          // POST FormData → multipart upload
uploadSmart(workspaceId, file: SelectedFile, destPath?)
  // 有 localPath → uploadByPath (零拷贝, desktop 专用)
  // 有 file      → upload (FormData, web 通用)
```

**③ 后端层** — `agent/dawei/api/workspaces/files.py`:

- `POST /files/upload` — FormData multipart (已有)
- `POST /files/upload-by-path` — JSON `{source_path, parent_path}` → `shutil.copy2()` (新增)

**已迁移的上传入口** (全部完成):

- `src/lib/workspace-files-store.ts` — `uploadFiles()` 接受 `SelectedFile[]`, 内部调 `uploadSmart()`
- `src/components/chat-view.tsx` — `handleUpload` 用 `selectFiles()` + store
- `src/components/workspace-panel.tsx` — 上传按钮 + 拖拽都用新接口
- `src/components/chat/file-upload-dialog.tsx` — 对话框上传用 `uploadSmart()`
- `src/components/compliance/material-uploader.tsx` — `selectFiles({ wantFile: true })` + `selectedFileToFile()`
- `src/components/compliance-form.tsx` — 文件选择用 `selectFiles()` (仅存文件名)
- `src/components/smart-firm/PartyImportDialog.tsx` — CSV 导入用 `selectFiles({ wantFile: true })`
- `src/routes/knowledge.tsx` — 知识库文档上传用 `selectFiles({ wantFile: true })`
- `src/routes/sanctions.monitoring.tsx` — 批量筛查 CSV 用 `selectFiles({ wantFile: true })`

> **`wantFile` 模式**: 垂直业务 API (材料上传/CSV 导入/知识库索引等) 需要传入 `File` 对象做 FormData。
> 在 desktop 上, `selectFiles({ wantFile: true })` 使用 `<input type="file">` (Tauri webview 原生支持)
> 而非 Tauri dialog, 以获取 File 对象。
> `selectedFileToFile()` 辅助函数从 `SelectedFile` 中提取 File。

### 3.4 后端连接 (已抽好, 无需改)

`src/lib/env.ts` 已经是正确的单一出口:

- `getApiBaseUrl()` / `getWsBaseUrl()` — sidecar 端口运行时注入
- `setSidecarBase(port)` — desktop 专用
- `getApiBaseUrl()` 被 14 处调用, 全部走这个出口 ✓

## 4. 差异点完整清单

### 4.1 桌面专属逻辑 (4 处重复 `isTauri()`, 待收敛)

| 位置                                                   | 用途                                                          | 失效行为                  |
| ------------------------------------------------------ | ------------------------------------------------------------- | ------------------------- |
| `src/main.tauri.tsx:11`                                | sidecar 端口解析                                              | web 静默 return           |
| `src/hooks/use-update.ts:18`                           | 自动更新 (4h 轮询, check_update, download_and_install_update) | web 静默 return           |
| `src/hooks/use-sidecar.ts:23`                          | sidecar 健康探测, 订阅 sidecar-status / sidecar-log 事件      | web 静默 return           |
| `src/components/sidecar-overlay.tsx:17`                | 启动中/失败的全屏遮罩                                         | web 渲染 null             |
| `src/components/drawers/user-settings-drawer.tsx:1721` | "关于"页读 getVersion()                                       | web fallback `"1.0-beta"` |

Tauri API 调用 (全动态 `import()`, 不污染 web 包, 这点做得好):

- `@tauri-apps/api/core` — `invoke("get_sidecar_port" / "restart_app" / "reveal_sidecar_log" / "check_update" / "download_and_install_update")`
- `@tauri-apps/api/event` — `listen("update-available" / "update-ready" / "sidecar-status" / "sidecar-log")`
- `@tauri-apps/api/app` — `getVersion()`

### 4.2 后端连接 (已统一)

`src/lib/env.ts` 是单一出口, 14 处调用点全部走 `getApiBaseUrl()`。

### 4.3 构建配置差异

| 维度           | Web (`vite.config.ts`)                                                        | Desktop (`vite.config.tauri.ts`) |
| -------------- | ----------------------------------------------------------------------------- | -------------------------------- |
| 入口 HTML      | `index.html`                                                                  | `index.tauri.html`               |
| `base`         | `/app-ui/`                                                                    | (默认 `/`)                       |
| 输出           | `dist/`                                                                       | `src-tauri/ui-dist/`             |
| SPA fallback   | `spaDevIndex()` + 旧 `/legalbot-ui` 重定向                                    | `tauriDevIndex()`                |
| HTML 改名插件  | 无                                                                            | `tauriHtmlRename()`              |
| proxy          | 6 条 (`/api` `/ws` `/sanctions` `/kb-searcher` `/nn-kb-searcher` `/normflow`) | 无                               |
| `manualChunks` | 相同                                                                          | 相同                             |

### 4.4 npm scripts

当前无显式 `build:web` / `build:desktop` 命名, 区分靠 `tauri` CLI 隐式选取 `vite.config.tauri.ts`。建议补齐:

```json
{
  "build:web": "vite build",
  "build:desktop": "vite build --config vite.config.tauri.ts",
  "dev:web": "vite dev",
  "dev:desktop": "tauri dev"
}
```

### 4.5 构建脚本对照

两个 SKU 各有一个端到端构建脚本, 位于 `project/scripts/`:

| 脚本               | 产物                                             | 后端连接                       | 沙箱               |
| ------------------ | ------------------------------------------------ | ------------------------------ | ------------------ |
| `build-desktop.sh` | Tauri 安装包 (.deb/.dmg/.exe)                    | sidecar (`localhost:动态端口`) | 本地 docker/podman |
| `build-saas.sh`    | dawei sidecar binary (`dist/dawei`, PyInstaller) | 同一个 binary, 部署为服务      | CubeSandbox 云沙箱 |

**关键**: SaaS 和 desktop **共用同一个 PyInstaller sidecar binary** (`engine/agent/dist/dawei`)。两个脚本都调用 `build-binary.py --collect-all dawei` 生成它。区别只在后续:

- desktop 把 binary 打进 Tauri 安装包
- SaaS 直接 scp binary 到服务器, 跑成 systemd 服务

前端在 server 模式下被**铺平**到 `agent/dawei/frontend/{index.html, assets/}`(不能有 `dist/` 子目录, `server_app.py` 读的是 `frontend/index.html`), 由 `--collect-all dawei` 自动打进 binary。

`build-saas.sh` 支持两种部署形态:

- **`--mode server`** (默认): 前端铺平进 `agent/dawei/frontend/`, sidecar 同源托管 `/app-ui/`。用 `.env.server`。即 `demo.normnomos.com` 的部署方式。
- **`--mode production`**: 前端独立部署到 nginx/CDN, API 指向远程 (`api.normnomos.com`)。用 `.env.production`。前端不打进 binary。

```bash
# SaaS 完整构建 (server-embedded, 和 demo 一致)
bash project/scripts/build-saas.sh

# SaaS 独立部署
bash project/scripts/build-saas.sh --mode production

# 仅前端 / 仅 sidecar
bash project/scripts/build-saas.sh frontend
bash project/scripts/build-saas.sh sidecar
```

## 5. 可删除的死代码 (lite/full 整条轴)

清理后可移除:

| 位置                                                    | 内容                                                                                                         |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `index.html:12`                                         | `<script>window.__APP_MODE = 'lite';</script>`                                                               |
| `index.tauri.html:12`                                   | 同上                                                                                                         |
| `src/router.tsx:14-55`                                  | `AppMode` 类型, `FULL_UNLOCK_TOKEN`, `FULL_UNLOCK_KEY`, `readFullUnlock()`, `isFullUnlock()`, `getAppMode()` |
| `src/components/app-sidebar.tsx:101, 460-462, 185, 263` | `isLite` / `showHidden` 过滤逻辑                                                                             |
| `src/lib/sidebar-config.ts:13, 28, 44`                  | `SidebarMode` 类型, `modes?` 字段                                                                            |

`?full=2084` 后门随之消失 — 如果 dev 仍然需要"显示全部模块", 改用后端 `effective_modules` 返回全量即可 (本就是设计意图, 见 `sidebar-config.ts:8` 注释)。

## 6. 迁移路径

每阶段独立可交付, 建议顺序:

### Phase 1: 清理死代码 ✅ 已完成

- 删除 `__APP_MODE` / lite/full 整条轴 (见 §5)
- 验证 sidebar 仍正常渲染所有模块
- 结果: 5 文件修改, TS 错误 48 → 47 (零新增)

### Phase 2: 平台抽象层 ✅ 已完成

- 新建 `src/lib/platform.ts` (IS_DESKTOP / IS_WEB / isTauri)
- 两个 vite config 注入 `__APP_TARGET__`
- 收敛 7 处 isTauri()/inline check → `IS_DESKTOP`
- 补齐 `build:web` / `build:desktop` / `dev:web` / `dev:desktop` scripts
- 结果: 7 文件重构, TS 错误 47 (零新增)

### Phase 3: 文件操作抽象 ✅ 已完成

- 新建 `src/lib/platform/files.ts` (`selectFiles()` + `SelectedFile`)
- `file.ts` 加 `uploadByPath()` + `uploadSmart()`
- 后端加 `POST /files/upload-by-path` endpoint
- 改造 4 个上传入口: store, chat-view, workspace-panel, file-upload-dialog
- 结果: TS 错误 47 (零新增)

### Phase 4: 沙箱状态 UI (已有基础设施)

沙箱模块已完整存在, 无需新建:

| 层    | 文件                                       | 说明                                                                 |
| ----- | ------------------------------------------ | -------------------------------------------------------------------- |
| 类型  | `src/lib/types/sandbox.ts`                 | ProviderType, SandboxCapabilities, QuotaUsage 等                     |
| API   | `src/lib/api/sandbox.ts`                   | providers, capabilities, quota, test-connection, **deployment-mode** |
| Store | `src/lib/stores/sandbox-store.ts`          | 持久化 selectedProvider, 管理 status/quota                           |
| UI    | `src/components/sandbox/*.tsx`             | 10 个组件: status-panel, provider-selector, quota-indicator 等       |
| 路由  | `src/routes/settings.security.sandbox.tsx` | 设置页沙箱配置                                                       |

**平台感知**: 后端 `GET /api/system/deployment-mode` 返回 `{mode: "local" | "saas"}`,
前端据此 (而非 `IS_DESKTOP`) 判断沙箱类型 — 设计正确, 因为 sidecar 在 desktop 和 SaaS
跑的是同一个 binary, 只有后端知道自己的运行环境。

支持 Provider: `docker` / `podman` / `e2b` (CubeSandbox) / `subprocess` / `auto`

## 7. 决策记录

**Q: 为什么不拆 monorepo (`apps/desktop` + `apps/web` + `packages/shared`)?**
A: 当前差异点 < 10 处, 绝大部分代码共享。拆仓库的 setup/心智成本远大于收益。平台抽象层已足够覆盖。

**触发拆分的阈值**: 若 desktop/web 差异超过 30% 代码路径, 或导航结构完全分叉, 再考虑拆。

**Q: 既然功能对等, 为什么 `?full=2084` 后门要删?**
A: 它是"按档位砍功能"旧思路的遗留, 与现行"两端功能完全对等"策略冲突。保留会误导后续维护者以为 lite/full 仍在生效。

**Q: desktop 也要登录, 那 auth store 两端完全一样?**
A: 是的。Auth 流程两端共享, 无需分支。差异只在登录后的**数据流向** (desktop 文件留本地, SaaS 上云), 那是 platform/files.ts 的事。
