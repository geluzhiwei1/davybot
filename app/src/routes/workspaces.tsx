import { dateLocale } from "@/lib/date-locale";
import { createFileRoute, Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useState, useEffect, useCallback, useMemo } from "react";
import { useStore, type WorkspaceCollection } from "@/lib/store";
import { toExperts } from "@/lib/experts";
import { useMarketTeamsStore } from "@/lib/market-teams-store";
import { IS_DESKTOP } from "@/lib/platform";
import { marketApi, type MarketResource } from "@/lib/api-client";
import { useQuickChat } from "@/hooks/use-quick-chat";
import { SwipeActionRow } from "@/components/mobile-shell/swipe-action-row";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import {
  FolderOpen,
  FolderPlus,
  Layers,
  LayersIcon,
  MoreHorizontal,
  Pencil,
  Trash2,
  ArrowRight,
  ArrowLeft,
  ChevronRight,
  Loader2,
  Settings,
  Settings2,
  Search,
  X,
  Bot,
  BookOpen,
  Wrench,
  Sparkles,
  Users,
  Filter,
  ListTodo,
  MessageSquarePlus,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import i18n from "@/lib/i18n";

export const Route = createFileRoute("/workspaces")({
  head: () => ({
    meta: [{ title: i18n.t("routesB:workspaces.metaTitle") }],
  }),
  component: WorkspacesPage,
  validateSearch: (search: Record<string, unknown>) => ({
    mode: (search.mode as string) || undefined,
  }),
});

// ── Dialog states ────────────────────────────────────────────
type RenameState =
  | { open: true; id: string; name: string; kind: "workspace" | "collection" }
  | { open: false };
type DeleteState =
  | { open: true; id: string; name: string; kind: "workspace" | "collection"; count: number }
  | { open: false };
type CreateCollState = { open: true } | { open: false };
type EditCollWsState =
  | { open: true; collectionId: string; collectionName: string }
  | { open: false };

// ── Resource type filter definitions ─────────────────────────
const TYPE_TEAM_TYPES = {
  all: null,
  compliance: "compliance",
  ip: "intellectual-property",
  lfm: "law-firm-management",
} as const;
const TYPE_FILTER_KEYS = {
  all: "workspaces.typeFilter.all",
  compliance: "workspaces.typeFilter.compliance",
  ip: "workspaces.typeFilter.ip",
  lfm: "workspaces.typeFilter.lfm",
} as const;
type TypeFilterKey = "all" | "compliance" | "ip" | "lfm";

/** Map knowledge tags to team_type for filtering */
function getKnowledgeType(kb: MarketResource): string {
  const tags = kb.tags ?? [];
  const sanctions = new Set(["sanctions", "US", "OFAC", "EU", "UN", "UK"]);
  const exportCtrl = new Set(["export-control", "EAR", "ECCN", "ITAR"]);
  const data = new Set(["data-compliance", "PIPL", "GDPR"]);
  const overseas = new Set(["overseas-investment", "CFIUS", "ODI"]);
  const labor = new Set(["labor-employment"]);
  const antitrustSet = new Set(["antitrust"]);
  const quality = new Set(["product-quality", "safety"]);
  const bribery = new Set(["anti-bribery", "FCPA"]);
  const tax = new Set(["tax", "treaty", "CRS", "OECD"]);
  const supply = new Set(["supply-chain", "UFLPA", "forced-labor", "ILO"]);
  const ipSet = new Set(["intellectual-property", "patent", "trademark", "guidelines"]);
  const esgSet = new Set(["esg", "sustainability", "reporting"]);
  for (const t of tags) {
    if (
      sanctions.has(t) ||
      exportCtrl.has(t) ||
      data.has(t) ||
      overseas.has(t) ||
      labor.has(t) ||
      antitrustSet.has(t) ||
      quality.has(t) ||
      bribery.has(t) ||
      tax.has(t) ||
      supply.has(t)
    )
      return "compliance";
    if (ipSet.has(t)) return "intellectual-property";
    if (esgSet.has(t)) return "compliance"; // esg teams have type=compliance
  }
  return "";
}

/** Map MCP server ID to team_type */
function getMcpType(mcp: MarketResource): string {
  const id = mcp.id;
  if (id === "mcp/sanctions-knowledge" || id === "mcp/paper-search-mcp") return "compliance";
  if (id === "mcp/nn-kb-searcher") return "law-firm-management";
  return "";
}

// ── Resource picker section component ───────────────────────
function ResourceSection({
  title,
  icon: Icon,
  items,
  selectedIds,
  onToggle,
  loading,
  renderLabel,
  renderSub,
  getSearchText,
  filterType,
  resourceTypeMap,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  items: Array<{ id: string }>;
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  loading?: boolean;
  renderLabel: (item: { id: string }) => string;
  renderSub?: (item: { id: string }) => string | undefined;
  getSearchText?: (item: { id: string }) => string;
  filterType?: string | null;
  resourceTypeMap?: Map<string, string>;
}) {
  const { t: tr } = useTranslation("routesB");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchText, setSearchText] = useState("");
  const MIN_FOR_SEARCH = 6;

  const filtered = useMemo(() => {
    let result = items;
    // Type filter
    if (filterType && resourceTypeMap) {
      result = result.filter((item) => resourceTypeMap.get(item.id) === filterType);
    }
    // Text search
    if (searchText.trim()) {
      const q = searchText.trim().toLowerCase();
      result = result.filter((item) => {
        const label = renderLabel(item).toLowerCase();
        if (label.includes(q)) return true;
        if (getSearchText) {
          const extra = getSearchText(item).toLowerCase();
          if (extra.includes(q)) return true;
        }
        return false;
      });
    }
    return result;
  }, [items, searchText, filterType, resourceTypeMap, renderLabel, getSearchText]);

  const showSearchToggle = items.length >= MIN_FOR_SEARCH;
  const showCount = (filterType || searchText.trim()) && filtered.length !== items.length;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 text-muted-foreground" />
        <span className="text-sm font-medium">{title}</span>
        {loading && <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />}
        {showSearchToggle && !searchOpen && (
          <button
            onClick={() => setSearchOpen(true)}
            className="ml-1 p-0.5 rounded hover:bg-accent/50 transition text-muted-foreground"
            title={tr("workspaces.searchFilter")}
          >
            <Search className="w-3 h-3" />
          </button>
        )}
        <Badge variant="secondary" className="text-[10px] ml-auto">
          {showCount
            ? tr("workspaces.showingCount", { shown: filtered.length, total: items.length })
            : items.length > 0
              ? tr("workspaces.selectedCount", { selected: selectedIds.size, total: items.length })
              : tr("workspaces.noneAvailable")}
        </Badge>
      </div>

      {/* Search input */}
      {searchOpen && (
        <div className="flex items-center gap-1.5 pl-0">
          <div className="flex-1 relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
            <input
              type="text"
              placeholder={tr("workspaces.filterByName")}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              autoFocus
              className="w-full h-7 pl-7 pr-2 text-xs rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-brand/30"
            />
          </div>
          <button
            onClick={() => {
              setSearchOpen(false);
              setSearchText("");
            }}
            className="p-0.5 rounded hover:bg-accent/50 transition text-muted-foreground shrink-0"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {filtered.length === 0 && !loading ? (
        <p className="text-xs text-muted-foreground pl-6 py-1">
          {searchText.trim()
            ? tr("workspaces.noMatchFor", { query: searchText.trim(), title })
            : tr("workspaces.noneAvailableHint", { title })}
        </p>
      ) : (
        <div className="pl-6 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          {filtered.map((item) => {
            const checked = selectedIds.has(item.id);
            return (
              <label
                key={item.id}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg cursor-pointer transition text-sm
                  ${checked ? "bg-brand/10 border border-brand/30" : "hover:bg-accent/50 border border-transparent"}`}
              >
                <Checkbox checked={checked} onCheckedChange={() => onToggle(item.id)} />
                <div className="min-w-0 flex-1">
                  <span className="truncate block">{renderLabel(item)}</span>
                  {renderSub?.(item) && (
                    <span className="text-[11px] text-muted-foreground truncate block">
                      {renderSub(item)}
                    </span>
                  )}
                </div>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

function WorkspacesPage() {
  const { t } = useTranslation("routesB");
  const navigate = useNavigate();
  const {
    workspaces,
    collections,
    tasks,
    createWorkspace,
    renameWorkspace,
    deleteWorkspace,
    createCollection,
    updateCollection,
    deleteCollection,
    addWorkspacesToCollection,
    removeWorkspacesFromCollection,
    getOrCreateEmptyTask,
    setActiveDrawer,
    setFilesDrawerFor,
  } = useStore();

  // Page mode: "list" or "create" (reads ?mode=create from URL)
  const search = useSearch({ strict: false }) as { mode?: string };
  const [mode, setMode] = useState<"list" | "create">(search.mode === "create" ? "create" : "list");
  const [view, setView] = useState<"workspaces" | "tasks">("workspaces");
  const { startChat: handleQuickNewTask, creating } = useQuickChat();

  // Market teams → allExperts (for agent selector in create form)
  const marketTeamsStore = useMarketTeamsStore((s) => s.teams);
  const fetchTeams = useMarketTeamsStore((s) => s.fetchTeams);
  const allExperts = useMemo(() => toExperts(marketTeamsStore), [marketTeamsStore]);
  useEffect(() => {
    fetchTeams();
  }, [fetchTeams]);

  // Create form state
  const [newWsPath, setNewWsPath] = useState("");
  const [newWsDisplayName, setNewWsDisplayName] = useState("");
  const [newWsDescription, setNewWsDescription] = useState("");
  const [createWsLoading, setCreateWsLoading] = useState(false);
  const [createWsError, setCreateWsError] = useState<string | null>(null);

  // Resource selection state
  const [_selectedModels, setSelectedModels] = useState<Set<string>>(new Set());
  const [selectedExperts, setSelectedExperts] = useState<Set<string>>(new Set());
  const [selectedKnowledgeBases, setSelectedKnowledgeBases] = useState<Set<string>>(new Set());
  const [selectedMcpServers, setSelectedMcpServers] = useState<Set<string>>(new Set());
  const [selectedSkills, setSelectedSkills] = useState<Set<string>>(new Set());

  // Fetched resource data (from support system market API)
  const [marketSkills, setMarketSkills] = useState<MarketResource[]>([]);
  const [marketAgents, setMarketAgents] = useState<MarketResource[]>([]);
  const [marketMcpServers, setMarketMcpServers] = useState<MarketResource[]>([]);
  const [marketKnowledge, setMarketKnowledge] = useState<MarketResource[]>([]);
  const [marketTeams, setMarketTeams] = useState<MarketResource[]>([]);
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);
  const [resourcesLoading, setResourcesLoading] = useState(false);
  const [selectedType, setSelectedType] = useState<TypeFilterKey>("all");

  // Build resource type mapping from teams data
  const resourceTypeMap = useMemo(() => {
    const map = new Map<string, string>();
    // Teams: from extra_metadata.team_type
    for (const t of marketTeams) {
      const tt = (t.extra_metadata?.team_type as string) ?? "";
      if (tt) map.set(t.id, tt);
    }
    // Build agent directory name → team_type from teams' extra_metadata.agents
    // Team stores "agent/<dirname>" (e.g. "agent/patent-team")
    // Agent scanner sets tags[0] = directory name (e.g. "patent-team")
    const dirType = new Map<string, string>();
    for (const t of marketTeams) {
      const tt = (t.extra_metadata?.team_type as string) ?? "";
      const agents = (t.extra_metadata?.agents as string[] | null) ?? [];
      if (tt) {
        for (const ref of agents) {
          const dirName = ref.replace(/^agent\//, "");
          if (dirName && !dirType.has(dirName)) dirType.set(dirName, tt);
        }
      }
    }
    // Agents (market): match tags[0] (directory name) to type
    for (const a of marketAgents) {
      const dirName = a.tags?.[0];
      if (dirName) {
        const tt = dirType.get(dirName);
        if (tt) map.set(a.id, tt);
      }
    }
    // Agents (experts): from Expert.category
    for (const e of allExperts) {
      if (e.category) map.set(e.id, e.category);
    }
    // Knowledge: from tags
    for (const k of marketKnowledge) {
      const tt = getKnowledgeType(k);
      if (tt) map.set(k.id, tt);
    }
    // MCP: by ID
    for (const m of marketMcpServers) {
      const tt = getMcpType(m);
      if (tt) map.set(m.id, tt);
    }
    return map;
  }, [marketTeams, marketAgents, marketKnowledge, marketMcpServers, allExperts]);

  // Per-type resource counts for filter bar
  const typeCounts = useMemo(() => {
    const counts: Record<TypeFilterKey, number> = { all: 0, compliance: 0, ip: 0, lfm: 0 };
    // Teams
    for (const t of marketTeams) {
      counts.all++;
      const tt = (t.extra_metadata?.team_type as string) ?? "";
      if (tt === "compliance") counts.compliance++;
      else if (tt === "intellectual-property") counts.ip++;
      else if (tt === "law-firm-management") counts.lfm++;
    }
    // Agents
    for (const a of marketAgents) {
      counts.all++;
      const tt = resourceTypeMap.get(a.id);
      if (tt) counts[typeKey(tt)]++;
    }
    for (const e of allExperts) {
      counts.all++;
      const tt = e.category;
      if (tt) counts[typeKey(tt)]++;
    }
    // Knowledge
    for (const k of marketKnowledge) {
      counts.all++;
      const tt = resourceTypeMap.get(k.id);
      if (tt) counts[typeKey(tt)]++;
    }
    // MCP
    for (const _ of marketMcpServers) {
      counts.all++;
      // MCPs are small enough, always show
    }
    return counts;
  }, [marketTeams, marketAgents, marketKnowledge, marketMcpServers, allExperts, resourceTypeMap]);

  function typeKey(tt: string): TypeFilterKey {
    if (tt === "compliance") return "compliance";
    if (tt === "intellectual-property") return "ip";
    if (tt === "law-firm-management") return "lfm";
    return "all";
  }

  const filterType = TYPE_TEAM_TYPES[selectedType];

  const filteredTeams = useMemo(() => {
    if (!filterType) return marketTeams;
    return marketTeams.filter((t) => (t.extra_metadata?.team_type as string) === filterType);
  }, [marketTeams, filterType]);

  // Fetch available resources when entering create mode
  const fetchResources = useCallback(async () => {
    setResourcesLoading(true);
    const results = await Promise.allSettled([
      marketApi.listResources({ type: "team", page_size: 100 }),
      marketApi.listResources({ type: "skill", page_size: 100 }),
      marketApi.listResources({ type: "agent", page_size: 100 }),
      marketApi.listResources({ type: "mcp", page_size: 100 }),
      marketApi.listResources({ type: "knowledge", page_size: 100 }),
    ]);
    if (results[0].status === "fulfilled") {
      setMarketTeams(results[0].value.items ?? []);
    }
    if (results[1].status === "fulfilled") {
      setMarketSkills(results[1].value.items ?? []);
    }
    if (results[2].status === "fulfilled") {
      setMarketAgents(results[2].value.items ?? []);
    }
    if (results[3].status === "fulfilled") {
      setMarketMcpServers(results[3].value.items ?? []);
    }
    if (results[4].status === "fulfilled") {
      setMarketKnowledge(results[4].value.items ?? []);
    }
    setResourcesLoading(false);
  }, []);

  useEffect(() => {
    if (mode === "create") {
      fetchResources();
    }
  }, [mode, fetchResources]);

  const toggleSet = (setter: React.Dispatch<React.SetStateAction<Set<string>>>) => (id: string) => {
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const [renameTarget, setRenameTarget] = useState<RenameState>({ open: false });
  const [renameValue, setRenameValue] = useState("");

  const [deleteTarget, setDeleteTarget] = useState<DeleteState>({ open: false });

  const [createColl, setCreateColl] = useState<CreateCollState>({ open: false });
  const [newCollName, setNewCollName] = useState("");
  const [newCollDesc, setNewCollDesc] = useState("");

  const [editCollWs, setEditCollWs] = useState<EditCollWsState>({ open: false });
  const [selectedWsIds, setSelectedWsIds] = useState<Set<string>>(new Set());

  const [expandedCollections, setExpandedCollections] = useState<Set<string>>(new Set());

  // ── Handlers ───────────────────────────────────────────────

  const handleCreateWorkspace = async () => {
    const path = newWsPath.trim();
    if (!path) return;
    setCreateWsLoading(true);
    setCreateWsError(null);
    try {
      // Build resource lists from current selections
      const teamMeta = selectedTeam
        ? (marketTeams.find((t) => t.id === selectedTeam)?.extra_metadata ?? null)
        : null;

      const ws = await createWorkspace({
        path,
        displayName: newWsDisplayName.trim() || undefined,
        description: newWsDescription.trim() || undefined,
        teamId: selectedTeam || undefined,
        teamMeta: teamMeta as Record<string, unknown> | null | undefined,
        skillIds: selectedSkills.size > 0 ? [...selectedSkills] : undefined,
        agentIds: selectedExperts.size > 0 ? [...selectedExperts] : undefined,
        mcpIds: selectedMcpServers.size > 0 ? [...selectedMcpServers] : undefined,
        knowledgeIds: selectedKnowledgeBases.size > 0 ? [...selectedKnowledgeBases] : undefined,
      });
      toast.success(t("workspaces.created", { name: ws.name }));
      const task = await getOrCreateEmptyTask({ workspaceId: ws.id });
      navigate({
        to: "/workspace/$workspaceId/task/$taskId",
        params: { workspaceId: ws.id, taskId: task.id },
      });
    } catch (e) {
      setCreateWsError(e instanceof Error ? e.message : t("workspaces.createFailed"));
    } finally {
      setCreateWsLoading(false);
    }
  };

  const resetCreateForm = () => {
    setNewWsPath("");
    setNewWsDisplayName("");
    setNewWsDescription("");
    setCreateWsError(null);
    setCreateWsLoading(false);
    setSelectedModels(new Set());
    setSelectedExperts(new Set());
    setSelectedKnowledgeBases(new Set());
    setSelectedMcpServers(new Set());
    setSelectedSkills(new Set());
    setSelectedTeam(null);
    setSelectedType("all");
  };

  // Auto-configure resources when a team is selected.
  //
  // Strategy: selected* Sets hold BOTH formats:
  //   1. YAML refs (backend format, e.g. "agent/patent-team") — sent to backend
  //   2. Display IDs  (shown in ResourceSection, e.g. "davybot.com/patent-team/patent-engineer")
  //
  // - ResourceSection checks `selectedIds.has(item.id)` — matches display IDs.
  // - Manual checkbox toggles via toggleSet() add/remove display IDs.
  // - handleCreateWorkspace sends the Set as-is; backend ignores display IDs when teamId is set.
  // - Knowledge and MCP: YAML ref === display ID, no mapping needed.
  const handleTeamSelect = useCallback(
    (teamId: string | null) => {
      setSelectedTeam(teamId);
      if (!teamId) {
        setSelectedExperts(new Set());
        setSelectedSkills(new Set());
        setSelectedKnowledgeBases(new Set());
        setSelectedMcpServers(new Set());
        return;
      }

      const team = marketTeams.find((t) => t.id === teamId);
      if (!team?.extra_metadata) return;

      const meta = team.extra_metadata;
      const yamlAgents = (meta.agents as string[]) ?? [];
      const yamlSkills = (meta.skills as string[]) ?? [];
      const yamlKnowledges = (meta.knowledges as string[]) ?? [];
      const yamlMcps = (meta.mcps as string[]) ?? [];

      // ── Agents: YAML refs + matching display IDs (by tags[0]) ──
      const selectedAgents = new Set(yamlAgents);
      for (const ref of yamlAgents) {
        const dir = ref.replace(/^agent\//, "");
        for (const a of marketAgents) {
          if (a.tags?.[0] === dir) selectedAgents.add(a.id);
        }
      }

      // Skills: match by endsWith — YAML refs like "skill/docx" → display IDs like "normnomos.com/docx"
      const selectedSkillsCombined = new Set(yamlSkills);
      for (const ref of yamlSkills) {
        const refSuffix = ref.replace(/^skill\//, "");
        for (const s of marketSkills) {
          if (s.id.endsWith(`/${refSuffix}`)) {
            selectedSkillsCombined.add(s.id);
          }
        }
      }

      // ── Knowledge / MCP: YAML ref === display ID, no mapping needed ──
      setSelectedExperts(selectedAgents);
      setSelectedSkills(selectedSkillsCombined);
      setSelectedKnowledgeBases(new Set(yamlKnowledges));
      setSelectedMcpServers(new Set(yamlMcps));
    },
    [marketTeams, marketAgents, marketSkills],
  );

  const handleRename = () => {
    if (!renameTarget.open || !renameValue.trim()) return;
    if (renameTarget.kind === "workspace") {
      renameWorkspace(renameTarget.id, renameValue.trim());
    } else {
      updateCollection(renameTarget.id, { name: renameValue.trim() }).catch(() =>
        toast.error(t("workspaces.renameFailed")),
      );
    }
    toast.success(t("workspaces.renamed"));
    setRenameTarget({ open: false });
  };

  const handleDelete = () => {
    if (!deleteTarget.open) return;
    if (deleteTarget.kind === "workspace") {
      deleteWorkspace(deleteTarget.id);
    } else {
      deleteCollection(deleteTarget.id).catch(() => toast.error(t("workspaces.deleteFailed")));
    }
    toast.success(t("workspaces.deleted", { name: deleteTarget.name }));
    setDeleteTarget({ open: false });
  };

  const handleCreateCollection = async () => {
    const name = newCollName.trim();
    if (!name) return;
    try {
      await createCollection(name, newCollDesc.trim());
      toast.success(t("workspaces.collectionCreated", { name }));
      setNewCollName("");
      setNewCollDesc("");
      setCreateColl({ open: false });
    } catch {
      toast.error(t("workspaces.createCollectionFailed"));
    }
  };

  const openEditCollWs = (coll: WorkspaceCollection) => {
    setSelectedWsIds(new Set(coll.workspaceIds));
    setEditCollWs({ open: true, collectionId: coll.id, collectionName: coll.name });
  };

  const handleSaveCollWs = async () => {
    if (!editCollWs.open) return;
    const collId = editCollWs.collectionId;
    const coll = collections.find((c) => c.id === collId);
    if (!coll) return;

    const oldIds = new Set(coll.workspaceIds);
    const toAdd = [...selectedWsIds].filter((id) => !oldIds.has(id));
    const toRemove = [...oldIds].filter((id) => !selectedWsIds.has(id));

    try {
      if (toAdd.length > 0) await addWorkspacesToCollection(collId, toAdd);
      if (toRemove.length > 0) await removeWorkspacesFromCollection(collId, toRemove);
      if (toAdd.length > 0 || toRemove.length > 0) {
        toast.success(t("workspaces.workspacesUpdated"));
      }
    } catch {
      toast.error(t("workspaces.updateFailed"));
    }
    setEditCollWs({ open: false });
  };

  const toggleExpanded = (id: string) => {
    setExpandedCollections((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const openWorkspace = async (wsId: string) => {
    // Navigate directly to the most recent task, or create a new one
    const wsTasks = tasks.filter((t) => t.workspaceId === wsId);
    if (wsTasks.length > 0) {
      navigate({
        to: "/workspace/$workspaceId/task/$taskId",
        params: { workspaceId: wsId, taskId: wsTasks[0].id },
      });
    } else {
      const t = await getOrCreateEmptyTask({ workspaceId: wsId });
      navigate({
        to: "/workspace/$workspaceId/task/$taskId",
        params: { workspaceId: wsId, taskId: t.id },
      });
    }
  };

  // ── Render helpers ─────────────────────────────────────────

  const renderWorkspaceRow = (
    ws: { id: string; name: string; createdAt: number; lifecycle?: string },
    showCollectionBadge = false,
    collName?: string,
  ) => {
    const wsTasks = tasks.filter((t) => t.workspaceId === ws.id);
    return (
      <SwipeActionRow
        key={ws.id}
        actions={[
          {
            key: "rename",
            label: t("workspaces.rename"),
            icon: Pencil,
            onClick: () => {
              setRenameValue(ws.name);
              setRenameTarget({ open: true, id: ws.id, name: ws.name, kind: "workspace" });
            },
          },
          {
            key: "delete",
            label: t("workspaces.delete"),
            icon: Trash2,
            destructive: true,
            onClick: () =>
              setDeleteTarget({
                open: true,
                id: ws.id,
                name: ws.name,
                kind: "workspace",
                count: wsTasks.length,
              }),
          },
        ]}
      >
        <div className="group bg-gradient-card border border-border rounded-xl p-3.5 flex items-center gap-3 hover:border-brand/40 transition">
          <div className="w-9 h-9 rounded-lg bg-brand/10 border border-brand/30 flex items-center justify-center shrink-0">
            <FolderOpen className="w-4 h-4 text-brand" />
          </div>
          {/* 移动端整卡可点 = 打开;桌面按钮齐全,此中段点击为附加上手路径 */}
          <div className="flex-1 min-w-0 cursor-pointer" onClick={() => openWorkspace(ws.id)}>
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm truncate">{ws.name}</span>
              {ws.lifecycle === "temporary" && (
                <Badge
                  variant="outline"
                  className="text-[10px] text-amber-600 border-amber-500/40 bg-amber-500/10"
                >
                  {t("workspaces.temporary")}
                </Badge>
              )}
              <Badge variant="secondary" className="text-[10px]">
                {t("workspaces.taskCount", { count: wsTasks.length })}
              </Badge>
              {showCollectionBadge && collName && (
                <Badge
                  variant="outline"
                  className="text-[10px] text-muted-foreground hidden sm:inline-flex"
                >
                  {collName}
                </Badge>
              )}
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5">
              {t("workspaces.createdAt", {
                date: new Date(ws.createdAt).toLocaleDateString(dateLocale()),
              })}
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 hidden sm:inline-flex"
              title={t("workspaces.workspaceSettings")}
              onClick={() => {
                setFilesDrawerFor(ws.id);
                setActiveDrawer("workspace-settings");
              }}
            >
              <Settings className="w-3.5 h-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="gap-1 text-xs h-7 hidden sm:inline-flex"
              onClick={() => openWorkspace(ws.id)}
            >
              {t("workspaces.open")} <ArrowRight className="w-3 h-3" />
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 opacity-0 group-hover:opacity-100 max-md:opacity-100 transition"
                >
                  <MoreHorizontal className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {/* 移动端专属项:设置/打开(桌面有独立按钮,<sm 时菜单是唯一入口) */}
                <DropdownMenuItem className="sm:hidden" onClick={() => openWorkspace(ws.id)}>
                  <ArrowRight className="w-3.5 h-3.5 mr-2" /> {t("workspaces.open")}
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="sm:hidden"
                  onClick={() => {
                    setFilesDrawerFor(ws.id);
                    setActiveDrawer("workspace-settings");
                  }}
                >
                  <Settings className="w-3.5 h-3.5 mr-2" /> {t("workspaces.workspaceSettings")}
                </DropdownMenuItem>
                <DropdownMenuSeparator className="sm:hidden" />
                <DropdownMenuItem
                  onClick={() => {
                    setRenameValue(ws.name);
                    setRenameTarget({ open: true, id: ws.id, name: ws.name, kind: "workspace" });
                  }}
                >
                  <Pencil className="w-3.5 h-3.5 mr-2" /> {t("workspaces.rename")}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onClick={() =>
                    setDeleteTarget({
                      open: true,
                      id: ws.id,
                      name: ws.name,
                      kind: "workspace",
                      count: wsTasks.length,
                    })
                  }
                >
                  <Trash2 className="w-3.5 h-3.5 mr-2" /> {t("workspaces.delete")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </SwipeActionRow>
    );
  };

  // ── Create Workspace Page ──────────────────────────────────
  if (mode === "create") {
    return (
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="px-4 py-6 sm:px-6 sm:py-8">
          {/* Top bar with back button */}
          <div className="flex flex-wrap items-center gap-2 justify-between mb-6 sm:mb-8">
            <button
              onClick={() => {
                resetCreateForm();
                setMode("list");
              }}
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition"
            >
              <ArrowLeft className="w-4 h-4" />
              {t("workspaces.backToList")}
            </button>
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  resetCreateForm();
                  setMode("list");
                }}
                disabled={createWsLoading}
              >
                {t("workspaces.cancel")}
              </Button>
              <Button
                className="bg-gradient-brand text-brand-foreground gap-2"
                onClick={handleCreateWorkspace}
                disabled={!newWsPath.trim() || createWsLoading}
              >
                {createWsLoading && <Loader2 className="w-4 h-4 animate-spin" />}
                {createWsLoading ? t("workspaces.creating") : t("workspaces.createWorkspace")}
              </Button>
            </div>
          </div>

          {/* Page title */}
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-xl bg-gradient-brand flex items-center justify-center shadow-brand">
              <FolderPlus className="w-5 h-5 text-brand-foreground" />
            </div>
            <div>
              <h1 className="text-xl font-bold">{t("workspaces.newWorkspaceTitle")}</h1>
              <p className="text-sm text-muted-foreground">{t("workspaces.newWorkspaceDesc")}</p>
            </div>
          </div>

          {/* Error */}
          {createWsError && (
            <div className="bg-destructive/10 border border-destructive/30 rounded-lg px-4 py-3 text-sm text-destructive mb-6">
              {createWsError}
            </div>
          )}

          {/* ── Basic info ── */}
          <div className="space-y-5 max-w-3xl mb-10">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
              <FolderOpen className="w-3.5 h-3.5" /> {t("workspaces.basicInfo")}
            </h2>
            {/* Path */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1">
                {t("workspaces.directoryPath")}
                <span className="text-destructive text-xs">*</span>
              </label>
              <div className="flex gap-2">
                <Input
                  placeholder={t("workspaces.pathPlaceholder")}
                  value={newWsPath}
                  onChange={(e) => setNewWsPath(e.target.value)}
                  className="text-sm flex-1"
                  autoFocus
                />
                {IS_DESKTOP && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="shrink-0"
                    onClick={async () => {
                      try {
                        const { open } = await import("@tauri-apps/plugin-dialog");
                        const selected = await open({
                          directory: true,
                          multiple: false,
                          title: t("workspaces.selectDirectory"),
                        });
                        if (selected) {
                          setNewWsPath(
                            typeof selected === "string"
                              ? selected
                              : (selected as string[]).join(""),
                          );
                        }
                      } catch {
                        // user cancelled or dialog unavailable
                      }
                    }}
                  >
                    {t("workspaces.select")}
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">{t("workspaces.pathHint")}</p>
            </div>
            {/* Display name */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t("workspaces.displayName")}</label>
              <Input
                placeholder={t("workspaces.displayNamePlaceholder")}
                value={newWsDisplayName}
                onChange={(e) => setNewWsDisplayName(e.target.value)}
                className="text-sm"
              />
              <p className="text-xs text-muted-foreground">{t("workspaces.displayNameHint")}</p>
            </div>
            {/* Description */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t("workspaces.description")}</label>
              <Textarea
                placeholder={t("workspaces.descriptionPlaceholder")}
                value={newWsDescription}
                onChange={(e) => setNewWsDescription(e.target.value)}
                rows={3}
                className="text-sm resize-none"
              />
            </div>
          </div>

          <Separator className="mb-10 max-w-3xl" />

          {/* ── Resource selection ── */}
          <div className="space-y-8 max-w-3xl">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
              <Settings2 className="w-3.5 h-3.5" /> {t("workspaces.capabilityConfig")}
            </h2>
            <p className="text-xs text-muted-foreground -mt-5">
              {t("workspaces.capabilityConfigDesc")}
            </p>

            {/* Type filter bar */}
            <div className="flex items-center gap-1.5 -mt-2 flex-nowrap overflow-x-auto">
              <Filter className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
              {(Object.keys(TYPE_FILTER_KEYS) as TypeFilterKey[]).map((key) => {
                const config = TYPE_FILTER_KEYS[key];
                const active = selectedType === key;
                const count = typeCounts[key];
                return (
                  <button
                    key={key}
                    onClick={() => setSelectedType(key)}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition border shrink-0
                      ${
                        active
                          ? "bg-brand/15 border-brand/40 text-brand shadow-sm"
                          : "bg-transparent border-border text-muted-foreground hover:border-muted-foreground/40 hover:text-foreground"
                      }`}
                  >
                    {t(config)}
                    {count > 0 && (
                      <span
                        className={`inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full text-[10px] font-semibold
                          ${active ? "bg-brand/20 text-brand" : "bg-muted text-muted-foreground"}`}
                      >
                        {count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* Team selector */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm font-medium">{t("workspaces.team")}</span>
                {resourcesLoading && (
                  <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
                )}
                <Badge variant="secondary" className="text-[10px] ml-auto">
                  {filteredTeams.length > 0
                    ? selectedTeam
                      ? t("workspaces.oneSelected")
                      : t("workspaces.notSelected")
                    : t("workspaces.noneAvailable")}
                  {filterType && filteredTeams.length !== marketTeams.length && (
                    <span className="ml-1 opacity-60">
                      ({filteredTeams.length}/{marketTeams.length})
                    </span>
                  )}
                </Badge>
              </div>
              {filteredTeams.length === 0 && !resourcesLoading ? (
                <p className="text-xs text-muted-foreground pl-6 py-1">
                  {t("workspaces.noTeamsHint")}
                </p>
              ) : (
                <div className="pl-6 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                  {/* "None" option to deselect */}
                  <label
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-lg cursor-pointer transition text-sm
                      ${!selectedTeam ? "bg-brand/10 border border-brand/30" : "hover:bg-accent/50 border border-transparent"}`}
                  >
                    <Checkbox
                      checked={!selectedTeam}
                      onCheckedChange={() => handleTeamSelect(null)}
                    />
                    <div className="min-w-0 flex-1">
                      <span className="truncate block text-muted-foreground">
                        {t("workspaces.noTeam")}
                      </span>
                      <span className="text-[11px] text-muted-foreground">
                        {t("workspaces.manualConfig")}
                      </span>
                    </div>
                  </label>
                  {filteredTeams.map((team) => {
                    const checked = selectedTeam === team.id;
                    const meta = team.extra_metadata || {};
                    const agentCount = ((meta.agents as string[] | null) ?? []).length;
                    const skillCount = ((meta.skills as string[] | null) ?? []).length;
                    const kbCount = ((meta.knowledges as string[] | null) ?? []).length;
                    const mcpCount = ((meta.mcps as string[] | null) ?? []).length;
                    const total = agentCount + skillCount + kbCount + mcpCount;
                    return (
                      <label
                        key={team.id}
                        className={`flex items-center gap-2.5 px-3 py-2 rounded-lg cursor-pointer transition text-sm
                          ${checked ? "bg-brand/10 border border-brand/30" : "hover:bg-accent/50 border border-transparent"}`}
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={() => handleTeamSelect(checked ? null : team.id)}
                        />
                        <div className="min-w-0 flex-1">
                          <span className="truncate block">{team.name}</span>
                          <span className="text-[11px] text-muted-foreground truncate block">
                            {total > 0
                              ? t("workspaces.resourceCount", { count: total })
                              : team.description?.slice(0, 30) || t("workspaces.teamConfig")}
                          </span>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Experts / Agents (dynamic + market) */}
            <ResourceSection
              title={t("workspaces.agents")}
              icon={Bot}
              items={[
                ...allExperts.map((e) => ({ id: e.id })),
                ...marketAgents.map((a) => ({ id: a.id })),
              ]}
              selectedIds={selectedExperts}
              onToggle={toggleSet(setSelectedExperts)}
              filterType={filterType}
              resourceTypeMap={resourceTypeMap}
              getSearchText={(item) => {
                const e = allExperts.find((e) => e.id === item.id);
                if (e) return e.description ?? "";
                const a = marketAgents.find((a) => a.id === item.id);
                return a ? `${a.author} ${a.description ?? ""}` : "";
              }}
              renderLabel={(item) => {
                const e = allExperts.find((e) => e.id === item.id);
                if (e) return e.name;
                const a = marketAgents.find((a) => a.id === item.id);
                return a?.name || item.id;
              }}
              renderSub={(item) => {
                const e = allExperts.find((e) => e.id === item.id);
                if (e) return e.description;
                const a = marketAgents.find((a) => a.id === item.id);
                return a ? `${a.author} · v${a.version}` : undefined;
              }}
            />

            {/* Knowledge Bases (from market) */}
            <ResourceSection
              title={t("workspaces.knowledgeBases")}
              icon={BookOpen}
              items={marketKnowledge.map((kb) => ({ id: kb.id }))}
              selectedIds={selectedKnowledgeBases}
              onToggle={toggleSet(setSelectedKnowledgeBases)}
              loading={resourcesLoading}
              filterType={filterType}
              resourceTypeMap={resourceTypeMap}
              getSearchText={(item) => {
                const kb = marketKnowledge.find((kb) => kb.id === item.id);
                return kb ? `${kb.description ?? ""} ${kb.tags?.join(" ") ?? ""}` : "";
              }}
              renderLabel={(item) =>
                marketKnowledge.find((kb) => kb.id === item.id)?.name || item.id
              }
              renderSub={(item) => {
                const kb = marketKnowledge.find((kb) => kb.id === item.id);
                return kb
                  ? `${kb.author} · v${kb.version}${kb.description ? ` · ${kb.description.slice(0, 30)}` : ""}`
                  : undefined;
              }}
            />

            {/* MCP Servers (from market) */}
            <ResourceSection
              title={t("workspaces.mcpServers")}
              icon={Wrench}
              items={marketMcpServers.map((s) => ({ id: s.id }))}
              selectedIds={selectedMcpServers}
              onToggle={toggleSet(setSelectedMcpServers)}
              loading={resourcesLoading}
              filterType={filterType}
              resourceTypeMap={resourceTypeMap}
              renderLabel={(item) =>
                marketMcpServers.find((s) => s.id === item.id)?.name || item.id
              }
              renderSub={(item) => {
                const s = marketMcpServers.find((s) => s.id === item.id);
                return s ? `${s.author} · v${s.version}` : undefined;
              }}
            />

            {/* Skills (from market) */}
            <ResourceSection
              title={t("workspaces.skills")}
              icon={Sparkles}
              items={marketSkills.map((s) => ({ id: s.id }))}
              selectedIds={selectedSkills}
              onToggle={toggleSet(setSelectedSkills)}
              loading={resourcesLoading}
              filterType={filterType}
              resourceTypeMap={resourceTypeMap}
              renderLabel={(item) => marketSkills.find((s) => s.id === item.id)?.name || item.id}
              renderSub={(item) => {
                const s = marketSkills.find((s) => s.id === item.id);
                return s
                  ? `v${s.version}${s.downloads ? t("workspaces.downloadsSuffix", { count: s.downloads }) : ""}`
                  : undefined;
              }}
            />
          </div>
        </div>
      </div>
    );
  }

  // ── List Page ──────────────────────────────────────────────
  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin">
      <div className="max-w-5xl mx-auto px-4 py-6 sm:px-6 sm:py-10">
        {/* Header */}
        <div className="flex flex-col gap-4 mb-8 sm:flex-row sm:items-center sm:gap-3">
          <div className="flex items-center gap-3 sm:contents">
            <div className="w-12 h-12 rounded-xl bg-gradient-brand flex items-center justify-center shadow-brand shrink-0">
              <FolderOpen className="w-6 h-6 text-brand-foreground" />
            </div>
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl font-bold">{t("workspaces.title")}</h1>
              <p className="text-sm text-muted-foreground">{t("workspaces.subtitle")}</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:flex sm:items-center sm:gap-2">
            <Button onClick={() => handleQuickNewTask()} disabled={creating} className="gap-1.5">
              {creating ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <MessageSquarePlus className="w-4 h-4" />
              )}
              {t("workspaces.newChat")}
            </Button>
            <Button
              variant="outline"
              onClick={() => setCreateColl({ open: true })}
              className="gap-1.5"
            >
              <Layers className="w-4 h-4" />
              {t("workspaces.newCollection")}
            </Button>
            <Button
              onClick={() => {
                resetCreateForm();
                setMode("create");
              }}
              className="gap-1.5"
            >
              <FolderPlus className="w-4 h-4" />
              {t("workspaces.createWorkspace")}
            </Button>
          </div>
        </div>

        {/* View toggle: 工作区 / 全部任务 */}
        <div className="w-full grid grid-cols-2 gap-1 p-1 bg-muted/40 rounded-lg mb-6 sm:w-auto sm:inline-flex sm:items-center">
          {(["workspaces", "tasks"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${
                view === v
                  ? "bg-background shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {v === "workspaces" ? t("workspaces.tabWorkspaces") : t("workspaces.tabTasks")}
            </button>
          ))}
        </div>

        {view === "workspaces" && (
          <>
            {/* ── Collections Section ─────────────────────────────── */}
            {collections.length > 0 && (
              <div className="mb-8">
                <div className="flex items-center gap-2 mb-3">
                  <LayersIcon className="w-4 h-4 text-muted-foreground" />
                  <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                    {t("workspaces.collectionSection")}
                  </h2>
                  <Badge variant="secondary" className="text-[10px]">
                    {collections.length}
                  </Badge>
                </div>
                <div className="space-y-3">
                  {collections.map((coll) => {
                    const collWorkspaces = workspaces.filter((ws) =>
                      coll.workspaceIds.includes(ws.id),
                    );
                    const isExpanded = expandedCollections.has(coll.id);
                    return (
                      <Collapsible
                        key={coll.id}
                        open={isExpanded}
                        onOpenChange={() => toggleExpanded(coll.id)}
                      >
                        <div className="bg-card/60 border border-border rounded-2xl overflow-hidden">
                          {/* Collection header */}
                          <CollapsibleTrigger asChild>
                            <div className="flex items-center gap-3 p-4 cursor-pointer hover:bg-accent/30 transition">
                              <ChevronRight
                                className={`w-4 h-4 text-muted-foreground transition-transform ${isExpanded ? "rotate-90" : ""}`}
                              />
                              <div className="w-9 h-9 rounded-lg bg-violet-500/10 border border-violet-500/30 flex items-center justify-center shrink-0">
                                <Layers className="w-4 h-4 text-violet-500" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="font-medium text-sm truncate">{coll.name}</span>
                                  <Badge variant="secondary" className="text-[10px]">
                                    {t("workspaces.workspaceCount", {
                                      count: collWorkspaces.length,
                                    })}
                                  </Badge>
                                </div>
                                {coll.description && (
                                  <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
                                    {coll.description}
                                  </p>
                                )}
                              </div>
                              <div
                                className="flex items-center gap-1 shrink-0"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="gap-1 text-xs h-7 hidden sm:inline-flex"
                                  onClick={() => openEditCollWs(coll)}
                                >
                                  <Settings2 className="w-3 h-3" />
                                  {t("workspaces.manageWorkspaces")}
                                </Button>
                                <DropdownMenu>
                                  <DropdownMenuTrigger asChild>
                                    <Button variant="ghost" size="icon" className="h-7 w-7">
                                      <MoreHorizontal className="w-4 h-4" />
                                    </Button>
                                  </DropdownMenuTrigger>
                                  <DropdownMenuContent align="end">
                                    <DropdownMenuItem
                                      className="sm:hidden"
                                      onClick={() => openEditCollWs(coll)}
                                    >
                                      <Settings2 className="w-3.5 h-3.5 mr-2" />{" "}
                                      {t("workspaces.manageWorkspaces")}
                                    </DropdownMenuItem>
                                    <DropdownMenuSeparator className="sm:hidden" />
                                    <DropdownMenuItem
                                      onClick={() => {
                                        setRenameValue(coll.name);
                                        setRenameTarget({
                                          open: true,
                                          id: coll.id,
                                          name: coll.name,
                                          kind: "collection",
                                        });
                                      }}
                                    >
                                      <Pencil className="w-3.5 h-3.5 mr-2" />{" "}
                                      {t("workspaces.rename")}
                                    </DropdownMenuItem>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem
                                      className="text-destructive focus:text-destructive"
                                      onClick={() =>
                                        setDeleteTarget({
                                          open: true,
                                          id: coll.id,
                                          name: coll.name,
                                          kind: "collection",
                                          count: collWorkspaces.length,
                                        })
                                      }
                                    >
                                      <Trash2 className="w-3.5 h-3.5 mr-2" />{" "}
                                      {t("workspaces.deleteCollection")}
                                    </DropdownMenuItem>
                                  </DropdownMenuContent>
                                </DropdownMenu>
                              </div>
                            </div>
                          </CollapsibleTrigger>

                          {/* Collection workspaces */}
                          <CollapsibleContent>
                            <div className="px-4 pb-4 space-y-2">
                              {collWorkspaces.length === 0 ? (
                                <div className="text-xs text-muted-foreground py-3 text-center border-t border-border/50">
                                  {t("workspaces.emptyCollection")}
                                </div>
                              ) : (
                                collWorkspaces.map((ws) => renderWorkspaceRow(ws))
                              )}
                            </div>
                          </CollapsibleContent>
                        </div>
                      </Collapsible>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── All Workspaces Section ──────────────────────────── */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <FolderOpen className="w-4 h-4 text-muted-foreground" />
                <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                  {t("workspaces.allWorkspaces")}
                </h2>
                <Badge variant="secondary" className="text-[10px]">
                  {workspaces.length}
                </Badge>
              </div>

              {workspaces.length === 0 ? (
                <div className="bg-card/40 border border-dashed border-border rounded-2xl p-8 sm:p-14 text-center">
                  <FolderOpen className="w-10 h-10 mx-auto text-muted-foreground/40 mb-3" />
                  <p className="text-sm text-muted-foreground mb-4">
                    {t("workspaces.noWorkspaces")}
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => {
                      resetCreateForm();
                      setMode("create");
                    }}
                    className="gap-1.5"
                  >
                    <FolderPlus className="w-4 h-4" />
                    {t("workspaces.createWorkspace")}
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  {workspaces.map((ws) => {
                    const parentColl = collections.find((c) => c.workspaceIds.includes(ws.id));
                    return (
                      <div key={ws.id}>
                        {renderWorkspaceRow(ws, !!parentColl, parentColl?.name)}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}

        {/* ── All Tasks (flat, cross-workspace) view ─────────── */}
        {view === "tasks" && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <ListTodo className="w-4 h-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                {t("workspaces.tabTasks")}
              </h2>
              <Badge variant="secondary" className="text-[10px]">
                {tasks.length}
              </Badge>
            </div>

            {tasks.length === 0 ? (
              <div className="bg-card/40 border border-dashed border-border rounded-2xl p-8 sm:p-14 text-center">
                <ListTodo className="w-10 h-10 mx-auto text-muted-foreground/40 mb-3" />
                <p className="text-sm text-muted-foreground mb-4">{t("workspaces.noTasks")}</p>
                <Button
                  onClick={() => handleQuickNewTask()}
                  disabled={creating}
                  className="gap-1.5"
                >
                  {creating ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <MessageSquarePlus className="w-4 h-4" />
                  )}
                  {t("workspaces.newChat")}
                </Button>
              </div>
            ) : (
              <div className="space-y-2.5">
                {tasks.map((tk) => {
                  const ws = workspaces.find((w) => w.id === tk.workspaceId);
                  const hasWorkspace = !!tk.workspaceId;
                  return (
                    <Link
                      key={tk.id}
                      to={hasWorkspace ? "/workspace/$workspaceId/task/$taskId" : "/temp/$taskId"}
                      params={
                        hasWorkspace
                          ? { workspaceId: tk.workspaceId!, taskId: tk.id }
                          : { taskId: tk.id }
                      }
                      className="group bg-gradient-card border border-border rounded-2xl p-4 flex items-center gap-4 hover:border-brand/40 transition-all"
                    >
                      <div className="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center shrink-0">
                        <FolderOpen className="w-5 h-5 text-brand" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium truncate">{tk.title}</h3>
                        <p className="text-xs text-muted-foreground mt-1">
                          {ws
                            ? ws.name
                            : hasWorkspace
                              ? t("workspaces.workspaceTask")
                              : t("workspaces.temporaryTask")}
                        </p>
                      </div>
                      <ArrowRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition shrink-0" />
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Dialogs (only rename, delete, collection create, collection edit) ── */}

      {/* Create Collection */}
      <Dialog
        open={createColl.open}
        onOpenChange={(o) => setCreateColl(o ? { open: true } : { open: false })}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("workspaces.newCollectionTitle")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder={t("workspaces.collectionNamePlaceholder")}
              value={newCollName}
              onChange={(e) => setNewCollName(e.target.value)}
              autoFocus
            />
            <Textarea
              placeholder={t("workspaces.collectionDescPlaceholder")}
              value={newCollDesc}
              onChange={(e) => setNewCollDesc(e.target.value)}
              rows={2}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setCreateColl({ open: false })}>
              {t("workspaces.cancel")}
            </Button>
            <Button
              className="bg-gradient-brand text-brand-foreground"
              onClick={handleCreateCollection}
            >
              {t("workspaces.create")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename (workspace or collection) */}
      <Dialog open={renameTarget.open} onOpenChange={(o) => !o && setRenameTarget({ open: false })}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("workspaces.renameTitlePrefix")}
              {renameTarget.open && renameTarget.kind === "collection"
                ? t("workspaces.kindCollection")
                : t("workspaces.kindWorkspace")}
            </DialogTitle>
          </DialogHeader>
          <Input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && renameValue.trim()) handleRename();
            }}
            autoFocus
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRenameTarget({ open: false })}>
              {t("workspaces.cancel")}
            </Button>
            <Button className="bg-gradient-brand text-brand-foreground" onClick={handleRename}>
              {t("workspaces.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation (workspace or collection) */}
      <AlertDialog
        open={deleteTarget.open}
        onOpenChange={(o) => !o && setDeleteTarget({ open: false })}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-destructive">
              {deleteTarget.open && deleteTarget.kind === "collection"
                ? t("workspaces.deleteCollectionTitle")
                : t("workspaces.deleteWorkspaceTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("workspaces.deletePrefix", { name: deleteTarget.open ? deleteTarget.name : "" })}
              {deleteTarget.open && deleteTarget.kind === "workspace" && deleteTarget.count > 0 && (
                <>
                  {t("workspaces.andAlso")}{" "}
                  <span className="text-destructive font-medium">
                    {t("workspaces.deleteTasksAlso", { count: deleteTarget.count })}
                  </span>
                </>
              )}
              {deleteTarget.open && deleteTarget.kind === "collection" && (
                <>{t("workspaces.collectionDeleteNote")}</>
              )}{" "}
              {t("workspaces.cannotUndo")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("workspaces.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteTarget.open && deleteTarget.kind === "collection"
                ? t("workspaces.deleteCollection")
                : t("workspaces.deleteWorkspace")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Edit Collection Workspaces (checkbox picker) */}
      <Dialog open={editCollWs.open} onOpenChange={(o) => !o && setEditCollWs({ open: false })}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {t("workspaces.manageCollectionWorkspaces", {
                name: editCollWs.open ? editCollWs.collectionName : "",
              })}
            </DialogTitle>
          </DialogHeader>
          <div className="max-h-[50vh] overflow-y-auto space-y-2 py-2">
            {workspaces.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                {t("workspaces.noSelectableWorkspaces")}
              </p>
            ) : (
              workspaces.map((ws) => {
                const checked = selectedWsIds.has(ws.id);
                return (
                  <label
                    key={ws.id}
                    className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-accent/50 cursor-pointer transition"
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={(c) => {
                        setSelectedWsIds((prev) => {
                          const next = new Set(prev);
                          if (c) next.add(ws.id);
                          else next.delete(ws.id);
                          return next;
                        });
                      }}
                    />
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium truncate block">{ws.name}</span>
                      <span className="text-[11px] text-muted-foreground">
                        {t("workspaces.taskCount", {
                          count: tasks.filter((x) => x.workspaceId === ws.id).length,
                        })}
                      </span>
                    </div>
                  </label>
                );
              })
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditCollWs({ open: false })}>
              {t("workspaces.cancel")}
            </Button>
            <Button className="bg-gradient-brand text-brand-foreground" onClick={handleSaveCollWs}>
              {t("workspaces.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
