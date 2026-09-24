/**
 * Chat message component with ContentBlock rendering.
 * Mirrors legalbot/webui Message.vue block separation pattern:
 *   - reasoning blocks: rendered above the main bubble
 *   - tool_execution blocks: rendered between reasoning and main bubble
 *   - simple_text blocks: rendered without bubble wrapper
 *   - other blocks (text, tool_call, tool_result, error, etc.): inside main bubble
 */
import { dateLocale } from "@/lib/date-locale";
import { memo, useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ChatMessage as ChatMessageModel, ContentBlock } from "@/lib/types";
import { getExpert, toExperts } from "@/lib/experts";
import { useMarketTeamsStore } from "@/lib/market-teams-store";
import { ExpertIcon, getCategoryHue } from "@/components/expert-icon";
import { User, Bot, Loader2, ListChecks, Layers, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  TextContent,
  ThinkingContent,
  ReasoningContent,
  ToolCallContent,
  ToolResultContent,
  ErrorContent,
} from "./content";
import { renderMarkdown } from "./content/markdown";
import { renderTextWithMentions } from "./content/mention-text";
import { MessageActions } from "./message-actions";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { DisplayMode } from "@/lib/chat-store";
import type { SubtaskBatchCardContentBlock, SubtaskCardContentBlock } from "@/lib/types";
import type { SubtaskStatus } from "@/lib/types/subtask";
import { findSubtaskNode, findSubtaskWorkspace, toSubtaskStatus } from "@/lib/subtask-card";
import { parseSubtaskReport, type SubtaskReport } from "@/lib/subtask-report";
import { useSubtaskStore } from "@/lib/subtask-store";
import { wsClient } from "@/lib/ws-client";

// ── Content block dispatcher ──────────────────────────────────────

function ContentBlockRenderer({
  block,
  isStreaming,
  reasoningDefaultOpen,
  subtaskBatchDefaultOpen,
  messageRendererExt,
}: {
  block: ContentBlock;
  isStreaming?: boolean;
  reasoningDefaultOpen?: boolean;
  /** C21 渲染分档：detailed 模式下批量进度卡默认展开 */
  subtaskBatchDefaultOpen?: boolean;
  /** E3: Custom message renderer extension — if a custom render is returned, use it instead of the default */
  messageRendererExt?: (block: ContentBlock) => ReactNode | null;
}) {
  // E3: Check for custom extension renderer
  if (messageRendererExt) {
    const custom = messageRendererExt(block);
    if (custom !== null) return custom;
  }

  switch (block.type) {
    case "text":
      return <TextContent block={block} isStreaming={isStreaming} />;
    case "thinking":
      return <ThinkingContent block={block} />;
    case "reasoning":
      return <ReasoningContent block={block} defaultOpen={reasoningDefaultOpen} />;
    case "tool_call":
      return <ToolCallContent block={block} />;
    case "tool_result":
      return <ToolResultContent block={block} />;
    case "error":
      return <ErrorContent block={block} />;
    case "simple_text":
      return <div className="text-sm text-muted-foreground">{block.text}</div>;
    case "image":
      return (
        <div className="my-1">
          <img
            src={block.image}
            alt={block.filename ?? "image"}
            className="max-w-full rounded-lg border border-border"
          />
        </div>
      );
    case "tool_execution":
      return <ToolExecutionBlock block={block} />;
    case "subtask_card":
      return <SubtaskCardBlock block={block} />;
    case "subtask_batch_card":
      return <SubtaskBatchCardBlock block={block} defaultOpen={subtaskBatchDefaultOpen} />;
    case "system_command_result":
      return <SystemCommandBlock block={block} />;
    // audio, video, file — placeholder
    default:
      return (
        <div className="text-xs text-muted-foreground bg-muted/30 rounded p-2">
          [{block.type}] (rendering not yet implemented)
        </div>
      );
  }
}

// ── Tool Execution Block (standalone, outside bubble) ─────────────

import type { ToolExecutionContentBlock, SystemCommandResultContentBlock } from "@/lib/types";
import { CheckCircle2, XCircle, Terminal, Circle, Ban, MessageSquare } from "lucide-react";

function ToolExecutionBlock({ block }: { block: ToolExecutionContentBlock }) {
  const { t } = useTranslation("chatUi");
  const statusIcon =
    block.status === "completed" ? (
      <CheckCircle2 className="w-3 h-3 text-green-500" />
    ) : block.status === "failed" ? (
      <XCircle className="w-3 h-3 text-red-500" />
    ) : (
      <Loader2 className="w-3 h-3 animate-spin text-yellow-500" />
    );

  const statusLabel: Record<ToolExecutionContentBlock["status"], string> = {
    started: t("message.exec.status.started"),
    validating: t("message.exec.status.validating"),
    executing: t("message.exec.status.executing"),
    completed: t("message.exec.status.completed"),
    failed: t("message.exec.status.failed"),
    timeout: t("message.exec.status.timeout"),
  };

  return (
    <div className="rounded-lg bg-muted/20 border border-border/50 px-3 py-2 my-1 text-xs">
      <div className="flex items-center gap-2">
        {statusIcon}
        <span className="font-medium">{block.toolName}</span>
        <span className="text-[10px] text-muted-foreground">{statusLabel[block.status]}</span>
        {block.executionTime != null && (
          <span className="text-[10px] text-muted-foreground ml-auto">
            {(block.executionTime / 1000).toFixed(1)}s
          </span>
        )}
      </div>
      {block.progressPercentage != null && (
        <div className="mt-1.5 h-1 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-brand rounded-full transition-all"
            style={{ width: `${block.progressPercentage}%` }}
          />
        </div>
      )}
      {block.currentStep && (
        <div className="text-[10px] text-muted-foreground mt-1">{block.currentStep}</div>
      )}
    </div>
  );
}

// ── Subtask Card Block (UI-B 子任务卡片, §6.3) ──────────────────────

const SUBTASK_STATUS_ICONS: Record<SubtaskStatus, React.ReactNode> = {
  pending: <Circle className="w-3 h-3 text-gray-400" />,
  running: <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />,
  completed: <CheckCircle2 className="w-3 h-3 text-green-500" />,
  failed: <XCircle className="w-3 h-3 text-red-500" />,
  aborted: <Ban className="w-3 h-3 text-gray-400" />,
};

const SUBTASK_STATUS_COLORS: Record<SubtaskStatus, string> = {
  pending: "border-gray-300 bg-gray-50",
  running: "border-blue-300 bg-blue-50",
  completed: "border-green-300 bg-green-50",
  failed: "border-red-300 bg-red-50",
  aborted: "border-gray-200 bg-gray-50",
};

const SUBTASK_STATUS_LABEL_KEYS: Record<SubtaskStatus, string> = {
  pending: "message.subtask.status.pending",
  running: "message.subtask.status.running",
  completed: "message.subtask.status.completed",
  failed: "message.subtask.status.failed",
  aborted: "message.subtask.status.aborted",
};

function SubtaskCardBlock({ block }: { block: SubtaskCardContentBlock }) {
  const { t } = useTranslation("chatUi");
  // 实时状态联动 UI-A 树面板（同源 subtask-store；无实时节点时回落结果快照）
  const live = useSubtaskStore((s) => findSubtaskNode(s.workspaceSubtasks, block.subtaskId));
  const wsId = useSubtaskStore((s) => findSubtaskWorkspace(s.workspaceSubtasks, block.subtaskId));
  const openThread = useSubtaskStore((s) => s.openThread);
  const status: SubtaskStatus =
    live?.status ?? toSubtaskStatus(block.initialStatus, block.isError ? "failed" : "pending");
  const delegateLabel =
    block.toolName === "run_task"
      ? t("message.subtask.delegate.blocking")
      : t("message.subtask.delegate.async");
  const description = live?.description || block.message || `#${block.subtaskId.slice(0, 8)}`;
  const conversationId = live?.conversation_id ?? block.conversationId;
  const steerCount = live?.steerMessages.length ?? 0;

  // 打开 UI-C 线程抽屉：归属工作区取实时桶 > 当前 WS 连接工作区
  const openThreadForCard = () => {
    const target = wsId ?? wsClient.getWorkspaceId();
    if (target) openThread(target, block.subtaskId);
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={openThreadForCard}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") openThreadForCard();
      }}
      title={t("message.subtask.viewThread")}
      className={cn(
        "rounded-lg border px-3 py-2 my-1 text-xs cursor-pointer transition-shadow hover:shadow-sm",
        SUBTASK_STATUS_COLORS[status],
      )}
    >
      <div className="flex items-center gap-2">
        {SUBTASK_STATUS_ICONS[status]}
        <span className="font-medium">{t("message.subtask.title")}</span>
        <span className="text-[10px] text-muted-foreground">{delegateLabel}</span>
        <span className="text-[10px] text-muted-foreground">
          {t(SUBTASK_STATUS_LABEL_KEYS[status])}
        </span>
        {block.agent && (
          <Badge variant="outline" className="text-[10px] h-4 px-1.5">
            {block.agent}
          </Badge>
        )}
        {block.executionTime != null && (
          <span className="text-[10px] text-muted-foreground ml-auto">
            {(block.executionTime / 1000).toFixed(1)}s
          </span>
        )}
      </div>
      <div className="text-[11px] mt-1 truncate text-foreground/80">{description}</div>
      <div className="flex items-center gap-2 text-[10px] text-muted-foreground mt-0.5">
        {conversationId && (
          <span className="inline-flex items-center gap-0.5">
            <MessageSquare className="w-3 h-3" />
            {t("message.subtask.standaloneSession")}
          </span>
        )}
        {steerCount > 0 && <span>steer ×{steerCount}</span>}
        <span className="ml-auto font-mono">{block.subtaskId.slice(0, 8)}…</span>
      </div>
    </div>
  );
}

// ── Subtask Batch Card（C21/§3.8.1 批量进度卡：Collapsible 总览 + 逐项行）──

/** 行内 todo 步级字符进度条：▓▓▓░░ 3/5（+ 当前步文案，C25 数据） */
function batchTodoStepText(todos: { total: number; completed: number; current?: string }): string {
  const width = 5;
  const total = Math.max(todos.total, 1);
  const filled = Math.min(Math.round((todos.completed / total) * width), width);
  const bar = "▓".repeat(filled) + "░".repeat(width - filled);
  const cur = todos.current ? ` · ${todos.current}` : "";
  return `${bar} ${todos.completed}/${todos.total}${cur}`;
}

function SubtaskBatchCardBlock({
  block,
  defaultOpen,
}: {
  block: SubtaskBatchCardContentBlock;
  defaultOpen?: boolean;
}) {
  const { t } = useTranslation("chatUi");
  const [open, setOpen] = useState(Boolean(defaultOpen));
  // 实时状态联动 subtask-store（同 subtask_card；无实时节点时回落 pending 快照）
  const buckets = useSubtaskStore((s) => s.workspaceSubtasks);
  const openThread = useSubtaskStore((s) => s.openThread);

  const items = block.itemIds.map((id, i) => {
    const live = findSubtaskNode(buckets, id);
    return {
      id,
      identity: live?.itemIdentity ?? block.itemIdentities[i] ?? id.slice(0, 8),
      status: (live?.status ?? "pending") as SubtaskStatus,
      todos: live?.todos ?? null,
    };
  });
  const terminal = (s: SubtaskStatus) => s === "completed" || s === "failed" || s === "aborted";
  const done = items.filter((it) => terminal(it.status)).length;
  const failed = items.filter((it) => it.status === "failed" || it.status === "aborted").length;
  const allDone = done === items.length && items.length > 0;

  const openThreadForItem = (id: string) => {
    const target = findSubtaskWorkspace(buckets, id) ?? wsClient.getWorkspaceId();
    if (target) openThread(target, id);
  };

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div
        className={cn(
          "rounded-lg border px-3 py-2 my-1 text-xs",
          failed > 0 ? "border-red-200 bg-red-50/50" : "border-border bg-muted/20",
        )}
      >
        {/* 头部总览一行：标题 + 进度条 + done/total + 失败数（耗时无可靠后端时钟源，不展示） */}
        <CollapsibleTrigger asChild>
          <button type="button" className="flex items-center gap-2 w-full text-left">
            <ChevronRight
              className={cn("w-3 h-3 shrink-0 transition-transform", open && "rotate-90")}
            />
            <Layers className="w-3 h-3 shrink-0 text-brand" />
            <span className="font-medium shrink-0">{t("message.subtaskBatch.title")}</span>
            {block.mode && (
              <Badge variant="outline" className="text-[10px] h-4 px-1.5 shrink-0">
                {block.mode}
              </Badge>
            )}
            <span className="text-[10px] text-muted-foreground shrink-0">
              {t("message.subtaskBatch.count", { count: items.length })}
            </span>
            {/* 手写进度条（仿 tool-call-content.tsx） */}
            <span className="flex-1 min-w-[48px] h-1.5 bg-muted rounded-full overflow-hidden mx-1">
              <span
                className={cn(
                  "block h-full rounded-full transition-all",
                  failed > 0 ? "bg-red-400" : "bg-brand",
                )}
                style={{ width: `${items.length ? (done / items.length) * 100 : 0}%` }}
              />
            </span>
            <span className="text-[10px] text-muted-foreground shrink-0">
              {done}/{items.length}
              {failed > 0 && (
                <span className="text-red-500">
                  {" "}
                  · {t("message.subtaskBatch.failed", { count: failed })}
                </span>
              )}
              {allDone && (
                <span className="text-green-600"> · {t("message.subtaskBatch.allDone")}</span>
              )}
            </span>
          </button>
        </CollapsibleTrigger>

        <CollapsibleContent>
          {/* 逐项行：状态图标 + identity + todo 步级（running 项）；点行 → 线程抽屉（C19） */}
          <div className="divide-y divide-border/40 mt-1">
            {items.map((it, i) => (
              <div
                key={it.id}
                role="button"
                tabIndex={0}
                onClick={() => openThreadForItem(it.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") openThreadForItem(it.id);
                }}
                title={t("message.subtask.viewThread")}
                className="flex items-center gap-2 py-1.5 cursor-pointer hover:bg-muted/40 rounded px-1 -mx-1"
              >
                {SUBTASK_STATUS_ICONS[it.status]}
                <span className="truncate max-w-[45%]" title={it.identity}>
                  {it.identity}
                </span>
                {/* todo 步级（C25：running 项实时；终态项显示定格终步） */}
                {it.todos && (
                  <span className="font-mono text-[10px] text-muted-foreground truncate">
                    {batchTodoStepText(it.todos)}
                  </span>
                )}
                <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
                  {t(SUBTASK_STATUS_LABEL_KEYS[it.status])}
                </span>
                <span className="font-mono text-[10px] text-muted-foreground/60 shrink-0">
                  #{i + 1}
                </span>
              </div>
            ))}
          </div>
          {/* 派发即有未创建项（duplicate/error）→ 提示去看工具结果详情 */}
          {block.createdCount < block.totalItems && (
            <div className="text-[10px] text-amber-600 dark:text-amber-400 pt-1">
              {t("message.subtaskBatch.partial", {
                created: block.createdCount,
                total: block.totalItems,
              })}
            </div>
          )}
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

// ── Subtask Report Card（P2 UI：[子任务执行报告] 结构化卡片）─────────
// 后端 _inject_subtask_summaries 以 UserMessage 纯文本回注报告；此处把
// 报告文本解析为结构化条目渲染卡片，替代右侧用户裸文本气泡。

function SubtaskReportCard({ report }: { report: SubtaskReport }) {
  const { t } = useTranslation("chatUi");

  return (
    <div className="rounded-2xl rounded-br-sm border border-border bg-card inline-block text-left w-full text-[var(--chat-font-size)] overflow-hidden">
      {/* 卡片头 */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border/60 bg-muted/30">
        <ListChecks className="w-4 h-4 text-brand shrink-0" />
        <span className="font-medium">{t("message.subtaskReport.title")}</span>
        <span className="text-[var(--chat-font-size-sm)] text-muted-foreground">
          {t("message.subtaskReport.count", { count: report.entries.length })}
        </span>
      </div>

      {/* 每个子任务条目 */}
      <div className="divide-y divide-border/40">
        {report.entries.map((entry) => (
          <div key={entry.subtaskId} className="px-4 py-2">
            <div className="flex items-center gap-2 flex-wrap">
              {entry.status && (
                <>
                  {SUBTASK_STATUS_ICONS[entry.status]}
                  <span className="text-[var(--chat-font-size-sm)] text-muted-foreground">
                    {t(SUBTASK_STATUS_LABEL_KEYS[entry.status])}
                  </span>
                </>
              )}
              <span className="font-mono text-[var(--chat-font-size-sm)] text-muted-foreground">
                {entry.subtaskId.slice(0, 8)}…
              </span>
              {entry.cost && (
                <span className="text-[var(--chat-font-size-sm)] text-muted-foreground ml-auto">
                  {entry.cost}
                </span>
              )}
            </div>
            {entry.description && (
              <div className="mt-1 text-foreground/90">{entry.description}</div>
            )}
            {entry.acceptance && (
              <div className="mt-1 text-[var(--chat-font-size-sm)] text-amber-600 dark:text-amber-400">
                {t("message.subtaskReport.acceptance")}: {entry.acceptance}
              </div>
            )}
            {entry.result && (
              <pre className="mt-1.5 whitespace-pre-wrap font-mono text-[var(--chat-font-size-sm)] text-muted-foreground max-h-40 overflow-y-auto">
                {entry.result}
              </pre>
            )}
          </div>
        ))}
      </div>

      {/* 判定提示（有验收标准时后端追加） */}
      {report.verdictHint && (
        <div className="px-4 py-2 border-t border-border/60 bg-amber-50/50 dark:bg-amber-950/20 text-[var(--chat-font-size-sm)] whitespace-pre-wrap">
          <span className="font-medium text-amber-700 dark:text-amber-400">
            {t("message.subtaskReport.verdictHint")}:
          </span>{" "}
          {report.verdictHint.replace(/^判定提示:?\s*/, "")}
        </div>
      )}
    </div>
  );
}

function SystemCommandBlock({ block }: { block: SystemCommandResultContentBlock }) {
  return (
    <div className="rounded-lg bg-muted/20 border border-border/50 my-1">
      <div className="flex items-center gap-2 px-3 py-1.5 text-xs border-b border-border/40">
        <Terminal className="w-3 h-3 text-muted-foreground" />
        <code className="text-foreground font-mono">{block.command}</code>
        <span
          className={cn(
            "text-[10px] ml-auto",
            block.exitCode === 0 ? "text-green-600" : "text-red-600",
          )}
        >
          exit {block.exitCode}
        </span>
        {block.executionTime != null && (
          <span className="text-[10px] text-muted-foreground">
            {(block.executionTime / 1000).toFixed(1)}s
          </span>
        )}
      </div>
      {block.stdout && (
        <pre className="px-3 py-2 text-[11px] font-mono max-h-32 overflow-y-auto">
          {block.stdout}
        </pre>
      )}
      {block.stderr && (
        <pre className="px-3 py-2 text-[11px] font-mono text-red-500 border-t border-border/40 max-h-20 overflow-y-auto">
          {block.stderr}
        </pre>
      )}
    </div>
  );
}

// ── Main Message component ────────────────────────────────────────

interface MessageProps {
  message: ChatMessageModel;
  isStreaming?: boolean;
  /** Display mode: controls which block types are visible */
  displayMode?: DisplayMode;
  /** Compact mode — reduced spacing/padding */
  compactMode?: boolean;
  /** Font size for message text content (12–20px, default 14) */
  fontSize?: number;
  /** E3: Custom message renderer extension for IP or other modules */
  messageRendererExt?: (block: ContentBlock) => ReactNode | null;
}

/**
 * Filter blocks based on display mode:
 * - minimal: only text + error blocks
 * - default: reasoning (collapsed), tool_execution, text, error — hide tool_call/tool_result details
 * - detailed: all blocks
 *
 * C21 渲染分档：subtask_batch_card 走 other 桶 —— minimal 隐藏（other 仅
 * text/error），default 折叠仅头部（defaultOpen=false），detailed 展开
 * （subtaskBatchDefaultOpen=true 传入渲染器），与 tool_call 块同款分档。
 */
function filterBlocksByMode(
  blocks: ContentBlock[],
  mode: DisplayMode,
): {
  reasoning: ContentBlock[];
  thinking: ContentBlock[];
  toolExecution: ContentBlock[];
  simpleText: ContentBlock[];
  systemCmd: ContentBlock[];
  other: ContentBlock[];
} {
  if (mode === "minimal") {
    // Minimal: only text and error blocks. Also hide "tool-only" history markers
    // (chat-store.ts emits simple_text blocks tagged with kind="history-tool-marker"
    // to surface intermediate tool-call rounds in default/detailed modes — minimal
    // hides them since they are noise when the user wants a clean transcript).
    // Other simple_text variants (kind="interrupted", kind="attempt_completion",
    // or legacy un-tagged) still show.
    return {
      reasoning: [],
      thinking: [],
      toolExecution: [],
      simpleText: blocks.filter(
        (b) => b.type === "simple_text" && b.kind !== "history-tool-marker",
      ),
      systemCmd: [],
      other: blocks.filter((b) => b.type === "text" || b.type === "error"),
    };
  }

  if (mode === "detailed") {
    // Detailed: show everything
    return {
      reasoning: blocks.filter((b) => b.type === "reasoning"),
      thinking: blocks.filter((b) => b.type === "thinking"),
      toolExecution: blocks.filter((b) => b.type === "tool_execution"),
      simpleText: blocks.filter((b) => b.type === "simple_text"),
      systemCmd: blocks.filter((b) => b.type === "system_command_result"),
      other: blocks.filter(
        (b) =>
          ![
            "reasoning",
            "thinking",
            "tool_execution",
            "simple_text",
            "system_command_result",
          ].includes(b.type),
      ),
    };
  }

  // Default: reasoning (will be collapsed), tool_execution, text, error — hide tool_call/tool_result
  return {
    reasoning: blocks.filter((b) => b.type === "reasoning"),
    thinking: [], // hide structured thinking in default
    toolExecution: blocks.filter((b) => b.type === "tool_execution"),
    simpleText: blocks.filter((b) => b.type === "simple_text"),
    systemCmd: [], // hide system commands in default
    other: blocks.filter(
      (b) =>
        ![
          "reasoning",
          "thinking",
          "tool_execution",
          "simple_text",
          "system_command_result",
          "tool_call",
          "tool_result",
        ].includes(b.type),
    ),
  };
}

function ChatMessageBase({
  message,
  isStreaming,
  displayMode = "default",
  compactMode = false,
  fontSize = 14,
  messageRendererExt,
}: MessageProps) {
  const { t } = useTranslation("chatUi");
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  // Market teams → allExperts for getExpert + mention rendering
  const marketTeams = useMarketTeamsStore((s) => s.teams);
  const fetchTeams = useMarketTeamsStore((s) => s.fetchTeams);
  const allExperts = useMemo(() => toExperts(marketTeams), [marketTeams]);
  useEffect(() => {
    fetchTeams();
  }, [fetchTeams]);

  const expert = message.agentId ? getExpert(allExperts, message.agentId) : undefined;

  // Computed CSS variables for font scaling — main text and secondary labels
  const cm = compactMode;
  const fs = Math.min(20, Math.max(12, fontSize));
  const fsSm = Math.round(fs * 0.8);

  // Categorize blocks — filtered by display mode
  const allBlocks = message.blocks ?? [];
  const hasBlocks = allBlocks.length > 0;
  const {
    reasoning: reasoningBlocks,
    thinking: thinkingBlocks,
    toolExecution: toolExecutionBlocks,
    simpleText: simpleTextBlocks,
    systemCmd: systemCmdBlocks,
    other: otherBlocks,
  } = filterBlocksByMode(allBlocks, displayMode);

  // If no blocks, fall back to legacy content string rendering

  // System messages get a simpler treatment
  if (isSystem) {
    return (
      <div className="flex justify-center px-2">
        <div
          className="text-[var(--chat-font-size-sm)] text-muted-foreground bg-muted/40 rounded-full px-3 py-1"
          style={{ "--chat-font-size-sm": `${fsSm}px` } as React.CSSProperties}
        >
          {message.content}
        </div>
      </div>
    );
  }

  // Agent message whose blocks are all filtered out by the current display mode
  // (e.g. minimal hides reasoning / tool_call / history-tool-marker blocks) has
  // nothing to render — skip the whole row instead of leaving an empty bubble
  // (avatar + "智能体" label with no content). Streaming messages are kept so
  // the "正在思考..." feedback bubble still shows.
  if (!isUser && !isStreaming) {
    const hasVisibleContent =
      reasoningBlocks.length > 0 ||
      thinkingBlocks.length > 0 ||
      toolExecutionBlocks.length > 0 ||
      simpleTextBlocks.length > 0 ||
      systemCmdBlocks.length > 0 ||
      otherBlocks.length > 0 ||
      // legacy fallbacks (no blocks): content string or reasoning-only models
      (!hasBlocks && Boolean(message.content || message.reasoning));
    if (!hasVisibleContent) return null;
  }

  return (
    <div
      className={cn("flex px-2", cm ? "gap-2" : "gap-3", isUser ? "flex-row-reverse" : "flex-row")}
      style={
        {
          "--chat-font-size": `${fs}px`,
          "--chat-font-size-sm": `${fsSm}px`,
        } as React.CSSProperties
      }
    >
      {/* Avatar */}
      <div className={cn("shrink-0", !cm && "mt-1")}>
        {isUser ? (
          <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center">
            <User className="w-4 h-4" />
          </div>
        ) : expert ? (
          <ExpertIcon emoji={expert.icon} hue={getCategoryHue(expert.category)} size="sm" />
        ) : (
          <div className="w-8 h-8 rounded-full bg-gradient-brand flex items-center justify-center">
            <Bot className="w-4 h-4 text-brand-foreground" />
          </div>
        )}
      </div>

      {/* Message body */}
      <div className={cn("group max-w-[85%] min-w-0", isUser && "text-right")}>
        {/* Agent name */}
        {!isUser && (
          <div
            className={cn(
              "text-[var(--chat-font-size-sm)] text-muted-foreground px-1 inline-flex items-center gap-1.5",
              cm ? "mb-0.5" : "mb-1",
            )}
          >
            {message.agentName || t("message.agent.default")}
            {message.ts > 0 && (
              <span className="text-muted-foreground/60">
                {new Date(message.ts).toLocaleTimeString(dateLocale(), {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            )}
            {isStreaming && <Loader2 className="w-3 h-3 animate-spin text-brand" />}
          </div>
        )}

        {/* Reasoning blocks (above bubble) — defaultOpen in detailed mode */}
        {reasoningBlocks.map((block, i) => (
          <ContentBlockRenderer
            key={`reasoning-${i}`}
            block={block}
            reasoningDefaultOpen={displayMode === "detailed"}
            messageRendererExt={messageRendererExt}
          />
        ))}

        {/* Thinking blocks (above bubble) */}
        {thinkingBlocks.map((block, i) => (
          <ContentBlockRenderer
            key={`thinking-${i}`}
            block={block}
            messageRendererExt={messageRendererExt}
          />
        ))}

        {/* Tool execution blocks (between reasoning and main) */}
        {toolExecutionBlocks.map((block, i) => (
          <ContentBlockRenderer
            key={`tool-exec-${i}`}
            block={block}
            messageRendererExt={messageRendererExt}
          />
        ))}

        {/* System command blocks */}
        {systemCmdBlocks.map((block, i) => (
          <ContentBlockRenderer
            key={`sys-cmd-${i}`}
            block={block}
            messageRendererExt={messageRendererExt}
          />
        ))}

        {/* Simple text blocks (no bubble) */}
        {simpleTextBlocks.map((block, i) => (
          <div key={`simple-${i}`} className={cm ? "px-0.5 my-0.5" : "px-1 my-1"}>
            <ContentBlockRenderer block={block} messageRendererExt={messageRendererExt} />
          </div>
        ))}

        {/* Main bubble (other blocks or legacy content) */}
        {(() => {
          if (isUser) {
            // [子任务执行报告] 回注文本（后端 _inject_subtask_summaries）→ 结构化卡片
            const report = parseSubtaskReport(message.content);
            if (report) return <SubtaskReportCard report={report} />;
            return (
              <div
                className={cn(
                  "rounded-2xl inline-block text-left bg-gradient-brand text-brand-foreground rounded-br-sm text-[var(--chat-font-size)]",
                  cm ? "px-3 py-1.5" : "px-4 py-2.5",
                )}
              >
                <p className="whitespace-pre-wrap">
                  {renderTextWithMentions(message.content, undefined, allExperts)}
                </p>
              </div>
            );
          }

          if (!hasBlocks && message.content) {
            // Legacy fallback — render content string as markdown
            return (
              <div
                className={cn(
                  "rounded-2xl bg-card border border-border rounded-bl-sm inline-block text-left text-[var(--chat-font-size)]",
                  cm ? "px-3 py-1.5" : "px-4 py-2.5",
                )}
              >
                <div className="space-y-1">
                  {renderMarkdown(message.content)}
                  {isStreaming && (
                    <span className="inline-block w-1.5 h-4 bg-brand animate-pulse rounded-sm ml-0.5 align-text-bottom" />
                  )}
                </div>
              </div>
            );
          }

          // Reasoning-only models (GLM-4.7, DeepSeek Reasoner) put all text
          // in reasoning_content with empty content deltas. The backend copies
          // reasoning_content to content in CompleteMessage, but as a fallback
          // render message.reasoning when content is missing.
          if (!hasBlocks && !message.content && message.reasoning) {
            return (
              <div
                className={cn(
                  "rounded-2xl bg-card border border-border rounded-bl-sm inline-block text-left text-[var(--chat-font-size)]",
                  cm ? "px-3 py-1.5" : "px-4 py-2.5",
                )}
              >
                <div className="space-y-1">
                  {renderMarkdown(message.reasoning)}
                  {isStreaming && (
                    <span className="inline-block w-1.5 h-4 bg-brand animate-pulse rounded-sm ml-0.5 align-text-bottom" />
                  )}
                </div>
              </div>
            );
          }

          if (otherBlocks.length > 0) {
            return (
              <div
                className={cn(
                  "rounded-2xl bg-card border border-border rounded-bl-sm inline-block text-left text-[var(--chat-font-size)]",
                  cm ? "px-3 py-1.5" : "px-4 py-2.5",
                )}
              >
                {otherBlocks.map((block, i) => (
                  <ContentBlockRenderer
                    key={`other-${i}`}
                    block={block}
                    isStreaming={
                      isStreaming && i === otherBlocks.length - 1 && block.type === "text"
                    }
                    subtaskBatchDefaultOpen={displayMode === "detailed"}
                    messageRendererExt={messageRendererExt}
                  />
                ))}
              </div>
            );
          }

          // Streaming with no content yet
          if (isStreaming && !message.content && otherBlocks.length === 0) {
            return (
              <div
                className={cn(
                  "rounded-2xl bg-card border border-border rounded-bl-sm inline-block text-left",
                  cm ? "px-3 py-1.5" : "px-4 py-2.5",
                )}
              >
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span className="text-xs">{t("message.thinking")}</span>
                </div>
              </div>
            );
          }

          return null;
        })()}

        {/* Per-message actions: copy / export markdown / export PDF.
            触屏无 hover:移动端常显;桌面保留 hover 浮现。 */}
        <div
          className={cn(
            "opacity-100 md:opacity-0 md:group-hover:opacity-100 md:focus-within:opacity-100 transition-opacity duration-150",
            isUser ? "flex justify-end" : "flex justify-start",
          )}
        >
          {isUser && message.ts > 0 && !isStreaming && (
            <span className="text-[var(--chat-font-size-sm)] text-muted-foreground/60 px-1 mr-2 self-center">
              {new Date(message.ts).toLocaleTimeString(dateLocale(), {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          )}
          <MessageActions message={message} align={isUser ? "end" : "start"} />
        </div>
      </div>
    </div>
  );
}

// 流式渲染优化(方案 Phase 3.2):memo 包装后,流式 chunk 触发的消息列表重渲染中
// 只有引用变化的消息真正重渲染 —— chat-store `_flushStreamBuffer` 每次只替换
// 正在流式的那条消息对象,其余 N-1 条 props 引用不变,直接跳过渲染。
export const ChatMessage = memo(ChatMessageBase);
