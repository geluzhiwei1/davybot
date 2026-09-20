/**
 * ToolPage — 通用工具頁面骨架。
 *
 * 原 LegalToolPage 抽離而來，複用「工作區列表 + 新建」流程，
 * 通過 ``teamId`` / ``groupLabel`` 適配任意 sidebar 一級組。
 *
 * 用於：法律AI工具、科研助手、深度調研、市場營銷、社媒助手等所有
 * 「以會話為中心、底層是一個 workspace」的工具頁。
 */
import { dateLocale } from "@/lib/date-locale";
import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "@tanstack/react-router";
import {
  Loader2,
  Plus,
  ArrowRight,
  FolderOpen,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Trash2,
  Wand2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { Input } from "@/components/ui/input";
import {
  ToolWizard,
  type ToolWizardConfig,
  type ToolWizardSubmitPayload,
} from "@/components/tool-wizard";
import { setPendingAutoStart } from "@/lib/pending-auto-start";
import { workspaceApi } from "@/lib/api/workspace";
import { useStore } from "@/lib/store";
import { toast } from "sonner";

export interface ToolPageProps {
  /** Agent mode slug for this tool */
  expertId: string;
  /** 業務模塊標識（如 research-original）：創建工作區時固化為 biz_module，
   *  列表按它過濾本模塊的工作區，與工作區名稱徹底解耦（改名不影響歸屬）。 */
  bizModule: string;
  /** 顯示標題，例如「合同起草」 */
  title: string;
  /** 副標題 / 描述 */
  subtitle: string;
  /** 圖標組件 */
  icon: React.ComponentType<{ className?: string }>;
  /** 底層 team 包 ID（market 資源中的 team slug）。決定了安裝哪些 MCP / skill / agent。 */
  teamId: string;
  /** 工作區描述前綴，例如「[法律AI工具]」 / 「[科研助手]」 — 用於工作區列表識別 */
  groupLabel: string;
  /** team 缺失時降級提示文案 */
  fallbackHint?: string;
  /**
   * 跨語言匹配名稱列表。工作區 display_name 在創建時固化為當時界面語言的
   * 標題（如 zh「原創論文」/ en "Original Paper"），若只按當前語言的 title
   * 精確匹配，切換界面語言後列表會「消失」。傳入所有語言的標題即可穩定匹配。
   */
  matchTitles?: string[];
  /**
   * 分步向导配置（对齐产品调研向导的交互）。传入后头部出现「向导启动」按钮：
   * 分步收集需求 → 末步生成可编辑的需求单 → 提交后创建工作区并把需求单
   * 作为开场消息自动发给对应 expert。
   */
  wizard?: ToolWizardConfig;
  /**
   * 直接创建（「新建」按钮，非向导路径）时的开场消息。传入后即使不走向导，
   * 进入工作区也会由 ChatView 自动发出，驱动 agent 先发送开场白/流水线提示，
   * 而不是让用户面对一个静默的空会话（对齐产品调研创建即见概览的体验）。
   */
  directStartPrompt?: string;
}

interface WorkspaceItem {
  id: string;
  name: string;
  display_name?: string;
  /** 创建时固化的工具标识（如「[科研助手] 原创论文」），不随改名变化 */
  description?: string;
  /** 业务模块标识（创建时固化，如 research-original）——本列表的主过滤字段 */
  biz_module?: string;
  created_at: string;
  updated_at?: string;
  lifecycle?: string;
}

/** Relative time formatter, e.g. "3分钟前", "2小时前", "昨天" */
function formatRelativeTime(
  ts: number,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const now = Date.now();
  const diff = now - ts;
  const minute = 60_000;
  const hour = 3_600_000;
  const day = 86_400_000;
  if (diff < minute) return t("toolPage.justNow");
  if (diff < hour) return t("toolPage.minutesAgo", { count: Math.floor(diff / minute) });
  if (diff < day) return t("toolPage.hoursAgo", { count: Math.floor(diff / hour) });
  if (diff < 7 * day) return t("toolPage.daysAgo", { count: Math.floor(diff / day) });
  return new Date(ts).toLocaleDateString(dateLocale());
}

export function ToolPage({
  expertId,
  bizModule,
  title,
  subtitle,
  icon: Icon,
  teamId,
  groupLabel,
  fallbackHint,
  matchTitles,
  wizard,
  directStartPrompt,
}: ToolPageProps) {
  const { t } = useTranslation("commonUi");
  const navigate = useNavigate();
  const getOrCreateEmptyTask = useStore((s) => s.getOrCreateEmptyTask);
  const storeTasks = useStore((s) => s.tasks);
  const renameWorkspace = useStore((s) => s.renameWorkspace);
  const deleteWorkspace = useStore((s) => s.deleteWorkspace);
  const renameTask = useStore((s) => s.renameTask);

  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [showWizard, setShowWizard] = useState(false);

  // Rename / delete dialog state
  const [renameTarget, setRenameTarget] = useState<{ id: string; name: string } | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const fetchWorkspaces = useCallback(async () => {
    setLoading(true);
    try {
      const res = await workspaceApi.listWithTemp();
      // 后端顶层返回 {success, total, workspaces}（无 data 包裹）。
      const all = res.workspaces ?? [];
      // 主过滤：业务模块标识（创建时固化，改名/改描述都不影响归属）。
      // 名称匹配仅为兼容 biz_module 上线前的存量工作区（含已被改名、
      // 只能靠固化的 description 识别的），新工作区一律走 biz_module。
      const names = new Set<string>(matchTitles?.length ? matchTitles : [title]);
      const filtered = all.filter((ws) => {
        if (ws.biz_module) return ws.biz_module === bizModule;
        // legacy 兜底（无 biz_module 的存量工作区）
        return (
          names.has(ws.display_name ?? "") ||
          names.has(ws.name) ||
          [...names].some((n) => (ws.description ?? "").includes(n))
        );
      });
      setWorkspaces(filtered);
    } catch {
      console.error(`[ToolPage:${expertId}] failed to list workspaces`);
    } finally {
      setLoading(false);
    }
  }, [expertId, bizModule, title, matchTitles]);

  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  /**
   * 创建工作区并跳转会话页。向导路径通过 opts 注入：
   * - workspaceName：工作区显示名（缺省用页面标题）
   * - taskTitle：任务重命名（缺省保持「新任务」）
   * - autoStartPrompt：开场消息，经 setPendingAutoStart 由 ChatView 自动发出；
   *   未显式传入时回退 directStartPrompt（覆盖「新建」直接创建的静默空会话）。
   */
  const handleCreate = async (opts?: {
    workspaceName?: string;
    taskTitle?: string;
    autoStartPrompt?: string;
  }) => {
    const startPrompt = opts?.autoStartPrompt?.trim() || directStartPrompt?.trim();
    setCreating(true);
    try {
      const wsName = opts?.workspaceName?.trim() || title;
      // Try createFull with team/{teamId} (installs agent + skills + mcp)
      try {
        const res = await workspaceApi.createFull({
          display_name: wsName,
          description: `[${groupLabel}] ${title}`,
          biz_module: bizModule,
          team_id: `team/${teamId}`,
          team_meta: null,
        });
        if (res.workspace?.id) {
          const task = await getOrCreateEmptyTask({
            workspaceId: res.workspace.id,
            expertId,
          });
          if (opts?.taskTitle?.trim()) renameTask(task.id, opts.taskTitle.trim());
          if (startPrompt) {
            setPendingAutoStart(task.id, startPrompt);
          }
          navigate({
            to: "/workspace/$workspaceId/task/$taskId",
            params: { workspaceId: res.workspace.id, taskId: task.id },
          });
          return;
        }
      } catch {
        // Team install failed — fallback to temp workspace
        toast.warning(fallbackHint ?? t("toolPage.fallbackHintDefault", { label: groupLabel }), {
          description: t("toolPage.fallbackDesc", { teamId }),
        });
      }

      // Fallback: create temp workspace
      const tempRes = await workspaceApi.createTemp(wsName);
      const task = await getOrCreateEmptyTask({
        workspaceId: tempRes.workspace.id,
        expertId,
      });
      if (opts?.taskTitle?.trim()) renameTask(task.id, opts.taskTitle.trim());
      if (startPrompt) {
        setPendingAutoStart(task.id, startPrompt);
      }
      navigate({
        to: "/workspace/$workspaceId/task/$taskId",
        params: { workspaceId: tempRes.workspace.id, taskId: task.id },
      });
    } catch (e) {
      console.error("[ToolPage] create failed:", e);
      toast.error(t("toolPage.createFailed"));
    } finally {
      setCreating(false);
    }
  };

  /** 向导提交：需求单作为开场消息，主题作为工作区/任务名 */
  const handleWizardSubmit = ({ brief, topic }: ToolWizardSubmitPayload) => {
    void handleCreate({
      workspaceName: topic || undefined,
      taskTitle: topic || undefined,
      autoStartPrompt: brief,
    });
  };

  const handleOpenWorkspace = async (wsId: string) => {
    const wsTasks = storeTasks.filter((t) => t.workspaceId === wsId);
    if (wsTasks.length > 0) {
      navigate({
        to: "/workspace/$workspaceId/task/$taskId",
        params: { workspaceId: wsId, taskId: wsTasks[0].id },
      });
    } else {
      const task = await getOrCreateEmptyTask({ workspaceId: wsId, expertId });
      navigate({
        to: "/workspace/$workspaceId/task/$taskId",
        params: { workspaceId: wsId, taskId: task.id },
      });
    }
  };

  const handleRename = () => {
    if (!renameTarget || !renameValue.trim()) return;
    renameWorkspace(renameTarget.id, renameValue.trim());
    // Also update local state for immediate feedback
    setWorkspaces((prev) =>
      prev.map((ws) =>
        ws.id === renameTarget.id
          ? { ...ws, display_name: renameValue.trim(), name: renameValue.trim() }
          : ws,
      ),
    );
    toast.success(t("toolPage.renamed"));
    setRenameTarget(null);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    const { id, name } = deleteTarget;
    await deleteWorkspace(id);
    setWorkspaces((prev) => prev.filter((ws) => ws.id !== id));
    toast.success(t("toolPage.deleted", { name }));
    setDeleteTarget(null);
  };

  /** Compute the most recent activity timestamp for a workspace (from its tasks) */
  const getLastActive = (wsId: string): number => {
    const wsTasks = storeTasks.filter((t) => t.workspaceId === wsId);
    if (wsTasks.length === 0) return 0;
    return Math.max(...wsTasks.map((t) => t.updatedAt || t.createdAt || 0));
  };

  // Sort by last active descending
  const sortedWorkspaces = [...workspaces].sort((a, b) => {
    const aTime = getLastActive(a.id) || new Date(a.created_at).getTime();
    const bTime = getLastActive(b.id) || new Date(b.created_at).getTime();
    return bTime - aTime;
  });

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin">
      {/* 向导模式：整页替换列表视图（对齐产品调研 ProductSurveyHome 的 view 切换） */}
      {showWizard && wizard ? (
        <div className="h-full">
          <ToolWizard
            config={wizard}
            title={title}
            icon={Icon}
            busy={creating}
            onClose={() => setShowWizard(false)}
            onSubmit={handleWizardSubmit}
          />
        </div>
      ) : (
      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div className="w-12 h-12 rounded-xl bg-gradient-brand flex items-center justify-center shadow-brand">
            <Icon className="w-6 h-6 text-brand-foreground" />
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-bold">{title}</h1>
            <p className="text-sm text-muted-foreground">{subtitle}</p>
          </div>
          {wizard && (
            <Button
              variant="outline"
              className="gap-1.5"
              onClick={() => setShowWizard(true)}
              disabled={creating}
            >
              <Wand2 className="w-4 h-4" /> 向导启动
            </Button>
          )}
          <Button className="gap-1.5" onClick={() => void handleCreate()} disabled={creating}>
            {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            {t("toolPage.create")}
          </Button>
        </div>

        {/* Recent workspaces */}
        <div className="mb-3">
          <div className="flex items-center gap-2 mb-3">
            <FolderOpen className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
              {t("toolPage.recentWorkspaces")}
            </h2>
            <Badge variant="secondary" className="text-[10px]">
              {workspaces.length}
            </Badge>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              <span className="text-sm">{t("common.loading")}</span>
            </div>
          ) : sortedWorkspaces.length === 0 ? (
            <div className="bg-card/40 border border-dashed border-border rounded-2xl p-14 text-center">
              <Icon className="w-10 h-10 mx-auto text-muted-foreground/40 mb-3" />
              <p className="text-sm text-muted-foreground mb-4">{t("toolPage.empty", { title })}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {sortedWorkspaces.map((ws) => {
                const wsTasks = storeTasks.filter((t) => t.workspaceId === ws.id);
                const lastActive = getLastActive(ws.id);
                const displayName = ws.display_name || ws.name;
                return (
                  <Card
                    key={ws.id}
                    className="group cursor-pointer hover:border-brand/40 transition"
                    onClick={() => handleOpenWorkspace(ws.id)}
                  >
                    <CardContent className="p-3.5 flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-brand/10 border border-brand/30 flex items-center justify-center shrink-0">
                        <MessageSquare className="w-4 h-4 text-brand" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm truncate">{displayName}</span>
                          {ws.lifecycle === "temporary" && (
                            <Badge
                              variant="outline"
                              className="text-[10px] text-amber-600 border-amber-500/40 bg-amber-500/10"
                            >
                              {t("toolPage.temporary")}
                            </Badge>
                          )}
                          <Badge variant="secondary" className="text-[10px]">
                            {t("toolPage.sessionCount", { count: wsTasks.length })}
                          </Badge>
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">
                          {lastActive > 0
                            ? t("toolPage.updatedAt", { time: formatRelativeTime(lastActive, t) })
                            : t("toolPage.createdAt", {
                                time: formatRelativeTime(new Date(ws.created_at).getTime(), t),
                              })}
                        </div>
                      </div>
                      {/* Actions */}
                      <div
                        className="flex items-center gap-1 shrink-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Button
                          variant="ghost"
                          size="sm"
                          className="gap-1 text-xs h-7 opacity-0 group-hover:opacity-100 transition"
                          onClick={() => handleOpenWorkspace(ws.id)}
                        >
                          {t("toolPage.open")} <ArrowRight className="w-3 h-3" />
                        </Button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 opacity-0 group-hover:opacity-100 transition"
                            >
                              <MoreHorizontal className="w-4 h-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => {
                                setRenameValue(displayName);
                                setRenameTarget({ id: ws.id, name: displayName });
                              }}
                            >
                              <Pencil className="w-3.5 h-3.5 mr-2" /> {t("common.rename")}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => setDeleteTarget({ id: ws.id, name: displayName })}
                            >
                              <Trash2 className="w-3.5 h-3.5 mr-2" /> {t("common.delete")}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      </div>
      )}

      {/* Rename dialog */}
      <Dialog open={!!renameTarget} onOpenChange={(o) => !o && setRenameTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("sidebar.renameWorkspace")}</DialogTitle>
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
            <Button variant="ghost" onClick={() => setRenameTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              className="bg-gradient-brand text-brand-foreground"
              onClick={handleRename}
              disabled={!renameValue.trim()}
            >
              {t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-destructive">
              {t("sidebar.deleteWorkspace.title")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("toolPage.deleteWorkspaceDesc", { name: deleteTarget?.name ?? "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("sidebar.deleteWorkspace.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
