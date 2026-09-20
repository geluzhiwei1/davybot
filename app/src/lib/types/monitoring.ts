/**
 * Monitoring type definitions.
 */

/** Node status within a task graph execution */
export type NodeStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "SKIPPED" | "CANCELLED";

/** System health metrics */
export interface SystemHealthMetrics {
  cpuUsage: number;
  memoryUsage: number;
  memoryTotal: number;
  memoryUsed: number;
  diskUsage: number;
  networkLatency: number;
  activeConnections: number;
  timestamp: number;
}

/** Task node within an execution */
export interface TaskNodeData {
  id: string;
  label: string;
  status: NodeStatus;
  progress: number;
  startedAt?: number;
  completedAt?: number;
  error?: string;
  todoCount?: number;
  todoCompleted?: number;
}

/** Task graph execution */
export interface TaskGraphExecution {
  id: string;
  name: string;
  status: NodeStatus;
  nodes: Record<string, TaskNodeData>;
  progress: number;
  startedAt: number;
  completedAt?: number;
  totalTokens?: number;
  totalCost?: number;
}

/** Alert severity */
export type AlertSeverity = "info" | "warning" | "error" | "critical";

/** Performance alert */
export interface PerformanceAlert {
  id: string;
  severity: AlertSeverity;
  title: string;
  message: string;
  timestamp: number;
  acknowledged: boolean;
}

/** Monitoring config */
export interface MonitoringConfig {
  refreshInterval: number;
  maxAlerts: number;
  retentionMs: number;
}

/** Log entry */
export interface LogEntry {
  id: string;
  level: "debug" | "info" | "warn" | "error";
  source: string;
  message: string;
  timestamp: number;
  details?: string;
}

/** Cost data */
export interface CostData {
  totalTokens: number;
  totalCost: number;
  inputTokens: number;
  outputTokens: number;
  modelBreakdown: Record<string, { tokens: number; cost: number }>;
}
