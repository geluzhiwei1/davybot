/**
 * Subtask store — 子任务委派 §6.3 前端状态中枢。
 *
 * 数据来源：
 * - WS `subtask_lifecycle` 广播 → applyLifecycle()（monitoring-ws 分发，工作区归属
 *   由调用方解析：显式 msg.workspace_id > wsClient.getWorkspaceId()）
 * - WS `subtask_progress` 广播 → applyProgress()（C25/§3.8 todo 步级，纯 UI 态）
 * - REST GET /subtasks bootstrap → restoreFromBootstrap()（重连/首载兜底）
 *
 * 状态机（event → status，msg.status 显式值优先）：
 *   created→pending  started→running  completed→completed  failed→failed
 *   aborted→aborted  steered→保持原状态（仅记录指令）
 *
 * 批次（C16）：new_task_batch 展开的子任务带 batchId/itemIdentity（lifecycle
 * 从 metadata 捕获 / progress 载荷直带 / bootstrap 从 REST 读取），
 * selectBatchGroups() 产出批次聚合视图供进度卡与面板分组渲染。
 */
import { create } from "zustand";
import { on } from "./event-bus";
import { subtaskApi } from "./api/subtask";
import type {
  SubtaskInfo,
  SubtaskLifecycleEventName,
  SubtaskLifecyclePayload,
  SubtaskNode,
  SubtaskProgressPayload,
  SubtaskStatus,
  SubtaskTreeNode,
} from "./types/subtask";

// ── 状态归一化 ───────────────────────────────────────────────────────

/** 后端 TaskStatus 小写值 + graphs 端点历史别名的宽容映射 */
const KNOWN_STATUS: Record<string, SubtaskStatus> = {
  pending: "pending",
  running: "running",
  completed: "completed",
  failed: "failed",
  aborted: "aborted",
  in_progress: "running",
  success: "completed",
  done: "completed",
};

/** event → 默认状态推导（steered 无推导，保持原状态） */
const EVENT_STATUS: Partial<Record<SubtaskLifecycleEventName, SubtaskStatus>> = {
  created: "pending",
  started: "running",
  completed: "completed",
  failed: "failed",
  aborted: "aborted",
};

function normalizeStatus(value: unknown, fallback: SubtaskStatus): SubtaskStatus {
  if (typeof value !== "string") return fallback;
  return KNOWN_STATUS[value.toLowerCase()] ?? fallback;
}

// ── Store ────────────────────────────────────────────────────────────

interface SubtaskStoreState {
  /** per-workspace 子任务扁平表（task_id → node） */
  workspaceSubtasks: Record<string, Record<string, SubtaskNode>>;

  /** UI-C 线程抽屉目标（null = 关闭；单抽屉，后开覆盖先开；focusSteer = 打开后聚焦 steer 输入框） */
  threadDrawer: { workspaceId: string; taskNodeId: string; focusSteer?: boolean } | null;

  // Actions
  /** WS subtask_lifecycle 事件 → upsert（乱序事件自动兜底建节点） */
  applyLifecycle: (workspaceId: string, msg: SubtaskLifecyclePayload) => void;
  /** WS subtask_progress 事件 → upsert todos 步级（乱序先于 lifecycle 到达时建 running 骨架） */
  applyProgress: (workspaceId: string, msg: SubtaskProgressPayload) => void;
  /** REST bootstrap → 整体替换该工作区桶（后端为权威结构） */
  restoreFromBootstrap: (workspaceId: string, subtasks: SubtaskInfo[]) => void;
  clearWorkspace: (workspaceId: string) => void;

  /** 打开子代理线程抽屉（树节点 / 聊天子任务卡片共用；opts.focusSteer 聚焦指令输入框） */
  openThread: (workspaceId: string, taskNodeId: string, opts?: { focusSteer?: boolean }) => void;
  closeThread: () => void;

  // Getters
  getSubtasks: (workspaceId: string) => SubtaskNode[];
  getSubtask: (workspaceId: string, taskId: string) => SubtaskNode | undefined;
}

export const useSubtaskStore = create<SubtaskStoreState>((set, get) => ({
  workspaceSubtasks: {},
  threadDrawer: null,

  openThread: (workspaceId, taskNodeId, opts) =>
    set({
      threadDrawer: {
        workspaceId,
        taskNodeId,
        ...(opts?.focusSteer ? { focusSteer: true } : {}),
      },
    }),
  closeThread: () => set({ threadDrawer: null }),

  applyLifecycle: (workspaceId, m) => {
    const subtaskId = m?.subtask_id;
    if (!subtaskId) return;

    const now = Date.now();
    set((s) => {
      const bucket = s.workspaceSubtasks[workspaceId] ?? {};
      const prev = bucket[subtaskId];

      // 显式 status 优先 → event 推导 → 既有状态 → pending
      const status = normalizeStatus(m.status, EVENT_STATUS[m.event] ?? prev?.status ?? "pending");

      // steered 指令入历史（metadata.message）；缺省字段不回退已记录值
      const steerMessages =
        m.event === "steered" && typeof m.metadata?.message === "string"
          ? [...(prev?.steerMessages ?? []), m.metadata.message]
          : (prev?.steerMessages ?? []);

      const node: SubtaskNode = {
        task_id: subtaskId,
        parent_id: m.parent_id ?? prev?.parent_id ?? null,
        status,
        agent: m.agent ?? prev?.agent ?? null,
        model: prev?.model ?? null,
        mode: prev?.mode ?? null,
        depth: m.depth ?? prev?.depth ?? null,
        conversation_id: m.conversation_id ?? prev?.conversation_id ?? null,
        description: prev?.description ?? "",
        lastEvent: m.event,
        steerMessages,
        batchId: (m.metadata?.batch_id as string | undefined) ?? prev?.batchId ?? null,
        itemIdentity: (m.metadata?.item_identity as string | undefined) ?? prev?.itemIdentity ?? null,
        todos: prev?.todos ?? null,
        createdAt: prev?.createdAt ?? now,
        updatedAt: now,
      };

      return {
        workspaceSubtasks: {
          ...s.workspaceSubtasks,
          [workspaceId]: { ...bucket, [subtaskId]: node },
        },
      };
    });
  },

  applyProgress: (workspaceId, m) => {
    const subtaskId = m?.subtask_id;
    if (!subtaskId || !m.todos) return;

    const now = Date.now();
    set((s) => {
      const bucket = s.workspaceSubtasks[workspaceId] ?? {};
      const prev = bucket[subtaskId];

      const node: SubtaskNode = prev
        ? {
            ...prev,
            // 步级推进 = 已在执行：pending 提升为 running；终态不被迟到的 progress 回退
            status: prev.status === "pending" ? "running" : prev.status,
            batchId: m.batch_id ?? prev.batchId,
            itemIdentity: m.item_identity ?? prev.itemIdentity,
            todos: m.todos,
            updatedAt: now,
          }
        : {
            // 乱序兜底：progress 先于 lifecycle 到达 → 建 running 骨架
            task_id: subtaskId,
            parent_id: m.parent_id ?? null,
            status: "running",
            agent: null,
            model: null,
            mode: null,
            depth: null,
            conversation_id: null,
            description: m.item_identity ?? "",
            lastEvent: null,
            steerMessages: [],
            batchId: m.batch_id ?? null,
            itemIdentity: m.item_identity ?? null,
            todos: m.todos,
            createdAt: now,
            updatedAt: now,
          };

      return {
        workspaceSubtasks: {
          ...s.workspaceSubtasks,
          [workspaceId]: { ...bucket, [subtaskId]: node },
        },
      };
    });
  },

  restoreFromBootstrap: (workspaceId, subtasks) => {
    const now = Date.now();
    const bucket: Record<string, SubtaskNode> = {};
    subtasks.forEach((item, i) => {
      bucket[item.task_id] = {
        task_id: item.task_id,
        parent_id: item.parent_id,
        status: normalizeStatus(item.status, "pending"),
        agent: item.agent,
        model: item.model,
        mode: item.mode,
        depth: item.depth,
        conversation_id: item.conversation_id,
        description: item.description ?? "",
        lastEvent: null,
        steerMessages: [],
        batchId: item.batch_id ?? null,
        itemIdentity: item.item_identity ?? null,
        todos: null, // todo 步级是纯 UI 态，bootstrap 不含 → 等后续 WS 补
        createdAt: now + i, // 保序列表顺序 → 树内子节点排序
        updatedAt: now + i,
      };
    });
    set((s) => ({
      workspaceSubtasks: { ...s.workspaceSubtasks, [workspaceId]: bucket },
    }));
  },

  clearWorkspace: (workspaceId) => {
    set((s) => ({
      workspaceSubtasks: { ...s.workspaceSubtasks, [workspaceId]: {} },
    }));
  },

  getSubtasks: (workspaceId) =>
    Object.values(get().workspaceSubtasks[workspaceId] ?? {}).sort(
      (a, b) => a.createdAt - b.createdAt,
    ),
  getSubtask: (workspaceId, taskId) => get().workspaceSubtasks[workspaceId]?.[taskId],
}));

// ── C22：WS connected/重连 → REST bootstrap 恢复 ─────────────────────
// connection-store 在 connected 时 emit（ws:resync_subtasks）；此处订阅并自行
// 拉取（事件总线解耦，同 ws:resync_history → chat-store 先例）。此前 bootstrap
// 仅在监控树挂载时触发，聊天页刷新后子任务卡片/批次进度静止。
on("ws:resync_subtasks", (detail) => {
  const { wsId } = (detail ?? {}) as { wsId?: string };
  if (!wsId) return;
  subtaskApi
    .list(wsId)
    .then((res) => {
      if (res.success) {
        useSubtaskStore.getState().restoreFromBootstrap(wsId, res.subtasks ?? []);
      }
    })
    .catch((err) => {
      console.error("[Subtask] bootstrap restore failed:", err);
    });
});

// ── 树组装 selector（纯函数，组件与测试共用） ─────────────────────────

/**
 * 扁平节点表 → 树。
 * - 根判定：parent_id 为空，或父节点不在图中（父 = 根任务，后端已排除）
 * - 子节点按 createdAt 升序（WS 到达序 / bootstrap 列表序）
 * - 环引用保护：已访问节点不重复展开；不可达节点上提为裸根，保证可见性
 */
export function selectSubtaskTree(nodes: Record<string, SubtaskNode>): SubtaskTreeNode[] {
  // 按父分组（父不在图中的挂根，不进 children 表）
  const byParent = new Map<string, SubtaskNode[]>();
  for (const node of Object.values(nodes)) {
    const pid = node.parent_id;
    if (pid && nodes[pid]) {
      const list = byParent.get(pid) ?? [];
      list.push(node);
      byParent.set(pid, list);
    }
  }
  for (const list of byParent.values()) {
    list.sort((a, b) => a.createdAt - b.createdAt);
  }

  const visited = new Set<string>();

  const build = (node: SubtaskNode): SubtaskTreeNode => {
    visited.add(node.task_id);
    const treeNode: SubtaskTreeNode = { ...node, children: [] };
    for (const child of byParent.get(node.task_id) ?? []) {
      if (visited.has(child.task_id)) continue; // 环引用保护
      treeNode.children.push(build(child));
    }
    return treeNode;
  };

  const roots: SubtaskTreeNode[] = [];
  for (const node of Object.values(nodes)) {
    const pid = node.parent_id;
    const isRoot = !pid || !nodes[pid];
    if (isRoot && !visited.has(node.task_id)) {
      roots.push(build(node));
    }
  }

  // 不可达节点（纯环）→ 上提为裸根，各自可见且不再展开
  for (const node of Object.values(nodes)) {
    if (!visited.has(node.task_id)) {
      visited.add(node.task_id);
      roots.push({ ...node, children: [] });
    }
  }

  return roots;
}

// ── batch 分组 selector（C16：纯函数，进度卡 / 树面板分组渲染共用） ────

/** 批次终态集合（SubtaskStatus 值域内） */
const BATCH_TERMINAL = new Set<SubtaskStatus>(["completed", "failed", "aborted"]);

/** 批次聚合视图（batchId → 成员 + 汇总；单发子任务不进组） */
export interface SubtaskBatchGroup {
  batchId: string;
  /** 成员按 createdAt 升序（派发展开序） */
  items: SubtaskNode[];
  /** 终态成员数（completed/failed/aborted） */
  done: number;
  completed: number;
  failed: number;
  /** 成员 todo 合计（任一成员上报过才有，否则 null） */
  todos: { total: number; completed: number } | null;
  updatedAt: number;
}

/**
 * 扁平节点表 → 批次分组。
 * - batchId 为 null（new_task 单发 / 未知）的节点不进组（由树视图单独承载）
 * - 组间按 updatedAt 升序（最新活跃批次靠后；渲染层可自行反转）
 */
export function selectBatchGroups(nodes: Record<string, SubtaskNode>): SubtaskBatchGroup[] {
  const groups = new Map<string, SubtaskNode[]>();
  for (const node of Object.values(nodes)) {
    if (!node.batchId) continue;
    const list = groups.get(node.batchId) ?? [];
    list.push(node);
    groups.set(node.batchId, list);
  }

  const result: SubtaskBatchGroup[] = [];
  for (const [batchId, items] of groups) {
    items.sort((a, b) => a.createdAt - b.createdAt);
    let todosTotal = 0;
    let todosCompleted = 0;
    let hasTodos = false;
    for (const it of items) {
      if (it.todos) {
        hasTodos = true;
        todosTotal += it.todos.total;
        todosCompleted += it.todos.completed;
      }
    }
    result.push({
      batchId,
      items,
      done: items.filter((i) => BATCH_TERMINAL.has(i.status)).length,
      completed: items.filter((i) => i.status === "completed").length,
      failed: items.filter((i) => i.status === "failed" || i.status === "aborted").length,
      todos: hasTodos ? { total: todosTotal, completed: todosCompleted } : null,
      updatedAt: Math.max(...items.map((i) => i.updatedAt)),
    });
  }

  result.sort((a, b) => a.updatedAt - b.updatedAt);
  return result;
}
