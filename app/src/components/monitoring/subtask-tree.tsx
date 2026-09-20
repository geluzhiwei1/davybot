"use client";
/**
 * SubtaskTree — 子任务委派 UI-A 树面板（§6.3）。
 *
 * 数据流：
 * - 挂载时 REST bootstrap（GET /subtasks）填充存量结构
 * - WS subtask_lifecycle 事件经 subtask-store.applyLifecycle 实时驱动状态迁移
 * - 树由 selectSubtaskTree（纯 selector）组装：根任务子节点为树根，逐层嵌套
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Ban,
  CheckCircle2,
  Circle,
  Loader2,
  MessageSquare,
  MessageSquarePlus,
  RotateCw,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { subtaskApi } from "@/lib/api/subtask";
import { selectSubtaskTree, useSubtaskStore } from "@/lib/subtask-store";
import {
  availableSubtaskActions,
  describeActionResult,
  describeRerunResult,
} from "@/lib/subtask-thread";
import type { SubtaskStatus, SubtaskTreeNode } from "@/lib/types/subtask";
import { wsClient } from "@/lib/ws-client";

const STATUS_ICONS: Record<SubtaskStatus, React.ReactNode> = {
  pending: <Circle className="w-3.5 h-3.5 text-gray-400" />,
  running: <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />,
  completed: <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />,
  failed: <XCircle className="w-3.5 h-3.5 text-red-500" />,
  aborted: <Ban className="w-3.5 h-3.5 text-gray-400" />,
};

const STATUS_COLORS: Record<SubtaskStatus, string> = {
  pending: "border-gray-300 bg-gray-50",
  running: "border-blue-300 bg-blue-50",
  completed: "border-green-300 bg-green-50",
  failed: "border-red-300 bg-red-50",
  aborted: "border-gray-200 bg-gray-50",
};

interface SubtaskTreeProps {
  /** 工作区归属；缺省取 store 中首个非空桶（监控页无工作区上下文） */
  workspaceId?: string;
}

export function SubtaskTree({ workspaceId }: SubtaskTreeProps) {
  const { t } = useTranslation("monitoring");
  const buckets = useSubtaskStore((s) => s.workspaceSubtasks);

  // 活动工作区：显式 prop > store 中首个非空桶
  const activeWs =
    workspaceId ??
    Object.keys(buckets).find((k) => Object.keys(buckets[k] ?? {}).length > 0) ??
    null;
  const nodes = useMemo(() => (activeWs ? (buckets[activeWs] ?? {}) : {}), [buckets, activeWs]);
  const tree = useMemo(() => selectSubtaskTree(nodes), [nodes]);

  // 挂载时 bootstrap 存量子任务（失败静默：等待 WS 实时事件）
  const [bootstrappedWs, setBootstrappedWs] = useState<string | null>(null);
  useEffect(() => {
    const wsId = workspaceId ?? wsClient.getWorkspaceId();
    if (!wsId || wsId === bootstrappedWs) return;
    setBootstrappedWs(wsId);
    subtaskApi
      .list(wsId)
      .then((res) => {
        if (res.success) {
          useSubtaskStore.getState().restoreFromBootstrap(wsId, res.subtasks);
        }
      })
      .catch(() => {
        /* 后端不可达（TUI/离线）→ 树面板退化为纯 WS 驱动 */
      });
  }, [workspaceId, bootstrappedWs]);

  const total = tree.length === 0 ? 0 : Object.keys(nodes).length;
  const completed = Object.values(nodes).filter((n) => n.status === "completed").length;

  return (
    <Card className="py-0">
      <CardHeader className="pb-2 pt-3 px-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium">{t("subtask.title")}</CardTitle>
          <div className="flex items-center gap-2">
            {activeWs && (
              <Badge variant="outline" className="text-[10px] max-w-40 truncate">
                {activeWs}
              </Badge>
            )}
            <Badge variant="outline" className="text-[10px]">
              {t("subtask.completedOf", { completed, total })}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-3 pb-3">
        {tree.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-sm text-muted-foreground border border-dashed rounded-lg">
            {t("subtask.empty")}
          </div>
        ) : (
          <div className="space-y-1.5">
            {tree.map((node) => (
              <SubtaskBranch key={node.task_id} node={node} workspaceId={activeWs ?? ""} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SubtaskBranch({ node, workspaceId }: { node: SubtaskTreeNode; workspaceId: string }) {
  return (
    <div className="space-y-1.5">
      <SubtaskNodeRow node={node} workspaceId={workspaceId} />
      {node.children.length > 0 && (
        <div className="ml-3 pl-3 border-l border-border/60 space-y-1.5">
          {node.children.map((child) => (
            <SubtaskBranch key={child.task_id} node={child} workspaceId={workspaceId} />
          ))}
        </div>
      )}
    </div>
  );
}

function SubtaskNodeRow({ node, workspaceId }: { node: SubtaskTreeNode; workspaceId: string }) {
  const { t } = useTranslation("monitoring");
  const openThread = useSubtaskStore((s) => s.openThread);
  const clickable = workspaceId !== "";

  // UI-D：状态化动作可用性（pending/running → steer+abort；completed → steer+rerun；failed/aborted → rerun）
  const { canSteer, canAbort, canRerun } = availableSubtaskActions(node.status);

  // abort 两步确认（3 秒未二次点击自动复位）
  const [confirmingAbort, setConfirmingAbort] = useState(false);
  const [aborting, setAborting] = useState(false);
  const confirmTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (confirmTimer.current) clearTimeout(confirmTimer.current);
    },
    [],
  );

  const startAbortConfirm = () => {
    setConfirmingAbort(true);
    if (confirmTimer.current) clearTimeout(confirmTimer.current);
    confirmTimer.current = setTimeout(() => setConfirmingAbort(false), 3000);
  };

  const doAbort = async () => {
    if (!workspaceId || aborting) return;
    setAborting(true);
    try {
      const res = await subtaskApi.abort(workspaceId, node.task_id, "user_abort");
      if (res.success) {
        toast.success(describeActionResult("abort", res));
        // 本地即时置灰（幂等；子树级联由后端逐节点 WS 事件补齐）
        useSubtaskStore.getState().applyLifecycle(workspaceId, {
          type: "subtask_lifecycle",
          subtask_id: node.task_id,
          event: "aborted",
        });
      } else {
        toast.error(describeActionResult("abort", res));
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("subtask.abortFailed"));
    } finally {
      setAborting(false);
      setConfirmingAbort(false);
    }
  };

  // P2-D rerun：终态原位重跑（旧结果后端 stash 到 prev_*，非破坏性 → 单击即发，无需两步确认）
  const [rerunning, setRerunning] = useState(false);
  const doRerun = async () => {
    if (!workspaceId || rerunning) return;
    setRerunning(true);
    try {
      const res = await subtaskApi.rerun(workspaceId, node.task_id, "user_rerun");
      if (res.success) {
        toast.success(describeRerunResult(res));
        // 本地即时置 PENDING（幂等；后续 WS 事件补齐真实调度状态）
        useSubtaskStore.getState().applyLifecycle(workspaceId, {
          type: "subtask_lifecycle",
          subtask_id: node.task_id,
          event: "created",
          status: "pending",
        });
      } else {
        toast.error(t("subtask.rerunFailed"));
      }
    } catch (e) {
      // 409（RUNNING/CANCELLED）/404/400 → 后端 detail 透出
      toast.error(e instanceof Error ? e.message : t("subtask.rerunFailed"));
    } finally {
      setRerunning(false);
    }
  };

  const actionBtn =
    "shrink-0 inline-flex items-center gap-0.5 rounded p-1 text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/10 transition-colors disabled:opacity-50";

  return (
    <div
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? () => openThread(workspaceId, node.task_id) : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") openThread(workspaceId, node.task_id);
            }
          : undefined
      }
      title={clickable ? t("subtask.viewThread") : undefined}
      className={cn(
        "group flex items-center gap-2 p-2 rounded-md border text-xs transition-colors",
        STATUS_COLORS[node.status],
        clickable && "cursor-pointer hover:shadow-sm hover:border-border",
      )}
    >
      {STATUS_ICONS[node.status]}
      <div className="min-w-0 flex-1">
        <div className="font-medium truncate">{node.description || node.task_id}</div>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          <span>{t(`subtask.status.${node.status}`)}</span>
          {node.conversation_id && (
            <span className="inline-flex items-center gap-0.5">
              <MessageSquare className="w-3 h-3" />
              {t("subtask.standaloneThread")}
            </span>
          )}
          {node.steerMessages.length > 0 && <span>steer ×{node.steerMessages.length}</span>}
        </div>
      </div>
      {(canSteer || canAbort || canRerun) && (
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
          {canSteer && (
            <button
              type="button"
              className={actionBtn}
              title={t("subtask.sendSteer")}
              onClick={(e) => {
                e.stopPropagation();
                openThread(workspaceId, node.task_id, { focusSteer: true });
              }}
              onKeyDown={(e) => e.stopPropagation()}
            >
              <MessageSquarePlus className="w-3.5 h-3.5" />
            </button>
          )}
          {canAbort &&
            (confirmingAbort ? (
              <button
                type="button"
                className={cn(actionBtn, "text-red-500 hover:text-red-600")}
                title={t("subtask.confirmAbortTitle")}
                disabled={aborting}
                onClick={(e) => {
                  e.stopPropagation();
                  doAbort();
                }}
                onKeyDown={(e) => e.stopPropagation()}
              >
                {aborting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <span className="text-[10px]">{t("subtask.confirmAbortShort")}</span>
                )}
              </button>
            ) : (
              <button
                type="button"
                className={actionBtn}
                title={t("subtask.abortTitle")}
                onClick={(e) => {
                  e.stopPropagation();
                  startAbortConfirm();
                }}
                onKeyDown={(e) => e.stopPropagation()}
              >
                <Ban className="w-3.5 h-3.5" />
              </button>
            ))}
          {canRerun && (
            <button
              type="button"
              className={actionBtn}
              title={t("subtask.rerunTitle")}
              disabled={rerunning}
              onClick={(e) => {
                e.stopPropagation();
                doRerun();
              }}
              onKeyDown={(e) => e.stopPropagation()}
            >
              {rerunning ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <RotateCw className="w-3.5 h-3.5" />
              )}
            </button>
          )}
        </div>
      )}
      {node.agent && (
        <Badge variant="outline" className="text-[10px] shrink-0">
          {node.agent}
        </Badge>
      )}
    </div>
  );
}
