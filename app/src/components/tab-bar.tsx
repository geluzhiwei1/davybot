/**
 * TabBar — horizontal tab strip for open workspace / temp-task / page tabs.
 * Reads state from useTabsStore. Clicking a tab navigates via TanStack Router;
 * the X button closes and navigates to the neighbour.
 * Right-click shows context menu: close others, close left, close right.
 */
import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { useTabsStore, type TabItem } from "@/lib/tabs-store";
import {
  X,
  FolderOpen,
  Sparkles,
  Home,
  Search,
  BookOpen,
  FileSearch,
  Settings,
  Workflow,
  Scale,
  Activity,
  ListTodo,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";

/** Map icon name string to Lucide component */
const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  home: Home,
  search: Search,
  "book-open": BookOpen,
  "file-search": FileSearch,
  sparkles: Sparkles,
  settings: Settings,
  workflow: Workflow,
  scale: Scale,
  activity: Activity,
  "folder-open": FolderOpen,
  "list-todo": ListTodo,
};

function TabIcon({ tab }: { tab: TabItem }) {
  if (tab.type === "workspace-task") {
    return <FolderOpen className="w-3 h-3 shrink-0 text-brand/70" />;
  }
  if (tab.type === "temp-task") {
    return <Sparkles className="w-3 h-3 shrink-0 text-brand/70" />;
  }
  // Page tab — use icon name or fallback
  const IconComp = (tab.icon && ICON_MAP[tab.icon]) || Home;
  return <IconComp className="w-3 h-3 shrink-0 text-brand/70" />;
}

export function TabBar() {
  const { t } = useTranslation("commonUi");
  const tabs = useTabsStore((s) => s.tabs);
  const activeTabKey = useTabsStore((s) => s.activeTabKey);
  const setActiveTab = useTabsStore((s) => s.setActiveTab);
  const closeTab = useTabsStore((s) => s.closeTab);
  const closeOtherTabs = useTabsStore((s) => s.closeOtherTabs);
  const closeTabsToLeft = useTabsStore((s) => s.closeTabsToLeft);
  const closeTabsToRight = useTabsStore((s) => s.closeTabsToRight);
  const navigate = useNavigate();
  // 移动端页签切换器(方案 Phase 2):<md 无页签条,以 Sheet 列表切换/关闭
  const [switcherOpen, setSwitcherOpen] = useState(false);

  if (tabs.length === 0) return null;

  const activeTab = tabs.find((t) => t.key === activeTabKey) ?? null;

  const handleClick = (key: string) => {
    setActiveTab(key);
    const tab = tabs.find((t) => t.key === key);
    if (tab) {
      navigateToTab(navigate, tab);
    }
  };

  const handleClose = (e: React.MouseEvent, key: string) => {
    e.stopPropagation();
    const idx = tabs.findIndex((t) => t.key === key);
    const remaining = tabs.filter((t) => t.key !== key);
    const wasActive = key === activeTabKey;

    closeTab(key);

    if (wasActive) {
      if (remaining.length > 0) {
        const newIdx = Math.min(idx, remaining.length - 1);
        const neighbour = remaining[newIdx];
        navigateToTab(navigate, neighbour);
      } else {
        navigate({ to: "/" });
      }
    }
  };

  const getTabLabel = (tab: TabItem) => {
    if (tab.type === "workspace-task") {
      return tab.workspaceName || tab.title || t("tabBar.workspace");
    }
    if (tab.type === "temp-task") {
      return tab.title || t("tabBar.recentTask");
    }
    return tab.title;
  };

  return (
    <>
      {/* 移动端(<md):单行页签头 + 列表式切换器,替代横向滚动页签条 */}
      <div className="flex md:hidden items-center gap-2 bg-muted/30 border-b border-border px-3 h-11 shrink-0">
        {activeTab && (
          <>
            <TabIcon tab={activeTab} />
            <span className="text-sm font-medium truncate">{getTabLabel(activeTab)}</span>
          </>
        )}
        <button
          onClick={() => setSwitcherOpen(true)}
          aria-label={t("tabBar.tabs")}
          className="ml-auto flex items-center gap-1.5 h-9 px-2.5 rounded-md text-muted-foreground hover:bg-background/60 active:bg-background transition-colors"
        >
          <Layers className="w-4 h-4" />
          <span className="text-xs tabular-nums">{tabs.length}</span>
        </button>
      </div>

      {/* 桌面端(≥md):原横向页签条 */}
      <div className="hidden md:flex items-end bg-muted/30 border-b border-border overflow-x-auto scrollbar-none shrink-0">
        {tabs.map((tab, idx) => {
          const isActive = tab.key === activeTabKey;
          const hasLeft = idx > 0;
          const hasRight = idx < tabs.length - 1;

          return (
            <ContextMenu key={tab.key}>
              <ContextMenuTrigger asChild>
                <div
                  onClick={() => handleClick(tab.key)}
                  className={cn(
                    "group relative flex items-center gap-1.5 px-3 py-1.5 cursor-pointer border-r border-border/60 min-w-0 max-w-[180px] select-none",
                    "transition-colors",
                    isActive
                      ? "bg-background text-foreground border-b-2 border-b-brand -mb-px"
                      : "text-muted-foreground hover:bg-background/60 hover:text-foreground",
                  )}
                >
                  <TabIcon tab={tab} />
                  <span className="text-xs truncate">{getTabLabel(tab)}</span>
                  <button
                    onClick={(e) => handleClose(e, tab.key)}
                    aria-label={t("common.close")}
                    className={cn(
                      "shrink-0 w-4 h-4 rounded-sm flex items-center justify-center",
                      "opacity-0 group-hover:opacity-100 hover:bg-muted/80 transition-opacity",
                    )}
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                </div>
              </ContextMenuTrigger>
              <ContextMenuContent className="w-48">
                <ContextMenuItem
                  onClick={() =>
                    handleClose({ stopPropagation: () => {} } as React.MouseEvent, tab.key)
                  }
                >
                  {t("common.close")}
                </ContextMenuItem>
                <ContextMenuItem
                  disabled={!hasLeft && !hasRight}
                  onClick={() => closeOtherTabs(tab.key)}
                >
                  {t("tabBar.closeOthers")}
                </ContextMenuItem>
                <ContextMenuSeparator />
                <ContextMenuItem disabled={!hasLeft} onClick={() => closeTabsToLeft(tab.key)}>
                  {t("tabBar.closeLeft")}
                </ContextMenuItem>
                <ContextMenuItem disabled={!hasRight} onClick={() => closeTabsToRight(tab.key)}>
                  {t("tabBar.closeRight")}
                </ContextMenuItem>
              </ContextMenuContent>
            </ContextMenu>
          );
        })}
      </div>

      {/* 移动端页签切换 Sheet:点按切换,X 关闭(替代桌面右键菜单) */}
      <Sheet open={switcherOpen} onOpenChange={setSwitcherOpen}>
        <SheetContent side="bottom" className="p-0">
          <SheetHeader className="px-4 pb-2 pt-4">
            <SheetTitle>{t("tabBar.tabs")}</SheetTitle>
          </SheetHeader>
          <div className="max-h-[60dvh] overflow-y-auto pb-[max(1rem,env(safe-area-inset-bottom))]">
            {tabs.map((tab) => {
              const isActive = tab.key === activeTabKey;
              return (
                <div
                  key={tab.key}
                  onClick={() => {
                    handleClick(tab.key);
                    setSwitcherOpen(false);
                  }}
                  className={cn(
                    "flex items-center gap-2.5 min-h-12 px-4 py-1 cursor-pointer select-none border-b border-border/40 last:border-b-0",
                    isActive
                      ? "bg-background text-foreground"
                      : "text-muted-foreground active:bg-background/60",
                  )}
                >
                  <TabIcon tab={tab} />
                  <span className="text-sm truncate">{getTabLabel(tab)}</span>
                  <button
                    onClick={(e) => handleClose(e, tab.key)}
                    aria-label={t("common.close")}
                    className="ml-auto shrink-0 w-9 h-9 -mr-2 rounded-full flex items-center justify-center hover:bg-muted/80"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              );
            })}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}

/**
 * Navigate to the route represented by a tab item.
 */
function navigateToTab(navigate: ReturnType<typeof useNavigate>, tab: TabItem) {
  if (tab.type === "page" && tab.route) {
    navigate({ to: tab.route as typeof tab.route & string });
    return;
  }
  if (tab.type === "workspace-overview" && tab.workspaceId) {
    navigate({
      to: "/workspace/$workspaceId",
      params: { workspaceId: tab.workspaceId },
    });
    return;
  }
  if (tab.type === "workspace-task" && tab.workspaceId && tab.taskId) {
    navigate({
      to: "/workspace/$workspaceId/task/$taskId",
      params: { workspaceId: tab.workspaceId, taskId: tab.taskId },
    });
  } else if (tab.taskId) {
    navigate({
      to: "/temp/$taskId",
      params: { taskId: tab.taskId },
    });
  }
}
