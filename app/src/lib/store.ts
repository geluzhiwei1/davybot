import { toastError, ApiError } from "./api/client.js";
import { create } from "zustand";
import { nanoid } from "nanoid";
import { toast } from "sonner";
import { STORAGE_KEYS } from "./env";
import { useChatStore } from "./chat-store";
import {
  workspaceApi,
  collectionApi,
  conversationApi,
  llmApi,
  workspaceResourceApi,
  type CollectionItem,
} from "./api-client";
import { listGatewayModels } from "./llm-gateway-service";

/** Map backend CollectionItem (snake_case) → frontend WorkspaceCollection (camelCase) */
function mapCollectionItem(c: CollectionItem): WorkspaceCollection {
  return {
    id: c.id,
    name: c.name,
    description: c.description || "",
    workspaceIds: c.workspace_ids || [],
    createdAt: c.created_at,
    updatedAt: c.updated_at,
  };
}

// ── Chat input preference persistence ─────────────────────────────
// These keys remember the user's last selections (model, mode)
// so they carry over across task creation and page reloads.
// NOTE: expert 刻意不缓存——expert 是领域身份而非通用偏好，预盖章会绕过
// Orchestrator 路由，且曾跨工作区泄漏（SocialAgent 污染综述工作区）。

const LS_KEYS = {
  lastModel: STORAGE_KEYS.lastModel,
  lastMode: STORAGE_KEYS.lastMode,
} as const;

export function getSavedPrefs(): { model?: string; mode?: "single" | "team" } {
  try {
    const model = localStorage.getItem(LS_KEYS.lastModel) || undefined;
    const modeRaw = localStorage.getItem(LS_KEYS.lastMode);
    const mode = modeRaw === "single" || modeRaw === "team" ? modeRaw : undefined;
    return { model, mode };
  } catch {
    return {};
  }
}

function savePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* no-op */
  }
}

export interface Message {
  id: string;
  role: "user" | "agent";
  agentId?: string;
  agentName?: string;
  content: string;
  ts: number;
}

/**
 * Task = Conversation in the backend.
 * - id: backend conversation ID (UUID) or local nanoid for temporary tasks
 * - workspaceId: null for temporary tasks (not yet saved to backend)
 * - messages: stored in chat-store (WebSocket-driven), only title/metadata here
 */
export interface Task {
  id: string;
  title: string;
  workspaceId: string | null; // null => temporary task
  messages: Message[];
  mode?: "single" | "team";
  expertId?: string;
  model?: string;
  createdAt: number;
  updatedAt: number;
  /** 会话类别："subtask" = 编排器自动创建的子任务会话（非用户直接创建） */
  taskType?: string;
  /** 子任务会话归属的父（主）会话 id；null = 无父，平铺兜底展示 */
  parentConversationId?: string | null;
}

export type FileKind = "upload" | "ai";

export interface WorkspaceFile {
  id: string;
  name: string;
  kind: FileKind;
}

/** A mode installed in a workspace (from GET /api/workspaces/{id}/resources) */
export interface WorkspaceMode {
  slug: string;
  name: string;
  description: string;
  source: string;
}

export interface Workspace {
  id: string;
  name: string;
  files: WorkspaceFile[];
  createdAt: number;
  /** Generic workspace type identifier, e.g. "ip-draft", "sanctions" */
  workspaceType?: string;
  /** Backend lifecycle: "temporary" (quick-chat/temp) vs persistent */
  lifecycle?: string;
  /** deep-research 流水线 slug（来自注册元数据 deep_research.pipeline，task 页直连用） */
  deepResearchPipeline?: string;
  /** Generic metadata slot, available to any module */
  metadata?: Record<string, unknown>;
  /** Modes installed in this workspace */
  modes?: WorkspaceMode[];
  modesLoading?: boolean;
  modesLoaded?: boolean;
  /** agent slug → mode slugs（安装时各 agent 的 modes.yaml 归属，供专家下拉按入口专家所属 agent 过滤） */
  agentModes?: Record<string, string[]>;
}

export interface WorkspaceCollection {
  id: string;
  name: string;
  description: string;
  workspaceIds: string[];
  createdAt: string;
  updatedAt: string;
}

export type AutomationFrequency = "daily" | "interval" | "once";

export interface LLMModel {
  id: string;
  name: string;
  displayName?: string;
  provider?: string;
  /** 模型来源：official=官方/网关(系统内置,按积分计费)；local=用户自配 Key */
  source?: "official" | "local";
  /** 仅 local：provider 配置名，用于后端精确路由本地 provider（避免靠 model id 猜测） */
  configName?: string;
  /** 仅官方模型：定价（积分/1K tokens） */
  pricing?: { inputRate: number; outputRate: number };
  /** 仅官方模型：是否支持视觉 */
  supportsVision?: boolean;
}

/**
 * 展示排序：官方模型排在前，本地模型排在后。
 * 仅用于 UI 展示顺序（如“切换模型”下拉），不影响默认模型选择（仍取 models[0]）。
 */
export function modelsOfficialFirst(models: LLMModel[]): LLMModel[] {
  return [...models].sort((a, b) => {
    const ao = a.source === "official" ? 0 : 1;
    const bo = b.source === "official" ? 0 : 1;
    return ao - bo;
  });
}

/**
 * 选择默认模型：官方优先（网关返回顺序即后端 priority 排序），无官方时退化到第一个本地模型。
 * 用于首次访问 / 清缓存后（localStorage 无偏好）自动设定默认模型，
 * 避免用户面对禁用的发送按钮、或对话引导因 !task.model 而静默失败。
 */
export function pickDefaultModel(models: LLMModel[]): LLMModel | undefined {
  return modelsOfficialFirst(models)[0];
}

export interface State {
  workspaces: Workspace[];
  /** true once fetchWorkspaces() has succeeded at least once (for route guards) */
  workspacesLoaded: boolean;
  collections: WorkspaceCollection[];
  tasks: Task[];
  models: LLMModel[];
  loading: boolean;
  error: string | null;

  // Transient UI signals
  filesDrawerFor: string | null;
  pendingInsert: { taskId: string; text: string } | null;
  setFilesDrawerFor: (workspaceId: string | null) => void;
  requestInsert: (taskId: string, text: string) => void;
  consumeInsert: (taskId: string) => string | null;

  // Drawer state
  activeDrawer: string | null;
  setActiveDrawer: (drawer: string | null) => void;

  // Data fetching from backend
  fetchWorkspaces: () => Promise<void>;
  fetchCollections: () => Promise<void>;
  fetchModels: () => Promise<void>;
  fetchTasksForWorkspace: (workspaceId: string) => Promise<void>;
  fetchInitialData: () => Promise<void>;

  createWorkspace: (opts: {
    /** 可选：不传时后端按 owner/tenant 分配独立目录（web 端账号隔离的推荐方式） */
    path?: string;
    name?: string;
    displayName?: string;
    description?: string;
    teamId?: string | null;
    teamMeta?: Record<string, unknown> | null;
    skillIds?: string[];
    agentIds?: string[];
    mcpIds?: string[];
    knowledgeIds?: string[];
  }) => Promise<Workspace>;
  renameWorkspace: (id: string, name: string) => void;
  deleteWorkspace: (id: string) => Promise<void>;
  /**
   * 清空工作区（危险操作）：调用后端 reset 清除任务/日志/文件，
   * 同步清除本地任务与消息缓存，然后创建一个空任务返回（等同新建状态）。
   */
  clearWorkspace: (workspaceId: string) => Promise<Task | null>;
  addFile: (workspaceId: string, name: string, kind?: FileKind) => void;

  // Collection CRUD (via backend API)
  createCollection: (
    name: string,
    description?: string,
    workspaceIds?: string[],
  ) => Promise<WorkspaceCollection>;
  updateCollection: (id: string, patch: { name?: string; description?: string }) => Promise<void>;
  deleteCollection: (id: string) => Promise<void>;
  addWorkspacesToCollection: (collectionId: string, workspaceIds: string[]) => Promise<void>;
  removeWorkspacesFromCollection: (collectionId: string, workspaceIds: string[]) => Promise<void>;

  createTask: (opts: {
    workspaceId: string | null;
    title?: string;
    expertId?: string;
  }) => Promise<Task>;
  getOrCreateEmptyTask: (opts: { workspaceId: string | null; expertId?: string }) => Promise<Task>;
  renameTask: (id: string, title: string) => void;
  deleteTask: (id: string) => void;
  moveTask: (id: string, workspaceId: string | null) => void;
  addMessage: (taskId: string, msg: Omit<Message, "id" | "ts">) => void;
  setTaskMode: (id: string, mode: "single" | "team") => void;
  setTaskModel: (id: string, model: string | undefined) => void;
  setTaskExpert: (id: string, expertId: string | undefined) => void;
  /** Add/update a workspace directly (for externally-created IP workspaces) */
  upsertWorkspace: (ws: Workspace) => void;
  /** Add/update a task directly (for externally-created IP tasks) */
  upsertTask: (task: Task) => void;

  /** Fetch modes/resources installed in a workspace */
  fetchWorkspaceResources: (workspaceId: string) => Promise<void>;
}

/** Prevent concurrent fetchTasksForWorkspace calls for the same workspace */
const workspaceTaskFetching = new Set<string>();

// Workspace rename persistence debounce (trailing, per workspace id).
// Some UIs (settings drawer General tab) call renameWorkspace on every keystroke;
// the trailing debounce collapses them into a single PUT /api/workspaces/{id}.
const wsRenameTimers = new Map<string, ReturnType<typeof setTimeout>>();
const WS_RENAME_DEBOUNCE_MS = 600;

export const useStore = create<State>()((set, get) => ({
  workspaces: [],
  workspacesLoaded: false,
  collections: [],
  tasks: [],
  models: [],
  loading: false,
  error: null,

  filesDrawerFor: null,
  pendingInsert: null,
  activeDrawer: null,
  setFilesDrawerFor: (workspaceId) => set({ filesDrawerFor: workspaceId }),
  setActiveDrawer: (drawer) => set({ activeDrawer: drawer }),
  requestInsert: (taskId, text) => set({ pendingInsert: { taskId, text } }),
  consumeInsert: (taskId) => {
    const p = get().pendingInsert;
    if (p && p.taskId === taskId) {
      set({ pendingInsert: null });
      return p.text;
    }
    return null;
  },

  // ── Fetch real data from backend ──────────────────────────────
  fetchWorkspaces: async () => {
    try {
      const data = await workspaceApi.list();
      if (data.success && data.workspaces) {
        const workspaces: Workspace[] = data.workspaces.map((w) => ({
          id: w.id,
          name: w.display_name || w.name,
          files: [],
          createdAt: new Date(w.created_at).getTime(),
          workspaceType: w.workspace_type,
          lifecycle: w.lifecycle,
          deepResearchPipeline: w.deep_research?.pipeline,
        }));
        // 按创建时间降序（最新在前）—— 后端 /list 不保证顺序
        workspaces.sort((a, b) => b.createdAt - a.createdAt);
        set({ workspaces, workspacesLoaded: true });
      }
    } catch (e) {
      console.error("[Store] fetchWorkspaces failed:", e);
      toastError("加载工作区失败", e);
    }
  },

  fetchCollections: async () => {
    try {
      const data = await collectionApi.list();
      if (data.success && data.collections) {
        const collections: WorkspaceCollection[] = data.collections.map(mapCollectionItem);
        set({ collections });
      }
    } catch (e) {
      console.error("[Store] fetchCollections failed:", e);
      toastError("加载收藏夹失败", e);
    }
  },

  createCollection: async (name, description = "", workspaceIds = []) => {
    const data = await collectionApi.create({
      name,
      description,
      workspace_ids: workspaceIds,
    });
    const collection = mapCollectionItem(data.collection);
    set((s) => ({ collections: [...s.collections, collection] }));
    return collection;
  },

  updateCollection: async (id, patch) => {
    const data = await collectionApi.update(id, patch);
    const c = data.collection;
    set((s) => ({
      collections: s.collections.map((col) =>
        col.id === id
          ? { ...col, name: c.name, description: c.description || "", updatedAt: c.updated_at }
          : col,
      ),
    }));
  },

  deleteCollection: async (id) => {
    await collectionApi.delete(id);
    set((s) => ({ collections: s.collections.filter((c) => c.id !== id) }));
  },

  addWorkspacesToCollection: async (collectionId, workspaceIds) => {
    const data = await collectionApi.addWorkspaces(collectionId, workspaceIds);
    const c = data.collection;
    set((s) => ({
      collections: s.collections.map((col) =>
        col.id === collectionId
          ? { ...col, workspaceIds: c.workspace_ids || [], updatedAt: c.updated_at }
          : col,
      ),
    }));
  },

  removeWorkspacesFromCollection: async (collectionId, workspaceIds) => {
    const data = await collectionApi.removeWorkspaces(collectionId, workspaceIds);
    const c = data.collection;
    set((s) => ({
      collections: s.collections.map((col) =>
        col.id === collectionId
          ? { ...col, workspaceIds: c.workspace_ids || [], updatedAt: c.updated_at }
          : col,
      ),
    }));
  },

  fetchModels: async () => {
    // 本地模型（用户自配 Key）—— 来自 nn-bot 后端 /api/llms
    let localModels: LLMModel[] = [];
    try {
      const data = await llmApi.listGlobalModels();
      if (data.availableLLMs) {
        localModels = data.availableLLMs.map(
          (m: {
            id: string;
            name: string;
            displayName?: string;
            provider?: string;
            configName?: string;
          }) => ({
            id: m.id,
            name: m.displayName || m.name,
            displayName: m.displayName,
            provider: m.provider,
            configName: m.configName,
            source: "local" as const,
          }),
        );
      }
    } catch (e) {
      console.error("[Store] fetchModels (local) failed:", e);
      toastError("加载模型列表失败", e);
    }

    // 官方模型（系统内置/网关，按积分计费）—— best-effort，网关不可达时静默降级
    let officialModels: LLMModel[] = [];
    try {
      const gw = await listGatewayModels();
      officialModels = gw.map((m) => ({
        id: m.id,
        name: m.display_name || m.id,
        displayName: m.display_name,
        provider: m.provider,
        source: "official" as const,
        pricing: m.pricing
          ? { inputRate: m.pricing.input_rate, outputRate: m.pricing.output_rate }
          : undefined,
        supportsVision: m.supports_vision,
      }));
    } catch (e) {
      // 网关未联调/未登录时不应阻塞本地模型展示
      console.warn("[Store] fetchModels (official/gateway) skipped:", e);
    }

    // 合并去重（按 id；同 id 时本地自配 Key 优先，覆盖官方默认）
    const seen = new Set<string>();
    const merged: LLMModel[] = [];
    for (const m of [...localModels, ...officialModels]) {
      if (seen.has(m.id)) continue;
      seen.add(m.id);
      merged.push(m);
    }
    set({ models: merged });

    // 首次访问 / 清缓存后（localStorage 无 model 偏好）自动选默认官方模型，
    // 避免对话引导因 !task.model 静默失败、发送按钮禁用。
    const prefs = getSavedPrefs();
    if (!prefs.model && merged.length > 0) {
      const dm = pickDefaultModel(merged);
      if (dm) {
        savePref(LS_KEYS.lastModel, dm.id);
        // 同步给所有 model 尚未设置的 task
        set((s) => ({
          tasks: s.tasks.map((t) => (t.model ? t : { ...t, model: dm.id })),
        }));
      }
    }
  },

  /**
   * Fetch conversations from backend and merge into tasks array.
   * Backend: GET /api/workspaces/{id}/conversations
   * Each conversation becomes a Task with the conversation's backend ID.
   */
  fetchTasksForWorkspace: async (workspaceId: string) => {
    // Prevent concurrent calls for the same workspace (causes duplicate task keys)
    if (workspaceTaskFetching.has(workspaceId)) return;
    workspaceTaskFetching.add(workspaceId);
    try {
      const data = await conversationApi.list(workspaceId);
      // API returns array of conversations directly or under a key
      const conversations = Array.isArray(data) ? data : (data.conversations ?? []);
      if (conversations.length === 0) return;

      const saved = getSavedPrefs();
      const backendTasks: Task[] = conversations.map(
        (c: {
          id?: string;
          conversation_id?: string;
          title?: string;
          name?: string;
          created_at?: string;
          updated_at?: string;
          task_type?: string;
          parent_conversation_id?: string | null;
        }) => ({
          id: c.id || c.conversation_id || nanoid(10),
          title: c.title || c.name || "对话",
          workspaceId,
          messages: [], // Messages come via WebSocket in chat-store
          // Backend conversation listing doesn't include model/mode fields;
          // use saved user preference if available, otherwise leave undefined.
          mode: saved.mode,
          model: saved.model,
          createdAt: c.created_at ? new Date(c.created_at).getTime() : Date.now(),
          updatedAt: c.updated_at ? new Date(c.updated_at).getTime() : Date.now(),
          // 子任务会话元数据：任务列表据此把自动创建的子任务折叠进父任务行
          taskType: c.task_type || "user",
          parentConversationId: c.parent_conversation_id ?? null,
        }),
      );

      // Merge: keep local tasks that aren't from backend, add backend tasks.
      // Deduplicate backendTasks by id (backend may return dupes) and deduplicate
      // the final array to prevent React duplicate-key warnings.
      set((s) => {
        const seen = new Set<string>();
        const dedupedBackend: Task[] = [];
        for (const t of backendTasks) {
          if (!seen.has(t.id)) {
            seen.add(t.id);
            dedupedBackend.push(t);
          }
        }
        const backendIds = new Set(dedupedBackend.map((t) => t.id));
        const localOnly = s.tasks.filter(
          (t) => t.workspaceId !== workspaceId || !backendIds.has(t.id),
        );
        // Final dedup: guard against race conditions from concurrent calls
        const merged = [...dedupedBackend, ...localOnly];
        const allSeen = new Set<string>();
        const deduped: Task[] = [];
        for (const t of merged) {
          if (!allSeen.has(t.id)) {
            allSeen.add(t.id);
            deduped.push(t);
          }
        }
        return { tasks: deduped };
      });
    } catch (e) {
      // If workspace no longer exists on backend (404) or is inaccessible to
      // the current account (403 — e.g. a foreign-owned workspace resurrected
      // into local cache by create-by-path), purge it from local store so the
      // sidebar/home never renders dead entries.
      if (e instanceof ApiError && (e.status === 404 || e.status === 403)) {
        console.warn(
          `[Store] Workspace ${workspaceId} not accessible (${e.status}), purging from local cache`,
        );
        set((s) => ({
          workspaces: s.workspaces.filter((w) => w.id !== workspaceId),
          tasks: s.tasks.filter((t) => t.workspaceId !== workspaceId),
        }));
        return;
      }
      console.error("[Store] fetchTasksForWorkspace failed:", e);
      toastError("加载对话列表失败", e);
    } finally {
      workspaceTaskFetching.delete(workspaceId);
    }
  },

  fetchInitialData: async () => {
    set({ loading: true, error: null });
    try {
      await Promise.all([get().fetchWorkspaces(), get().fetchCollections(), get().fetchModels()]);
      // After loading workspaces, fetch conversations for each
      const workspaces = get().workspaces;
      await Promise.all(workspaces.map((ws) => get().fetchTasksForWorkspace(ws.id)));
    } catch (e) {
      set({ error: String(e) });
    } finally {
      set({ loading: false });
    }
  },

  createWorkspace: async ({
    path,
    name,
    displayName,
    description,
    teamId,
    teamMeta,
    skillIds,
    agentIds,
    mcpIds,
    knowledgeIds,
  }) => {
    const data = await workspaceApi.createFull({
      path,
      name,
      display_name: displayName || undefined,
      description: description || undefined,
      team_id: teamId || undefined,
      team_meta: teamMeta || undefined,
      skill_ids: skillIds?.length ? skillIds : undefined,
      agent_ids: agentIds?.length ? agentIds : undefined,
      mcp_ids: mcpIds?.length ? mcpIds : undefined,
      knowledge_ids: knowledgeIds?.length ? knowledgeIds : undefined,
    });
    const wsData = data.workspace || data;
    const ws: Workspace = {
      id: wsData.id,
      name: wsData.display_name || wsData.name || name || path?.split("/").pop() || "工作区",
      files: [],
      createdAt: wsData.created_at ? new Date(wsData.created_at).getTime() : Date.now(),
    };
    set((s) => ({ workspaces: [...s.workspaces, ws] }));
    return ws;
  },
  renameWorkspace: (id, name) => {
    // Update local state immediately (optimistic)
    set((s) => ({ workspaces: s.workspaces.map((w) => (w.id === id ? { ...w, name } : w)) }));
    // Persist to backend (debounced) — mirrors renameTask
    const prev = wsRenameTimers.get(id);
    if (prev) clearTimeout(prev);
    const trimmed = name.trim();
    if (!trimmed) return; // backend requires display_name min_length=1
    wsRenameTimers.set(
      id,
      setTimeout(() => {
        wsRenameTimers.delete(id);
        workspaceApi.update(id, { display_name: trimmed }).catch((e) => {
          console.error("[Store] renameWorkspace backend failed:", e);
          toastError("工作区重命名同步失败，刷新后可能恢复", e);
        });
      }, WS_RENAME_DEBOUNCE_MS),
    );
  },
  deleteWorkspace: async (id) => {
    try {
      await workspaceApi.delete(id);
    } catch (err: unknown) {
      toastError("删除工作区失败", err);
      return; // keep local state on API failure
    }
    set((s) => ({
      workspaces: s.workspaces.filter((w) => w.id !== id),
      tasks: s.tasks.filter((t) => t.workspaceId !== id),
    }));
  },
  clearWorkspace: async (workspaceId) => {
    // 后端执行清空（任务/日志/文件）；失败则保持本地状态不变
    await workspaceApi.reset(workspaceId);

    // 清除该工作区的本地任务与消息缓存（fetchTasksForWorkspace 对空列表
    // 不做清除，所以这里必须显式移除）
    const stale = get().tasks.filter((t) => t.workspaceId === workspaceId);
    const chatStore = useChatStore.getState();
    stale.forEach((t) => chatStore.clearMessages(t.id));
    set((s) => ({
      tasks: s.tasks.filter((t) => t.workspaceId !== workspaceId),
      workspaces: s.workspaces.map((w) => (w.id === workspaceId ? { ...w, files: [] } : w)),
    }));

    // 与「新建工作区」一致：创建一个空任务供调用方导航
    return get().createTask({ workspaceId, title: "新任务" });
  },
  addFile: (workspaceId, name, kind = "upload") =>
    set((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.id === workspaceId ? { ...w, files: [...w.files, { id: nanoid(6), name, kind }] } : w,
      ),
    })),

  /**
   * Create a task (= conversation) — locally and optionally on backend.
   * If workspaceId is set, creates a real conversation via API.
   * Returns the Task with the real backend ID.
   */
  createTask: async ({ workspaceId, title, expertId }) => {
    const saved = getSavedPrefs();
    const taskTitle = title || (workspaceId ? "新任务" : "新临时任务");
    let taskId = nanoid(10);

    // If connected to a workspace, create a real conversation on the backend
    if (workspaceId) {
      try {
        const data = await conversationApi.create(workspaceId, taskTitle);
        // Backend may return the created conversation
        if (data.conversation_id || data.id) {
          taskId =
            (data as { conversation_id?: string; id?: string }).conversation_id ||
            (data as { id?: string }).id ||
            taskId;
        }
      } catch (e) {
        console.error("[Store] createTask backend failed:", e);
        toastError("创建对话失败，使用本地临时 ID", e);
      }
    }

    const task: Task = {
      id: taskId,
      title: taskTitle,
      workspaceId,
      messages: [],
      mode: saved.mode,
      expertId, // 不从偏好继承：新任务默认无 expert，走 Orchestrator 路由
      model: saved.model,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    set((s) => {
      // Deduplicate: replace existing task with same id, or prepend
      const filtered = s.tasks.filter((t) => t.id !== task.id);
      return { tasks: [task, ...filtered] };
    });
    return task;
  },
  getOrCreateEmptyTask: async ({ workspaceId, expertId }) => {
    const saved = getSavedPrefs();
    const defaultTitle = workspaceId ? "新任务" : "新临时任务";
    // Check both local task messages AND chatStore messages (authoritative source)
    const chatStore = useChatStore.getState();
    const existing = get().tasks.find(
      (t) =>
        t.workspaceId === workspaceId &&
        t.messages.length === 0 &&
        t.title === defaultTitle &&
        // Verify chatStore also has no messages — avoids stale "empty" task after refresh
        chatStore.getMessages(t.id).length === 0,
    );
    if (existing) {
      // Sync model/mode to latest user preference — avoids showing a stale model
      // (e.g. user switched default model in another task, then "立即开始" reuses
      // this empty task which still holds the old model from when it was created).
      const latestModel = saved.model;
      const latestMode = saved.mode;
      if (
        existing.model !== latestModel ||
        existing.mode !== latestMode ||
        (expertId && existing.expertId !== expertId)
      ) {
        const updated = {
          ...existing,
          model: latestModel,
          mode: latestMode,
          expertId: expertId || existing.expertId,
        };
        set((s) => ({
          tasks: s.tasks.map((t) => (t.id === existing.id ? updated : t)),
        }));
        return updated;
      }
      return existing;
    }

    // Try to create conversation in backend to get a real ID
    let taskId = nanoid(10);
    if (workspaceId) {
      try {
        const data = await conversationApi.create(workspaceId, defaultTitle);
        if (data?.id) {
          taskId = data.id;
        }
      } catch {
        // Fallback to nanoid if backend unreachable
        toast.error("创建对话失败，使用本地临时 ID");
      }
    }

    const task: Task = {
      id: taskId,
      title: defaultTitle,
      workspaceId,
      messages: [],
      mode: saved.mode,
      expertId, // 不从偏好继承：新任务默认无 expert，走 Orchestrator 路由
      model: saved.model,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    set((s) => {
      // Deduplicate: replace existing task with same id, or prepend
      const filtered = s.tasks.filter((t) => t.id !== task.id);
      return { tasks: [task, ...filtered] };
    });
    return task;
  },
  renameTask: (id, title) => {
    // Update local state immediately
    set((s) => ({
      tasks: s.tasks.map((t) => (t.id === id ? { ...t, title, updatedAt: Date.now() } : t)),
    }));
    // Persist to backend asynchronously
    const task = get().tasks.find((t) => t.id === id);
    if (task?.workspaceId) {
      conversationApi.rename(task.workspaceId, id, title).catch((e) => {
        console.error("[Store] renameTask backend failed:", e);
        toastError("重命名同步失败，刷新后可能恢复", e);
      });
    }
  },
  deleteTask: (id) => {
    const task = get().tasks.find((t) => t.id === id);
    // Delete from backend（级联：后端一并删除折叠其下的子任务会话）
    if (task?.workspaceId) {
      conversationApi
        .deleteScoped(task.workspaceId, id)
        .then((res) => {
          // 后端实际级联清单兜底移除（防本地 parentConversationId 缺失的旧缓存）
          const cascaded = res.cascaded_conversation_ids ?? [];
          if (cascaded.length > 0) {
            set((s) => ({ tasks: s.tasks.filter((t) => !cascaded.includes(t.id)) }));
          }
        })
        .catch((e) => {
          console.error("[Store] deleteTask backend failed:", e);
          toastError("删除同步失败，刷新后可能恢复", e);
        });
    }
    // 本地立即移除：父任务 + 折叠其下的子任务会话
    set((s) => ({
      tasks: s.tasks.filter(
        (t) => t.id !== id && !(t.taskType === "subtask" && t.parentConversationId === id),
      ),
    }));
  },
  moveTask: (id, workspaceId) =>
    set((s) => ({
      tasks: s.tasks.map((t) => (t.id === id ? { ...t, workspaceId, updatedAt: Date.now() } : t)),
    })),
  addMessage: (taskId, msg) =>
    set((s) => ({
      tasks: s.tasks.map((t) =>
        t.id === taskId
          ? {
              ...t,
              messages: [...t.messages, { ...msg, id: nanoid(8), ts: Date.now() }],
              updatedAt: Date.now(),
              title:
                t.messages.length === 0 && msg.role === "user"
                  ? msg.content.slice(0, 24) || t.title
                  : t.title,
            }
          : t,
      ),
    })),
  setTaskMode: (id, mode) => {
    savePref(LS_KEYS.lastMode, mode);
    set((s) => ({ tasks: s.tasks.map((t) => (t.id === id ? { ...t, mode } : t)) }));
  },
  setTaskModel: (id, model) => {
    if (model) savePref(LS_KEYS.lastModel, model);
    else {
      try {
        localStorage.removeItem(LS_KEYS.lastModel);
      } catch {
        /* no-op */
      }
    }
    set((s) => ({ tasks: s.tasks.map((t) => (t.id === id ? { ...t, model } : t)) }));
  },
  setTaskExpert: (id, expertId) => {
    // 🔧 expert 不做任何 localStorage 缓存：expert 是领域身份而非通用偏好，
    // 预盖章会绕过 Orchestrator 路由且曾跨工作区泄漏（SocialAgent 污染综述工作区）。
    // 新任务一律不带 expert，由 Orchestrator 按 DOMAIN EXPERTS 路由决定。
    set((s) => ({ tasks: s.tasks.map((t) => (t.id === id ? { ...t, expertId } : t)) }));
  },
  upsertWorkspace: (ws) =>
    set((s) => {
      const idx = s.workspaces.findIndex((w) => w.id === ws.id);
      if (idx >= 0) {
        const copy = [...s.workspaces];
        copy[idx] = ws;
        return { workspaces: copy };
      }
      return { workspaces: [...s.workspaces, ws] };
    }),
  upsertTask: (task) =>
    set((s) => {
      const idx = s.tasks.findIndex((t) => t.id === task.id);
      if (idx >= 0) {
        const copy = [...s.tasks];
        copy[idx] = task;
        return { tasks: copy };
      }
      return { tasks: [task, ...s.tasks] };
    }),

  fetchWorkspaceResources: async (workspaceId: string) => {
    const ws = get().workspaces.find((w) => w.id === workspaceId);
    if (!ws || ws.modesLoaded || ws.modesLoading) return;
    set((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.id === workspaceId ? { ...w, modesLoading: true } : w,
      ),
    }));
    try {
      const data = await workspaceResourceApi.get(workspaceId);
      set((s) => ({
        workspaces: s.workspaces.map((w) =>
          w.id === workspaceId
            ? {
                ...w,
                modes: data.modes ?? [],
                agentModes: data.agent_modes ?? undefined,
                modesLoading: false,
                modesLoaded: true,
              }
            : w,
        ),
      }));
    } catch {
      set((s) => ({
        workspaces: s.workspaces.map((w) =>
          w.id === workspaceId ? { ...w, modesLoading: false } : w,
        ),
      }));
    }
  },
}));

// Models loaded from backend; this is a fallback for offline
export const MODELS: LLMModel[] = [];
