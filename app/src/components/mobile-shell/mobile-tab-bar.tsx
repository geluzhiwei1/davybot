/**
 * MobileTabBar — 移动端底部导航(移动端可用性提升方案 Phase 2 / L3 移动外壳)。
 *
 * 数据源唯一:`sidebar-config.ts` SSOT × auth-store effectiveModules,
 * 不维护第二份导航配置。固定入口按优先级取:
 *   首页 → smart-law-firm.workbench(工作台)→ social.approvals(审批中心)→ 更多
 * 缺失的槽位按配置顺序回填(模块未启用时不渲染对应入口);
 * 「更多」打开 AppSidebar 的移动端 Sheet(完整侧栏:分组/固定项/用户菜单/主题语言)。
 *
 * 桌面端零影响:根节点 `md:hidden`,≥768px 不渲染不占位。
 * 点击行为与桌面侧栏一致:openTab(page tab)+ navigate(tabs-store 状态共用)。
 */
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Home, Menu } from "lucide-react";
import { SIDEBAR_CONFIG, isExactRoute, type SidebarItem } from "@/lib/sidebar-config";
import { resolveIcon } from "@/lib/icon-map";
import { useTabsStore } from "@/lib/tabs-store";
import { useAuthStore } from "@/lib/auth-store";
import { cn } from "@/lib/utils";
import { useSidebar } from "@/components/ui/sidebar";

/** 固定入口优先级(与方案 P0 场景对应:工作台/审批);缺失按配置顺序回填 */
const MOBILE_PRIORITY_KEYS = ["smart-law-firm.workbench", "social.approvals"];

/** 与 app-sidebar.tsx filterItems 同规则:hidden 隐藏;模块管控过滤;localOnly 豁免 */
function filterItems(items: SidebarItem[], enabledKeys: Set<string> | null): SidebarItem[] {
  return items.filter((it) => {
    if (it.hidden) return false;
    if (enabledKeys !== null && !it.localOnly && !enabledKeys.has(it.key)) return false;
    return true;
  });
}

/** 与 app-sidebar.tsx isRouteActive 同规则(前缀匹配;exact 仅精确) */
function isRouteActive(path: string, route: string): boolean {
  if (route === "/") return path === "/";
  const exact = isExactRoute(route);
  if (exact) return path === route;
  return path === route || path.startsWith(route + "/");
}

interface NavEntry {
  key: string;
  title: string;
  route: string;
  icon: string;
}

export function MobileTabBar() {
  const { t } = useTranslation("commonUi");
  const navigate = useNavigate();
  const openTab = useTabsStore((s) => s.openTab);
  const effectiveModules = useAuthStore((s) => s.effectiveModules);
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  // 「更多」直接打开 AppSidebar 移动端 Sheet(本组件在 SidebarProvider 内,直连 openMobile)
  const { openMobile, setOpenMobile } = useSidebar();

  const enabledKeys = effectiveModules ? new Set(effectiveModules) : null;
  // F2: 無模組管控(自包含本地態) → 僅核心分組(与 app-sidebar 同規則)
  const coreOnly = effectiveModules === null;

  // 分组展开(顶层 + 子分组),供「更多」抽屉与回填使用
  const groups = SIDEBAR_CONFIG.filter((g) => g.key !== "home" && (!coreOnly || g.core))
    .map((g) => ({
      title: g.title,
      items: [
        ...(g.items ? filterItems(g.items, enabledKeys) : []),
        ...(g.subgroups ?? []).flatMap((sg) => filterItems(sg.items, enabledKeys)),
      ],
    }))
    .filter((g) => g.items.length > 0);

  const flat = groups.flatMap((g) => g.items);

  // 快捷入口:首页 + 优先级项(存在即取)+ 配置顺序回填,最多 3 个
  const quick: NavEntry[] = [{ key: "home", title: t("sidebar.home"), route: "/", icon: "home" }];
  const used = new Set<string>(["home"]);
  for (const key of MOBILE_PRIORITY_KEYS) {
    const hit = flat.find((it) => it.key === key);
    if (hit) {
      quick.push({ key: hit.key, title: hit.title, route: hit.route, icon: hit.icon });
      used.add(hit.key);
    }
  }
  for (const it of flat) {
    if (quick.length >= 4) break; // 首页 + 2 个槽位;第 4 格固定为「更多」
    if (used.has(it.key)) continue;
    quick.push({ key: it.key, title: it.title, route: it.route, icon: it.icon });
    used.add(it.key);
  }

  const go = (entry: NavEntry) => {
    openTab({
      key: entry.route,
      title: entry.title,
      type: "page",
      route: entry.route,
      icon: entry.icon,
    });
    navigate({ to: entry.route } as Parameters<typeof navigate>[0]);
  };

  // 当前路由不在快捷入口但在可见模块内 → 「更多」高亮(当前模块提示)
  const quickActive = quick.some((e) => isRouteActive(pathname, e.route));
  const moreActive = !quickActive && flat.some((it) => isRouteActive(pathname, it.route));

  return (
    <>
      <nav
        aria-label={t("mobileNav.more")}
        className="md:hidden flex items-stretch border-t border-border bg-background/95 backdrop-blur shrink-0 pb-[env(safe-area-inset-bottom)]"
      >
        {quick.map((entry) => {
          const active = isRouteActive(pathname, entry.route);
          const Icon = entry.key === "home" ? Home : resolveIcon(entry.icon);
          return (
            <button
              key={entry.key}
              onClick={() => go(entry)}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex-1 flex flex-col items-center justify-center gap-0.5 min-h-14 px-1 select-none",
                active ? "text-brand" : "text-muted-foreground active:text-foreground",
              )}
            >
              <Icon className="w-5 h-5 shrink-0" />
              <span className="text-[10px] leading-tight truncate w-full text-center">
                {entry.title}
              </span>
            </button>
          );
        })}
        {/* 「更多」→ AppSidebar 移动端 Sheet(方案 Phase 2 第 2 项:分组标题/当前模块高亮/关闭焦点回收) */}
        <button
          onClick={() => setOpenMobile(true)}
          aria-expanded={openMobile}
          className={cn(
            "flex-1 flex flex-col items-center justify-center gap-0.5 min-h-14 px-1 select-none",
            moreActive || openMobile
              ? "text-brand"
              : "text-muted-foreground active:text-foreground",
          )}
        >
          <Menu className="w-5 h-5 shrink-0" />
          <span className="text-[10px] leading-tight">{t("mobileNav.more")}</span>
        </button>
      </nav>
    </>
  );
}
