/**
 * WorkspacePanel — Right-side collapsible panel with 3 tabs:
 * 1. 概览 (Overview — workspace tasks, quick actions, trace)
 * 2. 文件浏览器 (File Tree)
 * 3. 工作区能力 (Workspace Capabilities — LLMs, knowledge, installed resources)
 */
import { dateLocale } from "@/lib/date-locale";
import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import type { Task, Workspace } from "@/lib/store";
import { useStore } from "@/lib/store";
import { useAgentStore } from "@/lib/agent-store";
import { useShallow } from "zustand/react/shallow";
import { useWorkspaceFilesStore } from "@/lib/workspace-files-store";
import { selectFiles } from "@/lib/platform/files";
import { FileTreeNode, type FileTreeItem } from "@/components/files/file-tree-node";
import { SubtaskTree } from "@/components/monitoring";
import { type WorkspaceResources, workspaceResourceApi } from "@/lib/api-client";
import { marketApi, botApi, type MarketResource } from "@/lib/market-api";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  FolderTree,
  Loader2,
  Plus,
  Trash2,
  Pencil,
  Database,
  Cpu,
  RefreshCw,
  Wrench,
  Sparkles,
  Bot,
  UserCircle,
  FileText,
  Clock,
  Search,
  Download,
  Upload,
  Info,
  X,
  LayoutDashboard,
  MessageSquare,
  Activity,
  FolderOpen,
  PackagePlus,
  Check,
  Shield,
  Eraser,
  Network,
  Eye,
  ChevronDown,
  ChevronRight,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { groupTasksByParent } from "@/lib/task-grouping";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { PromptDialog } from "@/components/confirm-dialog";

// ── Types ──────────────────────────────────────────────────────────

type TabId = string;

interface ExtraTab {
  id: string;
  label: string;
  icon: React.ReactNode;
  content: React.ReactNode;
}

interface Props {
  task: Task;
  workspace: Workspace;
  /** E5: Extra tabs injected after the built-in tabs */
  extraTabs?: ExtraTab[];
  /** E6: Slot rendered at the top of the Overview tab */
  overviewHeaderSlot?: React.ReactNode;
}

// ── Drag & Drop helpers ────────────────────────────────────────────

type DroppedFile = { name: string; size: number; file: File; relativePath?: string };

/** 从 drop 事件提取文件；支持拖入文件夹（递归展开，保留相对路径）。
 *  Chrome 拖入文件夹时 dataTransfer.files 为空，必须走 items/webkitGetAsEntry。
 *  注意 entries 必须同步收集（事件返回后 DataTransferItemList 即失效）。 */
async function extractDroppedFiles(e: React.DragEvent): Promise<DroppedFile[]> {
  const dt = e.dataTransfer;
  const out: DroppedFile[] = [];

  const entries = Array.from(dt.items ?? [])
    .map((it) => (typeof it.webkitGetAsEntry === "function" ? it.webkitGetAsEntry() : null))
    .filter((en): en is FileSystemEntry => en !== null);

  const readEntry = (entry: FileSystemEntry, prefix: string): Promise<void> =>
    new Promise((resolve) => {
      if (entry.isFile) {
        (entry as FileSystemFileEntry).file(
          (f) => {
            out.push({
              name: f.name,
              size: f.size,
              file: f,
              relativePath: prefix ? `${prefix}/${f.name}` : undefined,
            });
            resolve();
          },
          () => resolve(), // 单文件读取失败：跳过，不中断整批
        );
      } else if (entry.isDirectory) {
        const reader = (entry as FileSystemDirectoryEntry).createReader();
        // readEntries 每次最多返回 100 条，需循环读到空为止
        const readBatch = () =>
          reader.readEntries(
            async (batch) => {
              if (batch.length === 0) {
                resolve();
                return;
              }
              for (const en of batch) {
                await readEntry(en, prefix ? `${prefix}/${en.name}` : en.name);
              }
              readBatch();
            },
            () => resolve(),
          );
        readBatch();
      } else {
        resolve();
      }
    });

  if (entries.length > 0) {
    for (const en of entries) await readEntry(en, "");
    if (out.length > 0) return out;
  }

  // 回退：普通文件拖入（或浏览器不支持 entry API）
  return Array.from(dt.files).map((f) => ({
    name: f.name,
    size: f.size,
    file: f,
    relativePath: (f as File & { webkitRelativePath?: string }).webkitRelativePath || undefined,
  }));
}

// ── Main Component ─────────────────────────────────────────────────

export function WorkspacePanel({ task, workspace, extraTabs, overviewHeaderSlot }: Props) {
  const { t: uiT } = useTranslation("commonUi");
  const wsStore = useWorkspaceFilesStore();
  const {
    fileTree,
    fileTreeLoading,
    fileContentLoading,
    knowledgeBases,
    knowledgeDomains,
    kbLoading,
  } = wsStore;

  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [showTrace, setShowTrace] = useState(false);
  const [showMonitor, setShowMonitor] = useState(false);

  // File search & info state
  const [searchQuery, setSearchQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [showFileInfo, setShowFileInfo] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  // Name-input dialog for new file / new folder / rename (replaces window.prompt)
  const [nameDialog, setNameDialog] = useState<{
    kind: "newFile" | "newFolder" | "rename";
    path?: string;
  } | null>(null);

  // Workspace resources state
  const [resources, setResources] = useState<WorkspaceResources | null>(null);
  const [resourcesLoading, setResourcesLoading] = useState(false);

  // Market browser state
  const [showMarket, setShowMarket] = useState(false);
  const [marketItems, setMarketItems] = useState<MarketResource[]>([]);
  const [marketLoading, setMarketLoading] = useState(false);
  const [marketType, setMarketType] = useState<"agent" | "skill">("agent");
  const [marketSearch, setMarketSearch] = useState("");
  const [installingIds, setInstallingIds] = useState<Set<string>>(new Set());
  const [uninstallingIds, setUninstallingIds] = useState<Set<string>>(new Set());

  const refreshResources = useCallback(() => {
    setResourcesLoading(true);
    return workspaceResourceApi
      .get(workspace.id)
      .then((r) =>
        setResources({
          skills: r.skills ?? [],
          modes: r.modes ?? [],
          mcp_servers: r.mcp_servers ?? [],
          team: r.team ?? null,
        }),
      )
      .catch(() => setResources(null))
      .finally(() => setResourcesLoading(false));
  }, [workspace.id]);

  // Fetch data when workspace/task changes
  useEffect(() => {
    wsStore.fetchFileTree(workspace.id);
    wsStore.fetchKnowledgeBases();

    // Fetch workspace resources
    setResourcesLoading(true);
    workspaceResourceApi
      .get(workspace.id)
      .then((r) =>
        setResources({
          skills: r.skills ?? [],
          modes: r.modes ?? [],
          mcp_servers: r.mcp_servers ?? [],
          team: r.team ?? null,
        }),
      )
      .catch((e) => {
        toast.error(uiT("wsPanel.loadResourcesFailed"), { description: String(e) });
        setResources(null);
      })
      .finally(() => setResourcesLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- wsStore is a Zustand store subscription; adding it causes infinite re-renders
  }, [workspace.id, task.id]);

  const handleUploadClick = useCallback(async () => {
    const selected = await selectFiles({ multiple: true });
    if (selected.length > 0) {
      wsStore.uploadFiles(workspace.id, selected);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- wsStore is a Zustand store subscription; adding it causes infinite re-renders
  }, [workspace.id]);

  // selectFiles({directory}) handles the platform split: web/desktop use
  // <input webkitdirectory>; the light shell (WebKitGTK) uses the native
  // pick_folder_files command — the hidden webkitdirectory input can't work
  // there, so the button must NOT go through an <input> directly.
  const handleUploadFolderClick = useCallback(async () => {
    const selected = await selectFiles({ directory: true, multiple: true });
    if (selected.length > 0) {
      wsStore.uploadFiles(workspace.id, selected);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- wsStore is a Zustand store subscription; adding it causes infinite re-renders
  }, [workspace.id]);

  const handleFileClick = useCallback(
    (item: FileTreeItem) => {
      if (item.type === "file") {
        setSelectedPath(item.path);
        wsStore.openFile(workspace.id, item.path);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- wsStore is a Zustand store subscription; adding it causes infinite re-renders
    [workspace.id],
  );

  const handleNewFile = () => setNameDialog({ kind: "newFile" });

  const handleNewFolder = () => setNameDialog({ kind: "newFolder" });

  // PromptDialog confirm: create file/folder or rename, based on dialog kind
  const handleNameDialogConfirm = (value: string) => {
    const name = value.trim();
    if (!name || !nameDialog) return;
    if (nameDialog.kind === "newFile") {
      wsStore.createFile(workspace.id, name, "file");
    } else if (nameDialog.kind === "newFolder") {
      wsStore.createFile(workspace.id, name, "directory");
    } else if (nameDialog.path) {
      const dir = nameDialog.path.includes("/")
        ? nameDialog.path.substring(0, nameDialog.path.lastIndexOf("/") + 1)
        : "";
      wsStore.renameFile(workspace.id, nameDialog.path, dir + name);
    }
    setNameDialog(null);
  };

  const handleDelete = (path: string) => {
    setConfirmDeleteFile(path);
  };

  const doDeleteFile = () => {
    if (!confirmDeleteFile) return;
    wsStore.deleteFile(workspace.id, confirmDeleteFile);
    setSelectedPath(null);
    setConfirmDeleteFile(null);
  };

  const doDeleteTask = () => {
    if (!confirmDeleteTask) return;
    const targetId = confirmDeleteTask.id;
    // If we're deleting the currently-viewed task, find the next sibling
    // （候选排除被级联删除的子任务会话 — 不能导航进即将消失的会话）
    const isCurrentTask = targetId === task.id;
    deleteTask(targetId);
    if (isCurrentTask) {
      const remaining = allTasks.filter(
        (ot) =>
          ot.id !== targetId &&
          !(ot.taskType === "subtask" && ot.parentConversationId === targetId),
      );
      const next = remaining.length > 0 ? remaining[0] : null;
      if (next) {
        navigatePanel({
          to: "/workspace/$workspaceId/task/$taskId",
          params: { workspaceId: workspace.id, taskId: next.id },
        });
      }
    }
    setConfirmDeleteTask(null);
  };

  // 清空工作区（危险操作）：后端清除任务/日志/文件 → 刷新文件树与轨迹 → 导航到新空任务
  const doClearWorkspace = async () => {
    if (clearingWs) return;
    setClearingWs(true);
    try {
      const freshTask = await clearWorkspace(workspace.id);
      wsStore.fetchFileTree(workspace.id);
      if (showTrace) fetchTraceSpans(workspace.id);
      toast.success(uiT("wsPanel.clearWorkspace.success"));
      if (freshTask) {
        navigatePanel({
          to: "/workspace/$workspaceId/task/$taskId",
          params: { workspaceId: workspace.id, taskId: freshTask.id },
        });
      }
    } catch (e) {
      toast.error(uiT("wsPanel.clearWorkspace.failed"), { description: String(e) });
    } finally {
      setClearingWs(false);
      setConfirmClearWs(false);
    }
  };

  const handleRename = (path: string) => {
    setNameDialog({ kind: "rename", path });
  };

  // Categorize modes: system (orchestrator/pdca) vs workspace (installed agents)
  const systemModes = useMemo(
    () => resources?.modes?.filter((m) => m.source === "system") ?? [],
    [resources?.modes],
  );
  const workspaceModes = useMemo(
    () => resources?.modes?.filter((m) => m.source === "workspace") ?? [],
    [resources?.modes],
  );

  // Set of installed resource slugs (for market browser "installed" badge)
  const installedSlugs = useMemo(() => {
    const s = new Set<string>();
    workspaceModes.forEach((m) => s.add(m.slug));
    resources?.skills?.forEach((sk) => s.add(sk.slug));
    return s;
  }, [workspaceModes, resources?.skills]);

  const models = useStore((s) => s.models);
  const totalFiles = fileTree.reduce(countFiles, 0);

  // Market browser handlers
  const fetchMarket = useCallback(async (type: "agent" | "skill") => {
    setMarketLoading(true);
    setMarketType(type);
    try {
      const res = await marketApi.listResources({ type, page_size: 100 });
      setMarketItems(res.items ?? []);
    } catch (e) {
      toast.error(uiT("wsPanel.loadMarketFailed"), { description: String(e) });
      setMarketItems([]);
    } finally {
      setMarketLoading(false);
    }
  }, []);

  const handleInstallFromMarket = useCallback(
    async (resourceType: string, resourceSlug: string) => {
      // Backend expects resource_id in "type/slug" format (e.g. "skill/docx", "agent/firm-team")
      const resourceId = `${resourceType}/${resourceSlug}`;
      setInstallingIds((prev) => new Set(prev).add(resourceId));
      try {
        await botApi.installResources({
          workspace: workspace.id,
          resource_ids: [resourceId],
        });
        toast.success(uiT("wsPanel.installSuccess"), { description: resourceSlug });
        await refreshResources();
      } catch (e) {
        toast.error(uiT("wsPanel.installFailed"), { description: String(e) });
      } finally {
        setInstallingIds((prev) => {
          const s = new Set(prev);
          s.delete(resourceId);
          return s;
        });
      }
    },
    [workspace.id, refreshResources],
  );

  const handleUninstallSkill = useCallback(
    async (skillSlug: string) => {
      setUninstallingIds((prev) => new Set(prev).add(`skill/${skillSlug}`));
      try {
        await workspaceResourceApi.deleteSkill(workspace.id, skillSlug);
        toast.success(uiT("wsPanel.uninstalled"), { description: skillSlug });
        await refreshResources();
      } catch (e) {
        toast.error(uiT("wsPanel.uninstallFailed"), { description: String(e) });
      } finally {
        setUninstallingIds((prev) => {
          const s = new Set(prev);
          s.delete(`skill/${skillSlug}`);
          return s;
        });
      }
    },
    [workspace.id, refreshResources],
  );

  const handleUninstallMode = useCallback(
    async (modeSlug: string) => {
      setUninstallingIds((prev) => new Set(prev).add(`mode/${modeSlug}`));
      try {
        await workspaceResourceApi.deleteMode(workspace.id, modeSlug);
        toast.success(uiT("wsPanel.deletedToast"), { description: modeSlug });
        await refreshResources();
      } catch (e) {
        toast.error(uiT("wsPanel.deleteFailed"), { description: String(e) });
      } finally {
        setUninstallingIds((prev) => {
          const s = new Set(prev);
          s.delete(`mode/${modeSlug}`);
          return s;
        });
      }
    },
    [workspace.id, refreshResources],
  );

  const allTasks = useStore(
    useShallow((s) => s.tasks.filter((t) => t.workspaceId === workspace.id)),
  );
  // 任务列表嵌套：子任务会话（taskType=subtask）折叠进父任务行，不再平铺
  const { groups: taskGroups, orphans: orphanSubtasks } = groupTasksByParent(allTasks);
  const userTaskCount = taskGroups.length;
  const firstUserTask = taskGroups[0]?.parent;
  const [expandedTaskParents, setExpandedTaskParents] = useState<Set<string>>(new Set());
  // 当前会话为子任务时自动展开其父行（保证活动会话可见、上下文可定位）
  const activeParentId = task.parentConversationId ?? null;
  const effectiveExpandedTaskParents =
    activeParentId && allTasks.some((t) => t.id === activeParentId)
      ? new Set([...expandedTaskParents, activeParentId])
      : expandedTaskParents;
  const createTask = useStore((s) => s.createTask);
  const getOrCreateEmptyTask = useStore((s) => s.getOrCreateEmptyTask);
  const deleteTask = useStore((s) => s.deleteTask);
  const clearWorkspace = useStore((s) => s.clearWorkspace);
  const renameTask = useStore((s) => s.renameTask);
  const renameWorkspace = useStore((s) => s.renameWorkspace);
  const [renameTarget, setRenameTarget] = useState<{ id: string; title: string } | null>(null);
  const [confirmDeleteFile, setConfirmDeleteFile] = useState<string | null>(null);
  const [confirmDeleteTask, setConfirmDeleteTask] = useState<{
    id: string;
    title: string;
    subCount?: number;
  } | null>(null);
  const [confirmClearWs, setConfirmClearWs] = useState(false);
  const [clearingWs, setClearingWs] = useState(false);
  const [editingWsName, setEditingWsName] = useState(false);
  const [wsNameValue, setWsNameValue] = useState("");
  const fetchTasksForWorkspaceRef = useRef(useStore.getState().fetchTasksForWorkspace);
  fetchTasksForWorkspaceRef.current = useStore.getState().fetchTasksForWorkspace;
  const navigatePanel = useNavigate();
  const fetchTraceSpans = useAgentStore((s) => s.fetchTraceSpans);
  // Select the whole map to keep references stable; derive locally to avoid `?? []` creating
  // a new array identity on every render, which would cause an infinite update loop.
  const workspaceTraceSpans = useAgentStore((s) => s.workspaceTraceSpans);
  const traceSpans = workspaceTraceSpans[workspace.id];

  // Fetch tasks for the overview tab on mount
  useEffect(() => {
    fetchTasksForWorkspaceRef.current(workspace.id);
  }, [workspace.id]);

  // Fetch trace spans when inline trace is toggled on
  useEffect(() => {
    if (showTrace) {
      fetchTraceSpans(workspace.id);
    }
  }, [showTrace, workspace.id, fetchTraceSpans]);

  const tabs: Array<{ id: string; label: string; icon: React.ReactNode }> = [
    {
      id: "overview",
      label: uiT("wsPanel.tab.overview"),
      icon: <LayoutDashboard className="w-3.5 h-3.5" />,
    },
    { id: "files", label: uiT("wsPanel.tab.files"), icon: <FolderTree className="w-3.5 h-3.5" /> },
    {
      id: "capabilities",
      label: uiT("wsPanel.tab.capabilities"),
      icon: <Cpu className="w-3.5 h-3.5" />,
    },
    ...(extraTabs ?? []),
  ];

  return (
    <div className="flex flex-col h-full border-l border-border bg-background/80">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border flex items-center gap-2 shrink-0">
        <FolderTree className="w-3.5 h-3.5 text-brand" />
        <span className="text-xs font-medium truncate">{workspace.name}</span>
        <span className="text-[10px] text-muted-foreground">
          {uiT("wsPanel.filesShort", { count: totalFiles })}
        </span>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-border shrink-0">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-[11px] font-medium transition-colors",
              activeTab === tab.id
                ? "text-brand border-b-2 border-brand bg-brand/5"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/30",
            )}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {/* ── Overview Tab ── */}
        {activeTab === "overview" && (
          <div className="p-3 space-y-3">
            {/* E6: Overview header slot (e.g. IP module badge + quick actions) */}
            {overviewHeaderSlot}
            {/* Workspace info */}
            <div className="bg-muted/30 rounded-lg p-2.5">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-6 h-6 rounded-md bg-brand/10 border border-brand/30 flex items-center justify-center shrink-0">
                  <FolderOpen className="w-3 h-3 text-brand" />
                </div>
                {editingWsName ? (
                  <input
                    autoFocus
                    value={wsNameValue}
                    onChange={(e) => setWsNameValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && wsNameValue.trim()) {
                        renameWorkspace(workspace.id, wsNameValue.trim());
                        setEditingWsName(false);
                      } else if (e.key === "Escape") {
                        setEditingWsName(false);
                      }
                    }}
                    onBlur={() => {
                      if (wsNameValue.trim() && wsNameValue.trim() !== workspace.name) {
                        renameWorkspace(workspace.id, wsNameValue.trim());
                      }
                      setEditingWsName(false);
                    }}
                    className="bg-transparent border-b border-brand/50 outline-none flex-1 min-w-0 text-xs font-semibold text-foreground px-0"
                  />
                ) : (
                  <button
                    onClick={() => {
                      setWsNameValue(workspace.name);
                      setEditingWsName(true);
                    }}
                    className="hover:text-brand transition group inline-flex items-center gap-1 min-w-0"
                    title={uiT("wsPanel.clickRename")}
                  >
                    <span className="text-xs font-semibold truncate">{workspace.name}</span>
                    <Pencil className="w-3 h-3 opacity-0 group-hover:opacity-50 transition shrink-0" />
                  </button>
                )}
              </div>
              <div className="flex items-center gap-3 mt-1.5 text-[10px] text-muted-foreground">
                <span>{uiT("wsPanel.tasksCount", { count: userTaskCount })}</span>
                <span>{uiT("wsPanel.filesFull", { count: workspace.files.length })}</span>
                <span>
                  {uiT("wsPanel.createdAt", {
                    date: new Date(workspace.createdAt).toLocaleDateString(dateLocale()),
                  })}
                </span>
              </div>
            </div>

            {/* Observation group */}
            <div>
              <div className="text-[10px] font-medium text-muted-foreground mb-1.5 flex items-center gap-1">
                <Eye className="w-3 h-3" />
                {uiT("wsPanel.observation")}
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                <button
                  onClick={() => setShowTrace((v) => !v)}
                  className={cn(
                    "text-[10px] px-2 py-1 rounded-md border border-border hover:border-brand/30 hover:bg-brand/5 transition flex items-center gap-1",
                    showTrace && "border-brand/40 bg-brand/5 text-brand",
                  )}
                >
                  <Activity className="w-3 h-3" />
                  {showTrace ? uiT("wsPanel.hideTrace") : uiT("wsPanel.trace")}
                </button>
                <button
                  onClick={() => setShowMonitor((v) => !v)}
                  className={cn(
                    "text-[10px] px-2 py-1 rounded-md border border-border hover:border-brand/30 hover:bg-brand/5 transition flex items-center gap-1",
                    showMonitor && "border-brand/40 bg-brand/5 text-brand",
                  )}
                >
                  <Network className="w-3 h-3" />
                  {showMonitor ? uiT("wsPanel.hideMonitor") : uiT("wsPanel.monitor")}
                </button>
              </div>
            </div>

            {/* Quick actions */}
            <div>
              <div className="text-[10px] font-medium text-muted-foreground mb-1.5 flex items-center gap-1">
                <MessageSquare className="w-3 h-3" />
                {uiT("wsPanel.quickActions")}
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                <button
                  onClick={async () => {
                    const t = await getOrCreateEmptyTask({ workspaceId: workspace.id });
                    navigatePanel({
                      to: "/workspace/$workspaceId/task/$taskId",
                      params: { workspaceId: workspace.id, taskId: t.id },
                    });
                  }}
                  className="text-[10px] px-2 py-1 rounded-md border border-border hover:border-brand/30 hover:bg-brand/5 transition flex items-center gap-1"
                >
                  <MessageSquare className="w-3 h-3" />
                  {uiT("wsPanel.quickStart")}
                </button>
                <button
                  onClick={() => {
                    if (!firstUserTask) return;
                    navigatePanel({
                      to: "/workspace/$workspaceId/task/$taskId",
                      params: { workspaceId: workspace.id, taskId: firstUserTask.id },
                    });
                  }}
                  disabled={!firstUserTask}
                  className="text-[10px] px-2 py-1 rounded-md border border-border hover:border-brand/30 hover:bg-brand/5 transition flex items-center gap-1 disabled:opacity-40"
                >
                  <Clock className="w-3 h-3" />
                  {uiT("wsPanel.continueLast")}
                </button>
                <button
                  onClick={async () => {
                    const t = await createTask({ workspaceId: workspace.id, title: "新任务" });
                    navigatePanel({
                      to: "/workspace/$workspaceId/task/$taskId",
                      params: { workspaceId: workspace.id, taskId: t.id },
                    });
                  }}
                  className="text-[10px] px-2 py-1 rounded-md border border-border hover:border-brand/30 hover:bg-brand/5 transition flex items-center gap-1"
                >
                  <Plus className="w-3 h-3" />
                  {uiT("wsPanel.createTask")}
                </button>
                <button
                  onClick={() => setConfirmClearWs(true)}
                  title={uiT("wsPanel.clearWorkspace")}
                  className="text-[10px] px-2 py-1 rounded-md border border-border hover:border-destructive/40 hover:bg-destructive/5 hover:text-destructive transition flex items-center gap-1"
                >
                  <Eraser className="w-3 h-3" />
                  {uiT("wsPanel.clearWorkspace")}
                </button>
              </div>
            </div>

            {/* Inline trace display */}
            {showTrace &&
              (() => {
                const spans = traceSpans ?? [];
                return (
                  <div className="border border-border/60 rounded-md p-2">
                    <div className="text-[10px] font-medium text-muted-foreground mb-1.5 flex items-center gap-1">
                      <Activity className="w-3 h-3" />
                      {uiT("wsPanel.traceTitle")}
                      {spans.length > 0 && (
                        <span className="text-[9px] text-muted-foreground/60">
                          ({spans.length} spans)
                        </span>
                      )}
                    </div>
                    {spans.length === 0 ? (
                      <div className="text-[10px] text-muted-foreground/60 text-center py-2">
                        {uiT("wsPanel.traceEmpty")}
                      </div>
                    ) : (
                      <div className="space-y-1 max-h-[200px] overflow-y-auto scrollbar-thin">
                        {spans.slice(0, 20).map((span) => (
                          <div
                            key={span.span_id}
                            className="flex items-center gap-1.5 text-[10px] py-0.5"
                          >
                            <span
                              className={cn(
                                "w-1.5 h-1.5 rounded-full shrink-0",
                                span.phase === "plan"
                                  ? "bg-blue-400"
                                  : span.phase === "do"
                                    ? "bg-emerald-400"
                                    : span.phase === "check"
                                      ? "bg-amber-400"
                                      : span.phase === "act"
                                        ? "bg-purple-400"
                                        : "bg-slate-400",
                              )}
                            />
                            <span className="truncate min-w-0 flex-1">{span.span_name}</span>
                            <span className="text-[9px] text-muted-foreground/60 shrink-0">
                              {span.duration_ms != null ? `${span.duration_ms}ms` : ""}
                            </span>
                          </div>
                        ))}
                        {spans.length > 20 && (
                          <div className="text-[9px] text-muted-foreground/50 text-center">
                            {uiT("wsPanel.moreSpans", { count: spans.length - 20 })}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })()}

            {/* Inline monitor: subtask tree scoped to this workspace (仿照 Trace 就地展开,不跳页) */}
            {showMonitor && (
              <div className="max-h-[360px] overflow-y-auto scrollbar-thin">
                <SubtaskTree workspaceId={workspace.id} />
              </div>
            )}

            {/* Task list */}
            <div>
              <div className="text-[10px] font-medium text-muted-foreground mb-1.5">
                {uiT("wsPanel.taskList", { count: userTaskCount })}
              </div>
              {allTasks.length === 0 ? (
                <div className="text-[11px] text-muted-foreground text-center py-4">
                  {uiT("wsPanel.noTasks")}
                </div>
              ) : (
                <div className="space-y-1">
                  {/* 顶层行 = 用户创建的任务；子任务会话折叠其内（归父失败者平铺兜底） */}
                  {[
                    ...taskGroups.map((g) => ({ task: g.parent, children: g.children })),
                    ...orphanSubtasks.map((s) => ({ task: s, children: [] as Task[] })),
                  ].map(({ task: t, children }) => {
                    const isRenaming = renameTarget?.id === t.id;
                    const expanded = effectiveExpandedTaskParents.has(t.id);
                    return (
                      <div
                        key={t.id}
                        className={cn(
                          "w-full text-left rounded-md border border-border/60 hover:border-brand/30 hover:bg-brand/5 transition group flex flex-col",
                          t.id === task.id && "border-brand/30 bg-brand/5",
                        )}
                      >
                        <div className="flex items-center">
                          {isRenaming ? (
                            <input
                              autoFocus
                              value={renameTarget!.title}
                              onChange={(e) =>
                                setRenameTarget((r) => (r ? { ...r, title: e.target.value } : r))
                              }
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && renameTarget!.title.trim()) {
                                  renameTask(t.id, renameTarget!.title.trim());
                                  setRenameTarget(null);
                                } else if (e.key === "Escape") {
                                  setRenameTarget(null);
                                }
                              }}
                              onBlur={() => {
                                if (
                                  renameTarget &&
                                  renameTarget.title.trim() &&
                                  renameTarget.title.trim() !== t.title
                                ) {
                                  renameTask(t.id, renameTarget.title.trim());
                                }
                                setRenameTarget(null);
                              }}
                              className="flex-1 min-w-0 text-[11px] px-2 py-1.5 bg-transparent border-none outline-none"
                            />
                          ) : (
                            <>
                              {children.length > 0 && (
                                <button
                                  onClick={() =>
                                    setExpandedTaskParents((prev) => {
                                      const next = new Set(prev);
                                      if (next.has(t.id)) next.delete(t.id);
                                      else next.add(t.id);
                                      return next;
                                    })
                                  }
                                  className="shrink-0 p-1 ml-1 rounded hover:bg-brand/10 text-muted-foreground hover:text-brand transition"
                                  aria-label={uiT("wsOverview.subtaskCount", {
                                    count: children.length,
                                  })}
                                >
                                  {expanded ? (
                                    <ChevronDown className="w-3 h-3" />
                                  ) : (
                                    <ChevronRight className="w-3 h-3" />
                                  )}
                                </button>
                              )}
                              <button
                                onClick={() =>
                                  navigatePanel({
                                    to: "/workspace/$workspaceId/task/$taskId",
                                    params: { workspaceId: workspace.id, taskId: t.id },
                                  })
                                }
                                className="flex-1 flex items-center gap-1.5 min-w-0 px-2 py-1.5"
                              >
                                {t.taskType === "subtask" ? (
                                  <Workflow className="w-3 h-3 shrink-0 text-muted-foreground/70" />
                                ) : (
                                  <MessageSquare className="w-3 h-3 shrink-0 text-muted-foreground" />
                                )}
                                <span className="text-[11px] truncate">{t.title}</span>
                                {children.length > 0 && !expanded && (
                                  <span className="text-[9px] text-muted-foreground/70 shrink-0">
                                    {uiT("wsOverview.subtaskCount", { count: children.length })}
                                  </span>
                                )}
                              </button>
                            </>
                          )}
                          {!isRenaming && (
                            <>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setRenameTarget({ id: t.id, title: t.title });
                                }}
                                className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-brand/10 text-muted-foreground hover:text-brand transition"
                                title={uiT("common.rename")}
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setConfirmDeleteTask({
                                    id: t.id,
                                    title: t.title,
                                    subCount: children.length,
                                  });
                                }}
                                className="opacity-0 group-hover:opacity-100 p-1 mr-1 rounded hover:bg-red-500/10 text-muted-foreground hover:text-red-500 transition"
                                title={uiT("wsPanel.deleteTask")}
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            </>
                          )}
                        </div>
                        {/* Timestamps */}
                        {!isRenaming && (
                          <div className="flex items-center gap-2 px-2 pb-1 text-[9px] text-muted-foreground/70">
                            <span title={uiT("wsPanel.createdTitle")}>
                              {new Date(t.createdAt).toLocaleString(dateLocale(), {
                                month: "2-digit",
                                day: "2-digit",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                            {t.updatedAt !== t.createdAt && (
                              <span title={uiT("wsPanel.updatedTitle")}>
                                {uiT("wsPanel.updatedPrefix")}{" "}
                                {new Date(t.updatedAt).toLocaleString(dateLocale(), {
                                  month: "2-digit",
                                  day: "2-digit",
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })}
                              </span>
                            )}
                          </div>
                        )}
                        {/* 折叠区：编排器自动创建的子任务会话（嵌套在父任务行内） */}
                        {expanded && children.length > 0 && (
                          <div className="border-t border-border/40 py-0.5">
                            {children.map((sub) => (
                              <button
                                key={sub.id}
                                onClick={() =>
                                  navigatePanel({
                                    to: "/workspace/$workspaceId/task/$taskId",
                                    params: { workspaceId: workspace.id, taskId: sub.id },
                                  })
                                }
                                className={cn(
                                  "w-full flex items-center gap-1.5 pl-6 pr-2 py-1 rounded-sm hover:bg-brand/5 transition",
                                  sub.id === task.id && "bg-brand/10",
                                )}
                              >
                                <Workflow className="w-2.5 h-2.5 shrink-0 text-muted-foreground/70" />
                                <span className="text-[10px] truncate text-muted-foreground">
                                  {sub.title}
                                </span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Files Tab ── */}
        {activeTab === "files" && (
          <div
            className={cn(
              "p-2 rounded-md transition-colors",
              isDragOver && "border-2 border-dashed border-brand/50 bg-brand/5",
            )}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={(e) => {
              // Only clear when the pointer actually leaves the tab container
              // (dragleave also fires when moving between child elements)
              if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
                setIsDragOver(false);
              }
            }}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragOver(false);
              if (wsStore.uploading) return;
              void extractDroppedFiles(e).then((files) => {
                if (files.length > 0) {
                  wsStore.uploadFiles(workspace.id, files);
                } else {
                  toast.error(uiT("wsPanel.dropEmpty"));
                }
              });
            }}
          >
            {/* Action bar */}
            <div className="flex items-center gap-1 pb-2">
              <button
                onClick={handleNewFile}
                className="p-1 rounded hover:bg-muted/60 transition"
                title={uiT("wsPanel.newFile")}
              >
                <Plus className="w-3 h-3" />
              </button>
              <button
                onClick={handleNewFolder}
                className="p-1 rounded hover:bg-muted/60 transition"
                title={uiT("wsPanel.newFolder")}
              >
                <Plus className="w-3 h-3 opacity-60" />
              </button>
              <button
                onClick={handleUploadClick}
                className="p-1 rounded hover:bg-muted/60 transition"
                title={uiT("wsPanel.uploadFile")}
                disabled={wsStore.uploading}
              >
                {wsStore.uploading ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Upload className="w-3 h-3" />
                )}
              </button>
              <button
                onClick={handleUploadFolderClick}
                className="p-1 rounded hover:bg-muted/60 transition"
                title={uiT("wsPanel.uploadFolder")}
                disabled={wsStore.uploading}
              >
                <FolderOpen className="w-3 h-3" />
              </button>
              <button
                onClick={() => {
                  setShowSearch(!showSearch);
                  if (showSearch) {
                    wsStore.clearSearch();
                    setSearchQuery("");
                  }
                }}
                className={cn(
                  "p-1 rounded hover:bg-muted/60 transition",
                  showSearch && "text-brand",
                )}
                title={uiT("wsPanel.searchFile")}
              >
                <Search className="w-3 h-3" />
              </button>
              <button
                onClick={() => wsStore.fetchFileTree(workspace.id)}
                className="p-1 rounded hover:bg-muted/60 transition ml-auto"
                title={uiT("wsPanel.refresh")}
              >
                <RefreshCw className="w-3 h-3" />
              </button>
            </div>

            {/* Upload progress bar */}
            {wsStore.uploading && (
              <div className="w-full h-1 bg-muted/60 rounded-full overflow-hidden mb-2">
                <div
                  className="h-full bg-brand rounded-full transition-all"
                  style={{ width: `${wsStore.uploadProgress}%` }}
                />
              </div>
            )}

            {/* Search bar */}
            {showSearch && (
              <div className="flex items-center gap-1 pb-2">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    if (e.target.value.trim()) {
                      wsStore.searchFiles(workspace.id, e.target.value);
                    } else {
                      wsStore.clearSearch();
                    }
                  }}
                  placeholder={uiT("wsPanel.searchPlaceholder")}
                  className="flex-1 text-[11px] px-2 py-1 rounded bg-muted/40 border border-border focus:outline-none focus:border-brand"
                  autoFocus
                />
                <button
                  onClick={() => {
                    setShowSearch(false);
                    wsStore.clearSearch();
                    setSearchQuery("");
                  }}
                  className="p-0.5 rounded hover:bg-muted/60"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}

            {/* Search results */}
            {showSearch && wsStore.searchResults.length > 0 && (
              <div className="mb-2 border border-border rounded-md overflow-hidden">
                <div className="text-[10px] text-muted-foreground px-2 py-1 bg-muted/30 border-b border-border">
                  {uiT("wsPanel.searchResults", { count: wsStore.searchResults.length })}
                </div>
                {wsStore.searchResults.map((r) => (
                  <button
                    key={r.path}
                    onClick={() => {
                      setSelectedPath(r.path);
                      wsStore.openFile(workspace.id, r.path);
                    }}
                    className={cn(
                      "flex items-center gap-1.5 w-full px-2 py-1 text-[11px] text-left hover:bg-muted/60 transition border-b border-border last:border-b-0",
                      selectedPath === r.path && "bg-brand/10 text-brand",
                    )}
                  >
                    <FileText className="w-3 h-3 shrink-0 text-muted-foreground" />
                    <span className="truncate">{r.path}</span>
                  </button>
                ))}
              </div>
            )}
            {showSearch && wsStore.searchLoading && (
              <div className="flex items-center justify-center py-2">
                <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
              </div>
            )}

            {/* File info panel */}
            {showFileInfo && wsStore.selectedFileInfo && (
              <div className="mb-2 border border-brand/20 rounded-md p-2 bg-brand/5 text-[11px] space-y-1">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-brand flex items-center gap-1">
                    <Info className="w-3 h-3" />
                    {uiT("wsPanel.fileInfo")}
                  </span>
                  <button
                    onClick={() => {
                      setShowFileInfo(false);
                      wsStore.clearFileInfo();
                    }}
                    className="p-0.5 rounded hover:bg-muted/60"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
                <div className="text-muted-foreground space-y-0.5">
                  <div>
                    <span className="text-foreground/60">{uiT("wsPanel.fileName")}</span>{" "}
                    {wsStore.selectedFileInfo.name}
                  </div>
                  <div>
                    <span className="text-foreground/60">{uiT("wsPanel.filePath")}</span>{" "}
                    {wsStore.selectedFileInfo.path}
                  </div>
                  <div>
                    <span className="text-foreground/60">{uiT("wsPanel.fileType")}</span>{" "}
                    {wsStore.selectedFileInfo.type === "directory"
                      ? uiT("wsPanel.folderType")
                      : uiT("wsPanel.fileTypeFile")}
                  </div>
                  <div>
                    <span className="text-foreground/60">{uiT("wsPanel.fileSize")}</span>{" "}
                    {formatFileSize(wsStore.selectedFileInfo.size)}
                  </div>
                  {wsStore.selectedFileInfo.mime_type && (
                    <div>
                      <span className="text-foreground/60">MIME:</span>{" "}
                      {wsStore.selectedFileInfo.mime_type}
                    </div>
                  )}
                  {wsStore.selectedFileInfo.language && (
                    <div>
                      <span className="text-foreground/60">{uiT("wsPanel.fileLanguage")}:</span>{" "}
                      {wsStore.selectedFileInfo.language}
                    </div>
                  )}
                  <div>
                    <span className="text-foreground/60">{uiT("wsPanel.fileCreated")}</span>{" "}
                    {formatDate(wsStore.selectedFileInfo.created_at)}
                  </div>
                  <div>
                    <span className="text-foreground/60">{uiT("wsPanel.fileModified")}</span>{" "}
                    {formatDate(wsStore.selectedFileInfo.modified_at)}
                  </div>
                  <div className="flex gap-2">
                    <span>{wsStore.selectedFileInfo.permissions.readable ? "R" : "-"}</span>
                    <span>{wsStore.selectedFileInfo.permissions.writable ? "W" : "-"}</span>
                    <span>{wsStore.selectedFileInfo.permissions.executable ? "X" : "-"}</span>
                  </div>
                </div>
              </div>
            )}
            {showFileInfo && wsStore.fileInfoLoading && (
              <div className="flex items-center justify-center py-2">
                <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
              </div>
            )}
            {showFileInfo && !wsStore.fileInfoLoading && !wsStore.selectedFileInfo && (
              <div className="mb-2 flex items-center justify-between border border-red-500/20 rounded-md px-2 py-1 bg-red-500/5 text-[11px] text-red-500">
                <span className="flex items-center gap-1">
                  <Info className="w-3 h-3" />
                  {uiT("wsPanel.fileInfoFailed")}
                </span>
                <button
                  onClick={() => setShowFileInfo(false)}
                  className="p-0.5 rounded hover:bg-red-500/10"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}

            {isDragOver && (
              <div className="flex items-center justify-center gap-1.5 py-6 text-[11px] text-brand">
                <Upload className="w-4 h-4" />
                <span>{uiT("wsPanel.dropHint")}</span>
              </div>
            )}

            <>
              {fileTreeLoading && (
                <div className="flex items-center justify-center py-3">
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                </div>
              )}

              {fileTree.length === 0 && !fileTreeLoading && (
                <div className="text-[11px] text-muted-foreground text-center py-4">
                  {uiT("common.noFiles")}
                </div>
              )}

              <div className="max-h-[500px] overflow-y-auto scrollbar-thin">
                {fileTree.map((item) => (
                  <FileTreeNode
                    key={item.path}
                    item={item}
                    level={0}
                    selectedPath={selectedPath}
                    onClick={handleFileClick}
                    renderActions={(file) => (
                      <>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            wsStore.downloadFile(workspace.id, file.path);
                          }}
                          className="p-1 rounded hover:bg-muted/60 transition"
                          title={uiT("wsPanel.download")}
                        >
                          <Download className="w-3 h-3" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRename(file.path);
                          }}
                          className="p-1 rounded hover:bg-muted/60 transition"
                          title={uiT("common.rename")}
                        >
                          <Pencil className="w-3 h-3" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(file.path);
                          }}
                          className="p-1 rounded hover:bg-red-500/10 text-red-500 transition"
                          title={uiT("common.delete")}
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            setSelectedPath(file.path);
                            setShowFileInfo(true);
                            await wsStore.fetchFileInfo(workspace.id, file.path);
                          }}
                          className="p-1 rounded hover:bg-muted/60 transition"
                          title={uiT("wsPanel.fileInfo")}
                        >
                          <Info className="w-3 h-3" />
                        </button>
                      </>
                    )}
                  />
                ))}
              </div>
            </>

            {fileContentLoading && (
              <div className="flex items-center justify-center py-3">
                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
              </div>
            )}
          </div>
        )}

        {/* ── Capabilities Tab ── */}
        {activeTab === "capabilities" && (
          <div className="p-3 space-y-3">
            {/* Available LLMs */}
            <CtxSection
              icon={<Cpu className="w-3 h-3" />}
              title={uiT("wsPanel.availableLlm")}
              count={models.length}
            >
              {models.length === 0 ? (
                <div className="text-[10px] text-muted-foreground">{uiT("wsPanel.notLoaded")}</div>
              ) : (
                <div className="space-y-1">
                  {models.map((m) => (
                    <div
                      key={m.id}
                      className={cn(
                        "text-[11px] px-2 py-1 rounded flex items-center gap-1.5",
                        m.id === task.model ? "bg-brand/10 text-brand" : "text-muted-foreground",
                      )}
                    >
                      <Cpu className="w-3 h-3 shrink-0" />
                      <span className="truncate">{m.name}</span>
                      {m.source === "official" && (
                        <span className="text-[8px] px-1 py-px rounded bg-brand/15 text-brand shrink-0">
                          {uiT("wsPanel.official")}
                        </span>
                      )}
                      {m.provider && (
                        <span className="ml-auto text-[9px] opacity-60">{m.provider}</span>
                      )}
                      {m.id === task.model && (
                        <span className="text-[9px] ml-auto">{uiT("wsPanel.current")}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CtxSection>

            {/* System Modes (orchestrator, PDCA, etc.) */}
            <CtxSection
              icon={<Shield className="w-3 h-3" />}
              title={uiT("wsPanel.systemModes")}
              count={systemModes.length}
              loading={resourcesLoading}
            >
              {systemModes.length === 0 ? (
                <div className="text-[10px] text-muted-foreground">{uiT("wsPanel.none")}</div>
              ) : (
                <div className="space-y-0.5">
                  {systemModes.map((m) => (
                    <div
                      key={m.slug}
                      className="flex items-center gap-1.5 text-[11px] text-muted-foreground"
                    >
                      <Shield className="w-2.5 h-2.5 shrink-0" />
                      <span className="truncate">{m.name}</span>
                      <span className="text-[9px] px-1 py-0.5 rounded bg-muted/50 ml-auto">
                        {uiT("wsPanel.system")}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CtxSection>

            {/* Workspace Agents (user-installed agents) */}
            <CtxSection
              icon={<Bot className="w-3 h-3" />}
              title={uiT("wsPanel.workspaceAgents")}
              count={workspaceModes.length}
              loading={resourcesLoading}
              extra={
                <button
                  onClick={() => {
                    setShowMarket(true);
                    fetchMarket("agent");
                  }}
                  className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded border border-border hover:border-brand/30 hover:bg-brand/5 hover:text-brand transition"
                  title={uiT("wsPanel.installAgentFromMarket")}
                >
                  <PackagePlus className="w-2.5 h-2.5" />
                  {uiT("wsPanel.add")}
                </button>
              }
            >
              {workspaceModes.length === 0 ? (
                <div className="text-[10px] text-muted-foreground">{uiT("wsPanel.noAgents")}</div>
              ) : (
                <div className="space-y-0.5">
                  {workspaceModes.map((m) => (
                    <div
                      key={m.slug}
                      className="flex items-center gap-1.5 text-[11px] text-muted-foreground group"
                    >
                      <Bot className="w-2.5 h-2.5 shrink-0" />
                      <span className="truncate">{m.name}</span>
                      <span className="text-[9px] px-1 py-0.5 rounded bg-brand/10 text-brand ml-auto">
                        {uiT("wsPanel.workspace")}
                      </span>
                      {uninstallingIds.has(`mode/${m.slug}`) ? (
                        <Loader2 className="w-2.5 h-2.5 animate-spin shrink-0" />
                      ) : (
                        <button
                          onClick={() => handleUninstallMode(m.slug)}
                          className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-500/10 hover:text-red-500 transition shrink-0"
                          title={uiT("common.delete")}
                        >
                          <Trash2 className="w-2.5 h-2.5" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CtxSection>

            {/* Knowledge Bases */}
            <CtxSection
              icon={<Database className="w-3 h-3" />}
              title={uiT("wsPanel.kbTitle")}
              count={knowledgeBases.length}
              loading={kbLoading}
            >
              {knowledgeBases.length === 0 ? (
                <div className="text-[10px] text-muted-foreground">{uiT("wsPanel.noKb")}</div>
              ) : (
                <div className="space-y-1.5">
                  {knowledgeBases.map((kb) => (
                    <div key={kb.id} className="text-[11px]">
                      <div className="flex items-center gap-1.5">
                        <Database className="w-3 h-3 shrink-0 text-brand/60" />
                        <span className="truncate font-medium">{kb.name}</span>
                        {kb.is_default && (
                          <span className="text-[9px] px-1 py-0.5 rounded bg-brand/10 text-brand">
                            {uiT("input.defaultKb")}
                          </span>
                        )}
                      </div>
                      <div className="text-[9px] text-muted-foreground pl-4.5">
                        {uiT("wsPanel.kbStats", {
                          docs: kb.stats.total_documents,
                          chunks: kb.stats.total_chunks,
                        })}
                        {kb.settings.domain && ` · ${kb.settings.domain}`}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CtxSection>

            {/* Knowledge Domains */}
            {knowledgeDomains.length > 0 && (
              <div>
                <div className="text-[10px] text-muted-foreground mb-1.5">
                  {uiT("wsPanel.kbDomains")}
                </div>
                <div className="flex flex-wrap gap-1">
                  {knowledgeDomains.map((d) => (
                    <span
                      key={d.name}
                      className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted/60 text-muted-foreground"
                    >
                      {d.display_name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Skills */}
            <CtxSection
              icon={<Sparkles className="w-3 h-3" />}
              title={uiT("wsPanel.skills")}
              count={resources?.skills?.length ?? 0}
              loading={resourcesLoading}
              extra={
                <button
                  onClick={() => {
                    setShowMarket(true);
                    fetchMarket("skill");
                  }}
                  className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded border border-border hover:border-brand/30 hover:bg-brand/5 hover:text-brand transition"
                  title={uiT("wsPanel.installSkillFromMarket")}
                >
                  <PackagePlus className="w-2.5 h-2.5" />
                  {uiT("wsPanel.add")}
                </button>
              }
            >
              {!resources?.skills || resources.skills.length === 0 ? (
                <div className="text-[10px] text-muted-foreground">{uiT("wsPanel.noSkills")}</div>
              ) : (
                <div className="space-y-0.5">
                  {resources.skills.map((s) => (
                    <div
                      key={s.slug}
                      className="flex items-center gap-1.5 text-[11px] text-muted-foreground group"
                    >
                      <Sparkles className="w-2.5 h-2.5 shrink-0" />
                      <span className="truncate">{s.name || s.slug}</span>
                      {uninstallingIds.has(`skill/${s.slug}`) ? (
                        <Loader2 className="w-2.5 h-2.5 animate-spin ml-auto shrink-0" />
                      ) : (
                        <button
                          onClick={() => handleUninstallSkill(s.slug)}
                          className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-500/10 hover:text-red-500 transition ml-auto shrink-0"
                          title={uiT("wsPanel.uninstall")}
                        >
                          <Trash2 className="w-2.5 h-2.5" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CtxSection>

            {/* MCP Servers */}
            <CtxSection
              icon={<Wrench className="w-3 h-3" />}
              title={uiT("wsPanel.mcpTitle")}
              count={resources?.mcp_servers?.length ?? 0}
              loading={resourcesLoading}
            >
              {!resources?.mcp_servers || resources.mcp_servers.length === 0 ? (
                <div className="text-[10px] text-muted-foreground">{uiT("wsPanel.noMcp")}</div>
              ) : (
                <div className="space-y-0.5">
                  {resources.mcp_servers.map((s) => (
                    <div
                      key={s.name}
                      className="flex items-center gap-1.5 text-[11px] text-muted-foreground"
                    >
                      <Wrench className="w-2.5 h-2.5 shrink-0" />
                      <span className="truncate">{s.name}</span>
                    </div>
                  ))}
                </div>
              )}
            </CtxSection>

            {/* Team */}
            {resources?.team && (
              <div className="bg-brand/5 border border-brand/15 rounded-lg p-2">
                <div className="flex items-center gap-1.5 mb-1">
                  <UserCircle className="w-3 h-3 text-brand" />
                  <span className="text-[11px] font-medium text-brand">
                    {uiT("wsPanel.team")}: {resources.team.name || resources.team.slug}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1 text-[9px] text-muted-foreground">
                  {resources.team.skills && resources.team.skills.length > 0 && (
                    <span className="px-1.5 py-0.5 rounded bg-muted/50">
                      {uiT("wsPanel.teamSkills", { count: resources.team.skills.length })}
                    </span>
                  )}
                  {resources.team.agents && resources.team.agents.length > 0 && (
                    <span className="px-1.5 py-0.5 rounded bg-muted/50">
                      {uiT("wsPanel.teamAgents", { count: resources.team.agents.length })}
                    </span>
                  )}
                  {resources.team.mcps && resources.team.mcps.length > 0 && (
                    <span className="px-1.5 py-0.5 rounded bg-muted/50">
                      {uiT("wsPanel.teamMcps", { count: resources.team.mcps.length })}
                    </span>
                  )}
                  {resources.team.knowledges && resources.team.knowledges.length > 0 && (
                    <span className="px-1.5 py-0.5 rounded bg-muted/50">
                      {uiT("wsPanel.teamKbs", { count: resources.team.knowledges.length })}
                    </span>
                  )}
                </div>
                {/* Knowledge domain labels (display only) */}
                {resources.team.knowledges && resources.team.knowledges.length > 0 && (
                  <div className="mt-1.5 pt-1.5 border-t border-brand/10">
                    <div className="text-[10px] text-muted-foreground mb-1">
                      {uiT("wsPanel.kbDomains")}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {resources.team.knowledges.map((kid: string) => (
                        <span
                          key={kid}
                          className="text-[9px] px-1.5 py-0.5 rounded bg-muted/40 text-muted-foreground"
                        >
                          {kid.includes("/") ? kid.split("/").pop() : kid}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        {/* ── E5: Extra tabs (injected via extraTabs prop) ── */}
        {extraTabs?.map((ext) =>
          activeTab === ext.id ? (
            <div key={ext.id} className="p-3">
              {ext.content}
            </div>
          ) : null,
        )}
      </div>

      {/* Market Browser Sheet */}
      <Sheet open={showMarket} onOpenChange={setShowMarket}>
        <SheetContent side="right" className="w-[400px] sm:w-[540px] flex flex-col">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-1.5">
              <PackagePlus className="w-4 h-4 text-brand" />
              {uiT("wsPanel.marketTitle")}
            </SheetTitle>
          </SheetHeader>

          {/* Type toggle + search */}
          <div className="flex items-center gap-2 px-1 pb-2">
            <div className="flex rounded-md border border-border overflow-hidden">
              <button
                onClick={() => fetchMarket("agent")}
                className={cn(
                  "text-[11px] px-2.5 py-1 transition",
                  marketType === "agent"
                    ? "bg-brand text-white"
                    : "text-muted-foreground hover:bg-muted/50",
                )}
              >
                {uiT("wsPanel.agents")}
              </button>
              <button
                onClick={() => fetchMarket("skill")}
                className={cn(
                  "text-[11px] px-2.5 py-1 transition",
                  marketType === "skill"
                    ? "bg-brand text-white"
                    : "text-muted-foreground hover:bg-muted/50",
                )}
              >
                {uiT("wsPanel.skillsTab")}
              </button>
            </div>
            <input
              type="text"
              value={marketSearch}
              onChange={(e) => setMarketSearch(e.target.value)}
              placeholder={uiT("wsPanel.marketSearch")}
              className="flex-1 text-[11px] px-2 py-1 rounded bg-muted/40 border border-border focus:outline-none focus:border-brand"
            />
          </div>

          {/* Market items list */}
          <div className="flex-1 overflow-y-auto scrollbar-thin space-y-1.5 px-1">
            {marketLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : marketItems.length === 0 ? (
              <div className="text-[11px] text-muted-foreground text-center py-8">
                {uiT("wsPanel.noResources")}
              </div>
            ) : (
              marketItems
                .filter(
                  (item) =>
                    !marketSearch ||
                    item.name.toLowerCase().includes(marketSearch.toLowerCase()) ||
                    item.slug?.toLowerCase().includes(marketSearch.toLowerCase()),
                )
                .map((item) => {
                  // Market resource ids are multi-segment paths like
                  // "{shard}/{uuid}/versions/{version}".  We need a stable,
                  // unique identifier that resolve() can match — the UUID
                  // (segment index 1) is ideal.  For simpler id formats like
                  // "{org}/{slug}", segment 1 is the slug itself.
                  const idParts = item.id.split("/");
                  const slug = item.slug ?? idParts[1] ?? item.id;
                  const resourceId = `${item.type}/${slug}`;
                  const isInstalled = installedSlugs.has(slug);
                  const isInstalling = installingIds.has(resourceId);
                  return (
                    <div
                      key={item.id}
                      className="flex items-start gap-2 p-2 rounded-md border border-border hover:border-brand/30 transition"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          {marketType === "agent" ? (
                            <Bot className="w-3 h-3 shrink-0 text-brand/60" />
                          ) : (
                            <Sparkles className="w-3 h-3 shrink-0 text-brand/60" />
                          )}
                          <span className="text-[11px] font-medium truncate">{item.name}</span>
                          <span className="text-[9px] text-muted-foreground/60 shrink-0">
                            v{item.version}
                          </span>
                        </div>
                        {item.description && (
                          <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">
                            {item.description}
                          </p>
                        )}
                        {item.tags && item.tags.length > 0 && (
                          <div className="flex flex-wrap gap-0.5 mt-1">
                            {item.tags.slice(0, 3).map((tag) => (
                              <span
                                key={tag}
                                className="text-[8px] px-1 py-px rounded bg-muted/50 text-muted-foreground"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="shrink-0">
                        {isInstalled ? (
                          <span className="flex items-center gap-0.5 text-[9px] px-2 py-1 rounded bg-brand/10 text-brand">
                            <Check className="w-3 h-3" />
                            {uiT("wsPanel.installed")}
                          </span>
                        ) : isInstalling ? (
                          <span className="flex items-center gap-0.5 text-[9px] px-2 py-1 rounded bg-muted/50 text-muted-foreground">
                            <Loader2 className="w-3 h-3 animate-spin" />
                            {uiT("wsPanel.installing")}
                          </span>
                        ) : (
                          <button
                            onClick={() => handleInstallFromMarket(item.type, slug)}
                            className="flex items-center gap-0.5 text-[9px] px-2 py-1 rounded bg-brand text-white hover:bg-brand/90 transition"
                          >
                            <PackagePlus className="w-3 h-3" />
                            {uiT("wsPanel.install")}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
            )}
          </div>
        </SheetContent>
      </Sheet>

      {/* Name input: new file / new folder / rename (replaces window.prompt) */}
      <PromptDialog
        open={nameDialog !== null}
        onOpenChange={(o) => !o && setNameDialog(null)}
        title={
          nameDialog?.kind === "newFile"
            ? uiT("wsPanel.newFilePrompt")
            : nameDialog?.kind === "newFolder"
              ? uiT("wsPanel.newFolderPrompt")
              : uiT("wsPanel.renamePrompt")
        }
        defaultValue={
          nameDialog?.kind === "rename" ? (nameDialog.path?.split("/").pop() ?? "") : ""
        }
        actionLabel={nameDialog?.kind === "rename" ? uiT("common.rename") : uiT("wsPanel.create")}
        onConfirm={handleNameDialogConfirm}
      />

      {/* Delete confirmation: file */}
      <AlertDialog
        open={confirmDeleteFile !== null}
        onOpenChange={(o) => !o && setConfirmDeleteFile(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-destructive">
              {uiT("wsPanel.deleteFile.title")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {uiT("wsPanel.deleteFile.desc", { name: confirmDeleteFile ?? "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{uiT("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={doDeleteFile}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {uiT("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete confirmation: task */}
      <AlertDialog
        open={confirmDeleteTask !== null}
        onOpenChange={(o) => !o && setConfirmDeleteTask(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-destructive">
              {uiT("wsPanel.deleteTask.title")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {uiT("wsPanel.deleteTask.desc", { title: confirmDeleteTask?.title ?? "" })}
              {(confirmDeleteTask?.subCount ?? 0) > 0 && (
                <span className="block mt-1 text-destructive">
                  {uiT("wsPanel.deleteTask.cascade", {
                    count: confirmDeleteTask?.subCount ?? 0,
                  })}
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{uiT("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={doDeleteTask}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {uiT("wsPanel.deleteTask")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Clear workspace confirmation (danger): wipes tasks/logs/files, keeps the workspace itself */}
      <AlertDialog open={confirmClearWs} onOpenChange={setConfirmClearWs}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-destructive">
              {uiT("wsPanel.clearWorkspace.title")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {uiT("wsPanel.clearWorkspace.desc", {
                name: workspace.name,
                count: allTasks.length,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={clearingWs}>{uiT("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                // preventDefault keeps the dialog open (with spinner) until the API settles
                e.preventDefault();
                doClearWorkspace();
              }}
              disabled={clearingWs}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {clearingWs && <Loader2 className="w-3 h-3 animate-spin mr-1" />}
              {uiT("wsPanel.clearWorkspace.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ── Helper components ──────────────────────────────────────────────

function CtxSection({
  icon,
  title,
  count,
  loading,
  extra,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  count?: number | string;
  loading?: boolean;
  extra?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-1.5">
        {icon}
        <span className="text-[10px] font-medium text-muted-foreground">{title}</span>
        {count !== undefined && (
          <span className="text-[9px] text-muted-foreground/60">{count}</span>
        )}
        {loading && <Loader2 className="w-3 h-3 animate-spin" />}
        {extra && <div className="ml-auto">{extra}</div>}
      </div>
      {children}
    </div>
  );
}

function countFiles(acc: number, item: FileTreeItem): number {
  if (item.type === "file") return acc + 1;
  return acc + (item.children?.reduce(countFiles, 0) ?? 0);
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(dateLocale(), {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
