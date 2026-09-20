/**
 * Parallel tasks type definitions.
 */

export type ParallelTaskState =
  "PENDING" | "RUNNING" | "PAUSED" | "COMPLETED" | "FAILED" | "CANCELLED" | "SKIPPED";

export interface ParallelTaskMetrics {
  duration: number;
  toolCalls: number;
  llmCalls: number;
  tokensUsed: number;
}

export interface ParallelTaskInfo {
  id: string;
  name: string;
  state: ParallelTaskState;
  progress: number;
  priority: number;
  agentId?: string;
  agentName?: string;
  output: string[];
  error?: string;
  createdAt: number;
  startedAt?: number;
  completedAt?: number;
  metrics?: ParallelTaskMetrics;
}

export interface ParallelTasksStats {
  total: number;
  active: number;
  completed: number;
  failed: number;
  pending: number;
}
