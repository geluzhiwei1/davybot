"use client";
/**
 * SubtaskThreadDrawer — UI-C 子代理线程抽屉（§6.3）。
 *
 * 打开来源：monitoring 子任务树节点 / chat 子任务卡片（subtask-store.openThread）。
 * 数据流（打开目标变化时拉取）：
 * - REST GET /subtasks/{id}/conversation → 只读消息流（degraded 时按 reason 降级）
 * - REST GET /agents/profiles → 头部 Agent Profile 摘要（UI-E 前置能力）
 *
 * 偏离说明：不挂 AppDrawer（其 activeDrawer 为全局单选、无上下文目标），
 * 目标态由 subtask-store.threadDrawer 承载，Sheet 标记复用 AppDrawer 布局。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Ban,
  Bot,
  CheckCircle2,
  Circle,
  Loader2,
  MessageSquare,
  RefreshCw,
  Send,
  User,
  Wrench,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { subtaskApi } from "@/lib/api/subtask";
import { useSubtaskStore } from "@/lib/subtask-store";
import {
  availableSubtaskActions,
  describeActionResult,
  extractConversationMessages,
  findAgentProfile,
} from "@/lib/subtask-thread";
import type {
  AgentProfileInfo,
  SubtaskConversationResponse,
  SubtaskStatus,
} from "@/lib/types/subtask";

const STATUS_ICONS: Record<SubtaskStatus, React.ReactNode> = {
  pending: <Circle className="w-4 h-4 text-gray-400" />,
  running: <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />,
  completed: <CheckCircle2 className="w-4 h-4 text-green-500" />,
  failed: <XCircle className="w-4 h-4 text-red-500" />,
  aborted: <Ban className="w-4 h-4 text-gray-400" />,
};

const STATUS_LABEL_KEYS: Record<SubtaskStatus, string> = {
  pending: "subtask.status.pending",
  running: "subtask.status.running",
  completed: "subtask.status.completed",
  failed: "subtask.status.failed",
  aborted: "subtask.status.aborted",
};

const ROLE_LABEL_KEYS: Record<string, string> = {
  user: "subtask.role.user",
  assistant: "subtask.role.assistant",
  system: "subtask.role.system",
  tool: "subtask.role.tool",
};

const ROLE_STYLES: Record<string, string> = {
  user: "ml-10 bg-primary/10 border-primary/20",
  assistant: "mr-10 bg-muted/40 border-border/60",
  system: "mx-4 bg-muted/20 border-dashed border-border/60 font-mono",
  tool: "mr-10 bg-muted/20 border-border/40 font-mono",
};

export function SubtaskThreadDrawer() {
  const { t } = useTranslation("drawersUi");
  const target = useSubtaskStore((s) => s.threadDrawer);
  const closeThread = useSubtaskStore((s) => s.closeThread);
  const open = target != null;
  const wsId = target?.workspaceId ?? null;
  const taskNodeId = target?.taskNodeId ?? null;

  // 实时节点（WS 驱动；抽屉打开期间状态迁移即时反映）
  const node = useSubtaskStore((s) =>
    s.threadDrawer
      ? (s.workspaceSubtasks[s.threadDrawer.workspaceId]?.[s.threadDrawer.taskNodeId] ?? null)
      : null,
  );

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conv, setConv] = useState<SubtaskConversationResponse | null>(null);
  const [profiles, setProfiles] = useState<AgentProfileInfo[]>([]);
  const [reloadTick, setReloadTick] = useState(0);

  // UI-D steer 输入（抽屉底部）
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const steerInputRef = useRef<HTMLInputElement>(null);

  // focusSteer 入口（树节点 steer 按钮）→ 打开即聚焦输入框
  useEffect(() => {
    if (open && target?.focusSteer) steerInputRef.current?.focus();
  }, [open, target]);

  useEffect(() => {
    if (!wsId || !taskNodeId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setConv(null);

    (async () => {
      try {
        const [convRes, profRes] = await Promise.all([
          subtaskApi.getConversation(wsId, taskNodeId),
          // profiles 失败不阻塞会话渲染（仅头部摘要缺失）
          subtaskApi.getAgentProfiles(wsId).catch(() => null),
        ]);
        if (cancelled) return;
        setConv(convRes);
        setProfiles(profRes?.profiles ?? []);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : t("subtask.error.loadFailed"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [wsId, taskNodeId, reloadTick, t]);

  // 关闭时清空，避免下次打开闪现上一目标内容
  useEffect(() => {
    if (!open) {
      setConv(null);
      setError(null);
      setProfiles([]);
      setLoading(false);
      setDraft("");
    }
  }, [open]);

  // UI-D：发送 steer（RUNNING 注入会话 / PENDING 追加描述 / COMPLETED 续跑）
  const sendSteer = async () => {
    const text = draft.trim();
    if (!text || !wsId || !taskNodeId || sending) return;
    setSending(true);
    try {
      const res = await subtaskApi.steer(wsId, taskNodeId, text);
      if (res.success) {
        toast.success(describeActionResult("steer", res));
        setDraft("");
        setReloadTick((t) => t + 1); // 拉新会话以显示 [steer] 消息
      } else {
        toast.error(describeActionResult("steer", res));
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("subtask.toast.steerFailed"));
    } finally {
      setSending(false);
    }
  };

  const thread = useMemo(() => extractConversationMessages(conv?.conversation ?? null), [conv]);
  const profile = useMemo(() => findAgentProfile(profiles, node?.agent), [profiles, node?.agent]);
  const status = node?.status ?? null;
  const title =
    node?.description || t("subtask.title.fallback", { id: (taskNodeId ?? "").slice(0, 8) });

  return (
    <Sheet open={open} onOpenChange={(o) => !o && closeThread()}>
      <SheetContent side="right" className="w-full sm:w-[560px] sm:max-w-[720px] p-0 flex flex-col">
        <SheetHeader className="px-6 py-4 border-b border-border/60">
          <SheetTitle className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-brand" />
            <span className="truncate">{title}</span>
            {status && (
              <Badge variant="secondary" className="text-[10px] shrink-0">
                {t(STATUS_LABEL_KEYS[status])}
              </Badge>
            )}
          </SheetTitle>
          <SheetDescription className="flex items-center gap-2 text-xs">
            {status && STATUS_ICONS[status]}
            {node?.agent && <span>{node.agent}</span>}
            {node?.conversation_id && (
              <span className="inline-flex items-center gap-0.5">
                <MessageSquare className="w-3 h-3" />
                {t("subtask.header.independent")}
              </span>
            )}
            {thread.length > 0 && (
              <span>{t("subtask.header.messageCount", { count: thread.length })}</span>
            )}
            <span className="ml-auto font-mono">{(taskNodeId ?? "").slice(0, 8)}…</span>
          </SheetDescription>
        </SheetHeader>

        {profile && (
          <div className="px-6 py-3 border-b border-border/40 bg-muted/20 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-medium">{profile.agent}</span>
              <Badge variant="outline" className="text-[10px] h-4 px-1.5">
                {profile.builtin ? t("subtask.profile.builtin") : t("subtask.profile.custom")}
              </Badge>
              {profile.model && (
                <span className="text-[10px] text-muted-foreground">{profile.model}</span>
              )}
            </div>
            {profile.description && (
              <p className="mt-1 text-muted-foreground">{profile.description}</p>
            )}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {loading && (
            <div className="flex items-center justify-center gap-2 h-32 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              {t("subtask.loading")}
            </div>
          )}

          {!loading && error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-600">
              {t("subtask.errorPrefix", { error })}
            </div>
          )}

          {!loading && !error && conv?.degraded && (
            <DegradedView reason={conv.reason ?? ""} message={conv.message ?? null} />
          )}

          {!loading && !error && !conv?.degraded && thread.length === 0 && (
            <div className="flex items-center justify-center h-32 text-sm text-muted-foreground border border-dashed rounded-lg">
              {t("subtask.empty")}
            </div>
          )}

          {!loading &&
            !error &&
            !conv?.degraded &&
            thread.map((m, i) => {
              const known = m.role in ROLE_STYLES;
              return (
                <div
                  key={i}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-xs whitespace-pre-wrap break-words",
                    known ? ROLE_STYLES[m.role] : ROLE_STYLES.assistant,
                  )}
                >
                  <div className="flex items-center gap-1 text-[10px] text-muted-foreground mb-1">
                    {m.role === "user" ? (
                      <User className="w-3 h-3" />
                    ) : m.role === "tool" ? (
                      <Wrench className="w-3 h-3" />
                    ) : (
                      <Bot className="w-3 h-3" />
                    )}
                    {m.role in ROLE_LABEL_KEYS ? t(ROLE_LABEL_KEYS[m.role]) : m.role}
                  </div>
                  {m.text}
                </div>
              );
            })}
        </div>

        {node && availableSubtaskActions(node.status).canSteer && wsId && taskNodeId ? (
          <div className="px-6 py-3 border-t border-border/60 flex items-center gap-2">
            <Input
              ref={steerInputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing) sendSteer();
              }}
              placeholder={t("subtask.steer.placeholder")}
              className="text-xs h-8"
              disabled={sending}
            />
            <Button
              size="sm"
              className="text-xs h-8 shrink-0"
              disabled={sending || !draft.trim()}
              onClick={sendSteer}
            >
              {sending ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Send className="w-3 h-3" />
              )}
              {t("subtask.steer.send")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-xs h-8 shrink-0"
              disabled={loading}
              onClick={() => setReloadTick((t) => t + 1)}
              title={t("subtask.steer.refreshTitle")}
            >
              <RefreshCw className={cn("w-3 h-3", loading && "animate-spin")} />
            </Button>
          </div>
        ) : (
          <div className="px-6 py-3 border-t border-border/60 flex justify-end">
            <Button
              variant="outline"
              size="sm"
              className="text-xs"
              disabled={!wsId || !taskNodeId || loading}
              onClick={() => setReloadTick((t) => t + 1)}
            >
              <RefreshCw className={cn("w-3 h-3", loading && "animate-spin")} />
              {t("subtask.steer.refresh")}
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

/** 降级视图（shared_conversation / conversation_not_found / 其他） */
function DegradedView({ reason, message }: { reason: string; message: string | null }) {
  const { t } = useTranslation("drawersUi");
  const text =
    reason === "shared_conversation"
      ? t("subtask.degraded.shared")
      : reason === "conversation_not_found"
        ? t("subtask.degraded.notFound")
        : (message ?? t("subtask.degraded.fallback"));
  return (
    <div className="rounded-lg border border-dashed border-border/60 bg-muted/20 p-4 text-xs text-muted-foreground">
      <div className="flex items-center gap-2 mb-1 font-medium text-foreground/80">
        <MessageSquare className="w-3.5 h-3.5" />
        {t("subtask.degraded.title")}
      </div>
      {text}
    </div>
  );
}
