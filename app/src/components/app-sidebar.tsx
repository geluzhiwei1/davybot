import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "@tanstack/react-router";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageSelector } from "@/components/language-selector";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  ChevronRight,
  ChevronDown,
  Scale,
  Home,
  Building2,
  Users,
  LogOut,
  ArrowLeftRight,
  Pin,
  CircleUser,
  MonitorSmartphone,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useTabsStore } from "@/lib/tabs-store";
import { usePinnedStore } from "@/lib/pinned-store";
import { resolveIcon } from "@/lib/icon-map";
import { BIZ_SIDEBAR_CONTEXT_SELECTS } from "@/lib/biz-registry";
import { cn } from "@/lib/utils";
import { redirectToLogin, useAuthStore } from "@/lib/auth-store";
import { SUPPORT_API_URL, USER_CENTER_BASE_URL } from "@/lib/env";
import { useSidebarCounts } from "@/hooks/use-sidebar-counts";
import { isSectionVisible } from "@/lib/caps";
import { useCaps } from "@/lib/stores/runtime-store";
import { CountBadge, BetaBadge, AlphaBadge } from "@/components/count-badge";
import {
  SIDEBAR_CONFIG,
  isCoreModuleKey,
  isExactRoute,
  routeToModuleKey,
  type SidebarItem,
  type SidebarSubgroup,
} from "@/lib/sidebar-config";

/**
 * Pin toggle button — shown on hover for sidebar menu items.
 * Clicking toggles the pin state without triggering navigation.
 * When already pinned, the icon is always visible and highlighted.
 */
function PinToggleButton({
  route,
  title,
  iconName,
  pinned,
  onToggle,
}: {
  route: string;
  title: string;
  iconName: string;
  pinned: boolean;
  onToggle: (route: string, title: string, iconName: string) => void;
}) {
  const { t } = useTranslation("commonUi");
  return (
    <span
      role="button"
      tabIndex={-1}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle(route, title, iconName);
      }}
      className={cn(
        "ml-auto shrink-0 rounded p-0.5 transition-all cursor-pointer",
        pinned
          ? "opacity-100 text-brand"
          : "opacity-0 group-hover/menu-item:opacity-100 text-muted-foreground hover:text-foreground",
      )}
      title={pinned ? t("sidebar.unpin") : t("sidebar.pin")}
    >
      <Pin className="w-3 h-3" fill={pinned ? "currentColor" : "none"} />
    </span>
  );
}

// ============================================================================
// SidebarGroupsRenderer — 數據驅動渲染整個 sidebar body
// ============================================================================
type CountsShape = Record<string, number>;

interface RendererProps {
  path: string;
  collapsed: boolean;
  collapsedGroups: Set<string>;
  toggleGroup: (key: string) => void;
  pinnedItems: Array<{ key: string; title: string; route: string; icon: string }>;
  pinnedKeys: Set<string>;
  handleTogglePin: (route: string, title: string, iconName: string) => void;
  openPageTab: (route: string, title: string, icon: string) => void;
  sidebarCounts: CountsShape;
  setActiveDrawer: (drawer: string | null) => void;
  effectiveModules: string[] | null;
  /** 当前路由所在分组 key — 移动端 Sheet 传入,分组标题高亮定位当前模块 */
  activeGroupKey?: string | null;
}

/**
 * 過濾 sidebar items：
 *   - hidden → 隱藏
 *   - enabledKeys !== null（已載入）且不含 item.key → 隱藏
 *   - localOnly（後端 SEED_MODULES 未播種的前端自治頁）不受模塊管控過濾
 */
function filterItems(items: SidebarItem[], enabledKeys: Set<string> | null): SidebarItem[] {
  return items.filter((it) => {
    if (it.hidden) return false;
    if (enabledKeys !== null && !it.localOnly && !enabledKeys.has(it.key)) return false;
    return true;
  });
}

/** 處理某路由是否 active（含子路徑前綴；exact=佈局索引頁僅精確匹配）。 */
function isRouteActive(path: string, route: string, exact = false): boolean {
  if (route === "/") return path === "/";
  if (exact) return path === route;
  return path === route || path.startsWith(route + "/");
}

export function SidebarGroupsRenderer(props: RendererProps) {
  const { t } = useTranslation("commonUi");
  const {
    path,
    collapsed,
    collapsedGroups,
    activeGroupKey,
    toggleGroup,
    pinnedItems,
    pinnedKeys,
    handleTogglePin,
    openPageTab,
    sidebarCounts,
    setActiveDrawer,
    effectiveModules,
  } = props;

  const enabledKeys: Set<string> | null = effectiveModules ? new Set(effectiveModules) : null;
  // F2: 無模組管控(自包含 server/tui 本地態) → 僅渲染核心分組(home/explore/system)
  const coreOnly = effectiveModules === null;
  // F2: 釘倉跨構建持久 —— coreOnly 下過濾歷史釘住的業務項(否則死鏈被路由守衛彈回)。
  // 釘的 key=route,經 routeToModuleKey 反查;null(非業務路由)放行,與守衛語義一致。
  const visiblePinned = coreOnly
    ? pinnedItems.filter((p) => {
        const mk = routeToModuleKey(p.route);
        return mk === null || isCoreModuleKey(mk);
      })
    : pinnedItems;

  return (
    <>
      {/* Home group — always rendered */}
      <SidebarGroup>
        <SidebarGroupContent>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={path === "/"}
                onClick={() => openPageTab("/", t("sidebar.home"), "home")}
              >
                <Home className="w-4 h-4" />
                <span>{t("sidebar.home")}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
            {/* Pinned shortcuts — shown directly under 首页 */}
            {visiblePinned.map((item) => {
              const Icon = resolveIcon(item.icon);
              return (
                <SidebarMenuItem key={item.key} className="group/menu-item">
                  <SidebarMenuButton
                    isActive={isRouteActive(path, item.route, isExactRoute(item.route))}
                    onClick={() => openPageTab(item.route, item.title, item.icon)}
                  >
                    <Icon className="w-4 h-4" />
                    <span>{item.title}</span>
                    {!collapsed && (
                      <PinToggleButton
                        route={item.route}
                        title={item.title}
                        iconName={item.icon}
                        pinned={pinnedKeys.has(item.route)}
                        onToggle={handleTogglePin}
                      />
                    )}
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      {/* 其餘分組（home 之後）— 按 SIDEBAR_CONFIG 順序;F2 core-only 時只出核心分組 */}
      {SIDEBAR_CONFIG.filter((g) => g.key !== "home" && (!coreOnly || g.core)).map((group) => {
        // 過濾頂層 items
        const topItems = group.items ? filterItems(group.items, enabledKeys) : [];
        // 過濾子分组
        const subgroups: SidebarSubgroup[] = (group.subgroups ?? [])
          .map((sg) => ({ label: sg.label, items: filterItems(sg.items, enabledKeys) }))
          .filter((sg) => sg.items.length > 0);

        // 整組如果頂層 + 子分组都空 → 不渲染
        if (topItems.length === 0 && subgroups.length === 0) return null;

        const collapsedNow = collapsedGroups.has(group.key);
        // 当前模块高亮:当前路由所在分组的标题着色(仅移动端 Sheet 传入,桌面为 null)
        const groupActive = group.key === activeGroupKey;

        return (
          <SidebarGroup key={group.key}>
            {!collapsed && (
              <SidebarGroupLabel
                className={cn(
                  "cursor-pointer select-none hover:text-foreground transition-colors",
                  groupActive && "text-brand font-medium",
                )}
                onClick={() => toggleGroup(group.key)}
              >
                <span>{group.title}</span>
                {group.badge === "alpha" && <AlphaBadge />}
                <ChevronDown
                  className={cn(
                    "ml-auto w-3.5 h-3.5 transition-transform",
                    collapsedNow && "-rotate-90",
                  )}
                />
              </SidebarGroupLabel>
            )}
            {(!collapsedNow || collapsed) && (
              <SidebarGroupContent>
                <SidebarMenu>
                  {/* 頂層 items */}
                  {topItems.map((it) => (
                    <SidebarItemRow
                      key={it.key}
                      item={it}
                      path={path}
                      collapsed={collapsed}
                      pinnedKeys={pinnedKeys}
                      handleTogglePin={handleTogglePin}
                      openPageTab={openPageTab}
                      sidebarCounts={sidebarCounts}
                      setActiveDrawer={setActiveDrawer}
                    />
                  ))}

                  {/* biz 注册的上下文行(产品/品牌全局切换等,assemble 注入;核心构建 = 空表不渲染) */}
                  {!collapsed &&
                    !collapsedNow &&
                    BIZ_SIDEBAR_CONTEXT_SELECTS.filter((e) => e.groupKey === group.key).map((e) => {
                      const ContextSelect = e.component;
                      return (
                        <div key={e.groupKey} className="flex items-center gap-2 px-2 pt-2 pb-1">
                          <span className="text-xs font-semibold tracking-wide text-foreground/80 shrink-0">
                            {typeof e.label === "function" ? e.label() : e.label}
                          </span>
                          <ContextSelect />
                          <div className="h-px flex-1 bg-sidebar-border" />
                        </div>
                      );
                    })}

                  {/* 子分组 */}
                  {subgroups.map((sg, idx) => (
                    <SidebarSubgroupBlock
                      key={sg.label}
                      label={sg.label}
                      items={sg.items}
                      path={path}
                      collapsed={collapsed}
                      pinnedKeys={pinnedKeys}
                      handleTogglePin={handleTogglePin}
                      openPageTab={openPageTab}
                      sidebarCounts={sidebarCounts}
                      showSeparator={idx > 0 || topItems.length > 0}
                    />
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            )}
          </SidebarGroup>
        );
      })}
    </>
  );
}

/** 單個 sidebar item 行 — 含圖標、標題、count 徽章、AI 徽章、Pin 按鈕。 */
function SidebarItemRow({
  item,
  path,
  collapsed,
  pinnedKeys,
  handleTogglePin,
  openPageTab,
  sidebarCounts,
  setActiveDrawer,
}: {
  item: SidebarItem;
  path: string;
  collapsed: boolean;
  pinnedKeys: Set<string>;
  handleTogglePin: (route: string, title: string, iconName: string) => void;
  openPageTab: (route: string, title: string, icon: string) => void;
  sidebarCounts: CountsShape;
  setActiveDrawer: (drawer: string | null) => void;
}) {
  const Icon = resolveIcon(item.icon);
  const isDrawer = item.route.startsWith("/__drawer_");
  const handleClick = () => {
    if (isDrawer && item.route === "/__drawer_user_settings__") {
      setActiveDrawer("user-settings");
      return;
    }
    openPageTab(item.route, item.title, item.icon);
  };

  return (
    <SidebarMenuItem className="group/menu-item">
      <SidebarMenuButton
        isActive={isRouteActive(path, item.route, item.exact)}
        onClick={handleClick}
      >
        <Icon className="w-4 h-4" />
        <span>{item.title}</span>
        {/* Count badge */}
        {!collapsed && item.countKey && sidebarCounts[item.countKey] !== undefined && (
          <CountBadge count={sidebarCounts[item.countKey]} variant={item.countVariant} />
        )}
        {/* Beta badge */}
        {!collapsed && item.badge === "beta" && <BetaBadge />}
        {/* AI badge */}
        {!collapsed && item.badge === "ai" && (
          <span className="ml-auto rounded-full bg-brand/10 px-1.5 py-0.5 text-[9px] font-semibold text-brand">
            AI
          </span>
        )}
        {!collapsed && (
          <PinToggleButton
            route={item.route}
            title={item.title}
            iconName={item.icon}
            pinned={pinnedKeys.has(item.route)}
            onToggle={handleTogglePin}
          />
        )}
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

/** 子分组塊 — 含分隔符 + 內部 items。 */
function SidebarSubgroupBlock({
  label,
  items,
  path,
  collapsed,
  pinnedKeys,
  handleTogglePin,
  openPageTab,
  sidebarCounts,
  showSeparator,
}: {
  label: string;
  items: SidebarItem[];
  path: string;
  collapsed: boolean;
  pinnedKeys: Set<string>;
  handleTogglePin: (route: string, title: string, iconName: string) => void;
  openPageTab: (route: string, title: string, icon: string) => void;
  sidebarCounts: CountsShape;
  showSeparator: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <>
      {showSeparator && (
        <>
          {!collapsed && (
            <div className="flex items-center gap-2 px-2 pt-2 pb-0">
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70 shrink-0">
                {label}
              </span>
              <div className="h-px flex-1 bg-sidebar-border" />
            </div>
          )}
          {collapsed && <SidebarSeparator className="my-1" />}
        </>
      )}
      {items.map((it) => (
        <SidebarItemRow
          key={it.key}
          item={it}
          path={path}
          collapsed={collapsed}
          pinnedKeys={pinnedKeys}
          handleTogglePin={handleTogglePin}
          openPageTab={openPageTab}
          sidebarCounts={sidebarCounts}
          setActiveDrawer={() => {}}
        />
      ))}
    </>
  );
}

export function AppSidebar() {
  const { t } = useTranslation("commonUi");
  // 运行期能力 (多模式统一方案 §L4): 用户菜单入口按 SECTIONS 表显隐
  const { caps } = useCaps();
  const { state, openMobile, setOpenMobile } = useSidebar();
  // 移动端 Sheet 恒为展开态(分组标题/文案常显);桌面 openMobile 恒 false,语义不变
  const collapsed = state === "collapsed" && !openMobile;
  const location = useLocation();
  const navigate = useNavigate();
  const renameWorkspace = useStore((s) => s.renameWorkspace);
  const deleteWorkspace = useStore((s) => s.deleteWorkspace);
  const renameTask = useStore((s) => s.renameTask);
  const deleteTask = useStore((s) => s.deleteTask);
  const setActiveDrawer = useStore((s) => s.setActiveDrawer);

  const openTab = useTabsStore((s) => s.openTab);
  const authUser = useAuthStore((s) => s.user);
  const availableTenants = useAuthStore((s) => s.availableTenants);
  const currentTenant = availableTenants?.find((t) => t.is_current) ?? null;

  // Pinned menu items
  const pinnedItems = usePinnedStore((s) => s.pinned);
  const togglePin = usePinnedStore((s) => s.togglePin);
  const pinnedKeys = new Set(pinnedItems.map((p) => p.key));
  const handleTogglePin = useCallback(
    (route: string, title: string, iconName: string) => {
      togglePin({ key: route, title, route, icon: iconName });
    },
    [togglePin],
  );

  // Dynamic sidebar badge counts for 智能律所
  const { counts: sidebarCounts } = useSidebarCounts();

  const [renameTarget, setRenameTarget] = useState<{ id: string; title: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string;
    title: string;
    workspaceId: string | null;
  } | null>(null);
  const [renameWsTarget, setRenameWsTarget] = useState<{ id: string; name: string } | null>(null);
  const [deleteWsTarget, setDeleteWsTarget] = useState<{
    id: string;
    name: string;
    count: number;
  } | null>(null);

  const effectiveMods = useAuthStore((s) => s.effectiveModules);
  const path = location.pathname;

  // Collapsible sidebar groups — 全部折叠（仅 "home" 单项不参与折叠）
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    () => new Set(SIDEBAR_CONFIG.filter((g) => g.key !== "home").map((g) => g.key)),
  );
  const toggleGroup = (key: string) =>
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  // ── 移动端侧栏 Sheet 补齐(方案 Phase 2 第 2 项)──
  // 当前路由所在分组:Sheet 打开时自动展开 + 标题高亮,用户一眼定位所在模块
  const activeGroupKey = useMemo(() => {
    for (const g of SIDEBAR_CONFIG) {
      if (g.key === "home") continue;
      const items = [...(g.items ?? []), ...(g.subgroups ?? []).flatMap((sg) => sg.items)];
      if (items.some((it) => !it.hidden && isRouteActive(path, it.route, it.exact))) return g.key;
    }
    return null;
  }, [path]);

  // Sheet 打开时展开当前分组(桌面 openMobile 恒 false,零影响)
  useEffect(() => {
    if (!openMobile || !activeGroupKey) return;
    setCollapsedGroups((prev) => {
      if (!prev.has(activeGroupKey)) return prev;
      const next = new Set(prev);
      next.delete(activeGroupKey);
      return next;
    });
  }, [openMobile, activeGroupKey]);

  // 路由变化后自动关闭 Sheet;Radix 关闭时把焦点还给触发器(底部导航「更多」)
  const prevPathRef = useRef(path);
  useEffect(() => {
    if (prevPathRef.current === path) return;
    prevPathRef.current = path;
    if (openMobile) setOpenMobile(false);
  }, [path, openMobile, setOpenMobile]);

  /** Open or switch to a page tab */
  const openPageTab = (route: string, title: string, icon: string) => {
    openTab({ key: route, title, type: "page", route, icon });
    navigate({ to: route } as Parameters<typeof navigate>[0]);
  };

  /**
   * 我的账号 — 一次性 SSO 授权码自动登录用户中心。
   *
   * 流程：用当前 accessToken 调 /v1/auth/sso/code 换 60s 一次性 code，
   * 打开 `{USER_CENTER_BASE_URL}/support/ui/user/sso?code=...`；
   * Web 中继页 exchange 后以相同身份（个人/租户）自动登录。
   * 任一环节失败 → 降级打开登录页（与旧行为一致的安全网）。
   */
  const openMyAccount = async () => {
    // F: 用户中心为可选集成 —— 未配置 VITE_USER_CENTER_BASE_URL(server 自包含)不外跳
    if (!USER_CENTER_BASE_URL) return;
    const base = USER_CENTER_BASE_URL.replace(/\/+$/, "");
    const fallback = `${base}/support/ui/user/login`;
    const win = window.open(fallback, "_blank"); // 先开窗口，避免异步后弹窗被拦截
    try {
      const { accessToken } = useAuthStore.getState();
      if (!accessToken || !win) return;
      const res = await fetch(`${SUPPORT_API_URL}/v1/auth/sso/code`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) return;
      const data = await res.json();
      const code = typeof data?.code === "string" ? data.code : null;
      if (code && win) {
        win.location.href = `${base}/support/ui/user/sso?code=${encodeURIComponent(code)}`;
      }
    } catch {
      // 保持 fallback 登录页
    }
  };

  const handleConfirmDelete = () => {
    if (!deleteTarget) return;
    const { id, workspaceId } = deleteTarget;
    deleteTask(id);
    if (path.includes(id)) {
      navigate({ to: "/" });
    }
    setDeleteTarget(null);
    void workspaceId;
  };

  const handleConfirmDeleteWs = () => {
    if (!deleteWsTarget) return;
    const { id } = deleteWsTarget;
    deleteWorkspace(id);
    if (path.startsWith(`/workspace/${id}`)) navigate({ to: "/" });
    setDeleteWsTarget(null);
  };

  return (
    <Sidebar collapsible="icon" className="border-r-0">
      <TooltipProvider delayDuration={150} disableHoverableContent>
        <SidebarHeader className="border-b border-sidebar-border">
          <Link
            to="/"
            className={cn(
              "flex items-center gap-2 py-2 transition-[padding,gap] duration-150",
              collapsed ? "justify-center px-0" : "px-2",
            )}
          >
            <div className="w-8 h-8 rounded-lg bg-gradient-brand flex items-center justify-center shadow-brand shrink-0">
              <Scale className="w-4 h-4 text-[oklch(0.16_0.03_250)]" strokeWidth={2.5} />
            </div>
            {!collapsed && (
              <div className="flex flex-col leading-tight">
                <span className="text-sm font-semibold tracking-tight">NormNomos</span>
                <span className="text-[10px] text-muted-foreground">{t("sidebar.tagline")}</span>
              </div>
            )}
          </Link>
        </SidebarHeader>

        <SidebarContent className="scrollbar-thin">
          {/* Toolbar row: trigger + theme + lang */}
          <div
            className={cn(
              "flex items-center gap-1 px-2 py-1 shrink-0 border-b border-sidebar-border/60",
              collapsed ? "justify-center" : "justify-between",
            )}
          >
            <SidebarTrigger className="h-7 w-7" />
            {!collapsed && (
              <div className="flex items-center gap-0.5">
                <LanguageSelector />
                <ThemeToggle />
              </div>
            )}
          </div>

          {/* ── 數據驅動 sidebar 渲染 ──
              SIDEBAR_CONFIG 是 SSOT；SidebarGroupsRenderer 按 effectiveModules 過濾。
              null = 未載入，降級全量顯示（兼容老後端或離線首屏）。 */}
          <SidebarGroupsRenderer
            path={path}
            collapsed={collapsed}
            collapsedGroups={collapsedGroups}
            activeGroupKey={openMobile ? activeGroupKey : null}
            toggleGroup={toggleGroup}
            pinnedItems={pinnedItems}
            pinnedKeys={pinnedKeys}
            handleTogglePin={handleTogglePin}
            openPageTab={openPageTab}
            sidebarCounts={sidebarCounts}
            setActiveDrawer={setActiveDrawer}
            effectiveModules={effectiveMods}
          />
        </SidebarContent>

        <SidebarFooter className="border-t border-sidebar-border">
          {/* User / settings row */}
          <SidebarMenu>
            <SidebarMenuItem>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuButton className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-gradient-brand flex items-center justify-center text-[10px] font-bold text-brand-foreground shrink-0">
                      {authUser?.nickname?.charAt(0)?.toUpperCase() ?? "U"}
                    </div>
                    {!collapsed && (
                      <div className="flex flex-col leading-tight flex-1 min-w-0">
                        <span className="text-xs font-medium truncate">
                          {authUser?.nickname ?? t("sidebar.user.default")}
                        </span>
                        <span className="text-[10px] text-muted-foreground flex items-center gap-1 truncate">
                          {currentTenant ? (
                            <>
                              <Building2 className="w-2.5 h-2.5 shrink-0" />
                              <span className="truncate">
                                {currentTenant.tenant_name ?? currentTenant.tenant_id}
                              </span>
                            </>
                          ) : (
                            <>
                              <Users className="w-2.5 h-2.5 shrink-0" />
                              <span>{t("sidebar.user.personal")}</span>
                            </>
                          )}
                        </span>
                      </div>
                    )}
                    {!collapsed && <ChevronRight className="w-3.5 h-3.5 opacity-60 ml-auto" />}
                  </SidebarMenuButton>
                </DropdownMenuTrigger>
                <DropdownMenuContent side="top" align="start" className="w-48">
                  <DropdownMenuItem onClick={() => navigate({ to: "/select-tenant" })}>
                    <ArrowLeftRight className="w-4 h-4 mr-2" />
                    <span>{t("sidebar.user.switch")}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => void openMyAccount()}>
                    <CircleUser className="w-4 h-4 mr-2" />
                    <span>{t("sidebar.user.myAccount")}</span>
                  </DropdownMenuItem>
                  {isSectionVisible("devices", caps) && (
                    <DropdownMenuItem
                      onClick={() =>
                        openPageTab(
                          "/settings/devices",
                          t("sidebar.user.myDevices"),
                          "monitor-smartphone",
                        )
                      }
                    >
                      <MonitorSmartphone className="w-4 h-4 mr-2" />
                      <span>{t("sidebar.user.myDevices")}</span>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem
                    onClick={() => redirectToLogin()}
                    className="text-red-600 focus:text-red-600 focus:bg-red-50 dark:focus:bg-red-950"
                  >
                    <LogOut className="w-4 h-4 mr-2" />
                    <span>{t("sidebar.user.logout")}</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>

        {/* Rename task dialog */}
        <Dialog open={!!renameTarget} onOpenChange={(o) => !o && setRenameTarget(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("sidebar.renameTask")}</DialogTitle>
            </DialogHeader>
            <Input
              value={renameTarget?.title || ""}
              onChange={(e) => setRenameTarget((r) => (r ? { ...r, title: e.target.value } : r))}
              onKeyDown={(e) => {
                if (e.key === "Enter" && renameTarget && renameTarget.title.trim()) {
                  renameTask(renameTarget.id, renameTarget.title.trim());
                  setRenameTarget(null);
                } else if (e.key === "Escape") {
                  setRenameTarget(null);
                }
              }}
              autoFocus
            />
            <DialogFooter>
              <Button variant="ghost" onClick={() => setRenameTarget(null)}>
                {t("common.cancel")}
              </Button>
              <Button
                className="bg-gradient-brand text-brand-foreground"
                onClick={() => {
                  if (renameTarget && renameTarget.title.trim()) {
                    renameTask(renameTarget.id, renameTarget.title.trim());
                    setRenameTarget(null);
                  }
                }}
              >
                {t("common.save")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Rename workspace dialog */}
        <Dialog open={!!renameWsTarget} onOpenChange={(o) => !o && setRenameWsTarget(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("sidebar.renameWorkspace")}</DialogTitle>
            </DialogHeader>
            <Input
              value={renameWsTarget?.name || ""}
              onChange={(e) => setRenameWsTarget((r) => (r ? { ...r, name: e.target.value } : r))}
              onKeyDown={(e) => {
                if (e.key === "Enter" && renameWsTarget && renameWsTarget.name.trim()) {
                  renameWorkspace(renameWsTarget.id, renameWsTarget.name.trim());
                  setRenameWsTarget(null);
                } else if (e.key === "Escape") {
                  setRenameWsTarget(null);
                }
              }}
              autoFocus
            />
            <DialogFooter>
              <Button variant="ghost" onClick={() => setRenameWsTarget(null)}>
                {t("common.cancel")}
              </Button>
              <Button
                className="bg-gradient-brand text-brand-foreground"
                onClick={() => {
                  if (renameWsTarget && renameWsTarget.name.trim()) {
                    renameWorkspace(renameWsTarget.id, renameWsTarget.name.trim());
                    setRenameWsTarget(null);
                  }
                }}
              >
                {t("common.save")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Delete task confirmation */}
        <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t("sidebar.deleteTask.title")}</AlertDialogTitle>
              <AlertDialogDescription>
                {t("sidebar.deleteTask.desc", { title: deleteTarget?.title ?? "" })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleConfirmDelete}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {t("common.delete")}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Delete workspace confirmation */}
        <AlertDialog open={!!deleteWsTarget} onOpenChange={(o) => !o && setDeleteWsTarget(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle className="text-destructive">
                {t("sidebar.deleteWorkspace.title")}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {t("sidebar.deleteWorkspace.descPrefix", { name: deleteWsTarget?.name ?? "" })}
                {deleteWsTarget && deleteWsTarget.count > 0 && (
                  <>
                    {t("sidebar.deleteWorkspace.andAlso")}{" "}
                    <span className="text-destructive font-medium">
                      {t("sidebar.deleteWorkspace.deleteTasks", { count: deleteWsTarget.count })}
                    </span>
                  </>
                )}
                {t("sidebar.deleteWorkspace.cannotUndo")}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleConfirmDeleteWs}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {t("sidebar.deleteWorkspace.confirm")}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </TooltipProvider>
    </Sidebar>
  );
}
