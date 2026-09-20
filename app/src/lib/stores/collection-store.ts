/**
 * Collection store — Workspace collection CRUD.
 * Extracted from store.ts for domain separation.
 */
import { toastError } from "../api/client.js";
import { create } from "zustand";
import { collectionApi, type CollectionItem } from "../api-client";

// ── Types (re-exported from store.ts) ──────────────────────────────

export interface WorkspaceCollection {
  id: string;
  name: string;
  description: string;
  workspaceIds: string[];
  createdAt: string;
  updatedAt: string;
}

/** Map backend CollectionItem (snake_case) → frontend WorkspaceCollection (camelCase) */
function mapCollectionItem(c: CollectionItem): WorkspaceCollection {
  return {
    id: c.id,
    name: c.name,
    description: c.description || "",
    workspaceIds: c.workspace_ids || [],
    createdAt: c.created_at,
    updatedAt: c.updated_at,
  };
}

// ── Store ───────────────────────────────────────────────────────────

interface CollectionState {
  collections: WorkspaceCollection[];
  fetchCollections: () => Promise<void>;
  createCollection: (
    name: string,
    description?: string,
    workspaceIds?: string[],
  ) => Promise<WorkspaceCollection>;
  updateCollection: (id: string, patch: { name?: string; description?: string }) => Promise<void>;
  deleteCollection: (id: string) => Promise<void>;
  addWorkspacesToCollection: (collectionId: string, workspaceIds: string[]) => Promise<void>;
  removeWorkspacesFromCollection: (collectionId: string, workspaceIds: string[]) => Promise<void>;
}

export const useCollectionStore = create<CollectionState>()((set) => ({
  collections: [],

  fetchCollections: async () => {
    try {
      const data = await collectionApi.list();
      if (data.success && data.collections) {
        const collections: WorkspaceCollection[] = data.collections.map(mapCollectionItem);
        set({ collections });
      }
    } catch (e) {
      console.error("[CollectionStore] fetchCollections failed:", e);
      toastError("加载收藏夹失败", e);
    }
  },

  createCollection: async (name, description = "", workspaceIds = []) => {
    const data = await collectionApi.create({
      name,
      description,
      workspace_ids: workspaceIds,
    });
    const collection = mapCollectionItem(data.collection);
    set((s) => ({ collections: [...s.collections, collection] }));
    return collection;
  },

  updateCollection: async (id, patch) => {
    const data = await collectionApi.update(id, patch);
    const c = data.collection;
    set((s) => ({
      collections: s.collections.map((col) =>
        col.id === id
          ? { ...col, name: c.name, description: c.description || "", updatedAt: c.updated_at }
          : col,
      ),
    }));
  },

  deleteCollection: async (id) => {
    await collectionApi.delete(id);
    set((s) => ({ collections: s.collections.filter((c) => c.id !== id) }));
  },

  addWorkspacesToCollection: async (collectionId, workspaceIds) => {
    const data = await collectionApi.addWorkspaces(collectionId, workspaceIds);
    const c = data.collection;
    set((s) => ({
      collections: s.collections.map((col) =>
        col.id === collectionId
          ? { ...col, workspaceIds: c.workspace_ids || [], updatedAt: c.updated_at }
          : col,
      ),
    }));
  },

  removeWorkspacesFromCollection: async (collectionId, workspaceIds) => {
    const data = await collectionApi.removeWorkspaces(collectionId, workspaceIds);
    const c = data.collection;
    set((s) => ({
      collections: s.collections.map((col) =>
        col.id === collectionId
          ? { ...col, workspaceIds: c.workspace_ids || [], updatedAt: c.updated_at }
          : col,
      ),
    }));
  },
}));
