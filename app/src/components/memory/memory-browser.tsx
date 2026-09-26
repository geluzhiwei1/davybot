/**
 * MemoryBrowser — 四象限记忆管理.
 *
 *         手写          Agent自动写
 *      ┌──────────┬──────────┐
 * 用户级 │ ✏️ 用户   │ 🤖 用户   │
 *      │ memory.md │ auto-mem  │
 *      ├──────────┼──────────┤
 * 工作区 │ ✏️ 工作区 │ 🤖 工作区 │
 *      │ memory.md │ auto-mem  │
 *      └──────────┴──────────┘
 *
 * 手写: Textarea 编辑 memory.md
 * 自动: 只读列表 + 清空按钮
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useStore } from "@/lib/store";
import { useWorkspaceStore } from "@/lib/workspace-store";
import { useMemoryStore } from "@/lib/memory-store";
import { memoryApi } from "@/lib/memory-service";
import type { AutoMemoryResponse } from "@/lib/memory-service";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  RefreshCw,
  Save,
  Loader2,
  FileText,
  AlertCircle,
  FolderOpen,
  Bot,
  Trash2,
} from "lucide-react";

// ─── Constants ──────────────────────────────────────────────────

const MEMORY_MD_LINE_LIMIT = 200;

const TOPIC_LABEL_KEYS: Record<string, string> = {
  facts: "browser.topic.facts",
  preferences: "browser.topic.preferences",
  procedures: "browser.topic.procedures",
  debugging: "browser.topic.debugging",
};

const TOPIC_ICONS: Record<string, string> = {
  facts: "📋",
  preferences: "⚙️",
  procedures: "🔧",
  debugging: "🐛",
};

type TabScope = "user" | "workspace";
type TabMode = "manual" | "auto";

// ─── Component ──────────────────────────────────────────────────

export function MemoryBrowser() {
  const { t } = useTranslation("memoryUi");
  // -- Stores --
  const workspaces = useStore((s) => s.workspaces);
  const fetchWorkspaces = useStore((s) => s.fetchWorkspaces);
  const currentWorkspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const setWorkspace = useWorkspaceStore((s) => s.setWorkspace);
  const scope = useMemoryStore((s) => s.scope);
  const setScope = useMemoryStore((s) => s.setScope);

  const activeTab: TabScope = scope;

  // Sub-tab: manual (编辑 memory.md) vs auto (查看自动记忆)
  const [mode, setMode] = useState<TabMode>("manual");

  // -- Manual edit state (memory.md) --
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState<Record<string, string>>({
    user: "",
    workspace: "",
  });
  const [filePath, setFilePath] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // -- Auto memory state --
  const [autoData, setAutoData] = useState<AutoMemoryResponse | null>(null);
  const [autoLoading, setAutoLoading] = useState(false);
  const [clearing, setClearing] = useState(false);

  // Track content per tab
  const draftRef = useRef<Record<string, string>>({ user: "", workspace: "" });

  const isDirty = content !== (savedContent[activeTab] ?? "");
  const lineCount = content.split("\n").length;
  const nearLimit = lineCount >= MEMORY_MD_LINE_LIMIT * 0.85;

  // Ensure workspace list is loaded
  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  // ---- Load manual content ----
  const loadContent = useCallback(
    async (tab: TabScope, wsId?: string) => {
      const effectiveWsId = wsId || currentWorkspaceId;
      if (tab === "workspace" && !effectiveWsId) return;

      setLoading(true);
      setError(null);
      try {
        if (tab === "user") {
          const res = await memoryApi.getUserMemoryMd();
          setContent(res.content || "");
          setSavedContent((p) => ({ ...p, user: res.content || "" }));
          setFilePath(res.path || "");
          draftRef.current.user = res.content || "";
        } else {
          const res = await memoryApi.getWorkspaceMemoryMd(effectiveWsId!);
          setContent(res.content || "");
          setSavedContent((p) => ({ ...p, workspace: res.content || "" }));
          setFilePath(res.path || "");
          draftRef.current.workspace = res.content || "";
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : t("browser.error.loadMemory"));
      } finally {
        setLoading(false);
      }
    },
    [currentWorkspaceId],
  );

  // ---- Load auto memory ----
  const loadAutoMemory = useCallback(
    async (tab: TabScope, wsId?: string) => {
      const effectiveWsId = wsId || currentWorkspaceId;
      if (tab === "workspace" && !effectiveWsId) return;

      setAutoLoading(true);
      setError(null);
      try {
        if (tab === "user") {
          const res = await memoryApi.getUserAutoMemory();
          setAutoData(res);
        } else {
          const res = await memoryApi.getWorkspaceAutoMemory(effectiveWsId!);
          setAutoData(res);
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : t("browser.error.loadAuto"));
      } finally {
        setAutoLoading(false);
      }
    },
    [currentWorkspaceId],
  );

  // ---- Save manual ----
  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      if (activeTab === "user") {
        const res = await memoryApi.updateUserMemoryMd(content);
        setContent(res.content);
        setSavedContent((p) => ({ ...p, user: res.content }));
        draftRef.current.user = res.content;
      } else if (currentWorkspaceId) {
        const res = await memoryApi.updateWorkspaceMemoryMd(currentWorkspaceId, content);
        setContent(res.content);
        setSavedContent((p) => ({ ...p, workspace: res.content }));
        draftRef.current.workspace = res.content;
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("browser.error.save"));
    } finally {
      setSaving(false);
    }
  };

  // ---- Delete one auto memory entry (更新 = 删旧 + 存新) ----
  const [deletingEntry, setDeletingEntry] = useState<string | null>(null);

  const handleDeleteAutoEntry = async (topic: string, line: number) => {
    const key = `${topic}#${line}`;
    setDeletingEntry(key);
    setError(null);
    try {
      if (activeTab === "user") {
        await memoryApi.deleteUserAutoMemoryEntry(topic, line);
      } else if (currentWorkspaceId) {
        await memoryApi.deleteWorkspaceAutoMemoryEntry(currentWorkspaceId, topic, line);
      }
      await loadAutoMemory(activeTab);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("browser.error.clear"));
    } finally {
      setDeletingEntry(null);
    }
  };

  // ---- Clear auto memory ----
  const handleClearAuto = async () => {
    setClearing(true);
    setError(null);
    try {
      if (activeTab === "user") {
        await memoryApi.clearUserAutoMemory();
      } else if (currentWorkspaceId) {
        await memoryApi.clearWorkspaceAutoMemory(currentWorkspaceId);
      }
      await loadAutoMemory(activeTab);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("browser.error.clear"));
    } finally {
      setClearing(false);
    }
  };

  // ---- Tab switching ----
  const handleTabChange = (value: string) => {
    draftRef.current[activeTab] = content;
    const newTab = value as TabScope;
    setScope(newTab);

    if (newTab === "workspace" && !currentWorkspaceId && workspaces.length > 0) {
      const firstWsId = workspaces[0].id;
      setWorkspace(firstWsId);
      if (mode === "manual") loadContent("workspace", firstWsId);
      else loadAutoMemory("workspace", firstWsId);
    } else {
      if (mode === "manual") loadContent(newTab);
      else loadAutoMemory(newTab);
    }
  };

  // ---- Mode switching (manual/auto) ----
  const handleModeChange = (newMode: TabMode) => {
    if (newMode === mode) return;
    if (mode === "manual") draftRef.current[activeTab] = content;
    setMode(newMode);
    if (newMode === "manual") loadContent(activeTab);
    else loadAutoMemory(activeTab);
  };

  // ---- Workspace selection ----
  const handleWorkspaceChange = (wsId: string) => {
    if (mode === "manual") draftRef.current.workspace = content;
    setWorkspace(wsId);
    if (mode === "manual") loadContent("workspace", wsId);
    else loadAutoMemory("workspace", wsId);
  };

  // ---- Initial load ----
  useEffect(() => {
    if (activeTab === "workspace" && !currentWorkspaceId) {
      setScope("user");
      loadContent("user");
    } else {
      loadContent(activeTab);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-select workspace when list loads
  useEffect(() => {
    if (activeTab === "workspace" && !currentWorkspaceId && workspaces.length > 0) {
      const firstWsId = workspaces[0].id;
      setWorkspace(firstWsId);
      if (mode === "manual") loadContent("workspace", firstWsId);
      else loadAutoMemory("workspace", firstWsId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaces.length]);

  // Reload when workspace changes externally
  useEffect(() => {
    if (activeTab === "workspace" && currentWorkspaceId) {
      if (mode === "manual") loadContent("workspace");
      else loadAutoMemory("workspace");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentWorkspaceId]);

  const placeholder =
    activeTab === "user" ? t("browser.placeholder.user") : t("browser.placeholder.workspace");

  const hasWorkspace = !(activeTab === "workspace" && !currentWorkspaceId);

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Scope Tabs + Mode Toggle + Workspace selector */}
      <div className="flex items-center gap-2 flex-wrap">
        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <TabsList>
            <TabsTrigger value="user" className="gap-1">
              {t("browser.tab.user")}
              {draftRef.current.user !== (savedContent.user ?? "") && (
                <span className="ml-1 text-amber-500">*</span>
              )}
            </TabsTrigger>
            <TabsTrigger value="workspace" className="gap-1">
              {t("browser.tab.workspace")}
              {draftRef.current.workspace !== (savedContent.workspace ?? "") && (
                <span className="ml-1 text-amber-500">*</span>
              )}
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Mode toggle: manual edit vs auto memory */}
        <div className="flex items-center gap-0.5 rounded-md border bg-muted/40 p-0.5">
          <button
            className={`flex items-center gap-1 px-2.5 py-1 text-xs rounded transition-colors ${
              mode === "manual"
                ? "bg-background shadow-sm font-medium"
                : "text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => handleModeChange("manual")}
          >
            <FileText className="w-3 h-3" />
            {t("browser.mode.manual")}
          </button>
          <button
            className={`flex items-center gap-1 px-2.5 py-1 text-xs rounded transition-colors ${
              mode === "auto"
                ? "bg-background shadow-sm font-medium"
                : "text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => handleModeChange("auto")}
          >
            <Bot className="w-3 h-3" />
            {t("browser.mode.auto")}
          </button>
        </div>

        {/* Workspace selector */}
        {activeTab === "workspace" && (
          <Select value={currentWorkspaceId ?? ""} onValueChange={handleWorkspaceChange}>
            <SelectTrigger className="h-8 text-xs w-48">
              <SelectValue placeholder={t("browser.workspace.placeholder")} />
            </SelectTrigger>
            <SelectContent>
              {workspaces.length === 0 ? (
                <SelectItem value="__none__" disabled>
                  {t("browser.workspace.none")}
                </SelectItem>
              ) : (
                workspaces.map((ws) => (
                  <SelectItem key={ws.id} value={ws.id} className="text-xs">
                    <span className="flex items-center gap-1.5">
                      <FolderOpen className="w-3 h-3" />
                      {ws.name}
                    </span>
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive flex items-center gap-2">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}

      {/* No workspace message */}
      {!hasWorkspace && !loading && !autoLoading && (
        <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
          {workspaces.length === 0
            ? t("browser.workspace.createFirst")
            : t("browser.workspace.selectFirst")}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════ */}
      {/* Manual mode: Textarea editor for memory.md               */}
      {/* ═══════════════════════════════════════════════════════ */}
      {mode === "manual" && hasWorkspace && (
        <>
          <div className="flex-1 flex flex-col gap-2 min-h-0">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <>
                <Textarea
                  value={content}
                  onChange={(e) => {
                    setContent(e.target.value);
                    draftRef.current[activeTab] = e.target.value;
                  }}
                  placeholder={placeholder}
                  className="flex-1 resize-none font-mono text-[13px] leading-relaxed min-h-[300px]"
                />
                {/* Line count + warning */}
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5 text-muted-foreground truncate">
                    <FileText className="w-3 h-3 shrink-0" />
                    <span className="truncate">{filePath}</span>
                  </div>
                  <span
                    className={nearLimit ? "text-amber-500 font-medium" : "text-muted-foreground"}
                  >
                    {t("browser.lines", { count: lineCount, limit: MEMORY_MD_LINE_LIMIT })}
                    {nearLimit && ` ${t("browser.nearLimit")}`}
                  </span>
                </div>
              </>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1 border-t">
            <Button
              variant="outline"
              size="sm"
              onClick={() => loadContent(activeTab)}
              disabled={loading}
              className="gap-2"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              {t("browser.refresh")}
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!isDirty || saving || loading}
              className="gap-2"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {t("browser.save")}
              {isDirty && <span className="text-amber-300">*</span>}
            </Button>
          </div>
        </>
      )}

      {/* ═══════════════════════════════════════════════════════ */}
      {/* Auto mode: Read-only auto memory browser                  */}
      {/* ═══════════════════════════════════════════════════════ */}
      {mode === "auto" && hasWorkspace && (
        <>
          <div className="flex-1 overflow-y-auto min-h-0">
            {autoLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : !autoData || autoData.stats.total_entries === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-sm text-muted-foreground gap-2">
                <Bot className="w-8 h-8 opacity-40" />
                <p>{t("browser.auto.emptyTitle")}</p>
                <p className="text-xs">{t("browser.auto.emptyHint")}</p>
              </div>
            ) : (
              <div className="space-y-3">
                {/* Stats bar */}
                <div className="flex items-center gap-3 text-xs text-muted-foreground bg-muted/30 rounded-md px-3 py-2">
                  <span>{t("browser.auto.total", { count: autoData.stats.total_entries })}</span>
                  <span>·</span>
                  <span>{t("browser.auto.indexLines", { count: autoData.stats.index_lines })}</span>
                  {autoData.stats.index_near_limit && (
                    <span className="text-amber-500">{t("browser.auto.indexNearLimit")}</span>
                  )}
                  <span className="ml-auto truncate text-[10px]">{autoData.path}</span>
                </div>

                {/* Topic sections */}
                {Object.entries(autoData.topics).map(([cat, content]) => {
                  const entries = content
                    .trim()
                    .split("\n")
                    .filter((l) => l.trim().startsWith("- "));

                  return (
                    <div key={cat} className="rounded-lg border">
                      <div className="flex items-center gap-1.5 px-3 py-2 border-b bg-muted/20">
                        <span>{TOPIC_ICONS[cat] || "📄"}</span>
                        <span className="text-xs font-medium">
                          {TOPIC_LABEL_KEYS[cat] ? t(TOPIC_LABEL_KEYS[cat]) : cat}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {t("browser.auto.entries", { count: entries.length })}
                        </span>
                      </div>
                      <div className="px-3 py-2 text-xs leading-relaxed space-y-1">
                        {entries.map((entry, i) => {
                          const entryKey = `${cat}#${i + 1}`;
                          return (
                            <div key={entryKey} className="group flex items-start gap-1">
                              <span className="flex-1 text-foreground/80">
                                {entry.replace(/^- /, "• ")}
                              </span>
                              <button
                                type="button"
                                title={t("browser.deleteEntry")}
                                onClick={() => handleDeleteAutoEntry(cat, i + 1)}
                                disabled={deletingEntry === entryKey}
                                className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive disabled:opacity-50 shrink-0"
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1 border-t">
            <Button
              variant="outline"
              size="sm"
              onClick={() => loadAutoMemory(activeTab)}
              disabled={autoLoading}
              className="gap-2"
            >
              <RefreshCw className={`h-4 w-4 ${autoLoading ? "animate-spin" : ""}`} />
              {t("browser.refresh")}
            </Button>
            {autoData && autoData.stats.total_entries > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearAuto}
                disabled={clearing}
                className="gap-2 text-destructive hover:text-destructive"
              >
                {clearing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                {t("browser.clear")}
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
