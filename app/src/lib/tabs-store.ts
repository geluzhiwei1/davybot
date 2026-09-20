/**
 * Tabs store — tracks open workspace/task tabs in the content area.
 * Persisted so tabs survive page refresh.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface TabItem {
  /** Unique key: route path with params resolved, e.g. "/workspace/abc/task/def" */
  key: string;
  /** Display title */
  title: string;
  /** Tab type */
  type: "workspace-task" | "workspace-overview" | "temp-task" | "page";
  /** Route to navigate to (for page tabs) */
  route?: string;
  /** Icon name for page tabs */
  icon?: string;
  /** Workspace ID (for workspace tasks) */
  workspaceId?: string;
  /** Workspace name (for display) */
  workspaceName?: string;
  /** Task ID (not required for page tabs) */
  taskId?: string;
  /** ISO timestamp when opened */
  openedAt: string;
  /** Generic metadata slot, available to any module */
  metadata?: Record<string, unknown>;
}

interface TabsState {
  /** All open tabs, ordered */
  tabs: TabItem[];
  /** Key of the active tab */
  activeTabKey: string | null;

  // Actions
  openTab: (tab: Omit<TabItem, "openedAt">) => void;
  closeTab: (key: string) => void;
  setActiveTab: (key: string) => void;
  updateTabTitle: (key: string, title: string) => void;
  /** Remove all tabs referencing a given task */
  closeTabsForTask: (taskId: string) => void;
  /** Close all tabs except the given key */
  closeOtherTabs: (keepKey: string) => void;
  /** Close all tabs to the left of the given key */
  closeTabsToLeft: (key: string) => void;
  /** Close all tabs to the right of the given key */
  closeTabsToRight: (key: string) => void;
}

export const useTabsStore = create<TabsState>()(
  persist(
    (set, get) => ({
      tabs: [],
      activeTabKey: null,

      openTab: (tab) => {
        const { tabs, activeTabKey } = get();
        const existing = tabs.find((t) => t.key === tab.key);
        if (existing) {
          // Already open — only update if something actually changed
          const newTitle = tab.title;
          const newWorkspaceName = tab.workspaceName ?? existing.workspaceName;
          const titleChanged = existing.title !== newTitle;
          const wsNameChanged = existing.workspaceName !== newWorkspaceName;
          const activeChanged = activeTabKey !== tab.key;
          if (titleChanged || wsNameChanged || activeChanged) {
            set({
              activeTabKey: tab.key,
              tabs:
                titleChanged || wsNameChanged
                  ? tabs.map((t) =>
                      t.key === tab.key
                        ? { ...t, title: newTitle, workspaceName: newWorkspaceName }
                        : t,
                    )
                  : tabs,
            });
          }
          return;
        }
        const newTab: TabItem = { ...tab, openedAt: new Date().toISOString() };
        set({
          tabs: [...tabs, newTab],
          activeTabKey: tab.key,
        });
      },

      closeTab: (key) => {
        const { tabs, activeTabKey } = get();
        const idx = tabs.findIndex((t) => t.key === key);
        const remaining = tabs.filter((t) => t.key !== key);

        // If closing the active tab, activate neighbor
        let newActive = activeTabKey;
        if (activeTabKey === key) {
          if (remaining.length === 0) {
            newActive = null;
          } else {
            // Activate the tab to the left, or the first
            const newIdx = Math.min(idx, remaining.length - 1);
            newActive = remaining[newIdx]?.key ?? null;
          }
        }
        set({ tabs: remaining, activeTabKey: newActive });
      },

      setActiveTab: (key) => set({ activeTabKey: key }),

      updateTabTitle: (key, title) =>
        set((s) => ({
          tabs: s.tabs.map((t) => (t.key === key ? { ...t, title } : t)),
        })),

      closeTabsForTask: (taskId) =>
        set((s) => ({
          tabs: s.tabs.filter((t) => t.taskId !== taskId),
          activeTabKey:
            s.activeTabKey && s.tabs.some((t) => t.key === s.activeTabKey && t.taskId === taskId)
              ? (s.tabs.find((t) => t.taskId !== taskId)?.key ?? null)
              : s.activeTabKey,
        })),

      closeOtherTabs: (keepKey) =>
        set((s) => {
          const remaining = s.tabs.filter((t) => t.key === keepKey);
          const activeKey =
            s.activeTabKey && remaining.some((t) => t.key === s.activeTabKey)
              ? s.activeTabKey
              : keepKey;
          return { tabs: remaining, activeTabKey: activeKey };
        }),

      closeTabsToLeft: (key) =>
        set((s) => {
          const idx = s.tabs.findIndex((t) => t.key === key);
          if (idx < 0) return s;
          const remaining = s.tabs.slice(idx);
          const activeKey = remaining.some((t) => t.key === s.activeTabKey) ? s.activeTabKey : key;
          return { tabs: remaining, activeTabKey: activeKey };
        }),

      closeTabsToRight: (key) =>
        set((s) => {
          const idx = s.tabs.findIndex((t) => t.key === key);
          if (idx < 0) return s;
          const remaining = s.tabs.slice(0, idx + 1);
          const activeKey = remaining.some((t) => t.key === s.activeTabKey) ? s.activeTabKey : key;
          return { tabs: remaining, activeTabKey: activeKey };
        }),
    }),
    {
      name: "normnomos-tabs-v1",
      partialize: (s) => ({ tabs: s.tabs, activeTabKey: s.activeTabKey }),
    },
  ),
);
