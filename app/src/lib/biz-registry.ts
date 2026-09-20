import type { ComponentType } from "react";
import type { SidebarGroup } from "./sidebar-config";

/**
 * 业务域注册表 —— 核心构建(开源形态)恒为空数组。
 *
 * enterprise assemble(scripts/assemble.mjs)时,本文件在合树(.assemble/)中被
 * 重写为各 biz 域 manifest 的聚合注入。核心源码(src/)不得 import 本表以外的
 * 任何 biz 模块(拆库方案 §5.2 F7 守卫)。
 */

// ── 工作区专属 ChatView 注册(任务路由按 workspaceType/name 分发)──
export interface WorkspaceChatEntry {
  /** 命中判断:workspaceType/name 二元组 */
  match: (ctx: { workspaceType?: string | null; name?: string | null }) => boolean;
  /** 命中后渲染的任务页 ChatView 组件 */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  component: ComponentType<any>;
  /** 命中时页面上下文 Dock 的 module 字段(不设则走默认 workspace-task) */
  agentModule?: string;
  /** task.title 为空时摘要文案的 i18n key(不设则回退 workspace.name) */
  agentSummaryKey?: string;
}

// ── 工作区空状态注册(chat-view 空消息时的模块化引导界面)──
export interface WorkspaceEmptyStateConfig {
  /** Icon name from lucide-react (resolved at render time) */
  icon: string;
  title: string;
  description: string;
  primaryAction: string;
  primaryIsUpload?: boolean;
  secondaryAction?: string;
  secondaryActionPrompt?: string;
}
export interface WorkspaceEmptyStateEntry {
  /** workspaceType === prefix,或 workspace.name 以 prefix- 开头时命中 */
  prefix: string;
  config: WorkspaceEmptyStateConfig;
}

// ── 工作区空状态组件注册(组件型;chat-view 空消息引导界面的整组件形态)──
export interface WorkspaceEmptyComponentEntry {
  /** 命中判断:workspaceType/name 二元组 */
  match: (ctx: { workspaceType?: string | null; name?: string | null }) => boolean;
  /** 命中后渲染的空状态组件(onInsert 向输入框注入快捷指令) */
  component: ComponentType<{ onInsert: (text: string) => void }>;
}

// ── Agent fleet 状态下沉注册(monitoring-ws 的 WS 消息 → 域内 store)──
export interface AgentStatusSinkEntry {
  /** WS 消息 type(如 "market_agent_status";契约 { data: { expert_id, status, last_action? } }) */
  messageType: string;
  /** 命中时调用域内 store 的 setAgentStatus(expertId, status, lastAction?) */
  setAgentStatus: (expertId: string, status: string, lastAction?: string) => void;
}

// ── sidebar 分组上下文行注册(产品/品牌全局切换等;按 group.key 挂载)──
export interface SidebarContextSelectEntry {
  /** 挂载目标 sidebar 分组 key */
  groupKey: string;
  /** 行标签:静态串或取值函数(支持 i18n 动态解析) */
  label: string | (() => string);
  /** 上下文选择组件 */
  component: ComponentType;
}

// ── 身份切换重置钩子注册(reset-stores 逐个 try/catch 调用)──
export interface IdentityResetHookEntry {
  /** 重置域内 tenant-scoped store(如 social brand 上下文);异常由调用方吞掉 */
  reset: () => void;
}

// ── sidebar 徽标计数注册(取数/轮询逻辑在域内 hook;core 侧只做合并)──
export interface SidebarCountHookEntry {
  /** 返回本域计数(key = sidebar item countKey;如 activeCases/pendingLeads) */
  useCounts: () => Record<string, number>;
}

// ── 根布局浮动 Dock 注册(如 FirmAgentDock;按模块键命中,__root 统一 lazy 化)──
export interface RootDockEntry {
  /** 模块键命中判断(moduleKey = routeToModuleKey(path)) */
  match: (moduleKey: string) => boolean;
  /** 动态加载 Dock 组件(保持 chunk 分包;返回 { default: ComponentType }) */
  load: () => Promise<{ default: ComponentType }>;
}

export const BIZ_SIDEBAR_GROUPS: SidebarGroup[] = [];

export const BIZ_TASK_CHAT_VIEWS: WorkspaceChatEntry[] = [];

export const BIZ_WORKSPACE_EMPTY_STATES: WorkspaceEmptyStateEntry[] = [];

export const BIZ_WORKSPACE_EMPTY_COMPONENTS: WorkspaceEmptyComponentEntry[] = [];

export const BIZ_AGENT_STATUS_SINKS: AgentStatusSinkEntry[] = [];

export const BIZ_SIDEBAR_CONTEXT_SELECTS: SidebarContextSelectEntry[] = [];

export const BIZ_IDENTITY_RESET_HOOKS: IdentityResetHookEntry[] = [];

export const BIZ_SIDEBAR_COUNT_HOOKS: SidebarCountHookEntry[] = [];

export const BIZ_ROOT_DOCKS: RootDockEntry[] = [];
