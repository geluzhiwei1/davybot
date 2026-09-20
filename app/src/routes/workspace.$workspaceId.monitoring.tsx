/**
 * Workspace Monitoring Page — 工作区级任务/子任务状态监视。
 * Route: /workspace/$workspaceId/monitoring
 *
 * 作用域(与全局 /monitoring 旧页的根本区别):本页只展示 URL 工作区的
 * 任务委派树状态 —— SubtaskTree 收显式 workspaceId(REST bootstrap 按
 * 该工作区拉取,WS 事件按 store 中该工作区 bucket upsert),不混入
 * 其他并行工作区的数据,也不注入任何演示数据。
 *
 * 入口:工作区概览页「监视」按钮(workspace-overview.tsx),与「追踪」并列。
 */
import { useEffect, useRef } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { FolderOpen } from "lucide-react";
import { useStore } from "@/lib/store";
import { useTabsStore } from "@/lib/tabs-store";
import { SubtaskTree } from "@/components/monitoring";
import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";

export const Route = createFileRoute("/workspace/$workspaceId/monitoring")({
  component: WorkspaceMonitoringPage,
});

function WorkspaceMonitoringPage() {
  const { t } = useTranslation("routesB");
  const { workspaceId } = Route.useParams();

  const workspace = useStore(useShallow((s) => s.workspaces.find((w) => w.id === workspaceId)));
  const openTab = useTabsStore((s) => s.openTab);
  const tabRegistered = useRef(false);

  useEffect(() => {
    if (workspace && !tabRegistered.current) {
      tabRegistered.current = true;
      openTab({
        key: `/workspace/${workspaceId}/monitoring`,
        title: t("workspaceMonitoring.tabTitle", { name: workspace.name }),
        type: "page",
        route: `/workspace/${workspaceId}/monitoring`,
        icon: "network",
        workspaceId,
        workspaceName: workspace.name,
      });
    }
  }, [workspace?.id, workspace?.name, workspaceId, openTab]);

  if (!workspace) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-sm text-muted-foreground">{t("workspaceMonitoring.notFound")}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header(对齐 trace 页) */}
      <div className="border-b border-border px-4 sm:px-6 py-3 shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-md bg-brand/10 border border-brand/30 flex items-center justify-center shrink-0">
            <FolderOpen className="w-3.5 h-3.5 text-brand" />
          </div>
          <div>
            <h1 className="text-sm font-semibold">
              {workspace.name}
              <span className="text-muted-foreground font-normal ml-1">
                {t("workspaceMonitoring.headerSuffix")}
              </span>
            </h1>
          </div>
        </div>
      </div>

      {/* 任务/子任务状态树 —— 显式 scope 到当前工作区 */}
      <div className="flex-1 min-h-0 overflow-auto p-4">
        <div className="max-w-3xl mx-auto">
          <SubtaskTree workspaceId={workspaceId} />
        </div>
      </div>
    </div>
  );
}
