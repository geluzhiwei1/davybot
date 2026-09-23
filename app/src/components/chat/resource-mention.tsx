/**
 * Resource mention picker — shown when user types '@' in the input.
 * Tabbed interface: Files, Experts, Recent.
 * Search, keyboard nav, click to insert.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { FileText, Search, Clock, Sparkles, Bot, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import i18n from "@/lib/i18n";
import { type Expert } from "@/lib/experts";
import { ExpertIcon, getCategoryHue } from "@/components/expert-icon";

// ── Types ─────────────────────────────────────────────────────────

export interface MentionItem {
  id: string;
  name: string;
  description?: string;
  /** Lucide icon (for files, recent items) */
  icon?: LucideIcon;
  /** Emoji string — preferred for ExpertIcon emoji mode */
  expertEmoji?: string;
  /** HSL hue — for ExpertIcon background gradient */
  expertHue?: number;
  /** LucideIcon — backward compat (custom agents) */
  expertIcon?: LucideIcon;
  type: "file" | "expert" | "recent";
  meta?: string; // e.g. "2 小时前"
}

type TabId = "files" | "experts" | "recent";

interface TabDef {
  id: TabId;
  label: string;
  icon: LucideIcon;
}

const TABS: TabDef[] = [
  { id: "files", label: "mention.tab.files", icon: FileText },
  { id: "experts", label: "mention.tab.experts", icon: Bot },
  { id: "recent", label: "mention.tab.recent", icon: Clock },
];

// ── Component ─────────────────────────────────────────────────────

interface Props {
  visible: boolean;
  workspaceFiles?: { id: string; name: string; path?: string; kind?: string }[];
  /** Experts to list in the "experts" tab (from dynamic market teams) */
  experts?: Expert[];
  onSelect: (item: MentionItem) => void;
  onClose: () => void;
}

export function ResourceMention({
  visible,
  workspaceFiles = [],
  experts = [],
  onSelect,
  onClose,
}: Props) {
  const [activeTab, setActiveTab] = useState<TabId>("files");
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const { t } = useTranslation("chatUi");
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Build items for active tab
  const items = buildItems(activeTab, workspaceFiles, experts, query);

  // Reset on open
  useEffect(() => {
    if (visible) {
      setQuery("");
      setActiveIdx(0);
      // Auto-switch tab based on workspace files availability
      setActiveTab(workspaceFiles.length > 0 ? "files" : "experts");
      requestAnimationFrame(() => searchRef.current?.focus());
    }
  }, [visible, workspaceFiles.length]);

  // Scroll active into view
  useEffect(() => {
    if (!listRef.current) return;
    const activeEl = listRef.current.children[activeIdx] as HTMLElement | undefined;
    activeEl?.scrollIntoView({ block: "nearest" });
  }, [activeIdx]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case "ArrowUp":
          e.preventDefault();
          setActiveIdx((i) => Math.max(0, i - 1));
          break;
        case "ArrowDown":
          e.preventDefault();
          setActiveIdx((i) => Math.min(items.length - 1, i + 1));
          break;
        case "Enter":
          e.preventDefault();
          if (items[activeIdx]) onSelect(items[activeIdx]);
          break;
        case "Escape":
          e.preventDefault();
          onClose();
          break;
        case "Tab":
          e.preventDefault();
          // Cycle tabs
          setActiveTab((prev) => {
            const idx = TABS.findIndex((t) => t.id === prev);
            return TABS[(idx + 1) % TABS.length].id;
          });
          setActiveIdx(0);
          break;
      }
    },
    [items, activeIdx, onSelect, onClose],
  );

  if (!visible) return null;

  return (
    <div
      className="absolute bottom-full left-0 right-0 mb-1 z-50 rounded-xl border border-border bg-card/95 backdrop-blur-md shadow-lg overflow-hidden"
      onKeyDown={handleKeyDown}
    >
      {/* Tabs */}
      <div className="flex border-b border-border/60">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const count = buildItems(tab.id, workspaceFiles, experts, "").length;
          return (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                setActiveIdx(0);
                setQuery("");
              }}
              className={cn(
                "flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors",
                activeTab === tab.id
                  ? "text-brand border-b-2 border-brand"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {t(tab.label)}
              {count > 0 && <span className="text-[10px] text-muted-foreground">{count}</span>}
            </button>
          );
        })}
      </div>

      {/* Search */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/40">
        <Search className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        <input
          ref={searchRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIdx(0);
          }}
          placeholder={
            activeTab === "files"
              ? t("mention.search.files")
              : activeTab === "experts"
                ? t("mention.search.experts")
                : t("mention.search.recent")
          }
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>

      {/* Items */}
      <div ref={listRef} className="max-h-48 overflow-y-auto py-1">
        {items.length === 0 ? (
          <div className="px-3 py-6 text-center text-sm text-muted-foreground">
            {activeTab === "files"
              ? t("mention.empty.files")
              : activeTab === "experts"
                ? t("mention.empty.experts")
                : t("mention.empty.recent")}
          </div>
        ) : (
          items.map((item, i) => (
            <button
              key={item.id}
              onClick={() => onSelect(item)}
              onMouseEnter={() => setActiveIdx(i)}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2 text-left transition-colors",
                i === activeIdx ? "bg-accent/60" : "hover:bg-accent/30",
              )}
            >
              {item.expertEmoji ? (
                <ExpertIcon
                  emoji={item.expertEmoji}
                  hue={item.expertHue}
                  size="sm"
                  className="!w-5 !h-5 shrink-0"
                />
              ) : item.expertHue != null ? (
                <ExpertIcon
                  hue={item.expertHue}
                  icon={item.expertIcon}
                  size="sm"
                  className="!w-5 !h-5 shrink-0"
                />
              ) : item.icon ? (
                <item.icon className="w-4 h-4 text-muted-foreground shrink-0" />
              ) : (
                <Sparkles className="w-4 h-4 text-muted-foreground shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium truncate">{item.name}</div>
                {item.description && (
                  <div className="text-[11px] text-muted-foreground truncate">
                    {item.description}
                  </div>
                )}
              </div>
              {item.meta && (
                <span className="text-[10px] text-muted-foreground shrink-0">{item.meta}</span>
              )}
            </button>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-1.5 border-t border-border/40 text-[10px] text-muted-foreground flex items-center gap-3">
        <span>{t("mention.footer.navigate")}</span>
        <span>{t("mention.footer.switchTab")}</span>
        <span>{t("mention.footer.select")}</span>
        <span>{t("mention.footer.close")}</span>
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────

function buildItems(
  tab: TabId,
  workspaceFiles: { id: string; name: string; path?: string; kind?: string }[],
  experts: Expert[],
  query: string,
): MentionItem[] {
  const q = query.toLowerCase();

  switch (tab) {
    case "files":
      return workspaceFiles
        .filter((f) => f.name.toLowerCase().includes(q) || (f.path?.toLowerCase().includes(q) ?? false))
        .slice(0, 20)
        .map((f) => {
          // 副标题显示文件路径(去掉首部 "/", 根目录文件路径===文件名时回退来源标签)
          const path = f.path?.replace(/^\/+/, "");
          return {
            id: f.id,
            name: f.name,
            description:
              path && path !== f.name
                ? path
                : f.kind === "ai"
                  ? i18n.t("mention.file.aiGenerated", { ns: "chatUi" })
                  : i18n.t("mention.file.userUploaded", { ns: "chatUi" }),
            icon: FileText,
            type: "file" as const,
          };
        });

    case "experts":
      return experts
        .filter((e) => e.name.toLowerCase().includes(q) || e.description.toLowerCase().includes(q))
        .map((e) => ({
          id: e.id,
          name: e.name,
          description: e.description,
          expertEmoji: e.icon,
          expertHue: getCategoryHue(e.category),
          type: "expert" as const,
        }));

    case "recent": {
      // Load from localStorage (mirrors Vue ResourceMention pattern)
      try {
        const raw = localStorage.getItem("recent-mentions");
        if (!raw) return [];
        const recent: Array<{ id: string; name: string; type: string; ts: number }> =
          JSON.parse(raw);
        return recent
          .filter((r) => r.name.toLowerCase().includes(q))
          .slice(0, 15)
          .map((r) => {
            // Look up expert for icon if this was an expert mention
            const expert = experts.find((e) => e.id === r.id || e.name === r.name);
            // 文件类最近引用: id 即路径, 副标题显示路径(与"文件"tab 一致)
            const recentPath =
              !expert && r.type === "file" ? r.id.replace(/^\/+/, "") : "";
            return {
              id: r.id,
              name: r.name,
              meta: formatTimeAgo(r.ts),
              type: "recent" as const,
              ...(expert
                ? {
                    expertEmoji: expert.icon,
                    expertHue: getCategoryHue(expert.category),
                    description: expert.description,
                  }
                : {
                    icon: FileText,
                    ...(recentPath && recentPath !== r.name ? { description: recentPath } : {}),
                  }),
            };
          });
      } catch {
        return [];
      }
    }
  }
}

function formatTimeAgo(ts: number): string {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return i18n.t("mention.time.justNow", { ns: "chatUi" });
  if (mins < 60) return i18n.t("mention.time.minutesAgo", { ns: "chatUi", count: mins });
  const hours = Math.floor(mins / 60);
  if (hours < 24) return i18n.t("mention.time.hoursAgo", { ns: "chatUi", count: hours });
  const days = Math.floor(hours / 24);
  return i18n.t("mention.time.daysAgo", { ns: "chatUi", count: days });
}

// ── Utility: save recent mention to localStorage ──────────────────

export function saveRecentMention(id: string, name: string, type: string) {
  try {
    const raw = localStorage.getItem("recent-mentions");
    const recent: Array<{ id: string; name: string; type: string; ts: number }> = raw
      ? JSON.parse(raw)
      : [];
    // Remove duplicate
    const filtered = recent.filter((r) => !(r.id === id && r.type === type));
    // Add to front
    filtered.unshift({ id, name, type, ts: Date.now() });
    // Keep max 50, max 7 days
    const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
    const trimmed = filtered.filter((r) => r.ts > cutoff).slice(0, 50);
    localStorage.setItem("recent-mentions", JSON.stringify(trimmed));
  } catch {
    // Silently fail — localStorage not available
  }
}
