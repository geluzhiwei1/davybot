/**
 * Todo type definitions.
 */

export type TodoStatus = "PENDING" | "IN_PROGRESS" | "COMPLETED";
export type TodoPriority = "low" | "medium" | "high" | "critical";

export interface TodoItem {
  id: string;
  title: string;
  description?: string;
  status: TodoStatus;
  priority: TodoPriority;
  taskNodeId?: string;
  taskNodeName?: string;
  createdAt: number;
  completedAt?: number;
  assignee?: string;
}

export interface TodoGroup {
  taskNodeId: string;
  taskNodeName: string;
  todos: TodoItem[];
}

export interface TodoStatistics {
  total: number;
  pending: number;
  inProgress: number;
  completed: number;
  completionRate: number;
}
