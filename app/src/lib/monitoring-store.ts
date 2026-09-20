/**
 * Monitoring dashboard Zustand store.
 * Consolidated: includes parallel tasks (merged from parallel-tasks-store).
 */

import { create } from "zustand";
import type {
  SystemHealthMetrics,
  TaskGraphExecution,
  PerformanceAlert,
  LogEntry,
  CostData,
} from "@/lib/types/monitoring";
import type {
  ParallelTaskInfo,
  ParallelTaskState,
  ParallelTasksStats,
} from "@/lib/types/parallel-tasks";

interface MonitoringState {
  // Connection state
  isConnected: boolean;

  // Metrics
  systemMetrics: SystemHealthMetrics | null;

  // Task executions
  activeExecutions: TaskGraphExecution[];

  // Alerts
  alerts: PerformanceAlert[];

  // Logs
  logs: LogEntry[];

  // Cost tracking
  costData: CostData | null;

  // Parallel tasks (merged from parallel-tasks-store)
  parallelTasks: Map<string, ParallelTaskInfo>;
  maxParallel: number;

  // Actions — monitoring
  setConnected: (connected: boolean) => void;
  updateMetrics: (metrics: SystemHealthMetrics) => void;
  addExecution: (execution: TaskGraphExecution) => void;
  updateExecution: (id: string, updates: Partial<TaskGraphExecution>) => void;
  removeExecution: (id: string) => void;
  addAlert: (alert: PerformanceAlert) => void;
  acknowledgeAlert: (id: string) => void;
  clearAlerts: () => void;
  addLog: (log: LogEntry) => void;
  clearLogs: () => void;
  updateCost: (cost: CostData) => void;

  // Actions — parallel tasks
  addParallelTask: (task: ParallelTaskInfo) => void;
  updateParallelTask: (id: string, updates: Partial<ParallelTaskInfo>) => void;
  removeParallelTask: (id: string) => void;
  setParallelTaskState: (id: string, taskState: ParallelTaskState) => void;
  addParallelTaskOutput: (id: string, line: string) => void;
  clearParallelTaskOutput: (id: string) => void;
  incrementToolCall: (taskId: string) => void;
  incrementLlmCall: (taskId: string) => void;
}

export const useMonitoringStore = create<MonitoringState>((set) => ({
  // Initial state — monitoring
  isConnected: false,
  systemMetrics: null,
  activeExecutions: [],
  alerts: [],
  logs: [],
  costData: null,

  // Initial state — parallel tasks
  parallelTasks: new Map<string, ParallelTaskInfo>(),
  maxParallel: 2,

  // Actions — monitoring
  setConnected: (connected) => set({ isConnected: connected }),

  updateMetrics: (metrics) => set({ systemMetrics: metrics }),

  addExecution: (execution) =>
    set((state) => ({
      activeExecutions: [...state.activeExecutions, execution],
    })),

  updateExecution: (id, updates) =>
    set((state) => ({
      activeExecutions: state.activeExecutions.map((exec) =>
        exec.id === id ? { ...exec, ...updates } : exec,
      ),
    })),

  removeExecution: (id) =>
    set((state) => ({
      activeExecutions: state.activeExecutions.filter((exec) => exec.id !== id),
    })),

  addAlert: (alert) =>
    set((state) => ({
      alerts: [...state.alerts, alert],
    })),

  acknowledgeAlert: (id) =>
    set((state) => ({
      alerts: state.alerts.map((alert) =>
        alert.id === id ? { ...alert, acknowledged: true } : alert,
      ),
    })),

  clearAlerts: () => set({ alerts: [] }),

  addLog: (log) =>
    set((state) => ({
      logs: [...state.logs, log],
    })),

  clearLogs: () => set({ logs: [] }),

  updateCost: (cost) => set({ costData: cost }),

  // Actions — parallel tasks
  addParallelTask: (task) =>
    set((state) => {
      const newTasks = new Map(state.parallelTasks);
      newTasks.set(task.id, task);
      return { parallelTasks: newTasks };
    }),

  updateParallelTask: (id, updates) =>
    set((state) => {
      const newTasks = new Map(state.parallelTasks);
      const existing = newTasks.get(id);
      if (existing) {
        newTasks.set(id, { ...existing, ...updates });
      }
      return { parallelTasks: newTasks };
    }),

  removeParallelTask: (id) =>
    set((state) => {
      const newTasks = new Map(state.parallelTasks);
      newTasks.delete(id);
      return { parallelTasks: newTasks };
    }),

  setParallelTaskState: (id, taskState) =>
    set((state) => {
      const newTasks = new Map(state.parallelTasks);
      const existing = newTasks.get(id);
      if (existing) {
        newTasks.set(id, { ...existing, state: taskState });
      }
      return { parallelTasks: newTasks };
    }),

  addParallelTaskOutput: (id, line) =>
    set((state) => {
      const newTasks = new Map(state.parallelTasks);
      const existing = newTasks.get(id);
      if (existing) {
        newTasks.set(id, {
          ...existing,
          output: [...existing.output, line],
        });
      }
      return { parallelTasks: newTasks };
    }),

  clearParallelTaskOutput: (id) =>
    set((state) => {
      const newTasks = new Map(state.parallelTasks);
      const existing = newTasks.get(id);
      if (existing) {
        newTasks.set(id, { ...existing, output: [] });
      }
      return { parallelTasks: newTasks };
    }),

  incrementToolCall: (taskId) =>
    set((state) => {
      const newTasks = new Map(state.parallelTasks);
      const existing = newTasks.get(taskId);
      if (existing) {
        const metrics = existing.metrics ?? {
          duration: 0,
          toolCalls: 0,
          llmCalls: 0,
          tokensUsed: 0,
        };
        newTasks.set(taskId, {
          ...existing,
          metrics: { ...metrics, toolCalls: metrics.toolCalls + 1 },
        });
      }
      return { parallelTasks: newTasks };
    }),

  incrementLlmCall: (taskId) =>
    set((state) => {
      const newTasks = new Map(state.parallelTasks);
      const existing = newTasks.get(taskId);
      if (existing) {
        const metrics = existing.metrics ?? {
          duration: 0,
          toolCalls: 0,
          llmCalls: 0,
          tokensUsed: 0,
        };
        newTasks.set(taskId, {
          ...existing,
          metrics: { ...metrics, llmCalls: metrics.llmCalls + 1 },
        });
      }
      return { parallelTasks: newTasks };
    }),
}));

/**
 * Computed helper to get parallel task statistics.
 */
export function getParallelTasksStats(state: {
  parallelTasks: Map<string, ParallelTaskInfo>;
}): ParallelTasksStats {
  const tasks = Array.from(state.parallelTasks.values());
  return {
    total: tasks.length,
    active: tasks.filter((t) => t.state === "RUNNING" || t.state === "PAUSED").length,
    completed: tasks.filter((t) => t.state === "COMPLETED").length,
    failed: tasks.filter((t) => t.state === "FAILED").length,
    pending: tasks.filter((t) => t.state === "PENDING").length,
  };
}

/**
 * Re-export for backward compatibility.
 * Components importing from parallel-tasks-store will be migrated to useMonitoringStore.
 */
export { useMonitoringStore as useParallelTasksStore };
