/**
 * Workspace Layout Route
 * Route: /workspace/$workspaceId
 * Serves as the layout shell for nested routes:
 *   - /workspace/$workspaceId             → WorkspaceOverview (index, legacy)
 *   - /workspace/$workspaceId/task/$taskId → ChatView
 *   - /workspace/$workspaceId/trace        → TraceView
 *
 * Single source of truth: always checks the API if store doesn't have the workspace.
 * When found via API, writes it into the store so child routes can access it.
 */
import { createFileRoute, useNavigate, Outlet } from "@tanstack/react-router";
import { useStore } from "@/lib/store";
import { useShallow } from "zustand/react/shallow";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/workspace/$workspaceId")({
  component: WorkspaceLayout,
});

function WorkspaceLayout() {
  const { t } = useTranslation("routesB");
  const { workspaceId } = Route.useParams();

  const workspace = useStore(useShallow((s) => s.workspaces.find((w) => w.id === workspaceId)));
  const loading = useStore((s) => s.loading);
  const fetchWorkspaces = useStore((s) => s.fetchWorkspaces);
  const navigate = useNavigate();
  const fetchedRef = useRef(false);

  // Store 没有 → 从 API 拉取全部 workspaces 列表（一次）
  useEffect(() => {
    if (workspace || fetchedRef.current) return;
    fetchedRef.current = true;
    fetchWorkspaces();
  }, [workspace, fetchWorkspaces]);

  // 还在加载（初始 fetchWorkspaces 或 loading）
  if (!workspace && loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground">
        {t("workspace.loading")}
      </div>
    );
  }

  if (!workspace) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-lg font-semibold">{t("workspace.notFound")}</h2>
          <p className="text-sm text-muted-foreground mt-2">{t("workspace.notFoundDesc")}</p>
          <button
            onClick={() => navigate({ to: "/workspaces", search: { mode: undefined } })}
            className="mt-4 text-sm text-brand hover:underline"
          >
            {t("workspace.backToList")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <Outlet />
    </div>
  );
}
