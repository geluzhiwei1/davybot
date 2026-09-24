/**
 * Sidebar Configuration — Single Source of Truth for sidebar rendering.
 *
 * 每個 item 的 `key` 必須與後端 `Module.key` 一致（見
 * `nn-user-system/support_system/models_beanie/module_documents.py` 的 SEED_MODULES）。
 *
 * 過濾邏輯見 `app-sidebar.tsx` 的 `filterItems()`：根據當前用戶的
 * `effective_modules`（來自 `/auth/me`）對 item.key 過濾；
 * null = 無模組管控（自包含 server/tui 本地態）→ 僅渲染 `core: true` 分組（F2）。
 */

import type { TFunction } from "i18next";
import { BIZ_SIDEBAR_GROUPS } from "./biz-registry";

export type SidebarBadge = "alpha" | "beta" | "ai";
export type CountVariant = "count" | "alert";

export interface SidebarItem {
  /**與後端 Module.key 對齊 — 點分式 `{group}.{slug}` */
  key: string;
  title: string;
  route: string;
  icon: string;
  badge?: SidebarBadge;
  /**
   * 動態 count 對應 useSidebarCounts 的哪個字段。
   * 例如 "activeCases" → sidebarCounts.activeCases
   */
  countKey?: string;
  countVariant?: CountVariant;
  /**標記為隱藏的模塊（不渲染） */
  hidden?: boolean;
  /**
   * 前端自治入口(A7/可用性升級 v1.5):該頁未在後端 SEED_MODULES 播種,
   * 模塊管控無從談起 —— 渲染與路由守衛均繞過 effective_modules 過濾
   * (仍受 hidden 控制)。後端播種模塊鍵後應移除此標記,回歸統一管控。
   */
  localOnly?: boolean;
  /**
   * 僅精確匹配才算選中(佈局索引頁專用):route 同時是子頁前綴
   * (如 /social、/normflow)時,默認前綴匹配會讓它在全部子頁保持選中。
   */
  exact?: boolean;
}

export interface SidebarSubgroup {
  label: string;
  items: SidebarItem[];
}

export interface SidebarGroup {
  key: string;
  title: string;
  order: number;
  badge?: SidebarBadge;
  items?: SidebarItem[];
  /**子分组（如 智能律所的 案件/合同/財務/流程/報表/行政/更多） */
  subgroups?: SidebarSubgroup[];
  /**
   * F2: 核心分组标记 —— 引擎自包含能力(首页/资源市场/系统)。
   * effectiveModules == null(無模組管控/自包含本地態)時僅渲染核心分組;
   * 業務分組須連賬號體系/業務服務,不在開源自包含形態出現。
   */
  core?: boolean;
}

/**
 * 核心分组配置 — 与后端 SEED_MODULES 对齐;业务域(sanctions 等)经
 * biz-registry 注入(见各 biz/<domain>/manifest.ts)。
 *
 * 顺序按 order 字段排序:首頁 → [業務域注入] → 合規智能體 → 智能律所 → …
 */
const CORE_SIDEBAR_GROUPS: SidebarGroup[] = [
  // ── 首頁（常駐 pinned;核心）──
  {
    key: "home",
    title: "首页",
    order: 0,
    core: true,
    items: [{ key: "home", title: "首页", route: "/", icon: "home" }],
  },

  // ── 系統（部分常駐 pinned;核心）──
  {
    key: "system",
    title: "系统",
    order: 80,
    core: true,
    items: [
      { key: "system.workspaces", title: "我的工作区", route: "/workspaces", icon: "folder-open" },
      { key: "system.audit", title: "操作审计", route: "/audit", icon: "scroll-text" },
      { key: "system.memory", title: "记忆管理", route: "/memory", icon: "lightbulb" },
      // 用户设置(原抽屉改为 tab 页卡,布局对齐记忆管理)
      {
        key: "system.user-settings",
        title: "用户设置",
        route: "/user-settings",
        icon: "shield",
      },
    ],
  },
];

/** 完整 sidebar 配置 — 核心 + 业务(biz-registry 注入;核心构建 = 空业务)。按 order 排序。 */
export const SIDEBAR_CONFIG: SidebarGroup[] = [...CORE_SIDEBAR_GROUPS, ...BIZ_SIDEBAR_GROUPS].sort(
  (a, b) => a.order - b.order,
);

/**
 * 导航标题渲染期 i18n 解析:按模块键查 commonUi 命名空间 `sidebar.nav.<key>`,
 * 缺键回退配置原文(FAST FAIL 不挡渲染 —— zh 不配键即显示 manifest 原文,英文翻
 * 译集中在 en-US/commonUi.ts 的 sidebar.nav 段)。key 为空(非模块项)直接回退。
 */
export function navTitle(t: TFunction, key: string | null | undefined, fallback: string): string {
  return key ? t(`sidebar.nav.${key}`, { defaultValue: fallback, ns: "commonUi" }) : fallback;
}

/**
 * 子分组标签渲染期 i18n 解析:子分组无模块键,按 `sidebar.nav.<groupKey>.<label>`
 * 查询(叶子为原文标签,flat key);缺键回退原文,机制同 navTitle。
 */
export function navSubgroupLabel(t: TFunction, groupKey: string, label: string): string {
  return t(`sidebar.nav.${groupKey}.${label}`, { defaultValue: label, ns: "commonUi" });
}

/**
 * F2: 模块键是否属于核心分组（首页/资源市场/系统）。
 * effectiveModules == null 时路由守卫仅放行核心模块键。
 */
export function isCoreModuleKey(key: string): boolean {
  const groupKey = key.split(".")[0];
  return SIDEBAR_CONFIG.some((g) => g.key === groupKey && g.core === true);
}

/**
 * 反查：路由 path → module key（用於路由守衛）。
 *
 * 支持前綴匹配：`/normflow/contracts/123` → `smart-law-firm.contracts`。
 *
 * @returns 匹配的 module key；未匹配返回 null。
 */
export function routeToModuleKey(path: string): string | null {
  // 特殊：根路徑 → home
  if (path === "/" || path === "") return "home";

  // 收集所有 item 的 {route, key}（含子分组內的）。
  // localOnly 頁不入表:後端未播種模塊鍵,模塊守衛按「非業務路由」放行
  // (與歷史直鏈行為一致,避免加鍵反而封死 URL 直達)。
  const all: Array<{ route: string; key: string }> = [];
  for (const g of SIDEBAR_CONFIG) {
    if (g.items)
      for (const it of g.items) if (!it.localOnly) all.push({ route: it.route, key: it.key });
    if (g.subgroups)
      for (const sg of g.subgroups)
        for (const it of sg.items) if (!it.localOnly) all.push({ route: it.route, key: it.key });
  }

  // 按路由長度降序，避免 `/normflow` 蓋過 `/normflow/contracts`
  all.sort((a, b) => b.route.length - a.route.length);

  for (const { route, key } of all) {
    // 跳過虛擬路由（抽屜）
    if (route.startsWith("/__drawer_")) continue;
    if (path === route || path.startsWith(route + "/")) return key;
  }
  return null;
}

/**
 * 反查：route 是否為「僅精確匹配」項（佈局索引頁）。
 * 固定釘（pinned store）只存 4 個欄位，渲染時以此從配置取回 exact 語義。
 */
export function isExactRoute(route: string): boolean {
  for (const g of SIDEBAR_CONFIG) {
    if (g.items) for (const it of g.items) if (it.route === route && it.exact) return true;
    if (g.subgroups)
      for (const sg of g.subgroups)
        for (const it of sg.items) if (it.route === route && it.exact) return true;
  }
  return false;
}

/**
 * 獲取所有可見（非 hidden）item 的 key — 用於管理界面 / 路由守衛兜底。
 */
export function getAllVisibleItemKeys(): string[] {
  const keys: string[] = [];
  for (const g of SIDEBAR_CONFIG) {
    if (g.items) for (const it of g.items) if (!it.hidden) keys.push(it.key);
    if (g.subgroups)
      for (const sg of g.subgroups) for (const it of sg.items) if (!it.hidden) keys.push(it.key);
  }
  return keys;
}
