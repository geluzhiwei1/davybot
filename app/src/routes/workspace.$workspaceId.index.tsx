/**
 * Workspace Index Route
 * Route: /workspace/$workspaceId (exact match, no child)
 * Renders the workspace overview: task list, file browser, quick actions.
 */
import { createFileRoute } from "@tanstack/react-router";
import { useStore } from "@/lib/store";
import { WorkspaceOverview } from "@/components/workspace-overview";
import { useShallow } from "zustand/react/shallow";

export const Route = createFileRoute("/workspace/$workspaceId/")({
  component: WorkspaceIndexPage,
});

function WorkspaceIndexPage() {
  const { workspaceId } = Route.useParams();

  const workspace = useStore(useShallow((s) => s.workspaces.find((w) => w.id === workspaceId)));
  const tasks = useStore(useShallow((s) => s.tasks.filter((t) => t.workspaceId === workspaceId)));

  if (!workspace) return null;

  return <WorkspaceOverview workspace={workspace} tasks={tasks} />;
}
