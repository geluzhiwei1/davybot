/**
 * Monitoring WebSocket integration.
 *
 * Subscribes to the event-bus `ws:message` stream and populates the
 * monitoring store with live data from running agents / task graphs.
 *
 * Lifecycle: call `initMonitoringWs()` once at app startup (e.g. in
 * __root.tsx).  The listener lives for the entire session.
 */

import { on } from "./event-bus";
import { useMonitoringStore } from "./monitoring-store";
import { useSubtaskStore } from "./subtask-store";
import { useTaskStore } from "./task-store";
import { useTodoStore } from "./todo-store";
import type { ParallelTaskInfo } from "./types/parallel-tasks";
import type { SubtaskLifecyclePayload } from "./types/subtask";
import type { TodoItem, TodoStatus, TodoPriority } from "./types/todos";
import { wsClient } from "./ws-client";
import { BIZ_AGENT_STATUS_SINKS } from "./biz-registry";
let initialized = false;
let unsub: (() => void) | null = null;

/** Start listening to WS events for monitoring. Idempotent. */
export function initMonitoringWs(): void {
  if (initialized) return;
  initialized = true;

  unsub = on("ws:message", (detail) => {
    const msg = detail as Record<string, unknown>;
    handleMonitoringMessage(msg);
  });
}

/** Stop listening (primarily for tests / HMR). */
export function shutdownMonitoringWs(): void {
  if (unsub) {
    unsub();
    unsub = null;
  }
  initialized = false;
}

// ── Helpers ────────────────────────────────────────────────

function makeTask(id: string, name: string, priority = 1): ParallelTaskInfo {
  const now = Date.now();
  return {
    id,
    name,
    state: "RUNNING",
    progress: 0,
    priority,
    output: [],
    createdAt: now,
    startedAt: now,
    metrics: { duration: 0, toolCalls: 0, llmCalls: 0, tokensUsed: 0 },
  };
}

// ── Message handler ────────────────────────────────────────

function handleMonitoringMessage(msg: Record<string, unknown>): void {
  const store = useMonitoringStore.getState();
  const type = msg.type as string;

  switch (type) {
    // ── Agent lifecycle ────────────────────────────────────

    case "agent_start": {
      const taskId = msg.task_id as string | undefined;
      if (!taskId || store.parallelTasks.has(taskId)) break;

      const mode = (msg.agent_mode as string) || "Agent";
      store.addParallelTask(makeTask(taskId, mode));
      break;
    }

    case "stream_start": {
      // Each stream-start = one LLM API call
      const taskId = msg.task_id as string | undefined;
      if (taskId && store.parallelTasks.has(taskId)) {
        store.incrementLlmCall(taskId);
      }
      break;
    }

    case "agent_complete": {
      const taskId = msg.task_id as string | undefined;
      if (!taskId) break;
      const existing = store.parallelTasks.get(taskId);
      if (existing && (existing.state === "RUNNING" || existing.state === "PENDING")) {
        store.updateParallelTask(taskId, {
          state: "COMPLETED",
          progress: 100,
          completedAt: Date.now(),
        });
      }
      break;
    }

    case "agent_stopped": {
      const taskId = msg.task_id as string | undefined;
      if (taskId && store.parallelTasks.has(taskId)) {
        store.setParallelTaskState(taskId, "CANCELLED");
      }
      break;
    }

    // ── Task graph nodes (broadcast, no conversation_id) ──

    case "task_node_start": {
      const d = (msg.data as Record<string, unknown>) ?? {};
      const nodeId = (d.task_node_id as string) ?? "";
      if (!nodeId) break;

      if (!store.parallelTasks.has(nodeId)) {
        const name = (d.name as string) ?? (d.task_name as string) ?? "Task Node";
        const priority = (d.priority as number) ?? 1;
        store.addParallelTask(makeTask(nodeId, name, priority));
      } else {
        store.setParallelTaskState(nodeId, "RUNNING");
      }
      break;
    }

    case "task_node_progress": {
      const d = (msg.data as Record<string, unknown>) ?? {};
      const nodeId = (d.task_node_id as string) ?? "";
      if (!nodeId) break;
      const progress = d.progress as number | undefined;
      if (progress != null) {
        store.updateParallelTask(nodeId, { progress });
      }
      break;
    }

    case "task_node_complete": {
      const d = (msg.data as Record<string, unknown>) ?? {};
      const nodeId = (d.task_node_id as string) ?? "";
      if (!nodeId) break;
      const success = d.success !== false;
      store.updateParallelTask(nodeId, {
        state: success ? "COMPLETED" : "FAILED",
        progress: 100,
        completedAt: Date.now(),
      });
      break;
    }

    // ── Subtask lifecycle (§6.3 子任务委派，驱动 subtask-tree 树面板) ──
    // 后端契约：{ type: "subtask_lifecycle", subtask_id, event, status?, parent_id?,
    //            conversation_id?, agent?, depth?, metadata? }（exclude_none）
    case "subtask_lifecycle": {
      const wsId = (msg.workspace_id as string) || wsClient.getWorkspaceId() || "";
      if (!wsId) break;
      useSubtaskStore.getState().applyLifecycle(wsId, msg as unknown as SubtaskLifecyclePayload);
      break;
    }

    // ── §6.3 UI-F：TaskGraph 增量更新（task_status_update / task_graph_update）──
    // 后端契约（engine/agent/dawei/websocket/protocol.py）：
    //   task_status_update: { task_id, graph_id, old_status, new_status, timestamp }
    //   task_graph_update: { graph_id, update_type, data, timestamp }
    // 调研结论（2026-08-24）：两类协议当前在 MessageType 枚举中已声明且
    // validator 注册完毕，但 backend 全仓**零生产发射点**——handler 已就绪
    // 以备 backend P3-6 在 engine 状态变更处 fire-and-forget 广播即自动接入。
    case "task_status_update": {
      const wsId = (msg.workspace_id as string) || wsClient.getWorkspaceId() || "";
      if (!wsId) break;
      const taskId = msg.task_id as string | undefined;
      const newStatus = msg.new_status as string | undefined;
      if (!taskId || !newStatus) break;
      useTaskStore.getState().markNodeStatus(wsId, taskId, newStatus);
      break;
    }

    case "task_graph_update": {
      const wsId = (msg.workspace_id as string) || wsClient.getWorkspaceId() || "";
      if (!wsId) break;
      const updateType = msg.update_type as string | undefined;
      const data = (msg.data as Record<string, unknown>) ?? undefined;
      if (!updateType) break;
      useTaskStore.getState().applyGraphUpdate(wsId, updateType, data);
      break;
    }

    // ── biz 注册的 Agent fleet status(firm/market/social agent 等,assemble 注入;核心构建 = 空表不命中) ──
    // 后端契约：{ type: "<domain>_agent_status", data: { expert_id, status, last_action? } }
    // expert_id 与域内 FLEET_ROSTER 对齐；未知 id 静默忽略。核心构建 = 空表,不命中。
    default: {
      const sink = BIZ_AGENT_STATUS_SINKS.find((s) => s.messageType === type);
      if (!sink) break;
      const d = (msg.data as Record<string, unknown>) ?? {};
      const expertId = (d.expert_id as string) ?? (d.expertId as string) ?? "";
      if (!expertId) break;
      const status = (d.status as string) ?? "idle";
      const lastAction = (d.last_action as string) ?? (d.lastAction as string) ?? undefined;
      sink.setAgentStatus(expertId, status, lastAction);
      break;
    }

    // ── Agent thinking → update last output line ──────────

    case "agent_thinking": {
      const taskId = msg.task_id as string | undefined;
      const content = msg.content as string | undefined;
      if (taskId && content && store.parallelTasks.has(taskId)) {
        store.addParallelTaskOutput(taskId, content.slice(0, 200));
      }
      break;
    }

    // ── Agent pause / resume ──────────────────────────────

    case "agent_pause": {
      const taskId = msg.task_id as string | undefined;
      if (taskId && store.parallelTasks.has(taskId)) {
        store.setParallelTaskState(taskId, "PAUSED");
      }
      break;
    }

    case "agent_resume": {
      const taskId = msg.task_id as string | undefined;
      if (taskId && store.parallelTasks.has(taskId)) {
        store.setParallelTaskState(taskId, "RUNNING");
      }
      break;
    }

    // ── Todo CRUD (broadcast, no conversation_id) ─────────

    case "todo_created": {
      const d = (msg.data as Record<string, unknown>) ?? msg;
      const todoId = d.todo_id as string | undefined;
      if (!todoId) break;
      const todoStore = useTodoStore.getState();
      // Avoid duplicates
      if (todoStore.todos.some((t) => t.id === todoId)) break;
      const todo: TodoItem = {
        id: todoId,
        title: (d.content as string) ?? "Untitled",
        status: "PENDING",
        priority: (d.priority as TodoPriority) ?? "medium",
        taskNodeId: d.task_node_id as string | undefined,
        taskNodeName: d.task_description as string | undefined,
        createdAt: Date.now(),
      };
      todoStore.addTodo(todo);
      break;
    }

    case "todo_updated": {
      const d = (msg.data as Record<string, unknown>) ?? msg;
      const todoId = d.todo_id as string | undefined;
      if (!todoId) break;
      const todoStore = useTodoStore.getState();
      const updates: Partial<TodoItem> = {};
      if (d.status != null) updates.status = d.status as TodoStatus;
      if (d.content != null) updates.title = d.content as string;
      if (d.priority != null) updates.priority = d.priority as TodoPriority;
      if (d.status === "COMPLETED") updates.completedAt = Date.now();
      todoStore.updateTodo(todoId, updates);
      break;
    }

    case "todo_deleted": {
      const d = (msg.data as Record<string, unknown>) ?? msg;
      const todoId = d.todo_id as string | undefined;
      if (!todoId) break;
      useTodoStore.getState().removeTodo(todoId);
      break;
    }

    case "todo_batch_updated": {
      const d = (msg.data as Record<string, unknown>) ?? msg;
      const todoIds = d.todo_ids as string[] | undefined;
      const status = d.status as TodoStatus | undefined;
      if (!todoIds || !status) break;
      const todoStore = useTodoStore.getState();
      for (const id of todoIds) {
        todoStore.setTodoStatus(id, status);
      }
      break;
    }
  }
}
