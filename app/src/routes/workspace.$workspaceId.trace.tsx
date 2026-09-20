/**
 * Trace View Page
 * Route: /workspace/$workspaceId/trace
 * Shows Agent execution trace waterfall for a workspace.
 */
import { useEffect, useRef } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useStore } from "@/lib/store";
import { useTabsStore } from "@/lib/tabs-store";
import { TraceWaterfall } from "@/components/monitoring/trace-waterfall";
import { useAgentStore } from "@/lib/agent-store";
import { Button } from "@/components/ui/button";
import { Trash2, FolderOpen } from "lucide-react";
import { useShallow } from "zustand/react/shallow";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/workspace/$workspaceId/trace")({
  component: WorkspaceTracePage,
});

function WorkspaceTracePage() {
  const { t } = useTranslation("routesB");
  const { workspaceId } = Route.useParams();

  const workspace = useStore(useShallow((s) => s.workspaces.find((w) => w.id === workspaceId)));
  const openTab = useTabsStore((s) => s.openTab);
  const clearTraceSpans = useAgentStore((s) => s.clearTraceSpans);
  const hasSpans = useAgentStore((s) => {
    const spans = s.workspaceTraceSpans[workspaceId];
    return spans ? spans.length > 0 : false;
  });
  const fetchTraceSpans = useAgentStore((s) => s.fetchTraceSpans);
  const tabRegistered = useRef(false);

  // Fetch trace spans on mount so the page has content even without a live agent execution
  useEffect(() => {
    fetchTraceSpans(workspaceId);
  }, [workspaceId, fetchTraceSpans]);

  useEffect(() => {
    if (workspace && !tabRegistered.current) {
      tabRegistered.current = true;
      openTab({
        key: `/workspace/${workspaceId}/trace`,
        title: t("workspaceTrace.tabTitle", { name: workspace.name }),
        type: "page",
        route: `/workspace/${workspaceId}/trace`,
        icon: "activity",
        workspaceId,
        workspaceName: workspace.name,
      });
    }
  }, [workspace?.id, workspace?.name, workspaceId, openTab]);

  if (!workspace) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-sm text-muted-foreground">{t("workspaceTrace.notFound")}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-border px-4 sm:px-6 py-3 shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-md bg-brand/10 border border-brand/30 flex items-center justify-center shrink-0">
            <FolderOpen className="w-3.5 h-3.5 text-brand" />
          </div>
          <div>
            <h1 className="text-sm font-semibold">
              {workspace.name}
              <span className="text-muted-foreground font-normal ml-1">
                {t("workspaceTrace.headerSuffix")}
              </span>
            </h1>
          </div>
        </div>
        {hasSpans && (
          <Button
            variant="ghost"
            size="sm"
            className="gap-1 text-xs h-7"
            onClick={() => clearTraceSpans(workspaceId)}
          >
            <Trash2 className="w-3 h-3" />
            {t("workspaceTrace.clear")}
          </Button>
        )}
      </div>

      {/* Trace waterfall */}
      <div className="flex-1 min-h-0">
        <TraceWaterfall workspaceId={workspaceId} />
      </div>
    </div>
  );
}
