/**
 * TraceWaterfall — 瀑布图/甘特图展示 Agent 执行 Tracing。
 * 从 agent-store 的 workspaceTraceSpans 读取数据。
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAgentStore } from "@/lib/agent-store";
import type { TraceSpan } from "@/lib/types/agents";
import {
  Clock,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Check,
  Loader2,
  GanttChart,
} from "lucide-react";

interface Props {
  workspaceId: string;
}

// ── Phase color map ─────────────────────────────────────────────────
const PHASE_COLORS: Record<string, { bar: string; bg: string; text: string }> = {
  plan: {
    bar: "bg-blue-500",
    bg: "bg-blue-50 dark:bg-blue-950/30",
    text: "text-blue-700 dark:text-blue-300",
  },
  do: {
    bar: "bg-emerald-500",
    bg: "bg-emerald-50 dark:bg-emerald-950/30",
    text: "text-emerald-700 dark:text-emerald-300",
  },
  check: {
    bar: "bg-amber-500",
    bg: "bg-amber-50 dark:bg-amber-950/30",
    text: "text-amber-700 dark:text-amber-300",
  },
  act: {
    bar: "bg-purple-500",
    bg: "bg-purple-50 dark:bg-purple-950/30",
    text: "text-purple-700 dark:text-purple-300",
  },
  tool_call: {
    bar: "bg-cyan-500",
    bg: "bg-cyan-50 dark:bg-cyan-950/30",
    text: "text-cyan-700 dark:text-cyan-300",
  },
  llm_call: {
    bar: "bg-indigo-500",
    bg: "bg-indigo-50 dark:bg-indigo-950/30",
    text: "text-indigo-700 dark:text-indigo-300",
  },
  orchestrator: {
    bar: "bg-sky-500",
    bg: "bg-sky-50 dark:bg-sky-950/30",
    text: "text-sky-700 dark:text-sky-300",
  },
};
const DEFAULT_COLOR = {
  bar: "bg-slate-400",
  bg: "bg-slate-50 dark:bg-slate-800/30",
  text: "text-slate-600 dark:text-slate-300",
};

function phaseColor(span: TraceSpan) {
  // Check phase first
  if (span.phase && PHASE_COLORS[span.phase]) return PHASE_COLORS[span.phase];
  // Check span_name for keyword
  const n = span.span_name.toLowerCase();
  if (n.includes("tool_call") || n.includes("tool_")) return PHASE_COLORS["tool_call"];
  if (n.includes("llm") || n.includes("api_call")) return PHASE_COLORS["llm_call"];
  for (const [k, v] of Object.entries(PHASE_COLORS)) {
    if (n.includes(k)) return v;
  }
  return DEFAULT_COLOR;
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ── Build tree from flat spans ──────────────────────────────────────
interface SpanNode {
  span: TraceSpan;
  children: SpanNode[];
}

function buildTree(spans: TraceSpan[]): SpanNode[] {
  const map = new Map<string, SpanNode>();
  const roots: SpanNode[] = [];

  // Sort by start_time
  const sorted = [...spans].sort(
    (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime(),
  );

  for (const s of sorted) {
    const node: SpanNode = { span: s, children: [] };
    map.set(s.span_id, node);

    if (s.parent_span_id && map.has(s.parent_span_id)) {
      map.get(s.parent_span_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

// ── Flat list for waterfall display ─────────────────────────────────
interface WaterfallItem {
  span: TraceSpan;
  depth: number;
  hasChildren: boolean;
}

function flattenTree(nodes: SpanNode[], depth = 0): WaterfallItem[] {
  const result: WaterfallItem[] = [];
  for (const n of nodes) {
    result.push({ span: n.span, depth, hasChildren: n.children.length > 0 });
    result.push(...flattenTree(n.children, depth + 1));
  }
  return result;
}

// Stable empty array to avoid re-renders when no spans exist
const EMPTY_SPANS: TraceSpan[] = [];

// ── Sub-component: single waterfall row ─────────────────────────────
function WaterfallRow({
  item,
  globalStart,
  totalDuration,
}: {
  item: WaterfallItem;
  globalStart: number;
  totalDuration: number;
}) {
  const { t } = useTranslation("monitoring");
  const [expanded, setExpanded] = useState(false);
  const { span, depth, hasChildren } = item;
  const colors = phaseColor(span);
  const startMs = new Date(span.start_time).getTime();
  const endMs = span.end_time ? new Date(span.end_time).getTime() : Date.now();
  const durMs = span.duration_ms ?? endMs - startMs;

  // Position bar relative to global timeline
  const leftPct = totalDuration > 0 ? ((startMs - globalStart) / totalDuration) * 100 : 0;
  const widthPct = totalDuration > 0 ? Math.max((durMs / totalDuration) * 100, 1) : 1;

  const StatusIcon =
    span.status === "error" ? AlertTriangle : span.status === "running" ? Loader2 : Check;

  return (
    <>
      <div
        className={`group flex items-center gap-1 px-3 py-1.5 border-b border-border/40 text-xs hover:bg-muted/40 transition cursor-pointer ${colors.bg}`}
        onClick={() => hasChildren && setExpanded(!expanded)}
        style={{ paddingLeft: `${12 + depth * 20}px` }}
      >
        {/* Expand toggle */}
        <span className="w-3.5 h-3.5 shrink-0 flex items-center justify-center">
          {hasChildren ? (
            expanded ? (
              <ChevronDown className="w-3 h-3 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-3 h-3 text-muted-foreground" />
            )
          ) : (
            <span className="w-3 h-3" />
          )}
        </span>

        {/* Status icon */}
        <StatusIcon
          className={`w-3 h-3 shrink-0 ${
            span.status === "error"
              ? "text-red-500"
              : span.status === "running"
                ? "text-blue-500 animate-spin"
                : "text-emerald-500"
          }`}
        />

        {/* Span name */}
        <span className={`font-medium truncate ${colors.text}`}>
          {span.span_name}
          {span.phase && <span className="ml-1 text-[10px] opacity-60">[{span.phase}]</span>}
        </span>

        {/* Duration */}
        <span className="text-[10px] text-muted-foreground ml-auto shrink-0 w-14 text-right tabular-nums">
          {durMs > 0 ? formatMs(durMs) : "—"}
        </span>

        {/* Waterfall bar (mini) */}
        <div className="relative w-20 h-1.5 rounded-full bg-muted shrink-0 ml-1">
          <div
            className={`absolute top-0 h-full rounded-full ${colors.bar}`}
            style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
          />
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div
          className="px-3 py-2 border-b border-border/30 bg-muted/20 text-[11px] text-muted-foreground space-y-1"
          style={{ paddingLeft: `${24 + depth * 20}px` }}
        >
          {span.span_id && (
            <div className="flex gap-2">
              <span className="text-muted-foreground/60 w-12 shrink-0">Span ID:</span>
              <span className="font-mono text-[10px]">{span.span_id.slice(0, 8)}…</span>
            </div>
          )}
          {span.start_time && (
            <div className="flex gap-2">
              <span className="text-muted-foreground/60 w-12 shrink-0">{t("trace.start")}</span>
              <span>{new Date(span.start_time).toLocaleTimeString()}</span>
            </div>
          )}
          {span.end_time && (
            <div className="flex gap-2">
              <span className="text-muted-foreground/60 w-12 shrink-0">{t("trace.end")}</span>
              <span>{new Date(span.end_time).toLocaleTimeString()}</span>
            </div>
          )}
          {span.input_summary && (
            <div className="flex gap-2">
              <span className="text-muted-foreground/60 w-12 shrink-0">{t("trace.input")}</span>
              <span className="truncate max-w-lg">{span.input_summary}</span>
            </div>
          )}
          {span.output_summary && (
            <div className="flex gap-2">
              <span className="text-muted-foreground/60 w-12 shrink-0">{t("trace.output")}</span>
              <span className="truncate max-w-lg">{span.output_summary}</span>
            </div>
          )}
        </div>
      )}
    </>
  );
}

// ── Main component ───────────────────────────────────────────────────
export function TraceWaterfall({ workspaceId }: Props) {
  const { t } = useTranslation("monitoring");
  // Use a stable selector — only re-render when the actual spans array reference changes
  const rawSpans = useAgentStore((s) => s.workspaceTraceSpans[workspaceId]);
  const spans = rawSpans ?? EMPTY_SPANS;

  const { items, globalStart, totalDuration, stats } = useMemo(() => {
    if (spans.length === 0) {
      return { items: [], globalStart: 0, totalDuration: 0, stats: null };
    }

    const tree = buildTree(spans);
    const items = flattenTree(tree);
    const startTimes = spans.map((s) => new Date(s.start_time).getTime());
    const globalStart = Math.min(...startTimes);
    const endTimes = spans.filter((s) => s.end_time).map((s) => new Date(s.end_time!).getTime());
    const globalEnd = endTimes.length > 0 ? Math.max(...endTimes) : Date.now();
    const totalDuration = globalEnd - globalStart;

    const completed = spans.filter((s) => s.status === "success").length;
    const errors = spans.filter((s) => s.status === "error").length;
    const running = spans.filter((s) => s.status === "running").length;

    return {
      items,
      globalStart,
      totalDuration,
      stats: { total: spans.length, completed, errors, running },
    };
  }, [spans]);

  if (spans.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
        <GanttChart className="w-8 h-8 opacity-30" />
        <p className="text-sm">{t("trace.empty")}</p>
        <p className="text-xs opacity-60">{t("trace.emptyHint")}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Stats bar */}
      {stats && (
        <div className="flex items-center gap-4 px-4 py-2 border-b border-border/60 bg-muted/30 text-xs shrink-0">
          <div className="flex items-center gap-1">
            <GanttChart className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">{stats.total} Spans</span>
          </div>
          <div className="flex items-center gap-1">
            <Check className="w-3 h-3 text-emerald-500" />
            <span className="text-emerald-600 dark:text-emerald-400">{stats.completed}</span>
          </div>
          {stats.running > 0 && (
            <div className="flex items-center gap-1">
              <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />
              <span className="text-blue-600 dark:text-blue-400">{stats.running}</span>
            </div>
          )}
          {stats.errors > 0 && (
            <div className="flex items-center gap-1">
              <AlertTriangle className="w-3 h-3 text-red-500" />
              <span className="text-red-600 dark:text-red-400">{stats.errors}</span>
            </div>
          )}
          {totalDuration > 0 && (
            <div className="flex items-center gap-1 ml-auto">
              <Clock className="w-3 h-3 text-muted-foreground" />
              <span className="text-muted-foreground tabular-nums">{formatMs(totalDuration)}</span>
            </div>
          )}
        </div>
      )}

      {/* Waterfall list */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {items.map((item) => (
          <WaterfallRow
            key={item.span.span_id}
            item={item}
            globalStart={globalStart}
            totalDuration={totalDuration}
          />
        ))}
        {/* Timeline legend */}
        <div className="px-4 py-3 border-t border-border/40 flex items-center gap-3 flex-wrap text-[10px] text-muted-foreground">
          <span className="text-muted-foreground/60">{t("trace.legend")}</span>
          {Object.entries(PHASE_COLORS).map(([phase, c]) => (
            <span key={phase} className="inline-flex items-center gap-1">
              <span className={`w-2.5 h-2.5 rounded-sm ${c.bar}`} />
              {phase}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
