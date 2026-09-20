/**
 * Identity switch — reset all stores.
 *
 * Called when the user switches identity (personal ↔ tenant, or tenant A ↔
 * tenant B).  Every store that holds workspace / tenant scoped data must be
 * reset here so stale data from the previous identity never leaks.
 */
import { useStore } from "./store";
import { useChatStore } from "./chat-store";
import { useKnowledgeStore } from "./knowledge-store";
import { useTaskStore } from "./task-store";
import { useAgentStore } from "./agent-store";
import { useConnectionStore } from "./connection-store";
import { useTabsStore } from "./tabs-store";
import { useWorkspaceFilesStore } from "./workspace-files-store";
import { usePinnedStore } from "./pinned-store";
import { BIZ_IDENTITY_RESET_HOOKS } from "./biz-registry";
import { wsClient } from "./ws-client";

/** Identity-scoped localStorage keys to remove on switch. */
const SCOPED_LS_KEYS = [
  "normnomos-workspace-id",
  "normnomos-last-model",
  "normnomos-last-mode",
  "normnomos-last-expert",
];

/**
 * Reset every store that holds identity-scoped data.
 *
 * UI-only preferences (theme, language, font size, display mode, compact
 * mode) are intentionally preserved — they are user-level, not tenant-level.
 */
export function resetAllStores(): void {
  // 1. Interrupt any in-flight SSE / streaming before clearing state
  try {
    useChatStore.getState().interruptAllStreams();
  } catch {
    /* noop */
  }

  // 2. Disconnect WebSocket (will auto-reconnect with new token on next page load)
  try {
    wsClient.disconnect();
  } catch {
    /* noop */
  }

  // 3. Reset main app store (workspaces, tasks, collections)
  useStore.setState({
    workspaces: [],
    workspacesLoaded: false,
    collections: [],
    tasks: [],
    loading: false,
    error: null,
    filesDrawerFor: null,
    pendingInsert: null,
  });

  // 4. Reset chat store (all conversations)
  useChatStore.setState({
    conversations: new Map(),
    historyLoadErrors: {},
  });

  // 5. Reset knowledge store
  useKnowledgeStore.setState({
    bases: [],
    basesLoading: false,
    error: null,
    selectedBaseId: null,
    selectedBase: null,
    documents: [],
    documentsTotal: 0,
    documentsLoading: false,
    documentsPage: 1,
    stats: null,
    statsLoading: false,
    searchResults: [],
    searchLoading: false,
    searchStats: null,
    entities: [],
    relations: [],
    graphLoading: false,
    entitySources: null,
    entitySourcesLoading: false,
    syncTask: null,
    selectedWorkspaceId: null,
  });

  // 6. Reset task store (task graphs per workspace)
  useTaskStore.setState({
    workspaceCurrentTaskId: {},
    workspaceTaskGraphData: {},
    workspaceTaskGraphStats: {},
    workspaceActiveNodes: {},
    workspaceCompletedNodes: {},
  });

  // 7. Reset agent store (agent state per workspace)
  useAgentStore.setState({
    workspaceIsThinking: {},
    workspaceCurrentTaskId: {},
    workspaceAgentStatus: {},
    workspaceDegradedFeatures: {},
    workspaceTraceSpans: {},
    _taskToWorkspace: {},
  });

  // 8. Reset connection store
  useConnectionStore.setState({
    state: "disconnected",
    sessionId: null,
    connectedAt: null,
  });

  // 9. Reset tabs store (close all tabs — they reference old workspace/task IDs)
  useTabsStore.setState({
    tabs: [],
    activeTabKey: null,
  });

  // 10. Reset workspace files store
  useWorkspaceFilesStore.setState({
    fileTree: [],
    fileTreeLoading: false,
    fileTreeError: null,
    currentWorkspaceId: null,
    openFiles: [],
    activeFileId: null,
    fileContentLoading: false,
    knowledgeBases: [],
    knowledgeDomains: [],
    kbLoading: false,
    searchResults: [],
    searchLoading: false,
    selectedFileInfo: null,
    fileInfoLoading: false,
    uploading: false,
    uploadProgress: 0,
  });

  // 11. Clear identity-scoped localStorage keys
  if (typeof window !== "undefined") {
    for (const key of SCOPED_LS_KEYS) {
      localStorage.removeItem(key);
    }
  }

  // 12. Reset biz domain stores (registry 注入;如 social 品牌上下文 —— 持久化
  //     选择是 tenant-scoped,换身份后旧 brand id 会让品牌筛选列表 404)
  for (const entry of BIZ_IDENTITY_RESET_HOOKS) {
    try {
      entry.reset();
    } catch {
      /* noop */
    }
  }

  // 13. Reset pinned shortcuts — pins are identity-scoped: a FirmAgent pin
  //     created under account A is a 403 dead link for account B
  //     (persist key "normnomos-pinned-v1" otherwise survives logout/login).
  usePinnedStore.setState({ pinned: [] });
}
