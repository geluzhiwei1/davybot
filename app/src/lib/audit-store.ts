/**
 * Audit store — 操作审计日志
 * 记录用户在应用中的关键操作，持久化到 localStorage，保留最近 1000 条。
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

/** 审计操作类型 */
export type AuditAction =
  | "page_view"
  | "task_create"
  | "task_delete"
  | "task_rename"
  | "workspace_create"
  | "workspace_delete"
  | "workspace_rename"
  | "search"
  | "export"
  | "login"
  | "logout"
  | "sanctions_search"
  | "knowledge_upload"
  | "knowledge_delete"
  | "settings_change"
  | "chat_message";

/** 审计日志条目 */
export interface AuditEntry {
  /** 唯一 ID */
  id: string;
  /** 操作类型 */
  action: AuditAction;
  /** 操作目标（页面路径、任务名称等） */
  target: string;
  /** 补充详情 */
  detail?: string;
  /** ISO 时间戳 */
  timestamp: string;
}

/** 操作类型 → 中文标签 */
export const AUDIT_ACTION_LABELS: Record<AuditAction, string> = {
  page_view: "页面访问",
  task_create: "创建任务",
  task_delete: "删除任务",
  task_rename: "重命名任务",
  workspace_create: "创建工作区",
  workspace_delete: "删除工作区",
  workspace_rename: "重命名工作区",
  search: "搜索",
  export: "导出",
  login: "登录",
  logout: "退出登录",
  sanctions_search: "制裁筛查",
  knowledge_upload: "上传知识",
  knowledge_delete: "删除知识",
  settings_change: "修改设置",
  chat_message: "对话消息",
};

const MAX_ENTRIES = 1000;

interface AuditState {
  entries: AuditEntry[];

  /** 添加一条审计记录 */
  addAuditEntry: (entry: Omit<AuditEntry, "id" | "timestamp">) => void;
  /** 清空所有审计记录 */
  clearAuditEntries: () => void;
}

export const useAuditStore = create<AuditState>()(
  persist(
    (set) => ({
      entries: [],

      addAuditEntry: (entry) =>
        set((state) => {
          const newEntry: AuditEntry = {
            ...entry,
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
          };
          const entries = [newEntry, ...state.entries].slice(0, MAX_ENTRIES);
          return { entries };
        }),

      clearAuditEntries: () => set({ entries: [] }),
    }),
    {
      name: "normnomos-audit-log",
    },
  ),
);
