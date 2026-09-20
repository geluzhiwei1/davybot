import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect, useCallback } from "react";
import {
  Store,
  Search,
  Download,
  Eye,
  Star,
  Users,
  BookOpen,
  Monitor,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  PackageCheck,
  ChevronDown,
  ChevronUp,
  Tag,
  User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  marketApi,
  botApi,
  type MarketResource,
  type DiscoveryStats,
  type TeamHierarchyResponse,
  type TeamHierarchyEntry,
} from "@/lib/market-api";
import { useWorkspaceStore } from "@/lib/workspace-store";
import { toast } from "sonner";
import { toastError } from "@/lib/api/client.js";
import { useTranslation } from "react-i18next";
import i18n from "@/lib/i18n";

// ── Local install state (for web mode) ───────────────────────────

function getInstalledSet(): Set<string> {
  try {
    const raw = localStorage.getItem("market_installed_ids");
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function markInstalled(id: string) {
  const set = getInstalledSet();
  set.add(id);
  localStorage.setItem("market_installed_ids", JSON.stringify([...set]));
}

// ── Route ────────────────────────────────────────────────────────

export const Route = createFileRoute("/resources")({
  head: () => ({
    meta: [{ title: i18n.t("routesB:market.metaTitle") }],
  }),
  component: MarketPage,
});

const RESOURCE_TABS = [
  { type: "team", labelKey: "market.tab.team", icon: Users },
  { type: "knowledge", labelKey: "market.tab.knowledge", icon: BookOpen },
  { type: "skill", labelKey: "market.tab.skill", icon: Sparkles },
  { type: "agent", labelKey: "market.tab.agent", icon: Monitor },
  { type: "mcp", labelKey: "market.tab.mcp", icon: Monitor },
] as const;

const TYPE_ICON: Record<string, typeof Store> = {
  skill: Sparkles,
  agent: Monitor,
  mcp: Monitor,
  knowledge: BookOpen,
  plugin: PackageCheck,
  team: Users,
};

// ── Main Page ────────────────────────────────────────────────────

function MarketPage() {
  const { t } = useTranslation("routesB");
  const [activeTab, setActiveTab] = useState("team");
  const [resources, setResources] = useState<MarketResource[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<DiscoveryStats | null>(null);
  const pageSize = 20;

  // Detail sheet state
  const [selectedResource, setSelectedResource] = useState<MarketResource | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // Team hierarchy state
  const [teamHierarchy, setTeamHierarchy] = useState<TeamHierarchyResponse | null>(null);
  const [expandedTeams, setExpandedTeams] = useState<Set<string>>(new Set());
  const [selectedTeam, setSelectedTeam] = useState<TeamHierarchyEntry | null>(null);

  // Install state
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [installedIds, setInstalledIds] = useState<Set<string>>(getInstalledSet());

  const loadResources = useCallback(async () => {
    setLoading(true);
    try {
      const res = await marketApi.listResources({
        type: activeTab,
        page,
        page_size: pageSize,
        search: searchQuery || undefined,
      });
      setResources(res.items || []);
      setTotal(res.total || 0);
    } catch (e: unknown) {
      console.error("Failed to load market resources:", e);
      toastError(t("market.loadFailed"), e);
    } finally {
      setLoading(false);
    }
  }, [activeTab, page, searchQuery]);

  const loadStats = useCallback(async () => {
    try {
      const res = await marketApi.getDiscoveryStats();
      setStats(res);
    } catch (e) {
      console.error("Failed to load market stats:", e);
      toastError(t("market.statsFailed"), e);
    }
  }, []);

  const loadTeamHierarchy = useCallback(async () => {
    try {
      const res = await marketApi.getTeamHierarchy();
      setTeamHierarchy(res);
    } catch (e) {
      console.error("Failed to load team hierarchy:", e);
      toastError(t("market.hierarchyFailed"), e);
    }
  }, []);

  useEffect(() => {
    loadResources();
  }, [loadResources]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    if (activeTab === "team") {
      loadTeamHierarchy();
    }
  }, [activeTab, loadTeamHierarchy]);

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    setPage(1);
    setSearchQuery("");
    setSelectedResource(null);
    setSelectedTeam(null);
    setDetailOpen(false);
  };

  const handleSearch = () => {
    setPage(1);
    loadResources();
  };

  const handleCardClick = (resource: MarketResource) => {
    setSelectedResource(resource);
    setDetailOpen(true);
  };

  const handleInstall = async (item: MarketResource) => {
    setInstallingId(item.id);
    try {
      const workspaceId = useWorkspaceStore.getState().currentWorkspaceId;
      if (!workspaceId) {
        toast.error(t("market.noWorkspace"));
        return;
      }

      // v3 资源 id 已是完整形式(template/{team}/{slug});旧数据缺 id 时退回 type/slug 构造
      const resourceId = item.id?.includes("/")
        ? item.id
        : `${item.type}/${item.slug || item.name}`;
      const result = await botApi.installResources({
        workspace: workspaceId,
        resource_id: resourceId,
      });

      if (result.success) {
        const installed = result.installed;
        const count = Object.values(installed).flat().length;
        toast.success(
          count > 0
            ? t("market.installedWithCount", { name: item.name, count })
            : t("market.installed", { name: item.name }),
        );
      } else {
        toast.error(t("market.installFailed", { error: result.error || t("market.unknownError") }));
      }

      markInstalled(item.id);
      setInstalledIds(getInstalledSet());
    } catch (e: unknown) {
      toast.error(
        t("market.installFailed", {
          error: e instanceof Error ? e.message : t("market.unknownError"),
        }),
      );
    } finally {
      setInstallingId(null);
    }
  };

  const toggleTeam = (slug: string) => {
    setExpandedTeams((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  };

  const totalPages = Math.ceil(total / pageSize);
  const typeCount = (type: string) => stats?.total_by_type?.[type] || 0;

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin">
      <div className="max-w-6xl mx-auto px-6 py-10">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div className="w-12 h-12 rounded-xl bg-gradient-brand flex items-center justify-center shadow-brand">
            <Store className="w-6 h-6 text-brand-foreground" />
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-bold">{t("market.title")}</h1>
            <p className="text-sm text-muted-foreground">{t("market.desc")}</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder={t("market.searchPlaceholder")}
                className="pl-9 w-56"
              />
            </div>
          </div>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
            {RESOURCE_TABS.map((tab) => {
              const count = typeCount(tab.type);
              const Icon = tab.icon;
              return (
                <div
                  key={tab.type}
                  className="bg-card/60 border border-border rounded-xl p-4 flex items-center gap-3"
                >
                  <div className="w-10 h-10 rounded-lg bg-brand/10 flex items-center justify-center shrink-0">
                    <Icon className="w-5 h-5 text-brand" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold">{count}</p>
                    <p className="text-xs text-muted-foreground">{t(tab.labelKey)}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <TabsList className="mb-6">
            {RESOURCE_TABS.map((tab) => (
              <TabsTrigger key={tab.type} value={tab.type} className="gap-1.5">
                <tab.icon className="w-3.5 h-3.5" />
                {t(tab.labelKey)}
                {stats && typeCount(tab.type) > 0 && (
                  <span className="text-[10px] text-muted-foreground ml-1">
                    ({typeCount(tab.type)})
                  </span>
                )}
              </TabsTrigger>
            ))}
          </TabsList>

          {RESOURCE_TABS.map((tab) => (
            <TabsContent key={tab.type} value={tab.type}>
              {tab.type === "team" ? (
                <TeamTabContent
                  resources={resources}
                  teamHierarchy={teamHierarchy}
                  expandedTeams={expandedTeams}
                  loading={loading}
                  onToggleTeam={toggleTeam}
                  onCardClick={handleCardClick}
                  onTeamClick={(team) => {
                    setSelectedTeam(team);
                    setSelectedResource(null);
                    setDetailOpen(true);
                  }}
                  onInstall={handleInstall}
                  installingId={installingId}
                  installedIds={installedIds}
                />
              ) : (
                <ResourceGrid
                  resources={resources}
                  loading={loading}
                  emptyLabel={t(tab.labelKey)}
                  onCardClick={handleCardClick}
                  onInstall={handleInstall}
                  installingId={installingId}
                  installedIds={installedIds}
                />
              )}

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2 mt-8">
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <span className="text-sm text-muted-foreground">
                    {page} / {totalPages} ({total})
                  </span>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              )}
            </TabsContent>
          ))}
        </Tabs>
      </div>

      {/* Detail Sheet */}
      <ResourceDetailSheet
        resource={selectedResource}
        team={selectedTeam}
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setSelectedTeam(null);
        }}
        onInstall={handleInstall}
        installingId={installingId}
        installedIds={installedIds}
      />
    </div>
  );
}

// ── Team Tab Content ─────────────────────────────────────────────

function TeamTabContent({
  resources,
  teamHierarchy,
  expandedTeams,
  loading,
  onToggleTeam,
  onCardClick,
  onTeamClick,
  onInstall,
  installingId,
  installedIds,
}: {
  resources: MarketResource[];
  teamHierarchy: TeamHierarchyResponse | null;
  expandedTeams: Set<string>;
  loading: boolean;
  onToggleTeam: (slug: string) => void;
  onCardClick: (r: MarketResource) => void;
  onTeamClick: (team: TeamHierarchyEntry) => void;
  onInstall: (r: MarketResource) => void;
  installingId: string | null;
  installedIds: Set<string>;
}) {
  const { t } = useTranslation("routesB");
  const teams = teamHierarchy?.teams;
  const hasHierarchy = teams && Array.isArray(teams) && teams.length > 0;

  if (hasHierarchy) {
    return (
      <div className="space-y-3">
        {teams.map((team, idx) => {
          const key = team.slug || team.name || String(idx);
          const members = Array.isArray(team.members) ? team.members : [];
          const memberCount = members.length || team.members_count || 0;
          return (
            <div key={key} className="border border-border rounded-xl overflow-hidden">
              <div className="flex items-center">
                {/* Clickable main area → opens team detail sheet */}
                <button
                  onClick={() => onTeamClick(team)}
                  className="flex-1 flex items-center gap-3 p-4 hover:bg-muted/30 transition-colors text-left"
                >
                  <div className="w-10 h-10 rounded-lg bg-brand/10 flex items-center justify-center shrink-0 text-lg">
                    {team.icon || <Users className="w-5 h-5 text-brand" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-sm truncate">{team.name}</h3>
                    <p className="text-xs text-muted-foreground truncate">
                      {team.description || t("market.memberCount", { count: memberCount })}
                    </p>
                  </div>
                  <Badge variant="secondary" className="text-[10px] shrink-0">
                    {t("market.resourceCount", { count: memberCount })}
                  </Badge>
                </button>
                {/* Chevron toggle → expand/collapse members */}
                <button
                  onClick={() => onToggleTeam(key)}
                  className="px-3 py-4 hover:bg-muted/30 transition-colors border-l border-border"
                  title={expandedTeams.has(key) ? t("market.collapse") : t("market.expandMembers")}
                >
                  {expandedTeams.has(key) ? (
                    <ChevronUp className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                  )}
                </button>
              </div>

              {expandedTeams.has(key) && members.length > 0 && (
                <div className="border-t border-border p-3 space-y-2">
                  {members.map((member) => {
                    const resource: MarketResource = {
                      id: member.id,
                      type: member.type,
                      name: member.name,
                      slug: member.slug,
                      description: member.description,
                      author: member.author,
                      version: member.version,
                      tags: member.tags,
                      extra_metadata: member.extra_metadata,
                      visibility: member.visibility,
                      status: member.status,
                      downloads: member.downloads,
                      rating_avg: member.rating_avg,
                      rating_count: member.rating_count,
                      view_count: member.view_count,
                      created_at: member.created_at,
                      updated_at: member.updated_at,
                    };
                    const Icon = TYPE_ICON[member.type] || Monitor;
                    return (
                      <div
                        key={member.id}
                        className="flex items-center gap-3 p-3 rounded-lg hover:bg-muted/20 cursor-pointer transition-colors group"
                        onClick={() => onCardClick(resource)}
                      >
                        <div className="w-8 h-8 rounded bg-muted/50 flex items-center justify-center shrink-0">
                          <Icon className="w-4 h-4 text-muted-foreground" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium truncate">{member.name}</span>
                            <Badge variant="outline" className="text-[9px] px-1 py-0 shrink-0">
                              {member.type}
                            </Badge>
                            {member.version && (
                              <Badge variant="secondary" className="text-[9px] px-1 py-0 shrink-0">
                                v{member.version}
                              </Badge>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground truncate">
                            {member.description || "No description"}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-[11px] text-muted-foreground flex items-center gap-0.5">
                            <Download className="w-3 h-3" /> {member.downloads}
                          </span>
                          <Button
                            size="sm"
                            variant={installedIds.has(member.id) ? "secondary" : "outline"}
                            className="h-6 text-[11px] gap-1 px-2"
                            disabled={installingId === member.id}
                            onClick={(e) => {
                              e.stopPropagation();
                              onInstall(resource);
                            }}
                          >
                            {installedIds.has(member.id) ? (
                              <>
                                <PackageCheck className="w-3 h-3" /> {t("market.installedBtn")}
                              </>
                            ) : installingId === member.id ? (
                              t("market.installing")
                            ) : (
                              <>
                                <PackageCheck className="w-3 h-3" /> {t("market.installBtn")}
                              </>
                            )}
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  // Fallback: show team resources as regular cards
  return (
    <ResourceGrid
      resources={resources}
      loading={loading}
      emptyLabel="团队"
      onCardClick={onCardClick}
      onInstall={onInstall}
      installingId={installingId}
      installedIds={installedIds}
    />
  );
}

// ── Resource Grid ────────────────────────────────────────────────

function ResourceGrid({
  resources,
  loading,
  emptyLabel,
  onCardClick,
  onInstall,
  installingId,
  installedIds,
}: {
  resources: MarketResource[];
  loading: boolean;
  emptyLabel: string;
  onCardClick: (r: MarketResource) => void;
  onInstall: (r: MarketResource) => void;
  installingId: string | null;
  installedIds: Set<string>;
}) {
  const { t } = useTranslation("routesB");
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">Loading...</div>
    );
  }
  if (resources.length === 0) {
    return (
      <div className="bg-card/40 border border-dashed border-border rounded-2xl p-10 text-center">
        <p className="text-sm text-muted-foreground">
          {t("market.emptyResources", { type: emptyLabel })}
        </p>
      </div>
    );
  }
  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {resources.map((item) => (
        <ResourceCard
          key={item.id}
          resource={item}
          onClick={() => onCardClick(item)}
          onInstall={onInstall}
          installing={installingId === item.id}
          installed={installedIds.has(item.id)}
        />
      ))}
    </div>
  );
}

// ── Resource Card ────────────────────────────────────────────────

function ResourceCard({
  resource,
  onClick,
  onInstall,
  installing,
  installed,
}: {
  resource: MarketResource;
  onClick: () => void;
  onInstall: (item: MarketResource) => void;
  installing: boolean;
  installed: boolean;
}) {
  const { t } = useTranslation("routesB");
  return (
    <div
      className="group bg-gradient-card border border-border rounded-2xl p-4 hover:border-brand/40 hover:shadow-brand/10 hover:shadow-md transition-all cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="font-medium text-sm truncate flex-1">{resource.name}</h3>
        <Badge variant="secondary" className="text-[10px] shrink-0">
          {resource.version}
        </Badge>
      </div>

      <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed mb-3 min-h-[2.5rem]">
        {resource.description || "No description"}
      </p>

      {/* Tags */}
      {resource.tags?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {resource.tags.slice(0, 4).map((tag) => (
            <Badge key={tag} variant="outline" className="text-[10px] px-1.5 py-0">
              {tag}
            </Badge>
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-0.5">
            <Download className="w-3 h-3" /> {resource.downloads}
          </span>
          <span className="flex items-center gap-0.5">
            <Eye className="w-3 h-3" /> {resource.view_count}
          </span>
          <span className="flex items-center gap-0.5">
            <Star className="w-3 h-3" /> {resource.rating_avg?.toFixed(1) || "-"}
          </span>
        </div>
        <Button
          size="sm"
          variant={installed ? "secondary" : "outline"}
          className="h-7 text-xs gap-1"
          disabled={installing}
          onClick={(e) => {
            e.stopPropagation();
            onInstall(resource);
          }}
        >
          {installed ? (
            <>
              <PackageCheck className="w-3 h-3" /> {t("market.installedBtn")}
            </>
          ) : installing ? (
            t("market.installing")
          ) : (
            <>
              <PackageCheck className="w-3 h-3" /> {t("market.installBtn")}
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

// ── Detail Sheet ─────────────────────────────────────────────────

function ResourceDetailSheet({
  resource,
  team,
  open,
  onClose,
  onInstall,
  installingId,
  installedIds,
}: {
  resource: MarketResource | null;
  team: TeamHierarchyEntry | null;
  open: boolean;
  onClose: () => void;
  onInstall: (r: MarketResource) => void;
  installingId: string | null;
  installedIds: Set<string>;
}) {
  const { t } = useTranslation("routesB");
  // Team detail mode
  if (team && !resource) {
    const members = Array.isArray(team.members) ? team.members : [];
    const mcps = Array.isArray(team.mcps) ? team.mcps : [];
    const skills = Array.isArray(team.skills) ? team.skills : [];
    const knowledges = Array.isArray(team.knowledges) ? team.knowledges : [];
    const agents = Array.isArray(team.agents) ? team.agents : [];

    const CATEGORY_SECTIONS = [
      { label: "MCP", items: mcps, icon: Monitor },
      { label: "Skills", items: skills, icon: Sparkles },
      { label: "Knowledge", items: knowledges, icon: BookOpen },
      { label: "Agents", items: agents, icon: Users },
    ] as const;

    return (
      <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
        <SheetContent className="w-[440px] sm:max-w-[440px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center shrink-0 text-base">
                {team.icon || <Users className="w-4 h-4 text-brand" />}
              </div>
              <span className="truncate">{team.name}</span>
              <Badge variant="outline" className="text-[10px] shrink-0">
                {t("market.badgeTeam")}
              </Badge>
            </SheetTitle>
            <SheetDescription className="sr-only">{team.name} team details</SheetDescription>
          </SheetHeader>

          <div className="space-y-5 pt-4">
            {/* Description */}
            {team.description && (
              <div>
                <h4 className="text-xs font-medium text-muted-foreground mb-1">
                  {t("market.description")}
                </h4>
                <p className="text-sm leading-relaxed">{team.description}</p>
              </div>
            )}

            {/* Team metadata */}
            <div className="grid grid-cols-2 gap-3">
              {team.team_type && (
                <div className="bg-muted/30 rounded-lg p-3">
                  <div className="text-xs text-muted-foreground mb-1">{t("market.type")}</div>
                  <p className="text-sm font-medium capitalize">{team.team_type}</p>
                </div>
              )}
              {team.category && (
                <div className="bg-muted/30 rounded-lg p-3">
                  <div className="text-xs text-muted-foreground mb-1">{t("market.category")}</div>
                  <p className="text-sm font-medium capitalize">{team.category}</p>
                </div>
              )}
              <div className="bg-muted/30 rounded-lg p-3">
                <div className="text-xs text-muted-foreground mb-1">{t("market.priority")}</div>
                <p className="text-sm font-medium">{team.priority ?? "-"}</p>
              </div>
              <div className="bg-muted/30 rounded-lg p-3">
                <div className="text-xs text-muted-foreground mb-1">{t("market.status")}</div>
                <p className="text-sm font-medium">
                  {team.enabled !== false ? (
                    <span className="text-green-600">{t("market.enabled")}</span>
                  ) : (
                    <span className="text-muted-foreground">{t("market.disabled")}</span>
                  )}
                </p>
              </div>
              <div className="bg-muted/30 rounded-lg p-3">
                <div className="text-xs text-muted-foreground mb-1">
                  {t("market.totalResources")}
                </div>
                <p className="text-sm font-medium">{members.length}</p>
              </div>
              <div className="bg-muted/30 rounded-lg p-3">
                <div className="text-xs text-muted-foreground mb-1">Slug</div>
                <p className="text-sm font-medium font-mono text-[11px]">{team.slug || "-"}</p>
              </div>
            </div>

            {/* Categorized member sections */}
            {CATEGORY_SECTIONS.map(({ label, items, icon: SectionIcon }) =>
              items.length > 0 ? (
                <div key={label}>
                  <h4 className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1.5">
                    <SectionIcon className="w-3 h-3" /> {label}
                    <Badge variant="secondary" className="text-[9px] px-1 py-0 ml-1">
                      {items.length}
                    </Badge>
                  </h4>
                  <div className="space-y-1.5">
                    {items.map((member) => {
                      const isDisplayOnly =
                        (member as unknown as Record<string, unknown>)?.display_only === true;
                      const memberResource: MarketResource = {
                        id: member.id,
                        type: member.type,
                        name: member.name,
                        slug: member.slug,
                        description: member.description,
                        author: member.author,
                        version: member.version,
                        tags: member.tags,
                        extra_metadata: member.extra_metadata,
                        visibility: member.visibility,
                        status: member.status,
                        downloads: member.downloads,
                        rating_avg: member.rating_avg,
                        rating_count: member.rating_count,
                        view_count: member.view_count,
                        created_at: member.created_at,
                        updated_at: member.updated_at,
                      };
                      const ItemIcon = TYPE_ICON[member.type] || Monitor;
                      return (
                        <div
                          key={member.id}
                          className="flex items-center gap-2 p-2 rounded-lg border border-border hover:bg-muted/20 transition-colors"
                        >
                          <div className="w-6 h-6 rounded bg-muted/50 flex items-center justify-center shrink-0">
                            <ItemIcon className="w-3 h-3 text-muted-foreground" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="text-sm font-medium truncate block">
                              {member.name}
                            </span>
                            {member.description && (
                              <p className="text-[11px] text-muted-foreground truncate">
                                {member.description}
                              </p>
                            )}
                          </div>
                          {isDisplayOnly ? (
                            <span className="text-[10px] text-muted-foreground shrink-0 px-2">
                              {t("market.displayOnly")}
                            </span>
                          ) : (
                            <Button
                              size="sm"
                              variant={installedIds.has(member.id) ? "secondary" : "outline"}
                              className="h-6 text-[11px] gap-1 px-2 shrink-0"
                              disabled={installingId === member.id}
                              onClick={(e) => {
                                e.stopPropagation();
                                onInstall(memberResource);
                              }}
                            >
                              {installedIds.has(member.id) ? (
                                <>
                                  <PackageCheck className="w-3 h-3" /> {t("market.installedBtn")}
                                </>
                              ) : installingId === member.id ? (
                                t("market.installing")
                              ) : (
                                <>
                                  <PackageCheck className="w-3 h-3" /> {t("market.installBtn")}
                                </>
                              )}
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null,
            )}

            {/* Close */}
            <div className="pt-2">
              <Button variant="outline" className="w-full" onClick={onClose}>
                {t("market.close")}
              </Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    );
  }

  // Resource detail mode
  if (!resource) return null;

  const isInstalling = installingId === resource.id;
  const isInstalled = installedIds.has(resource.id);
  const Icon = TYPE_ICON[resource.type] || Monitor;

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-[440px] sm:max-w-[440px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center shrink-0">
              <Icon className="w-4 h-4 text-brand" />
            </div>
            <span className="truncate">{resource.name}</span>
            <Badge variant="outline" className="text-[10px] shrink-0">
              {resource.type}
            </Badge>
          </SheetTitle>
          <SheetDescription className="sr-only">{resource.name} resource details</SheetDescription>
        </SheetHeader>

        <div className="space-y-5 pt-4">
          {/* Description */}
          {resource.description && (
            <div>
              <h4 className="text-xs font-medium text-muted-foreground mb-1">
                {t("market.description")}
              </h4>
              <p className="text-sm leading-relaxed">{resource.description}</p>
            </div>
          )}

          {/* Meta grid */}
          <div className="grid grid-cols-2 gap-3">
            {resource.author && (
              <div className="bg-muted/30 rounded-lg p-3">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                  <User className="w-3 h-3" /> {t("market.author")}
                </div>
                <p className="text-sm font-medium">{resource.author}</p>
              </div>
            )}
            <div className="bg-muted/30 rounded-lg p-3">
              <div className="text-xs text-muted-foreground mb-1">{t("market.version")}</div>
              <p className="text-sm font-medium">{resource.version}</p>
            </div>
            <div className="bg-muted/30 rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                <Download className="w-3 h-3" /> {t("market.downloads")}
              </div>
              <p className="text-sm font-medium">{resource.downloads}</p>
            </div>
            <div className="bg-muted/30 rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                <Eye className="w-3 h-3" /> {t("market.views")}
              </div>
              <p className="text-sm font-medium">{resource.view_count}</p>
            </div>
            <div className="bg-muted/30 rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                <Star className="w-3 h-3" /> {t("market.rating")}
              </div>
              <p className="text-sm font-medium">
                {resource.rating_avg?.toFixed(1) || "-"}
                {resource.rating_count > 0 && (
                  <span className="text-xs text-muted-foreground ml-1">
                    ({resource.rating_count})
                  </span>
                )}
              </p>
            </div>
            <div className="bg-muted/30 rounded-lg p-3">
              <div className="text-xs text-muted-foreground mb-1">{t("market.status")}</div>
              <p className="text-sm font-medium capitalize">{resource.status}</p>
            </div>
          </div>

          {/* Tags */}
          {resource.tags?.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1">
                <Tag className="w-3 h-3" /> {t("market.tags")}
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {resource.tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-xs">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Extra metadata */}
          {resource.extra_metadata && Object.keys(resource.extra_metadata).length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-muted-foreground mb-2">
                {t("market.extraInfo")}
              </h4>
              <div className="bg-muted/30 rounded-lg p-3 text-xs font-mono whitespace-pre-wrap">
                {JSON.stringify(resource.extra_metadata, null, 2)}
              </div>
            </div>
          )}

          {/* Dates */}
          <div className="text-xs text-muted-foreground space-y-1">
            <p>{t("market.createdAt", { date: new Date(resource.created_at).toLocaleString() })}</p>
            <p>{t("market.updatedAt", { date: new Date(resource.updated_at).toLocaleString() })}</p>
          </div>

          {/* Install button */}
          <div className="flex gap-2 pt-2">
            <Button variant="outline" className="flex-1" onClick={onClose}>
              {t("market.close")}
            </Button>
            <Button
              className="flex-1 gap-1.5"
              disabled={isInstalling || isInstalled}
              onClick={() => onInstall(resource)}
            >
              {isInstalled ? (
                <>
                  <PackageCheck className="w-4 h-4" /> {t("market.installedBtn")}
                </>
              ) : isInstalling ? (
                t("market.installing")
              ) : (
                <>
                  <PackageCheck className="w-4 h-4" /> {t("market.installBtn")}
                </>
              )}
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
