/**
 * Workspace store — Workspace CRUD and file management.
 * Extracted from store.ts for domain separation.
 */
import { toastError } from "../api/client.js";
import { create } from "zustand";
import { nanoid } from "nanoid";
import { workspaceApi } from "../api-client";

// ── Types (re-exported from store.ts) ──────────────────────────────

export type FileKind = "upload" | "ai";

export interface WorkspaceFile {
  id: string;
  name: string;
  kind: FileKind;
}

export interface Workspace {
  id: string;
  name: string;
  files: WorkspaceFile[];
  createdAt: number;
}

// ── Store ───────────────────────────────────────────────────────────

interface WorkspaceState {
  workspaces: Workspace[];
  fetchWorkspaces: () => Promise<void>;
  createWorkspace: (opts: {
    path: string;
    name?: string;
    displayName?: string;
    description?: string;
    teamId?: string | null;
    teamMeta?: Record<string, unknown> | null;
    skillIds?: string[];
    agentIds?: string[];
    mcpIds?: string[];
    knowledgeIds?: string[];
  }) => Promise<Workspace>;
  renameWorkspace: (id: string, name: string) => void;
  deleteWorkspace: (id: string) => Promise<void>;
  addFile: (workspaceId: string, name: string, kind?: FileKind) => void;
}

export const useWorkspaceStore = create<WorkspaceState>()((set) => ({
  workspaces: [],

  fetchWorkspaces: async () => {
    try {
      const data = await workspaceApi.list();
      if (data.success && data.workspaces) {
        const workspaces: Workspace[] = data.workspaces.map(
          (w: { id: string; name: string; display_name?: string; created_at: string }) => ({
            id: w.id,
            name: w.display_name || w.name,
            files: [],
            createdAt: new Date(w.created_at).getTime(),
          }),
        );
        set({ workspaces });
      }
    } catch (e) {
      console.error("[WorkspaceStore] fetchWorkspaces failed:", e);
      toastError("加载工作区失败", e);
    }
  },

  createWorkspace: async ({
    path,
    name,
    displayName,
    description,
    teamId,
    teamMeta,
    skillIds,
    agentIds,
    mcpIds,
    knowledgeIds,
  }) => {
    const data = await workspaceApi.createFull({
      path,
      name,
      display_name: displayName || undefined,
      description: description || undefined,
      team_id: teamId || undefined,
      team_meta: teamMeta || undefined,
      skill_ids: skillIds?.length ? skillIds : undefined,
      agent_ids: agentIds?.length ? agentIds : undefined,
      mcp_ids: mcpIds?.length ? mcpIds : undefined,
      knowledge_ids: knowledgeIds?.length ? knowledgeIds : undefined,
    });
    const wsData = data.workspace || data;
    const ws: Workspace = {
      id: wsData.id,
      name: wsData.display_name || wsData.name || name || path.split("/").pop() || "工作区",
      files: [],
      createdAt: wsData.created_at ? new Date(wsData.created_at).getTime() : Date.now(),
    };
    set((s) => ({ workspaces: [...s.workspaces, ws] }));
    return ws;
  },

  renameWorkspace: (id, name) =>
    set((s) => ({ workspaces: s.workspaces.map((w) => (w.id === id ? { ...w, name } : w)) })),

  deleteWorkspace: async (id) => {
    try {
      await workspaceApi.delete(id);
    } catch (err: unknown) {
      toastError("删除工作区失败", err);
      return; // keep local state on API failure
    }
    set((s) => ({
      workspaces: s.workspaces.filter((w) => w.id !== id),
    }));
  },

  addFile: (workspaceId, name, kind = "upload") =>
    set((s) => ({
      workspaces: s.workspaces.map((w) =>
        w.id === workspaceId ? { ...w, files: [...w.files, { id: nanoid(6), name, kind }] } : w,
      ),
    })),
}));
