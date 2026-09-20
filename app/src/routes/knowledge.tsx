/**
 * Knowledge Route — Local knowledge base management with 3 tabs.
 * Tab 1: KB CRUD + documents + settings (incl. directory sync)
 * Tab 2: Search (hybrid/vector/graph/fulltext)
 * Tab 3: Knowledge graph (real API data, SVG)
 */
import { dateLocale } from "@/lib/date-locale";
import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import {
  Brain,
  Plus,
  Pencil,
  Trash2,
  RefreshCw,
  Loader2,
  AlertCircle,
  X,
  Search,
  Shuffle,
  BookOpen,
  FileText,
  BarChart3,
  FolderSync,
  Network,
  History,
  Upload,
  Copy,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Star,
  User,
  FolderOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { useStore } from "@/lib/store";
import { useKnowledgeStore } from "@/lib/knowledge-store";
import { useWorkspaceStore } from "@/lib/workspace-store";
import {
  knowledgeBasesApi,
  type KnowledgeBaseItem,
  type KnowledgeBaseSettings,
  type DocumentInfo,
  type SearchResult,
  type GraphEntity,
  type GraphRelation,
  type EntitySource,
  type CreateKBRequest,
  type SyncTaskStatus,
} from "@/lib/api-client";
import { selectFiles, selectedFileToFile, type SelectedFile } from "@/lib/platform/files";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/knowledge")({
  head: () => ({ meta: [{ title: "知识管理 — NormNomos" }] }),
  component: KnowledgePage,
});

// ── Helpers ──────────────────────────────────────────────────────────

const STATUS_LABEL_KEYS: Record<string, string> = {
  active: "knowledge.status.active",
  archived: "knowledge.status.archived",
  deleting: "knowledge.status.deleting",
};
const STATUS_COLOR: Record<string, string> = {
  active: "bg-green-500/10 text-green-600",
  archived: "bg-yellow-500/10 text-yellow-600",
  deleting: "bg-red-500/10 text-red-600",
};

const SEARCH_MODE_LABEL_KEYS: Record<string, string> = {
  hybrid: "knowledge.mode.hybrid",
  vector: "knowledge.mode.vector",
  graph: "knowledge.mode.graph",
  fulltext: "knowledge.mode.fulltext",
};

// Selectable KB domains (must match dawei/knowledge/domains/* profiles)
const DOMAIN_OPTIONS = [
  { value: "general", label: "knowledge.domain.general" },
  { value: "legal", label: "knowledge.domain.legal" },
  { value: "sanctions", label: "knowledge.domain.sanctions" },
  { value: "labor_compliance", label: "knowledge.domain.labor_compliance" },
  { value: "medical", label: "knowledge.domain.medical" },
  { value: "research", label: "knowledge.domain.research" },
];

const EXTRACTION_STRATEGY_OPTIONS = [
  { value: "rule_based", label: "knowledge.extraction.rule_based" },
  { value: "llm", label: "knowledge.extraction.llm" },
  { value: "ner_model", label: "knowledge.extraction.ner_model" },
  { value: "auto", label: "knowledge.extraction.auto" },
];

const RETRIEVAL_MODE_OPTIONS = [
  { value: "hybrid", label: "knowledge.mode.hybrid" },
  { value: "vector", label: "knowledge.mode.vector" },
  { value: "graph", label: "knowledge.mode.graph" },
  { value: "fulltext", label: "knowledge.mode.fulltext" },
];

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(dateLocale(), { hour12: false });
}

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString(dateLocale(), { hour12: false });
}

// Graph color palette
const TYPE_PALETTE = [
  "#3b82f6",
  "#8b5cf6",
  "#f59e0b",
  "#10b981",
  "#ef4444",
  "#06b6d4",
  "#f97316",
  "#ec4899",
  "#6366f1",
  "#84cc16",
];

function typeColor(type: string, map: Map<string, string>): string {
  if (!map.has(type)) {
    map.set(type, TYPE_PALETTE[map.size % TYPE_PALETTE.length]);
  }
  return map.get(type)!;
}

/**
 * Force-directed graph layout (Fruchterman–Reingold): nodes repel, edges act as
 * springs, gentle center gravity. Produces readable clusters instead of a fixed
 * circle. Computed once per entities/relations change; iteration count scales
 * down for large graphs to stay responsive. No external dependency.
 *
 * Returns absolute (x, y) coordinates within the given viewBox.
 */
function computeForceLayout(
  entities: GraphEntity[],
  relations: GraphRelation[],
  width: number,
  height: number,
): { id: string; x: number; y: number }[] {
  const n = entities.length;
  if (n === 0) return [];
  if (n === 1) return [{ id: entities[0].id, x: width / 2, y: height / 2 }];

  const nodes = entities.map((e) => ({
    id: e.id,
    x: width / 2 + (Math.random() - 0.5) * 200,
    y: height / 2 + (Math.random() - 0.5) * 160,
    vx: 0,
    vy: 0,
  }));
  const idMap = new Map(nodes.map((node) => [node.id, node]));
  const edges = relations.filter((r) => idMap.has(r.from_entity) && idMap.has(r.to_entity));

  const k = Math.sqrt((width * height) / n); // ideal spacing
  // Scale iterations down for large graphs so layout stays responsive.
  const iterations = Math.max(60, Math.min(200, Math.round(4000 / n)));

  for (let iter = 0; iter < iterations; iter++) {
    // Repulsion between all node pairs
    for (let i = 0; i < n; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < n; j++) {
        const b = nodes[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const force = (k * k) / dist;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }
    // Attraction along edges (springs)
    for (const e of edges) {
      const a = idMap.get(e.from_entity)!;
      const b = idMap.get(e.to_entity)!;
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const force = (dist * dist) / k;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.vx -= fx;
      a.vy -= fy;
      b.vx += fx;
      b.vy += fy;
    }
    // Center gravity + integrate with cooling + clamp to viewBox
    const cooling = 1 - iter / iterations;
    for (const node of nodes) {
      node.vx += (width / 2 - node.x) * 0.02;
      node.vy += (height / 2 - node.y) * 0.02;
      node.x += node.vx * 0.1 * cooling;
      node.y += node.vy * 0.1 * cooling;
      node.x = Math.max(20, Math.min(width - 20, node.x));
      node.y = Math.max(20, Math.min(height - 20, node.y));
      node.vx *= 0.85;
      node.vy *= 0.85;
    }
  }
  return nodes.map((node) => ({ id: node.id, x: node.x, y: node.y }));
}

// ════════════════════════════════════════════════════════════════════
// Main Page
// ════════════════════════════════════════════════════════════════════

function KnowledgePage() {
  const { t } = useTranslation("routesA");
  const workspaces = useStore((s) => s.workspaces);
  const {
    bases,
    basesLoading,
    error,
    selectedBaseId,
    documents,
    documentsTotal,
    documentsLoading,
    stats,
    statsLoading,
    searchResults,
    searchLoading,
    searchStats,
    entities,
    relations,
    graphLoading,
    entitySources,
    entitySourcesLoading,
    syncTask,
    selectedWorkspaceId,
    fetchBases,
    selectBase,
    createBase,
    updateBase,
    deleteBase,
    setDefaultBase,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
    search,
    fetchGraphData,
    fetchEntitySources,
    startSync,
    pollSyncStatus,
    stopPollingSync,
    cancelSync,
    reindexAll,
    reindexDocument,
    setSelectedWorkspace,
    clearError,
  } = useKnowledgeStore();

  const setWsStore = useWorkspaceStore((s) => s.setWorkspace);

  // Dialog state
  const [activeTab, setActiveTab] = useState("bases");
  const [kbFormOpen, setKbFormOpen] = useState(false);
  const [editingKb, setEditingKb] = useState<KnowledgeBaseItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeBaseItem | null>(null);
  const [detailSubTab, setDetailSubTab] = useState("overview");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState("hybrid");
  const [searchTopK, setSearchTopK] = useState(5);

  // Graph state
  const [graphZoom, setGraphZoom] = useState(1);
  const [graphOffset, setGraphOffset] = useState({ x: 0, y: 0 });
  const [graphSelected, setGraphSelected] = useState<GraphEntity | null>(null);
  const [graphTypeFilter, setGraphTypeFilter] = useState("all");
  const svgRef = useRef<SVGSVGElement>(null);
  const dragging = useRef(false);
  const lastPos = useRef({ x: 0, y: 0 });

  const wsId = selectedWorkspaceId;

  // Fetch bases on mount (user-level, no workspace filter) and when workspace changes
  useEffect(() => {
    fetchBases(wsId ?? undefined);
  }, [wsId]);

  // Fetch docs when docs sub-tab visible
  useEffect(() => {
    if (selectedBaseId && activeTab === "bases" && detailSubTab === "documents") {
      fetchDocuments(selectedBaseId);
    }
  }, [selectedBaseId, activeTab, detailSubTab]);

  // Fetch graph data on graph tab
  useEffect(() => {
    if (selectedBaseId && activeTab === "graph") {
      fetchGraphData(selectedBaseId);
    }
  }, [selectedBaseId, activeTab]);

  // Fetch entity provenance (source docs/pages) when a graph entity is selected
  useEffect(() => {
    if (graphSelected && selectedBaseId) {
      fetchEntitySources(selectedBaseId, graphSelected.id);
    }
  }, [graphSelected, selectedBaseId, fetchEntitySources]);

  // Cleanup sync polling on unmount
  useEffect(() => {
    return () => stopPollingSync();
  }, []);

  // ── Handlers ──
  const handleWorkspaceChange = (id: string) => {
    const effectiveId = id === "__user__" ? null : id;
    setSelectedWorkspace(effectiveId);
    setWsStore(effectiveId || "");
    fetchBases(effectiveId ?? undefined);
  };

  const handleCreate = async (data: Record<string, unknown>) => {
    try {
      const base = await createBase(data as unknown as CreateKBRequest);
      setKbFormOpen(false);
      selectBase(base.id);
      toast.success(t("knowledge.created"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("knowledge.createFailed"));
    }
  };

  const handleUpdate = async (data: Record<string, unknown>) => {
    if (!editingKb) return;
    try {
      await updateBase(editingKb.id, data);
      setKbFormOpen(false);
      setEditingKb(null);
      toast.success(t("knowledge.updated"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("knowledge.updateFailed"));
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteBase(deleteTarget.id);
      setDeleteTarget(null);
      toast.success(t("knowledge.deleted"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("knowledge.deleteFailed"));
    }
  };

  const handleUpload = async (selected: SelectedFile[]) => {
    if (selected.length === 0 || !selectedBaseId) return;
    try {
      const file = selectedFileToFile(selected[0]);
      const res = await uploadDocument(selectedBaseId, file);
      if (res && res.vectors_indexed === false) {
        toast.info(t("knowledge.uploadedVectorsPending"));
      } else {
        toast.success(t("knowledge.uploadSuccess"));
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : t("knowledge.uploadFailed"));
    }
  };

  const handleSearch = async () => {
    if (!selectedBaseId || !searchQuery.trim()) return;
    await search(selectedBaseId, searchQuery.trim(), searchMode, searchTopK);
  };

  const handleReindex = async () => {
    if (!selectedBaseId) return;
    try {
      toast.info(t("knowledge.reindexing"));
      await reindexAll(selectedBaseId);
      toast.success(t("knowledge.reindexDone"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("knowledge.reindexFailed"));
    }
  };

  const handleSync = async (dirPath?: string, forceRebuild?: boolean) => {
    if (!selectedBaseId) return;
    try {
      await startSync(selectedBaseId, dirPath, forceRebuild);
      pollSyncStatus(selectedBaseId);
      toast.success(t("knowledge.syncStarted"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("knowledge.syncStartFailed"));
    }
  };

  // ── Graph interactions ──
  const handleGraphWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setGraphZoom((z) => Math.max(0.2, Math.min(5, z - e.deltaY * 0.001)));
  }, []);
  const handleGraphMouseDown = useCallback((e: React.MouseEvent) => {
    dragging.current = true;
    lastPos.current = { x: e.clientX, y: e.clientY };
  }, []);
  const handleGraphMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging.current) return;
    setGraphOffset((o) => ({
      x: o.x + e.clientX - lastPos.current.x,
      y: o.y + e.clientY - lastPos.current.y,
    }));
    lastPos.current = { x: e.clientX, y: e.clientY };
  }, []);
  const handleGraphMouseUp = useCallback(() => {
    dragging.current = false;
  }, []);

  // Filtered graph data
  const graphEntityTypes = useMemo(() => {
    const types = new Set<string>();
    entities.forEach((e) => types.add(e.type));
    return Array.from(types).sort();
  }, [entities]);

  const filteredEntities = useMemo(() => {
    if (graphTypeFilter === "all") return entities;
    return entities.filter((e) => e.type === graphTypeFilter);
  }, [entities, graphTypeFilter]);

  const filteredRelations = useMemo(() => {
    const entityIds = new Set(filteredEntities.map((e) => e.id));
    return relations.filter((r) => entityIds.has(r.from_entity) && entityIds.has(r.to_entity));
  }, [relations, filteredEntities]);

  const selectedBaseDisplay = bases.find((b) => b.id === selectedBaseId);

  // ── Render ──
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border/60 shrink-0">
        <Brain className="w-5 h-5 text-brand" />
        <h1 className="text-base font-semibold flex-1">{t("knowledge.title")}</h1>

        <Select value={wsId ?? "__user__"} onValueChange={handleWorkspaceChange}>
          <SelectTrigger className="w-48 h-8 text-xs">
            <SelectValue placeholder={t("knowledge.selectScope")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__user__" className="text-xs">
              <span className="flex items-center gap-1.5">
                <User className="w-3 h-3" />
                {t("knowledge.userScope")}
              </span>
            </SelectItem>
            {workspaces.map((ws) => (
              <SelectItem key={ws.id} value={ws.id} className="text-xs">
                <span className="flex items-center gap-1.5">
                  <FolderOpen className="w-3 h-3" />
                  {ws.name}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {bases.length > 0 && (
          <Select value={selectedBaseId ?? ""} onValueChange={(v) => selectBase(v || null)}>
            <SelectTrigger className="w-44 h-8 text-xs">
              <SelectValue placeholder={t("knowledge.selectKb")} />
            </SelectTrigger>
            <SelectContent>
              {bases.map((kb) => (
                <SelectItem key={kb.id} value={kb.id} className="text-xs">
                  {kb.is_default && <Star className="w-3 h-3 inline mr-1 text-yellow-500" />}
                  {kb.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* Main content */}
      <div className="flex-1 min-h-0 overflow-auto p-4">
        <>
          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive flex items-center gap-2 mb-4">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              {error}
              <Button
                variant="ghost"
                size="sm"
                className="h-5 w-5 p-0 ml-auto"
                onClick={clearError}
              >
                <X className="w-3 h-3" />
              </Button>
            </div>
          )}

          <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <TabsList>
                <TabsTrigger value="bases" className="text-sm">
                  {t("knowledge.tabBases")}
                </TabsTrigger>
                <TabsTrigger value="search" className="text-sm" disabled={!selectedBaseId}>
                  {t("knowledge.tabSearch")}
                </TabsTrigger>
                <TabsTrigger value="graph" className="text-sm" disabled={!selectedBaseId}>
                  {t("knowledge.tabGraph")}
                </TabsTrigger>
              </TabsList>
              {activeTab === "bases" && (
                <Button
                  size="sm"
                  className="h-7 text-xs gap-1"
                  onClick={() => {
                    setEditingKb(null);
                    setKbFormOpen(true);
                  }}
                >
                  <Plus className="w-3.5 h-3.5" />
                  {t("knowledge.newKb")}
                </Button>
              )}
            </div>

            {/* ═══ Tab 1: KB Management ═══ */}
            <TabsContent value="bases" className="mt-0 flex-1 min-h-0">
              <div className="flex gap-4 min-h-0 h-full">
                <div className="w-72 shrink-0 overflow-auto space-y-2 pr-2 border-r border-border/40">
                  {basesLoading && bases.length === 0 ? (
                    <div className="flex justify-center py-8">
                      <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                    </div>
                  ) : bases.length === 0 ? (
                    <EmptyHint
                      icon={<BookOpen className="w-8 h-8 mb-2 opacity-20" />}
                      title={t("knowledge.emptyKbTitle")}
                      desc={t("knowledge.emptyKbDesc")}
                    />
                  ) : (
                    bases.map((kb) => (
                      <KBListItem
                        key={kb.id}
                        kb={kb}
                        isSelected={kb.id === selectedBaseId}
                        onSelect={() => selectBase(kb.id)}
                        onSetDefault={() => setDefaultBase(kb.id)}
                        onEdit={() => {
                          setEditingKb(kb);
                          setKbFormOpen(true);
                        }}
                        onDelete={() => setDeleteTarget(kb)}
                      />
                    ))
                  )}
                </div>

                <div className="flex-1 min-w-0 overflow-auto">
                  {selectedBaseDisplay ? (
                    <KBDetailPanel
                      kb={selectedBaseDisplay}
                      stats={stats}
                      statsLoading={statsLoading}
                      documents={documents}
                      documentsTotal={documentsTotal}
                      documentsLoading={documentsLoading}
                      syncTask={syncTask}
                      subTab={detailSubTab}
                      onSubTabChange={setDetailSubTab}
                      onUpload={handleUpload}
                      onDeleteDoc={(docId) =>
                        selectedBaseId && deleteDocument(selectedBaseId, docId)
                      }
                      onReindex={handleReindex}
                      onSync={handleSync}
                      onCancelSync={() => selectedBaseId && cancelSync(selectedBaseId)}
                      onEdit={() => {
                        setEditingKb(selectedBaseDisplay);
                        setKbFormOpen(true);
                      }}
                      onPageChange={(page) =>
                        selectedBaseId && fetchDocuments(selectedBaseId, page * 10, 10)
                      }
                      onSaveSettings={async (settings) => {
                        if (selectedBaseId) await updateBase(selectedBaseId, { settings });
                      }}
                      onScanDir={(dir) =>
                        selectedBaseId
                          ? knowledgeBasesApi.scanDir(selectedBaseId, dir)
                          : Promise.reject(new Error(t("knowledge.noKbSelected")))
                      }
                      onReindexDoc={(docId) =>
                        selectedBaseId && reindexDocument(selectedBaseId, docId)
                      }
                    />
                  ) : (
                    <EmptyHint
                      icon={<BookOpen className="w-12 h-12 mb-4 opacity-20" />}
                      title={
                        bases.length === 0
                          ? t("knowledge.createKbFirst")
                          : t("knowledge.selectKbTitle")
                      }
                      desc={t("knowledge.selectKbDesc")}
                    />
                  )}
                </div>
              </div>
            </TabsContent>

            {/* ═══ Tab 2: Search ═══ */}
            <TabsContent value="search" className="mt-0 flex-1 min-h-0">
              <SearchPanel
                query={searchQuery}
                mode={searchMode}
                topK={searchTopK}
                results={searchResults}
                loading={searchLoading}
                stats={searchStats}
                onQueryChange={setSearchQuery}
                onModeChange={setSearchMode}
                onTopKChange={setSearchTopK}
                onSearch={handleSearch}
              />
            </TabsContent>

            {/* ═══ Tab 3: Graph ═══ */}
            <TabsContent value="graph" className="mt-0 flex-1 min-h-0">
              <GraphPanel
                entities={filteredEntities}
                relations={filteredRelations}
                entityTypes={graphEntityTypes}
                typeFilter={graphTypeFilter}
                loading={graphLoading}
                selected={graphSelected}
                sources={entitySources}
                sourcesLoading={entitySourcesLoading}
                zoom={graphZoom}
                offset={graphOffset}
                svgRef={svgRef}
                onTypeFilterChange={setGraphTypeFilter}
                onSelect={setGraphSelected}
                onWheel={handleGraphWheel}
                onMouseDown={handleGraphMouseDown}
                onMouseMove={handleGraphMouseMove}
                onMouseUp={handleGraphMouseUp}
                onZoomIn={() => setGraphZoom((z) => Math.min(5, z * 1.2))}
                onZoomOut={() => setGraphZoom((z) => Math.max(0.2, z / 1.2))}
                onReset={() => {
                  setGraphZoom(1);
                  setGraphOffset({ x: 0, y: 0 });
                }}
                onRefresh={() => selectedBaseId && fetchGraphData(selectedBaseId)}
              />
            </TabsContent>
          </Tabs>
        </>
      </div>

      {/* Dialogs */}
      <KBFormDialog
        open={kbFormOpen}
        onOpenChange={(o) => {
          setKbFormOpen(o);
          if (!o) setEditingKb(null);
        }}
        editingKb={editingKb}
        workspaceId={wsId}
        onSubmit={editingKb ? handleUpdate : handleCreate}
      />

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => {
          if (!o) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("knowledge.deleteKbTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("knowledge.deleteKbDesc", { name: deleteTarget?.name ?? "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("knowledge.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("knowledge.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// Empty Hint
// ════════════════════════════════════════════════════════════════════

function EmptyHint({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
      {icon}
      <p className="text-sm font-medium">{title}</p>
      <p className="text-xs mt-1">{desc}</p>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// KB List Item (sidebar card)
// ════════════════════════════════════════════════════════════════════

function KBListItem({
  kb,
  isSelected,
  onSelect,
  onSetDefault,
  onEdit,
  onDelete,
}: {
  kb: KnowledgeBaseItem;
  isSelected: boolean;
  onSelect: () => void;
  onSetDefault: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation("routesA");
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className={cn(
        "w-full text-left p-3 rounded-xl border transition-all group cursor-pointer",
        isSelected
          ? "border-brand/40 bg-brand/5 shadow-sm"
          : "border-border bg-card hover:border-brand/30 hover:bg-accent/50",
      )}
    >
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-medium text-sm truncate">{kb.name}</span>
            {kb.is_default && <Star className="w-3 h-3 shrink-0 text-yellow-500" />}
          </div>
          {kb.description && (
            <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-1">
              {kb.description}
            </p>
          )}
          <div className="flex items-center gap-1.5 mt-1.5">
            <Badge variant="outline" className={cn("text-[10px]", STATUS_COLOR[kb.status])}>
              {STATUS_LABEL_KEYS[kb.status] ? t(STATUS_LABEL_KEYS[kb.status]) : kb.status}
            </Badge>
            <span className="text-[10px] text-muted-foreground">
              {t("knowledge.docsCount", { count: kb.stats.total_documents })}
            </span>
          </div>
        </div>
        {isSelected && (
          <div className="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            {!kb.is_default && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={(ev) => {
                  ev.stopPropagation();
                  onSetDefault();
                }}
                title={t("knowledge.setDefault")}
              >
                <Star className="w-3 h-3" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={(ev) => {
                ev.stopPropagation();
                onEdit();
              }}
              title={t("knowledge.edit")}
            >
              <Pencil className="w-3 h-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-destructive"
              onClick={(ev) => {
                ev.stopPropagation();
                onDelete();
              }}
              title={t("knowledge.delete")}
            >
              <Trash2 className="w-3 h-3" />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// KB Detail Panel (sub-tabs: overview / documents / settings / sync)
// ════════════════════════════════════════════════════════════════════

function KBDetailPanel({
  kb,
  stats,
  statsLoading,
  documents,
  documentsTotal,
  documentsLoading,
  syncTask,
  subTab,
  onSubTabChange,
  onUpload,
  onDeleteDoc,
  onReindex,
  onSync,
  onCancelSync,
  onEdit,
  onPageChange,
  onSaveSettings,
  onScanDir,
  onReindexDoc,
}: {
  kb: KnowledgeBaseItem;
  stats: KnowledgeBaseItem["stats"] | null;
  statsLoading: boolean;
  documents: DocumentInfo[];
  documentsTotal: number;
  documentsLoading: boolean;
  syncTask: import("@/lib/api-client").SyncTaskStatus | null;
  subTab: string;
  onSubTabChange: (t: string) => void;
  onUpload: (selected: SelectedFile[]) => void;
  onDeleteDoc: (docId: string) => void;
  onReindex: () => void;
  onSync: (dirPath?: string, forceRebuild?: boolean) => void;
  onCancelSync: () => void;
  onEdit: () => void;
  onPageChange: (page: number) => void;
  onSaveSettings: (settings: KnowledgeBaseSettings) => Promise<void>;
  onScanDir: (
    dirPath?: string,
  ) => Promise<{ total: number; new_count: number; existing_count: number }>;
  onReindexDoc: (docId: string) => void;
}) {
  const { t } = useTranslation("routesA");
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <BookOpen className="w-5 h-5 text-brand" />
        <h2 className="text-lg font-semibold flex-1">{kb.name}</h2>
        <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={onEdit}>
          <Pencil className="w-3 h-3" />
          {t("knowledge.edit")}
        </Button>
      </div>
      {kb.description && <p className="text-sm text-muted-foreground">{kb.description}</p>}

      <Tabs value={subTab} onValueChange={onSubTabChange}>
        <TabsList className="mb-3">
          <TabsTrigger value="overview" className="text-xs">
            {t("knowledge.subOverview")}
          </TabsTrigger>
          <TabsTrigger value="documents" className="text-xs">
            {t("knowledge.subDocuments")}
          </TabsTrigger>
          <TabsTrigger value="settings" className="text-xs">
            {t("knowledge.subSettings")}
          </TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview" className="mt-0">
          {stats && stats.vectors_pending > 0 && (
            <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-3 text-xs text-yellow-700 dark:text-yellow-500 flex items-center gap-2 mb-3">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{t("knowledge.vectorsPending", { count: stats.vectors_pending })}</span>
            </div>
          )}
          {statsLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin" />
            </div>
          ) : stats ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              <StatCard
                label={t("knowledge.statDocs")}
                value={stats.total_documents}
                icon={<FileText className="w-4 h-4" />}
              />
              <StatCard
                label={t("knowledge.statChunks")}
                value={stats.total_chunks}
                icon={<BarChart3 className="w-4 h-4" />}
              />
              <StatCard
                label={t("knowledge.statEntities")}
                value={stats.total_entities}
                icon={<Network className="w-4 h-4" />}
              />
              <StatCard
                label={t("knowledge.statRelations")}
                value={stats.total_relations}
                icon={<Network className="w-4 h-4" />}
              />
              <StatCard
                label={t("knowledge.statIndexed")}
                value={stats.indexed_documents}
                icon={<RefreshCw className="w-4 h-4" />}
              />
              <StatCard
                label={t("knowledge.statStorage")}
                value={formatBytes(stats.storage_size_bytes)}
                icon={<FileText className="w-4 h-4" />}
              />
              <StatCard
                label={t("knowledge.statLastIndexed")}
                value={formatDate(stats.last_indexed_at)}
                icon={<History className="w-4 h-4" />}
                className="col-span-2"
              />
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">{t("knowledge.noStats")}</p>
          )}
          <div className="rounded-lg border p-3 space-y-1.5 text-xs">
            <InfoRow
              label={t("knowledge.status")}
              value={
                <Badge variant="outline" className={cn("text-[10px]", STATUS_COLOR[kb.status])}>
                  {STATUS_LABEL_KEYS[kb.status] ? t(STATUS_LABEL_KEYS[kb.status]) : kb.status}
                </Badge>
              }
            />
            <InfoRow
              label={t("knowledge.defaultKb")}
              value={kb.is_default ? t("knowledge.yes") : t("knowledge.no")}
            />
            <InfoRow label={t("knowledge.createdAt")} value={formatDate(kb.created_at)} />
            <InfoRow label={t("knowledge.updatedAt")} value={formatDate(kb.updated_at)} />
            <InfoRow label={t("knowledge.createdBy")} value={kb.created_by} />
            <InfoRow
              label={t("knowledge.storagePath")}
              value={<code className="text-[10px]">{kb.storage_path}</code>}
            />
            {kb.tags.length > 0 && (
              <InfoRow
                label={t("knowledge.tags")}
                value={kb.tags.map((t) => (
                  <Badge key={t} variant="secondary" className="text-[10px] mr-1">
                    {t}
                  </Badge>
                ))}
              />
            )}
          </div>
        </TabsContent>

        {/* Documents */}
        <TabsContent value="documents" className="mt-0">
          <div className="flex items-center gap-2 mb-3">
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1"
              onClick={async () => {
                const selected = await selectFiles({
                  accept: ".md,.markdown,.pdf,.docx,.txt",
                  wantFile: true,
                });
                onUpload(selected);
              }}
            >
              <Upload className="w-3 h-3" />
              {t("knowledge.uploadDoc")}
            </Button>
            <span className="text-[10px] text-muted-foreground">
              {t("knowledge.uploadFormats")}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1 ml-auto text-destructive hover:text-destructive"
              onClick={onReindex}
            >
              <RotateCcw className="w-3 h-3" />
              {t("knowledge.reindexAll")}
            </Button>
          </div>

          {documentsLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin" />
            </div>
          ) : documents.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-8">
              {t("knowledge.noDocs")}
            </p>
          ) : (
            <>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b text-left">
                    <th className="py-2 font-medium text-muted-foreground">
                      {t("knowledge.colFileName")}
                    </th>
                    <th className="py-2 font-medium text-muted-foreground">
                      {t("knowledge.colSize")}
                    </th>
                    <th className="py-2 font-medium text-muted-foreground">
                      {t("knowledge.colUploadedAt")}
                    </th>
                    <th className="py-2 font-medium text-muted-foreground text-right">
                      {t("knowledge.colActions")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={doc.id} className="border-b last:border-0">
                      <td className="py-2 font-mono text-[11px] truncate max-w-48">
                        {doc.file_name}
                      </td>
                      <td className="py-2">{formatBytes(doc.file_size)}</td>
                      <td className="py-2">{formatTimestamp(doc.uploaded_at)}</td>
                      <td className="py-2 text-right">
                        <div className="flex items-center justify-end gap-0.5">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={() => onReindexDoc(doc.id)}
                            title={t("knowledge.reindexDoc")}
                          >
                            <RotateCcw className="w-3 h-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 text-destructive"
                            onClick={() => onDeleteDoc(doc.id)}
                            title={t("knowledge.delete")}
                          >
                            <Trash2 className="w-3 h-3" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {documentsTotal > 10 && (
                <div className="flex justify-center gap-1 mt-3">
                  {Array.from({ length: Math.ceil(documentsTotal / 10) }, (_, i) => (
                    <Button
                      key={i}
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 text-xs p-0"
                      onClick={() => onPageChange(i)}
                    >
                      {i + 1}
                    </Button>
                  ))}
                </div>
              )}
            </>
          )}
        </TabsContent>

        {/* Settings */}
        <TabsContent value="settings" className="mt-0">
          <KBSettingsForm
            kb={kb}
            onSave={onSaveSettings}
            syncTask={syncTask}
            onSync={onSync}
            onCancelSync={onCancelSync}
            onScanDir={onScanDir}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ── Stat Card ──

function StatCard({
  label,
  value,
  icon,
  className,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border p-3", className)}>
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground mb-1">
        {icon} {label}
      </div>
      <p className="text-sm font-semibold">{value}</p>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <span className="text-muted-foreground w-20 shrink-0">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function SettingsRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 py-0.5">
      <span className="text-muted-foreground w-28 shrink-0">{label}</span>
      <span className="font-mono text-[11px]">{value === "" ? "—" : value}</span>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// Search Panel
// ════════════════════════════════════════════════════════════════════

function SearchPanel({
  query,
  mode,
  topK,
  results,
  loading,
  stats,
  onQueryChange,
  onModeChange,
  onTopKChange,
  onSearch,
}: {
  query: string;
  mode: string;
  topK: number;
  results: SearchResult[];
  loading: boolean;
  stats: {
    vector_count: number;
    graph_count: number;
    fulltext_count: number;
    latency_ms: number;
  } | null;
  onQueryChange: (v: string) => void;
  onModeChange: (v: string) => void;
  onTopKChange: (v: number) => void;
  onSearch: () => void;
}) {
  const { t } = useTranslation("routesA");
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            className="pl-7 h-9 text-sm"
            placeholder={t("knowledge.searchPlaceholder")}
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) onSearch();
            }}
          />
        </div>
        <Select value={mode} onValueChange={onModeChange}>
          <SelectTrigger className="w-24 h-9 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="hybrid">{t("knowledge.mode.hybrid")}</SelectItem>
            <SelectItem value="vector">{t("knowledge.mode.vector")}</SelectItem>
            <SelectItem value="graph">{t("knowledge.mode.graph")}</SelectItem>
            <SelectItem value="fulltext">{t("knowledge.mode.fulltext")}</SelectItem>
          </SelectContent>
        </Select>
        <Select value={String(topK)} onValueChange={(v) => onTopKChange(Number(v))}>
          <SelectTrigger className="w-16 h-9 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[3, 5, 10, 20].map((k) => (
              <SelectItem key={k} value={String(k)}>
                Top {k}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" className="h-9 text-xs" onClick={onSearch} disabled={loading}>
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : t("knowledge.search")}
        </Button>
      </div>

      {stats && (
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <span>{t("knowledge.statVector", { count: stats.vector_count })}</span>
          <span>{t("knowledge.statGraph", { count: stats.graph_count })}</span>
          <span>{t("knowledge.statFulltext", { count: stats.fulltext_count })}</span>
          <span>{t("knowledge.statLatency", { ms: stats.latency_ms })}</span>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : results.length === 0 && query ? (
        <p className="text-xs text-muted-foreground text-center py-8">{t("knowledge.noResults")}</p>
      ) : (
        <div className="space-y-2">
          {results.map((r, i) => (
            <div key={r.id || i} className="rounded-lg border p-3 space-y-1.5">
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="text-[10px]">
                  {SEARCH_MODE_LABEL_KEYS[r.source]
                    ? t(SEARCH_MODE_LABEL_KEYS[r.source])
                    : r.source}
                </Badge>
                <span className="text-[10px] text-muted-foreground">
                  score: {r.score.toFixed(4)}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5 ml-auto"
                  onClick={() => {
                    navigator.clipboard.writeText(r.content);
                    toast.success(t("knowledge.copied"));
                  }}
                >
                  <Copy className="w-3 h-3" />
                </Button>
              </div>
              <p className="text-xs leading-relaxed whitespace-pre-wrap line-clamp-8">
                {r.content}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// Graph Panel
// ════════════════════════════════════════════════════════════════════

function GraphPanel({
  entities,
  relations,
  entityTypes,
  typeFilter,
  loading,
  selected,
  sources,
  sourcesLoading,
  zoom,
  offset,
  svgRef,
  onTypeFilterChange,
  onSelect,
  onWheel,
  onMouseDown,
  onMouseMove,
  onMouseUp,
  onZoomIn,
  onZoomOut,
  onReset,
  onRefresh,
}: {
  entities: GraphEntity[];
  relations: GraphRelation[];
  entityTypes: string[];
  typeFilter: string;
  loading: boolean;
  selected: GraphEntity | null;
  sources: EntitySource[] | null;
  sourcesLoading: boolean;
  zoom: number;
  offset: { x: number; y: number };
  svgRef: React.RefObject<SVGSVGElement | null>;
  onTypeFilterChange: (t: string) => void;
  onSelect: (e: GraphEntity | null) => void;
  onWheel: (e: React.WheelEvent) => void;
  onMouseDown: (e: React.MouseEvent) => void;
  onMouseMove: (e: React.MouseEvent) => void;
  onMouseUp: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
  onRefresh: () => void;
}) {
  const { t } = useTranslation("routesA");
  const colorMap = useMemo(() => new Map<string, string>(), []);

  // layoutSeed lets the user request a fresh force-directed arrangement.
  const [layoutSeed, setLayoutSeed] = useState(0);

  // Force-directed layout (recomputed when entities/relations/filter/seed change)
  const positioned = useMemo(() => {
    void layoutSeed; // referenced so a seed bump triggers recompute
    const layout = computeForceLayout(entities, relations, 600, 500);
    const posMap = new Map(layout.map((p) => [p.id, p]));
    return entities.map((e) => ({
      ...e,
      x: posMap.get(e.id)?.x ?? 300,
      y: posMap.get(e.id)?.y ?? 250,
    }));
  }, [entities, relations, layoutSeed]);

  const nodeMap = useMemo(() => {
    const m = new Map<string, (typeof positioned)[0]>();
    positioned.forEach((e) => m.set(e.id, e));
    return m;
  }, [positioned]);

  const selectedRelations = useMemo(() => {
    if (!selected) return [];
    return relations.filter((r) => r.from_entity === selected.id || r.to_entity === selected.id);
  }, [selected, relations]);

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <Select value={typeFilter} onValueChange={onTypeFilterChange}>
            <SelectTrigger className="w-28 h-7 text-xs">
              <SelectValue placeholder={t("knowledge.typeFilter")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("knowledge.allTypes")}</SelectItem>
              {entityTypes.map((t) => (
                <SelectItem key={t} value={t}>
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-[10px] text-muted-foreground">
            {t("knowledge.graphSummary", {
              entities: entities.length,
              relations: relations.length,
            })}
          </span>
        </div>
        <div className="flex gap-1">
          <Button variant="outline" size="sm" className="h-6 w-6 p-0" onClick={onZoomIn}>
            <ZoomIn className="w-3 h-3" />
          </Button>
          <Button variant="outline" size="sm" className="h-6 w-6 p-0" onClick={onZoomOut}>
            <ZoomOut className="w-3 h-3" />
          </Button>
          <Button variant="outline" size="sm" className="h-6 w-6 p-0" onClick={onReset}>
            <RotateCcw className="w-3 h-3" />
          </Button>
          <Button variant="outline" size="sm" className="h-6 w-6 p-0" onClick={onRefresh}>
            <RefreshCw className="w-3 h-3" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => setLayoutSeed((s) => s + 1)}
            title={t("knowledge.relayout")}
          >
            <Shuffle className="w-3 h-3" />
          </Button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0 gap-3">
        <Card className="flex-1 overflow-hidden">
          {loading ? (
            <div className="flex justify-center items-center h-full">
              <Loader2 className="w-5 h-5 animate-spin" />
            </div>
          ) : entities.length === 0 ? (
            <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
              {t("knowledge.noGraphData")}
            </div>
          ) : (
            <svg
              ref={svgRef}
              className="w-full h-full cursor-grab active:cursor-grabbing"
              viewBox="0 0 600 500"
              onWheel={onWheel}
              onMouseDown={onMouseDown}
              onMouseMove={onMouseMove}
              onMouseUp={onMouseUp}
              onMouseLeave={onMouseUp}
            >
              <g transform={`translate(${offset.x / zoom}, ${offset.y / zoom}) scale(${zoom})`}>
                {relations.map((rel) => {
                  const from = nodeMap.get(rel.from_entity);
                  const to = nodeMap.get(rel.to_entity);
                  if (!from || !to) return null;
                  return (
                    <line
                      key={rel.id}
                      x1={from.x}
                      y1={from.y}
                      x2={to.x}
                      y2={to.y}
                      stroke="#94a3b8"
                      strokeWidth={Math.max(0.5, rel.weight * 2)}
                      opacity={0.4}
                    />
                  );
                })}
                {positioned.map((entity) => {
                  const color = typeColor(entity.type, colorMap);
                  const isSelected = selected?.id === entity.id;
                  return (
                    <g key={entity.id} className="cursor-pointer" onClick={() => onSelect(entity)}>
                      <circle
                        cx={entity.x}
                        cy={entity.y}
                        r={isSelected ? 14 : 10}
                        fill={color}
                        opacity={isSelected ? 0.95 : 0.75}
                      />
                      {isSelected && (
                        <circle
                          cx={entity.x}
                          cy={entity.y}
                          r={17}
                          fill="none"
                          stroke={color}
                          strokeWidth={2}
                        />
                      )}
                      <text
                        x={entity.x}
                        y={entity.y + 16}
                        textAnchor="middle"
                        className="text-[9px] fill-muted-foreground pointer-events-none select-none"
                      >
                        {entity.name.length > 6 ? entity.name.slice(0, 6) + ".." : entity.name}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          )}
        </Card>

        {selected && (
          <Card className="w-56 shrink-0 overflow-auto">
            <CardContent className="p-3 space-y-2">
              <div className="flex items-center gap-2">
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: typeColor(selected.type, colorMap) }}
                />
                <span className="font-medium text-sm">{selected.name}</span>
              </div>
              <Badge variant="outline" className="text-[10px]">
                {selected.type}
              </Badge>
              {selected.description && (
                <p className="text-[11px] text-muted-foreground">{selected.description}</p>
              )}
              <div className="space-y-1 pt-1">
                {Object.entries(selected.properties).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-[11px]">
                    <span className="text-muted-foreground">{k}</span>
                    <span>{String(v)}</span>
                  </div>
                ))}
              </div>

              {/* Provenance — source documents/pages for this entity */}
              {sourcesLoading ? (
                <div className="flex justify-center py-1">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
                </div>
              ) : sources && sources.length > 0 ? (
                <div className="pt-2 border-t">
                  <p className="text-[11px] font-medium text-muted-foreground mb-1">
                    {t("knowledge.sourcesCount", { count: sources.length })}
                  </p>
                  {sources.slice(0, 10).map((s, i) => (
                    <div key={i} className="text-[11px] py-0.5">
                      <span className="font-medium">{s.document_title || "—"}</span>
                      {s.page_number != null && (
                        <span className="text-muted-foreground"> · p{s.page_number}</span>
                      )}
                      {s.content && (
                        <p className="text-muted-foreground line-clamp-2">{s.content}</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : null}

              {selectedRelations.length > 0 && (
                <div className="pt-2 border-t">
                  <p className="text-[11px] font-medium text-muted-foreground mb-1">
                    {t("knowledge.relatedCount", { count: selectedRelations.length })}
                  </p>
                  {selectedRelations.slice(0, 20).map((r) => {
                    const otherId = r.from_entity === selected.id ? r.to_entity : r.from_entity;
                    const otherEntity = entities.find((e) => e.id === otherId);
                    return (
                      <div key={r.id} className="text-[11px] py-0.5 flex items-center gap-1">
                        <span className="text-muted-foreground">{r.relation_type}</span>
                        <span className="text-muted-foreground">→</span>
                        <span
                          className="font-medium cursor-pointer hover:underline"
                          onClick={() => {
                            const e = entities.find((en) => en.id === otherId);
                            if (e) onSelect(e);
                          }}
                        >
                          {otherEntity?.name || otherId.slice(0, 8)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-xs w-full"
                onClick={() => onSelect(null)}
              >
                {t("knowledge.closeDetail")}
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// KB Form Dialog
// ════════════════════════════════════════════════════════════════════

function KBFormDialog({
  open,
  onOpenChange,
  editingKb,
  workspaceId,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  editingKb: KnowledgeBaseItem | null;
  workspaceId: string | null;
  onSubmit: (data: Record<string, unknown>) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  // Settings (create-only). Edit mode edits name/desc here; full settings live in Settings tab.
  const [domain, setDomain] = useState("general");
  const [watchDir, setWatchDir] = useState("");
  const [extractionStrategy, setExtractionStrategy] = useState("llm");
  const [enableGraph, setEnableGraph] = useState(true);
  const [enableFulltext, setEnableFulltext] = useState(true);
  const [chunkSize, setChunkSize] = useState(1000);
  const [chunkOverlap, setChunkOverlap] = useState(200);
  const [submitting, setSubmitting] = useState(false);

  const { t } = useTranslation("routesA");
  const isEdit = !!editingKb;

  useEffect(() => {
    if (!open) return;
    if (editingKb) {
      setName(editingKb.name);
      setDescription(editingKb.description || "");
    } else {
      setName("");
      setDescription("");
      setDomain("general");
      setWatchDir("");
      setExtractionStrategy("llm");
      setEnableGraph(true);
      setEnableFulltext(true);
      setChunkSize(1000);
      setChunkOverlap(200);
    }
  }, [editingKb, open]);

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      if (isEdit) {
        await onSubmit({ name: name.trim(), description: description.trim() });
      } else {
        await onSubmit({
          name: name.trim(),
          description: description.trim(),
          workspace_id: workspaceId ?? undefined,
          settings: {
            domain,
            watch_dir: watchDir.trim(),
            extraction_strategy: extractionStrategy,
            enable_graph: enableGraph,
            enable_fulltext: enableFulltext,
            chunk_size: Number(chunkSize) || 1000,
            chunk_overlap: Number(chunkOverlap) || 200,
          },
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? t("knowledge.editKb") : t("knowledge.newKb")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 pt-2 max-h-[70vh] overflow-auto pr-1">
          <div>
            <Label className="text-xs">{t("knowledge.nameLabel")}</Label>
            <Input
              className="mt-1 h-8 text-xs"
              placeholder={t("knowledge.namePlaceholder")}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-xs">{t("knowledge.descLabel")}</Label>
            <Textarea
              className="mt-1 text-xs min-h-[50px]"
              placeholder={t("knowledge.descPlaceholder")}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {!isEdit && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">{t("knowledge.domainLabel")}</Label>
                  <Select value={domain} onValueChange={setDomain}>
                    <SelectTrigger className="mt-1 h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {DOMAIN_OPTIONS.map((d) => (
                        <SelectItem key={d.value} value={d.value} className="text-xs">
                          {t(d.label)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">{t("knowledge.extractionLabel")}</Label>
                  <Select value={extractionStrategy} onValueChange={setExtractionStrategy}>
                    <SelectTrigger className="mt-1 h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {EXTRACTION_STRATEGY_OPTIONS.map((s) => (
                        <SelectItem key={s.value} value={s.value} className="text-xs">
                          {t(s.label)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div>
                <Label className="text-xs">{t("knowledge.watchDirLabel")}</Label>
                <Input
                  className="mt-1 h-8 text-xs font-mono"
                  placeholder={t("knowledge.watchDirPlaceholder")}
                  value={watchDir}
                  onChange={(e) => setWatchDir(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">{t("knowledge.chunkSize")}</Label>
                  <Input
                    className="mt-1 h-8 text-xs"
                    type="number"
                    min={100}
                    max={10000}
                    value={chunkSize}
                    onChange={(e) => setChunkSize(Number(e.target.value))}
                  />
                </div>
                <div>
                  <Label className="text-xs">{t("knowledge.chunkOverlap")}</Label>
                  <Input
                    className="mt-1 h-8 text-xs"
                    type="number"
                    min={0}
                    max={1000}
                    value={chunkOverlap}
                    onChange={(e) => setChunkOverlap(Number(e.target.value))}
                  />
                </div>
              </div>

              <div className="flex items-center gap-6 pt-1">
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <Switch checked={enableGraph} onCheckedChange={setEnableGraph} />
                  <span>{t("knowledge.knowledgeGraph")}</span>
                </label>
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <Switch checked={enableFulltext} onCheckedChange={setEnableFulltext} />
                  <span>{t("knowledge.fulltextIndex")}</span>
                </label>
              </div>
              <p className="text-[10px] text-muted-foreground">{t("knowledge.embeddingNote")}</p>
            </>
          )}
        </div>
        <DialogFooter className="pt-2">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            {t("knowledge.cancel")}
          </Button>
          <Button size="sm" onClick={handleSubmit} disabled={submitting || !name.trim()}>
            {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />}
            {isEdit ? t("knowledge.save") : t("knowledge.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ════════════════════════════════════════════════════════════════════
// KB Settings Form (editable Settings tab)
// ════════════════════════════════════════════════════════════════════

function KBSettingsForm({
  kb,
  onSave,
  syncTask,
  onSync,
  onCancelSync,
  onScanDir,
}: {
  kb: KnowledgeBaseItem;
  onSave: (settings: KnowledgeBaseSettings) => Promise<void>;
  syncTask: SyncTaskStatus | null;
  onSync: (dirPath?: string, forceRebuild?: boolean) => void;
  onCancelSync: () => void;
  onScanDir: (
    dirPath?: string,
  ) => Promise<{ total: number; new_count: number; existing_count: number }>;
}) {
  const [s, setS] = useState<KnowledgeBaseSettings>(kb.settings);
  const [saving, setSaving] = useState(false);
  const [scanPreview, setScanPreview] = useState<{
    total: number;
    new_count: number;
    existing_count: number;
  } | null>(null);
  const [scanning, setScanning] = useState(false);
  const { t } = useTranslation("routesA");

  useEffect(() => {
    setS(kb.settings);
    setScanPreview(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kb.id, kb.updated_at]);

  const set = <K extends keyof KnowledgeBaseSettings>(key: K, value: KnowledgeBaseSettings[K]) =>
    setS((prev) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(s);
      toast.success(t("knowledge.settingsSaved"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("knowledge.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleScan = async () => {
    setScanning(true);
    try {
      const res = await onScanDir(s.watch_dir || undefined);
      setScanPreview({
        total: res.total,
        new_count: res.new_count,
        existing_count: res.existing_count,
      });
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("knowledge.scanFailed"));
    } finally {
      setScanning(false);
    }
  };

  const hasDocs = kb.stats.total_documents > 0;

  return (
    <div className="space-y-3">
      {/* ── 文档目录 ── */}
      <div className="rounded-lg border p-4 space-y-3">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          {t("knowledge.docDirectory")}
        </h4>

        <div>
          <Label className="text-xs">{t("knowledge.dirPath")}</Label>
          <Input
            className="mt-1 h-8 text-xs font-mono"
            placeholder={t("knowledge.notSet")}
            value={s.watch_dir}
            onChange={(e) => set("watch_dir", e.target.value)}
          />
          <p className="text-[10px] text-muted-foreground mt-1">{t("knowledge.dirPathHint")}</p>
        </div>

        <div className="flex items-center justify-between">
          <Label className="text-xs font-medium">{t("knowledge.autoSync")}</Label>
          <SettingSwitch
            label={t("knowledge.scanEvery60")}
            checked={s.watch_enabled}
            onChange={(v) => set("watch_enabled", v)}
          />
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={handleScan}
            disabled={scanning || !s.watch_dir}
          >
            {scanning ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Search className="w-3.5 h-3.5" />
            )}
            {t("knowledge.scan")}
          </Button>
          <Button
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={() => onSync()}
            disabled={!s.watch_dir}
          >
            <FolderSync className="w-3 h-3" />
            {t("knowledge.syncNew")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => onSync(undefined, true)}
            disabled={!s.watch_dir}
          >
            {t("knowledge.forceRebuild")}
          </Button>
          {syncTask?.status === "running" && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs text-destructive"
              onClick={onCancelSync}
            >
              {t("knowledge.cancel")}
            </Button>
          )}
        </div>
        <p className="text-[10px] text-muted-foreground">{t("knowledge.syncActionsHint")}</p>
        {scanPreview && (
          <p className="text-[10px] text-muted-foreground">
            {t("knowledge.scanPreview", {
              total: scanPreview.total,
              newCount: scanPreview.new_count,
              existingCount: scanPreview.existing_count,
            })}
          </p>
        )}
        {syncTask && (
          <div className="rounded-md bg-muted/50 p-2 space-y-1.5">
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className={cn(
                  "text-[10px]",
                  syncTask.status === "running" && "bg-blue-500/10 text-blue-600",
                  syncTask.status === "completed" &&
                    !syncTask.result?.errors?.length &&
                    "bg-green-500/10 text-green-600",
                  syncTask.status === "completed" &&
                    syncTask.result?.errors?.length &&
                    "bg-orange-500/10 text-orange-600",
                  syncTask.status === "failed" && "bg-red-500/10 text-red-600",
                )}
              >
                {syncTask.status === "pending"
                  ? t("knowledge.syncPending")
                  : syncTask.status === "running"
                    ? t("knowledge.syncRunning")
                    : syncTask.status === "completed"
                      ? syncTask.result?.errors?.length
                        ? t("knowledge.syncPartial")
                        : t("knowledge.syncCompleted")
                      : syncTask.status === "failed"
                        ? t("knowledge.syncFailed")
                        : syncTask.status}
              </Badge>
            </div>
            {syncTask.total_files > 0 && (
              <div>
                <div className="flex justify-between text-[10px] text-muted-foreground mb-0.5">
                  <span>
                    {syncTask.processed_files} / {syncTask.total_files}
                  </span>
                  <span>{Math.round(syncTask.progress)}%</span>
                </div>
                <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-brand transition-all rounded-full"
                    style={{ width: `${syncTask.progress}%` }}
                  />
                </div>
              </div>
            )}
            {syncTask.current_file && (
              <p className="text-[10px] text-muted-foreground truncate">
                {t("knowledge.currentFile", { file: syncTask.current_file })}
              </p>
            )}
            {syncTask.error && <p className="text-[10px] text-destructive">{syncTask.error}</p>}
            {syncTask.result?.errors && syncTask.result.errors.length > 0 && (
              <div className="space-y-0.5">
                {syncTask.result.errors.map((err, idx) => (
                  <p key={idx} className="text-[10px] text-destructive/80 break-all">
                    {err}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── 检索设置 ── */}
      <div className="rounded-lg border p-4 space-y-3">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          {t("knowledge.retrievalSettings")}
        </h4>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-xs">{t("knowledge.defaultTopK")}</Label>
            <Input
              className="mt-1 h-8 text-xs"
              type="number"
              min={1}
              max={50}
              value={s.default_top_k}
              onChange={(e) => set("default_top_k", Number(e.target.value))}
            />
          </div>
          <div>
            <Label className="text-xs">{t("knowledge.defaultMode")}</Label>
            <Select value={s.default_mode} onValueChange={(v) => set("default_mode", v)}>
              <SelectTrigger className="mt-1 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RETRIEVAL_MODE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value} className="text-xs">
                    {t(o.label)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* ── 全文检索 ── */}
      <div className="rounded-lg border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            {t("knowledge.fulltextSearch")}
          </h4>
          <SettingSwitch
            label={t("knowledge.enable")}
            checked={s.enable_fulltext}
            onChange={(v) => set("enable_fulltext", v)}
          />
        </div>
        <div>
          <Label className="text-xs">{t("knowledge.fulltextWeight")}</Label>
          <Input
            className="mt-1 h-8 text-xs"
            type="number"
            min={0}
            max={1}
            step={0.1}
            value={s.fulltext_weight}
            onChange={(e) => set("fulltext_weight", Number(e.target.value))}
          />
        </div>
      </div>

      {/* ── 向量检索 ── */}
      <div className="rounded-lg border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            {t("knowledge.vectorSearch")}
          </h4>
          <SettingSwitch
            label={t("knowledge.enable")}
            checked={s.enable_vector}
            onChange={(v) => set("enable_vector", v)}
          />
        </div>

        {s.enable_vector && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">{t("knowledge.chunkSize")}</Label>
                <Input
                  className="mt-1 h-8 text-xs"
                  type="number"
                  min={100}
                  max={10000}
                  value={s.chunk_size}
                  onChange={(e) => set("chunk_size", Number(e.target.value))}
                />
              </div>
              <div>
                <Label className="text-xs">{t("knowledge.chunkOverlap")}</Label>
                <Input
                  className="mt-1 h-8 text-xs"
                  type="number"
                  min={0}
                  max={1000}
                  value={s.chunk_overlap}
                  onChange={(e) => set("chunk_overlap", Number(e.target.value))}
                />
              </div>
            </div>

            <div>
              <Label className="text-xs">{t("knowledge.vectorWeight")}</Label>
              <Input
                className="mt-1 h-8 text-xs"
                type="number"
                min={0}
                max={1}
                step={0.1}
                value={s.vector_weight}
                onChange={(e) => set("vector_weight", Number(e.target.value))}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">{t("knowledge.embeddingModel")}</Label>
                <Input
                  className="mt-1 h-8 text-xs font-mono"
                  value={s.embedding_model}
                  onChange={(e) => set("embedding_model", e.target.value)}
                />
              </div>
              <div>
                <Label className="text-xs">{t("knowledge.dimension")}</Label>
                <Input
                  className="mt-1 h-8 text-xs"
                  type="number"
                  value={s.embedding_dimension}
                  onChange={(e) => set("embedding_dimension", Number(e.target.value))}
                />
              </div>
            </div>
            <div className="border-t pt-3 space-y-1">
              <SettingsRow label={t("knowledge.chunkStrategy")} value={s.chunk_strategy} />
            </div>
            {hasDocs && (
              <p className="text-[10px] text-yellow-600">{t("knowledge.embeddingChangeWarning")}</p>
            )}
          </>
        )}
        {!s.enable_vector && (
          <p className="text-[10px] text-muted-foreground">{t("knowledge.vectorDisabledHint")}</p>
        )}
      </div>

      {/* ── 知识图谱 ── */}
      <div className="rounded-lg border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            {t("knowledge.knowledgeGraph")}
          </h4>
          <SettingSwitch
            label={t("knowledge.enable")}
            checked={s.enable_graph}
            onChange={(v) => set("enable_graph", v)}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-xs">{t("knowledge.domainLabel")}</Label>
            <Select value={s.domain || "general"} onValueChange={(v) => set("domain", v)}>
              <SelectTrigger className="mt-1 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DOMAIN_OPTIONS.map((d) => (
                  <SelectItem key={d.value} value={d.value} className="text-xs">
                    {t(d.label)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">{t("knowledge.extractionLabel")}</Label>
            <Select
              value={s.extraction_strategy}
              onValueChange={(v) => set("extraction_strategy", v)}
            >
              <SelectTrigger className="mt-1 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXTRACTION_STRATEGY_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value} className="text-xs">
                    {t(o.label)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div>
          <Label className="text-xs">{t("knowledge.graphWeight")}</Label>
          <Input
            className="mt-1 h-8 text-xs"
            type="number"
            min={0}
            max={1}
            step={0.1}
            value={s.graph_weight}
            onChange={(e) => set("graph_weight", Number(e.target.value))}
          />
        </div>

        {s.extraction_llm_config && (
          <div className="border-t pt-3 space-y-1">
            <SettingsRow
              label={t("knowledge.extractionLlmConfig")}
              value={s.extraction_llm_config}
            />
          </div>
        )}
      </div>

      <div className="flex justify-end">
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {saving && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />}
          {t("knowledge.saveSettings")}
        </Button>
      </div>
    </div>
  );
}

function SettingSwitch({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-xs cursor-pointer">
      <Switch checked={checked} onCheckedChange={onChange} />
      <span>{label}</span>
    </label>
  );
}
