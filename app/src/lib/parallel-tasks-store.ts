/**
 * Parallel tasks store — DEPRECATED.
 * Merged into useMonitoringStore (monitoring-store.ts).
 * This file re-exports for backward compatibility only.
 */
export {
  useMonitoringStore as useParallelTasksStore,
  getParallelTasksStats as getTasksStats,
} from "./monitoring-store";
