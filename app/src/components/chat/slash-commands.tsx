/**
 * Slash command picker — shown when user types '/' at the start of input.
 * Search, keyboard nav (up/down/enter/esc), click to select.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  Search,
  FileText,
  Zap,
  Settings,
  Trash2,
  RotateCcw,
  HelpCircle,
  MessageSquare,
  Bot,
  BookOpen,
  Library,
  ClipboardList,
  Repeat,
  Glasses,
  Microscope,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import i18n from "@/lib/i18n";

function tr(key: string): string {
  return i18n.t(key, { ns: "chatUi" });
}

// ── Command definition ────────────────────────────────────────────

export interface SlashCommand {
  id: string;
  name: string;
  description: string;
  icon?: LucideIcon;
  tag?: string; // e.g. "常用", "系统"
}

// Built-in commands for the legal chat UI (built lazily so translations resolve at call time)
export function getDefaultCommands(): SlashCommand[] {
  return [
    {
      id: "clear",
      name: "/clear",
      description: tr("slash.cmd.clear"),
      icon: Trash2,
      tag: tr("slash.tag.system"),
    },
    {
      id: "reset",
      name: "/reset",
      description: tr("slash.cmd.reset"),
      icon: RotateCcw,
      tag: tr("slash.tag.system"),
    },
    {
      id: "help",
      name: "/help",
      description: tr("slash.cmd.help"),
      icon: HelpCircle,
      tag: tr("slash.tag.system"),
    },
    {
      id: "expert",
      name: "/expert",
      description: tr("slash.cmd.expert"),
      icon: Bot,
      tag: tr("slash.tag.chat"),
    },
    {
      id: "model",
      name: "/model",
      description: tr("slash.cmd.model"),
      icon: Settings,
      tag: tr("slash.tag.settings"),
    },
    {
      id: "summarize",
      name: "/summarize",
      description: tr("slash.cmd.summarize"),
      icon: FileText,
      tag: tr("slash.tag.chat"),
    },
    {
      id: "analyze",
      name: "/analyze",
      description: tr("slash.cmd.analyze"),
      icon: BookOpen,
      tag: tr("slash.tag.analysis"),
    },
    {
      id: "task",
      name: "/task",
      description: tr("slash.cmd.task"),
      icon: Zap,
      tag: tr("slash.tag.advanced"),
    },
    {
      id: "chat",
      name: "/chat",
      description: tr("slash.cmd.chat"),
      icon: MessageSquare,
      tag: tr("slash.tag.chat"),
    },
    // ── gelu-research pipeline commands (PRD §6.4.2) ──
    {
      id: "review-run",
      name: "/review run",
      description: tr("slash.cmd.review.run"),
      icon: Library,
      tag: tr("slash.tag.research"),
    },
    {
      id: "paper-status",
      name: "/paper status",
      description: tr("slash.cmd.paper.status"),
      icon: ClipboardList,
      tag: tr("slash.tag.research"),
    },
    {
      id: "paper-switch",
      name: "/paper switch <stage>",
      description: tr("slash.cmd.paper.switch"),
      icon: Repeat,
      tag: tr("slash.tag.research"),
    },
    {
      id: "lens-run",
      name: "/lens run <pdf>",
      description: tr("slash.cmd.lens.run"),
      icon: Glasses,
      tag: tr("slash.tag.research"),
    },
    {
      id: "lens-critique",
      name: "/lens critique <pdf>",
      description: tr("slash.cmd.lens.critique"),
      icon: Microscope,
      tag: tr("slash.tag.research"),
    },
  ];
}

// ── Component ─────────────────────────────────────────────────────

interface Props {
  visible: boolean;
  commands?: SlashCommand[];
  onSelect: (command: SlashCommand) => void;
  onClose: () => void;
}

export function SlashCommands({
  visible,
  commands = getDefaultCommands(),
  onSelect,
  onClose,
}: Props) {
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const { t } = useTranslation("chatUi");
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Filter commands by query (after the leading /)
  const filtered = commands.filter(
    (c) =>
      c.name.toLowerCase().includes(query.toLowerCase()) ||
      c.description.toLowerCase().includes(query.toLowerCase()),
  );

  // Reset on open/close
  useEffect(() => {
    if (visible) {
      setQuery("");
      setActiveIdx(0);
      // Focus search input after mount
      requestAnimationFrame(() => searchRef.current?.focus());
    }
  }, [visible]);

  // Scroll active item into view
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
          setActiveIdx((i) => Math.min(filtered.length - 1, i + 1));
          break;
        case "Enter":
          e.preventDefault();
          if (filtered[activeIdx]) {
            onSelect(filtered[activeIdx]);
          }
          break;
        case "Escape":
          e.preventDefault();
          onClose();
          break;
      }
    },
    [filtered, activeIdx, onSelect, onClose],
  );

  if (!visible) return null;

  return (
    <div
      className="absolute bottom-full left-0 right-0 mb-1 z-50 rounded-xl border border-border bg-card/95 backdrop-blur-md shadow-lg overflow-hidden"
      onKeyDown={handleKeyDown}
    >
      {/* Header + search */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/60">
        <Search className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        <input
          ref={searchRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIdx(0);
          }}
          placeholder={t("slash.searchPlaceholder")}
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
        <span className="text-[10px] text-muted-foreground shrink-0">
          {t("slash.count", { count: filtered.length })}
        </span>
      </div>

      {/* Command list */}
      <div ref={listRef} className="max-h-56 overflow-y-auto py-1">
        {filtered.length === 0 ? (
          <div className="px-3 py-6 text-center text-sm text-muted-foreground">
            {t("slash.noMatch")}
          </div>
        ) : (
          filtered.map((cmd, i) => {
            const Icon = cmd.icon;
            return (
              <button
                key={cmd.id}
                onClick={() => onSelect(cmd)}
                onMouseEnter={() => setActiveIdx(i)}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2 text-left transition-colors",
                  i === activeIdx ? "bg-accent/60" : "hover:bg-accent/30",
                )}
              >
                {Icon ? (
                  <Icon className="w-4 h-4 text-muted-foreground shrink-0" />
                ) : (
                  <div className="w-4 h-4 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{cmd.name}</div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {cmd.description}
                  </div>
                </div>
                {cmd.tag && (
                  <span className="text-[10px] text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded shrink-0">
                    {cmd.tag}
                  </span>
                )}
              </button>
            );
          })
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-1.5 border-t border-border/40 text-[10px] text-muted-foreground flex items-center gap-3">
        <span>{t("slash.footer.navigate")}</span>
        <span>{t("slash.footer.select")}</span>
        <span>{t("slash.footer.close")}</span>
      </div>
    </div>
  );
}
