/**
 * Scheduled Tasks Zustand Store — manages backend scheduled_tasks API state.
 * Supports both per-workspace mode and global (cross-workspace) mode.
 */
import { toastError } from "./api/client.js";
import { create } from "zustand";
import {
  scheduledTasksApi,
  type ScheduledTask,
  type ScheduledTaskExecution,
  type CreateScheduledTaskRequest,
  type CreateScheduledTaskGlobalRequest,
} from "@/lib/api-client";

interface ScheduledTasksState {
  /** Task list */
  tasks: ScheduledTask[];
  schedulerActive: boolean;
  isLoading: boolean;
  error: string | null;

  /** Execution history cache (keyed by task_id) */
  executionsCache: Record<string, ScheduledTaskExecution[]>;
  executionsLoading: boolean;

  /** Client-side filters */
  filterStatus: string | null;
  filterScheduleType: string | null;
  searchText: string;

  /** Selected workspace (per-workspace mode) */
  selectedWorkspaceId: string | null;

  /** Global mode */
  isGlobalMode: boolean;

  /** Pagination (global mode) */
  totalCount: number;
  currentPage: number;
  totalPages: number;

  /** Polling interval ID */
  _pollInterval: ReturnType<typeof setInterval> | null;

  // ── Actions ──

  fetchTasks: (workspaceId: string) => Promise<void>;
  createTask: (workspaceId: string, data: CreateScheduledTaskRequest) => Promise<ScheduledTask>;
  updateTask: (
    workspaceId: string,
    taskId: string,
    updates: Partial<ScheduledTask>,
  ) => Promise<void>;
  deleteTask: (workspaceId: string, taskId: string) => Promise<void>;
  pauseTask: (workspaceId: string, taskId: string) => Promise<void>;
  resumeTask: (workspaceId: string, taskId: string) => Promise<void>;
  triggerTask: (workspaceId: string, taskId: string) => Promise<void>;
  fetchExecutions: (workspaceId: string, taskId: string, page?: number) => Promise<void>;
  setFilter: (filter: { status?: string; scheduleType?: string; search?: string }) => void;
  setSelectedWorkspace: (id: string | null) => void;
  startPolling: () => void;
  stopPolling: () => void;
  clearError: () => void;

  // ── Global mode actions ──
  setGlobalMode: (enabled: boolean) => void;
  fetchGlobalTasks: (params?: {
    status?: string;
    page?: number;
    page_size?: number;
  }) => Promise<void>;
  createGlobalTask: (data: CreateScheduledTaskGlobalRequest) => Promise<ScheduledTask>;
  setPage: (page: number) => void;
}

export const useScheduledTasksStore = create<ScheduledTasksState>((set, get) => ({
  tasks: [],
  schedulerActive: false,
  isLoading: false,
  error: null,

  executionsCache: {},
  executionsLoading: false,

  filterStatus: null,
  filterScheduleType: null,
  searchText: "",

  selectedWorkspaceId: null,
  _pollInterval: null,

  isGlobalMode: true, // 默认全局模式
  totalCount: 0,
  currentPage: 1,
  totalPages: 0,

  // ── Set global mode ──
  setGlobalMode: (enabled: boolean) => {
    set({ isGlobalMode: enabled, tasks: [], error: null });
  },

  // ── Fetch global tasks ──
  fetchGlobalTasks: async (params) => {
    set({ isLoading: true, error: null });
    try {
      const res = await scheduledTasksApi.listGlobal(params);
      set({
        tasks: res.tasks,
        totalCount: res.total,
        currentPage: res.page,
        totalPages: res.total_pages,
        isLoading: false,
      });
    } catch (e: unknown) {
      set({ error: e instanceof Error ? e.message : "加载任务列表失败", isLoading: false });
    }
  },

  // ── Create global task ──
  createGlobalTask: async (data: CreateScheduledTaskGlobalRequest) => {
    const res = await scheduledTasksApi.createGlobal(data);
    // Refresh global list
    await get().fetchGlobalTasks({ page: 1 });
    return res.task;
  },

  // ── Set page ──
  setPage: (page: number) => {
    set({ currentPage: page });
    get().fetchGlobalTasks({ page, page_size: 20 });
  },

  // ── Fetch tasks (per-workspace) ──
  fetchTasks: async (workspaceId: string) => {
    set({ isLoading: true, error: null, selectedWorkspaceId: workspaceId });
    try {
      const res = await scheduledTasksApi.list(workspaceId);
      set({
        tasks: res.tasks,
        schedulerActive: res.scheduler_active,
        isLoading: false,
      });
    } catch (e: unknown) {
      set({ error: e instanceof Error ? e.message : "加载任务列表失败", isLoading: false });
    }
  },

  // ── Create (per-workspace) ──
  createTask: async (workspaceId: string, data: CreateScheduledTaskRequest) => {
    const res = await scheduledTasksApi.create(workspaceId, data);
    // Refresh list
    await get().fetchTasks(workspaceId);
    return res.task;
  },

  // ── Update ──
  updateTask: async (workspaceId: string, taskId: string, updates: Partial<ScheduledTask>) => {
    await scheduledTasksApi.update(workspaceId, taskId, updates);
    if (get().isGlobalMode) {
      await get().fetchGlobalTasks({ page: get().currentPage });
    } else {
      await get().fetchTasks(workspaceId);
    }
  },

  // ── Delete ──
  deleteTask: async (workspaceId: string, taskId: string) => {
    await scheduledTasksApi.delete(workspaceId, taskId);
    // Remove executions cache entry
    const cache = { ...get().executionsCache };
    delete cache[taskId];
    set({ executionsCache: cache });
    if (get().isGlobalMode) {
      await get().fetchGlobalTasks({ page: get().currentPage });
    } else {
      await get().fetchTasks(workspaceId);
    }
  },

  // ── Pause ──
  pauseTask: async (workspaceId: string, taskId: string) => {
    await scheduledTasksApi.pause(workspaceId, taskId);
    // Optimistic update
    set((s) => ({
      tasks: s.tasks.map((t) => (t.task_id === taskId ? { ...t, status: "paused" as const } : t)),
    }));
    if (!get().isGlobalMode) {
      await get().fetchTasks(workspaceId);
    }
  },

  // ── Resume ──
  resumeTask: async (workspaceId: string, taskId: string) => {
    await scheduledTasksApi.resume(workspaceId, taskId);
    set((s) => ({
      tasks: s.tasks.map((t) => (t.task_id === taskId ? { ...t, status: "pending" as const } : t)),
    }));
    if (!get().isGlobalMode) {
      await get().fetchTasks(workspaceId);
    }
  },

  // ── Trigger ──
  triggerTask: async (workspaceId: string, taskId: string) => {
    await scheduledTasksApi.trigger(workspaceId, taskId);
    set((s) => ({
      tasks: s.tasks.map((t) =>
        t.task_id === taskId ? { ...t, status: "triggered" as const } : t,
      ),
    }));
    if (!get().isGlobalMode) {
      await get().fetchTasks(workspaceId);
    }
  },

  // ── Executions ──
  fetchExecutions: async (workspaceId: string, taskId: string, page = 1) => {
    set({ executionsLoading: true });
    try {
      const res = await scheduledTasksApi.getExecutions(workspaceId, taskId, page);
      set((s) => ({
        executionsCache: { ...s.executionsCache, [taskId]: res.executions },
        executionsLoading: false,
      }));
    } catch (e) {
      toastError("加载执行记录失败", e);
      set({ executionsLoading: false });
    }
  },

  // ── Filter ──
  setFilter: (filter) => {
    set((s) => ({
      filterStatus: filter.status !== undefined ? filter.status : s.filterStatus,
      filterScheduleType:
        filter.scheduleType !== undefined ? filter.scheduleType : s.filterScheduleType,
      searchText: filter.search !== undefined ? filter.search : s.searchText,
    }));
  },

  // ── Workspace ──
  setSelectedWorkspace: (id: string | null) => {
    set({ selectedWorkspaceId: id });
  },

  // ── Polling (5s interval) ──
  startPolling: () => {
    get().stopPolling();
    const id = setInterval(() => {
      const { isGlobalMode, selectedWorkspaceId, schedulerActive } = get();
      if (isGlobalMode) {
        get().fetchGlobalTasks({ page: get().currentPage });
      } else if (schedulerActive && selectedWorkspaceId) {
        get().fetchTasks(selectedWorkspaceId);
      }
    }, 5000);
    set({ _pollInterval: id });
  },

  stopPolling: () => {
    const { _pollInterval } = get();
    if (_pollInterval) {
      clearInterval(_pollInterval);
      set({ _pollInterval: null });
    }
  },

  clearError: () => set({ error: null }),
}));
