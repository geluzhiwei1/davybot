/**
 * Task store — migrated from legalbot/webui/src/stores/task.ts
 * Zustand store for task and TaskGraph management.
 */
import { create } from "zustand";
import { on } from "./event-bus";

interface TaskGraphStats {
  total_tasks: number;
  status_counts: Record<string, number>;
}

export interface TaskGraphNodeData {
  task_id: string;
  description: string;
  mode: string;
  status: string;
  priority: string;
  parent_id: string | null;
  child_ids: string[];
  created_at: string | null;
  updated_at: string | null;
}

export interface TaskGraphData {
  graph_id: string;
  name: string;
  description: string;
  root_task_id: string | null;
  total_tasks: number;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  tasks: TaskGraphNodeData[];
}

interface TaskStoreState {
  // Per-workspace state
  workspaceCurrentTaskId: Record<string, string | null>;
  workspaceTaskGraphData: Record<string, unknown>;
  workspaceTaskGraphStats: Record<string, TaskGraphStats | null>;
  workspaceActiveNodes: Record<string, string[]>;
  workspaceCompletedNodes: Record<string, string[]>;

  // Actions
  startTask: (workspaceId: string, taskId: string) => void;
  completeTask: (workspaceId: string) => void;
  updateNodeProgress: (workspaceId: string, nodeId: string) => void;
  completeNode: (workspaceId: string, nodeId: string) => void;
  updateTaskGraph: (workspaceId: string, data: unknown) => void;
  setTaskGraphData: (workspaceId: string, data: unknown) => void;
  clearTaskGraph: (workspaceId: string) => void;
  /** Restore task graph state from backend API after WS reconnect */
  restoreFromGraph: (workspaceId: string, graph: TaskGraphData) => void;
  /**
   * §6.3 UI-F：将单节点状态迁移写入桶（task_status_update 入口）。
   * active 状态（running/pending/in_progress）→ 入 active；
   * 终态（completed/failed/success/done）→ active→completed；
   * 其他（cancelled/skipped/paused）→ 仅从 active 移除，不入 completed。
   */
  markNodeStatus: (workspaceId: string, nodeId: string, newStatus: string) => void;
  /**
   * §6.3 UI-F：按 update_type 路由任务图增量（task_graph_update 入口）。
   * 已知 node_added / node_updated / node_removed；未知类型 no-op。
   */
  applyGraphUpdate: (
    workspaceId: string,
    updateType: string,
    data: Record<string, unknown> | undefined,
  ) => void;

  // Getters
  getCurrentTaskId: (workspaceId: string) => string | null;
  getTaskGraphData: (workspaceId: string) => unknown;
  getTaskGraphStats: (workspaceId: string) => TaskGraphStats | null;
  getActiveNodes: (workspaceId: string) => string[];
  getCompletedNodes: (workspaceId: string) => string[];
  hasActiveTask: (workspaceId: string) => boolean;
  getTaskProgress: (workspaceId: string) => number;
}

export const useTaskStore = create<TaskStoreState>((set, get) => ({
  workspaceCurrentTaskId: {},
  workspaceTaskGraphData: {},
  workspaceTaskGraphStats: {},
  workspaceActiveNodes: {},
  workspaceCompletedNodes: {},

  startTask: (workspaceId, taskId) => {
    set((s) => ({
      workspaceCurrentTaskId: { ...s.workspaceCurrentTaskId, [workspaceId]: taskId },
    }));
  },

  completeTask: (workspaceId) => {
    set((s) => ({
      workspaceCurrentTaskId: { ...s.workspaceCurrentTaskId, [workspaceId]: null },
    }));
  },

  updateNodeProgress: (workspaceId, nodeId) => {
    set((s) => {
      const current = s.workspaceActiveNodes[workspaceId] || [];
      if (current.includes(nodeId)) return s;
      return {
        workspaceActiveNodes: { ...s.workspaceActiveNodes, [workspaceId]: [...current, nodeId] },
      };
    });
  },

  completeNode: (workspaceId, nodeId) => {
    set((s) => {
      const active = (s.workspaceActiveNodes[workspaceId] || []).filter((id) => id !== nodeId);
      const completed = s.workspaceCompletedNodes[workspaceId] || [];
      if (completed.includes(nodeId)) {
        return { workspaceActiveNodes: { ...s.workspaceActiveNodes, [workspaceId]: active } };
      }
      return {
        workspaceActiveNodes: { ...s.workspaceActiveNodes, [workspaceId]: active },
        workspaceCompletedNodes: {
          ...s.workspaceCompletedNodes,
          [workspaceId]: [...completed, nodeId],
        },
      };
    });
  },

  updateTaskGraph: (workspaceId, data) => {
    set((s) => {
      const update = data as { statistics?: TaskGraphStats };
      if (update?.statistics) {
        return {
          workspaceTaskGraphStats: {
            ...s.workspaceTaskGraphStats,
            [workspaceId]: update.statistics,
          },
        };
      }
      return s;
    });
  },

  setTaskGraphData: (workspaceId, data) => {
    set((s) => ({
      workspaceTaskGraphData: { ...s.workspaceTaskGraphData, [workspaceId]: data },
    }));
  },

  clearTaskGraph: (workspaceId) => {
    set((s) => ({
      workspaceCurrentTaskId: { ...s.workspaceCurrentTaskId, [workspaceId]: null },
      workspaceTaskGraphData: { ...s.workspaceTaskGraphData, [workspaceId]: null },
      workspaceTaskGraphStats: { ...s.workspaceTaskGraphStats, [workspaceId]: null },
      workspaceActiveNodes: { ...s.workspaceActiveNodes, [workspaceId]: [] },
      workspaceCompletedNodes: { ...s.workspaceCompletedNodes, [workspaceId]: [] },
    }));
  },

  restoreFromGraph: (workspaceId, graph) => {
    const { tasks } = graph;

    // Classify nodes by status
    const activeNodes: string[] = [];
    const completedNodes: string[] = [];
    const statusCounts: Record<string, number> = {};

    for (const t of tasks) {
      statusCounts[t.status] = (statusCounts[t.status] || 0) + 1;
      if (t.status === "running" || t.status === "pending" || t.status === "in_progress") {
        activeNodes.push(t.task_id);
      } else if (t.status === "completed" || t.status === "success" || t.status === "done") {
        completedNodes.push(t.task_id);
      }
    }

    set((s) => ({
      workspaceTaskGraphData: { ...s.workspaceTaskGraphData, [workspaceId]: graph },
      workspaceActiveNodes: { ...s.workspaceActiveNodes, [workspaceId]: activeNodes },
      workspaceCompletedNodes: { ...s.workspaceCompletedNodes, [workspaceId]: completedNodes },
      workspaceTaskGraphStats: {
        ...s.workspaceTaskGraphStats,
        [workspaceId]: {
          total_tasks: tasks.length,
          status_counts: statusCounts,
        },
      },
    }));
  },

  // ── §6.3 UI-F：WS 增量入口 ──────────────────────────────────────
  // 后端 MessageType.TASK_STATUS_UPDATE / TASK_GRAPH_UPDATE 当前在
  // protocol.py 枚举中已声明但**零生产发射点**（仅 enum/validator 注册），
  // handler 已就绪以备 backend P3-6 在 engine 状态变更处接入。

  markNodeStatus: (workspaceId, nodeId, newStatus) => {
    const lc = newStatus.toLowerCase();
    const isTerminal = lc === "completed" || lc === "failed" || lc === "success" || lc === "done";
    const isActive = lc === "running" || lc === "pending" || lc === "in_progress";
    if (isTerminal) {
      // 复用既有 completeNode（active → completed；幂等）
      get().completeNode(workspaceId, nodeId);
      return;
    }
    if (isActive) {
      get().updateNodeProgress(workspaceId, nodeId);
      return;
    }
    // cancelled / skipped / paused / 其他：仅从 active 移除，不入 completed
    set((s) => {
      const active = (s.workspaceActiveNodes[workspaceId] || []).filter((id) => id !== nodeId);
      return {
        workspaceActiveNodes: { ...s.workspaceActiveNodes, [workspaceId]: active },
      };
    });
  },

  applyGraphUpdate: (workspaceId, updateType, data) => {
    const d = data ?? {};
    switch (updateType) {
      case "node_added": {
        const taskId = d.task_id as string | undefined;
        if (!taskId) return;
        const status = (d.status as string) ?? "pending";
        get().markNodeStatus(workspaceId, taskId, status);
        return;
      }
      case "node_updated": {
        const taskId = d.task_id as string | undefined;
        const status = d.status as string | undefined;
        if (!taskId || !status) return;
        get().markNodeStatus(workspaceId, taskId, status);
        return;
      }
      case "node_removed": {
        const taskId = d.task_id as string | undefined;
        if (!taskId) return;
        set((s) => ({
          workspaceActiveNodes: {
            ...s.workspaceActiveNodes,
            [workspaceId]: (s.workspaceActiveNodes[workspaceId] || []).filter(
              (id) => id !== taskId,
            ),
          },
          workspaceCompletedNodes: {
            ...s.workspaceCompletedNodes,
            [workspaceId]: (s.workspaceCompletedNodes[workspaceId] || []).filter(
              (id) => id !== taskId,
            ),
          },
        }));
        return;
      }
      // 未知 update_type → 静默 no-op（避免广播噪声扩散到前端）
    }
  },

  getCurrentTaskId: (workspaceId) => get().workspaceCurrentTaskId[workspaceId] ?? null,
  getTaskGraphData: (workspaceId) => get().workspaceTaskGraphData[workspaceId],
  getTaskGraphStats: (workspaceId) => get().workspaceTaskGraphStats[workspaceId] ?? null,
  getActiveNodes: (workspaceId) => get().workspaceActiveNodes[workspaceId] ?? [],
  getCompletedNodes: (workspaceId) => get().workspaceCompletedNodes[workspaceId] ?? [],
  hasActiveTask: (workspaceId) => !!get().workspaceCurrentTaskId[workspaceId],
  getTaskProgress: (workspaceId) => {
    const stats = get().workspaceTaskGraphStats[workspaceId];
    if (!stats) return 0;
    const total = stats.total_tasks || 0;
    const completed = stats.status_counts?.completed || 0;
    return total > 0 ? (completed / total) * 100 : 0;
  },
}));

// ── Event bus subscriptions (decoupled from connection-store) ───────

on("ws:graph_restored", (detail) => {
  const { wsId, graph } = detail as { wsId: string; graph: TaskGraphData };
  useTaskStore.getState().restoreFromGraph(wsId, graph);
});

// agent_start 携带后端真实执行态 task_id（每条消息一个 uuid，与 _active_agents 键一致）。
// 记录到 workspaceCurrentTaskId，供 floating-input.handleStop 精确停止当前运行的 agent，
// 而不是兜底发 conversation_id 导致后端查不到活跃任务。
on("ws:agent_start", (detail) => {
  const { wsId, taskId } = detail as { wsId: string; taskId?: string };
  if (wsId && taskId) {
    useTaskStore.getState().startTask(wsId, taskId);
  }
});
