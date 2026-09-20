/**
 * Memory Route — Standalone memory management page.
 * User-level (cross-workspace) and workspace-level memory CRUD.
 * Header pattern matches knowledge.tsx for UI consistency.
 */
import { createFileRoute } from "@tanstack/react-router";
import { useEffect } from "react";
import { Lightbulb, User, FolderOpen } from "lucide-react";
import { MemoryBrowser } from "@/components/memory";
import { useStore } from "@/lib/store";
import { useWorkspaceStore } from "@/lib/workspace-store";
import { useMemoryStore } from "@/lib/memory-store";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/memory")({
  component: MemoryRoute,
});

function MemoryRoute() {
  const { t } = useTranslation("routesB");
  const workspaces = useStore((s) => s.workspaces);
  const fetchWorkspaces = useStore((s) => s.fetchWorkspaces);
  const setWsStore = useWorkspaceStore((s) => s.setWorkspace);
  const { scope, setScope } = useMemoryStore();
  const currentWorkspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);

  // Ensure workspace list is loaded
  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  // Show all workspaces (sorted: persistent first, then by creation time desc)
  const sortedWorkspaces = [...workspaces].sort((a, b) => {
    if ((a.lifecycle === "temporary") !== (b.lifecycle === "temporary")) {
      return a.lifecycle === "temporary" ? 1 : -1;
    }
    return b.createdAt - a.createdAt;
  });

  // Compute Select value
  const selectValue = scope === "workspace" && currentWorkspaceId ? currentWorkspaceId : "__user__";

  const handleChange = (id: string) => {
    if (id === "__user__") {
      setScope("user");
    } else {
      setWsStore(id);
      setScope("workspace");
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header — matches knowledge.tsx layout */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border/60 shrink-0">
        <Lightbulb className="w-5 h-5 text-brand" />
        <h1 className="text-base font-semibold flex-1">{t("memory.title")}</h1>

        <Select value={selectValue} onValueChange={handleChange}>
          <SelectTrigger className="w-40 sm:w-48 h-8 text-xs">
            <SelectValue placeholder={t("memory.selectScope")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__user__" className="text-xs">
              <span className="flex items-center gap-1.5">
                <User className="w-3 h-3" />
                {t("memory.userScope")}
              </span>
            </SelectItem>
            {sortedWorkspaces.map((ws) => (
              <SelectItem key={ws.id} value={ws.id} className="text-xs">
                <span className="flex items-center gap-1.5">
                  <FolderOpen className="w-3 h-3" />
                  {ws.name}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Main content */}
      <div className="flex-1 min-h-0 overflow-hidden p-4">
        <MemoryBrowser />
      </div>
    </div>
  );
}
