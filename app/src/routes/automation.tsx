/**
 * Automation Route — Cross-workspace scheduled tasks management.
 * Global view showing all tasks from all workspaces.
 */
import { dateLocale } from "@/lib/date-locale";
import { BRAND_NAME } from "@/lib/brand";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, useEffect, useMemo } from "react";
import {
  Workflow,
  Plus,
  Pencil,
  Trash2,
  Play,
  History,
  Loader2,
  AlertCircle,
  X,
  RefreshCw,
  Clock,
  Calendar,
  RotateCw,
  FolderOpen,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { useScheduledTasksStore } from "@/lib/scheduled-tasks-store";
import {
  type ScheduledTask,
  type ScheduledTaskExecution,
  type ScheduleType,
  type TriggerStatus,
  type CreateScheduledTaskRequest,
  type CreateScheduledTaskGlobalRequest,
  workspaceApi,
} from "@/lib/api-client";
import { AUTOMATION_TEMPLATES } from "@/lib/automation-templates";
import { toast } from "sonner";
import { toastError } from "@/lib/api/client.js";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/automation")({
  head: () => ({ meta: [{ title: `定时任务 — ${BRAND_NAME}` }] }),
  component: AutomationPage,
});

// ── Helpers ──────────────────────────────────────────────────────────

const STATUS_LABEL_KEYS: Record<TriggerStatus, string> = {
  pending: "automation.status.pending",
  paused: "automation.status.paused",
  triggered: "automation.status.triggered",
  completed: "automation.status.completed",
  failed: "automation.status.failed",
  cancelled: "automation.status.cancelled",
};

const STATUS_COLOR: Record<TriggerStatus, string> = {
  pending: "bg-blue-500/10 text-blue-600",
  paused: "bg-yellow-500/10 text-yellow-600",
  triggered: "bg-purple-500/10 text-purple-600",
  completed: "bg-green-500/10 text-green-600",
  failed: "bg-red-500/10 text-red-600",
  cancelled: "bg-gray-500/10 text-gray-500",
};

const SCHEDULE_LABEL_KEYS: Record<ScheduleType, string> = {
  delay: "automation.schedule.delay",
  at_time: "automation.schedule.at_time",
  recurring: "automation.schedule.recurring",
  cron: "automation.schedule.cron",
};

function formatTriggerTime(
  t: ScheduledTask,
  tr: (k: string, o?: Record<string, unknown>) => string,
): string {
  const d = new Date(t.trigger_time);
  const local = d.toLocaleString(dateLocale(), { hour12: false });
  if (t.schedule_type === "cron" && t.cron_expression) {
    return `Cron: ${t.cron_expression}`;
  }
  if (t.schedule_type === "delay") {
    return tr("automation.delayAt", { time: local });
  }
  if (t.schedule_type === "recurring") {
    const interval = t.repeat_interval ? `${Math.round(t.repeat_interval / 60)}min` : "?";
    return tr("automation.everyInterval", { interval, time: local });
  }
  return local;
}

// ── Workspace type for selector ──
interface WorkspaceOption {
  id: string;
  name: string;
  display_name?: string;
  lifecycle?: string;
  workspace_type?: string;
}

// ── Main Page ────────────────────────────────────────────────────────

function AutomationPage() {
  const { t } = useTranslation("routesA");
  const navigate = useNavigate();
  const {
    tasks,
    isLoading,
    error,
    executionsCache,
    executionsLoading,
    filterStatus,
    filterScheduleType,
    searchText,
    totalCount,
    currentPage,
    totalPages,
    fetchGlobalTasks,
    createGlobalTask,
    deleteTask,
    pauseTask,
    resumeTask,
    triggerTask,
    fetchExecutions,
    setFilter,
    clearError,
    startPolling,
    stopPolling,
  } = useScheduledTasksStore();

  // Dialog state
  const [formOpen, setFormOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ScheduledTask | null>(null);
  const [executionsTaskId, setExecutionsTaskId] = useState<string | null>(null);
  const [prefilledData, setPrefilledData] = useState<CreateScheduledTaskGlobalRequest | null>(null);

  // Initial load
  useEffect(() => {
    fetchGlobalTasks({ page: 1, page_size: 20 });
  }, [fetchGlobalTasks]);

  // Polling
  useEffect(() => {
    startPolling();
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  // Filtered tasks (client-side)
  const filteredTasks = useMemo(() => {
    let list = tasks;
    if (filterStatus) list = list.filter((t) => t.status === filterStatus);
    if (filterScheduleType) list = list.filter((t) => t.schedule_type === filterScheduleType);
    if (searchText) {
      const q = searchText.toLowerCase();
      list = list.filter(
        (t) =>
          t.description.toLowerCase().includes(q) ||
          t.tags?.some((tag) => tag.toLowerCase().includes(q)) ||
          t.workspace_display_name?.toLowerCase().includes(q),
      );
    }
    return list;
  }, [tasks, filterStatus, filterScheduleType, searchText]);

  // Stats
  const stats = useMemo(
    () => ({
      total: totalCount,
      pending: tasks.filter((t) => t.status === "pending").length,
      paused: tasks.filter((t) => t.status === "paused").length,
      failed: tasks.filter((t) => t.status === "failed").length,
    }),
    [tasks, totalCount],
  );

  // ── Handlers ───────────────────────────────────────────────────────
  const handleCreate = async (data: CreateScheduledTaskGlobalRequest) => {
    try {
      await createGlobalTask(data);
      setFormOpen(false);
      toast.success(t("automation.created"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("automation.createFailed"));
    }
  };

  const handlePause = async (task: ScheduledTask) => {
    try {
      await pauseTask(task.workspace_id, task.task_id);
      toast.success(t("automation.paused"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("automation.actionFailed"));
    }
  };

  const handleResume = async (task: ScheduledTask) => {
    try {
      await resumeTask(task.workspace_id, task.task_id);
      toast.success(t("automation.resumed"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("automation.actionFailed"));
    }
  };

  const handleTrigger = async (task: ScheduledTask) => {
    try {
      await triggerTask(task.workspace_id, task.task_id);
      toast.success(t("automation.triggered"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("automation.triggerFailed"));
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteTask(deleteTarget.workspace_id, deleteTarget.task_id);
      setDeleteTarget(null);
      toast.success(t("automation.deleted"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("automation.deleteFailed"));
    }
  };

  // ── Render ─────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border/60 shrink-0">
        <Workflow className="w-5 h-5 text-brand" />
        <h1 className="text-base font-semibold flex-1">{t("automation.title")}</h1>
        <div className="flex gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => fetchGlobalTasks({ page: currentPage, page_size: 20 })}
            disabled={isLoading}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin")} />
          </Button>
          <Button
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={() => {
              setEditingTask(null);
              setFormOpen(true);
            }}
          >
            <Plus className="h-3.5 w-3.5" />
            {t("automation.newTask")}
          </Button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 min-h-0 overflow-auto p-4">
        {/* Stats bar */}
        <div className="flex items-center gap-4 mb-4 p-3 rounded-lg border bg-card/50">
          <span className="text-xs text-muted-foreground">
            {t("automation.statsAll", { count: stats.total })} |{" "}
            {t("automation.statsPending", { count: stats.pending })} |{" "}
            {t("automation.statsPaused", { count: stats.paused })}
            {stats.failed > 0 && <> | {t("automation.statsFailed", { count: stats.failed })}</>}
          </span>
        </div>

        {/* Toolbar */}
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <Select
            value={filterStatus ?? "all"}
            onValueChange={(v) => setFilter({ status: v === "all" ? undefined : v })}
          >
            <SelectTrigger className="w-28 h-7 text-xs">
              <SelectValue placeholder={t("automation.statusPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("automation.allStatuses")}</SelectItem>
              <SelectItem value="pending">{t("automation.status.pending")}</SelectItem>
              <SelectItem value="paused">{t("automation.status.paused")}</SelectItem>
              <SelectItem value="triggered">{t("automation.status.triggered")}</SelectItem>
              <SelectItem value="completed">{t("automation.status.completed")}</SelectItem>
              <SelectItem value="failed">{t("automation.status.failed")}</SelectItem>
              <SelectItem value="cancelled">{t("automation.status.cancelled")}</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={filterScheduleType ?? "all"}
            onValueChange={(v) => setFilter({ scheduleType: v === "all" ? undefined : v })}
          >
            <SelectTrigger className="w-28 h-7 text-xs">
              <SelectValue placeholder={t("automation.typePlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("automation.allTypes")}</SelectItem>
              <SelectItem value="delay">{t("automation.schedule.delay")}</SelectItem>
              <SelectItem value="at_time">{t("automation.schedule.at_time")}</SelectItem>
              <SelectItem value="recurring">{t("automation.schedule.recurring")}</SelectItem>
              <SelectItem value="cron">Cron</SelectItem>
            </SelectContent>
          </Select>

          <Input
            placeholder={t("automation.searchPlaceholder")}
            className="h-7 text-xs w-40"
            value={searchText}
            onChange={(e) => setFilter({ search: e.target.value })}
          />
        </div>

        {/* Error banner */}
        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive flex items-center gap-2 mb-4">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            {error}
            <Button variant="ghost" size="sm" className="h-5 w-5 p-0 ml-auto" onClick={clearError}>
              <X className="w-3 h-3" />
            </Button>
          </div>
        )}

        {/* Loading */}
        {isLoading && tasks.length === 0 && (
          <div className="flex justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Task cards */}
        {!isLoading && filteredTasks.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <Workflow className="w-12 h-12 mb-4 opacity-20" />
            <p className="text-sm font-medium">
              {tasks.length === 0 ? t("automation.emptyTitle") : t("automation.noMatch")}
            </p>
            <p className="text-xs mt-1">
              {tasks.length === 0 ? t("automation.emptyHint") : t("automation.noMatchHint")}
            </p>
          </div>
        )}

        {filteredTasks.length > 0 && (
          <div className="space-y-2.5 mb-6">
            {filteredTasks.map((t) => (
              <TaskCard
                key={t.task_id}
                task={t}
                onEdit={(task) => {
                  setEditingTask(task);
                  setFormOpen(true);
                }}
                onPause={() => handlePause(t)}
                onResume={() => handleResume(t)}
                onTrigger={() => handleTrigger(t)}
                onDelete={() => setDeleteTarget(t)}
                onExecutions={() => {
                  setExecutionsTaskId(t.task_id);
                  fetchExecutions(t.workspace_id, t.task_id);
                }}
                onNavigate={() =>
                  navigate({
                    to: "/workspace/$workspaceId",
                    params: { workspaceId: t.workspace_id },
                  })
                }
                onViewExecution={(convId) =>
                  navigate({
                    to: "/workspace/$workspaceId/task/$taskId",
                    params: { workspaceId: t.workspace_id, taskId: convId },
                  })
                }
              />
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-1 mb-6">
            <Button
              variant="outline"
              size="sm"
              className="h-7 w-7 p-0"
              disabled={currentPage <= 1}
              onClick={() => useScheduledTasksStore.getState().setPage(currentPage - 1)}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((n) => (
              <Button
                key={n}
                variant={n === currentPage ? "default" : "outline"}
                size="sm"
                className="h-7 w-7 p-0 text-xs"
                onClick={() => useScheduledTasksStore.getState().setPage(n)}
              >
                {n}
              </Button>
            ))}
            <Button
              variant="outline"
              size="sm"
              className="h-7 w-7 p-0"
              disabled={currentPage >= totalPages}
              onClick={() => useScheduledTasksStore.getState().setPage(currentPage + 1)}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        )}

        {/* Templates section */}
        <TemplatesSection
          onUseTemplate={(data) => {
            setEditingTask(null);
            setPrefilledData(data as CreateScheduledTaskGlobalRequest);
            setFormOpen(true);
          }}
        />
      </div>

      {/* Task Form Dialog */}
      <TaskFormDialog
        open={formOpen}
        onOpenChange={(o) => {
          setFormOpen(o);
          if (!o) {
            setEditingTask(null);
            setPrefilledData(null);
          }
        }}
        editingTask={editingTask}
        prefilledData={prefilledData}
        onSubmit={
          editingTask
            ? async (data) => {
                // For editing, use per-workspace API
                const { updateTask } = useScheduledTasksStore.getState();
                await updateTask(
                  editingTask.workspace_id,
                  editingTask.task_id,
                  data as Partial<ScheduledTask>,
                );
                toast.success(t("automation.updated"));
                setFormOpen(false);
                setEditingTask(null);
              }
            : handleCreate
        }
      />

      {/* Execution History Dialog */}
      <ExecutionsDialog
        open={!!executionsTaskId}
        onOpenChange={(o) => {
          if (!o) setExecutionsTaskId(null);
        }}
        executions={executionsTaskId ? (executionsCache[executionsTaskId] ?? []) : []}
        loading={executionsLoading}
        tasks={tasks}
        executionsTaskId={executionsTaskId}
        onViewExecution={(convId, wsId) => {
          navigate({
            to: "/workspace/$workspaceId/task/$taskId",
            params: { workspaceId: wsId, taskId: convId },
          });
        }}
      />

      {/* Delete confirmation */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => {
          if (!o) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("automation.deleteConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("automation.deleteConfirmDesc", { name: deleteTarget?.description ?? "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("automation.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("automation.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// Task Card
// ════════════════════════════════════════════════════════════════════

function TaskCard({
  task,
  onEdit,
  onPause,
  onResume,
  onTrigger,
  onDelete,
  onExecutions,
  onNavigate,
  onViewExecution,
}: {
  task: ScheduledTask;
  onEdit: (t: ScheduledTask) => void;
  onPause: () => void;
  onResume: () => void;
  onTrigger: () => void;
  onDelete: () => void;
  onExecutions: () => void;
  onNavigate: () => void;
  onViewExecution: (convId: string) => void;
}) {
  const { t } = useTranslation("routesA");
  const isPaused = task.status === "paused";

  return (
    <div
      className={cn(
        "group bg-gradient-card border border-border rounded-2xl p-4 flex items-start gap-4 transition-opacity cursor-pointer hover:border-brand/40",
        isPaused && "opacity-60",
      )}
      onClick={onNavigate}
    >
      <ScheduleIcon type={task.schedule_type} />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="font-medium text-sm truncate">{task.description}</h3>
          <Badge variant="outline" className={cn("text-[10px]", STATUS_COLOR[task.status])}>
            {t(STATUS_LABEL_KEYS[task.status])}
          </Badge>
          <Badge variant="secondary" className="text-[10px]">
            {t(SCHEDULE_LABEL_KEYS[task.schedule_type])}
          </Badge>
          {task.tags?.map((tag) => (
            <Badge key={tag} variant="outline" className="text-[10px] px-1.5 py-0">
              {tag}
            </Badge>
          ))}
        </div>

        {/* Workspace info */}
        <div className="flex items-center gap-1.5 mt-1">
          <FolderOpen className="w-3 h-3 text-muted-foreground" />
          <span className="text-xs text-muted-foreground">
            {task.workspace_display_name || task.workspace_name || t("automation.unknownWorkspace")}
          </span>
          {task.is_temp_workspace && (
            <Badge variant="outline" className="text-[10px] px-1 py-0 ml-1">
              {t("automation.temp")}
            </Badge>
          )}
        </div>

        <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
          {task.execution_data.message}
        </p>
        <div className="text-[11px] text-muted-foreground mt-1.5 flex items-center gap-3">
          <span className="flex items-center gap-1">
            {task.schedule_type === "cron" ? (
              <RotateCw className="w-3 h-3" />
            ) : (
              <Clock className="w-3 h-3" />
            )}
            {formatTriggerTime(task, t)}
          </span>
          {task.repeat_count > 0 && (
            <span>{t("automation.executedCount", { count: task.repeat_count })}</span>
          )}
        </div>
        {task.last_error && (
          <p className="text-[11px] text-destructive mt-1 truncate">
            {t("automation.errorPrefix", { error: task.last_error })}
          </p>
        )}

        {/* Last execution link */}
        {task.last_execution_conversation_id && (
          <button
            className="text-[11px] text-brand hover:underline mt-1 block"
            onClick={(e) => {
              e.stopPropagation();
              onViewExecution(task.last_execution_conversation_id!);
            }}
          >
            {t("automation.viewLastExecution")} →
          </button>
        )}
      </div>

      <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
        <Switch checked={!isPaused} onCheckedChange={(on) => (on ? onResume() : onPause())} />
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onTrigger}
          title={t("automation.manualTrigger")}
          disabled={task.status === "triggered" || task.status === "completed"}
        >
          <Play className="w-4 h-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onExecutions}
          title={t("automation.executionHistory")}
        >
          <History className="w-4 h-4" />
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onEdit(task)}>
          <Pencil className="w-4 h-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-destructive hover:text-destructive"
          onClick={onDelete}
        >
          <Trash2 className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}

function ScheduleIcon({ type }: { type: ScheduleType }) {
  const cls = "w-5 h-5 text-brand";
  switch (type) {
    case "cron":
      return <RotateCw className={cls} />;
    case "recurring":
      return <Clock className={cls} />;
    case "at_time":
      return <Calendar className={cls} />;
    default:
      return <Clock className={cls} />;
  }
}

// ════════════════════════════════════════════════════════════════════
// Task Form Dialog (with workspace selector)
// ════════════════════════════════════════════════════════════════════

function TaskFormDialog({
  open,
  onOpenChange,
  editingTask,
  prefilledData,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  editingTask: ScheduledTask | null;
  prefilledData: CreateScheduledTaskGlobalRequest | null;
  onSubmit: (data: CreateScheduledTaskGlobalRequest) => Promise<void>;
}) {
  const [description, setDescription] = useState("");
  const [scheduleType, setScheduleType] = useState<ScheduleType>("at_time");
  const [triggerTime, setTriggerTime] = useState("");
  const [repeatInterval, setRepeatInterval] = useState("");
  const [maxRepeats, setMaxRepeats] = useState("");
  const [cronExpression, setCronExpression] = useState("");
  const [message, setMessage] = useState("");
  const [llm, setLlm] = useState("");
  const [mode, setMode] = useState("");
  const [tags, setTags] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { t } = useTranslation("routesA");

  // Workspace selector state
  const [workspaceMode, setWorkspaceMode] = useState<"auto" | "existing">("auto");
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceOption[]>([]);

  // Fetch workspaces for selector
  useEffect(() => {
    if (open && !editingTask) {
      workspaceApi
        .listWithTemp()
        .then((res) => {
          // 后端顶层返回 {success, total, workspaces}（无 data 包裹）。
          const wsList = res?.workspaces || [];
          setWorkspaces(wsList);
        })
        .catch((e) => {
          toastError(t("automation.wsLoadFailed"), e);
        });
    }
  }, [open, editingTask]);

  // Reset form when editingTask/prefilledData changes
  useEffect(() => {
    if (editingTask) {
      setDescription(editingTask.description);
      setScheduleType(editingTask.schedule_type);
      setTriggerTime(editingTask.trigger_time?.slice(0, 16) ?? "");
      setRepeatInterval(editingTask.repeat_interval?.toString() ?? "");
      setMaxRepeats(editingTask.max_repeats?.toString() ?? "");
      setCronExpression(editingTask.cron_expression ?? "");
      setMessage(editingTask.execution_data.message);
      setLlm(editingTask.execution_data.llm ?? "");
      setMode(editingTask.execution_data.mode ?? "");
      setTags(editingTask.tags?.join(", ") ?? "");
      setWorkspaceMode("existing");
      setSelectedWorkspaceId(editingTask.workspace_id);
    } else if (prefilledData) {
      // Prefill from template data
      setDescription(prefilledData.description ?? "");
      setScheduleType(prefilledData.schedule_type ?? "at_time");
      setTriggerTime(
        prefilledData.trigger_time
          ? new Date(prefilledData.trigger_time).toISOString().slice(0, 16)
          : "",
      );
      setRepeatInterval(prefilledData.repeat_interval?.toString() ?? "");
      setMaxRepeats(prefilledData.max_repeats?.toString() ?? "");
      setCronExpression(prefilledData.cron_expression ?? "");
      setMessage(prefilledData.execution_data?.message ?? "");
      setLlm(prefilledData.execution_data?.llm ?? "");
      setMode(prefilledData.execution_data?.mode ?? "");
      setTags(prefilledData.tags?.join(", ") ?? "");
      setWorkspaceMode("auto");
      setSelectedWorkspaceId(null);
    } else {
      setDescription("");
      setScheduleType("at_time");
      setTriggerTime("");
      setRepeatInterval("");
      setMaxRepeats("");
      setCronExpression("");
      setMessage("");
      setLlm("");
      setMode("");
      setTags("");
      setWorkspaceMode("auto");
      setSelectedWorkspaceId(null);
    }
  }, [editingTask, prefilledData, open]);

  const handleSubmit = async () => {
    if (!description.trim() || !message.trim() || !triggerTime) return;
    setSubmitting(true);
    try {
      const data: CreateScheduledTaskGlobalRequest = {
        description: description.trim(),
        schedule_type: scheduleType,
        trigger_time: new Date(triggerTime).toISOString(),
        execution_type: "message",
        execution_data: {
          message: message.trim(),
          llm: llm.trim() || undefined,
          mode: mode.trim() || undefined,
        },
        tags: tags.trim()
          ? tags
              .split(",")
              .map((t) => t.trim())
              .filter(Boolean)
          : undefined,
        workspace_id: workspaceMode === "existing" ? selectedWorkspaceId : null,
      };
      if (scheduleType === "recurring") {
        if (repeatInterval) data.repeat_interval = parseInt(repeatInterval);
        if (maxRepeats) data.max_repeats = parseInt(maxRepeats);
      }
      if (scheduleType === "cron" && cronExpression.trim()) {
        data.cron_expression = cronExpression.trim();
      }
      await onSubmit(data);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {editingTask ? t("automation.editTask") : t("automation.newScheduledTask")}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3 pt-2 max-h-[60vh] overflow-auto">
          <div>
            <Label className="text-xs">{t("automation.descLabel")}</Label>
            <Input
              className="mt-1 h-8 text-xs"
              placeholder={t("automation.descPlaceholder")}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {/* Workspace selector — only show when creating */}
          {!editingTask && (
            <div>
              <Label className="text-xs">{t("automation.workspaceLabel")}</Label>
              <div className="mt-1 space-y-2">
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    id="ws-auto"
                    name="workspace-mode"
                    checked={workspaceMode === "auto"}
                    onChange={() => setWorkspaceMode("auto")}
                    className="accent-brand"
                  />
                  <label htmlFor="ws-auto" className="text-xs cursor-pointer">
                    {t("automation.autoCreateWorkspace")}
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    id="ws-existing"
                    name="workspace-mode"
                    checked={workspaceMode === "existing"}
                    onChange={() => setWorkspaceMode("existing")}
                    className="accent-brand"
                  />
                  <label htmlFor="ws-existing" className="text-xs cursor-pointer">
                    {t("automation.selectExistingWorkspace")}
                  </label>
                </div>
                {workspaceMode === "existing" && (
                  <Select
                    value={selectedWorkspaceId ?? ""}
                    onValueChange={(v) => setSelectedWorkspaceId(v)}
                  >
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue placeholder={t("automation.selectWorkspace")} />
                    </SelectTrigger>
                    <SelectContent>
                      {workspaces.map((ws) => (
                        <SelectItem key={ws.id} value={ws.id} className="text-xs">
                          {ws.display_name || ws.name}
                          {ws.lifecycle === "temporary" && ` (${t("automation.temp")})`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>
          )}

          <div>
            <Label className="text-xs">{t("automation.scheduleTypeLabel")}</Label>
            <Select value={scheduleType} onValueChange={(v) => setScheduleType(v as ScheduleType)}>
              <SelectTrigger className="mt-1 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="at_time">{t("automation.schedule.at_time")}</SelectItem>
                <SelectItem value="delay">{t("automation.schedule.delay")}</SelectItem>
                <SelectItem value="recurring">{t("automation.schedule.recurring")}</SelectItem>
                <SelectItem value="cron">Cron</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">{t("automation.triggerTimeLabel")}</Label>
            <Input
              className="mt-1 h-8 text-xs"
              type="datetime-local"
              value={triggerTime}
              onChange={(e) => setTriggerTime(e.target.value)}
            />
          </div>
          {scheduleType === "recurring" && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">{t("automation.repeatIntervalLabel")}</Label>
                <Input
                  className="mt-1 h-8 text-xs"
                  type="number"
                  placeholder="3600"
                  value={repeatInterval}
                  onChange={(e) => setRepeatInterval(e.target.value)}
                />
              </div>
              <div>
                <Label className="text-xs">{t("automation.maxRepeatsLabel")}</Label>
                <Input
                  className="mt-1 h-8 text-xs"
                  type="number"
                  placeholder={t("automation.maxRepeatsPlaceholder")}
                  value={maxRepeats}
                  onChange={(e) => setMaxRepeats(e.target.value)}
                />
              </div>
            </div>
          )}
          {scheduleType === "cron" && (
            <div>
              <Label className="text-xs">{t("automation.cronLabel")}</Label>
              <Input
                className="mt-1 h-8 text-xs font-mono"
                placeholder="0 9 * * 1-5"
                value={cronExpression}
                onChange={(e) => setCronExpression(e.target.value)}
              />
            </div>
          )}
          <div>
            <Label className="text-xs">{t("automation.messageLabel")}</Label>
            <Input
              className="mt-1 h-8 text-xs"
              placeholder={t("automation.messagePlaceholder")}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">{t("automation.llmLabel")}</Label>
              <Input
                className="mt-1 h-8 text-xs"
                placeholder={t("automation.optional")}
                value={llm}
                onChange={(e) => setLlm(e.target.value)}
              />
            </div>
            <div>
              <Label className="text-xs">{t("automation.modeLabel")}</Label>
              <Input
                className="mt-1 h-8 text-xs"
                placeholder={t("automation.optional")}
                value={mode}
                onChange={(e) => setMode(e.target.value)}
              />
            </div>
          </div>
          <div>
            <Label className="text-xs">{t("automation.tagsLabel")}</Label>
            <Input
              className="mt-1 h-8 text-xs"
              placeholder={t("automation.tagsPlaceholder")}
              value={tags}
              onChange={(e) => setTags(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter className="pt-2">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            {t("automation.cancel")}
          </Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={
              submitting ||
              !description.trim() ||
              !message.trim() ||
              !triggerTime ||
              (workspaceMode === "existing" && !selectedWorkspaceId)
            }
          >
            {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />}
            {editingTask ? t("automation.save") : t("automation.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ════════════════════════════════════════════════════════════════════
// Execution History Dialog (with clickable rows)
// ════════════════════════════════════════════════════════════════════

function ExecutionsDialog({
  open,
  onOpenChange,
  executions,
  loading,
  tasks,
  executionsTaskId,
  onViewExecution,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  executions: ScheduledTaskExecution[];
  loading: boolean;
  tasks: ScheduledTask[];
  executionsTaskId: string | null;
  onViewExecution: (convId: string, workspaceId: string) => void;
}) {
  const { t } = useTranslation("routesA");
  // 通过精确的 task_id 查找所属任务，获取 workspace_id
  const matchedTask = executionsTaskId ? tasks.find((t) => t.task_id === executionsTaskId) : null;
  const matchedWsId = matchedTask?.workspace_id;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("automation.executionHistory")}</DialogTitle>
        </DialogHeader>
        <div className="max-h-80 overflow-auto">
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : executions.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-8">
              {t("automation.noExecutions")}
            </p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b text-left">
                  <th className="py-2 font-medium text-muted-foreground">
                    {t("automation.colConversationId")}
                  </th>
                  <th className="py-2 font-medium text-muted-foreground">
                    {t("automation.colTitle")}
                  </th>
                  <th className="py-2 font-medium text-muted-foreground">
                    {t("automation.colTriggerTime")}
                  </th>
                  <th className="py-2 font-medium text-muted-foreground text-right">
                    {t("automation.colMessages")}
                  </th>
                  <th className="py-2 font-medium text-muted-foreground text-right">
                    {t("automation.colCount")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {executions.map((ex) => {
                  // 直接使用精确匹配的 workspace_id
                  const wsId = matchedWsId;

                  return (
                    <tr
                      key={ex.conversation_id}
                      className={cn(
                        "border-b last:border-0",
                        wsId && "cursor-pointer hover:bg-muted/50",
                      )}
                      onClick={() => {
                        if (wsId) {
                          onViewExecution(ex.conversation_id, wsId);
                          onOpenChange(false);
                        }
                      }}
                    >
                      <td className="py-2 font-mono text-[10px] truncate max-w-24">
                        {ex.conversation_id.slice(0, 8)}...
                      </td>
                      <td className="py-2 truncate max-w-32">{ex.title}</td>
                      <td className="py-2">
                        {new Date(ex.triggered_at).toLocaleDateString(dateLocale())}
                      </td>
                      <td className="py-2 text-right">{ex.message_count}</td>
                      <td className="py-2 text-right">{ex.repeat_count}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ════════════════════════════════════════════════════════════════════
// Templates Section
// ════════════════════════════════════════════════════════════════════

function TemplatesSection({
  onUseTemplate,
}: {
  onUseTemplate: (data: CreateScheduledTaskRequest) => void;
}) {
  const { t } = useTranslation("routesA");
  return (
    <section>
      <div className="mb-4">
        <h2 className="text-base font-semibold">{t("automation.templatesTitle")}</h2>
        <p className="text-xs text-muted-foreground mt-1">{t("automation.templatesHint")}</p>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {AUTOMATION_TEMPLATES.map((tpl) => {
          const Icon = tpl.icon;
          return (
            <button
              key={tpl.id}
              onClick={() => {
                const triggerTime = tpl.time
                  ? (() => {
                      const today = new Date().toISOString().slice(0, 10);
                      return new Date(`${today}T${tpl.time}:00`).toISOString();
                    })()
                  : new Date(Date.now() + 60000).toISOString();

                const req: CreateScheduledTaskRequest = {
                  description: tpl.name,
                  schedule_type: tpl.frequency === "once" ? "at_time" : "recurring",
                  trigger_time: triggerTime,
                  execution_type: "message",
                  execution_data: {
                    message: tpl.prompt,
                  },
                };
                if (tpl.frequency === "interval") {
                  req.repeat_interval = (tpl.intervalDays ?? 1) * 86400;
                }
                onUseTemplate(req);
              }}
              className="group text-left bg-gradient-card border border-border rounded-2xl p-4 hover:border-brand/40 hover:shadow-brand/10 hover:shadow-md transition-all"
            >
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-muted/60 flex items-center justify-center shrink-0 group-hover:bg-brand/10 transition-colors">
                  <Icon className="w-5 h-5 text-muted-foreground group-hover:text-brand transition-colors" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm truncate">{tpl.name}</div>
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
                    {tpl.desc}
                  </p>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
