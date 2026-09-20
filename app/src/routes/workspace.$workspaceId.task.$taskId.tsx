import { useEffect, useMemo, useRef } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useStore } from "@/lib/store";
import { useTabsStore } from "@/lib/tabs-store";
import { useAgentContext } from "@/lib/use-agent-context";
import type { AgentContextSummary } from "@/lib/agent-context-store";
import { ChatView } from "@/components/chat-view";
import { BIZ_TASK_CHAT_VIEWS } from "@/lib/biz-registry";
import { Button } from "@/components/ui/button";
import { useShallow } from "zustand/react/shallow";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/workspace/$workspaceId/task/$taskId")({
  component: WorkspaceTaskPage,
});

function WorkspaceTaskPage() {
  const { t } = useTranslation("routesB");
  const { workspaceId, taskId } = Route.useParams();

  const task = useStore(useShallow((s) => s.tasks.find((t) => t.id === taskId)));
  const workspace = useStore(useShallow((s) => s.workspaces.find((w) => w.id === workspaceId)));
  const workspacesLoaded = useStore((s) => s.workspacesLoaded);
  const fetchWorkspaces = useStore((s) => s.fetchWorkspaces);
  const fetchTasksForWorkspace = useStore((s) => s.fetchTasksForWorkspace);
  const openTab = useTabsStore((s) => s.openTab);
  const tabRegistered = useRef(false);
  const taskFetchTried = useRef(false);

  // §隔离兜底：确保当前身份的工作区列表已从后端拉取（列表按 owner+tenant 过滤），
  // 深链进入时不能只依赖本地缓存 store —— 见 fetchWorkspaces / workspacesLoaded
  useEffect(() => {
    if (!workspacesLoaded) {
      fetchWorkspaces();
    }
  }, [workspacesLoaded, fetchWorkspaces]);

  // Task-as-Workspace 深链兜底：task 不在 store（如调研页外部创建后跳转 / 冷深链）
  // → 拉取该工作区会话列表一次；仍缺失则维持 notFound
  useEffect(() => {
    taskFetchTried.current = false;
  }, [workspaceId]);
  useEffect(() => {
    if (workspace && !task && !taskFetchTried.current) {
      taskFetchTried.current = true;
      fetchTasksForWorkspace(workspaceId);
    }
  }, [workspace, task, workspaceId, fetchTasksForWorkspace]);

  // biz 注册表命中：工作区专属 ChatView（firm/compliance/ip/deep-research/market/social
  // 等，assemble 注入；核心构建 = 空表 → 不命中，直接走默认 ChatView，行为零漂移）
  const chatEntry = BIZ_TASK_CHAT_VIEWS.find((e) =>
    e.match({ workspaceType: workspace?.workspaceType, name: workspace?.name }),
  );

  // §9.3.2 页面上下文：Dock 据此显示当前页摘要 + 隐藏 FirmAgent 主场的 Dock
  // 必须在早返回之前调用（Rules of Hooks）；task/workspace 未就绪时传 null
  const agentCtx = useMemo<AgentContextSummary | null>(() => {
    if (!task || !workspace) return null;
    if (chatEntry?.agentModule) {
      return {
        module: chatEntry.agentModule,
        entityType: "task",
        entityId: taskId,
        summary:
          task.title || (chatEntry.agentSummaryKey ? t(chatEntry.agentSummaryKey) : workspace.name),
      };
    }
    return {
      module: "workspace-task",
      entityType: "task",
      entityId: taskId,
      summary: task.title || workspace.name,
    };
  }, [task, workspace, chatEntry, taskId]);
  useAgentContext(agentCtx);

  // Register this task as a tab — run once when both task and workspace are available
  useEffect(() => {
    if (task && workspace && !tabRegistered.current) {
      tabRegistered.current = true;
      openTab({
        key: `/workspace/${workspaceId}/task/${taskId}`,
        title: task.title || workspace.name,
        type: "workspace-task",
        workspaceId,
        workspaceName: workspace.name,
        taskId,
      });
    }
  }, [task?.id, task?.title, workspace?.id, workspace?.name, workspaceId, taskId, openTab]);

  // 列表已加载但 workspace 不在其中 → 当前身份（个人/租户）无权访问该工作区
  if (workspacesLoaded && !workspace) {
    return (
      <div className="flex-1 flex items-center justify-center text-center p-6">
        <div>
          <p className="text-muted-foreground mb-1">{t("workspaceTask.noAccess")}</p>
          <p className="text-xs text-muted-foreground mb-3">{t("workspaceTask.noAccessDesc")}</p>
          <Button asChild>
            <Link to="/">{t("workspaceTask.backHome")}</Link>
          </Button>
        </div>
      </div>
    );
  }

  if (!task || !workspace) {
    return (
      <div className="flex-1 flex items-center justify-center text-center p-6">
        <div>
          <p className="text-muted-foreground mb-3">{t("workspaceTask.notFound")}</p>
          <Button asChild>
            <Link to="/">{t("workspaceTask.backHome")}</Link>
          </Button>
        </div>
      </div>
    );
  }

  if (chatEntry) {
    const WorkspaceChatView = chatEntry.component;
    return <WorkspaceChatView task={task} workspace={workspace} />;
  }
  return <ChatView task={task} workspace={workspace} />;
}
