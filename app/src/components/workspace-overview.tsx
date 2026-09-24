/**
 * WorkspaceOverview — main content for /workspace/$workspaceId route.
 * Shows workspace header, task list, file browser, and quick actions.
 */
import { dateLocale } from "@/lib/date-locale";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "@tanstack/react-router";
import { useStore, type Task, type Workspace } from "@/lib/store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Loader2,
  FolderOpen,
  Plus,
  MessageSquare,
  Clock,
  ArrowRight,
  FileText,
  Calendar,
  Activity,
  Network,
  ChevronDown,
  ChevronRight,
  Workflow,
} from "lucide-react";
import { groupTasksByParent } from "@/lib/task-grouping";

interface Props {
  workspace: Workspace;
  tasks: Task[];
}

export function WorkspaceOverview({ workspace, tasks }: Props) {
  const { t } = useTranslation("commonUi");
  const navigate = useNavigate();
  const createTask = useStore((s) => s.createTask);
  const getOrCreateEmptyTask = useStore((s) => s.getOrCreateEmptyTask);
  const [loading, setLoading] = useState(false);
  // 任务列表嵌套：父任务行折叠/展开（默认全部折叠）
  const [expandedParents, setExpandedParents] = useState<Set<string>>(new Set());
  const fetchTasksForWorkspaceRef = useRef(useStore.getState().fetchTasksForWorkspace);
  fetchTasksForWorkspaceRef.current = useStore.getState().fetchTasksForWorkspace;

  // 子任务会话折叠进父任务行（taskType=subtask 不再平铺）
  const { groups, orphans } = groupTasksByParent(tasks);
  // 计数口径 = 用户创建的任务（子任务折叠在父行内，不占列表名额）
  const userTaskCount = groups.length;
  const firstUserTask = groups[0]?.parent;

  // Fetch tasks from backend on mount
  useEffect(() => {
    fetchTasksForWorkspaceRef.current(workspace.id);
  }, [workspace.id]);

  // Navigate to a task
  const openTask = (taskId: string) => {
    navigate({
      to: "/workspace/$workspaceId/task/$taskId",
      params: { workspaceId: workspace.id, taskId },
    });
  };

  // Create and navigate to a new task
  const handleNewTask = async () => {
    setLoading(true);
    try {
      const task = await createTask({
        workspaceId: workspace.id,
        title: "新任务",
      });
      openTask(task.id);
    } finally {
      setLoading(false);
    }
  };

  // Quick create a task and navigate to it
  const handleQuickStart = async () => {
    const task = await getOrCreateEmptyTask({ workspaceId: workspace.id });
    openTask(task.id);
  };

  return (
    <div className="flex flex-col h-full">
      {/* ── Workspace Header ── */}
      {/* 设计级收敛(移动端):头部只留标题+追踪图标钮;「新建任务」→ FAB; */}
      {/* 「最近任务」与快捷操作「继续上次」同义(都开 tasks[0]),全局移除。 */}
      <div className="border-b border-border px-4 py-3 sm:px-6 sm:py-4 shrink-0">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-8 h-8 rounded-lg bg-brand/10 border border-brand/30 flex items-center justify-center shrink-0">
                <FolderOpen className="w-4 h-4 text-brand" />
              </div>
              <h1 className="text-xl font-semibold truncate">{workspace.name}</h1>
              <Badge variant="secondary" className="text-[10px] shrink-0">
                {t("wsOverview.taskCount", { count: userTaskCount })}
              </Badge>
              {/* <sm:追踪/监视为图标钮(桌面保留在按钮排) */}
              <div className="flex items-center gap-1 ml-auto sm:hidden">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  aria-label={t("wsOverview.trace")}
                  onClick={() =>
                    navigate({
                      to: "/workspace/$workspaceId/trace",
                      params: { workspaceId: workspace.id },
                    })
                  }
                >
                  <Activity className="w-4 h-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  aria-label={t("wsOverview.monitor")}
                  onClick={() =>
                    navigate({
                      to: "/workspace/$workspaceId/monitoring",
                      params: { workspaceId: workspace.id },
                    })
                  }
                >
                  <Network className="w-4 h-4" />
                </Button>
              </div>
            </div>
            <div className="flex items-center gap-4 mt-2 ml-0 sm:ml-10 flex-wrap">
              <span className="text-[11px] text-muted-foreground inline-flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {t("wsOverview.createdAt", {
                  date: new Date(workspace.createdAt).toLocaleDateString(dateLocale()),
                })}
              </span>
              <span className="text-[11px] text-muted-foreground inline-flex items-center gap-1">
                <FileText className="w-3 h-3" />
                {t("wsOverview.fileCount", { count: workspace.files.length })}
              </span>
            </div>
          </div>
          <div className="hidden sm:flex sm:items-center sm:gap-2 sm:shrink-0">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() =>
                navigate({
                  to: "/workspace/$workspaceId/trace",
                  params: { workspaceId: workspace.id },
                })
              }
            >
              <Activity className="w-3.5 h-3.5" />
              {t("wsOverview.trace")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() =>
                navigate({
                  to: "/workspace/$workspaceId/monitoring",
                  params: { workspaceId: workspace.id },
                })
              }
            >
              <Network className="w-3.5 h-3.5" />
              {t("wsOverview.monitor")}
            </Button>
            <Button size="sm" className="gap-1.5" onClick={handleNewTask} disabled={loading}>
              <Plus className="w-3.5 h-3.5" />
              {loading ? t("wsOverview.creating") : t("wsOverview.createTask")}
            </Button>
          </div>
        </div>
      </div>

      {/* ── Content Area ── */}
      <div className="flex-1 flex min-h-0">
        {/* Left: Task list + quick actions */}
        <div className="flex-1 flex flex-col min-w-0 md:border-r md:border-border">
          {/* Quick actions */}
          <div className="px-4 py-3 sm:px-6 border-b border-border/60">
            <h3 className="text-xs font-medium text-muted-foreground mb-2">
              {t("wsOverview.quickActions")}
            </h3>
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 text-xs h-7"
                onClick={handleQuickStart}
              >
                <MessageSquare className="w-3 h-3" />
                {t("wsOverview.quickStart")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 text-xs h-7"
                onClick={() =>
                  navigate({
                    to: "/workspace/$workspaceId/task/$taskId",
                    params: {
                      workspaceId: workspace.id,
                      taskId: firstUserTask?.id || "",
                    },
                  })
                }
                disabled={!firstUserTask}
              >
                <Clock className="w-3 h-3" />
                {t("wsOverview.continueLast")}
              </Button>
            </div>
          </div>

          {/* Task list */}
          <div className="flex-1 overflow-y-auto px-4 py-4 sm:px-6">
            <h3 className="text-xs font-medium text-muted-foreground mb-3">
              {t("wsOverview.taskList", { count: userTaskCount })}
            </h3>

            {groups.length === 0 && orphans.length === 0 ? (
              <div className="text-center py-12">
                <div className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-muted mb-3">
                  <MessageSquare className="w-5 h-5 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground mb-3">{t("wsOverview.emptyTask")}</p>
                <Button size="sm" className="gap-1.5" onClick={handleNewTask} disabled={loading}>
                  <Plus className="w-3.5 h-3.5" />
                  {t("wsOverview.createTask")}
                </Button>
              </div>
            ) : (
              <div className="space-y-1.5">
                {groups.map(({ parent, children }) => {
                  const expanded = expandedParents.has(parent.id);
                  return (
                    <div
                      key={parent.id}
                      className="rounded-lg border border-border/60 hover:border-brand/30 transition group"
                    >
                      <div className="flex items-center">
                        <button
                          onClick={() => openTask(parent.id)}
                          className="flex-1 min-w-0 text-left px-3 py-2.5"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2.5 min-w-0">
                              <div className="w-7 h-7 rounded-md bg-muted/60 flex items-center justify-center shrink-0">
                                <MessageSquare className="w-3.5 h-3.5 text-muted-foreground" />
                              </div>
                              <div className="min-w-0">
                                <div className="text-sm font-medium truncate">{parent.title}</div>
                                <div className="text-[11px] text-muted-foreground mt-0.5">
                                  {parent.mode === "team"
                                    ? t("wsOverview.teamMode")
                                    : t("wsOverview.soloMode")}
                                  {parent.expertId && ` · ${parent.expertId}`}
                                </div>
                              </div>
                            </div>
                            {children.length > 0 && !expanded && (
                              <span className="text-[10px] text-muted-foreground/80 shrink-0">
                                {t("wsOverview.subtaskCount", { count: children.length })}
                              </span>
                            )}
                          </div>
                        </button>
                        {children.length > 0 && (
                          <button
                            onClick={() =>
                              setExpandedParents((prev) => {
                                const next = new Set(prev);
                                if (next.has(parent.id)) next.delete(parent.id);
                                else next.add(parent.id);
                                return next;
                              })
                            }
                            className="shrink-0 p-2 mr-1 rounded hover:bg-brand/10 text-muted-foreground hover:text-brand transition"
                            aria-label={t("wsOverview.subtaskCount", { count: children.length })}
                          >
                            {expanded ? (
                              <ChevronDown className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronRight className="w-3.5 h-3.5" />
                            )}
                          </button>
                        )}
                      </div>
                      {/* 折叠区：编排器自动创建的子任务会话（嵌套在父任务内部） */}
                      {expanded && children.length > 0 && (
                        <div className="border-t border-border/40 px-3 py-1.5 space-y-0.5">
                          {children.map((sub) => (
                            <button
                              key={sub.id}
                              onClick={() => openTask(sub.id)}
                              className="w-full text-left flex items-center gap-2 px-2 py-1.5 rounded hover:bg-brand/5 transition"
                            >
                              <Workflow className="w-3 h-3 shrink-0 text-muted-foreground/70" />
                              <span className="text-xs truncate text-muted-foreground">
                                {sub.title}
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
                {/* 归属失败的子任务会话：平铺兜底（绝不丢数据） */}
                {orphans.map((task) => (
                  <button
                    key={task.id}
                    onClick={() => openTask(task.id)}
                    className="w-full text-left px-3 py-2.5 rounded-lg border border-border/60 hover:border-brand/30 hover:bg-brand/5 transition group"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-7 h-7 rounded-md bg-muted/60 flex items-center justify-center shrink-0">
                          <Workflow className="w-3.5 h-3.5 text-muted-foreground" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-sm font-medium truncate">{task.title}</div>
                          <div className="text-[11px] text-muted-foreground mt-0.5">
                            {t("wsOverview.subtaskItem")}
                          </div>
                        </div>
                      </div>
                      <ArrowRight className="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition shrink-0" />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: File browser panel(<md 隐藏:任务列独占;文件经任务内/设置抽屉可达) */}
        <div className="hidden md:flex md:w-72 md:shrink-0 md:flex-col">
          <div className="px-4 py-3 border-b border-border/60">
            <h3 className="text-xs font-medium text-muted-foreground">
              {t("wsOverview.fileBrowser")}
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto">
            <WorkspaceOverviewFiles workspace={workspace} />
          </div>
        </div>
      </div>

      {/* 移动端 FAB:新建任务(唯一主操作;避让底部导航 h-14 + 安全区) */}
      <Button
        size="icon"
        aria-label={t("wsOverview.createTask")}
        disabled={loading}
        onClick={handleNewTask}
        className="fixed right-4 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-40 h-14 w-14 rounded-full bg-gradient-brand text-brand-foreground shadow-brand md:hidden"
      >
        {loading ? <Loader2 className="w-6 h-6 animate-spin" /> : <Plus className="w-6 h-6" />}
      </Button>
    </div>
  );
}

/** Simplified file browser for the overview page. */
function WorkspaceOverviewFiles({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation("commonUi");
  if (workspace.files.length === 0) {
    return (
      <div className="p-4 text-center">
        <p className="text-xs text-muted-foreground">{t("common.noFiles")}</p>
        <p className="text-[11px] text-muted-foreground/60 mt-1">{t("wsOverview.uploadHint")}</p>
      </div>
    );
  }

  return (
    <div className="p-2">
      {workspace.files.map((file) => (
        <div
          key={file.id}
          className="flex items-center gap-2 px-2 py-1.5 rounded-md text-xs hover:bg-muted/60 transition cursor-pointer"
        >
          <FileText className="w-3 h-3 text-muted-foreground shrink-0" />
          <span className="truncate">{file.name}</span>
          <Badge variant="outline" className="text-[9px] ml-auto shrink-0">
            {file.kind || "file"}
          </Badge>
        </div>
      ))}
    </div>
  );
}
